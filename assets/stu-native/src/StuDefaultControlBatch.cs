using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string NativeCreateAction = "control-native-create-batch";

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
            private delegate IntPtr CreateDefaultControl(int typeId);

            private sealed class DefaultCreateChange {
                internal string Rtti, Name;
                internal int[] Rectangle;
                internal TemplateClass Kind;
                internal RectangleClass Geometry;
                internal SetRectangle SetRectangle;
                internal ReleaseDetachedControl Release;
                internal IntPtr Result;
                internal List<object> Defaults;
                internal bool InsertionEntered;
                internal string Phase = "not_started";
            }

            internal void ApplyDefaultCreateBatch(int pageId, string name, object rawChanges, Dictionary<string, object> receipt) {
                BeginPageReceipt(receipt);
                Window window = null;
                IntPtr document = IntPtr.Zero;
                List<DefaultCreateChange> changes = null;
                try {
                    changes = ParseDefaultCreateChanges(rawChanges);
                    foreach (var change in changes) {
                        Abi.RequireFeature(change.Kind.CreateFeature);
                        Abi.RequireFeature(change.Geometry.Feature);
                        change.SetRectangle = Abi.Bind<SetRectangle>(change.Geometry.Setter);
                        change.Release = Abi.Bind<ReleaseDetachedControl>(change.Kind.Delete);
                    }
                    window = SelectWindow(pageId, name);
                    document = GetDocumentForView(window);
                    int mode = context.Word(document, "clone_document_mode");
                    Require(mode == 0 || mode == 1, "Stu default control creation requires original drawing mode 0 or 1.");
                    receipt["original_document_mode"] = mode;
                    var expected = ReadTopLevelControls(document);
                    var occupied = new HashSet<IntPtr>(expected);
                    var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    RecordOccupiedControls(window, occupied, names);
                    var create = Abi.Bind<CreateDefaultControl>("create_default_control");
                    var add = Abi.Bind<InsertTopLevelControl>("insert_top_level_control");
                    var page = new PageWrite(this, window, document, receipt);
                    IntPtr bounds = Marshal.AllocHGlobal(4 * sizeof(int));
                    int completed = 0;
                    try {
                        page.Begin(() => VerifyDefaultCreatePage(document, expected, changes, mode, false));
                        receipt["operation_phase"] = "create_controls";
                        foreach (var change in changes) {
                            page.RequireActive();
                            RequireCreateMode(document, mode);
                            ApplyDefaultCreate(document, change, page, create, add, occupied, names, bounds, mode);
                            expected.Add(change.Result);
                            receipt["completed_count"] = ++completed;
                        }
                        Action verify = () => VerifyDefaultCreatePage(document, expected, changes, mode, true);
                        page.RefreshAndSave(verify, verify);
                    } finally { Marshal.FreeHGlobal(bounds); }
                    receipt["changes"] = ObserveCreatedControls(changes, expected, null, document);
                    receipt["operation_phase"] = "complete";
                    receipt["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    FailPageWrite(receipt, error);
                    if (document != IntPtr.Zero && changes != null)
                        receipt["changes"] = ObservePartialCreate(window, document, changes);
                }
            }

            private void ApplyDefaultCreate(IntPtr document, DefaultCreateChange change, PageWrite page,
                CreateDefaultControl create, InsertTopLevelControl add, HashSet<IntPtr> occupied,
                HashSet<string> names, IntPtr bounds, int mode) {
                bool detached = false;
                try {
                    change.Phase = "factory_entered";
                    IntPtr control = create(change.Kind.TypeId);
                    change.Result = control;
                    Require(control != IntPtr.Zero && !occupied.Contains(control), "The original Stu factory did not return an independent control.");
                    CheckOrdinaryControlType(control, change.Geometry, change.Kind);
                    Abi.CheckSlot(control, change.Geometry.Table, 1, change.Kind.Delete);
                    Require(context.Ptr(control, "control_owner") == IntPtr.Zero,
                        "The original Stu factory unexpectedly returned a control with a page owner.");
                    detached = true;
                    Require(context.Text(control, "control_name").Length == 0,
                        "The original factory did not leave the Stu control name for the page to allocate.");
                    Abi.CheckSlot(control, change.Geometry.Table, 21, change.Geometry.Setter);
                    change.Defaults = ReadOriginalDefaults(control, change.Kind.TypeId);
                    change.Phase = "private_defaults_verified";

                    page.RequireActive();
                    RequireCreateMode(document, mode);
                    change.InsertionEntered = true;
                    change.Phase = "insertion_entered";
                    detached = false;
                    add(document, control);
                    occupied.Add(control);
                    Require(context.Ptr(control, "control_owner") == document,
                        "The new Stu control was not adopted by its original page.");
                    change.Name = context.Text(control, "control_name");
                    Require(change.Name.Length != 0 && names.Add(change.Name), "The original Stu page did not allocate a unique control name.");
                    change.Phase = "adopted";
                    Marshal.Copy(change.Rectangle, 0, bounds, 4);
                    change.SetRectangle(control, bounds, IntPtr.Zero);
                    VerifyCreatedControl(document, change);
                    change.Phase = "geometry_verified";
                } finally {
                    if (detached) {
                        change.Release(change.Result, 1);
                        change.Result = IntPtr.Zero;
                        change.Phase = "private_control_released";
                    }
                }
            }

            private void RequireCreateMode(IntPtr document, int mode) {
                Require(context.Word(document, "clone_document_mode") == mode,
                    "The original Stu drawing mode changed before the new control was adopted.");
            }

            private List<object> ReadOriginalDefaults(IntPtr control, int typeId) {
                var defaults = ReadOrdinaryControlPayload(control, typeId);
                if (typeId == 0x5025)
                    Require(Object.Equals(defaults[0], String.Empty) && Object.Equals(defaults[1], -1) && Object.Equals(defaults[2], 0),
                        "The original default Stu input did not retain its empty variable binding.");
                return defaults;
            }

            private void VerifyCreatedControl(IntPtr document, DefaultCreateChange change) {
                CheckOrdinaryControlType(change.Result, change.Geometry, change.Kind);
                Require(context.Ptr(change.Result, "control_owner") == document && context.Text(change.Result, "control_name") == change.Name &&
                    EqualRectangle(ReadRectangle(change.Result), change.Rectangle) &&
                    EqualPayload(change.Defaults, ReadOriginalDefaults(change.Result, change.Kind.TypeId)),
                    "The new Stu control differs in name, original defaults or requested geometry: " + change.Name);
            }

            private void VerifyDefaultCreatePage(IntPtr document, List<IntPtr> expected, List<DefaultCreateChange> changes,
                int mode, bool complete) {
                RequireCreateMode(document, mode);
                RequireTopSequence(document, expected);
                if (complete) foreach (var change in changes) VerifyCreatedControl(document, change);
            }

            private List<object> ObservePartialCreate(Window window, IntPtr document, List<DefaultCreateChange> changes) {
                List<IntPtr> top = null;
                string reason = null;
                try {
                    context.RequireProject();
                    Require(PageDocument(window) == document, "The original Stu control page document changed.");
                    top = ReadTopLevelControls(document);
                } catch (InvalidOperationException error) { reason = error.Message; }
                return ObserveCreatedControls(changes, top, reason, document);
            }

            private List<object> ObserveCreatedControls(List<DefaultCreateChange> changes, List<IntPtr> top, string reason, IntPtr document) {
                var rows = new List<object>();
                foreach (var change in changes) {
                    var row = new Dictionary<string, object> {
                        {"native_type_id", change.Kind.TypeId}, {"phase", change.Phase}, {"actual", null}
                    };
                    rows.Add(row);
                    if (top == null) { row["actual_unavailable"] = reason; continue; }
                    if (!change.InsertionEntered || change.Result == IntPtr.Zero) continue;
                    int index = top.IndexOf(change.Result);
                    if (index < 0) continue;
                    try {
                        CheckOrdinaryControlType(change.Result, change.Geometry, change.Kind);
                        Require(context.Ptr(change.Result, "control_owner") == document, "The original Stu control owner changed.");
                        row["actual"] = new Dictionary<string, object> {
                            {"top_level_path", new[] { index }}, {"control_name", context.Text(change.Result, "control_name")},
                            {"native_type_id", change.Kind.TypeId}, {"native_class", change.Rtti}, {"rect", ReadRectangle(change.Result)},
                            {"original_defaults_preserved", EqualPayload(change.Defaults, ReadOriginalDefaults(change.Result, change.Kind.TypeId))}
                        };
                    } catch (InvalidOperationException error) { row["actual_unavailable"] = error.Message; }
                }
                return rows;
            }

            private static List<DefaultCreateChange> ParseDefaultCreateChanges(object raw) {
                var values = raw as IList;
                Require(values != null && values.Count != 0, "Stu control creation requires a nonempty JSON changes array.");
                var rows = new List<DefaultCreateChange>();
                foreach (object value in values) {
                    var row = StuNativeProfile.Map(value);
                    Require(row.Count == 2 && row.ContainsKey("native_type_id") && row.ContainsKey("after"),
                        "Stu control creation accepts its original type ID and target rectangle.");
                    int typeId = StuNativeProfile.Number(row["native_type_id"]);
                    var change = new DefaultCreateChange();
                    foreach (var entry in TemplateClasses) {
                        if (entry.Value.TypeId != typeId) continue;
                        change.Rtti = entry.Key;
                        change.Kind = entry.Value;
                        change.Geometry = RectangleClasses[entry.Key];
                        break;
                    }
                    Require(change.Kind != null, "The requested Stu type is not an ordinary label, input or standard button.");
                    change.Rectangle = ParseRectangle(row["after"]);
                    long width = (long)change.Rectangle[2] - change.Rectangle[0];
                    long height = (long)change.Rectangle[3] - change.Rectangle[1];
                    Require(width > 0 && width <= Int32.MaxValue && height > 0 && height <= Int32.MaxValue,
                        "A new Stu control requires positive Int32 width and height.");
                    rows.Add(change);
                }
                return rows;
            }
        }
    }
}
