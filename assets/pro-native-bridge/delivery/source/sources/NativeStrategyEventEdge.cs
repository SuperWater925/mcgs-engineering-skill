// Existing Event condition selection, with independent canonical and DAO cache projections.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Trigger=McgsInternalBridge.NativeStrategyTriggerContextEditing;
using Strategies=McgsInternalBridge.NativeStrategyWorkingModelEditing;

namespace McgsInternalBridge {
 internal static class NativeStrategyEventEdge {
  internal const string Kind="strategy-event-edge";
  const string ProfilePath="coverage-20261101/usable-edit-0001/strategy-prep/trigger-context-prep/strategy-event-trigger-edge-abi-profile.json";
  const string ProfileSha="eef2480e0f9c1902078331cd0e90c844837a6eb056a4aa3fe68e4d1ff38e3121";
  const int ListSelectionMask=3;
  // Original Event Property selector order.
  static readonly string[] Modes={"rising","falling","rising_then_falling","falling_then_rising","change"};

  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
  delegate int ListFindId(IntPtr owner,int id);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
  delegate int ListItemState(IntPtr owner,int row,int mask);
  [DllImport("user32.dll",ExactSpelling=true)]
  static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
  [DllImport("user32.dll",ExactSpelling=true)]
  static extern bool IsWindowVisible(IntPtr window);

  static Dictionary<string,object> Map(object value){return NativePageControlPreparation.Map(value);}
  static int Number(Dictionary<string,object> value,string key){return NativePageControlPreparation.Number(value,key);}
  static string Text(Dictionary<string,object> value,string key){return NativePageControlPreparation.Text(value,key);}
  static void Need(bool condition,string message){NativeMemory.Require(condition,message);}
  static void Same(object expected,object current,string message){NativePageControlPreparation.Same(expected,current,message);}
  static string Hex(byte[] value){return BitConverter.ToString(value).Replace("-","").ToLowerInvariant();}

  static List<object> EventWords(Dictionary<string,object> fields) {
   var result=new List<object>();
   foreach(object value in (IEnumerable)fields["serialized_event_words_uint32"])result.Add(value);
   Need(result.Count==2,"Event trigger must have its complete two-word tail.");
   return result;
  }
  static uint EdgeMode(Dictionary<string,object> fields) {
   uint edge=Strategies.LifecycleWord(EventWords(fields)[1]);
   Need(edge<(uint)Modes.Length,"This Event uses an unrecognized native condition mode.");
   return edge;
  }
  static Dictionary<string,object> WithEdge(Dictionary<string,object> fields,uint edge) {
   var result=new Dictionary<string,object>(fields);
   var words=EventWords(fields);words[1]=edge;result["serialized_event_words_uint32"]=words;
   return result;
  }
  static Dictionary<string,object> Without(Dictionary<string,object> fields,params string[] keys) {
   var result=new Dictionary<string,object>(fields);
   foreach(string key in keys)result.Remove(key);
   return result;
  }
  static Dictionary<string,object> DbRow(List<object> rows,int recordId) {
   Dictionary<string,object> result=null;
   foreach(object value in rows){
    var row=Map(value);
    if(Number(row,"id")==recordId){Need(result==null,"Event Trigger cursor row repeats.");result=row;}
   }
   Need(result!=null,"The Event's exact existing Trigger row is absent.");
   return result;
  }

  sealed class Api {
   internal readonly Trigger.Api Context;
   internal readonly Strategies.TypedContract StrategiesModel;
   internal readonly NativeReferencedPageEditing.Api References;
   internal readonly int Id;
   internal readonly string Name;
   internal readonly NativeLazyFunctionProfile Methods;

   internal Api(NativeEngine engine,NativeContext ctxt,string project,Dictionary<string,object> action){
    Need(Text(action,"kind")==Kind,"Event edge action kind differs.");
    var target=Map(action["target"]);
    Need(target.Count==2&&target.ContainsKey("block_id")&&target.ContainsKey("block_name"),
         "Select the exact canonical Event strategy by block_id and block_name.");
    Id=Number(target,"block_id");Name=Text(target,"block_name");
    Need(Id>=3,"Event edge editing requires an existing custom strategy.");
    Context=new Trigger.Api(engine,ctxt,project);
    StrategiesModel=Strategies.PersistentContract(engine,ctxt,project);
    References=new NativeReferencedPageEditing.Api(engine,ctxt,project);
    Methods=new NativeLazyFunctionProfile(engine,ProfilePath,ProfileSha,"editor");
   }

