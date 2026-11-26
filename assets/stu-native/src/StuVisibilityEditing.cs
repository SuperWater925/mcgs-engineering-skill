using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string VisibilityReadAction = "control-visible-read";
        private const string VisibilityEditAction = "control-visible-mode-edit";

        private static bool IsVisibilityAction(string action) {
            return action == VisibilityReadAction || action == VisibilityEditAction;
        }

        private sealed partial class StuDocument {
            private sealed class VisibilitySelection {
                internal IntPtr Control, Animation;
                internal IntPtr[] OriginalAnimationOrder;
                internal int TopIndex, TypeId, AnimationIndex, Mode;
                internal string Name, Expression;
            }

            internal void ApplyVisibility(string action, object rawOptions, Dictionary<string, object> receipt) {
                bool editing = action == VisibilityEditAction;
                if (editing) BeginPageReceipt(receipt);
                try {
                    VerifyFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (editing ? 9 : 6) && options.ContainsKey("top_level_path"),
                        "Stu visibility requires the exact original page, top-level control and animation index.");
                    int pageId = VisibilityIndex(options, "page_id");
                    string pageName = VisibilityText(options, "page", false);
                    int top = VisibilityTopPath(options["top_level_path"]);
                    int type = VisibilityIndex(options, "native_type_id");
                    string name = VisibilityText(options, "control_name", false);
                    int animationIndex = VisibilityIndex(options, "animation_index");
                    Window window = SelectWindow(pageId, pageName);
                    IntPtr document = editing ? GetDocumentForView(window) : PageDocument(window);
                    var before = ReadVisibility(document, top, name, type, animationIndex);
                    receipt["page_id"] = pageId;
                    receipt["page"] = pageName;
                    receipt["record"] = VisibilityRecord(before);
                    if (!editing) return;

                    int oldMode = VisibilityIndex(options, "expected_mode");
                    int newMode = VisibilityIndex(options, "mode");
                    string expression = VisibilityText(options, "expected_expression", true);
                    Require(oldMode <= 1 && newMode <= 1 && before.Mode == oldMode && before.Expression == expression,
                        "The Stu visibility expression or mode differs from the exact preimage.");
                    receipt["before_mode"] = oldMode;
                    receipt["changed"] = oldMode != newMode;
                    if (oldMode != newMode) {
                        var page = new PageWrite(this, window, document, receipt);
                        page.Begin(() => VerifyVisibility(document, before, oldMode));
                        page.RequireActive();
                        int modeOffset = Abi.Offset("visible_mode");
                        int flagOffset = Abi.Offset("visible_owner_flags");
                        // The original property commit stores the mode on this object
                        // and sets bit 0 of the same drawing owner's property flags.
                        int flags = StuNativeProfile.Word(before.Control, flagOffset);
                        receipt["before_owner_flags"] = flags;
                        receipt["operation_phase"] = "write_visibility_mode";
                        Marshal.WriteInt32(before.Animation, modeOffset, newMode);
                        Marshal.WriteInt32(before.Control, flagOffset, flags | 1);
                        receipt["applied_owner_flags"] = StuNativeProfile.Word(before.Control, flagOffset);
                        Require(Object.Equals(receipt["applied_owner_flags"], flags | 1),
                            "The original Stu drawing did not retain its expected change flag.");
                        VerifyVisibility(document, before, newMode);
                        receipt["completed_count"] = 1;
                        page.RefreshAndSave(() => VerifyVisibility(document, before, newMode),
                            () => VerifyVisibility(document, before, newMode));
                        receipt["record"] = VisibilityRecord(ReadVisibility(document, top, name, type, animationIndex));
                    }
                    receipt["operation_phase"] = "complete";
                    receipt["status"] = oldMode == newMode ? "no_changes" : "applied_and_saved";
                } catch (InvalidOperationException error) {
                    if (editing) FailPageWrite(receipt, error);
                    else {
                        receipt["ok"] = false;
                        receipt["status"] = "native_read_rejected";
                        receipt["error"] = error.Message;
                    }
                }
            }

            private VisibilitySelection ReadVisibility(IntPtr document, int index, string name, int type, int slot) {
                var controls = ReadTopLevelControls(document);
                Require(index < controls.Count, "The original Stu top-level control path is absent.");
                IntPtr control = controls[index], complete;
                Abi.Drawing(IntPtr.Add(control, Abi.Offset("control_view_offset")), out complete);
                Require(complete == control && context.Ptr(control, "control_owner") == document &&
                    context.Text(control, "control_name") == name && context.Word(control, "control_type_id") == type,
                    "The original Stu top-level control identity differs.");
                IntPtr array = IntPtr.Add(control, Abi.Offset("visible_control_animation_array"));
                Abi.CheckTable(array, "control_animation_array");
                int count = context.Word(array, "pointer_array_count");
                int capacity = context.Word(array, "pointer_array_capacity");
                IntPtr data = context.Ptr(array, "pointer_array_data");
                Require(slot < count && count <= capacity && count <= Int32.MaxValue / IntPtr.Size &&
                    StuNativeProfile.Readable(data, count * IntPtr.Size, false),
                    "The Stu animation slot or its original array layout differs.");
                var items = new IntPtr[count];
                for (int i = 0; i < count; i++) items[i] = StuNativeProfile.Pointer(data, i * IntPtr.Size);
                IntPtr animation = items[slot];
                Abi.CheckTable(animation, "visible_animation");
                Require(context.Ptr(animation, "visible_animation_owner") == control,
                    "The original Stu CAniVisible owner differs from the selected top-level drawing.");
                return new VisibilitySelection {
                    Control = control, Animation = animation, OriginalAnimationOrder = items,
                    TopIndex = index, TypeId = type, AnimationIndex = slot, Name = name,
                    Expression = context.Text(animation, "visible_expression"), Mode = context.Word(animation, "visible_mode")
                };
            }

            private void VerifyVisibility(IntPtr document, VisibilitySelection expected, int mode) {
                var current = ReadVisibility(document, expected.TopIndex, expected.Name, expected.TypeId, expected.AnimationIndex);
                Require(current.Control == expected.Control && current.Animation == expected.Animation &&
                    current.Expression == expected.Expression && current.Mode == mode &&
                    current.OriginalAnimationOrder.Length == expected.OriginalAnimationOrder.Length,
                    "The original Stu animation identity, expression, mode or collection size differs.");
                for (int i = 0; i < current.OriginalAnimationOrder.Length; i++)
                    Require(current.OriginalAnimationOrder[i] == expected.OriginalAnimationOrder[i],
                        "The Stu original animation list order or ownership changed.");
            }

            private static Dictionary<string, object> VisibilityRecord(VisibilitySelection value) {
                return new Dictionary<string, object> {
                    {"top_level_path", new[] { value.TopIndex }}, {"native_type_id", value.TypeId},
                    {"control_name", value.Name}, {"animation_index", value.AnimationIndex},
                    {"native_class", "CAniVisible"}, {"expression", value.Expression}, {"mode", value.Mode}
                };
            }

            private static int VisibilityIndex(Dictionary<string, object> options, string key) {
                object value;
                Require(options.TryGetValue(key, out value), "Missing Stu visibility index: " + key);
                int index = StuNativeProfile.Number(value);
                Require(index >= 0, "The Stu visibility index is negative: " + key);
                return index;
            }

            private static string VisibilityText(Dictionary<string, object> options, string key, bool allowEmpty) {
                object value;
                Require(options.TryGetValue(key, out value) && value is string, "Missing Stu visibility text: " + key);
                string text = (string)value;
                Require((allowEmpty || text.Length != 0) && text.IndexOf('\0') < 0, "Invalid Stu visibility text: " + key);
                return text;
            }

            private static int VisibilityTopPath(object value) {
                var list = value as IList;
                Require(list != null && list.Count == 1, "Stu visibility requires one exact top-level index.");
                int index = StuNativeProfile.Number(list[0]);
                Require(index >= 0, "The Stu visibility top-level index is negative.");
                return index;
            }
        }
    }
}
