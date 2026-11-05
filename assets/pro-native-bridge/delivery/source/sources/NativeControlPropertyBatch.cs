// One page, many logical controls, one original history capture/refresh/save.
using System;using System.Collections;using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativeControlPropertyEditing {
  internal const string BatchKind="control-properties-batch";

  // Opt-in coupling is an explicit expected native state, never a general
  // allowance for other properties to change. Read reports the actual state;
  // Prepare requires that state to equal the permit-bound Boolean.
  static void PairedExactCode(Api api,int rva,string hex){
   byte[] expected=new byte[hex.Length/2];for(int i=0;i<expected.Length;i++)expected[i]=Convert.ToByte(hex.Substring(2*i,2),16);
   NativeMemory.Require(BitConverter.ToString(expected)==BitConverter.ToString(NativeMemory.Bytes(api.Engine.Address(rva),expected.Length)),"Original paired Button visual setter/condition code differs.");
  }
  static Dictionary<string,object> PairedBasicInfo(Api api,Selection s){
   NativeMemory.Require(Convert.ToString(Map(s.Snapshot["control"])["rtti"])==".?AVCDrawButton@@"&&NativeMemory.I32(s.Full,0xC)==0x5027,"Paired basic visuals only apply to the actual CDrawButton class.");
   PairedExactCode(api,0x3797A0,"558bec51894dfc8b45fc837804007505e9e00400008b4dfc837908010f856c0200008b55fc8b420405a8010000506a2d8b4d0851e8cd2dccff83c40c0fb6d085d2742f8b45fc8b4804e8fc60cdff0fb6c885c9741d8b55fc8b420405a8010000508b4dfc8b490481c1a8020000e893b7caff8b55fc8b42040500010000506a048b4d0851e803ecc8ff83c40c0fb6d085d2742a8b45fc8b4804e8ac60cdff0fb6c885c974188b55fc8b42048b4dfc8b51048b800001000089827c0200008b4dfc8b510481c2e8000000526a0d8b450850e87ab9c9ff83c40c0fb6c885c974308b55fc8b4a04e86060cdff0fb6c085c0741e8b4dfc8b510481c2e8000000528b45fc8b480481c1b0020000e8d867c9ff8b4dfc8b510481c26c020000528b45fc8b480481c164020000516a038b550852e81f58ccff83c4100fb6c085c074428b4dfc8b4904e80160cdff0fb6d085d274308b45fc8b48048b55fc8b42048b89640200008988800200008b55fc8b42048b4dfc8b51048b806c0200008982880200008b4dfc8b510481c270020000528b45fc8b480481c168020000516a028b550852e8ae57ccff83c4100fb6c085c074428b4dfc8b4904e8905fcdff0fb6d085d274308b45fc8b48048b55fc8b42048b89680200008988840200008b55fc8b42048b4dfc8b51048b807002000089828c0200008b4dfc8b510481c2b0010000526a158b450850e8ee30ccff83c40c0fb6c885c9742a8b55fc8b4a04e82c5fcdff0fb6c085c074188b4dfc8b51048b45fc8b48048b92b00100008991900200008b45fc8b480481c1b4010000516a168b550852e8a230ccff83c40c0fb6c085c0742a8b4dfc8b4904e8e05ecdff0fb6d085d274188b45fc8b48048b55fc8b42048b89b4010000898894020000e9670200008b55fc8b420405a8020000506a2d8b4d0851e8612bccff83c40c0fb6d085d2742f8b45fc8b4804e8905ecdff0fb6c885c9741d8b55fc8b420405a8020000508b4dfc8b490481c1a8010000e827b5caff8b55fc8b4204057c020000506a048b4d0851e897e9c8ff83c40c0fb6d085d2742a8b45fc8b4804e8405ecdff0fb6c885c974188b55fc8b42048b4dfc8b51048b807c0200008982000100008b4dfc8b510481c2b0020000526a0d8b450850e80eb7c9ff83c40c0fb6c885c974308b55fc8b4a04e8f45dcdff0fb6c085c0741e8b4dfc8b510481c2b0020000528b45fc8b480481c1e8000000e86c65c9ff8b4dfc8b510481c288020000528b45fc8b480481c180020000516a038b550852e8b355ccff83c4100fb6c085c074428b4dfc8b4904e8955dcdff0fb6d085d274308b45fc8b48048b55fc8b42048b89800200008988640200008b55fc8b42048b4dfc8b51048b808802000089826c0200008b4dfc8b510481c28c020000528b45fc8b480481c184020000516a028b550852e84255ccff83c4100fb6c085c074428b4dfc8b4904e8245dcdff0fb6d085d274308b45fc8b48048b55fc8b42048b89840200008988680200008b55fc8b42048b4dfc8b51048b808c0200008982700200008b4dfc8b510481c290020000526a158b450850e8822eccff83c40c0fb6c885c9742a8b55fc8b4a04e8c05ccdff0fb6c085c074188b4dfc8b51048b45fc8b48048b92900200008991b00100008b45fc8b480481c194020000516a168b550852e8362eccff83c40c0fb6c085c0742a8b4dfc8b4904e8745ccdff0fb6d085d274188b45fc8b48048b55fc8b42048b89940200008988b40100008be55dc20400");
   PairedExactCode(api,0x371140,"558bec83ec08894df86a018b4df881c194030000e8a325c9ff8338017509c745fc01000000eb07c745fc000000008a45fc8be55dc3");
   PairedExactCode(api,0x381EC0,"558bec51894dfc8b4508508b4dfce8acb7c8ff8be55dc20400");
   PairedExactCode(api,0x3824C0,"558bec51894dfc837d08007c198b45fc8b4d083b48087d0e8b55fc8b42048b4d088d0488eb05e847c97a008be55dc20400");
   Dictionary<string,object> lift=null,press=null;
   foreach(var row in s.Values)if(Convert.ToString(row["native_owner"])==NativeMemory.Hex(s.Object)&&Convert.ToInt32(row["native_type_tag"])==9){
    string key=Convert.ToString(row["native_key"]);if((key!="抬起状态"&&key!="按下状态")||Convert.ToInt32(row["native_key_occurrence"])!=0)continue;
    NativeMemory.Require(Convert.ToString(row["component_rtti"])==".?AVDrawButtonBasicPropertyProxy@@"&&Convert.ToString(row["component_property_interface"])=="ObjectTree::IPropertyLinker","Paired state is not the original BasicProxy; OperationProxy is excluded.");
    if(key=="抬起状态"){NativeMemory.Require(lift==null,"Lift BasicProxy repeats.");lift=row;}else{NativeMemory.Require(press==null,"Press BasicProxy repeats.");press=row;}
   }
   NativeMemory.Require(lift!=null&&press!=null,"Original lift/press BasicProxy pair is absent.");
   IntPtr a=new IntPtr(NativeEngine.Number(lift["component_iobject"])),b=new IntPtr(NativeEngine.Number(press["component_iobject"]));
   NativeMemory.Require(a!=b&&(s.Selected==a||s.Selected==b),"Selected property target is not one of the two BasicProxy owners.");
   foreach(IntPtr x in new[]{a,b}){
    var d=NativePropertyTarget.Describe(api.Engine,x);
    NativeMemory.Require(Convert.ToString(d["rtti"])==".?AVDrawButtonBasicPropertyProxy@@"&&Convert.ToInt32(d["complete_offset"])==0&&NativeMemory.Ptr(x,0)==api.Engine.Address(0xD5E810)&&NativeMemory.Ptr(x,4)==s.Full,"BasicProxy original table/owner differs.");
    IntPtr vt=NativeMemory.Ptr(x,0);NativeMemory.Require(NativeMemory.Ptr(vt,20)==api.Engine.Address(0x40C69)&&NativeMemory.Ptr(vt,24)==api.Engine.Address(0x486E9),"BasicProxy original setter/getter entries differ.");
   }
   NativeMemory.Require(NativeMemory.I32(a,8)==0&&NativeMemory.I32(b,8)==1,"BasicProxy lifted/pressed state selectors differ.");
   IntPtr array=NativeMemory.Add(s.Full,0x394),data=NativeMemory.Ptr(array,4);int count=NativeMemory.I32(array,8);
   NativeMemory.Require(count>=2&&data!=IntPtr.Zero,"Original Button shared-style condition array is invalid.");NativeMemory.Readable(data,8);int raw=NativeMemory.I32(data,4);
   NativeMemory.Require(NativeMemory.Ptr(array,4)==data&&NativeMemory.I32(array,8)==count,"Button condition array changed during read.");
   return new Dictionary<string,object>{{"native_shared_visual_condition",raw==1},{"condition_element1_raw_int32",raw},{"condition_array_count",count},{"lift_owner",NativeMemory.Hex(a)},{"press_owner",NativeMemory.Hex(b)},{"selected_owner",NativeMemory.Hex(s.Selected)},{"condition_rule","Original771140: Button+394.GetAt(1)==1"},{"allowed_visual_keys",new[]{"字体","字符颜色","填充颜色","边线颜色","显示文本"}}};
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
   internal readonly List<Selection> Controls=new List<Selection>();
   internal readonly List<Dictionary<string,object>> Requests=new List<Dictionary<string,object>>();
   internal Dictionary<string,object> Snapshot;internal IntPtr Page,Doc,View;
  }
  static BatchSelection CaptureBatch(Api api,Dictionary<string,object> action){
   var parent=Map(action["target"]);IntPtr page=api.Common.Page(parent);
   var pageState=api.Common.PageSnapshot(page);var batch=new BatchSelection{Page=page,
    Doc=api.Common.Document(page,Convert.ToInt32(parent["page_id"]))};
   var fullObjects=new HashSet<uint>();var rows=new List<object>();
   foreach(object raw in(IEnumerable)Map(action["after"])["controls"]){
    var item=Map(raw);var target=new Dictionary<string,object>(parent);
    foreach(var pair in Map(item["target"])){
     NativeMemory.Require(pair.Key=="control_name"||pair.Key=="rtti"||pair.Key=="control_path"||pair.Key=="component_path","Property batch control target contains unsupported fields.");target.Add(pair.Key,pair.Value);
    }
    var request=new Dictionary<string,object>{{"target",target}};
    Selection control=Capture(api,request,pageState);
    NativeMemory.Require(control.Page==batch.Page&&control.Doc==batch.Doc&&fullObjects.Add(NativeMemory.U(control.Full)),"Each property batch entry must address a distinct native control on the same page.");
    if(batch.Controls.Count==0)batch.View=control.View;
    NativeMemory.Require(control.View==batch.View,"Batch targets disagree on the page's current view.");
    batch.Controls.Add(control);batch.Requests.Add(item);
    var capturedRow=new Dictionary<string,object>{{"target",item["target"]},{"control",control.Snapshot["control"]},{"selected_owner",control.Snapshot["selected_owner"]},{"properties",control.Values}};object pairedFlag;if(item.TryGetValue("expect_paired_basic_button_visuals",out pairedFlag)){NativeMemory.Require(pairedFlag is bool,"expect_paired_basic_button_visuals must be Boolean.");capturedRow["paired_basic_button_visuals"]=PairedBasicInfo(api,control);}rows.Add(capturedRow);
   }
   NativeMemory.Require(batch.Controls.Count>0,"Property batch needs at least one control.");
   batch.Snapshot=new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"kind",BatchKind},{"page",pageState},{"controls",rows},
    {"root_modified",NativeMemory.I32(api.Common.Shared.RootDoc(),0x48)},{"compile_valid",NativeMemory.I32(api.Common.Shared.RootDoc(),0x114)},{"full_serialization_preimage",false}};
   return batch;
  }
  internal static Dictionary<string,object> ReadBatch(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return CaptureBatch(new Api(e,c,project),action).Snapshot;}
  internal static PreparedBatch PrepareBatch(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new PreparedBatch(new Api(e,c,project),action);}
  sealed class BatchItem:IDisposable {
   internal Selection Before;internal List<Dictionary<string,object>> Expected;internal NativeTypedPropertyDispatcher Dispatcher;internal Setter Set;
   public void Dispose(){if(Dispatcher!=null){Dispatcher.Dispose();Dispatcher=null;}}
  }
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
    NativeMemory.Require(NativePageControlPreparation.Json(match["value"])!=NativePageControlPreparation.Json(value),"Remove unchanged batch properties.");
    match["value"]=value;writes.Add(new Dictionary<string,object>{{"native_key",key},{"native_type_tag",tag},{"value",row["value"]}});
   }
   NativeMemory.Require(writes.Count>0,"Batch control has no changed properties.");return writes;
  }
  internal sealed class PreparedBatch:INativePreparedPageControlEdit {
   readonly Api api;readonly Dictionary<string,object> action;readonly BatchSelection before;readonly List<BatchItem> items=new List<BatchItem>();
   readonly NativeControlHistoryContext history;readonly BeforeModify notify;readonly VI rootDirty,docDirty,invalidate;readonly V0 update;readonly SaveData save;bool disposed,applied;
   internal PreparedBatch(Api a,Dictionary<string,object> request){
    api=a;action=request;NativeMemory.Require(Convert.ToString(request["kind"])==BatchKind&&Convert.ToString(request["abi_profile_sha256"])==AbiProfileSha,"Property batch kind/ABI differs.");
    before=CaptureBatch(api,action);NativePageControlPreparation.Before(action,before.Snapshot);if(before.View!=IntPtr.Zero)history=new NativeControlHistoryContext(api.Engine,before.Doc,api.Common.Shared.RootDoc());
    notify=api.Bind<BeforeModify>("DocBeforeModify");rootDirty=api.Common.Shared.Bind<VI>("RootSetModified");docDirty=api.Common.Bind<VI>("standard","DocSetModified");invalidate=api.Bind<VI>("InvalidateView");update=api.Bind<V0>("UpdateView");save=api.Common.Bind<SaveData>("standard","WindowSaveData");
    if(before.View!=IntPtr.Zero)api.Common.Slot(before.Doc,96,0x3CBE6);api.Common.Slot(api.Context.WindowService,12,0x21733);
    try{for(int i=0;i<before.Controls.Count;i++){
     var item=new BatchItem{Before=before.Controls[i],Expected=CloneRows(before.Controls[i].Values)};items.Add(item);
     item.Set=api.Engine.Bind<Setter>(api.Engine.Virtual(item.Before.Selected,5));
     var writes=BatchWrites(item.Before,before.Requests[i],item.Expected);PairedBasicExpected(api,item.Before,before.Requests[i],item.Expected);item.Dispatcher=new NativeTypedPropertyDispatcher(api.Common.Shared,writes);
    }}catch{Dispose();throw;}
   }
   internal void ValidateBefore(){if(history!=null)history.ValidateBefore();NativeMemory.Require(!disposed&&!applied,"Property batch is disposed/already entered.");NativePageControlPreparation.Same(before.Snapshot,CaptureBatch(api,action).Snapshot,"Property batch preimage changed after preparation.");}
   void VerifyAfter(BatchSelection current){
    NativeMemory.Require(current.Page==before.Page&&current.Doc==before.Doc&&current.View==before.View&&current.Controls.Count==items.Count,"Property batch changed page ownership/view/selection count.");
    for(int i=0;i<items.Count;i++){
     object declared;if(before.Requests[i].TryGetValue("expect_paired_basic_button_visuals",out declared)){var oldRow=Map(((IList)before.Snapshot["controls"])[i]);var newRow=Map(((IList)current.Snapshot["controls"])[i]);NativePageControlPreparation.Same(oldRow["paired_basic_button_visuals"],newRow["paired_basic_button_visuals"],"Original paired Button condition or BasicProxy owners changed.");}
     Selection old=items[i].Before,now=current.Controls[i];NativeMemory.Require(now.Full==old.Full&&now.Selected==old.Selected&&now.Object==old.Object,"Property batch changed a selected object's native identity.");
     NativePageControlPreparation.Same(items[i].Expected,now.Values,"Property batch target value or untouched component postimage differs.");
     NativePageControlPreparation.Same(old.Snapshot["control"],now.Snapshot["control"],"Property batch changed a control name/class/owner.");
    }
    var protectedBefore=history==null?before.Snapshot:Map(history.ExpectedSnapshot(before.Snapshot));var left=Map(protectedBefore["page"]);var right=Map(current.Snapshot["page"]);
    foreach(string key in new[]{"attributes","pages","top_level_controls"})NativePageControlPreparation.Same(left[key],right[key],"Property batch changed page metadata, control geometry, ownership or raw state: "+key);
   }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){
    NativeMemory.Require(!disposed&&!applied,"Property batch is disposed/already entered.");lease.RequireCurrent();if(history!=null)history.ValidateBefore();
    var current=CaptureBatch(api,action);var left=new Dictionary<string,object>(before.Snapshot);var right=new Dictionary<string,object>(current.Snapshot);
    foreach(string key in new[]{"root_modified","compile_valid"}){left.Remove(key);right.Remove(key);}
    NativePageControlPreparation.Same(left,right,"Property batch target preimage changed before Apply.");lease.BeginApply(action);applied=true;
    NativeOperationTrace.BeforeMutation("batch-properties-original-page-before-modify");if(before.View!=IntPtr.Zero){notify(before.Doc,before.View,1,1);history.OriginalBeforeModifyReturned();}else docDirty(before.Doc,1);
    rootDirty(api.Common.Shared.RootDoc(),1);Marshal.WriteInt32(api.Common.Shared.RootDoc(),0x114,0);
    for(int i=0;i<items.Count;i++){
     BatchItem item=items[i];NativeOperationTrace.BeforeMutation("batch-properties-original-setter-"+i);
     item.Dispatcher.Invoke(delegate(IntPtr sink){item.Set(item.Before.Selected,sink);});
    }
    if(before.View!=IntPtr.Zero){NativeOperationTrace.BeforeMutation("batch-properties-native-invalidate");invalidate(before.View,1);NativeOperationTrace.BeforeMutation("batch-properties-native-update");update(before.View);}
    current=CaptureBatch(api,action);VerifyAfter(current);NativeMemory.Require(NativeMemory.I32(before.Doc,0x48)==1&&NativeMemory.I32(api.Common.Shared.RootDoc(),0x48)==1&&NativeMemory.I32(api.Common.Shared.RootDoc(),0x114)==0,"Batch history/dirty/compile contract differs.");lease.CompleteApply(action);
    return new Dictionary<string,object>{{"ok",true},{"kind",BatchKind},{"control_count",items.Count},{"after",current.Snapshot},{"original_history_captures",before.View==IntPtr.Zero?0:1},{"original_history_store_projection",history==null?null:(object)history.Report()},{"native_refreshes",before.View==IntPtr.Zero?0:1},{"automatic_history_replay",false},{"full_persistence_acceptance_pending",true}};
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){
    NativeMemory.Require(applied&&!disposed,"Property batch Apply must complete before Flush.");lease.BeginFlush(action);api.Common.Current();VerifyAfter(CaptureBatch(api,action));
    int dirty=NativeMemory.I32(before.Doc,0x48);NativeMemory.Require(dirty==0||dirty==1,"Property batch page dirty flag differs.");
    if(dirty==1){NativeOperationTrace.BeforeMutation("batch-properties-page-save-data");NativeMemory.Require(save(api.Context.WindowService,before.Page)&&NativeMemory.I32(before.Doc,0x48)==0,"Property batch page SaveData failed its clean contract.");}
    VerifyAfter(CaptureBatch(api,action));lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"root_save_called",false},{"control_count",items.Count}};
   }
   public void Dispose(){if(disposed)return;disposed=true;for(int i=items.Count-1;i>=0;i--)items[i].Dispose();items.Clear();}
  }
 }
}
