using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static partial class NativeOperations {
        static partial void DispatchExtension(Dictionary<string,object> request,NativeEngine engine,NativeContext context,string expected,ref Dictionary<string,object> result) {
            switch(Text(request,"op")) {
                case "engineering-project-lifecycle-read": result=NativeProjectLifecycle.Read(request,engine,context); break;
                case "engineering-project-close-reopen-original": result=NativeProjectLifecycle.Execute(request,engine,context); break;
                case "engineering-edit-inspect": RequirePageFixture(expected); result=NativeEngineeringBatch.Inspect(request,engine,context); break;
                case "engineering-edit-batch": RequirePageFixture(expected); result=NativeEngineeringBatch.Apply(request,engine,context); break;
                case "coverage-property-key-cache-warmup":
                    RequirePageFixture(expected);
                    result=NativePropertyKeyWarmupProfile.Run(engine,context);
                    break;
                case "coverage-label-base-scalars-read":
                    RequirePageFixture(expected);
                    result=NativeLabelScalarReadonlyProfile.Read(engine,context);
                    break;
                case "coverage-label-base-scalars-preflight":
                    RequirePageFixture(expected);
                    result=NativeLabelScalarReadonlyProfile.Preflight(engine,context);
                    break;
                case "coverage-fixed-three-metadata-read":
                    RequirePageFixture(expected);
                    result=NativeLabelMetadataReadonlyProfile.ReadFixedBatch(engine,context);
                    break;
                case "coverage-label-base-scalars-cached-read":
                    RequirePageFixture(expected);
                    result=NativeLabelScalarCachedReadonlyProfile.Read(engine,context);
                    break;
                case "coverage-label-base-scalars-cached-preflight":
                    RequirePageFixture(expected);
                    result=NativeLabelScalarCachedReadonlyProfile.Preflight(engine,context);
                    break;
                case "coverage-fixed-three-metadata-preflight":
                    RequirePageFixture(expected);
                    result=NativeLabelMetadataReadonlyProfile.PreflightFixedBatch(engine,context);
                    break;
                case "coverage-label-property-metadata-preflight":
                    RequirePageFixture(expected);
                    result=NativeLabelMetadataReadonlyProfile.Preflight(engine,context);
                    break;
                case "coverage-label-property-metadata-read":
                    RequirePageFixture(expected);
                    result=NativeLabelMetadataReadonlyProfile.Read(engine,context);
                    break;
                case "ext-strategy-source-read":
                    RequirePageFixture(expected);
                    result=NativeStrategyExtensionProfile.Inspect(engine,context);
                    break;
                case "ext-strategy-lifecycle-inspect":
                    RequirePageFixture(expected);
                    result=NativeStrategyExtensionProfile.InspectLifecycle(engine,context);
                    break;
                case "ext-page-inspect":
                    RequirePageFixture(expected);
                    result=NativePageExtensionProfile.Inspect(engine,context);
                    break;
                case "ext-control-inspect":
                    RequirePageFixture(expected);
                    result=NativeControlExtensionProfile.Inspect(engine,context);
                    break;
                case "ext-page-create-trial":
                    RequireExtensionWriteSession(engine,expected,true);
                    result=NativePageExtensionProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-control-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    NativeMemory.Require(NativeMemory.Hash(expected)=="f8db4e0ea0749683166a77608e3648aa429d31f2fdb634222fd03ac5513dcdcc","Recovered control trial requires its exact complete session baseline.");
                    result=NativeControlExtensionProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-standard-controls-inspect":
                    RequirePageFixture(expected);
                    result=NativeStandardControlsExtensionProfile.Inspect(engine,context);
                    break;
                case "ext-standard-controls-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    result=NativeStandardControlsExtensionProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-page-delete-inspect":
                    RequirePageFixture(expected);
                    result=NativePageDeleteExtensionProfile.Inspect(engine,context);
                    break;
                case "ext-page-delete-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    result=NativePageDeleteExtensionProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-page-size-inspect":
                    RequirePageFixture(expected);
                    result=NativePageSizeExtensionProfile.Inspect(engine,context);
                    break;
                case "ext-page-size-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    result=NativePageSizeExtensionProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-strategy-creation-inspect":
                    RequirePageFixture(expected);
                    result=NativeStrategyLifecycleProfile.Inspect(engine,context);
                    break;
                case "ext-trigger-cursor-inspect":
                    RequirePageFixture(expected);
                    result=NativeStrategyTriggerCursorProbe.Inspect(engine,context);
                    break;
                case "ext-strategy-create-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    result=NativeStrategyLifecycleProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-strategy-delete-inspect":
                    RequirePageFixture(expected);
                    result=NativeStrategyDeleteExtensionProfile.Inspect(engine,context);
                    break;
                case "coverage-references-view-inspect":
                    RequirePageFixture(expected);
                    result=NativeReferencesViewProfile.Inspect(engine,context);
                    break;
                case "coverage-references-view-v2":
                    RequirePageFixture(expected);
                    result=NativeReferencesViewProfileV2.Inspect(engine,context);
                    break;
                case "coverage-live-label-inspect":
                    RequirePageFixture(expected);
                    result=NativeLiveLabelTrialProfile.Inspect(engine,context);
                    break;
                case "coverage-live-label-trial":
                    RequirePageFixture(expected);
                    result=NativeLiveLabelTrialProfile.RunTrial(engine,context,expected);
                    break;
                case "coverage-button-references-inspect":
                    RequirePageFixture(expected);
                    result=NativeButtonReferenceReader.Inspect(engine,context);
                    break;
                case "coverage-live-page31-flush-inspect":
                    RequirePageFixture(expected);
                    result=NativeLivePage31FlushProfile.Inspect(engine,context);
                    break;
                case "coverage-live-page31-flush":
                    RequirePageFixture(expected);
                    result=NativeLivePage31FlushProfile.Flush(engine,context,expected);
                    break;
                case "coverage-reference-rename-inspect":
                    RequirePageFixture(expected);
                    result=NativeReferenceRenameTrialProfile.Inspect(engine,context);
                    break;
                case "coverage-reference-rename-trial":
                    RequirePageFixture(expected);
                    result=NativeReferenceRenameTrialProfile.RunTrial(engine,context,expected);
                    break;
                case "coverage-mainctrl-persistence-inspect":
                    RequirePageFixture(expected);
                    result=NativeMainCtrlPersistenceProfile.Inspect(engine,context);
                    break;
                case "coverage-mainctrl-restore":
                    RequirePageFixture(expected);
                    result=NativeMainCtrlRestorationTrialProfile.Restore(engine,context,expected);
                    break;
                case "coverage-control-geometry-inspect":
                    RequirePageFixture(expected);
                    result=NativeControlGeometryReadonlyProfile.Inspect(engine,context);
                    break;
                case "coverage-headless-reference-rename-inspect":
                    RequirePageFixture(expected);
                    result=NativeHeadlessReferenceRenameProfile.Inspect(engine,context);
                    break;
                case "coverage-headless-reference-rename-trial":
                    RequirePageFixture(expected);
                    result=NativeHeadlessReferenceRenameProfile.RunTrial(engine,context,expected);
                    break;
                case "ext-strategy-registration-inspect":
                    RequirePageFixture(expected);
                    result=NativeStrategyRegistrationRepair.Inspect(engine,context);
                    break;
                case "ext-strategy-registration-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    result=NativeStrategyRegistrationRepair.RunTrial(engine,context,expected);
                    break;
                case "ext-strategy-delete-trial":
                    RequireExtensionWriteSession(engine,expected,false);
                    result=NativeStrategyDeleteExtensionProfile.RunTrial(engine,context,expected);
                    break;
            }
        }
        static void RequireExtensionWriteSession(NativeEngine engine,string expected,bool initial) {
            RequirePageFixture(expected);
            if(initial) {
                NativeMemory.Require(Process.GetCurrentProcess().Id==24212 && EngineEntry.ExpectedUiThreadId==35436,"Initial page creation belongs only to the completed run0001 session.");
                NativeMemory.Require(NativeMemory.Hash(expected)=="96a8cd5e73c0bec13d9991738b8db505060fa69de8dffa0e5faefb10fd3c9924","Initial extension fixture differs from the complete run0001 baseline.");
                var api=new NativeStrategyProfile.Api(engine);IntPtr root=api.RootDoc();
                NativeMemory.Require(NativeMemory.I32(root,0x48)==0 && NativeMemory.I32(root,0x114)==1,"Initial extension root has unsaved changes or an invalid compile preimage.");
            } else {
                string file=Path.Combine(TaskRoot,"extensions","run-0002","session-preconditions.json");
                NativeMemory.Require(NativeMemory.Hash(file)=="c72e330cbc1d3f5b3182fc5aa75ae2b22385ee4712a60f295682facd9c37131a","Recovery session evidence differs.");
                var session=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(file));
                NativeMemory.Require(Process.GetCurrentProcess().Id==Convert.ToInt32(session["process_id"]) && EngineEntry.ExpectedUiThreadId==Convert.ToInt32(session["native_thread_id"]),"Extension writes require the separately verified clean recovery session.");
                NativeMemory.Require(Path.GetFullPath(Convert.ToString(session["expected_project"])).Equals(Path.GetFullPath(expected),StringComparison.OrdinalIgnoreCase),"Recovery target differs.");
            }
        }
    }
}