   internal IntPtr Canonical(out IntPtr strategyIo) {
    Context.Current();
    var blocks=Context.Base.Blocks();
    Need(blocks.TryGetValue(Id,out strategyIo)&&NativeStrategyProfile.ReadName(Context.Base.Read.Existing,strategyIo)==Name,
         "Exact canonical Event strategy ID/name differs.");
    Need(!StrategiesModel.Native.Views().ContainsKey(Id),
         "Close this strategy's private working editor before editing its canonical Event edge.");
    return NativeMemory.Ptr(strategyIo,0xC);
   }

   internal Dictionary<string,object> Capture(){
    IntPtr io,context=Canonical(out io);
    var record=Strategies.FullBlockRecord(StrategiesModel,Context,Id,io,true);
    var fields=Map(record["trigger_fields"]);
    Need(Number(fields,"native_type")==4&&Number(fields,"strategy_id")==Id,
         "The strategy does not own its expected Event trigger.");
    uint edge=EdgeMode(fields);
    int recordId=Number(fields,"native_record_id");
    var contexts=Context.Catalog(true);
    var selected=Context.Find(contexts,Id,Name);
    Need(Text(selected,"context")==NativeMemory.Hex(context),"The canonical Event is not its selected root-array owner.");
    var rows=Trigger.Db(Context);
    var sqlRow=DbRow(rows,recordId);
    Need(recordId>0&&Number(sqlRow,"strategy_id")==Id&&Number(sqlRow,"type")==4&&
         Text(sqlRow,"note")==Text(fields,"note"),"Event Trigger table owner/type/original note differs.");
    return new Dictionary<string,object>{{"abi_profile_sha256",ProfileSha},{"block_id",Id},{"block_name",Name},
     {"native_record_id",recordId},{"root_block_index",Number(selected,"root_block_index")},
     {"edge",Modes[(int)edge]},{"block",record},{"contexts",contexts},{"trigger_rows",rows},
     {"graph",NativeReferencedPageEditing.Graph(References)}};
   }
  }

  internal static Dictionary<string,object> Read(NativeEngine engine,NativeContext ctxt,string project,Dictionary<string,object> action){
   return new Api(engine,ctxt,project,action).Capture();
  }

  internal sealed class Prepared:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly Api api;
   readonly Dictionary<string,object> action,before,wanted;
   readonly IntPtr canonical,canonicalIo;
   readonly int recordId,index,edgeOffset;
   readonly uint desired;
   readonly Trigger.Factory create;
   readonly Trigger.VI destroy;
   readonly Trigger.VIP adopt;
   readonly Trigger.VP copy,rowLoad,rowWrite;
   readonly Trigger.VI dirty,rootDirty;
   readonly Trigger.V0 recordEdit,recordUpdate;
   readonly IntPtr list;
   readonly ListFindId findId;
   readonly ListItemState itemState;
   readonly Trigger.VI selectRow;
   readonly string scopeHash;
   IntPtr stored;
   Dictionary<string,object> diskWanted,applied;
   bool validated,entered,failed,disposed;

