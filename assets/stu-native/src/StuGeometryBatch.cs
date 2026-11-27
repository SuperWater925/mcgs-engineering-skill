using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private static readonly Dictionary<string, RectangleClass> RectangleClasses =
            new Dictionary<string, RectangleClass>(StringComparer.Ordinal) {
                {".?AVCDrawLabel@@", new RectangleClass("control-geometry-label", "label", "set_label_rect")},
                {".?AVCDrawEdit@@", new RectangleClass("control-geometry-edit", "input_control", "set_edit_rect")},
                {".?AVCDrawButton@@", new RectangleClass("control-geometry-button", "standard_button", "set_button_rect")}
            };

        private sealed class RectangleClass {
            internal readonly string Feature, Table, Setter;

            internal RectangleClass(string feature, string table, string setter) {
                Feature = feature;
                Table = table;
                Setter = setter;
            }
        }

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate void SetRectangle(IntPtr self, IntPtr bounds, IntPtr transform);

            private sealed class RectangleChange {
                internal int Index, TypeId;
                internal string Name, Rtti;
                internal IntPtr Control;
                internal int[] Before, After;
                internal SetRectangle Set;
                internal List<object> ShapeStyle;
                internal int ShapeMode;

                internal bool Changed { get { return !EqualRectangle(Before, After); } }
            }

            private int[] ReadRectangle(IntPtr control) {
                return new[] {
                    context.Word(control, "control_left"), context.Word(control, "control_top"),
                    context.Word(control, "control_right"), context.Word(control, "control_bottom")
                };
            }

            internal void ApplyGeometryBatch(int pageId, string name, object rawChanges, Dictionary<string, object> receipt) {
                BeginPageReceipt(receipt);
                Window window = null;
                List<RectangleChange> changes = null;
                IntPtr document = IntPtr.Zero;
                try {
                    changes = ParseGeometry(rawChanges);
                    window = SelectWindow(pageId, name);
                    document = GetDocumentForView(window);
                    var top = ReadTopLevelControls(document);
                    foreach (var edit in changes) {
                        Require(edit.Index < top.Count, "The original Stu top-level control path is absent: " + edit.Name);
                        edit.Control = top[edit.Index];
                        edit.Rtti = ReadControlType(document, edit);
                        Require(EqualRectangle(ReadRectangle(edit.Control), edit.Before),
                            "The actual Stu control rectangle differs from its exact preimage: " + edit.Name);
                        if (!edit.Changed) continue;
                        RectangleClass kind;
                        if (!RectangleClasses.TryGetValue(edit.Rtti, out kind)) {
                            DefaultShapeClass shape;
                            Require(DefaultShapeClasses.TryGetValue(edit.Rtti, out shape) && shape.Factory.TypeId == edit.TypeId,
                                "The selected Stu control has no verified original rectangle setter: " + edit.Rtti);
                            kind = shape.Geometry;
                            Abi.RequireFeature(kind.Feature);
                            CheckOrdinaryControlType(edit.Control, kind, shape.Factory);
                            edit.ShapeMode = context.Word(document, "clone_document_mode");
                            Require(edit.ShapeMode == 0 || edit.ShapeMode == 1,
                                "Stu static shape geometry requires original drawing mode 0 or 1.");
                            edit.ShapeStyle = ReadStaticShapeStyle(edit.Control);
                        }
                        Abi.RequireFeature(kind.Feature);
                        Abi.CheckSlot(edit.Control, kind.Table, 21, kind.Setter);
                        edit.Set = Abi.Bind<SetRectangle>(kind.Setter);
                    }

                    if (!changes.Exists(edit => edit.Changed)) {
                        receipt["changes"] = ObserveGeometry(window, document, changes);
                        receipt["operation_phase"] = "complete";
                        receipt["status"] = "no_changes";
                        return;
                    }

                    var page = new PageWrite(this, window, document, receipt);
                    IntPtr bounds = Marshal.AllocHGlobal(4 * sizeof(int));
                    int completed = 0;
                    try {
                        page.Begin(() => VerifyGeometry(document, changes, false));
                        receipt["operation_phase"] = "write_geometry";
                        foreach (var edit in changes) {
                            if (!edit.Changed) continue;
                            Require(ReadControlType(document, edit) == edit.Rtti &&
                                EqualRectangle(ReadRectangle(edit.Control), edit.Before),
                                "The Stu rectangle or native control identity changed before its assignment: " + edit.Name);
                            VerifyShapeGeometryContext(document, edit);
                            Marshal.Copy(edit.After, 0, bounds, 4);
                            edit.Set(edit.Control, bounds, IntPtr.Zero);
                            Require(ReadControlType(document, edit) == edit.Rtti &&
                                EqualRectangle(ReadRectangle(edit.Control), edit.After),
                                "The Stu original rectangle setter did not return the requested geometry: " + edit.Name);
                            VerifyShapeGeometryContext(document, edit);
                            receipt["completed_count"] = ++completed;
                        }
                        page.RefreshAndSave(() => VerifyGeometry(document, changes, true),
                                            () => VerifyGeometry(document, changes, true));
                    } finally { Marshal.FreeHGlobal(bounds); }
                    receipt["changes"] = ObserveGeometry(window, document, changes);
                    receipt["operation_phase"] = "complete";
                    receipt["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    FailPageWrite(receipt, error);
                    if (document != IntPtr.Zero) receipt["changes"] = ObserveGeometry(window, document, changes);
                }
            }

            private string ReadControlType(IntPtr document, RectangleChange edit) {
                IntPtr control = edit.Control, complete;
                string rtti = Abi.Drawing(IntPtr.Add(control, Abi.Offset("control_view_offset")), out complete);
                Require(control != IntPtr.Zero && complete == control && context.Ptr(control, "control_owner") == document &&
                    context.Word(control, "control_type_id") == edit.TypeId && context.Text(control, "control_name") == edit.Name,
                    "The original Stu geometry target identity differs: " + edit.Name);
                return rtti;
            }

            private void VerifyGeometry(IntPtr document, List<RectangleChange> changes, bool written) {
                var top = ReadTopLevelControls(document);
                foreach (var edit in changes) {
                    Require(edit.Index < top.Count && top[edit.Index] == edit.Control && ReadControlType(document, edit) == edit.Rtti,
                        "The original Stu rectangle target moved to a different path: " + edit.Name);
                    Require(EqualRectangle(ReadRectangle(edit.Control), written ? edit.After : edit.Before),
                        "The original Stu top-level rectangle does not match its expected value: " + edit.Name);
                    VerifyShapeGeometryContext(document, edit);
                }
            }

            private void VerifyShapeGeometryContext(IntPtr document, RectangleChange edit) {
                if (edit.ShapeStyle == null) return;
                Require(context.Word(document, "clone_document_mode") == edit.ShapeMode &&
                    EqualPayload(edit.ShapeStyle, ReadStaticShapeStyle(edit.Control)),
                    "The original Stu shape style or drawing mode changed: " + edit.Name);
            }

            private List<object> ObserveGeometry(Window window, IntPtr document, List<RectangleChange> changes) {
                List<IntPtr> top = null;
                string failure = null;
                try {
                    context.RequireProject();
                    Require(PageDocument(window) == document, "The original Stu geometry page document is no longer current.");
                    top = ReadTopLevelControls(document);
                } catch (InvalidOperationException error) {
                    failure = error.Message;
                }
                var result = new List<object>();
                foreach (var edit in changes) {
                    var row = new Dictionary<string, object> {
                        {"control_name", edit.Name}, {"native_type_id", edit.TypeId}, {"native_class", edit.Rtti},
                        {"top_level_path", new[] { edit.Index }}, {"before", RectangleValue(edit.Before)}, {"actual", null}
                    };
                    try {
                        Require(top != null, failure);
                        Require(edit.Control != IntPtr.Zero && edit.Index < top.Count && top[edit.Index] == edit.Control &&
                            ReadControlType(document, edit) == edit.Rtti,
                            "The original Stu geometry target cannot be read at its selected path.");
                        row["actual"] = RectangleValue(ReadRectangle(edit.Control));
                        if (edit.ShapeStyle != null) {
                            VerifyShapeGeometryContext(document, edit);
                            row["original_style_preserved"] = true;
                        }
                    } catch (InvalidOperationException error) {
                        row["actual_unavailable"] = error.Message;
                    }
                    result.Add(row);
                }
                return result;
            }

            private static List<RectangleChange> ParseGeometry(object raw) {
                var records = raw as IList;
                Require(records != null && records.Count > 0, "Stu geometry changes must be a nonempty JSON array.");
                var changes = new List<RectangleChange>();
                var indices = new HashSet<int>();
                foreach (object record in records) {
                    var row = StuNativeProfile.Map(record);
                    Require(row.Count == 5 && row.ContainsKey("control_name") && row.ContainsKey("native_type_id") &&
                        row.ContainsKey("top_level_path") && row.ContainsKey("before") && row.ContainsKey("after"),
                        "Stu geometry needs the exact top-level path, name, native type and two rectangles.");
                    var path = row["top_level_path"] as IList;
                    Require(path != null && path.Count == 1, "Stu geometry requires exactly one original top-level index.");
                    int index = StuNativeProfile.Number(path[0]);
                    Require(index >= 0 && indices.Add(index), "A Stu geometry path is invalid or selected twice.");
                    int[] before = ParseRectangle(row["before"]);
                    int[] after = ParseRectangle(row["after"]);
                    int typeId = StuNativeProfile.Number(row["native_type_id"]);
                    RequireGeometryBounds(after, typeId);
                    changes.Add(new RectangleChange { Index = index, Name = NativeEngineeringDeliveryLayout.Value(row, "control_name"),
                        TypeId = typeId, Before = before, After = after });
                }
                return changes;
            }

            private static void RequireGeometryBounds(int[] coords, int typeId) {
                long width = (long)coords[2] - coords[0], height = (long)coords[3] - coords[1];
                if (typeId == DefaultLineType)
                    Require((width != 0 || height != 0) && Math.Abs(width) <= Int32.MaxValue && Math.Abs(height) <= Int32.MaxValue,
                        "A Stu line requires distinct ordered endpoints with Int32 axis spans.");
                else
                    Require(width > 0 && width <= Int32.MaxValue && height > 0 && height <= Int32.MaxValue,
                        "The requested Stu rectangle must have a positive width and height within Int32.");
            }

            private static int[] ParseRectangle(object raw) {
                var map = StuNativeProfile.Map(raw);
                Require(map.Count == 1 && map.ContainsKey("rect"), "Stu geometry accepts only original RECT coordinates.");
                var values = map["rect"] as IList;
                Require(values != null && values.Count == 4, "Stu RECT requires four signed coordinates.");
                return new[] { StuNativeProfile.Number(values[0]), StuNativeProfile.Number(values[1]),
                    StuNativeProfile.Number(values[2]), StuNativeProfile.Number(values[3]) };
            }

            private static bool EqualRectangle(int[] first, int[] second) {
                return first[0] == second[0] && first[1] == second[1] && first[2] == second[2] && first[3] == second[3];
            }

            private static Dictionary<string, object> RectangleValue(int[] coords) {
                return new Dictionary<string, object> { {"rect", coords} };
            }
        }
    }
}
