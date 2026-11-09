// Typed properties for a logical control or explicit getter-derived component.
// Uses original getter/setter and document history/refresh/saveData chains.
using System;using System.Collections;using System.Collections.Generic;using System.Globalization;
using System.IO;using System.Runtime.InteropServices;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeControlPropertyEditing {
  internal const string AbiProfileSha="1944705fe9b567dd96e1e4e1ebee5542a58a3cf0f1f364f19c18f2c4830d558a";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Setter(IntPtr self,IntPtr dispatcher);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void BeforeModify(IntPtr doc,IntPtr view,int modified,int history);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VI(IntPtr self,int value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool SaveData(IntPtr service,IntPtr page);
  [DllImport("user32.dll")][return:MarshalAs(UnmanagedType.Bool)]static extern bool IsWindow(IntPtr hwnd);
  internal sealed class Api {
   internal readonly NativePageControlAbi Common;internal readonly NativeEngine Engine;internal readonly NativeContext Context;
   readonly NativeLazyFunctionProfile methods;
   internal Api(NativeEngine engine,NativeContext context,string project) {
    Engine=engine;Context=context;Common=new NativePageControlAbi(engine,context,project);
    string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"typed-properties","control-properties-abi-profile.json");
    NativeMemory.Require(NativeLazyFunctionProfile.SourceHash(file)==AbiProfileSha,"Control property ABI contract changed.");
    var contract=ReadJson(file);NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(contract["binary_sha256"]),engine.ImageSha256,"NativeControlPropertyEditing:21:editor"),"Control property ABI belongs to another installed image.");
    file=Path.Combine(NativeOperations.TaskRoot,Convert.ToString(contract["original_live_profile_file"]).Replace('/',Path.DirectorySeparatorChar));
    NativeMemory.Require(NativeLazyFunctionProfile.SourceHash(file)==Convert.ToString(contract["original_live_profile_sha256"]),"Control history/refresh ABI proof changed.");
    string relative=Path.GetFullPath(file).Substring(Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\').Length+1).Replace('\\','/');methods=new NativeLazyFunctionProfile(engine,relative,Convert.ToString(contract["original_live_profile_sha256"]),"editor");
   }
   internal T Bind<T>(string name)where T:class{Common.Current();return methods.Bind<T>(name);}
  }
  static Dictionary<string,object> ReadJson(string file){return new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Deserialize<Dictionary<string,object>>(NativeLazyFunctionProfile.ReadText(file));}
  static Dictionary<string,object> Map(object value){return NativePageControlPreparation.Map(value);}
  static List<Dictionary<string,object>> CloneRows(List<Dictionary<string,object>> rows){return new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Deserialize<List<Dictionary<string,object>>>(NativePageControlPreparation.Json(rows));}
  static List<IntPtr> GroupChildren(Api api,IntPtr complete,IntPtr doc) {
   int type=NativeMemory.I32(complete,0xC);NativeMemory.Require(type==0x503A||type==0x5039,"Only actual CDrawUnit/CDrawCell containers carry this verified child-list layout.");
   return NativeDynamicCollections.ReadDrawList(NativeMemory.Add(complete,0xE4),doc,api.Engine.Address(0xD3FD70));
  }
  sealed class Selection {internal IntPtr Page,Doc,Full,Object,Selected,View;internal List<Dictionary<string,object>> Values;internal Dictionary<string,object> Snapshot;}
  static IntPtr CaptureDrawingView(Api api,IntPtr doc) {
   IntPtr view=api.Bind<NativeEngine.ThisPointer>("GetDrawingView")(doc);
   if(view!=IntPtr.Zero)NativeMemory.Require(NativeMemory.Ptr(view,0)==api.Engine.Address(0xD9041C)&&api.Bind<NativeEngine.ThisPointer>("DrawingViewGetDocument")(view)==doc&&IsWindow(NativeMemory.Ptr(view,0x20)),"Control view/document/HWND differs.");
   return view;
  }
  static Selection Capture(Api api,Dictionary<string,object> action) {return Capture(api,Map(action["target"]),null);}
  static Selection Capture(Api api,Dictionary<string,object> target,BatchSelection batch) {
   IntPtr page=batch==null?api.Common.Page(target):batch.Page;
   IntPtr doc=batch==null?api.Common.Document(page,Convert.ToInt32(target["page_id"])):batch.Doc,full=IntPtr.Zero;
   var current=batch==null?api.Common.TopControls(doc):batch.TopControls;object raw;
   if(target.TryGetValue("control_path",out raw)) {
    var path=new List<int>();foreach(object n in (IEnumerable)raw)path.Add(Convert.ToInt32(n));NativeMemory.Require(path.Count>0,"Control path is empty.");
    var pathObjects=new HashSet<uint>();for(int i=0;i<path.Count;i++){NativeMemory.Require(path[i]>=0&&path[i]<current.Count,"Control path is outside current native ownership list.");full=current[path[i]];NativeMemory.Require(pathObjects.Add(NativeMemory.U(full)),"Control path repeats a native owner-tree object.");if(i+1<path.Count)current=GroupChildren(api,full,doc);}
   }else {
    foreach(IntPtr candidate in current)if(NativeStrategyProfile.ReadName(api.Common.Shared,NativeMemory.Add(candidate,4))==NativePageControlPreparation.Text(target,"control_name")){NativeMemory.Require(full==IntPtr.Zero,"Top-level control name is not unique; use a native control_path.");full=candidate;}
   }
   NativeMemory.Require(full!=IntPtr.Zero&&NativeMemory.Ptr(full,0x64)==doc,"Logical control is absent or has another document owner.");
   IntPtr obj=NativeMemory.Add(full,4);var info=api.Engine.Describe(obj);
   NativeMemory.Require(Convert.ToInt32(info["complete_offset"])==4&&NativeStrategyProfile.ReadName(api.Common.Shared,obj)==NativePageControlPreparation.Text(target,"control_name")&&Convert.ToString(info["rtti"])==NativePageControlPreparation.Text(target,"rtti"),"Logical control name/RTTI/base offset differs.");
   var s=new Selection{Page=page,Doc=doc,Full=full,Object=obj,Selected=obj,View=batch==null?CaptureDrawingView(api,doc):batch.View};
   using(var collector=new NativeTypedPropertyCollector(api.Engine))s.Values=collector.Read(obj);
   AnnotateComponentOccurrences(s.Values);
   if(target.TryGetValue("component_path",out raw))foreach(object n in (IEnumerable)raw) {
    IntPtr child=ResolveComponent(api,s.Values,s.Selected,n);
    NativeMemory.Require(child!=IntPtr.Zero,"Requested getter-derived component path is absent.");NativePropertyTarget.Describe(api.Engine,child);s.Selected=child;
   }
   s.Snapshot=new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"page",batch==null?api.Common.PageSnapshot(page):batch.PageState},
    {"control",new Dictionary<string,object>{{"name",NativeStrategyProfile.ReadName(api.Common.Shared,obj)},{"rtti",info["rtti"]},{"type_id",NativeMemory.I32(full,0xC)},{"complete",NativeMemory.Hex(full)},{"iobject",NativeMemory.Hex(obj)},{"owner_document",NativeMemory.Hex(doc)}}},
    {"selected_owner",NativeMemory.Hex(s.Selected)},{"properties",s.Values},{"root_modified",NativeMemory.I32(api.Common.Shared.RootDoc(),0x48)},{"compile_valid",NativeMemory.I32(api.Common.Shared.RootDoc(),0x114)}};
   return s;
  }
  internal static Dictionary<string,object> Read(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action){return Capture(new Api(engine,context,project),action).Snapshot;}
  internal static Prepared Prepare(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action){return new Prepared(new Api(engine,context,project),action);}
  internal sealed class Prepared:INativePreparedPageControlEdit {
   readonly Api api;readonly Dictionary<string,object> action;readonly Selection before;readonly List<Dictionary<string,object>> expected;
   readonly NativeControlHistoryContext history;readonly Setter setter;readonly BeforeModify notify;readonly VI rootDirty,docDirty,invalidate;readonly V0 update;readonly SaveData save;
   NativeTypedPropertyDispatcher dispatcher;bool applied,disposed;
   internal Prepared(Api native,Dictionary<string,object> request) {
    api=native;action=request;NativeMemory.Require(Convert.ToString(action["kind"])=="control-properties"&&Convert.ToString(action["abi_profile_sha256"])==AbiProfileSha,"Typed control action kind/ABI differs.");
    before=Capture(api,action);NativePageControlPreparation.Before(action,before.Snapshot);expected=CloneRows(before.Values);if(before.View!=IntPtr.Zero)history=new NativeControlHistoryContext(api.Engine,before.Doc,api.Common.Shared.RootDoc());
    setter=api.Engine.Bind<Setter>(api.Engine.Virtual(before.Selected,5));notify=api.Bind<BeforeModify>("DocBeforeModify");rootDirty=api.Common.Shared.Bind<VI>("RootSetModified");docDirty=api.Common.Bind<VI>("standard","DocSetModified");invalidate=api.Bind<VI>("InvalidateView");update=api.Bind<V0>("UpdateView");save=api.Common.Bind<SaveData>("standard","WindowSaveData");
    if(before.View!=IntPtr.Zero)api.Common.Slot(before.Doc,96,0x3CBE6);api.Common.Slot(api.Context.WindowService,12,0x21733);
    var writes=new List<Dictionary<string,object>>();var seen=new HashSet<string>(StringComparer.Ordinal);
    foreach(object raw in (IEnumerable)Map(action["after"])["properties"]) {
     var requested=Map(raw);string key=NativePageControlPreparation.Text(requested,"native_key");int tag=Convert.ToInt32(requested["native_type_tag"]);NativeMemory.Require(seen.Add(key)&&tag!=9,"Property key duplicates or requires an explicit component target.");
     Dictionary<string,object> match=null;foreach(var row in expected)if(Convert.ToString(row["native_owner"])==NativeMemory.Hex(before.Selected)&&Convert.ToString(row["native_key"])==key){NativeMemory.Require(match==null,"Native getter returned an ambiguous owner/key.");match=row;}
     NativeMemory.Require(match!=null&&Convert.ToInt32(match["native_type_tag"])==tag,"Requested key/tag is not an actual property of the selected native owner.");
     object value=requested["value"];
     if(tag==1){
      var font=Map(value);var normalized=new Dictionary<string,object>(font);var rows=new List<object>();var originalLanguages=new HashSet<int>();var changedLanguages=new HashSet<int>();
      foreach(object row in (IEnumerable)Map(match["value"])["rows"])NativeMemory.Require(originalLanguages.Add(Convert.ToInt32(Map(row)["language_id"])),"Original font language repeats.");
      foreach(object row in (IEnumerable)font["rows"]){int language=Convert.ToInt32(Map(row)["language_id"]);NativeMemory.Require(originalLanguages.Contains(language)&&changedLanguages.Add(language),"Font-style edit must retain each actual original language ID exactly once.");rows.Add(row);}
      NativeMemory.Require(changedLanguages.SetEquals(originalLanguages),"Font-style edit cannot remove a language record.");normalized["row_count"]=rows.Count;value=normalized;
     }
     NativeMemory.Require(NativePageControlPreparation.Json(match["value"])!=NativePageControlPreparation.Json(value),"Remove unchanged properties from an edit action.");match["value"]=value;
     writes.Add(new Dictionary<string,object>{{"native_key",key},{"native_type_tag",tag},{"value",requested["value"]}});
    }
    try{dispatcher=new NativeTypedPropertyDispatcher(api.Common.Shared,writes);}catch{Dispose();throw;}
   }
   internal void ValidateBefore(){if(history!=null)history.ValidateBefore();NativeMemory.Require(!disposed&&!applied,"Typed control preparation is disposed or already applied.");NativePageControlPreparation.Same(before.Snapshot,Capture(api,action).Snapshot,"Typed control preimage changed after preparation.");}
   void ValidateClaimedTarget(NativeUsableEditPermit.Lease lease){lease.RequireCurrent();if(history!=null)history.ValidateBefore();NativeMemory.Require(!disposed&&!applied,"Typed control preparation is disposed or already applied.");var current=Capture(api,action).Snapshot;var a=new Dictionary<string,object>(before.Snapshot);var b=new Dictionary<string,object>(current);a.Remove("root_modified");a.Remove("compile_valid");b.Remove("root_modified");b.Remove("compile_valid");NativePageControlPreparation.Same(a,b,"Claimed typed control target/page/property preimage changed.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease) {
    ValidateClaimedTarget(lease);lease.BeginApply(action);applied=true;lease.RequireApplying(action);
    NativeOperationTrace.BeforeMutation("typed-control-original-before-modify");
    if(before.View!=IntPtr.Zero){notify(before.Doc,before.View,1,1);history.OriginalBeforeModifyReturned();}else docDirty(before.Doc,1);
    rootDirty(api.Common.Shared.RootDoc(),1);Marshal.WriteInt32(api.Common.Shared.RootDoc(),0x114,0);
    NativeOperationTrace.BeforeMutation("typed-control-original-property-setter");dispatcher.Invoke(delegate(IntPtr sink){setter(before.Selected,sink);});
    if(before.View!=IntPtr.Zero){NativeOperationTrace.BeforeMutation("typed-control-native-invalidate");invalidate(before.View,1);NativeOperationTrace.BeforeMutation("typed-control-native-update");update(before.View);}
    Selection after=Capture(api,action);VerifyExpectedState(after);
    lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind","control-properties"},{"after",after.Snapshot},{"native_getter_setter_used",true},{"original_history_store_projection",history==null?null:(object)history.Report()},{"automatic_undo_redo_replay",false},{"full_persistence_acceptance_pending",true}};
   }
   void VerifyExpectedState(Selection after){NativeMemory.Require(after.Page==before.Page&&after.Doc==before.Doc&&after.Full==before.Full&&after.Selected==before.Selected&&after.View==before.View,"Typed setter changed native object ownership/identity.");
    NativePageControlPreparation.Same(expected,after.Values,"Typed property target postimage or untouched component values differ.");
    var protectedBefore=history==null?before.Snapshot:Map(history.ExpectedSnapshot(before.Snapshot));var b=Map(protectedBefore["page"]);var a=Map(after.Snapshot["page"]);NativePageControlPreparation.Same(b["attributes"],a["attributes"],"Typed setter changed page attributes.");NativePageControlPreparation.Same(b["top_level_controls"],a["top_level_controls"],"Typed setter changed control identity/geometry/raw state.");NativePageControlPreparation.Same(b["pages"],a["pages"],"Typed setter changed page identities.");
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(applied&&!disposed,"Apply must precede typed property Flush.");lease.BeginFlush(action);api.Common.Current();VerifyExpectedState(Capture(api,action));int dirty=NativeMemory.I32(before.Doc,0x48);NativeMemory.Require(dirty==0||dirty==1,"Typed page dirty state differs.");
    if(dirty==1){NativeOperationTrace.BeforeMutation("typed-control-page-save-data");NativeMemory.Require(save(api.Context.WindowService,before.Page)&&NativeMemory.I32(before.Doc,0x48)==0,"Typed property page saveData did not clean its document.");}
    VerifyExpectedState(Capture(api,action));lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"root_save_called",false}};
   }
   public void Dispose(){if(disposed)return;disposed=true;if(dispatcher!=null){dispatcher.Dispose();dispatcher=null;}}
  }
 }
}
