// One page, many logical controls, one original history capture/refresh/save.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;
using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativeControlPropertyEditing {
  internal const string BatchKind="control-properties-batch";

  // Opt-in coupling is an explicit expected native state, never a general
  // allowance for other properties to change. Read reports the actual state;
  // Prepare requires that state to equal the permit-bound Boolean.
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool ButtonSharedVisuals(IntPtr button);
  static Dictionary<string,object> PairedBasicInfo(Api api,Selection s){
   NativeMemory.Require(Convert.ToString(Map(s.Snapshot["control"])["rtti"])==".?AVCDrawButton@@"&&NativeMemory.I32(s.Full,NativeLayout.Offset("control.type_id"))==0x5027,"Paired basic visuals only apply to the actual CDrawButton class.");
   Dictionary<string,object> lift=null,press=null;
   foreach(var row in s.Values)if(Convert.ToString(row["native_owner"])==NativeMemory.Hex(s.Object)&&Convert.ToInt32(row["native_type_tag"])==9){
    string key=Convert.ToString(row["native_key"]);if((key!="抬起状态"&&key!="按下状态")||Convert.ToInt32(row["native_key_occurrence"])!=0)continue;
    NativeMemory.Require(Convert.ToString(row["component_rtti"])==".?AVDrawButtonBasicPropertyProxy@@"&&Convert.ToString(row["component_property_interface"])=="ObjectTree::IPropertyLinker","Paired state is not the original BasicProxy; OperationProxy is excluded.");
    if(key=="抬起状态"){NativeMemory.Require(lift==null,"Lift BasicProxy repeats.");lift=row;}else{NativeMemory.Require(press==null,"Press BasicProxy repeats.");press=row;}
   }
   NativeMemory.Require(lift!=null&&press!=null,"Original lift/press BasicProxy pair is absent.");
   IntPtr a=new IntPtr(NativeEngine.Number(lift["component_iobject"])),b=new IntPtr(NativeEngine.Number(press["component_iobject"]));
   NativeMemory.Require(a!=b&&(s.Selected==a||s.Selected==b),"Selected property target is not one of the two BasicProxy owners.");
   foreach(IntPtr x in new[]{a,b})NativeMemory.Require(Convert.ToString(NativePropertyTarget.Describe(api.Engine,x)["rtti"])==".?AVDrawButtonBasicPropertyProxy@@","Paired state must retain its original BasicProxy interface.");
   // Query the original condition routine instead of reproducing its array
   // implementation or admitting an entire setter body as a prerequisite.
   bool shared=api.Engine.Bind<ButtonSharedVisuals>(api.Engine.Address(0x371140))(s.Full);
   return new Dictionary<string,object>{{"native_shared_visual_condition",shared},{"lift_owner",NativeMemory.Hex(a)},{"press_owner",NativeMemory.Hex(b)},{"selected_owner",NativeMemory.Hex(s.Selected)},{"condition_rule","original Button shared-visual getter"},{"allowed_visual_keys",new[]{"字体","字符颜色","填充颜色","边线颜色","显示文本"}}};
  }

  static void PairedBasicExpected(Api api,Selection s,Dictionary<string,object> requested,List<Dictionary<string,object>> expected){
   object declared;if(!requested.TryGetValue("expect_paired_basic_button_visuals",out declared))return;
   NativeMemory.Require(declared is bool,"expect_paired_basic_button_visuals must be an explicit Boolean.");
   var info=PairedBasicInfo(api,s);bool shared=(bool)info["native_shared_visual_condition"];
   NativeMemory.Require((bool)declared==shared,"Original Button shared-style condition differs from the permit-bound expectation.");
   string selected=NativeMemory.Hex(s.Selected),paired=Convert.ToString(info[Convert.ToString(info["lift_owner"])==selected?"press_owner":"lift_owner"]);
   foreach(object raw in(IEnumerable)requested["properties"]){
    var write=Map(raw);string key=Convert.ToString(write["native_key"]);int tag=Convert.ToInt32(write["native_type_tag"]);
    NativeMemory.Require((key=="字体"&&tag==1)||((key=="字符颜色"||key=="填充颜色"||key=="边线颜色")&&tag==0)||(key=="显示文本"&&tag==8&&shared),"Explicit paired BasicProxy contract permits only the four proven visual fields or shared display text tag8.");
    Dictionary<string,object> from=null,to=null;
    foreach(var row in expected)if(Convert.ToString(row["native_key"])==key){string owner=Convert.ToString(row["native_owner"]);if(owner==selected){NativeMemory.Require(from==null,"Selected visual key repeats.");from=row;}if(owner==paired){NativeMemory.Require(to==null,"Paired visual key repeats.");to=row;}}
    NativeMemory.Require(from!=null&&to!=null&&Convert.ToInt32(from["native_type_tag"])==tag&&Convert.ToInt32(to["native_type_tag"])==tag,"Both actual BasicProxy owners must declare the matching key/tag.");
    if(tag==1){var left=new HashSet<int>();var right=new HashSet<int>();foreach(object r in(IEnumerable)Map(from["value"])["rows"])NativeMemory.Require(left.Add(Convert.ToInt32(Map(r)["language_id"])),"Requested font language repeats.");foreach(object r in(IEnumerable)Map(to["value"])["rows"])NativeMemory.Require(right.Add(Convert.ToInt32(Map(r)["language_id"])),"Paired font language repeats.");NativeMemory.Require(left.SetEquals(right),"Paired font edit must retain the same actual language set in both states.");}
    if(shared)to["value"]=CloneRows(new List<Dictionary<string,object>>{from})[0]["value"];
   }
  }

  sealed class BatchSelection {
   // Each capture resolves its own page and root list. Callers never reuse them for a later capture.
   internal readonly List<Selection> Controls=new List<Selection>();
   internal readonly List<Dictionary<string,object>> Requests=new List<Dictionary<string,object>>();
   internal readonly IntPtr Page,Doc,View;
   internal readonly List<IntPtr> TopControls;
   internal readonly Dictionary<string,object> PageState;
   internal Dictionary<string,object> Snapshot;
   HashSet<IntPtr> ownerIdentities;
   internal HashSet<IntPtr> OwnerIdentities(Api api){
    if(ownerIdentities==null)ownerIdentities=PropertyOwnerIndex(api,TopControls,Doc);
    return ownerIdentities;
   }
   internal BatchSelection(Api api,Dictionary<string,object> target){
    Page=api.Common.Page(target);
    Doc=api.Common.Document(Page,Convert.ToInt32(target["page_id"]));
    TopControls=api.Common.TopControls(Doc);
    PageState=api.Common.PageSnapshot(Page,TopControls);
    View=CaptureDrawingView(api,Doc);
    NativeMemory.Require(Convert.ToString(PageState["document"])==NativeMemory.Hex(Doc)&&Convert.ToString(PageState["view"])==NativeMemory.Hex(View),"Property batch page snapshot disagrees with the current document/view.");
   }
  }
  static BatchSelection CaptureBatch(Api api,Dictionary<string,object> action){
   var parent=Map(action["target"]);var batch=new BatchSelection(api,parent);
   var propertyOwners=new HashSet<string>(StringComparer.Ordinal);var rows=new List<object>();
   foreach(object raw in(IEnumerable)Map(action["after"])["controls"]){
    var item=Map(raw);var target=new Dictionary<string,object>(parent);
    foreach(var pair in Map(item["target"])){
     NativeMemory.Require(pair.Key=="control_name"||pair.Key=="rtti"||pair.Key=="control_path"||pair.Key=="component_path"||pair.Key=="complete"||pair.Key=="native_id","Property batch control target contains unsupported fields.");target.Add(pair.Key,pair.Value);
    }
    object properties;
    IEnumerable requested=item.TryGetValue("properties",out properties)?(IEnumerable)properties:null;
    Selection control=Capture(api,target,batch,requested,item.ContainsKey("expect_paired_basic_button_visuals"));
    NativeMemory.Require(propertyOwners.Add(NativeMemory.Hex(control.Full)+"/"+NativeMemory.Hex(control.Selected)),"Merge duplicate property-owner entries; different components of the same control are supported.");
    batch.Controls.Add(control);batch.Requests.Add(item);
    var capturedRow=new Dictionary<string,object>{{"target",item["target"]},{"control",control.Snapshot["control"]},{"selected_owner",control.Snapshot["selected_owner"]},{"properties",control.Values}};object pairedFlag;if(item.TryGetValue("expect_paired_basic_button_visuals",out pairedFlag)){NativeMemory.Require(pairedFlag is bool,"expect_paired_basic_button_visuals must be Boolean.");capturedRow["paired_basic_button_visuals"]=PairedBasicInfo(api,control);}rows.Add(capturedRow);
   }
   NativeMemory.Require(batch.Controls.Count>0,"Property batch needs at least one control.");
   batch.Snapshot=new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"kind",BatchKind},{"page",batch.PageState},{"controls",rows},
    {"root_modified",NativeMemory.I32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.modified"))},{"compile_valid",NativeMemory.I32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"))},{"full_serialization_preimage",false}};
   return batch;
  }
  internal static Dictionary<string,object> ReadBatch(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return CaptureBatch(new Api(e,c,project),action).Snapshot;}
  internal static Dictionary<string,object> ReadDirectBatch(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action,out object captured){
   var selection=CaptureBatch(new Api(e,c,project),action);captured=selection;return selection.Snapshot;
  }
  internal static PreparedBatch PrepareBatch(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action,object captured=null){
   return new PreparedBatch(new Api(e,c,project),action,captured as BatchSelection);
  }
  sealed class BatchItem:IDisposable {
   internal Selection Before;internal List<Dictionary<string,object>> Expected;internal NativeTypedPropertyDispatcher Dispatcher;internal Setter Set;
   public void Dispose(){if(Dispatcher!=null){Dispatcher.Dispose();Dispatcher=null;}}
  }
  static Tuple<IntPtr,string,string,int,int> PropertyIdentity(Selection selected,Dictionary<string,object> row){
   return Tuple.Create(selected.Full,Convert.ToString(row["native_owner"]),Convert.ToString(row["native_key"]),
    Convert.ToInt32(row["native_key_occurrence"]),Convert.ToInt32(row["native_type_tag"]));
  }
  static void ReadExpectedValues(Dictionary<Tuple<IntPtr,string,string,int,int>,object> state,Selection selected,List<Dictionary<string,object>> rows){foreach(var row in rows){if(Convert.ToInt32(row["native_type_tag"])==9)continue;object value;if(state.TryGetValue(PropertyIdentity(selected,row),out value))row["value"]=NativeDynamicCollections.CopyValue(value,false);}}
  static void StoreExpectedValues(Dictionary<Tuple<IntPtr,string,string,int,int>,object> state,Selection selected,List<Dictionary<string,object>> rows){foreach(var row in rows)if(Convert.ToInt32(row["native_type_tag"])!=9)state[PropertyIdentity(selected,row)]=NativeDynamicCollections.CopyValue(row["value"],false);}
  static List<Dictionary<string,object>> BatchWrites(Selection selection,Dictionary<string,object> requested,List<Dictionary<string,object>> expected){
   var writes=new List<Dictionary<string,object>>();var seen=new HashSet<string>(StringComparer.Ordinal);
   foreach(object raw in(IEnumerable)requested["properties"]){
    var row=Map(raw);string key=NativePageControlPreparation.Text(row,"native_key");int tag=Convert.ToInt32(row["native_type_tag"]);
    NativeMemory.Require(seen.Add(key)&&tag!=9,"Batch property key duplicates or needs an explicit component target.");
    Dictionary<string,object> match=null;foreach(var original in expected)if(Convert.ToString(original["native_owner"])==NativeMemory.Hex(selection.Selected)&&Convert.ToString(original["native_key"])==key){NativeMemory.Require(match==null,"Batch native owner/key is ambiguous.");match=original;}
    NativeMemory.Require(match!=null&&Convert.ToInt32(match["native_type_tag"])==tag,"Batch requested property key/tag is not declared by its selected native owner.");
    object value=row["value"];
    if(tag==1){
     var font=Map(value);var normalized=new Dictionary<string,object>(font);var languages=new HashSet<int>();var changed=new HashSet<int>();var rows=new List<object>();
     foreach(object old in(IEnumerable)Map(match["value"])["rows"])NativeMemory.Require(languages.Add(Convert.ToInt32(Map(old)["language_id"])),"Original batch font language repeats.");
     foreach(object next in(IEnumerable)font["rows"]){int id=Convert.ToInt32(Map(next)["language_id"]);NativeMemory.Require(languages.Contains(id)&&changed.Add(id),"Batch font edit must retain the actual original language IDs exactly once.");rows.Add(next);}
     NativeMemory.Require(changed.SetEquals(languages),"Batch font edit removes a language row.");normalized["row_count"]=rows.Count;value=normalized;
    }
    if(NativePageControlPreparation.Json(match["value"])==NativePageControlPreparation.Json(value))continue;
    match["value"]=value;writes.Add(new Dictionary<string,object>{{"native_key",key},{"native_type_tag",tag},{"value",row["value"]}});
   }
   return writes;
  }
  internal sealed class PreparedBatch:INativePreparedPageControlEdit {
   readonly Api api;readonly Dictionary<string,object> action;readonly BatchSelection before;readonly List<BatchItem> items=new List<BatchItem>();
   readonly bool direct;readonly BeforeModify notify;readonly VI rootDirty,docDirty,invalidate;readonly V0 update;bool disposed,applied;int setterCount,originalHistoryCalls;Dictionary<string,object> preservationPage;readonly Dictionary<string,object> timings=new Dictionary<string,object>();
   internal bool HasChanges{get{return setterCount>0;}}
   internal PreparedBatch(Api a,Dictionary<string,object> request,object baseline){
    var captured=baseline as BatchSelection;
    api=a;action=request;NativeMemory.Require(Convert.ToString(request["kind"])==BatchKind&&Convert.ToString(request["abi_profile_sha256"])==AbiProfileSha,"Property batch kind/ABI differs.");
    var clock=Stopwatch.StartNew();direct=captured!=null;before=captured??CaptureBatch(api,action);NativePageControlPreparation.Before(action,before.Snapshot);preservationPage=before.PageState;timings[direct?"reuse_direct_baseline":"baseline_capture"]=clock.Elapsed.TotalMilliseconds;clock.Restart();
    var finalValues=new Dictionary<Tuple<IntPtr,string,string,int,int>,object>();foreach(var selected in before.Controls)StoreExpectedValues(finalValues,selected,selected.Values);
    HashSet<string> namedBitmaps=null;
    try{for(int i=0;i<before.Controls.Count;i++){
     var item=new BatchItem{Before=before.Controls[i],Expected=CloneRows(before.Controls[i].Values)};items.Add(item);
     ReadExpectedValues(finalValues,item.Before,item.Expected);var writes=BatchWrites(item.Before,before.Requests[i],item.Expected);
     namedBitmaps=CollectNamedBitmapBackgrounds(api,item.Before,writes,namedBitmaps);
     var pairedRequest=new Dictionary<string,object>(before.Requests[i]);pairedRequest["properties"]=writes;PairedBasicExpected(api,item.Before,pairedRequest,item.Expected);StoreExpectedValues(finalValues,item.Before,item.Expected);if(writes.Count>0){item.Set=NativePropertyTarget.Bind<Setter>(api.Engine,item.Before.Selected,true);item.Dispatcher=new NativeTypedPropertyDispatcher(api.Common.Shared,writes);setterCount++;}
    }
     NativePictureResources.RequireNamedPictures(api.Engine,api.Context,api.Project,namedBitmaps);
     foreach(var item in items)ReadExpectedValues(finalValues,item.Before,item.Expected);
    }catch{Dispose();throw;}
    timings["prepare_setters"]=clock.Elapsed.TotalMilliseconds;if(setterCount>0){rootDirty=api.Common.Shared.Bind<VI>("RootSetModified");docDirty=api.Common.Bind<VI>("standard","DocSetModified");if(before.View!=IntPtr.Zero){notify=api.Bind<BeforeModify>("DocBeforeModify");invalidate=api.Bind<VI>("InvalidateView");update=api.Bind<V0>("UpdateView");}}
   }
   internal void ValidateBefore(){NativeMemory.Require(!disposed&&!applied,"Property batch is disposed/already entered.");var clock=Stopwatch.StartNew();NativePageControlPreparation.Same(before.Snapshot,CaptureBatch(api,action).Snapshot,"Property batch preimage changed after preparation.");timings["prewrite_read"]=clock.Elapsed.TotalMilliseconds;}
   void VerifyAfter(BatchSelection current){
    NativeMemory.Require(current.Page==before.Page&&current.Doc==before.Doc&&current.View==before.View&&current.Controls.Count==items.Count,"Property batch changed page ownership/view/selection count.");
    for(int i=0;i<items.Count;i++){
     object declared;if(before.Requests[i].TryGetValue("expect_paired_basic_button_visuals",out declared)){var oldRow=Map(((IList)before.Snapshot["controls"])[i]);var newRow=Map(((IList)current.Snapshot["controls"])[i]);NativePageControlPreparation.Same(oldRow["paired_basic_button_visuals"],newRow["paired_basic_button_visuals"],"Original paired Button condition or BasicProxy owners changed.");}
     Selection old=items[i].Before,now=current.Controls[i];NativeMemory.Require(now.Full==old.Full&&now.Selected==old.Selected&&now.Object==old.Object,"Property batch changed a selected object's native identity.");
     NativePageControlPreparation.Same(items[i].Expected,now.Values,"Property batch target value or untouched component postimage differs.");
     NativePageControlPreparation.Same(old.Snapshot["control"],now.Snapshot["control"],"Property batch changed a control name/class/owner.");
    }
    var left=preservationPage;var right=Map(current.Snapshot["page"]);
    foreach(string key in new[]{"attributes","pages","top_level_controls"})NativePageControlPreparation.Same(left[key],right[key],"Property batch changed page metadata, control geometry, ownership or raw state: "+key);
   }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){
    NativeMemory.Require(!disposed&&!applied,"Property batch is disposed/already entered.");lease.RequireCurrent();
    var clock=Stopwatch.StartNew();BatchSelection current=before;
    if(!direct){
     current=CaptureBatch(api,action);var left=new Dictionary<string,object>(before.Snapshot);var right=new Dictionary<string,object>(current.Snapshot);
     foreach(string key in new[]{"root_modified","compile_valid"}){left.Remove(key);right.Remove(key);}
     NativePageControlPreparation.Same(left,right,"Property batch target preimage changed before Apply.");
     timings["legacy_preapply_read"]=clock.Elapsed.TotalMilliseconds;clock.Restart();
    }
    lease.BeginApply(action);applied=true;
    if(setterCount==0){lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",BatchKind},{"no_op",true},{"control_count",items.Count},{"after",current.Snapshot},{"native_setter_calls",0},{"original_history_captures",0},{"native_refreshes",0},{"timings_ms",timings}};}
    NativeOperationTrace.BeforeMutation("batch-properties-original-page-before-modify");if(before.View!=IntPtr.Zero){notify(before.Doc,before.View,1,1);originalHistoryCalls++;var notified=CaptureBatch(api,action);for(int i=0;i<before.Controls.Count;i++)NativePageControlPreparation.Same(before.Controls[i].Values,notified.Controls[i].Values,"Original before-modify changed requested business properties.");NativeOriginalHistoryObservation.VerifyPage(preservationPage,notified.PageState);preservationPage=notified.PageState;}else docDirty(before.Doc,1);
    rootDirty(api.Common.Shared.RootDoc(),1);Marshal.WriteInt32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"),0);
    timings["history_notification_and_read"]=clock.Elapsed.TotalMilliseconds;clock.Restart();for(int i=0;i<items.Count;i++){
     BatchItem item=items[i];if(item.Dispatcher==null)continue;NativeOperationTrace.BeforeMutation("batch-properties-original-setter-"+i);
     item.Dispatcher.Invoke(delegate(IntPtr sink){item.Set(item.Before.Selected,sink);});
    }
    timings["native_apply"]=clock.Elapsed.TotalMilliseconds;clock.Restart();if(before.View!=IntPtr.Zero){NativeOperationTrace.BeforeMutation("batch-properties-native-invalidate");invalidate(before.View,1);NativeOperationTrace.BeforeMutation("batch-properties-native-update");update(before.View);}
    timings["refresh"]=clock.Elapsed.TotalMilliseconds;clock.Restart();current=CaptureBatch(api,action);VerifyAfter(current);timings["final_readback"]=clock.Elapsed.TotalMilliseconds;NativeMemory.Require(NativeMemory.I32(before.Doc,NativeLayout.Offset("document.modified"))==1&&NativeMemory.I32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.modified"))==1&&NativeMemory.I32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"))==0,"Batch history/dirty/compile contract differs.");lease.CompleteApply(action);
    return new Dictionary<string,object>{{"ok",true},{"kind",BatchKind},{"control_count",items.Count},{"native_setter_calls",setterCount},{"after",current.Snapshot},{"original_history_captures",originalHistoryCalls},{"history_baseline","observed after original notification, before setters"},{"timings_ms",timings},{"native_refreshes",before.View==IntPtr.Zero?0:1},{"automatic_history_replay",false},{"full_persistence_acceptance_pending",true}};
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){
    NativeMemory.Require(applied&&!disposed,"Property batch Apply must complete before Flush.");lease.BeginFlush(action);api.Common.Current();if(!direct&&HasChanges)VerifyAfter(CaptureBatch(api,action));
    int dirty=NativeMemory.I32(before.Doc,NativeLayout.Offset("document.modified"));NativeMemory.Require(dirty==0||dirty==1,"Property batch page dirty flag differs.");
    var clock=Stopwatch.StartNew();if(dirty==1&&setterCount>0){var save=api.Common.Bind<SaveData>("standard","WindowSaveData");NativeOperationTrace.BeforeMutation("batch-properties-page-save-data");NativeMemory.Require(save(api.Context.WindowService,before.Page)&&NativeMemory.I32(before.Doc,NativeLayout.Offset("document.modified"))==0,"Property batch page SaveData failed its clean contract.");}
    timings["save"]=clock.Elapsed.TotalMilliseconds;if(dirty==1&&HasChanges){clock.Restart();VerifyAfter(CaptureBatch(api,action));timings["save_readback"]=clock.Elapsed.TotalMilliseconds;}lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1&&setterCount>0},{"timings_ms",timings},{"root_save_called",false},{"control_count",items.Count}};
   }
   public void Dispose(){if(disposed)return;disposed=true;for(int i=items.Count-1;i>=0;i--)items[i].Dispose();items.Clear();}
  }
 }
}
