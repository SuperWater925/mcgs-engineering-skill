// User-requested native page Undo/Redo; never replayed automatically by an edit.
using System;using System.Collections.Generic;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static class NativePageHistoryEditing {
  internal const string AbiProfileSha="9ab9fef153e982c0a53e7a758dcf9eedd2c8797747acf393a85ce47eeb858d3a";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Can(IntPtr doc,int checkBusy);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Embedded(IntPtr view,IntPtr output);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VI(IntPtr self,int value);
  [UnmanagedFunctionPointer(CallingConvention.Cdecl)][return:MarshalAs(UnmanagedType.I1)]delegate bool Busy();
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool SaveData(IntPtr service,IntPtr page);
  static Dictionary<string,object> Map(object value){return NativePageControlPreparation.Map(value);}
  static Dictionary<string,object> State(NativeControlPropertyEditing.Api api,Dictionary<string,object> action) {
   IntPtr page=api.Common.Page(Map(action["target"])),doc=NativeMemory.Ptr(page,0x14),view=api.Bind<NativeEngine.ThisPointer>("GetDrawingView")(doc);
   NativeMemory.Require(view!=IntPtr.Zero&&NativeMemory.Ptr(view,0)==api.Engine.Address(0xD9041C)&&api.Bind<NativeEngine.ThisPointer>("DrawingViewGetDocument")(view)==doc,"Native page history requires its current drawing view.");
   NativeMemory.Require(!api.Bind<Busy>("GlobalBusy")(),"Native global edit guard is busy.");IntPtr storage=Marshal.AllocHGlobal(4);
   try{Marshal.WriteInt32(storage,0);NativeMemory.Require(api.Bind<Embedded>("EmbeddedEditor1")(view,storage)==0,"An embedded editor owns this native history branch.");Marshal.WriteInt32(storage,0);NativeMemory.Require(api.Bind<Embedded>("EmbeddedEditor2")(view,storage)==0,"An embedded editor owns this native history branch.");}finally{Marshal.FreeHGlobal(storage);}
   int undo=api.Bind<Can>("DocumentCanUndo")(doc,0),redo=api.Bind<Can>("DocumentCanRedo")(doc,0);NativeMemory.Require((undo==0||undo==1)&&(redo==0||redo==1),"Native history availability is not Boolean.");
   return new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"page",api.Common.PageSnapshot(page)},{"document",NativeMemory.Hex(doc)},{"view",NativeMemory.Hex(view)},
    {"all_grouped_common_controls",NativeUsableEditPermit.CurrentDrawControls(api.Engine,doc,Convert.ToInt32(Map(action["target"])["page_id"]))},{"can_undo",undo!=0},{"can_redo",redo!=0}};
  }
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return State(new NativeControlPropertyEditing.Api(e,c,p),action);}
  internal static Prepared Prepare(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return new Prepared(new NativeControlPropertyEditing.Api(e,c,p),action);}
  internal sealed class Prepared:INativePreparedPageControlEdit {
   readonly NativeControlPropertyEditing.Api api;readonly Dictionary<string,object> action,before;readonly string operation;readonly int steps;
   readonly V0 command,update;readonly VI invalidate;readonly SaveData save;bool applied,disposed;
   internal Prepared(NativeControlPropertyEditing.Api value,Dictionary<string,object> a) {
    api=value;action=a;NativeMemory.Require(Convert.ToString(a["kind"])=="page-history"&&Convert.ToString(a["abi_profile_sha256"])==AbiProfileSha,"Page history action kind/ABI differs.");before=State(api,a);NativePageControlPreparation.Before(a,before);
    var after=Map(a["after"]);operation=Convert.ToString(after["operation"]);steps=Convert.ToInt32(after["steps"]);NativeMemory.Require((operation=="undo"||operation=="redo")&&steps>=1,"Page history needs undo/redo and a positive explicit step count.");
    NativeMemory.Require(Convert.ToBoolean(before[operation=="undo"?"can_undo":"can_redo"]),"Requested native history is unavailable.");
    command=api.Bind<V0>(operation=="undo"?"UndoCommand":"RedoCommand");invalidate=api.Bind<VI>("InvalidateView");update=api.Bind<V0>("UpdateView");save=api.Common.Bind<SaveData>("standard","WindowSaveData");api.Common.Slot(api.Context.WindowService,12,0x21733);
   }
   internal void ValidateBefore(){NativeMemory.Require(!disposed&&!applied,"Prepared history is disposed/already entered.");NativePageControlPreparation.Same(before,State(api,action),"Page native history/common state changed after preparation.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease) {
    ValidateBefore();lease.BeginApply(action);applied=true;var checkpoints=new List<object>();
    for(int step=0;step<steps;step++) {
     lease.RequireApplying(action);var current=State(api,action);NativeMemory.Require(Convert.ToBoolean(current[operation=="undo"?"can_undo":"can_redo"]),"Native history ended before all requested steps; partial result retained, no replay.");
     IntPtr view=new IntPtr(NativeEngine.Number(current["view"]));NativeOperationTrace.BeforeMutation("explicit-native-page-"+operation+"-step-"+(step+1));command(view);
     // Every old control pointer is invalid after the original reconstruction command.
     var after=State(api,action);NativeMemory.Require(Convert.ToString(after["document"])==Convert.ToString(before["document"])&&Convert.ToString(after["view"])==Convert.ToString(before["view"]),"Native history changed its page document/view identity.");
     NativeOperationTrace.BeforeMutation("explicit-native-page-history-invalidate");invalidate(view,1);NativeOperationTrace.BeforeMutation("explicit-native-page-history-update");update(view);checkpoints.Add(after);
    }
    lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"operation",operation},{"requested_steps",steps},{"completed_steps",checkpoints.Count},{"checkpoints",checkpoints},{"controls_reenumerated_after_each_command",true},{"automatic_history_replay",false},{"consolidated_content_acceptance_pending",true}};
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(applied&&!disposed,"Page history Apply must precede Flush.");lease.BeginFlush(action);IntPtr page=api.Common.Page(Map(action["target"])),doc=NativeMemory.Ptr(page,0x14);int dirty=NativeMemory.I32(doc,0x48);NativeMemory.Require(dirty==0||dirty==1,"Native page history dirty state differs.");
    if(dirty==1){NativeOperationTrace.BeforeMutation("explicit-native-page-history-save-data");NativeMemory.Require(save(api.Context.WindowService,page)&&NativeMemory.I32(doc,0x48)==0,"Native history page saveData did not clean its document.");}lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"root_save_called",false}};
   }
   public void Dispose(){disposed=true;}
  }
 }
}
