using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private static readonly Dictionary<string, TemplateClass> TemplateClasses =
            new Dictionary<string, TemplateClass>(StringComparer.Ordinal) {
                {".?AVCDrawLabel@@", new TemplateClass(0x5008, "control-clone-label", "control-create-label", "label_view", "serialize_label_clone", "delete_label_clone")},
                {".?AVCDrawEdit@@", new TemplateClass(0x5025, "control-clone-edit", "control-create-edit", "input_control_view", "serialize_edit_clone", "delete_edit_clone")},
                {".?AVCDrawButton@@", new TemplateClass(0x5027, "control-clone-button", "control-create-button", "standard_button_view", "serialize_button_clone", "delete_button_clone")}
            };

        private sealed class TemplateClass {
            internal readonly int TypeId;
            internal readonly string Feature, CreateFeature, Interface, Serialize, Delete;

            internal TemplateClass(int typeId, string feature, string createFeature, string view, string serialize, string delete) {
                TypeId = typeId;
                Feature = feature;
                CreateFeature = createFeature;
                Interface = view;
                Serialize = serialize;
                Delete = delete;
            }
        }

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr CreateTemplateCopy(IntPtr source, IntPtr document);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void InsertTopLevelControl(IntPtr document, IntPtr control);
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr ReleaseDetachedControl(IntPtr control, int free);

            private sealed class CloneChange {
                internal int Index, TypeId;
                internal string Name, Rtti, NewName;
                internal int[] Before, After;
                internal IntPtr Source, Result;
                internal TemplateClass Kind;
                internal RectangleClass Geometry;
                internal SetRectangle SetRectangle;
                internal ReleaseDetachedControl Delete;
                internal List<object> Payload;
                internal bool InsertionEntered;
                internal string Phase = "not_started";
            }

            internal void ApplyTemplateCloneBatch(int pageId, string name, object rawChanges, Dictionary<string, object> receipt) {
                BeginPageReceipt(receipt);
                Window window = null;
                List<CloneChange> changes = null;
                IntPtr document = IntPtr.Zero;
                try {
                    changes = ParseCloneChanges(rawChanges);
                    window = SelectWindow(pageId, name);
                    document = GetDocumentForView(window);
                    int mode = context.Word(document, "clone_document_mode");
                    Require(mode == 0 || mode == 1, "This Stu template clone requires original drawing mode 0 or 1.");
                    receipt["original_document_mode"] = mode;
                    RequireArchiveAvailable();
                    var top = ReadTopLevelControls(document);
                    var expected = new List<IntPtr>(top);
                    var existingControls = new HashSet<IntPtr>(top);
                    var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    RecordOccupiedControls(window, existingControls, names);
                    foreach (var edit in changes) PrepareCloneSource(document, top, edit);
                    var copy = Abi.Bind<CreateTemplateCopy>("clone_control");
                    var add = Abi.Bind<InsertTopLevelControl>("insert_top_level_control");
                    var page = new PageWrite(this, window, document, receipt);
                    IntPtr bounds = Marshal.AllocHGlobal(4 * sizeof(int));
                    int completed = 0;
                    try {
                        page.Begin(() => VerifyClonePage(document, expected, changes, mode, false));
                        receipt["operation_phase"] = "copy_templates";
                        foreach (var edit in changes) {
                            page.RequireActive();
                            VerifyCloneSource(document, edit);
                            Require(context.Word(document, "clone_document_mode") == mode,
                                "The original Stu drawing mode changed before copying.");
                            RequireArchiveAvailable();
                            ApplyClone(document, edit, expected, existingControls, names, copy, add, page, bounds, mode);
                            receipt["completed_count"] = ++completed;
                        }
                        page.RefreshAndSave(() => VerifyClonePage(document, expected, changes, mode, true),
                                            () => VerifyClonePage(document, expected, changes, mode, true));
                    } finally { Marshal.FreeHGlobal(bounds); }
                    receipt["changes"] = ObserveClones(window, document, changes);
                    receipt["operation_phase"] = "complete";
                    receipt["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    FailPageWrite(receipt, error);
                    if (document != IntPtr.Zero) receipt["changes"] = ObserveClones(window, document, changes);
                }
            }

            private void PrepareCloneSource(IntPtr document, List<IntPtr> top, CloneChange edit) {
                Require(edit.Index < top.Count, "The original Stu template source path is absent: " + edit.Name);
                edit.Source = top[edit.Index];
                IntPtr complete;
                edit.Rtti = Abi.Drawing(IntPtr.Add(edit.Source, Abi.Offset("control_view_offset")), out complete);
                Require(complete == edit.Source && TemplateClasses.TryGetValue(edit.Rtti, out edit.Kind) &&
                    RectangleClasses.TryGetValue(edit.Rtti, out edit.Geometry) && edit.Kind.TypeId == edit.TypeId,
                    "The selected Stu template source is not one of the verified original top-level classes.");
                Abi.RequireFeature(edit.Kind.Feature);
                Abi.RequireFeature(edit.Geometry.Feature);
                CheckCloneType(edit.Source, edit);
                Abi.CheckSlot(edit.Source, edit.Geometry.Table, 28, "clone_control");
                Abi.CheckSlot(edit.Source, edit.Geometry.Table, 21, edit.Geometry.Setter);
                edit.SetRectangle = Abi.Bind<SetRectangle>(edit.Geometry.Setter);
                edit.Delete = Abi.Bind<ReleaseDetachedControl>(edit.Kind.Delete);
                edit.Payload = ReadOrdinaryControlPayload(edit.Source, edit.TypeId);
                VerifyCloneSource(document, edit);
            }

            private void ApplyClone(IntPtr document, CloneChange edit, List<IntPtr> expected, HashSet<IntPtr> existingControls,
                HashSet<string> names, CreateTemplateCopy copy, InsertTopLevelControl add, PageWrite page, IntPtr bounds, int mode) {
                bool mayDelete = false;
                try {
                    edit.Phase = "factory_entered";
                    IntPtr current = copy(edit.Source, document);
                    edit.Result = current;
                    Require(current != IntPtr.Zero && !existingControls.Contains(current),
                        "The Stu clone factory did not return an independent control.");
                    RequireArchiveAvailable();
                    CheckCloneType(current, edit);
                    IntPtr owner = context.Ptr(current, "control_owner");
                    Require(owner == IntPtr.Zero || owner == document, "The original Stu private copy belongs to another page.");
                    RequireTopSequence(document, expected);
                    mayDelete = true;
                    edit.Phase = "private_copy_verified";
                    edit.NewName = context.Text(current, "control_name");
                    Require(edit.NewName.Length != 0 && names.Add(edit.NewName), "The original Stu clone did not receive a new unique name.");
                    Require(EqualRectangle(ReadRectangle(current), edit.Before) &&
                        EqualPayload(edit.Payload, ReadOrdinaryControlPayload(current, edit.TypeId)),
                        "The original Stu private copy differs from the current template.");
                    VerifyCloneSource(document, edit);
                    Abi.CheckSlot(current, edit.Geometry.Table, 21, edit.Geometry.Setter);
                    page.RequireActive();
                    Require(context.Word(document, "clone_document_mode") == mode,
                        "The original Stu drawing mode changed before adoption.");
                    edit.Phase = "insertion_entered";
                    edit.InsertionEntered = true;
                    mayDelete = false;
                    add(document, current);
                    expected.Add(current);
                    RequireTopSequence(document, expected);
                    existingControls.Add(current);
                    Require(context.Ptr(current, "control_owner") == document && context.Text(current, "control_name") == edit.NewName,
                        "The new Stu template copy was not adopted by its original page with its allocated name.");
                    edit.Phase = "adopted";
                    Marshal.Copy(edit.After, 0, bounds, 4);
                    edit.SetRectangle(current, bounds, IntPtr.Zero);
                    VerifyAdoptedClone(document, edit);
                    edit.Phase = "geometry_verified";
                } finally {
                    if (mayDelete) {
                        edit.Delete(edit.Result, 1);
                        edit.Result = IntPtr.Zero;
                        edit.Phase = "private_copy_released";
                    }
                }
            }

            private void CheckCloneType(IntPtr control, CloneChange edit) {
                CheckOrdinaryControlType(control, edit.Geometry, edit.Kind);
                Abi.CheckSlot(control, edit.Geometry.Table, 2, edit.Kind.Serialize);
                Abi.CheckSlot(control, edit.Geometry.Table, 1, edit.Kind.Delete);
            }

            private void CheckOrdinaryControlType(IntPtr control, RectangleClass geometry, TemplateClass kind) {
                Abi.CheckTable(control, geometry.Table);
                Abi.CheckTable(IntPtr.Add(control, Abi.Offset("control_view_offset")), kind.Interface);
                Require(context.Word(control, "control_type_id") == kind.TypeId,
                    "The original Stu control type ID differs from its bound class.");
            }

            private void RecordOccupiedControls(Window window, HashSet<IntPtr> controls, HashSet<string> names) {
                VisitControls(window, (index, control, rtti, owned) => {
                    if (owned) {
                        controls.Add(control);
                        names.Add(context.Text(control, "control_name"));
                    }
                });
            }

            private void VerifyCloneSource(IntPtr document, CloneChange edit) {
                CheckCloneType(edit.Source, edit);
                Require(context.Ptr(edit.Source, "control_owner") == document && context.Text(edit.Source, "control_name") == edit.Name &&
                    EqualRectangle(ReadRectangle(edit.Source), edit.Before) &&
                    EqualPayload(edit.Payload, ReadOrdinaryControlPayload(edit.Source, edit.TypeId)),
                    "The current Stu template source no longer matches its exact original state: " + edit.Name);
            }

            private void VerifyAdoptedClone(IntPtr document, CloneChange edit) {
                CheckCloneType(edit.Result, edit);
                Require(context.Ptr(edit.Result, "control_owner") == document && context.Text(edit.Result, "control_name") == edit.NewName &&
                    EqualRectangle(ReadRectangle(edit.Result), edit.After) &&
                    EqualPayload(edit.Payload, ReadOrdinaryControlPayload(edit.Result, edit.TypeId)),
                    "The adopted Stu clone differs in original payload or requested geometry: " + edit.Name);
            }

            private void VerifyClonePage(IntPtr document, List<IntPtr> expected, List<CloneChange> changes, int mode, bool complete) {
                Require(context.Word(document, "clone_document_mode") == mode, "The original Stu drawing mode changed.");
                RequireArchiveAvailable();
                RequireTopSequence(document, expected);
                foreach (var edit in changes) {
                    Require(edit.Index < expected.Count && expected[edit.Index] == edit.Source,
                        "The original Stu template source moved to another path.");
                    VerifyCloneSource(document, edit);
                    if (complete) VerifyAdoptedClone(document, edit);
                }
            }

            private void RequireTopSequence(IntPtr document, List<IntPtr> expected) {
                var current = ReadTopLevelControls(document);
                Require(current.Count == expected.Count, "The current Stu top-level list has an unexpected size.");
                for (int i = 0; i < expected.Count; i++)
                    Require(current[i] == expected[i], "The current Stu top-level list differs from its exact original prefix.");
            }

            private void RequireArchiveAvailable() {
                Require(Abi.GlobalWord("clone_archive_busy") == 0, "The original Stu control-copy archive is busy.");
            }

            private List<object> ReadOrdinaryControlPayload(IntPtr control, int typeId) {
                Require(IsStaticLabel(control), "Stu ordinary controls need empty event and animation arrays for this action.");
                if (typeId == 0x5008) {
                    var values = ReadLabel(control);
                    return new List<object> { values.Caption, values.Primary, values.Color };
                }
                if (typeId == 0x5025)
                    return new List<object> { context.Text(control, "input_variable"),
                        context.Word(control, "clone_input_word_0"), context.Word(control, "clone_input_word_1") };

                var result = new List<object>();
                for (int i = 0; i < 4; i++) AddActionArray(result, control, "clone_button_words_" + i, "button_word_array", false);
                for (int i = 0; i < 2; i++) AddActionArray(result, control, "clone_button_strings_" + i, "button_text_array", true);
                result.Add(context.Text(control, "clone_button_condition_0"));
                result.Add(context.Text(control, "clone_button_condition_1"));
                return result;
            }

            private void AddActionArray(List<object> output, IntPtr control, string field, string table, bool text) {
                IntPtr array = IntPtr.Add(control, Abi.Offset(field));
                Abi.CheckTable(array, table);
                Require(context.Word(array, "pointer_array_count") == 8 && context.Word(array, "pointer_array_capacity") >= 8,
                    "The original Stu standard button action array has an unsupported shape.");
                IntPtr data = context.Ptr(array, "pointer_array_data");
                for (int i = 0; i < 8; i++) output.Add(text ? (object)StuNativeProfile.Text(data, 4 * i) : StuNativeProfile.Word(data, 4 * i));
            }

            private List<object> ObserveClones(Window window, IntPtr document, List<CloneChange> changes) {
                List<IntPtr> top = null;
                string reason = null;
                try {
                    context.RequireProject();
                    Require(PageDocument(window) == document, "The original Stu clone page document changed.");
                    top = ReadTopLevelControls(document);
                } catch (InvalidOperationException error) { reason = error.Message; }
                var rows = new List<object>();
                foreach (var edit in changes) {
                    var row = new Dictionary<string, object> {
                        {"top_level_path", new[] { edit.Index }}, {"control_name", edit.Name}, {"native_type_id", edit.TypeId},
                        {"before", RectangleValue(edit.Before)}, {"phase", edit.Phase}, {"actual", null}
                    };
                    rows.Add(row);
                    if (top == null) { row["actual_unavailable"] = reason; continue; }
                    if (!edit.InsertionEntered || edit.Result == IntPtr.Zero) continue;
                    int index = top.IndexOf(edit.Result);
                    if (index < 0) continue;
                    try {
                        CheckCloneType(edit.Result, edit);
                        Require(context.Ptr(edit.Result, "control_owner") == document, "The original Stu clone owner changed.");
                        row["actual"] = new Dictionary<string, object> {
                            {"top_level_path", new[] { index }}, {"control_name", context.Text(edit.Result, "control_name")},
                            {"native_type_id", edit.TypeId}, {"native_class", edit.Rtti}, {"rect", ReadRectangle(edit.Result)},
                            {"original_payload_preserved", EqualPayload(edit.Payload, ReadOrdinaryControlPayload(edit.Result, edit.TypeId))}
                        };
                    } catch (InvalidOperationException error) { row["actual_unavailable"] = error.Message; }
                }
                return rows;
            }

            private static List<CloneChange> ParseCloneChanges(object raw) {
                var values = raw as IList;
                Require(values != null && values.Count != 0, "Stu template clone requires a nonempty JSON changes array.");
                var rows = new List<CloneChange>();
                foreach (object value in values) {
                    var row = StuNativeProfile.Map(value);
                    Require(row.Count == 5 && row.ContainsKey("top_level_path") && row.ContainsKey("control_name") &&
                        row.ContainsKey("native_type_id") && row.ContainsKey("before") && row.ContainsKey("after"),
                        "Stu template clone requires the exact source identity and original/target rectangles.");
                    var path = row["top_level_path"] as IList;
                    Require(path != null && path.Count == 1, "Stu template clone needs one original top-level index.");
                    int index = StuNativeProfile.Number(path[0]);
                    Require(index >= 0, "The original Stu template path is invalid.");
                    int[] before = ParseRectangle(row["before"]), after = ParseRectangle(row["after"]);
                    long width = (long)after[2] - after[0], height = (long)after[3] - after[1];
                    Require(width > 0 && width <= Int32.MaxValue && height > 0 && height <= Int32.MaxValue,
                        "The Stu template copy requires positive Int32 width and height.");
                    rows.Add(new CloneChange { Index = index, Name = NativeEngineeringDeliveryLayout.Value(row, "control_name"),
                        TypeId = StuNativeProfile.Number(row["native_type_id"]), Before = before, After = after });
                }
                return rows;
            }

            private static bool EqualPayload(List<object> first, List<object> second) {
                if (first.Count != second.Count) return false;
                for (int i = 0; i < first.Count; i++) if (!Object.Equals(first[i], second[i])) return false;
                return true;
            }
        }
    }
}
