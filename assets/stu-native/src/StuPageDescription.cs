using System;
using System.Collections.Generic;
using System.Text;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string PageDescriptionReadAction = "page-description-read";
        private const string PageDescriptionEditAction = "page-description-edit";

        private static bool IsPageDescriptionAction(string action) {
            return action == PageDescriptionReadAction || action == PageDescriptionEditAction;
        }

        private sealed partial class StuDocument {
            private static readonly UnicodeEncoding PageDescriptionEncoding = new UnicodeEncoding(false, false, true);

            internal void ApplyPageDescription(string action, object rawOptions, Dictionary<string, object> receipt) {
                bool editing = action == PageDescriptionEditAction;
                if (editing) BeginPageReceipt(receipt);
                Window window = null;
                IntPtr document = IntPtr.Zero;
                try {
                    VerifyFeature(Abi, action);
                    var options = StuNativeProfile.Map(rawOptions);
                    Require(options.Count == (editing ? 4 : 2) &&
                        options.ContainsKey("page_id") && options.ContainsKey("page") &&
                        (!editing || options.ContainsKey("before") && options.ContainsKey("after")),
                        "Stu page description requires its exact page ID and name, and a description preimage to edit.");
                    int id = StuNativeProfile.Number(options["page_id"]);
                    Require(id >= 0, "The Stu page ID is invalid.");
                    window = SelectWindow(id, NativeEngineeringDeliveryLayout.Value(options, "page"));
                    document = GetDocumentForView(window);
                    string original = ReadPageDescription(window, document);
                    receipt["page_description"] = DescriptionRecord(window, original);
                    if (!editing) return;

                    string expected = ReadDescriptionOption(options["before"]);
                    string desired = ReadDescriptionOption(options["after"]);
                    Require(original == expected, "The original Stu page description differs from the preimage.");
                    receipt["before"] = DescriptionRecord(window, original);
                    if (original == desired) {
                        receipt["adjacent_string_preserved"] = true;
                        receipt["status"] = "no_changes";
                        receipt["operation_phase"] = "verified_no_changes";
                        return;
                    }

                    Abi.CheckSlot(document, "page_description_document", 102, "page_description_dialog_entry");
                    Abi.CheckSlot(document, "page_description_document", 83, "page_description_database_save");
                    IntPtr modifiable = IntPtr.Add(window.Page, Abi.Offset("page_description_modifiable_offset"));
                    Abi.CheckSlot(modifiable, "page_description_modifiable", 2, "page_description_native_flush");
                    string adjacent = context.Text(document, "page_description_adjacent_string");
                    var assign = Abi.BindImport<AssignText>("copy_page_description");
                    var write = new PageWrite(this, window, document, receipt);
                    using (var source = new AuthoringPageString(Abi, desired)) {
                        write.Begin(() => VerifyPageDescription(window, document, expected, adjacent));
                        write.RequireActive();
                        receipt["operation_phase"] = "set_description";
                        // Mirror the original dialog's CString assignment and use the
                        // guarded page flush to persist its archive and database note.
                        IntPtr destination = IntPtr.Add(document, Abi.Offset("page_description_text"));
                        Require(assign(destination, source.Storage) == destination,
                            "The original Stu CString copy did not return the target description.");
                        VerifyPageDescription(window, document, desired, adjacent);
                        receipt["completed_count"] = 1;
                        Action verify = () => VerifyPageDescription(window, document, desired, adjacent);
                        write.RefreshAndSave(verify, verify);
                    }
                    receipt["page_description"] = DescriptionRecord(window, ReadPageDescription(window, document));
                    receipt["adjacent_string_preserved"] = true;
                    receipt["status"] = "applied_and_saved";
                    receipt["operation_phase"] = "verified_saved";
                } catch (InvalidOperationException error) {
                    if (!editing) throw;
                    FailPageWrite(receipt, error);
                    if (window != null && document != IntPtr.Zero) {
                        try { receipt["page_description"] = DescriptionRecord(window, ReadPageDescription(window, document)); }
                        catch (InvalidOperationException) { receipt.Remove("page_description"); }
                    }
                }
            }

            private string ReadPageDescription(Window window, IntPtr document) {
                context.RequireProject();
                Require(PageDocument(window) == document, "The current Stu page document changed.");
                Abi.CheckSlot(document, "page_description_document", 2, "page_description_archive_entry");
                return context.Text(document, "page_description_text");
            }

            private void VerifyPageDescription(Window window, IntPtr document, string expected, string adjacent) {
                Require(ReadPageDescription(window, document) == expected &&
                    context.Text(document, "page_description_adjacent_string") == adjacent,
                    "Stu page description or its adjacent original text differs after editing.");
            }

            private static Dictionary<string, object> DescriptionRecord(Window window, string description) {
                return new Dictionary<string, object> {{"page_id", window.Id}, {"page", window.Name}, {"description", description}};
            }

            private static string ReadDescriptionOption(object value) {
                var fields = StuNativeProfile.Map(value);
                object text;
                Require(fields.Count == 1 && fields.TryGetValue("description", out text) && text is string,
                    "Only the original Stu page description text can be changed.");
                string description = (string)fields["description"];
                Require(description.IndexOf('\0') < 0 && description.Length <= 32768,
                    "Stu page description requires text within the supported CString readback range.");
                try { PageDescriptionEncoding.GetByteCount(description); }
                catch (EncoderFallbackException error) {
                    throw new InvalidOperationException("Stu page description requires valid Unicode text.", error);
                }
                return description;
            }
        }
    }
}
