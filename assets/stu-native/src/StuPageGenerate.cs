using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string PageGenerateAction = "page-native-generate";

        private sealed partial class StuDocument {
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
            [return: MarshalAs(UnmanagedType.I1)]
            private delegate bool GenerateUserPage(IntPtr page);

            internal void GeneratePage(IntPtr mainWindow, object rawOptions, Dictionary<string, object> result) {
                BeginPageReceipt(result);
                result["native_selected_page_generated"] = false;
                try {
                    VerifyFeature(Abi, PageGenerateAction);
                    var spec = StuNativeProfile.Map(rawOptions);
                    Require(spec.Count == 3 && spec.ContainsKey("page_id") && spec.ContainsKey("page") && spec.ContainsKey("expected_top_level_count"),
                        "Stu native page generation requires the exact page ID, name and top-level control count.");
                    int id = StuNativeProfile.Number(spec["page_id"]);
                    int count = StuNativeProfile.Number(spec["expected_top_level_count"]);
                    Require(id >= 0 && count >= 0, "The Stu native page identity or count is invalid.");
                    var window = SelectWindow(id, NativeEngineeringDeliveryLayout.Value(spec, "page"));
                    IntPtr document = GetDocumentForView(window);
                    RequireEmptyPageProtection(document);
                    Abi.CheckSlot(window.Page, "page", 21, "generate_single_page");
                    Abi.CheckSlot(document, "page_description_document", 85, "generate_user_document");
                    Abi.CheckSlot(document, "page_description_document", 83, "page_description_database_save");
                    Abi.CheckSlot(context.Root, "root", 26, "lifecycle_root_is_modified");
                    IntPtr frame = Abi.Bind<GetApplication>("get_main_frame")();
                    Abi.CheckTable(frame, "frame");
                    var modified = Abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                    Require(context.Ptr(frame, "frame_hwnd") == mainWindow && modified(context.Root) == 0,
                        "The original Stu workbench changed or has unsaved changes.");
                    result["clean_open_documents"] = VerifyOpenChildrenClean(Abi, frame, modified, false);
                    Require(ReadTopLevelControls(document).Count == count, "The original Stu page control count differs from its preimage.");
                    var original = AuthoringControls(window);
                    var write = new PageWrite(this, window, document, result);
                    Action verify = () => {
                        Require(SelectWindow(id, window.Name).Page == window.Page && PageDocument(window) == document &&
                            ReadTopLevelControls(document).Count == count && SameAuthoringControls(original, AuthoringControls(window)),
                            "The selected Stu page, control inventory or geometry changed during native generation.");
                        RequireEmptyPageProtection(document);
                    };
                    write.Begin(verify);
                    write.RequireActive();
                    result["operation_phase"] = "generate_original_page";
                    bool generated = Abi.Bind<GenerateUserPage>("generate_single_page")(window.Page);
                    result["native_page_generate_return"] = generated;
                    Require(generated, "The original Stu page generation returned failure.");
                    result["native_selected_page_generated"] = true;
                    write.RefreshAndSave(verify, verify);
                    result["page_id"] = id;
                    result["page"] = window.Name;
                    result["top_level_control_count"] = count;
                    result["completed_count"] = 1;
                    result["operation_phase"] = "verified_saved";
                    result["status"] = "applied_and_saved";
                } catch (InvalidOperationException error) {
                    FailPageWrite(result, error);
                }
            }
        }
    }
}