   internal Prepared(NativeEngine engine,NativeContext ctxt,string project,Dictionary<string,object> request){
    api=new Api(engine,ctxt,project,request);action=request;
    Need(Text(action,"abi_profile_sha256")==ProfileSha,"Event edge action ABI differs.");
    var after=Map(action["after"]);
    Need(after.Count==1&&after.ContainsKey("edge"),"Event edge editing accepts only an edge value.");
    string edge=Text(after,"edge");
    int mode=Array.IndexOf(Modes,edge);
    Need(mode!=2&&mode!=3,"The verified original Event compilers reject both compound transitions.");
    Need(mode>=0,"Event edge requires rising, falling or change.");
    desired=(uint)mode;
    before=api.Capture();
    NativePageControlPreparation.Before(action,before);
    canonical=api.Canonical(out canonicalIo);
    var original=Map(Map(before["block"])["trigger_fields"]);
    wanted=WithEdge(original,desired);
    NoOp=EdgeMode(original)==desired;
    recordId=Number(before,"native_record_id");index=Number(before,"root_block_index");
    scopeHash=NativeMemory.Hash(api.Context.Project);
    if(NoOp)return;

    IntPtr ctor=api.Methods.Address("CreateEvent"),dtor=api.Methods.Address("DeleteEvent");
    edgeOffset=api.Context.VerifyEventEdgeMethods(canonical,ctor,dtor,api.Methods.Address("EventEquals"),
                                                    api.Methods.Address("EventPropertyConfirm"));
    create=engine.Bind<Trigger.Factory>(ctor);destroy=engine.Bind<Trigger.VI>(dtor);
    adopt=api.Context.RootSet;copy=api.Context.Copy;rowLoad=api.Context.RowLoad;rowWrite=api.Context.RowWrite;
    dirty=api.Context.ContextDirty;rootDirty=api.Context.RootDirty;
    recordEdit=api.Context.RecordEdit;recordUpdate=api.Context.RecordUpdate;
    var listApi=new NativeStrategyDeleteExtensionProfile.Api(engine,ctxt);
    list=listApi.List;
    findId=listApi.Bind<ListFindId>("ListFindId");
    itemState=api.Methods.Bind<ListItemState>("StrategyListItemState");
    selectRow=api.Methods.Bind<Trigger.VI>("SelectStrategyListRow");
   }
   internal bool NoOp{get;private set;}

   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){
    if(NoOp)return;
    Need(plan.Commit,"Event edge editing requires commit:true to preserve the live and stored caches independently.");
    plan.RequireRelatedStrategyPersistence(action,api.Id);
   }

   void Current(){
    IntPtr io;
    Need(!disposed&&!failed&&api.Canonical(out io)==canonical&&io==canonicalIo,
         "Canonical Event owner changed.");
   }
   internal void ValidateBefore(){
    Current();
    Need(!entered,"Event edge Apply has already been entered.");
    Same(before,api.Capture(),"Event edge exact current preimage changed.");
    Need(NativeMemory.Hash(api.Context.Project)==scopeHash,"Stored Event project changed before Apply.");
    validated=true;
   }

   void ActivateManagementRow(){
    uint process;
    // The guarded CListCtrl state reader obtains this exact native HWND member.
    IntPtr window=NativeMemory.Ptr(list,0x20);
    Need(window!=IntPtr.Zero&&GetWindowThreadProcessId(window,out process)==NativeMemory.GetCurrentThreadId()&&
         process==(uint)Process.GetCurrentProcess().Id&&IsWindowVisible(window),
         "The strategy management list needs to be visible inside the current Pro project.");
    int row=findId(list,api.Id);
    Need(row>=0,"The exact native Event strategy has no management row.");
    if((itemState(list,row,ListSelectionMask)&ListSelectionMask)!=ListSelectionMask)selectRow(list,row);
    Need(findId(list,api.Id)==row&&(itemState(list,row,ListSelectionMask)&ListSelectionMask)==ListSelectionMask,
         "The original Event strategy management row was not selected.");
   }

   IntPtr CreateOwned(){
    IntPtr result=create();
    Need(result!=IntPtr.Zero&&result!=canonical&&result!=stored&&
         !api.Context.Base.Array(NativeMemory.Add(api.Context.Base.Root,0x240),"RootTriggers").Contains(result),
         "Native Event factory did not return an independent owner.");
    var projection=api.Context.Snapshot(result,true).Fields;
    Need(Number(projection,"native_type")==4,"Detached native Event type differs.");
    return result;
   }
   Dictionary<string,object> ReadFields(IntPtr address){return api.Context.Snapshot(address,true).Fields;}
   void ChangeOwnedEdge(IntPtr owned,Dictionary<string,object> completeAfter){
    Need(owned!=canonical&&!api.Context.Base.Array(NativeMemory.Add(api.Context.Base.Root,0x240),"RootTriggers").Contains(owned),
         "The Event edge word can only be set on a detached native owner.");
    Marshal.WriteInt32(owned,edgeOffset,unchecked((int)desired));
    Same(completeAfter,ReadFields(owned),"Detached Event field or cache changed outside its edge word.");
   }
   void Release(ref IntPtr owned){
    if(owned==IntPtr.Zero)return;
    IntPtr pointer=owned;owned=IntPtr.Zero;destroy(pointer,1);
   }

