using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string PagePropertiesReadAction = "page-properties-read";
        private const string PageBackgroundEditAction = "page-background-edit";

        private static bool IsPagePropertiesAction(string action) {
            return action == PagePropertiesReadAction || action == PageBackgroundEditAction;
        }

        private sealed partial class StuDocument {
            private sealed class PageDisplayProperties {
                internal readonly int Width, Height, Background;

                internal PageDisplayProperties(int width, int height, int background) {
                    Width = width;
                    Height = height;
                    Background = background;
                }

                internal Dictionary<string, object> Receipt(Window window) {
                    return new Dictionary<string, object> {
                        {"page_id", window.Id}, {"page", window.Name},
                        {"width", Width}, {"height", Height},
                        {"background_color_bgr", unchecked((uint)Background)}
                    };
                }
            }

            internal void ApplyPageProperties(string action, object rawOptions, Dictionary<string, object> receipt) {
                bool editing = action == PageBackgroundEditAction;
                if (editing) BeginPageReceipt(receipt);
                Window window = null;
                IntPtr doc = IntPtr.Zero;
                try {
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (editing ? 4 : 2) &&
                        options.ContainsKey("page_id") && options.ContainsKey("page") &&
                        (!editing || options.ContainsKey("before") && options.ContainsKey("after")),
                        "Stu page properties require its exact page ID and name, and a background preimage to edit.");
                    int id = StuNativeProfile.Number(options["page_id"]);
                    Require(id >= 0, "The Stu page ID is invalid.");
                    window = SelectWindow(id, NativeEngineeringDeliveryLayout.Value(options, "page"));
                    doc = GetDocumentForView(window);
                    PageDisplayProperties before = ReadDisplayProperties(window, doc);
                    receipt["page_properties"] = before.Receipt(window);
                    if (!editing) return;

                    int expected = ReadOrdinaryBackground(options["before"]);
                    int desired = ReadOrdinaryBackground(options["after"]);
                    Require(before.Background == expected, "The original Stu background COLORREF differs from the preimage.");
                    receipt["before"] = before.Receipt(window);
                    if (expected == desired) {
                        receipt["status"] = "no_changes";
                        receipt["operation_phase"] = "verified_no_changes";
                        return;
                    }

                    Abi.CheckSlot(doc, "page_display_document", 102, "page_background_dialog_entry");
                    var write = new PageWrite(this, window, doc, receipt);
                    write.Begin(() => VerifyDisplayProperties(window, doc, before, expected));
                    write.RequireActive();
                    receipt["operation_phase"] = "set_background";
                    // The guarded original property dialog copies its COLORREF to
                    // this DWORD. Drawing reads it on each repaint, so reuse the
                    // original drawing refresh and save without entering the dialog.
                    Marshal.WriteInt32(doc, Abi.Offset("page_background_color"), desired);
                    VerifyDisplayProperties(window, doc, before, desired);
                    receipt["completed_count"] = 1;
                    Action verify = () => VerifyDisplayProperties(window, doc, before, desired);
                    write.RefreshAndSave(verify, verify);
                    receipt["page_properties"] = ReadDisplayProperties(window, doc).Receipt(window);
                    receipt["status"] = "applied_and_saved";
                    receipt["operation_phase"] = "verified_saved";
                } catch (InvalidOperationException error) {
                    if (!editing) throw;
                    FailPageWrite(receipt, error);
                    if (window != null && doc != IntPtr.Zero) {
                        try { receipt["page_properties"] = ReadDisplayProperties(window, doc).Receipt(window); }
                        catch (InvalidOperationException) { receipt.Remove("page_properties"); }
                    }
                }
            }

            private PageDisplayProperties ReadDisplayProperties(Window window, IntPtr doc) {
                context.RequireProject();
                Require(PageDocument(window) == doc, "The current Stu page document changed.");
                Abi.CheckSlot(doc, "page_display_document", 2, "page_property_archive_entry");
                int width = context.Word(doc, "page_logical_width"), height = context.Word(doc, "page_logical_height");
                Require(width > 0 && height > 0, "The original Stu logical page dimensions are invalid.");
                return new PageDisplayProperties(width, height, context.Word(doc, "page_background_color"));
            }

            private void VerifyDisplayProperties(Window window, IntPtr doc, PageDisplayProperties before, int background) {
                PageDisplayProperties current = ReadDisplayProperties(window, doc);
                Require(current.Width == before.Width && current.Height == before.Height,
                    "The original Stu logical page dimensions changed during background editing.");
                Require(current.Background == background, "The original Stu background COLORREF did not match the expected value.");
            }

            private static int ReadOrdinaryBackground(object value) {
                var fields = StuNativeProfile.Map(value);
                Require(fields.Count == 1 && fields.ContainsKey("background_color_bgr"),
                    "Only the original background COLORREF can be changed.");
                int color = StuNativeProfile.Number(fields["background_color_bgr"]);
                Require(color >= 0 && color <= 0xffffff, "Stu background editing requires an ordinary 24-bit COLORREF.");
                return color;
            }
        }
    }
}
