// Unified development entry; one current native UI-thread session and file queue.
// All code is implemented before consolidated engineering acceptance is run.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;
using System.IO;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeEngineeringBatch {
  static readonly string[] BuiltinKinds={"label-caption-rect","control-properties","page-history",
   "page-create","page-rename","page-size","page-delete","page-copy","page-referenced-rename","page-reconcile-created-row",
   "control-create-label","control-clone","control-delete","control-template-clone","control-template-delete","control-geometry","control-geometry-batch","control-native-create","control-layer","control-group","control-ungroup",
   "strategy-source","strategy-rename","strategy-create-user","strategy-delete",
   "page-flush","strategy-flush","root-flush","main-control-flush","picture-create-from-controls"};
  static partial void AddKinds(List<string> kinds);
  static partial void AdditionalRead(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action,ref Dictionary<string,object> result);
  static partial void AdditionalPrepare(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action,ref Unit result);
  internal sealed class Unit:IDisposable {
   internal string Kind;internal Action Validate;internal Func<NativeUsableEditPermit.Lease,Dictionary<string,object>> Apply,Flush;
   internal IDisposable Resource;public void Dispose(){if(Resource!=null){IDisposable r=Resource;Resource=null;r.Dispose();}}
  }
  internal static List<string> Kinds(){var list=new List<string>(BuiltinKinds);list.Add(NativeControlPropertyEditing.BatchKind);list.Add(NativeControlPropertyEditing.RenameKind);list.Add(NativePageDocumentProperties.Kind);list.Add(NativePageViewOperations.Kind);list.Add(NativeAlarmDefinitionEditing.Kind);list.Add(NativeAlarmTypedSpecification.Kind);list.Add(NativePageEventSourceEditing.Kind);list.AddRange(NativePageEventListEditing.Kinds);list.Add(NativeLinguistOpenViewsRefresh.Kind);list.AddRange(NativeStrategyWorkingModelEditing.ImplementedKinds);list.AddRange(NativeDataEngineering.Kinds);list.Add(NativeDataBatchEditing.Kind);list.Add(NativeRecipeMatrixEditing.Kind);list.AddRange(NativeDataGroupsAndArrays.Kinds);list.AddRange(NativeDataReferencedRename.Kinds);list.AddRange(NativeUsableDeviceBatch.ImplementedKinds);list.AddRange(NativePictureResources.Kinds);list.AddRange(NativeLinguistEditing.Kinds);list.Add(NativeDomainProjectCheck.Kind);AddKinds(list);var unique=new HashSet<string>(StringComparer.Ordinal);foreach(string kind in list)NativeMemory.Require(unique.Add(kind),"Duplicate compiled engineering kind: "+kind);return list;}
  static Dictionary<string,object> Map(object value){return NativePageControlPreparation.Map(value);}
  static string Kind(Dictionary<string,object> action){return Convert.ToString(action["kind"]);}
  static bool IsSource(string kind){return Array.IndexOf(NativeUsableStrategySourceBatch.ImplementedKinds,kind)>=0;}
  static bool IsWorkingStrategy(Dictionary<string,object> action){return NativeStrategyWorkingModelEditing.Handles(action);}
  static bool IsLifecycleStrategy(Dictionary<string,object> action){return NativeStrategyWorkingModelEditing.LifecycleHandles(action);}
  static bool IsStrategySession(Dictionary<string,object> action){string k=Kind(action);return k==NativeStrategyWorkingModelEditing.AdoptionCompletionKind||IsWorkingStrategy(action)||IsLifecycleStrategy(action)||k==NativeStrategyWorkingModelEditing.TriggerPropertiesKind||k==NativeStrategyWorkingModelEditing.StandardSvrKind||k==NativeStrategyWorkingModelEditing.TypedKind||k==NativeStrategyWorkingModelEditing.CloseKind||Array.IndexOf(NativeStrategyTriggerContextEditing.Kinds,k)>=0;}
  static bool IsCanonicalSource(Dictionary<string,object> action){return IsSource(Kind(action))&&!IsWorkingStrategy(action)&&!IsLifecycleStrategy(action);}
  static bool IsDevice(string kind){return Array.IndexOf(NativeUsableDeviceBatch.ImplementedKinds,kind)>=0;}
  static bool IsExtraDevice(string kind){return kind==NativeUsableDeviceBatch.DriverProperties.InstalledDriverAdd.Kind||kind==NativeUsableDeviceBatch.DriverProperties.Kind||kind==NativeUsableDeviceBatch.DriverProperties.CatalogKind||kind==NativeUsableDeviceBatch.DriverProperties.ReferencedRename.Kind||Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.InPlaceProperties.Kinds,kind)>=0||Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.DeviceTree.Kinds,kind)>=0;}
  static bool IsPicture(string kind){return kind==NativePictureResources.VectorCreateKind||kind==NativePictureResources.ContainedReferenceKind||Array.IndexOf(NativePictureResources.Kinds,kind)>=0;}
  static bool IsLanguage(string kind){return kind==NativeLinguistManagementEditing.Kind||Array.IndexOf(NativeLinguistEditing.Kinds,kind)>=0||kind==NativeLinguistOpenViewsRefresh.Kind;}
  static bool IsPageControl(string k){return k.StartsWith("page-",StringComparison.Ordinal)&&k!="page-flush"&&k!="page-history"||k=="control-create-label"||k=="control-clone"||k=="control-delete"||k=="control-template-clone"||k=="control-template-delete"||k=="control-geometry"||k=="control-layer"||k=="control-group"||k=="control-ungroup";}
  static bool IsPersistence(string k){return k=="page-flush"||k=="strategy-flush"||k=="root-flush"||k=="main-control-flush"||k=="data-flush"||k=="recipe-flush"||k=="device-flush"||k=="device-tree-flush"||k=="picture-flush"||k=="language-flush"||k=="strategy-working-flush"||k==NativeStrategyTriggerContextEditing.FlushKind;}
  static bool IsData(string k){return k==NativeDataGroupDeleting.Kind||Array.IndexOf(NativeDataPrototypeEditing.Kinds,k)>=0||Array.IndexOf(NativeDataEngineering.Kinds,k)>=0||k==NativeDataBatchEditing.Kind||k==NativeRecipeMatrixEditing.Kind||k==NativeAlarmDefinitionEditing.Kind||k==NativeAlarmTypedSpecification.Kind||Array.IndexOf(NativeDataGroupsAndArrays.Kinds,k)>=0||Array.IndexOf(NativeDataReferencedRename.Kinds,k)>=0;}
  static List<Dictionary<string,object>> InspectionActions(Dictionary<string,object> request) {
   var result=new List<Dictionary<string,object>>();Dictionary<string,object> spec;if(!NativeRequestPipeline.TryInspection(request,out spec)){
   object raw;if(!request.TryGetValue("inspection_file",out raw))return result;
   string file=DirectInputFile(Convert.ToString(raw));NativeMemory.Require(NativeMemory.Hash(file)==Convert.ToString(request["inspection_sha256"]),"Inspection selectors file differs.");
   spec=new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));}
   foreach(object value in (IEnumerable)spec["actions"]){NativeMemory.Require(result.Count<64,"Inspection selectors exceed64 actions.");result.Add(Map(value));}return result;
  }
  static Dictionary<string,object> ReadSourceAction(NativeEngine engine,NativeContext context,Dictionary<string,object> action) {
   var target=Map(action["target"]);string kind=Kind(action);var full=NativeUsableStrategySourceBatch.Inspect(engine,context);int id=Convert.ToInt32(target[kind=="strategy-create-user"?"template_block_id":"block_id"]);Dictionary<string,object> block=null;
   foreach(object value in (IEnumerable)full["blocks"]){var b=Map(value);if(Convert.ToInt32(b["block_id"])==id){NativeMemory.Require(block==null,"Strategy ID repeats.");block=b;}}
   NativeMemory.Require(block!=null,"Logical strategy target is absent.");
   if(kind=="strategy-create-user")return new Dictionary<string,object>{{"template_block",block}};
   if(kind=="strategy-rename")return new Dictionary<string,object>{{"block_name",block["block_name"]}};
   int index=Convert.ToInt32(target["native_row_index"]);Dictionary<string,object> program=null;
   foreach(object value in (IEnumerable)block["programs"]){var p=Map(value);if(Convert.ToInt32(p["native_row_index"])==index){NativeMemory.Require(program==null,"Strategy native row repeats.");program=p;}}
   NativeMemory.Require(program!=null,"Logical strategy program is absent.");return new Dictionary<string,object>{{"source_utf16le_hex",program["source_utf16le_hex"]},{"source_utf16le_sha256",program["source_utf16le_sha256"]}};
  }
  internal static Dictionary<string,object> ReadAction(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action) {
   if(Kind(action)==NativeDomainProjectCheck.Kind)return NativeDomainProjectCheck.Read(engine,context,project,action);
   if(Kind(action)==NativeProjectCompileDiagnostics.Kind)return NativeProjectCompileDiagnostics.Read(engine,context,project,action);
   if(Kind(action)==NativePictureResources.VectorCreateKind)return NativePictureResources.ReadVectorCreate(engine,context,project,action);
   string kind=Kind(action);if(kind==NativeCurrentTemplateControlOperations.GeometryBatchKind)return NativeCurrentTemplateControlOperations.ReadGeometryBatch(engine,context,project,action);Dictionary<string,object> extension=null;AdditionalRead(engine,context,project,action,ref extension);if(extension!=null)return extension;if(kind=="label-caption-rect"){var t=Map(action["target"]);return Map(NativeUsableLabelEditor.Inspect(engine,context,Convert.ToInt32(t["page_id"]),Convert.ToString(t["control_name"]))["before"]);}
   if(kind==NativeRecipePersistenceContract.ReadKind)return NativeRecipePersistenceContract.Read(engine,context,project,action);
   if(kind=="strategy-product-capability-catalog")return NativeStrategyWorkingModelEditing.ReadProductCapabilities(engine,context,project);
   if(IsWorkingStrategy(action))return NativeStrategyWorkingModelEditing.Read(engine,context,project,action);
   if(kind=="strategy-source"){
    var target=Map(action["target"]);object model;if(target.TryGetValue("model",out model))NativeMemory.Require(Convert.ToString(model)=="canonical"||Convert.ToString(model)=="working","Unknown native strategy model selector.");
    return NativeStrategyWorkingModelEditing.Read(engine,context,project,action);
   }
   if(kind=="control-properties")return NativeControlPropertyEditing.Read(engine,context,project,action);
   if(kind==NativeControlPropertyEditing.BatchKind)return NativeControlPropertyEditing.ReadBatch(engine,context,project,action);
   if(kind==NativeControlPropertyEditing.RenameKind)return NativeControlPropertyEditing.ReadRename(engine,context,project,action);
   if(kind==NativePageDocumentProperties.Kind)return NativePageDocumentProperties.Read(engine,context,project,action);
   if(kind=="page-event-definitions")return NativePageEventDefinitionCatalog.Read(engine,context,project,action);
   if(kind==NativePageViewOperations.Kind)return NativePageViewOperations.Read(engine,context,project,action);
   if(kind==NativeAlarmDefinitionEditing.Kind||kind==NativeAlarmTypedSpecification.Kind)return NativeAlarmDefinitionEditing.Read(engine,context,project,action);
   if(kind=="page-history")return NativePageHistoryEditing.Read(engine,context,project,action);
   if(kind=="control-native-create")return NativeCurrentTemplateControlOperations.ReadFactory(engine,context,project,action);
   if(kind=="reference-graph"||kind=="main-control-flush")return NativeReferencedPageEditing.ReferenceInspect(engine,context,project,action);
   if(kind=="data-catalog"||kind=="recipe-catalog")return NativeDataEngineering.Inspect(engine,context,project,kind=="data-catalog"?2:4);
   if(kind=="data-array-name-plan")return NativeDataGroupsAndArrays.PlanArrayNames(engine,context,project,Map(action["target"]));
   if(kind=="device-catalog"||kind=="device-flush")return NativeUsableDeviceBatch.Inspect(engine,context);
   if(kind=="picture-catalog")return NativePictureResources.ReadRaw(engine,context,project);
   if(kind==NativeLinguistOpenViewsRefresh.Kind)return NativeLinguistOpenViewsRefresh.Read(engine,context,project,action);
   if(kind==NativePageEventSourceEditing.Kind)return NativePageEventSourceEditing.Read(engine,context,project,action);
   if(Array.IndexOf(NativePageEventListEditing.Kinds,kind)>=0)return NativePageEventListEditing.Read(engine,context,project,action);
   if(kind=="language-catalog"||IsLanguage(kind))return NativeLinguistEditing.Read(engine,context,project,action);
   if(IsPicture(kind))return NativePictureResources.Read(engine,context,project,action);
   if(IsDevice(kind)){
    string name=NativePageControlPreparation.Text(Map(action["target"]),"name");Dictionary<string,object> selected=null;
    foreach(object value in(IEnumerable)NativeUsableDeviceBatch.Inspect(engine,context)["devices"]){var row=Map(value);if(Convert.ToString(row["name"])==name){NativeMemory.Require(selected==null,"Device logical name repeats.");selected=new Dictionary<string,object>(row);}}
    NativeMemory.Require(selected!=null,"Logical device target is absent.");selected["abi_profile_sha256"]=NativeUsableDeviceBatch.AbiProfileSha;return selected;
   }
   if(Array.IndexOf(NativeDataGroupsAndArrays.Kinds,kind)>=0)return NativeDataGroupsAndArrays.Read(engine,context,project,action);
   if(Array.IndexOf(NativeDataReferencedRename.Kinds,kind)>=0)return NativeDataReferencedRename.Read(engine,context,project,action);
   if(kind==NativeDataBatchEditing.Kind)return NativeDataBatchEditing.Read(engine,context,project,action);
   if(kind==NativeRecipeMatrixEditing.Kind)return NativeRecipeMatrixEditing.Read(engine,context,project,action);
   if(IsData(kind))return NativeDataEngineering.Read(engine,context,project,action);
   if(IsSource(kind))return ReadSourceAction(engine,context,action);
   if(kind=="strategy-delete"){
    var target=Map(action["target"]);var all=NativeUsableStrategyDeleteBatch.Inspect(engine,context);Dictionary<string,object> selected=null;
    foreach(object value in (IEnumerable)all["targets"]){var row=Map(value);if(Convert.ToInt32(row["block_id"])==Convert.ToInt32(target["block_id"])&&Convert.ToString(row["block_name"])==Convert.ToString(target["block_name"])){NativeMemory.Require(selected==null,"Strategy delete target repeats.");selected=new Dictionary<string,object>(row);}}
    NativeMemory.Require(selected!=null,"Strategy delete target is absent or reserved.");selected["abi_profile_sha256"]=NativeUsableStrategyDeleteBatch.AbiProfileSha;return selected;
   }
   if(IsPersistence(kind))return NativePersistenceEditing.Read(engine,context,project,action);
   if(kind==NativePreparedPageOperations.ReconcileCreatedRowKind)return NativePreparedPageOperations.ReadCreatedRowCompletion(engine,context,project,action);
   if(IsPageControl(kind))return NativePageControlPreparation.Read(engine,context,project,action);
   Dictionary<string,object> result=null;AdditionalRead(engine,context,project,action,ref result);NativeMemory.Require(result!=null,"No compiled reader for engineering kind: "+kind);return result;
  }
  internal static Dictionary<string,object> Inspect(Dictionary<string,object> request,NativeEngine engine,NativeContext context) {
   string project=NativeEngineeringProjectScope.ExpectedProjectPath;var preimages=new List<object>();var kinds=new HashSet<string>(Kinds(),StringComparer.Ordinal);foreach(string read in new string[]{NativeRecipePersistenceContract.ReadKind,"reference-graph","data-catalog","recipe-catalog","data-array-name-plan","device-catalog","picture-catalog","language-catalog","page-event-definitions","strategy-provider-catalog","strategy-product-capability-catalog",NativeProjectCompileDiagnostics.Kind,NativeStrategyWorkingModelEditing.AdoptionDiagnosticKind,NativeLinguistManagementEditing.ReadKind})kinds.Add(read);
   foreach(var action in InspectionActions(request)){
    string kind=Kind(action);NativeMemory.Require(kinds.Contains(kind),"Requested reader has no compiled implementation.");NativeOperationTrace.SetPhase("engineering-inspect-begin-"+Convert.ToString(action["action_id"])+"-"+kind);var before=ReadAction(engine,context,project,action);NativeOperationTrace.SetPhase("engineering-inspect-returned-"+Convert.ToString(action["action_id"]));object abi;
    if(!before.TryGetValue("abi_profile_sha256",out abi))abi=IsSource(kind)?NativeUsableStrategySourceBatch.AbiProfileSha:kind=="label-caption-rect"?NativeUsableLabelEditor.AbiProfileSha:action["abi_profile_sha256"];
    preimages.Add(new Dictionary<string,object>{{"action_id",action["action_id"]},{"kind",kind},{"target",action["target"]},{"abi_profile_sha256",abi},{"before",before}});
   }
   // Lazy page loading and native cache construction belong before this current digest.
   NativeOperationTrace.SetPhase("engineering-inspect-current-summary");var summary=NativeUsableEditPermit.Capture(engine,context);NativeOperationTrace.SetPhase("engineering-inspect-summary-returned");
   return new Dictionary<string,object>{{"ok",true},{"op","engineering-edit-inspect"},{"process_id",Process.GetCurrentProcess().Id},{"creation_filetime",Process.GetCurrentProcess().StartTime.ToFileTimeUtc()},{"native_thread_id",NativeMemory.GetCurrentThreadId()},
    {"editor_image_sha256",engine.ImageSha256},{"native_summary",summary},{"native_summary_utf8_sha256",NativeUsableEditPermit.Digest(summary)},{"compiled_kinds",Kinds()},{"action_preimages",preimages},
    {"current_scope","Owned native Pro fixture; dynamic counts; actual installed ABI"},{"write_attempted",false},{"candidate_functional_acceptance_pending",true},{"complete_serialization_preimage_claimed",false},{"binary_validation_reuse",NativeEngineeringFileHashes.Status()}};
  }
  static Unit PrepareAction(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action) {
   if(Kind(action)==NativePictureResources.VectorCreateKind)return PreparedAdditional(e,c,p,action,NativePictureResources.PrepareVectorCreate(e,c,p,action));
   string k=Kind(action);if(k==NativeCurrentTemplateControlOperations.GeometryBatchKind){var b=NativeCurrentTemplateControlOperations.PrepareGeometryBatch(e,c,p,action);return new Unit{Kind=k,Resource=b,Validate=delegate{NativePageControlPreparation.Before(action,NativeCurrentTemplateControlOperations.ReadGeometryBatch(e,c,p,action));},Apply=b.Apply,Flush=b.Flush};}if(k==NativeDomainProjectCheck.Kind){var a=NativeDomainProjectCheck.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}Unit extension=null;AdditionalPrepare(e,c,p,action,ref extension);if(extension!=null)return extension;
   if(IsWorkingStrategy(action)){var a=NativeStrategyWorkingModelEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=delegate{NativePageControlPreparation.Same(action["before"],NativeStrategyWorkingModelEditing.Read(e,c,p,action),"Native strategy working-model preimage changed before Claim.");},Apply=a.Apply,Flush=a.Flush};}
   if(k=="label-caption-rect"){var a=NativeUsableLabelEditor.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k=="control-properties"){var a=NativeControlPropertyEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativeControlPropertyEditing.BatchKind){var a=NativeControlPropertyEditing.PrepareBatch(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativeControlPropertyEditing.RenameKind){var a=NativeControlPropertyEditing.PrepareRename(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativePageDocumentProperties.Kind){var a=NativePageDocumentProperties.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativePageViewOperations.Kind){var a=NativePageViewOperations.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativeAlarmDefinitionEditing.Kind||k==NativeAlarmTypedSpecification.Kind){var a=NativeAlarmDefinitionEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k=="page-history"){var a=NativePageHistoryEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k=="control-native-create"){var a=NativeCurrentTemplateControlOperations.PrepareFactory(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k=="main-control-flush"){var a=NativeReferencedPageEditing.PrepareReferencedRename(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(IsPicture(k)){var a=NativePictureResources.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativeLinguistOpenViewsRefresh.Kind){var a=NativeLinguistOpenViewsRefresh.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativePageEventSourceEditing.Kind){var a=NativePageEventSourceEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(Array.IndexOf(NativePageEventListEditing.Kinds,k)>=0){var a=NativePageEventListEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(IsLanguage(k)){var a=NativeLinguistEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(Array.IndexOf(NativeDataGroupsAndArrays.Kinds,k)>=0){var a=NativeDataGroupsAndArrays.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(Array.IndexOf(NativeDataReferencedRename.Kinds,k)>=0){var a=NativeDataReferencedRename.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativeDataBatchEditing.Kind){var a=NativeDataBatchEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativeRecipeMatrixEditing.Kind){var a=NativeRecipeMatrixEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(IsData(k)){var a=NativeDataEngineering.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(IsPersistence(k)){var a=NativePersistenceEditing.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=a.ValidateBefore,Apply=a.Apply,Flush=a.Flush};}
   if(k==NativePreparedPageOperations.ReconcileCreatedRowKind){var a=NativePreparedPageOperations.PrepareCreatedRowCompletion(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=delegate{NativePageControlPreparation.Same(action["before"],NativePreparedPageOperations.ReadCreatedRowCompletion(e,c,p,action),"Prepared native page completion preimage changed before Claim.");},Apply=a.Apply,Flush=a.Flush};}
   if(IsPageControl(k)){var a=NativePageControlPreparation.Prepare(e,c,p,action);return new Unit{Kind=k,Resource=a,Validate=delegate{NativePageControlPreparation.Same(action["before"],ReadAction(e,c,p,action),"Prepared page/control preimage changed before Claim.");},Apply=a.Apply,Flush=a.Flush};}
   Unit result=null;AdditionalPrepare(e,c,p,action,ref result);NativeMemory.Require(result!=null,"No compiled prepared adapter for kind: "+k);return result;
  }
  internal static bool IsFinalPersistencePlan(NativeUsableEditPermit.Plan plan){if(!plan.Commit||!plan.RootSaveAllowed)return false;foreach(var action in plan.Actions)if(!IsPersistence(Kind(action)))return false;return plan.Actions.Count>0;}
  static void CheckIndependentPlan(NativeUsableEditPermit.Plan plan) {
   foreach(var checkAction in plan.Actions)if(Kind(checkAction)==NativeDomainProjectCheck.Kind)NativeMemory.Require(plan.Actions.Count==1&&!plan.Commit&&!plan.RootSaveAllowed,"Original Root85 full-project check must be a separate explicitly permitted action after saving; no bridge child Flush/RootSave.");
   bool finalPersistenceOnly=IsFinalPersistencePlan(plan);int singleSourceActions=0;
   var kinds=new HashSet<string>();bool persistence=false,editing=false;int structural=0,deviceActions=0,pictureActions=0,languageActions=0,workingActions=0;var pages=new HashSet<int>();var modules=new HashSet<int>();
   foreach(var action in plan.Actions) {
    string kind=Kind(action);if(kind=="strategy-source"||kind=="strategy-working-source"||kind=="strategy-canonical-source")singleSourceActions++;kinds.Add(kind);if(Array.IndexOf(NativeUsableDeviceBatch.DriverProperties.DeviceTree.Kinds,kind)>=0)NativeMemory.Require(finalPersistenceOnly||plan.Actions.Count==1,"Whole native device-tree operations require their own dependent step in the same session.");if(IsPersistence(kind))persistence=true;else editing=true;
    if(IsExtraDevice(kind))NativeMemory.Require(finalPersistenceOnly||plan.Actions.Count==1,"Whole native driver/property/tree operations require their own dependent step in the same session.");
    if(IsDevice(kind)||IsExtraDevice(kind)){deviceActions++;if(kind=="device-delete"||kind=="device-clone-template"||kind=="device-config-from-template")structural++;}
    if(IsPicture(kind))pictureActions++;
    if(IsLanguage(kind))languageActions++;
    if(IsStrategySession(action))workingActions++;
    if(kind==NativeControlPropertyEditing.RenameKind||kind==NativePreparedPageOperations.ReconcileCreatedRowKind)structural++;
    if(kind=="reference-redirect"||kind==NativeReferencedPageEditing.ReferenceSyncKind)structural++;
    if(kind==NativeDataGroupDeleting.Kind||Array.IndexOf(NativeDataPrototypeEditing.Kinds,kind)>=0)structural++;
    if(kind==NativePageViewOperations.Kind)structural++;
    if(IsData(kind))NativeMemory.Require(modules.Add(Convert.ToInt32(Map(action["target"])["module_id"])),"Multiple actions in one whole-saved data/recipe module need an explicit catalog chain; combine module values or use fresh permits without reopening.");
    if(kind=="page-create"||kind=="page-copy"||kind=="page-delete"||kind=="page-rename"||kind=="page-referenced-rename"||kind=="strategy-create-user"||kind=="strategy-delete"||kind=="data-create"||kind=="data-rename"||kind=="data-delete"||kind=="recipe-create"||kind=="recipe-copy"||kind=="recipe-rename"||kind=="recipe-delete"||kind=="data-group-copy"||Array.IndexOf(NativeDataReferencedRename.Kinds,kind)>=0||kind=="control-layer"||kind=="control-group"||kind=="control-ungroup")structural++;
    if(!IsSource(kind)&&!IsPersistence(kind)){var target=Map(action["target"]);object raw;if(target.TryGetValue("page_id",out raw))NativeMemory.Require(pages.Add(Convert.ToInt32(raw)),"Dependent edits to the same page need a fresh chained permit; combine its final values in one action.");}
   }
   NativeMemory.Require(singleSourceActions<=1,"Multiple complete source updates require strategy-source-batch per owner; use the file-only multi-owner programme expander for one same-editor logical batch. No native mutation has been entered.");
   NativeMemory.Require(!(persistence&&editing),"Use a separate persistence-only permit for deferred saving; editing permits use commit/save_scope directly.");
   NativeMemory.Require(finalPersistenceOnly||deviceActions==0||deviceActions==plan.Actions.Count,"Device native storage boundaries require a separate dependent step in the same open session.");
   if(kinds.Contains(NativeUsableDeviceBatch.DriverProperties.Kind)||kinds.Contains(NativeUsableDeviceBatch.DriverProperties.CatalogKind)||deviceActions>0&&!IsDevice(Kind(plan.Actions[0])))NativeMemory.Require(finalPersistenceOnly||plan.Actions.Count==1,"Device driver properties require a separate dependent step in the same open session.");
   NativeMemory.Require(finalPersistenceOnly||pictureActions==0||(pictureActions==1&&plan.Actions.Count==1),"Resource catalog changes/export require a separate dependent step in the same open session.");
   NativeMemory.Require(finalPersistenceOnly||languageActions==0||(languageActions==1&&plan.Actions.Count==1),"Linguist map updates/save require a separate dependent step in the same open session.");
   NativeMemory.Require(finalPersistenceOnly||workingActions==0||(workingActions==1&&plan.Actions.Count==1),"Strategy designer model operations require a separate dependent step in the same open session.");
   // Structural operations change the very page/name catalog used by prepared actions.
   // A fresh next batch remains in the same open editor; no reopen is required.
   NativeMemory.Require(finalPersistenceOnly||structural==0||(structural==1&&plan.Actions.Count==1),"Structural page operations need their own chained permit; current planner does not predict native-assigned catalogs.");
  }
  internal static Dictionary<string,object> Apply(Dictionary<string,object> request,NativeEngine engine,NativeContext context,Dictionary<string,object> directDocument=null,Dictionary<string,object> directSummary=null) {
   if(directDocument==null&&!request.ContainsKey("permit_file"))return ApplyDirect(request,engine,context);
   var result=new Dictionary<string,object>{{"ok",false},{"op","engineering-edit-batch"},{"automatic_retry",false},{"automatic_rollback",false},{"candidate_functional_acceptance_pending",true},{"actions",new List<object>()}};
   NativeUsableEditPermit.Plan plan=null;NativeUsableEditPermit.Lease lease=null;var units=new List<Unit>();var reports=(List<object>)result["actions"];
   var phaseTimes=new Dictionary<string,object>();result["phase_timings_ms"]=phaseTimes;var totalClock=Stopwatch.StartNew();var phaseClock=Stopwatch.StartNew();
   try {
    string project=NativeEngineeringProjectScope.ExpectedProjectPath;var summary=directSummary??NativeUsableEditPermit.Capture(engine,context);plan=directDocument!=null?NativeUsableEditPermit.LoadDirectPlan(directDocument,engine,context,summary,Kinds()):NativeUsableEditPermit.LoadPlan(request,engine,context,summary,Kinds());CheckIndependentPlan(plan);plan.ValidatePersistenceScopesBeforeClaim();/* Commit authorizes only the exact child scopes; RootSave is a separate explicit capability. */
    NativePageDuplicateProfile.PreparedRootSave rootSave=plan.Commit&&plan.RootSaveAllowed?new NativePageDuplicateProfile.PreparedRootSave(engine,project):null;
    phaseTimes["plan_and_save_context"]=phaseClock.Elapsed.TotalMilliseconds;phaseClock.Restart();
    // Content actions precede the grouped strategy unit, so it can preserve its full source catalog.
    HashSet<int> openStrategyIds=null;
    foreach(var action in plan.Actions)if(!IsLifecycleStrategy(action)&&(IsCanonicalSource(action)||Kind(action)=="strategy-delete"||Kind(action)=="strategy-flush")){
     var target=Map(action["target"]);object raw;string kind=Kind(action);
     if(kind=="strategy-create-user")continue;
     NativeMemory.Require(target.TryGetValue("block_id",out raw)||target.TryGetValue("strategy_id",out raw),"Canonical strategy target needs its native block ID.");
     if(openStrategyIds==null)openStrategyIds=NativeStrategyWorkingModelEditing.OpenBlockIds(engine,context,project);
     NativeMemory.Require(!openStrategyIds.Contains(Convert.ToInt32(raw)),"This strategy has a native designer working document; edit/save that model to avoid a later Doc83 overwriting canonical changes.");
    }
    foreach(var action in plan.Actions)if((!IsCanonicalSource(action)||IsWorkingStrategy(action))&&!IsDevice(Kind(action))&&(Kind(action)!="strategy-delete"||IsLifecycleStrategy(action)))units.Add(PrepareAction(engine,context,project,action));
    bool hasDevice=false;foreach(var action in plan.Actions)if(IsDevice(Kind(action)))hasDevice=true;
    if(hasDevice){var a=NativeUsableDeviceBatch.Prepare(engine,context,plan);units.Add(new Unit{Kind="device-batch",Resource=a,Validate=a.ValidateBefore,Apply=delegate(NativeUsableEditPermit.Lease l){a.Apply(l);return a.Status();},Flush=delegate(NativeUsableEditPermit.Lease l){a.Flush(l);return a.Status();}});}
    bool hasSource=false;foreach(var action in plan.Actions)if(IsCanonicalSource(action))hasSource=true;
    if(hasSource){var a=NativeUsableStrategySourceBatch.Prepare(engine,context,plan);units.Add(new Unit{Kind="strategy-batch",Resource=a,Validate=a.ValidateBefore,Apply=delegate(NativeUsableEditPermit.Lease l){a.Apply(l);return a.Status();},Flush=delegate(NativeUsableEditPermit.Lease l){a.Flush(l);return a.Status();}});}
    bool hasDelete=false;foreach(var action in plan.Actions)if(Kind(action)=="strategy-delete"&&!IsLifecycleStrategy(action))hasDelete=true;
    if(hasDelete){var a=NativeUsableStrategyDeleteBatch.Prepare(engine,context,plan);units.Add(new Unit{Kind="strategy-delete",Resource=a,Validate=a.ValidateBefore,Apply=delegate(NativeUsableEditPermit.Lease l){a.Apply(l);return a.Status();},Flush=delegate(NativeUsableEditPermit.Lease l){a.Flush(l);return a.Status();}});}
    foreach(Unit unit in units){var related=unit.Resource as INativePreparedRelatedPersistence;if(related!=null)related.ValidatePersistence(plan);}
    phaseTimes["prepare"]=phaseClock.Elapsed.TotalMilliseconds;phaseClock.Restart();
    lease=plan.Claim(delegate{foreach(Unit unit in units)unit.Validate();});
    phaseTimes["validate_current_targets"]=phaseClock.Elapsed.TotalMilliseconds;phaseClock.Restart();
    // Independent content units can all modify before their consolidated child flushes.
    foreach(Unit unit in units){var report=unit.Apply(lease);reports.Add(new Dictionary<string,object>{{"unit",unit.Kind},{"apply",report}});}
    phaseTimes["apply_verify_refresh"]=phaseClock.Elapsed.TotalMilliseconds;phaseClock.Restart();
    if(plan.Commit){foreach(Unit unit in units)reports.Add(new Dictionary<string,object>{{"unit",unit.Kind},{"flush",unit.Flush(lease)}});if(rootSave!=null)result["root_save"]=rootSave.Execute(lease);}
    phaseTimes["flush_and_save"]=phaseClock.Elapsed.TotalMilliseconds;
    result["ok"]=true;result["status"]=plan.Commit?"native-batch-completed-pending-consolidated-acceptance":"native-edits-completed-persistence-deferred";result["explicit_child_flushes_requested"]=plan.Commit;result["root_save_requested"]=plan.Commit&&plan.RootSaveAllowed;result["persistence_scope"]=!plan.Commit?"all explicit persistence deferred":plan.RootSaveAllowed?"scoped children plus one root save":"scoped child persistence only";result["original_autosave_is_separate"]=true;result["native_actions_may_update_their_own_database_records"]=true;result["native_configuration_check_verified"]=false;result["close_reopen_verified"]=false;
    if(plan.Actions.Count==1&&Kind(plan.Actions[0])==NativeDomainProjectCheck.Kind){NativeMemory.Require(reports.Count==1,"Original project-check unit/report count differs.");var checkReport=Map(Map(reports[0])["apply"]);bool completed=Object.Equals(checkReport["original_worker_returned"],true),passed=Object.Equals(checkReport["native_check_passed"],true);result["status"]="original-full-project-check-worker-returned";result["persistence_scope"]="original worker-defined side effects only; no bridge Flush/RootSave";result["native_configuration_check_completed"]=completed;result["native_configuration_check_passed"]=passed;result["native_configuration_check_verified"]=completed&&passed;result["native_configuration_check_return_int32"]=checkReport["original_worker_return_int32"];result["error_count"]=null;result["warning_count"]=null;result["error_warning_counts_known"]=false;result["headless"]=false;result["original_worker_ui_preserved"]=true;}
   }catch(Exception error){result["error"]=error.GetType().Name+": "+error.Message;result["managed_stack"]=error.StackTrace;result["comparison_evidence"]=NativeEngineeringComparisonEvidence.Metadata(error);result["phase"]=NativeOperationTrace.Phase;result["native_result_may_be_partial"]=NativeOperationTrace.MutationAttempted;}
   finally{for(int i=units.Count-1;i>=0;i--)try{units[i].Dispose();}catch(Exception error){result["ok"]=false;result["owned_cleanup_error"]=error.GetType().Name+": "+error.Message;}phaseTimes["request_total_including_cleanup"]=totalClock.Elapsed.TotalMilliseconds;}
   if(lease!=null)result["permit_status"]=lease.Status();else if(plan!=null)result["permit_status"]=plan.ClaimStatus();result["write_attempted"]=NativeOperationTrace.MutationAttempted;result["binary_validation_reuse"]=NativeEngineeringFileHashes.Status();return result;
  }
 }
}
