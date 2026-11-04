// Explicit persistence of current verified native state, without replaying edit actions.
using System;using System.Collections;using System.Collections.Generic;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static class NativePersistenceEditing {
  internal const string PageAbi="3b38a7bafd4d49cc93be51a2b14529c95c8f57924072e42db04f45582a5fc18a";
  internal const string StrategyAbi=NativeUsableStrategySourceBatch.AbiProfileSha;
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VI(IntPtr self,int value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool SaveData(IntPtr service,IntPtr page);
  static Dictionary<string,object> Map(object v){return NativePageControlPreparation.Map(v);}
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action) {
   string kind=Convert.ToString(action["kind"]);var common=new NativePageControlAbi(e,c,p);IntPtr root=common.Shared.RootDoc();
   if(kind=="page-flush")return new Dictionary<string,object>{{"abi_profile_sha256",PageAbi},{"page",common.PageSnapshot(common.Page(Map(action["target"])) )}};
   if(kind=="root-flush")return new Dictionary<string,object>{{"abi_profile_sha256",PageAbi},{"root_document",NativeMemory.Hex(root)},{"root_modified",NativeMemory.I32(root,0x48)},{"compile_valid",NativeMemory.I32(root,0x114)},{"disk_sha256",NativeMemory.Hash(p)}};
   NativeMemory.Require(kind=="strategy-flush","Unknown persistence action.");
   var target=Map(action["target"]);int id=Convert.ToInt32(target["block_id"]);string name=Convert.ToString(target["block_name"]);
   var full=NativeStrategyExtensionProfile.Inspect(e,c);object block=null;var programs=new List<object>();
   foreach(object value in (IEnumerable)full["blocks"]){var row=Map(value);if(Convert.ToInt32(row["block_id"])==id){NativeMemory.Require(block==null&&Convert.ToString(row["block_name"])==name,"Persistence strategy block name/ID differs.");block=row;}}
   NativeMemory.Require(block!=null,"Persistence strategy block is absent.");foreach(object value in (IEnumerable)full["programs"])if(Convert.ToInt32(Map(value)["block_id"])==id)programs.Add(value);
   return new Dictionary<string,object>{{"abi_profile_sha256",StrategyAbi},{"block",block},{"programs",programs},{"root_modified",NativeMemory.I32(root,0x48)},{"compile_valid",NativeMemory.I32(root,0x114)}};
  }
  internal static Prepared Prepare(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return new Prepared(e,c,p,action);}
  internal sealed class Prepared:INativePreparedPageControlEdit {
   readonly NativeEngine engine;readonly NativeContext context;readonly string project,kind;readonly Dictionary<string,object> action,before;
   readonly NativePageControlAbi api;readonly IntPtr page,doc,block,preload;readonly SaveData pageSave;readonly V0 strategySave;readonly VI strategyDirty;
   bool applied,disposed;
   internal Prepared(NativeEngine e,NativeContext c,string p,Dictionary<string,object> a) {
    engine=e;context=c;project=p;action=a;kind=Convert.ToString(a["kind"]);api=new NativePageControlAbi(e,c,p);
    NativeMemory.Require(Convert.ToString(a["abi_profile_sha256"])==(kind=="strategy-flush"?StrategyAbi:PageAbi),"Persistence action ABI differs.");
    pageSave=api.Bind<SaveData>("standard","WindowSaveData");strategySave=api.Shared.Bind<V0>("StrategyPreloadSaveData");strategyDirty=api.Shared.Bind<VI>("StrategyPreloadSetDirty");
    before=Read(e,c,p,a);NativePageControlPreparation.Before(a,before);
    if(kind=="page-flush"){page=api.Page(Map(a["target"]));doc=NativeMemory.Ptr(page,0x14);api.Slot(c.WindowService,12,0x21733);}
    else if(kind=="strategy-flush") {
     block=new IntPtr(NativeEngine.Number(Map(before["block"])["block_iobject"]));preload=NativeMemory.Add(block,4);
     NativeMemory.Require(NativeMemory.Ptr(block,0)==e.Address(0xE3B4DC)&&NativeMemory.Ptr(block,-4)==e.Address(0xE3B4B8)&&NativeMemory.Ptr(preload,0)==e.Address(0xE3B56C),"Persistence strategy secondary interface differs.");
     api.Shared.MatchVirtual(preload,2,"StrategyPreloadSaveData");api.Shared.MatchVirtual(preload,3,"StrategyPreloadSetDirty");
    }
   }
   internal void ValidateBefore(){NativeMemory.Require(!disposed&&!applied,"Persistence preparation is disposed/applied.");NativePageControlPreparation.Same(before,Read(engine,context,project,action),"Current persistence preimage changed after preparation.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",kind},{"edit_replayed",false},{"native_mutation_in_apply",false}};}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(applied&&!disposed,"Persistence Apply must precede Flush.");lease.BeginFlush(action);api.Current();bool called=false;
    if(kind=="page-flush"){int dirty=NativeMemory.I32(doc,0x48);NativeMemory.Require(dirty==0||dirty==1,"Persistence page dirty state differs.");if(dirty==1){NativeOperationTrace.BeforeMutation("explicit-persistence-native-page-save-data");called=true;NativeMemory.Require(pageSave(context.WindowService,page)&&NativeMemory.I32(doc,0x48)==0,"Explicit page saveData failed to clean its page.");}}
    else if(kind=="strategy-flush") {
     int dirty=Marshal.ReadByte(block,0x60);NativeMemory.Require(dirty<=1,"Persistence strategy dirty state differs.");
     if(dirty==1){NativeOperationTrace.BeforeMutation("explicit-persistence-native-strategy-save-data");called=true;strategySave(preload);NativeMemory.Require(Marshal.ReadByte(block,0x60)==1,"Original strategy SaveData state differs.");}
     var after=Read(engine,context,project,action);NativePageControlPreparation.Same(before["programs"],after["programs"],"Explicit strategy saveData changed complete program sources.");
    }
    lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"kind",kind},{"child_save_data_called",called},{"root_save_called",false},{"consolidated_persistence_acceptance_pending",true}};
   }
   public void Dispose(){disposed=true;}
  }
 }
}
