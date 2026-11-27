using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        [DllImport("kernel32.dll")]
        private static extern int GetCurrentThreadId();

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr window, out uint owner);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate IntPtr GetApplication();

        private static readonly string[] Operations = {
            "ping", "inspect", "capabilities", "page-catalog", "control-catalog", "page-view-open",
            "label-properties-batch", "control-geometry-batch", "control-template-clone-batch", NativeCreateAction, "compile",
            LifecycleRead, LifecycleClose, LifecycleOpen, PageCreateAction, PageCopyAction,
            DataCatalogAction, DataReadAction, DataEditAction, RecipeCatalogAction, RecipeReadAction, RecipeEditAction,
            StrategyCatalogAction, StrategyReadAction, StrategyEditAction, PagePropertiesReadAction, PageBackgroundEditAction,
            VisibilityReadAction, VisibilityEditAction, PageDescriptionReadAction, PageDescriptionEditAction,
            PageReferenceReadAction, PageRenameAction, DataReferenceReadAction, DataRenameAction,
            TriggerCatalogAction, TriggerReadAction, LanguageCatalogAction, LanguageTextEditAction, LanguageAddAction,
            PictureCatalogAction, PictureImportAction, PictureCopyAction, PictureReplaceAction, PictureExportAction,
            PageGenerateAction, ControlReferenceReadAction, ControlRenameAction, RecipeReferenceReadAction, RecipeRenameAction,
            SerialDeviceReadAction, SerialDeviceEditAction
        };

        private static readonly string[] PageWrites = {
            "label-properties-batch", "control-geometry-batch", "control-template-clone-batch", NativeCreateAction,
            PageCreateAction, PageCopyAction, DataEditAction, RecipeEditAction, StrategyEditAction, PageBackgroundEditAction,
            VisibilityEditAction, PageDescriptionEditAction, PageRenameAction, DataRenameAction,
            LanguageTextEditAction, LanguageAddAction, PictureImportAction, PictureCopyAction, PictureReplaceAction,
            PageGenerateAction, ControlRenameAction, RecipeRenameAction, SerialDeviceEditAction
        };

        private sealed class Context {
            internal readonly StuNativeProfile Abi;
            internal readonly IntPtr App, Root;
            internal readonly string Project;

            internal Context(StuNativeProfile abi, string project) {
                Abi = abi;
                Project = project;
                Abi.RequireFeature("inspect");
                App = Abi.Bind<GetApplication>("get_application")();
                Abi.CheckTable(App, "app");
                Root = Ptr(App, "app_current_root");
                RequireProject();
            }

            internal IntPtr Ptr(IntPtr owner, string role) {
                return StuNativeProfile.Pointer(owner, Abi.Offset(role));
            }

            internal int Word(IntPtr owner, string role) {
                return StuNativeProfile.Word(owner, Abi.Offset(role));
            }

            internal string Text(IntPtr owner, string role) {
                return StuNativeProfile.Text(owner, Abi.Offset(role));
            }

            internal void RequireProject() {
                Abi.CheckTable(App, "app");
                Abi.CheckTable(Root, "root");
                Require(Ptr(App, "app_current_root") == Root &&
                    PathMatches(Text(App, "app_project_path")) && PathMatches(Text(Root, "root_project_path")),
                    "The requested MCS and the actual Stu application/root document differ.");
            }

            private bool PathMatches(string actual) {
                return !String.IsNullOrEmpty(actual) && NativeEngineeringDeliveryLayout.Same(
                    Project, NativeEngineeringDeliveryLayout.Absolute(actual));
            }
        }

        public static Dictionary<string, object> PrepareRequest(Dictionary<string, object> request) {
            if (IsLifecycleAction(NativeEngineeringDeliveryLayout.Value(request, "op"))) {
                string expected = NativeEngineeringDeliveryLayout.Value(request, "expected_engine_sha256");
                string assembly = typeof(EngineEntry).Assembly.Location;
                Require(expected == NativeEngineeringDeliveryLayout.HashFile(assembly),
                    "The active Stu engine changed since the lifecycle operation was prepared.");
            }
            return request;
        }

        public static Dictionary<string, object> Dispatch(Dictionary<string, object> request, object nativeContext, int thread) {
            Require(IntPtr.Size == 4 && thread > 0 && thread == GetCurrentThreadId(), "Stu actions require their x86 editor dispatch thread.");
            string action = NativeEngineeringDeliveryLayout.Value(request, "op");
            Require(Array.IndexOf(Operations, action) >= 0, "Stu action is not published: " + action);
            var scope = NativeEngineeringDeliveryLayout.Load();
            using (var process = Process.GetCurrentProcess()) {
                ProcessModule module = process.MainModule;
                Require(NativeEngineeringDeliveryLayout.Same(
                    NativeEngineeringDeliveryLayout.Absolute(module.FileName), scope.EditorExecutable),
                    "The current Stu process is not the selected installed editor.");
                uint owner;
                IntPtr window = process.MainWindowHandle;
                Require(window != IntPtr.Zero && GetWindowThreadProcessId(window, out owner) == (uint)thread && owner == (uint)process.Id,
                    "The captured thread is not the actual Stu main-window thread.");
                long creation = process.StartTime.ToFileTimeUtc();
                var response = new Dictionary<string, object> {
                    {"ok", true}, {"op", action}, {"family", "stu"}, {"engine_family", "McgsStu"},
                    {"process_id", process.Id}, {"creation_filetime", creation},
                    {"native_thread_id", thread}, {"thread_id", thread}, {"read_only", true},
                    {"engineering_delivery_scope_sha256", scope.Sha256}, {"stu_role_profile_sha256", scope.ProfileSha256}
                };
                if (action == "ping") return response;
                Require(NativeEngineeringDeliveryLayout.Value(request, "expected_engine_family") == "McgsStu" &&
                    Object.Equals(request["expected_process_id"], process.Id) &&
                    Object.Equals(request["expected_ui_thread_id"], thread) &&
                    Object.Equals(request["expected_creation_filetime"], creation),
                    "The request targets another Stu process, thread or process creation.");
                bool lifecycle = IsLifecycleAction(action);
                if (lifecycle || action == "page-view-open" || action == PictureExportAction || Array.IndexOf(PageWrites, action) >= 0)
                    Require(NativeEngineeringDeliveryLayout.Value(request, "engineering_delivery_scope_sha256") == scope.Sha256,
                        "The Stu view or edit request belongs to a different delivery scope.");
                string project = NativeEngineeringDeliveryLayout.Absolute(NativeEngineeringDeliveryLayout.Value(request, "expected_project"));
                Require(String.Equals(Path.GetExtension(project), ".mcs", StringComparison.OrdinalIgnoreCase),
                    "Stu project identity must name the current MCS.");
                var abi = new StuNativeProfile(module.BaseAddress, module.ModuleMemorySize, scope.Profile);
                response["editor_image_sha256"] = NativeEngineeringDeliveryLayout.HashFile(module.FileName);
                if (lifecycle) {
                    RunLifecycle(abi, window, action, project, request, response);
                    return response;
                }
                var context = new Context(abi, project);
                response["actual_project"] = project;
                response["project_path"] = context.Text(context.Root, "root_project_path");
                response["application_project_path"] = context.Text(context.App, "app_project_path");
                response["identity_source"] = "native_app_and_root_current_project";
                switch (action) {
                    case "inspect":
                        break;
                    case "capabilities":
                        var features = Capabilities(context.Abi);
                        response["features"] = features;
                        var writes = new List<string>();
                        foreach (string kind in PageWrites)
                            if (Object.Equals(StuNativeProfile.Map(features[kind])["state"], "located")) writes.Add(kind);
                        response["native_write"] = writes;
                        break;
                    case "page-catalog":
                        VerifyFeature(context.Abi, action);
                        var pages = new StuDocument(context).ReadPages();
                        response["pages"] = pages;
                        response["page_count"] = pages.Count;
                        break;
                    case "control-catalog":
                        VerifyFeature(context.Abi, action);
                        var options = StuNativeProfile.Map(request["options"]);
                        Require(options.Count == 2, "Stu control catalog requires the current page ID and exact name.");
                        int pageId = StuNativeProfile.Number(options["page_id"]);
                        string pageName = NativeEngineeringDeliveryLayout.Value(options, "page");
                        response["page"] = new StuDocument(context).ReadPage(pageId, pageName);
                        break;
                    case "compile":
                        VerifyFeature(context.Abi, action);
                        CompileProject(context, response);
                        break;
                    case PageCreateAction:
                    case PageCopyAction:
                        object pageOptions;
                        request.TryGetValue("options", out pageOptions);
                        new StuDocument(context).ApplyPageStructure(action, window, pageOptions, response);
                        break;
                    case PageGenerateAction:
                        new StuDocument(context).GeneratePage(window, request["options"], response);
                        break;
                    case DataCatalogAction:
                    case DataReadAction:
                    case DataEditAction:
                        object dataOptions;
                        request.TryGetValue("options", out dataOptions);
                        new StuDocument(context).ApplyDataAction(action, window, dataOptions, response);
                        break;
                    case RecipeCatalogAction:
                    case RecipeReadAction:
                    case RecipeEditAction:
                        object recipeOptions;
                        request.TryGetValue("options", out recipeOptions);
                        new StuDocument(context).ApplyRecipeAction(action, window, recipeOptions, response);
                        break;
                    case StrategyCatalogAction:
                    case StrategyReadAction:
                    case StrategyEditAction:
                        object strategyOptions;
                        request.TryGetValue("options", out strategyOptions);
                        new StuDocument(context).ApplyStrategyAction(action, window, strategyOptions, response);
                        break;
                    case PagePropertiesReadAction:
                    case PageBackgroundEditAction:
                        VerifyFeature(context.Abi, action);
                        new StuDocument(context).ApplyPageProperties(action, request["options"], response);
                        break;
                    case PageDescriptionReadAction:
                    case PageDescriptionEditAction:
                        new StuDocument(context).ApplyPageDescription(action, request["options"], response);
                        break;
                    case PageReferenceReadAction:
                    case PageRenameAction:
                        new StuDocument(context).ApplyPageReference(action, window, request["options"], response);
                        break;
                    case DataReferenceReadAction:
                    case DataRenameAction:
                        new StuDocument(context).ApplyDataReference(action, window, request["options"], response);
                        break;
                    case ControlReferenceReadAction:
                    case ControlRenameAction:
                        new StuDocument(context).ApplyControlReferenceRename(action, window, request["options"], response);
                        break;
                    case RecipeReferenceReadAction:
                    case RecipeRenameAction:
                        new StuDocument(context).ApplyRecipeRenameAction(action, window, request["options"], response);
                        break;
                    case SerialDeviceReadAction:
                    case SerialDeviceEditAction:
                        new StuDocument(context).ApplySerialDeviceAction(action, request["options"], response);
                        break;
                    case TriggerCatalogAction:
                    case TriggerReadAction:
                        object triggerOptions;
                        request.TryGetValue("options", out triggerOptions);
                        new StuDocument(context).ReadTriggers(action, triggerOptions, response);
                        break;
                    case LanguageCatalogAction:
                    case LanguageTextEditAction:
                    case LanguageAddAction:
                        object languageOptions;
                        request.TryGetValue("options", out languageOptions);
                        new StuDocument(context).ApplyLanguage(action, window, languageOptions, response);
                        break;
                    case PictureCatalogAction:
                    case PictureImportAction:
                    case PictureCopyAction:
                    case PictureReplaceAction:
                    case PictureExportAction:
                        object pictureOptions;
                        request.TryGetValue("options", out pictureOptions);
                        new StuDocument(context).ApplyPicture(action, window, pictureOptions, response);
                        break;
                    case VisibilityReadAction:
                    case VisibilityEditAction:
                        object visibilityOptions;
                        request.TryGetValue("options", out visibilityOptions);
                        new StuDocument(context).ApplyVisibility(action, visibilityOptions, response);
                        break;
                    case "page-view-open":
                    case "label-properties-batch":
                    case "control-geometry-batch":
                    case "control-template-clone-batch":
                    case NativeCreateAction:
                        RunPageAction(context, action, request, response);
                        break;
                }
                if (Object.Equals(response["ok"], true)) context.RequireProject();
                return response;
            }
        }

        private static Dictionary<string, object> Capabilities(StuNativeProfile abi) {
            var features = new Dictionary<string, object>();
            foreach (string feature in new[] { "inspect", "page-catalog", "control-catalog", "page-view-open",
                "label-properties-batch", "control-geometry-batch", "control-template-clone-batch", NativeCreateAction, "compile",
                LifecycleRead, LifecycleClose, LifecycleOpen, PageCreateAction, PageCopyAction,
                DataCatalogAction, DataReadAction, DataEditAction, RecipeCatalogAction, RecipeReadAction, RecipeEditAction,
                StrategyCatalogAction, StrategyReadAction, StrategyEditAction, PagePropertiesReadAction, PageBackgroundEditAction,
                VisibilityReadAction, VisibilityEditAction, PageDescriptionReadAction, PageDescriptionEditAction,
                PageReferenceReadAction, PageRenameAction, DataReferenceReadAction, DataRenameAction,
                TriggerCatalogAction, TriggerReadAction, LanguageCatalogAction, LanguageTextEditAction, LanguageAddAction,
                PictureCatalogAction, PictureImportAction, PictureCopyAction, PictureReplaceAction, PictureExportAction,
                PageGenerateAction, ControlReferenceReadAction, ControlRenameAction, RecipeReferenceReadAction, RecipeRenameAction,
                SerialDeviceReadAction, SerialDeviceEditAction }) {
                try {
                    VerifyFeature(abi, feature);
                    var result = new Dictionary<string, object> { {"state", "located"}, {"native_action_executed", false} };
                    if (feature == "control-geometry-batch" || feature == "control-template-clone-batch" || feature == NativeCreateAction) {
                        var classes = new Dictionary<string, object>();
                        int available = 0;
                        foreach (var item in RectangleClasses) {
                            try {
                                abi.RequireFeature(item.Value.Feature);
                                if (feature == "control-template-clone-batch")
                                    abi.RequireFeature(TemplateClasses[item.Key].Feature);
                                if (feature == NativeCreateAction)
                                    abi.RequireFeature(TemplateClasses[item.Key].CreateFeature);
                                classes[item.Key] = new Dictionary<string, object> { {"state", "located"} };
                                available++;
                            } catch (InvalidOperationException error) {
                                classes[item.Key] = new Dictionary<string, object> { {"state", "unavailable"}, {"reason", error.Message} };
                            }
                        }
                        if (feature == NativeCreateAction || feature == "control-geometry-batch")
                            available += AddShapeCapabilities(abi, classes, feature == NativeCreateAction);
                        result["classes"] = classes;
                        if (available == 0) result["state"] = "unavailable";
                    }
                    if (feature == DataEditAction) {
                        var fields = new Dictionary<string, object>();
                        int available = 0;
                        foreach (string field in DataTextFields) {
                            try {
                                abi.RequireFeature("data-edit-" + field);
                                fields[field] = new Dictionary<string, object> { {"state", "located"} };
                                available++;
                            } catch (InvalidOperationException error) {
                                fields[field] = new Dictionary<string, object> { {"state", "unavailable"}, {"reason", error.Message} };
                            }
                        }
                        result["fields"] = fields;
                        if (available == 0) result["state"] = "unavailable";
                    }
                    features[feature] = result;
                } catch (InvalidOperationException error) {
                    features[feature] = new Dictionary<string, object> { {"state", "unavailable"}, {"reason", error.Message}};
                }
            }
            return features;
        }

        private static void VerifyFeature(StuNativeProfile abi, string feature) {
            if (feature == ControlReferenceReadAction || feature == ControlRenameAction) {
                VerifyControlRenameFeature(abi, feature);
                return;
            }
            if (feature == RecipeReferenceReadAction || feature == RecipeRenameAction) {
                VerifyRecipeRenameFeature(abi, feature);
                return;
            }
            if (feature == SerialDeviceReadAction || feature == SerialDeviceEditAction) {
                VerifySerialDeviceFeature(abi, feature);
                return;
            }
            if (feature == TriggerCatalogAction || feature == TriggerReadAction) {
                abi.RequireFeature(StrategyCatalogAction);
                abi.RequireFeature(TriggerCatalogAction);
                return;
            }
            if (feature == PageReferenceReadAction || feature == PageRenameAction ||
                feature == DataReferenceReadAction || feature == DataRenameAction) {
                abi.RequireFeature("registered-reference-read");
                abi.RequireFeature(feature == PageReferenceReadAction || feature == PageRenameAction
                    ? "page-catalog" : DataCatalogAction);
                if (feature == PageRenameAction || feature == DataRenameAction) {
                    abi.RequireFeature("registered-reference-rename");
                    abi.RequireFeature("page-catalog");
                    abi.RequireFeature("page-view-inspect");
                    abi.RequireFeature("top-level-control-catalog");
                    abi.RequireFeature("page-authoring-common");
                    abi.RequireFeature(StrategyCatalogAction);
                    abi.RequireFeature(StrategyReadAction);
                    abi.RequireFeature(StrategyEditAction);
                }
                if (feature == PageRenameAction) {
                    abi.RequireFeature("control-catalog");
                    abi.RequireFeature(PageDescriptionEditAction);
                }
                if (feature == DataRenameAction) {
                    abi.RequireFeature(DataEditAction);
                }
                abi.RequireFeature(feature);
                return;
            }
            if (IsVisibilityAction(feature)) {
                abi.RequireFeature("page-catalog");
                abi.RequireFeature("top-level-control-catalog");
                abi.RequireFeature(VisibilityReadAction);
                if (feature == VisibilityEditAction) {
                    abi.RequireFeature("page-view-inspect");
                    abi.RequireFeature(VisibilityEditAction);
                }
                return;
            }
            if (IsPagePropertiesAction(feature)) {
                abi.RequireFeature("page-catalog");
                abi.RequireFeature("page-view-inspect");
                abi.RequireFeature(PagePropertiesReadAction);
                if (feature == PageBackgroundEditAction) abi.RequireFeature(PageBackgroundEditAction);
                return;
            }
            if (IsPageDescriptionAction(feature)) {
                abi.RequireFeature("page-catalog");
                abi.RequireFeature(PageDescriptionReadAction);
                if (feature == PageDescriptionEditAction) abi.RequireFeature(PageDescriptionEditAction);
                return;
            }
            if (IsStrategyAction(feature)) {
                abi.RequireFeature(StrategyCatalogAction);
                if (feature != StrategyCatalogAction) abi.RequireFeature(StrategyReadAction);
                if (feature == StrategyEditAction) abi.RequireFeature(StrategyEditAction);
                return;
            }
            if (IsRecipeAction(feature)) {
                abi.RequireFeature(feature);
                if (feature == RecipeEditAction) abi.RequireFeature("recipe-edit-workbench");
                return;
            }
            if (IsDataAction(feature)) {
                abi.RequireFeature(DataCatalogAction);
                if (feature == DataEditAction) abi.RequireFeature(DataEditAction);
                return;
            }
            if (IsLifecycleAction(feature)) {
                VerifyLifecycleFeature(abi, feature);
                return;
            }
            if (IsPageStructureAction(feature)) {
                abi.RequireFeature("page-catalog");
                abi.RequireFeature("page-view-inspect");
                abi.RequireFeature("top-level-control-catalog");
                abi.RequireFeature("page-authoring-common");
                if (feature == PageCopyAction) abi.RequireFeature("control-catalog");
                abi.RequireFeature(feature == PageCreateAction ? "page-create-original" : "page-copy-original");
                return;
            }
            if (feature == LanguageCatalogAction || feature == LanguageTextEditAction || feature == LanguageAddAction) {
                abi.RequireFeature(feature);
                return;
            }
            if (IsPictureAction(feature)) {
                VerifyPictureFeature(feature, abi);
                return;
            }
            if (feature == PageGenerateAction) {
                abi.RequireFeature("control-geometry-batch");
                abi.RequireFeature("page-authoring-common");
                abi.RequireFeature(PageGenerateAction);
                return;
            }
            bool pageWrite = Array.IndexOf(PageWrites, feature) >= 0;
            if (feature == "control-catalog" || feature == "page-view-open" || pageWrite)
                abi.RequireFeature("page-catalog");
            if (feature == "page-view-open" || pageWrite)
                abi.RequireFeature("page-view-inspect");
            if (pageWrite) abi.RequireFeature("top-level-control-catalog");
            if (feature == "label-properties-batch" || feature == "control-template-clone-batch" || feature == NativeCreateAction)
                abi.RequireFeature("control-catalog");
            if (feature == "label-properties-batch")
                abi.RequireFeature("label-static-read");
            abi.RequireFeature(feature == NativeCreateAction ? "control-create-batch" : feature);
        }

        private static void RunPageAction(Context context, string action, Dictionary<string, object> request,
            Dictionary<string, object> response) {
            response["write_attempted"] = false;
            response["native_result_may_be_partial"] = false;
            response["automatic_retry"] = false;
            response["operation_phase"] = "validate_preimage";
            try {
                bool pageWrite = action != "page-view-open";
                if (pageWrite) VerifyFeature(context.Abi, action);
                else {
                    context.Abi.RequireFeature("page-catalog");
                    context.Abi.RequireFeature("page-view-inspect");
                }
                var options = StuNativeProfile.Map(request["options"]);
                Require(options.Count == (pageWrite ? 3 : 2) && options.ContainsKey("page_id") &&
                    options.ContainsKey("page") && (!pageWrite || options.ContainsKey("changes")),
                    "Stu page action requires its current page ID, exact name and requested changes.");
                int id = StuNativeProfile.Number(options["page_id"]);
                Require(id >= 0, "The Stu page ID is invalid.");
                string page = NativeEngineeringDeliveryLayout.Value(options, "page");
                var document = new StuDocument(context);
                if (action == "label-properties-batch") document.ApplyLabelBatch(id, page, options["changes"], response);
                else if (action == "control-geometry-batch") document.ApplyGeometryBatch(id, page, options["changes"], response);
                else if (action == "control-template-clone-batch") document.ApplyTemplateCloneBatch(id, page, options["changes"], response);
                else if (action == NativeCreateAction) document.ApplyDefaultCreateBatch(id, page, options["changes"], response);
                else {
                    response["operation_phase"] = "activate_view";
                    document.OpenView(id, page, response);
                    response["operation_phase"] = "complete";
                    response["status"] = "view_active";
                }
            } catch (InvalidOperationException error) {
                response["ok"] = false;
                response["status"] = "native_preflight_rejected";
                response["error"] = error.Message;
            }
        }

        private static void Require(bool ok, string message) {
            if (!ok) throw new InvalidOperationException(message);
        }
    }
}
