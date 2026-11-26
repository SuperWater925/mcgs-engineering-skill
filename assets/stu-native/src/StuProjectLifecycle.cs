using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const string LifecycleRead = "project-lifecycle-state";
        private const string LifecycleClose = "project-close-clean";
        private const string LifecycleOpen = "project-open-closed";

        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate int LifecycleIsModified(IntPtr document);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate void LifecycleCloseRoot(IntPtr root);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate IntPtr LifecycleOpenProject(IntPtr app, IntPtr path);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate IntPtr FirstDocument(IntPtr template);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
        private delegate IntPtr NextDocument(IntPtr template, ref IntPtr position);

        private static readonly string[] CloseDocumentTables = {
            "lifecycle_control_document", "lifecycle_device_document", "page_document", "lifecycle_strategy_document"
        };

        private static bool IsLifecycleAction(string action) {
            return action == LifecycleRead || action == LifecycleClose || action == LifecycleOpen;
        }

        private static void VerifyLifecycleFeature(StuNativeProfile abi, string action) {
            abi.RequireFeature("engineering-project-lifecycle-read");
            if (action == LifecycleClose) abi.RequireFeature("engineering-project-close-original");
            if (action == LifecycleOpen) abi.RequireFeature("engineering-project-open-original");
        }

        private sealed class LifecycleState {
            internal IntPtr Current, Canonical;
            internal bool Busy, MatchesProject, ProjectFileAvailable;
            internal bool? Modified;
            internal string ProjectPath, ApplicationPath, ProjectSha;

            internal string Kind {
                get { return Current != Canonical ? "inconsistent" : Current == IntPtr.Zero ? "closed" : "open"; }
            }

            internal Dictionary<string, object> Value() {
                return new Dictionary<string, object> {
                    {"lifecycle_state", Kind}, {"current_root_present", Current != IntPtr.Zero},
                    {"canonical_root_present", Canonical != IntPtr.Zero}, {"roots_agree", Current == Canonical},
                    {"open_in_progress", Busy}, {"verified_same_project", MatchesProject}, {"root_modified", Modified},
                    {"actual_project", ProjectPath}, {"project_path", ProjectPath},
                    {"application_project_path", ApplicationPath}, {"project_file_available", ProjectFileAvailable},
                    {"project_sha256", ProjectSha}
                };
            }
        }

        private sealed class LifecycleProbe {
            private readonly StuNativeProfile abi;
            private readonly string project;
            private readonly IntPtr mainWindow, app;
            private readonly GetApplication getApp, getFrame;

            internal LifecycleProbe(StuNativeProfile abi, IntPtr mainWindow, string project) {
                this.abi = abi;
                this.mainWindow = mainWindow;
                this.project = project;
                getApp = abi.Bind<GetApplication>("get_application");
                getFrame = abi.Bind<GetApplication>("get_main_frame");
                app = getApp();
            }

            private IntPtr NativeFrame() {
                Require(getApp() == app, "The original Stu application changed during its lifecycle request.");
                abi.CheckTable(app, "app");
                IntPtr frame = getFrame();
                Require(frame == StuNativeProfile.Pointer(app, abi.Offset("lifecycle_app_main_frame")),
                    "The original Stu application and native main frame differ.");
                abi.CheckTable(frame, "frame");
                Require(StuNativeProfile.Pointer(frame, abi.Offset("frame_hwnd")) == mainWindow,
                    "The original Stu main frame is not the captured editor window.");
                return frame;
            }

            internal LifecycleState Capture(bool readModified = false) {
                NativeFrame();
                var state = new LifecycleState {
                    Current = StuNativeProfile.Pointer(app, abi.Offset("app_current_root")),
                    Canonical = abi.GlobalPointer("lifecycle_canonical_root"),
                    Busy = StuNativeProfile.ReadByte(app, abi.Offset("lifecycle_open_in_progress")) != 0
                };
                if (state.Kind == "open") {
                    abi.CheckTable(state.Current, "root");
                    state.ProjectPath = StuNativeProfile.Text(state.Current, abi.Offset("root_project_path"));
                    state.ApplicationPath = StuNativeProfile.Text(app, abi.Offset("app_project_path"));
                    state.MatchesProject = SamePath(state.ProjectPath, project) && SamePath(state.ApplicationPath, project);
                    if (readModified)
                        state.Modified = StuNativeProfile.Word(state.Current, abi.Offset("document_dirty")) != 0;
                }
                return state;
            }

            internal void CaptureFile(LifecycleState state, bool hash = false) {
                if (!state.MatchesProject && state.Kind != "closed") return;
                var file = new FileInfo(project);
                state.ProjectFileAvailable = file.Exists &&
                    (file.Attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) == 0;
                if (hash && state.ProjectFileAvailable)
                    state.ProjectSha = NativeEngineeringDeliveryLayout.HashFile(project);
            }

            internal void Close(LifecycleState before, Dictionary<string, object> result) {
                abi.CheckSlot(before.Current, "root", 26, "lifecycle_root_is_modified");
                abi.CheckSlot(before.Current, "root", 35, "lifecycle_close_root");
                var isModified = abi.Bind<LifecycleIsModified>("lifecycle_root_is_modified");
                var close = abi.Bind<LifecycleCloseRoot>("lifecycle_close_root");
                var fresh = Capture(true);
                Require(fresh.Current == before.Current && fresh.Canonical == fresh.Current && fresh.MatchesProject && !fresh.Busy,
                    "The original Stu project changed before close.");
                Require(fresh.Modified == false && isModified(fresh.Current) == 0,
                    "The current Stu project has unsaved changes.");
                result["clean_open_documents"] = VerifyOpenChildrenClean(abi, NativeFrame(), isModified, true);
                Enter(result, "close");
                close(fresh.Current);
                result["close_returned"] = true;
                result["operation_phase"] = "verify_after_close";

                // The original method releases the root. Reacquire state through the app only.
                var after = Capture();
                PutLifecycleState(result, "state_after", after);
                result["close_confirmed_empty"] = after.Kind == "closed" && !after.Busy;
                Require(Object.Equals(result["close_confirmed_empty"], true),
                    "The original Stu close did not leave both project roots empty.");
                CaptureFile(after);
                PutLifecycleState(result, "state_after", after);
            }

            internal void VerifyReopen() {
                abi.CheckSlot(app, "app", 43, "lifecycle_open_project");
            }

            internal void Open(Dictionary<string, object> result) {
                VerifyReopen();
                var open = abi.Bind<LifecycleOpenProject>("lifecycle_open_project");
                IntPtr filename = Marshal.StringToHGlobalUni(project);
                IntPtr returned;
                try {
                    var fresh = Capture();
                    Require(fresh.Kind == "closed" && !fresh.Busy, "The original Stu editor stopped being empty before opening.");
                    Enter(result, "open");
                    returned = open(app, filename);
                    result["open_returned"] = true;
                } finally { Marshal.FreeHGlobal(filename); }

                result["operation_phase"] = "verify_after_open";
                var after = Capture();
                PutLifecycleState(result, "state_after", after);
                result["open_confirmed_same_project"] = returned != IntPtr.Zero && returned == after.Current &&
                    after.Kind == "open" && after.MatchesProject && !after.Busy;
                Require(Object.Equals(result["open_confirmed_same_project"], true),
                    "The original Stu open did not return the exact requested project and both matching roots.");
                CaptureFile(after);
                PutLifecycleState(result, "state_after", after);
            }

            private static bool SamePath(string actual, string requested) {
                if (String.IsNullOrEmpty(actual)) return false;
                try { return NativeEngineeringDeliveryLayout.Same(NativeEngineeringDeliveryLayout.Absolute(actual), requested); }
                catch (InvalidOperationException) { return false; }
                catch (ArgumentException) { return false; }
            }
        }

        private static Dictionary<string, object> VerifyOpenChildrenClean(StuNativeProfile abi, IntPtr frame,
            LifecycleIsModified isModified, bool closing) {
            var first = abi.Bind<FirstDocument>("template_first_document");
            var next = abi.Bind<NextDocument>("template_next_document");
            string[] categories = { "control", "device", "page", "strategy" };
            var counts = new Dictionary<string, object>();
            for (int i = 0; i < CloseDocumentTables.Length; i++) {
                IntPtr template = StuNativeProfile.Pointer(frame, abi.Offset("lifecycle_frame_template_" + i));
                abi.CheckSlot(template, "designer_template", 23, "template_first_document");
                abi.CheckSlot(template, "designer_template", 24, "template_next_document");
                if (closing) abi.CheckSlot(template, "designer_template", 33, "lifecycle_template_close_all");
                var positions = new HashSet<IntPtr>();
                IntPtr position = first(template);
                while (position != IntPtr.Zero) {
                    Require(positions.Count < 32768 && positions.Add(position), "The original Stu document template list is invalid.");
                    IntPtr child = next(template, ref position);
                    abi.CheckSlot(child, CloseDocumentTables[i], 26, "lifecycle_root_is_modified");
                    Require(isModified(child) == 0, "An open Stu " + categories[i] + " document has unsaved changes.");
                }
                counts[categories[i]] = positions.Count;
            }
            return counts;
        }

        private static void RunLifecycle(StuNativeProfile abi, IntPtr mainWindow, string action, string project,
            Dictionary<string, object> request, Dictionary<string, object> result) {
            result["expected_project"] = project;
            result["identity_source"] = "native_app_and_canonical_root";
            result["write_attempted"] = false;
            result["native_result_may_be_partial"] = false;
            result["native_outcome_unknown"] = false;
            result["automatic_retry"] = false;
            result["close_entered"] = result["close_returned"] = result["close_confirmed_empty"] = false;
            result["open_entered"] = result["open_returned"] = result["open_confirmed_same_project"] = false;
            result["operation_phase"] = "validate_preimage";
            try {
                VerifyLifecycleFeature(abi, action);
                object options;
                Require(!request.TryGetValue("options", out options) || StuNativeProfile.Map(options).Count == 0,
                    "Stu lifecycle actions take the expected project and optional file hash in the request itself.");
                object verifyReopen;
                bool combined = request.TryGetValue("verify_reopen", out verifyReopen);
                Require(!combined || (action == LifecycleClose && Object.Equals(verifyReopen, true)),
                    "A combined Stu reopen requires its original close request.");
                var probe = new LifecycleProbe(abi, mainWindow, project);
                if (combined) {
                    VerifyLifecycleFeature(abi, LifecycleOpen);
                    probe.VerifyReopen();
                }
                LifecycleState before = probe.Capture(action == LifecycleClose);
                PutLifecycleState(result, "state_before", before);
                string expected = ExpectedLifecycleSha(request);
                probe.CaptureFile(before, expected != null);
                PutLifecycleState(result, "state_before", before);
                if (action != LifecycleRead) {
                    if (action == LifecycleClose)
                        Require(before.Kind == "open" && before.MatchesProject && !before.Busy,
                            "Closing requires the exact current Stu project and both original roots to agree.");
                    else
                        Require(before.Kind == "closed" && !before.Busy,
                            "Opening requires both original Stu roots to be empty and the editor idle.");
                    Require(before.ProjectFileAvailable, "The expected saved MCS file is unavailable.");
                    Require(expected == null || expected == before.ProjectSha, "The expected saved MCS file changed.");
                    if (action == LifecycleClose) probe.Close(before, result);
                    else probe.Open(result);
                }
                result["operation_phase"] = "complete";
                result["status"] = action == LifecycleRead ? "state_read" : action == LifecycleClose ? "project_closed" : "project_opened";
            } catch (InvalidOperationException error) { FailLifecycle(result, error); }
            catch (IOException error) { FailLifecycle(result, error); }
            catch (UnauthorizedAccessException error) { FailLifecycle(result, error); }
        }

        private static string ExpectedLifecycleSha(Dictionary<string, object> request) {
            if (!request.ContainsKey("expected_project_sha256")) return null;
            string hash = NativeEngineeringDeliveryLayout.Value(request, "expected_project_sha256");
            Require(hash.Length == 64 && Array.TrueForAll(hash.ToCharArray(), Uri.IsHexDigit), "Invalid expected MCS SHA-256.");
            return hash.ToLowerInvariant();
        }

        private static void PutLifecycleState(Dictionary<string, object> result, string key, LifecycleState state) {
            var value = state.Value();
            result[key] = value;
            foreach (var item in value) result[item.Key] = item.Value;
        }

        private static void Enter(Dictionary<string, object> result, string verb) {
            result["read_only"] = false;
            result["write_attempted"] = true;
            result["operation_phase"] = "native_" + verb;
            result[verb + "_entered"] = true;
        }

        private static void FailLifecycle(Dictionary<string, object> result, Exception error) {
            bool entered = Object.Equals(result["write_attempted"], true);
            result["ok"] = false;
            result["status"] = entered ? "native_partial_state" : "native_preflight_rejected";
            result["native_result_may_be_partial"] = entered;
            result["native_outcome_unknown"] = entered && !Object.Equals(result["close_returned"], true) &&
                !Object.Equals(result["open_returned"], true);
            result["error"] = error.Message;
        }
    }
}
