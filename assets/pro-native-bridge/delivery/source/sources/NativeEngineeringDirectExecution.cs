// Direct execution: fresh in-process read/prepare/apply, no permit or durable claim files.
// Native process/project/ABI/owner validation and in-memory phase sequencing remain unchanged.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.IO;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeEngineeringBatch {
  internal static string DirectInputFile(string file){string p=Path.GetFullPath(file);NativeMemory.Require(File.Exists(p)&&(File.GetAttributes(p)&FileAttributes.Directory)==0,"Specification is not an existing regular file.");NativeMemory.Require(new FileInfo(p).Length<=Int32.MaxValue,"Specification exceeds the CLR string/array representation.");return p;}
  static Dictionary<string,object> DirectClone(Dictionary<string,object> value){return new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(NativeUsableEditPermit.Json(value));}
  static bool DirectBoolean(Dictionary<string,object>d,string key,bool fallback){object v;if(!d.TryGetValue(key,out v))return fallback;NativeMemory.Require(v is bool,key+" must be Boolean.");return(bool)v;}
  static string DirectReference(Dictionary<string,object> row,out string path) {
   object raw;
   NativeMemory.Require(row.Count==1&&row.TryGetValue("$native_result",out raw),"Native result reference must be the whole value.");
   var reference=Map(row["$native_result"]);
   NativeMemory.Require(reference.Count==2&&reference.ContainsKey("action_id")&&reference["action_id"] is string&&reference.ContainsKey("path")&&reference["path"] is string,
    "Native result reference needs a string action_id and path.");
   path=(string)reference["path"];
   NativeMemory.Require(path.Length==0||path[0]=='/',"Native result path must be a JSON Pointer.");
   for(int i=0;i<path.Length;i++)if(path[i]=='~'){
    NativeMemory.Require(i+1<path.Length&&(path[i+1]=='0'||path[i+1]=='1'),"Invalid native result JSON Pointer escape.");
    i++;
   }
   return (string)reference["action_id"];
  }
  static object DirectResultPointer(object value,string path) {
   if(path.Length==0)return value;
   foreach(string raw in path.Substring(1).Split('/')){
    string key=raw.Replace("~1","/").Replace("~0","~");var row=value as IDictionary<string,object>;
    if(row!=null){NativeMemory.Require(row.TryGetValue(key,out value),"Native result field is absent: "+path);continue;}
    var list=value as IList;int index;
    bool valid=Int32.TryParse(key,System.Globalization.NumberStyles.None,System.Globalization.CultureInfo.InvariantCulture,out index);
    NativeMemory.Require(list!=null&&valid&&index>=0&&index<list.Count&&
     index.ToString(System.Globalization.CultureInfo.InvariantCulture)==key,"Native result list index is absent: "+path);
    value=list[index];
   }
   return value;
  }
  static object ResolveDirectResults(object value,Dictionary<string,Dictionary<string,object>> receipts) {
   var row=value as Dictionary<string,object>;
   if(row!=null){
    if(row.ContainsKey("$native_result")){
     string path;string id=DirectReference(row,out path);Dictionary<string,object> receipt;
     NativeMemory.Require(receipts.TryGetValue(id,out receipt),"Native result dependency has not completed successfully: "+id);
     return NativeDynamicCollections.CopyValue(DirectResultPointer(receipt,path),false);
    }
    var result=new Dictionary<string,object>();
    foreach(var pair in row)result.Add(pair.Key,ResolveDirectResults(pair.Value,receipts));
    return result;
   }
   if(value is IEnumerable&&!(value is string)){
    var result=new List<object>();
    foreach(object child in(IEnumerable)value)result.Add(ResolveDirectResults(child,receipts));
    return result;
   }
   return value;
  }
  static bool HasDirectResults(object value) {
   foreach(var row in NativeDynamicCollections.DictionaryValues(value))if(row.ContainsKey("$native_result"))return true;
   return false;
  }
  static void ValidateDirectReferences(Dictionary<string,object> action,HashSet<string> priorIds) {
   NativeMemory.Require(!action.ContainsKey("$native_result"),"Native result references belong in action target, after, or clone source.");
   foreach(var field in action){
    foreach(var row in NativeDynamicCollections.DictionaryValues(field.Value)){
     if(!row.ContainsKey("$native_result"))continue;
     NativeMemory.Require(field.Key=="target"||field.Key=="after"||(field.Key=="source"&&IsDirectClone(Kind(action))),"Native result references belong in action target, after, or clone source.");
     string path;string id=DirectReference(row,out path);
     NativeMemory.Require(priorIds.Contains(id),"Native result dependency must name an earlier action: "+id);
    }
   }
  }
  static Dictionary<string,object> DirectReceipt(Dictionary<string,object> result) {
   var applies=new List<object>();
   foreach(object report in(IEnumerable)result["actions"]){
    object value;if(Map(report).TryGetValue("apply",out value))applies.Add(value);
   }
   return new Dictionary<string,object>{{"result",result},{"applies",applies},{"apply",applies.Count==1?applies[0]:null}};
  }
  static Dictionary<string,object> DirectSpec(Dictionary<string,object> request){Dictionary<string,object> prepared;if(NativeRequestPipeline.TrySpecification(request,out prepared))return prepared;object raw;if(request.TryGetValue("specification",out raw))return DirectClone(Map(raw));NativeMemory.Require(request.TryGetValue("specification_file",out raw),"Direct execution needs specification or specification_file.");string path=DirectInputFile(Convert.ToString(raw));object hash;if(request.TryGetValue("specification_sha256",out hash))NativeMemory.Require(NativeMemory.Hash(path)==Convert.ToString(hash),"Submitted specification file changed.");return new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));}
  static bool DirectCommit(Dictionary<string,object> specification,Dictionary<string,object> action){if(Kind(action)==NativeDomainProjectCheck.Kind)return false;object raw;var scope=specification.TryGetValue("save_scope",out raw)?Map(raw):new Dictionary<string,object>();return IsPersistence(Kind(action))||DirectBoolean(scope,"root_save",DirectBoolean(specification,"root_save",false))||DirectBoolean(specification,"commit",false);}
  static Dictionary<string,object> DirectSaveScope(Dictionary<string,object> specification,Dictionary<string,object> action,bool final){object raw;var scope=specification.TryGetValue("save_scope",out raw)?DirectClone(Map(raw)):new Dictionary<string,object>();bool commit=DirectCommit(specification,action);bool root=DirectBoolean(scope,"root_save",DirectBoolean(specification,"root_save",false));scope["root_save"]=Kind(action)=="root-flush"||(commit&&final&&root);foreach(string key in new[]{"affected_page_ids","strategy_ids","module_ids","created_page_actions","created_strategy_actions"})scope[key]=new object[0];scope["main_control_document"]=true;scope["linguist_document"]=true;string kind=Kind(action),id=Convert.ToString(action["action_id"]);if(kind=="page-create"||kind=="page-copy")scope["created_page_actions"]=new[]{id};if(NativeUsableEditPermit.IsStrategyCreation(kind))scope["created_strategy_actions"]=new[]{id};return scope;}
  static Dictionary<string,object> DirectDocument(Dictionary<string,object> specification,Dictionary<string,object> action,Dictionary<string,object> summary,NativeEngine engine,bool final){return new Dictionary<string,object>{{"schema",1},{"purpose",NativeUsableEditPermit.Purpose},{"trial_id",Guid.NewGuid().ToString()},{"process_id",Process.GetCurrentProcess().Id},{"creation_filetime",Process.GetCurrentProcess().StartTime.ToFileTimeUtc()},{"ui_thread_id",NativeMemory.GetCurrentThreadId()},{"project_path",NativeEngineeringProjectScope.ExpectedProjectPath},{"project_sha256",summary["disk_sha256"]},{"editor_image_sha256",engine.ImageSha256},{"native_summary_utf8_sha256",NativeUsableEditPermit.Digest(summary)},{"commit",DirectCommit(specification,action)},{"save_scope",DirectSaveScope(specification,action,final)},{"actions",new object[]{action}}};}
  static Dictionary<string,object> DirectSummary(NativeEngine engine,NativeContext context){IntPtr root=NativeMemory.Ptr(engine.Address(0xFBB578),NativeLayout.Offset("app.root_document"));NativeMemory.Require(root!=IntPtr.Zero&&NativeMemory.Ptr(root,0)==engine.Address(0xD57684)&&NativeMemory.Ptr(root,NativeLayout.Offset("root.object_model"))==context.ObjectModel,"Current direct root/model differs.");return new Dictionary<string,object>{{"schema",1},{"scope","direct current process/project/root identity; action-specific reader supplies its exact target preimage"},{"project_path",NativeEngineeringProjectScope.ExpectedProjectPath},{"disk_sha256",NativeMemory.Hash(NativeEngineeringProjectScope.ExpectedProjectPath)},{"root",NativeMemory.Hex(root)},{"root_modified",NativeMemory.I32(root,NativeLayout.Offset("document.modified"))},{"compile_valid",NativeMemory.I32(root,NativeLayout.Offset("document.compile_valid"))},{"complete_project_summary",false}};}
  static int DirectFactoryRunEnd(Dictionary<string,object> spec,List<Dictionary<string,object>> actions,int start){
   if(!DirectBoolean(spec,"coalesce_native_creates",true)||Kind(actions[start])!="control-native-create"||DirectCommit(spec,actions[start])||actions[start].ContainsKey("before"))return start;
   var first=Map(actions[start]["target"]);int page=Convert.ToInt32(first["page_id"]);string name=Convert.ToString(first["page_name"]);int end=start;
   for(int i=start+1;i<actions.Count;i++){var action=actions[i];if(Kind(action)!="control-native-create"||DirectCommit(spec,action)||action.ContainsKey("before"))break;var target=Map(action["target"]);if(HasDirectResults(target)||Convert.ToInt32(target["page_id"])!=page||Convert.ToString(target["page_name"])!=name)break;end=i;}return end;
  }
  static bool IsDirectClone(string kind){return kind=="control-template-clone"||kind=="control-clone";}
  static bool TryClonePage(object value,out int page,out string name){
   page=0;name=null;var selector=value as Dictionary<string,object>;object id,raw;
   if(selector==null||!selector.TryGetValue("page_id",out id)||!selector.TryGetValue("page_name",out raw)||!(raw is string))return false;
   name=(string)raw;
   return name.Length>0&&Int32.TryParse(Convert.ToString(id,System.Globalization.CultureInfo.InvariantCulture),
    System.Globalization.NumberStyles.Integer,System.Globalization.CultureInfo.InvariantCulture,out page)&&page>=0;
  }
  // Preserve legacy action projections only where a later result dependency consumes them.
  static HashSet<string> DirectLegacyProjectionActions(List<Dictionary<string,object>> actions){
   var affected=new HashSet<string>(StringComparer.Ordinal);
   foreach(var action in actions)foreach(var row in NativeDynamicCollections.DictionaryValues(action)){
    if(!row.ContainsKey("$native_result"))continue;string path;
    string id=DirectReference(row,out path);
    foreach(string prefix in new[]{"/apply","/applies/0","/result/actions/0/apply"})
     foreach(string suffix in new[]{"/forest_after","/page_after/top_level_controls","/native_history_store_projection","/complete_forest_after"}){
      string field=prefix+suffix;
      if(path.Length==0||path==field||path.StartsWith(field+"/",StringComparison.Ordinal)||field.StartsWith(path+"/",StringComparison.Ordinal))affected.Add(id);
     }
   }
   return affected;
  }
  static int DirectCloneRunEnd(Dictionary<string,object> spec,List<Dictionary<string,object>> actions,int start,HashSet<string> legacyProjection){
   string kind=Kind(actions[start]);
   if(!IsDirectClone(kind)||!DirectBoolean(spec,"coalesce_native_clones",true))return start;
   int page;string name;
   if(!TryClonePage(actions[start]["target"],out page,out name))return start;
   int end=start-1;
   for(int i=start;i<actions.Count;i++){
    var action=actions[i];object source;
    if(Kind(action)!=kind||DirectCommit(spec,action)||action.ContainsKey("before")||legacyProjection.Contains(Convert.ToString(action["action_id"]))||!action.TryGetValue("source",out source))break;
    int current,sourcePage;string currentName,sourceName;
    if(!TryClonePage(action["target"],out current,out currentName)||current!=page||currentName!=name||
      !TryClonePage(source,out sourcePage,out sourceName)||sourcePage!=page||sourceName!=name)break;
    end=i;
   }
   return end>start?end:start;
  }
  internal static List<Dictionary<string,object>> ReadDirectActions(Dictionary<string,object> spec,bool prepared){
   NativeMemory.Require(spec.ContainsKey("actions"),"Direct specification needs actions.");var actions=new List<Dictionary<string,object>>();var ids=new HashSet<string>(StringComparer.Ordinal);var supported=new HashSet<string>(Kinds(),StringComparer.Ordinal);
   foreach(var field in spec)if(field.Key!="actions")NativeMemory.Require(field.Key!="$native_result"&&!HasDirectResults(field.Value),"Native result references belong in action target, after, or clone source.");
   foreach(object raw in(IEnumerable)spec["actions"]){var action=prepared?Map(raw):DirectClone(Map(raw));object id;if(!action.TryGetValue("action_id",out id))action["action_id"]="direct_"+actions.Count.ToString("D4");string aid=Convert.ToString(action["action_id"]);NativeMemory.Require(aid.Length>0&&aid.Length<=96&&!ids.Contains(aid),"Action ID is empty/repeated.");NativeAbiTargetProfiles.SelectFeature(action,"validate-action-kind");if(!supported.Contains(Kind(action)))throw NativeAbiTargetProfiles.Problem("unsupported_feature","No implemented adapter for: "+Kind(action),"compiled engineering adapters",Kind(action));Map(action["target"]);Map(action["after"]);ValidateDirectReferences(action,ids);ids.Add(aid);actions.Add(action);}
   NativeMemory.Require(actions.Count>0,"Direct request has no actions.");return actions;
  }
  static Dictionary<string,object> ValidateDesignPreflight(NativeEngine engine,NativeContext context,Dictionary<string,object> design){
   string project=NativeEngineeringProjectScope.ExpectedProjectPath;
   NativeMemory.Require(Convert.ToInt32(design["process_id"])==Process.GetCurrentProcess().Id&&Convert.ToInt64(design["creation_filetime"])==Process.GetCurrentProcess().StartTime.ToFileTimeUtc(),"Designed editor process generation changed before first mutation.");
   NativeMemory.Require(NativeUsableEditPermit.SamePath(Convert.ToString(design["project_path"]),project),"Designed project path differs.");
   var identity=DirectSummary(engine,context);
   NativeMemory.Require(Object.Equals(identity["disk_sha256"],design["project_sha256"])&&Object.Equals(identity["root"],design["root"]),"Designed project file/root identity changed before first mutation.");
   var result=NativeCurrentTemplateControlOperations.ValidateDesignPages(engine,context,project,design);object rows;
   if(design.TryGetValue("style_preimages",out rows))foreach(object value in (IEnumerable)rows){
    var item=Map(value);var action=new Dictionary<string,object>{{"kind","control-properties"},{"target",item["target"]},{"after",new Dictionary<string,object>{{"properties",item["properties"]}}}};
    var observed=NativeControlPropertyEditing.Read(engine,context,project,action);var actual=new List<object>();
    foreach(object requested in (IEnumerable)item["properties"]){var property=Map(requested);Dictionary<string,object> match=null;
     foreach(object raw in (IEnumerable)observed["properties"]){var row=Map(raw);if(!Object.Equals(row["native_owner"],observed["selected_owner"])||!Object.Equals(row["native_key"],property["native_key"])||Convert.ToInt32(row["native_type_tag"])!=Convert.ToInt32(property["native_type_tag"]))continue;NativeMemory.Require(match==null,"Design style getter key/type is ambiguous.");match=row;}
     NativeMemory.Require(match!=null,"Design style getter key/type disappeared.");actual.Add(new Dictionary<string,object>{{"native_key",match["native_key"]},{"native_type_tag",match["native_type_tag"]},{"value",match["value"]}});
    }
    NativePageControlPreparation.Same(item["properties"],actual,"Designed style sample changed before first mutation.");
   }
   if(design.TryGetValue("button_preimages",out rows))foreach(object value in (IEnumerable)rows){
    var item=Map(value);var action=new Dictionary<string,object>{{"kind",NativeButtonActionEditing.Kind},{"target",item["target"]},{"after",new Dictionary<string,object>()}};
    var observed=NativeButtonActionEditing.ReadDesignPhases(engine,context,project,action);
    NativePageControlPreparation.Same(item["phases"],observed,"Designed button binding/actions changed before first mutation.");
   }
   if(design.TryGetValue("variables",out rows)){
    var names=new HashSet<string>(StringComparer.Ordinal);foreach(object value in (IEnumerable)NativeDataEngineering.Inspect(engine,context,project,2)["records"])names.Add(Convert.ToString(Map(value)["name"]));
    foreach(object name in (IEnumerable)rows)NativeMemory.Require(names.Contains(Convert.ToString(name)),"Designed variable is no longer present: "+name);
   }
   if(design.TryGetValue("configured_auxiliary_page_ids",out rows)){
    IntPtr manager,main;var state=NativeReferencedPageEditing.PagePropertiesMainRead(new NativeReferencedPageEditing.Api(engine,context,project),out manager,out main);
    var ids=new HashSet<int>();foreach(object value in (IEnumerable)Map(Map(state["arrays"])["AuxIds"])["values"])ids.Add(Convert.ToInt32(value));
    foreach(object id in (IEnumerable)rows)NativeMemory.Require(ids.Contains(Convert.ToInt32(id)),"Designed auxiliary page is no longer configured: "+id);
   }
   return result;
  }
  static Dictionary<string,object> ApplyDirect(Dictionary<string,object> request,NativeEngine engine,NativeContext context){
   var result=new Dictionary<string,object>{{"ok",false},{"op","engineering-edit-batch"},{"execution_mode","direct"},{"permit_file_required",false},{"durable_permit_claim_used",false},{"approval_required",false},{"automatic_retry",false},{"automatic_rollback",false},{"actions",new List<object>()},{"direct_action_results",new List<object>()}};
   var reports=(List<object>)result["actions"];var flushReports=new List<object>();var individual=(List<object>)result["direct_action_results"];var preimages=new List<object>();object cloneFirstActionId=null;var factoryBatches=new List<object>();result["native_factory_batches"]=factoryBatches;var cloneBatches=new List<object>();result["native_clone_batches"]=cloneBatches;Dictionary<string,object> firstSummary=null,last=null;int completed=0,factoryEnd=-1,cloneEnd=-1,cloneStart=-1;NativeCurrentTemplateControlOperations.CloneBatchScope cloneBatch=null;NativeCurrentTemplateControlOperations.FactoryBatchScope factoryBatch=null;NativeCurrentTemplateControlOperations.DirectFactoryCaptureScope factoryCapture=null;string phase="direct-load-specification";string activeActionId=null;
   try{
    var spec=DirectSpec(request);var actions=ReadDirectActions(spec,NativeRequestPipeline.IsPrepared(request));
    var legacyProjection=DirectLegacyProjectionActions(actions);
    result["features"]=Features;
    object required;if(spec.TryGetValue("required_features",out required))foreach(object feature in (IEnumerable)required)
     NativeMemory.Require(Array.IndexOf(Features,Convert.ToString(feature))>=0,"Native engine lacks requested semantic feature: "+feature);
    object design;if(spec.TryGetValue("design_preflight",out design)){
     phase="direct-design-preflight";NativeOperationTrace.SetPhase(phase);
     result["design_preflight"]=ValidateDesignPreflight(engine,context,Map(design));
    }
    result["requested_action_count"]=actions.Count;var receipts=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);result["native_result_reference_contract"]="mcgs-native-result/v1";
    for(int i=0;i<actions.Count;i++){
     var action=actions[i];activeActionId=Convert.ToString(action["action_id"]);
     NativeAbiTargetProfiles.SelectFeature(action,"direct-resolve-dependencies");phase="direct-resolve-"+activeActionId;
     if(HasDirectResults(action["target"]))action["target"]=Map(ResolveDirectResults(action["target"],receipts));
     if(HasDirectResults(action["after"]))action["after"]=Map(ResolveDirectResults(action["after"],receipts));
     string kind=Kind(action);
     object cloneSource;
     if(IsDirectClone(kind)&&action.TryGetValue("source",out cloneSource)&&HasDirectResults(cloneSource))
      action["source"]=Map(ResolveDirectResults(cloneSource,receipts));
     NativeAbiTargetProfiles.SelectFeature(action,"direct-prepare-action");phase="direct-read-"+Convert.ToString(action["action_id"]);NativeOperationTrace.SetPhase(phase);
     if(factoryBatch==null){factoryEnd=DirectFactoryRunEnd(spec,actions,i);if(factoryEnd>i)factoryBatch=NativeCurrentTemplateControlOperations.BeginFactoryBatch(engine,context,NativeEngineeringProjectScope.ExpectedProjectPath,Map(action["target"]));}
     if(cloneBatch==null&&IsDirectClone(kind)){cloneEnd=DirectCloneRunEnd(spec,actions,i,legacyProjection);if(cloneEnd>i){cloneStart=i;cloneFirstActionId=action["action_id"];cloneBatch=NativeCurrentTemplateControlOperations.BeginCloneBatch(engine,context,NativeEngineeringProjectScope.ExpectedProjectPath,Map(action["target"]),kind);}}
     var actionClock=Stopwatch.StartNew();
     if(kind==NativeDomainProjectCheck.Kind){var after=Map(action["after"]);foreach(string k in new[]{"run_original_root85","confirm_project_already_saved","allow_original_worker_ui","allow_original_worker_persistence","preserve_original_warnings_and_exceptions","accept_unknown_error_warning_counts"})after[k]=true;}
     if(kind=="control-native-create"){NativeAbiTargetProfiles.SelectFeature(action,"direct-factory-capture");factoryCapture=NativeCurrentTemplateControlOperations.BeginDirectFactoryCapture(engine,context,NativeEngineeringProjectScope.ExpectedProjectPath,action);}
     object capturedPropertyBaseline=null;
     var before=kind==NativeControlPropertyEditing.BatchKind
      ?NativeControlPropertyEditing.ReadDirectBatch(engine,context,NativeEngineeringProjectScope.ExpectedProjectPath,action,out capturedPropertyBaseline)
      :ReadAction(engine,context,NativeEngineeringProjectScope.ExpectedProjectPath,action);object abi;if(!before.TryGetValue("abi_profile_sha256",out abi)){if(IsSource(kind))abi=NativeUsableStrategySourceBatch.AbiProfileSha;else if(kind=="label-caption-rect")abi=NativeUsableLabelEditor.AbiProfileSha;else{NativeMemory.Require(action.TryGetValue("abi_profile_sha256",out abi),"Adapter reader returned no ABI identity.");}}
     double readMs=actionClock.Elapsed.TotalMilliseconds;actionClock.Restart();
     if(!action.ContainsKey("before"))action["before"]=before;if(!action.ContainsKey("abi_profile_sha256"))action["abi_profile_sha256"]=abi;
     var preimage=new Dictionary<string,object>{{"action_id",action["action_id"]},{"kind",kind},{"target",action["target"]},{"abi_profile_sha256",abi},{"before",before}};
     if(IsDirectClone(kind)&&action.TryGetValue("source",out cloneSource))preimage["source"]=action["source"];
     preimages.Add(preimage);
     //Lazy page/module loading has completed before this one required summary.
     phase="direct-current-summary";NativeAbiTargetProfiles.SelectFeature(null,"direct-current-summary");var summary=DirectSummary(engine,context);if(firstSummary==null)firstSummary=summary;NativeAbiTargetProfiles.SelectFeature(action,"direct-prepare-apply");
     var document=DirectDocument(spec,action,summary,engine,i==actions.Count-1);phase="direct-apply-"+Convert.ToString(action["action_id"]);
     double summaryMs=actionClock.Elapsed.TotalMilliseconds;actionClock.Restart();
     last=Apply(request,engine,context,document,summary,capturedPropertyBaseline);if(factoryCapture!=null){factoryCapture.Dispose();factoryCapture=null;}individual.Add(new Dictionary<string,object>{{"action_id",action["action_id"]},{"result",last},{"direct_summary",summary},{"direct_summary_utf8_sha256",document["native_summary_utf8_sha256"]},{"timings_ms",new Dictionary<string,object>{{"read_target",readMs},{"current_summary_and_plan",summaryMs},{"prepare_apply_verify_and_flush",actionClock.Elapsed.TotalMilliseconds}}}});
     foreach(object report in(IEnumerable)last["actions"]){var row=Map(report);if(row.ContainsKey("flush"))flushReports.Add(report);else reports.Add(report);}
     if(!Object.Equals(last["ok"],true)){result["failed_action_id"]=action["action_id"];result["error"]=last.ContainsKey("error")?last["error"]:"Native action did not complete.";foreach(string key in new[]{"native_abi","failure_category","affected_feature"})if(last.ContainsKey(key))result[key]=last[key];break;}if(cloneBatch!=null)cloneBatch.VerifiedMutation();receipts.Add(Convert.ToString(action["action_id"]),DirectReceipt(last));completed++;result["completed_action_count"]=completed;
     if(cloneBatch!=null&&i==cloneEnd){
      NativeAbiTargetProfiles.SelectFeature(action,"direct-clone-batch-finalize");phase="direct-clone-batch-finalize";
      result["batch_finalization_action_id"]=action["action_id"];
      try{
       var completedBatch=cloneBatch.Complete();
       completedBatch["first_action_id"]=actions[cloneStart]["action_id"];completedBatch["last_action_id"]=action["action_id"];
       cloneBatches.Add(completedBatch);
      }
      catch{
       result["native_batch_finalization_failed"]=true;result["failed_action_id"]=action["action_id"];
       result["incomplete_native_clone_batch"]=cloneBatch.IncompleteReport(actions[cloneStart]["action_id"],action["action_id"]);
       throw;
      }
      finally{cloneBatch.Dispose();cloneBatch=null;}
      result.Remove("batch_finalization_action_id");
     }
     if(factoryBatch!=null&&i==factoryEnd){NativeAbiTargetProfiles.SelectFeature(action,"direct-factory-batch-finalize");phase="direct-factory-batch-finalize";result["batch_finalization_action_id"]=action["action_id"];try{factoryBatches.Add(factoryBatch.Complete());}catch{result["native_batch_finalization_failed"]=true;result["failed_action_id"]=action["action_id"];throw;}finally{factoryBatch.Dispose();factoryBatch=null;}result.Remove("batch_finalization_action_id");}
    }
    result["ok"]=completed==actions.Count;result["completed_action_count"]=completed;result["requested_action_count"]=actions.Count;
    if(last!=null){foreach(string key in new[]{"status","root_save","root_save_skipped","permit_status","explicit_child_flushes_requested","root_save_requested","persistence_scope","native_configuration_check_completed","native_configuration_check_passed","native_configuration_check_verified","native_configuration_check_return_int32","error_count","warning_count","error_warning_counts_known","headless","original_worker_ui_preserved"})if(last.ContainsKey(key))result[key]=last[key];}
   }catch(Exception error){if(activeActionId!=null&&!result.ContainsKey("failed_action_id"))result["failed_action_id"]=activeActionId;result["error"]=error.GetType().Name+": "+error.Message;result["managed_stack"]=error.StackTrace;result["comparison_evidence"]=NativeEngineeringComparisonEvidence.Metadata(error);NativeAbiTargetProfiles.RecordFailure(result,error);}finally{
    if(cloneBatch!=null){
     if(cloneBatch.MutationEntered)result["incomplete_native_clone_batch"]=cloneBatch.RefreshPartial(cloneFirstActionId,activeActionId);
     cloneBatch.Dispose();
    }
    if(factoryCapture!=null){factoryCapture.Dispose();factoryCapture=null;}if(factoryBatch!=null){result["incomplete_factory_batch_created_count"]=factoryBatch.appliedCount;result["incomplete_factory_batch_count_is_lower_bound"]=true;factoryBatch.Dispose();}result["completed_action_count"]=completed;}
   foreach(object report in flushReports)reports.Add(report);
   if(firstSummary!=null)result["direct_inspection"]=new Dictionary<string,object>{{"ok",true},{"op","engineering-edit-inspect"},{"process_id",Process.GetCurrentProcess().Id},{"creation_filetime",Process.GetCurrentProcess().StartTime.ToFileTimeUtc()},{"native_thread_id",NativeMemory.GetCurrentThreadId()},{"actual_project",NativeEngineeringProjectScope.ExpectedProjectPath},{"editor_image_sha256",engine.ImageSha256},{"native_summary",firstSummary},{"native_summary_utf8_sha256",NativeUsableEditPermit.Digest(firstSummary)},{"compiled_kinds",Kinds()},{"features",Features},{"project_sha256",firstSummary["disk_sha256"]},{"root",firstSummary["root"]},{"action_preimages",preimages},{"write_attempted",false},{"captured_inside_direct_execution",true},{"complete_project_summary",false}};
   result["phase"]=phase;result["write_attempted"]=NativeOperationTrace.MutationAttempted;result["native_result_may_be_partial"]=!Object.Equals(result["ok"],true)&&NativeOperationTrace.MutationAttempted;result["binary_validation_reuse"]=NativeEngineeringFileHashes.Status();return result;
  }
 }
}