   void PreserveCanonicalAndGraph(Dictionary<string,object> state) {
    var oldBlock=Map(before["block"]);var nowBlock=Map(state["block"]);
    Same(Without(oldBlock,"trigger_fields","trigger_complete_raw_hex","block_complete_raw_hex","block_dirty_raw"),
         Without(nowBlock,"trigger_fields","trigger_complete_raw_hex","block_complete_raw_hex","block_dirty_raw"),
         "Event edge edit changed another field or persistent node of the selected strategy.");
    byte[] raw=NativeMemory.Bytes(NativeMemory.Add(canonicalIo,-4),0x68);
    string recorded=Text(oldBlock,"block_complete_raw_hex");
    string current=Hex(raw);
    int dirtyHex=0x64*2;
    Need(recorded.Remove(dirtyHex,2)==current.Remove(dirtyHex,2),
         "The canonical strategy changed outside its original preload dirty byte.");
    Same(wanted,Map(nowBlock["trigger_fields"]),"Original adoption did not preserve the expected Event fields/cache.");
    Same(ForeignContexts(before),ForeignContexts(state),"Event edge edit changed a foreign trigger context.");
    Same(before["graph"],state["graph"],"Event edge edit changed original registered references.");
   }
   List<object> ForeignContexts(Dictionary<string,object> state) {
    var result=new List<object>();
    foreach(object value in (IEnumerable)state["contexts"])if(Number(Map(value),"block_id")!=api.Id)result.Add(value);
    return result;
   }

   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){
    Current();Need(validated&&!entered,"Event edge requires its validated current preimage.");
    lease.BeginApply(action);entered=true;
    if(NoOp){
     applied=before;lease.CompleteApply(action);
     return new Dictionary<string,object>{{"ok",true},{"changed",false},{"after",before}};
    }
    IntPtr owned=IntPtr.Zero;
    try{
     lease.RequireApplying(action);
     ActivateManagementRow();
     NativeOperationTrace.BeforeMutation("event-edge-original-private-dao-decode");
     stored=CreateOwned();
     using(var cursor=new Trigger.Cursor(api.Context)){
      cursor.Locate(recordId);
      Same(DbRow((List<object>)before["trigger_rows"],recordId),cursor.Value(),"Event Trigger preimage changed.");
      cursor.Call(delegate{rowLoad(stored,cursor.Storage);});
     }
     var disk=ReadFields(stored);
     Same(Without(Map(Map(before["block"])["trigger_fields"]),"event_cache"),Without(disk,"event_cache"),
          "Canonical and stored Event differ outside their independent compiled cache.");
     diskWanted=WithEdge(disk,desired);
     ChangeOwnedEdge(stored,diskWanted);

     NativeOperationTrace.BeforeMutation("event-edge-original-private-canonical-copy");
     owned=CreateOwned();
     copy(owned,canonical);
     Same(Map(Map(before["block"])["trigger_fields"]),ReadFields(owned),"Original Event copy changed canonical fields/cache.");
     ChangeOwnedEdge(owned,wanted);
     Current();lease.RequireApplying(action);
     NativeOperationTrace.BeforeMutation("event-edge-original-canonical-adoption");
     rootDirty(api.Context.Base.Root,1);
     Marshal.WriteInt32(api.Context.Base.Root,NativeLayout.Offset("document.compile_valid"),0);
     adopt(api.Context.Base.Root,index,owned);
     Need(Marshal.ReadByte(canonical,0x20)==1,"Original Event adoption did not mark the target dirty.");
     Release(ref owned);

     applied=api.Capture();
     PreserveCanonicalAndGraph(applied);
     Same(before["trigger_rows"],applied["trigger_rows"],"Event Apply wrote the Trigger table before its explicit Flush.");
     lease.CompleteApply(action);
     return new Dictionary<string,object>{{"ok",true},{"changed",true},{"after",applied},
      {"strategy_manager_row_selected",true},{"original_context_adoption_returned",true},
      {"canonical_compiled_cache",wanted["event_cache"]},{"original_stored_compiled_cache",diskWanted["event_cache"]}};
    }catch{
     failed=true;NativeOperationTrace.SetPhase("event-edge-apply-failed-owned-"+NativeMemory.Hex(owned)+"-stored-"+NativeMemory.Hex(stored));throw;
    }
   }

   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){
    Current();
    Need(entered&&applied!=null,"Event Apply must complete before Flush.");
    if(NoOp){lease.BeginFlush(action);lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"changed",false}};}
    Same(applied,api.Capture(),"Event edge changed before the exact native row update.");
    Need(NativeMemory.Hash(api.Context.Project)==scopeHash,"Stored Event project changed before Flush.");
    lease.BeginFlush(action);
    IntPtr verification=IntPtr.Zero;
    try{
     lease.RequireRelatedStrategyPersistence(action,api.Id);
     var originalRows=(List<object>)before["trigger_rows"];
     var rowBefore=DbRow(originalRows,recordId);
     Same(diskWanted,ReadFields(stored),"Detached stored Event changed before its exact flush.");
     NativeOperationTrace.BeforeMutation("event-edge-original-record-edit-serialize-update");
     using(var cursor=new Trigger.Cursor(api.Context)){
      cursor.Locate(recordId);
      Same(rowBefore,cursor.Value(),"Event native row changed before Edit.");
      cursor.Call(delegate{recordEdit(cursor.Storage);});
      cursor.Call(delegate{rowWrite(stored,cursor.Storage);});
      cursor.Call(delegate{recordUpdate(cursor.Storage);});
     }
     var currentRows=Trigger.Db(api.Context);
     Need(currentRows.Count==originalRows.Count,"Event update changed Trigger row count.");
     foreach(object value in originalRows){
      var row=Map(value);int id=Number(row,"id");
      var current=DbRow(currentRows,id);
      if(id!=recordId)Same(row,current,"Event update changed a non-target Trigger row.");
      else{
       Same(Without(row,"binary_sha256","binary_bytes"),Without(current,"binary_sha256","binary_bytes"),
            "Event update changed native row identity, original note, or nullable metadata.");
       Need(Text(row,"binary_sha256")!=Text(current,"binary_sha256"),"Event Trigger binary did not change.");
      }
     }
     verification=CreateOwned();
     using(var cursor=new Trigger.Cursor(api.Context)){
      cursor.Locate(recordId);
      cursor.Call(delegate{rowLoad(verification,cursor.Storage);});
     }
     Same(diskWanted,ReadFields(verification),"Fresh native row verification did not recover the exact Event properties and stored cache.");
     Release(ref verification);Release(ref stored);
     // Clear this one dirty byte after verified native persistence so a later
     // ordinary RootSave doesn't overwrite the independent Trigger-row cache.
     dirty(canonical,0);
     Need(Marshal.ReadByte(canonical,0x20)==0,"Original context dirty clear did not complete.");
     var verified=api.Capture();
     PreserveCanonicalAndGraph(verified);
     Same(currentRows,verified["trigger_rows"],"The independently decoded Trigger rows changed during native verification.");
     lease.CompleteFlush(action);
     return new Dictionary<string,object>{{"ok",true},{"changed",true},{"native_record_id",recordId},
      {"fresh_native_row_decode_exact",true},{"verified_native_trigger_rows_stable",true},
      {"root_save_still_required",true},{"stored_compiled_cache",diskWanted["event_cache"]},
      {"event_context_dirty_after",0}};
    }catch{
     failed=true;NativeOperationTrace.SetPhase("event-edge-flush-failed-owned-"+NativeMemory.Hex(verification)+"-stored-"+NativeMemory.Hex(stored));throw;
    }
   }

   public void Dispose(){
    if(disposed)return;
    disposed=true;
    // A failed native call can leave ownership uncertain. Release only on the verified path.
    if(!failed)Release(ref stored);
   }
  }
 }
}

