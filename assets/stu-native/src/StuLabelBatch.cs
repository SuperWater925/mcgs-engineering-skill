using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            private delegate IntPtr AssignText(IntPtr self, IntPtr text);

            private sealed class LabelValues {
                internal string Caption, Primary;
                internal int Color;

                internal void Write(Dictionary<string, object> row) {
                    row["caption"] = Caption;
                    row["caption_primary"] = Primary;
                    row["text_color_bgr"] = Color;
                }

                internal Dictionary<string, object> Map() {
                    var row = new Dictionary<string, object>();
                    Write(row);
                    return row;
                }

                internal bool Matches(LabelValues other) {
                    return Caption == other.Caption && Primary == other.Primary && Color == other.Color;
                }
            }

            private sealed class LabelChange {
                internal string Name;
                internal int TypeId, Index;
                internal IntPtr Control;
                internal LabelValues Before, Wanted;
                internal bool ChangesCaption { get { return Before.Caption != Wanted.Caption || Before.Primary != Wanted.Primary; } }
                internal bool ChangesColor { get { return Before.Color != Wanted.Color; } }
                internal bool IsChanged { get { return ChangesCaption || ChangesColor; } }
            }

            private LabelValues ReadLabel(IntPtr control) {
                return new LabelValues {
                    Caption = context.Text(control, "label_caption"), Primary = context.Text(control, "label_primary_caption"),
                    Color = context.Word(control, "label_text_color")
                };
            }

            private bool IsStaticLabel(IntPtr control) {
                return IntPtr.Zero != control && ReadArrayCount(control, "label_animation_array", "control_animation_array") == 0 &&
                    ReadArrayCount(control, "label_event_array", "control_event_array") == 0;
            }

            private int ReadArrayCount(IntPtr control, string field, string table) {
                IntPtr array = IntPtr.Add(control, Abi.Offset(field));
                Abi.CheckTable(array, table);
                int count = context.Word(array, "pointer_array_count");
                int capacity = context.Word(array, "pointer_array_capacity");
                IntPtr data = context.Ptr(array, "pointer_array_data");
                Require(count >= 0 && capacity >= count && (count == 0 || data != IntPtr.Zero),
                    "The original Stu label array header is invalid.");
                return count;
            }

            internal void ApplyLabelBatch(int pageId, string name, object rawChanges, Dictionary<string, object> receipt) {
                BeginPageReceipt(receipt);

                List<LabelChange> changes = null;
                Window window = null;
                IntPtr document = IntPtr.Zero;
                int completed = 0;
                try {
                    changes = ParseChanges(rawChanges);
                    var targets = new Dictionary<string, LabelChange>(StringComparer.Ordinal);
                    foreach (var edit in changes) {
                        Require(!targets.ContainsKey(edit.Name), "A Stu label was selected twice: " + edit.Name);
                        targets.Add(edit.Name, edit);
                    }
                    window = SelectWindow(pageId, name);
                    document = GetDocumentForView(window);
                    var top = ReadTopLevelControls(document);
                    for (int index = 0; index < top.Count; index++) {
                        IntPtr control = top[index], complete;
                        string rtti = Abi.Drawing(IntPtr.Add(control, Abi.Offset("control_view_offset")), out complete);
                        if (complete != control || context.Ptr(control, "control_owner") != document) continue;
                        LabelChange edit;
                        if (!targets.TryGetValue(context.Text(control, "control_name"), out edit)) continue;
                        Require(edit.Control == IntPtr.Zero && rtti == ".?AVCDrawLabel@@" &&
                            context.Word(control, "control_type_id") == edit.TypeId,
                            "The selected Stu label is ambiguous or its original type changed: " + edit.Name);
                        Abi.CheckTable(control, "label");
                        Require(IsStaticLabel(control), "The selected Stu label has an original animation or event: " + edit.Name);
                        Require(ReadLabel(control).Matches(edit.Before), "The actual Stu label values differ from the preimage: " + edit.Name);
                        edit.Control = control;
                        edit.Index = index;
                    }
                    foreach (var edit in changes)
                        Require(edit.Control != IntPtr.Zero, "No unique top-level Stu label matched: " + edit.Name);
                    if (!changes.Exists(edit => edit.IsChanged)) {
                        receipt["status"] = "no_changes";
                        receipt["changes"] = ObserveChanges(window, document, changes);
                        receipt["operation_phase"] = "complete";
                        return;
                    }
                    var page = new PageWrite(this, window, document, receipt);
                    var assign = Abi.BindImport<AssignText>("assign_label_text");
                    page.Begin(() => {
                        VerifyTopLevelTargets(document, changes);
                        VerifyLabels(document, changes, false);
                    });
                    receipt["operation_phase"] = "write_labels";
                    foreach (var edit in changes) {
                        if (!edit.IsChanged) continue;
                        Require(ReadExactLabel(document, edit).Matches(edit.Before),
                            "The actual Stu label changed before its assignment: " + edit.Name);
                        if (edit.ChangesCaption) {
                            IntPtr text = Marshal.StringToHGlobalUni(edit.Wanted.Caption);
                            try {
                                assign(IntPtr.Add(edit.Control, Abi.Offset("label_primary_caption")), text);
                                assign(IntPtr.Add(edit.Control, Abi.Offset("label_caption")), text);
                            } finally { Marshal.FreeHGlobal(text); }
                        }
                        if (edit.ChangesColor) Marshal.WriteInt32(edit.Control, Abi.Offset("label_text_color"), edit.Wanted.Color);
                        Require(ReadExactLabel(document, edit).Matches(edit.Wanted), "Stu label readback differs: " + edit.Name);
                        receipt["completed_count"] = ++completed;
                    }

                    page.RefreshAndSave(() => VerifyLabels(document, changes, true), () => {
                        VerifyTopLevelTargets(document, changes);
                        VerifyLabels(document, changes, true);
                    });
                    receipt["changes"] = ObserveChanges(window, document, changes);
                    receipt["operation_phase"] = "complete";
                    receipt["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    FailPageWrite(receipt, error);
                    if (document != IntPtr.Zero) receipt["changes"] = ObserveChanges(window, document, changes);
                }
            }

            private LabelValues ReadExactLabel(IntPtr document, LabelChange edit) {
                Abi.CheckTable(edit.Control, "label");
                Require(context.Ptr(edit.Control, "control_owner") == document &&
                    context.Text(edit.Control, "control_name") == edit.Name && context.Word(edit.Control, "control_type_id") == edit.TypeId &&
                    IsStaticLabel(edit.Control), "The original Stu label identity or static state changed: " + edit.Name);
                return ReadLabel(edit.Control);
            }

            private void VerifyLabels(IntPtr document, List<LabelChange> changes, bool written) {
                foreach (var edit in changes)
                    Require(ReadExactLabel(document, edit).Matches(written ? edit.Wanted : edit.Before),
                        "The current Stu label differs from its exact expected values: " + edit.Name);
            }

            private void VerifyTopLevelTargets(IntPtr document, List<LabelChange> changes) {
                var top = ReadTopLevelControls(document);
                foreach (var edit in changes)
                    Require(edit.Index < top.Count && top[edit.Index] == edit.Control,
                        "The original Stu top-level path changed: " + edit.Name);
            }

            private List<object> ObserveChanges(Window window, IntPtr document, List<LabelChange> changes) {
                var result = new List<object>();
                foreach (var edit in changes) {
                    var item = new Dictionary<string, object> {
                        {"control_name", edit.Name}, {"native_type_id", edit.TypeId},
                        {"top_level_path", edit.Control == IntPtr.Zero ? null : new[] { edit.Index }},
                        {"before", edit.Before.Map()}, {"actual", null}
                    };
                    try {
                        context.RequireProject();
                        Require(PageDocument(window) == document, "The original Stu page document is no longer selected.");
                        item["actual"] = ReadExactLabel(document, edit).Map();
                    } catch (InvalidOperationException failure) {
                        item["actual_unavailable"] = failure.Message;
                    }
                    result.Add(item);
                }
                return result;
            }

            private static List<LabelChange> ParseChanges(object raw) {
                var values = raw as IEnumerable;
                Require(values != null && !(raw is string) && !(raw is IDictionary), "Stu label changes must be a JSON array.");
                var changes = new List<LabelChange>();
                foreach (object item in values) {
                    var row = StuNativeProfile.Map(item);
                    Require(row.Count == 4 && row.ContainsKey("control_name") && row.ContainsKey("native_type_id") &&
                        row.ContainsKey("before") && row.ContainsKey("after"), "Stu label change requires its current native identity, before and after.");
                    var before = StuNativeProfile.Map(row["before"]);
                    var after = StuNativeProfile.Map(row["after"]);
                    Require(before.Count == 3 && before.ContainsKey("caption") && before.ContainsKey("caption_primary") &&
                        before.ContainsKey("text_color_bgr") && after.Count > 0 && after.Count <= 2,
                        "Stu label change requires the full current caption, primary caption and color.");
                    var old = new LabelValues { Caption = LabelText(before["caption"]), Primary = LabelText(before["caption_primary"]),
                        Color = StuNativeProfile.Number(before["text_color_bgr"]) };
                    var wanted = new LabelValues { Caption = old.Caption, Primary = old.Primary, Color = old.Color };
                    foreach (var field in after) {
                        if (field.Key == "caption") {
                            Require(old.Caption == old.Primary, "Stu caption write requires the existing visible and primary text to agree.");
                            wanted.Caption = wanted.Primary = LabelText(field.Value);
                        } else if (field.Key == "text_color_bgr") {
                            wanted.Color = StuNativeProfile.Number(field.Value);
                            Require(old.Color >= 0 && old.Color <= 0xffffff && wanted.Color >= 0 && wanted.Color <= 0xffffff,
                                "Stu label color edits require proven 24-bit BGR values for both images.");
                        } else throw new InvalidOperationException("Stu label property is not supported: " + field.Key);
                    }
                    changes.Add(new LabelChange { Name = NativeEngineeringDeliveryLayout.Value(row, "control_name"),
                        TypeId = StuNativeProfile.Number(row["native_type_id"]), Before = old, Wanted = wanted });
                }
                Require(changes.Count > 0, "Stu label batch has no changes.");
                return changes;
            }

            private static string LabelText(object value) {
                var text = value as string;
                Require(text != null && text.Length <= 32768 && text.IndexOf('\0') < 0, "The Stu label value is not a valid native string.");
                try { new UnicodeEncoding(false, false, true).GetByteCount(text); }
                catch (EncoderFallbackException) { throw new InvalidOperationException("The Stu label text contains invalid UTF-16."); }
                return text;
            }
        }
    }
}
