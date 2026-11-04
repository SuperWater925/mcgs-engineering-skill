// Control identity rename through the original reference-aware ObjectModel worker.
using System;using System.Collections.Generic;using System.IO;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativeControlPropertyEditing {
  internal const string RenameKind="control-referenced-rename",RenameScopeSha="dbc0f929f80f4ea9e2db8175958b79f9f4ba5416e39ac65899a349289891b3b4";
  static void RenameScope(){string path=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"typed-properties","control-rename-scope.json");NativeMemory.Require(NativeMemory.Hash(path)==RenameScopeSha,"Control rename contract differs.");}
  static Dictionary<string,object> ReadRename(Api api,Dictionary<string,object> action,out Selection selected){
   RenameScope();NativeMemory.Require(!Map(action["target"]).ContainsKey("component_path"),"A property component is not a drawing-control identity rename target.");
   selected=Capture(api,action);NativeMemory.Require(selected.Selected==selected.Object,"Control rename must address the original IObject owner.");
   return new Dictionary<string,object>{{"abi_profile_sha256",RenameScopeSha},{"kind",RenameKind},{"control_state",selected.Snapshot},
    {"rename_state",NativeReferencedPageEditing.PreparedObjectRename.Read(api.Engine,api.Context,NativeUsableEditPermit.Fixture,action,selected.Object)},{"full_serialization_preimage",false}};
  }
  internal static Dictionary<string,object> ReadRename(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){Selection selected;return ReadRename(new Api(e,c,project),action,out selected);}
  internal static PreparedRename PrepareRename(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new PreparedRename(new Api(e,c,project),action);}
  internal sealed class PreparedRename:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly Api api;readonly Dictionary<string,object> action,before,postAction;readonly Selection selected;readonly NativeReferencedPageEditing.PreparedObjectRename rename;
   readonly NativeControlHistoryContext history;readonly BeforeModify notify;readonly VI rootDirty,docDirty,invalidate;readonly V0 update;readonly object expectedProperties;bool disposed,applied,failed;
   internal PreparedRename(Api a,Dictionary<string,object> request){
    api=a;action=request;NativeMemory.Require(Convert.ToString(request["kind"])==RenameKind&&Convert.ToString(request["abi_profile_sha256"])==RenameScopeSha,"Control rename kind/ABI differs.");
    before=ReadRename(api,action,out selected);NativePageControlPreparation.Before(action,before);if(selected.View!=IntPtr.Zero)history=new NativeControlHistoryContext(api.Engine,selected.Doc,api.Common.Shared.RootDoc());
    var after=Map(action["after"]);NativeMemory.Require(after.ContainsKey("name")&&after.ContainsKey("target_properties")&&after.ContainsKey("rename_state"),"Control rename needs the complete explicit target property and consumer postimages.");
    string name=NativePageControlPreparation.Text(after,"name");NativePageControlPreparation.Name(name);NativeMemory.Require(name.IndexOf('.')<0&&name!=Convert.ToString(Map(action["target"])["control_name"]),"Control rename is a no-op or contains a linker separator.");
    expectedProperties=after["target_properties"];var target=new Dictionary<string,object>(Map(action["target"]));target["control_name"]=name;
    postAction=new Dictionary<string,object>(action);postAction["target"]=target;
    notify=api.Bind<BeforeModify>("DocBeforeModify");rootDirty=api.Common.Shared.Bind<VI>("RootSetModified");docDirty=api.Common.Bind<VI>("standard","DocSetModified");invalidate=api.Bind<VI>("InvalidateView");update=api.Bind<V0>("UpdateView");
    if(selected.View!=IntPtr.Zero)api.Common.Slot(selected.Doc,96,0x3CBE6);
    try{rename=NativeReferencedPageEditing.PreparedObjectRename.Prepare(api.Engine,api.Context,NativeUsableEditPermit.Fixture,action,selected.Object);
     ValidateBefore();
    }catch{Dispose();throw;}
   }
   internal void ValidateBefore(){if(history!=null)history.ValidateBefore();NativeMemory.Require(!disposed&&!applied&&!failed,"Control rename is disposed/applied/failed.");Selection now;NativePageControlPreparation.Same(before,ReadRename(api,action,out now),"Control and full consumer preimage changed after preparation.");rename.ValidateBefore();}
   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){rename.ValidatePersistence(plan);if(plan.Commit)plan.RequireRelatedPagePersistence(action,Convert.ToInt32(Map(action["target"])["page_id"]));}
   Selection VerifyTarget(){Selection now=Capture(api,postAction);NativeMemory.Require(now.Page==selected.Page&&now.Doc==selected.Doc&&now.Full==selected.Full&&now.Object==selected.Object&&now.View==selected.View,"Control rename changed identity, document, ownership or view.");NativePageControlPreparation.Same(expectedProperties,now.Values,"Control rename target property postimage differs from the complete explicit expectation.");var protectedBefore=history==null?selected.Snapshot:Map(history.ExpectedSnapshot(selected.Snapshot));var oldPage=Map(protectedBefore["page"]);var newPage=Map(now.Snapshot["page"]);var expectedTop=new List<object>();foreach(object raw in(System.Collections.IEnumerable)oldPage["top_level_controls"]){var row=new Dictionary<string,object>(Map(raw));if(Convert.ToString(row["complete"])==NativeMemory.Hex(selected.Full))row["name"]=Map(postAction["target"])["control_name"];expectedTop.Add(row);}NativePageControlPreparation.Same(expectedTop,newPage["top_level_controls"],"Control rename changed native control geometry/identity/raw state beyond its exact name and original history projection.");foreach(string key in new[]{"attributes","pages"})NativePageControlPreparation.Same(oldPage[key],newPage[key],"Control rename changed an unrelated page field: "+key);return now;}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){
    ValidateBefore();lease.BeginApply(action);try{
     var native=rename.ApplyWithinExistingLease(lease,delegate{
      NativeOperationTrace.BeforeMutation("control-rename-original-page-before-modify");if(selected.View!=IntPtr.Zero){history.ValidateBefore();notify(selected.Doc,selected.View,1,1);history.OriginalBeforeModifyReturned();}else docDirty(selected.Doc,1);
      rootDirty(api.Common.Shared.RootDoc(),1);Marshal.WriteInt32(api.Common.Shared.RootDoc(),0x114,0);
     },history);
     if(selected.View!=IntPtr.Zero){NativeOperationTrace.BeforeMutation("control-rename-native-invalidate");invalidate(selected.View,1);NativeOperationTrace.BeforeMutation("control-rename-native-update");update(selected.View);}
     Selection now=VerifyTarget();applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",RenameKind},{"native_rename",native},{"original_history_store_projection",history==null?null:(object)history.Report()},{"target_after",now.Snapshot},{"complete_expected_consumers_required",true},{"full_persistence_acceptance_pending",true}};
    }catch{failed=true;throw;}
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){
    NativeMemory.Require(applied&&!disposed&&!failed,"Control rename Apply must complete before Flush.");lease.BeginFlush(action);try{VerifyTarget();var result=rename.FlushWithinExistingLease(lease);VerifyTarget();lease.CompleteFlush(action);return result;}catch{failed=true;throw;}
   }
   public void Dispose(){if(disposed)return;disposed=true;if(rename!=null)rename.Dispose();}
  }
 }
}
