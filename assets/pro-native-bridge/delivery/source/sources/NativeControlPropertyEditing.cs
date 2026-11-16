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
   int type=NativeMemory.I32(complete,NativeLayout.Offset("control.type_id"));NativeMemory.Require(type==0x503A||type==0x5039,"Only actual CDrawUnit/CDrawCell containers carry this verified child-list layout.");
   return NativeDynamicCollections.ReadDrawList(NativeMemory.Add(complete,0xE4),doc,api.Engine.Address(0xD3FD70));
  }
  static readonly IntPtr[] EmptyOwnerChildren=new IntPtr[0];
  static IEnumerable<IntPtr> IdentityChildren(Api api,IntPtr full,IntPtr doc){
   IntPtr instance;string rtti;
   if(NativeOpaqueDrawState.TryControlObject(full,out instance,out rtti)&&(rtti==".?AVCDrawUnit@@"||rtti==".?AVCDrawCell@@"))
    return GroupChildren(api,full,doc);
   return EmptyOwnerChildren;
  }
  static HashSet<IntPtr> PropertyOwnerIndex(Api api,List<IntPtr> roots,IntPtr doc){
   var result=new HashSet<IntPtr>();
   foreach(IntPtr full in NativeDynamicCollections.DepthFirst(roots,delegate(IntPtr current){return IdentityChildren(api,current,doc);}))
    NativeMemory.Require(result.Add(full),"Current property owner tree repeats a native control.");
   return result;
  }
  sealed class Selection {internal IntPtr Page,Doc,Full,Object,Selected,View;internal List<Dictionary<string,object>> Values;internal Dictionary<string,object> Snapshot;}
  static IntPtr CaptureDrawingView(Api api,IntPtr doc) {
   IntPtr view=api.Bind<NativeEngine.ThisPointer>("GetDrawingView")(doc);
   if(view!=IntPtr.Zero)NativeMemory.Require(NativeMemory.Ptr(view,0)==api.Engine.Address(0xD9041C)&&api.Bind<NativeEngine.ThisPointer>("DrawingViewGetDocument")(view)==doc&&IsWindow(NativeMemory.Ptr(view,0x20)),"Control view/document/HWND differs.");
   return view;
  }
  static Selection Capture(Api api,Dictionary<string,object> action) {object after,properties;return Capture(api,Map(action["target"]),null,action.TryGetValue("after",out after)&&Map(after).TryGetValue("properties",out properties)?(IEnumerable)properties:null,false);}
  static Selection Capture(Api api,Dictionary<string,object> target,BatchSelection batch,IEnumerable requested=null,bool paired=false) {
   IntPtr page=batch==null?api.Common.Page(target):batch.Page;
   IntPtr doc=batch==null?api.Common.Document(page,Convert.ToInt32(target["page_id"])):batch.Doc,full=IntPtr.Zero;
   var current=batch==null?api.Common.TopControls(doc):batch.TopControls;object raw;
   if(target.TryGetValue("control_path",out raw)) {
    var path=new List<int>();foreach(object n in (IEnumerable)raw)path.Add(Convert.ToInt32(n));NativeMemory.Require(path.Count>0,"Control path is empty.");
    var pathObjects=new HashSet<uint>();for(int i=0;i<path.Count;i++){NativeMemory.Require(path[i]>=0&&path[i]<current.Count,"Control path is outside current native ownership list.");full=current[path[i]];NativeMemory.Require(pathObjects.Add(NativeMemory.U(full)),"Control path repeats a native owner-tree object.");if(i+1<path.Count)current=GroupChildren(api,full,doc);}
   }else if(target.TryGetValue("complete",out raw)){
    NativeMemory.Require(target.ContainsKey("native_id"),"Property target without a path needs its complete address and native ID.");
    var identities=batch==null?PropertyOwnerIndex(api,current,doc):batch.OwnerIdentities(api);
    full=new IntPtr(NativeEngine.Number(raw));
    NativeMemory.Require(identities.Contains(full),"Property control complete identity is outside the current page owner tree.");
   }else {
    string name=NativePageControlPreparation.Text(target,"control_name"),rtti=NativePageControlPreparation.Text(target,"rtti");
    foreach(IntPtr candidate in current){
     IntPtr instance;string type;
     if(!NativeOpaqueDrawState.TryControlObject(candidate,out instance,out type)||type!=rtti||NativeStrategyProfile.ReadName(api.Common.Shared,instance)!=name)continue;
     NativeMemory.Require(full==IntPtr.Zero,"Top-level control name and class are not unique; use a native control_path.");full=candidate;
    }
   }
   NativeMemory.Require(full!=IntPtr.Zero&&NativeMemory.Ptr(full,NativeLayout.Offset("control.owner_document"))==doc,"Logical control is absent or has another document owner.");
   IntPtr obj=NativeOpaqueDrawState.ControlObject(full);var info=NativePropertyTarget.Describe(api.Engine,obj);
   NativeMemory.Require(NativeStrategyProfile.ReadName(api.Common.Shared,obj)==NativePageControlPreparation.Text(target,"control_name")&&Convert.ToString(info["rtti"])==NativePageControlPreparation.Text(target,"rtti"),"Logical control name/RTTI/base offset differs.");
   if(target.TryGetValue("complete",out raw))NativeMemory.Require(full==new IntPtr(NativeEngine.Number(raw)),"Property control complete identity differs.");
   if(target.TryGetValue("native_id",out raw))NativeMemory.Require(NativeStrategyProfile.ReadId(api.Common.Shared,obj)==NativeEngine.Number(raw),"Property control native ID differs.");
   var s=new Selection{Page=page,Doc=doc,Full=full,Object=obj,Selected=obj,View=batch==null?CaptureDrawingView(api,doc):batch.View};
   bool local=requested!=null;
   if(!local){using(var collector=new NativeTypedPropertyCollector(api.Engine))s.Values=collector.Read(obj);AnnotateComponentOccurrences(s.Values);}
   if(target.TryGetValue("component_path",out raw))foreach(object n in (IEnumerable)raw) {
    if(local){using(var collector=new NativeTypedPropertyCollector(api.Engine))s.Values=collector.ReadComponents(s.Selected);AnnotateComponentOccurrences(s.Values);}
    IntPtr child=ResolveComponent(api,s.Values,s.Selected,n);
    NativeMemory.Require(child!=IntPtr.Zero,"Requested getter-derived component path is absent.");NativePropertyTarget.Describe(api.Engine,child);s.Selected=child;
   }
   if(local){var keys=new List<string>();foreach(object property in requested)keys.Add(NativePageControlPreparation.Text(Map(property),"native_key"));
    if(!paired){using(var collector=new NativeTypedPropertyCollector(api.Engine))s.Values=collector.ReadSelected(s.Selected,keys);}
    else{using(var collector=new NativeTypedPropertyCollector(api.Engine))s.Values=collector.ReadComponents(obj);var states=new List<Dictionary<string,object>>(s.Values);foreach(var row in states){string key=Convert.ToString(row["native_key"]);if(key!="抬起状态"&&key!="按下状态")continue;IntPtr owner=new IntPtr(NativeEngine.Number(row["component_iobject"]));var descriptor=NativePropertyTarget.Describe(api.Engine,owner);row["component_rtti"]=descriptor["rtti"];row["component_property_interface"]=descriptor["property_interface"];using(var collector=new NativeTypedPropertyCollector(api.Engine))s.Values.AddRange(collector.ReadSelected(owner,keys));}}
    AnnotateComponentOccurrences(s.Values);}
   s.Snapshot=new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"page",batch==null?api.Common.PageSnapshot(page):batch.PageState},
    {"control",new Dictionary<string,object>{{"name",NativeStrategyProfile.ReadName(api.Common.Shared,obj)},{"rtti",info["rtti"]},{"type_id",NativeMemory.I32(full,NativeLayout.Offset("control.type_id"))},{"complete",NativeMemory.Hex(full)},{"iobject",NativeMemory.Hex(obj)},{"owner_document",NativeMemory.Hex(doc)}}},
    {"selected_owner",NativeMemory.Hex(s.Selected)},{"properties",s.Values},{"property_capture_scope",local?"requested keys on selected owner":"full property tree"},{"root_modified",NativeMemory.I32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.modified"))},{"compile_valid",NativeMemory.I32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"))}};
   return s;
  }
  internal static Dictionary<string,object> Read(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action){return Capture(new Api(engine,context,project),action).Snapshot;}
  internal static Prepared Prepare(NativeEngine engine,NativeContext context,string project,Dictionary<string,object> action){return new Prepared(new Api(engine,context,project),action);}
  internal sealed class Prepared:INativePreparedPageControlEdit {
   readonly Api api;readonly Dictionary<string,object> action;readonly Selection before;readonly List<Dictionary<string,object>> expected;
   readonly Setter setter;readonly BeforeModify notify;readonly VI rootDirty,docDirty,invalidate;readonly V0 update;
   NativeTypedPropertyDispatcher dispatcher;bool applied,disposed,noOp;Dictionary<string,object> preservationPage;int originalHistoryCalls;
   internal bool HasChanges{get{return !noOp;}}
   internal Prepared(Api native,Dictionary<string,object> request) {
    api=native;action=request;NativeMemory.Require(Convert.ToString(action["kind"])=="control-properties"&&Convert.ToString(action["abi_profile_sha256"])==AbiProfileSha,"Typed control action kind/ABI differs.");
    before=Capture(api,action);NativePageControlPreparation.Before(action,before.Snapshot);expected=CloneRows(before.Values);preservationPage=Map(before.Snapshot["page"]);
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
     if(NativePageControlPreparation.Json(match["value"])==NativePageControlPreparation.Json(value))continue;match["value"]=value;
     writes.Add(new Dictionary<string,object>{{"native_key",key},{"native_type_tag",tag},{"value",requested["value"]}});
    }
    noOp=writes.Count==0;if(noOp)return;
    setter=NativePropertyTarget.Bind<Setter>(api.Engine,before.Selected,true);rootDirty=api.Common.Shared.Bind<VI>("RootSetModified");docDirty=api.Common.Bind<VI>("standard","DocSetModified");if(before.View!=IntPtr.Zero){notify=api.Bind<BeforeModify>("DocBeforeModify");invalidate=api.Bind<VI>("InvalidateView");update=api.Bind<V0>("UpdateView");}
    try{dispatcher=new NativeTypedPropertyDispatcher(api.Common.Shared,writes);}catch{Dispose();throw;}
   }
   internal void ValidateBefore(){NativeMemory.Require(!disposed&&!applied,"Typed control preparation is disposed or already applied.");NativePageControlPreparation.Same(before.Snapshot,Capture(api,action).Snapshot,"Typed control preimage changed after preparation.");}
   void ValidateClaimedTarget(NativeUsableEditPermit.Lease lease){lease.RequireCurrent();NativeMemory.Require(!disposed&&!applied,"Typed control preparation is disposed or already applied.");var current=Capture(api,action).Snapshot;var a=new Dictionary<string,object>(before.Snapshot);var b=new Dictionary<string,object>(current);a.Remove("root_modified");a.Remove("compile_valid");b.Remove("root_modified");b.Remove("compile_valid");NativePageControlPreparation.Same(a,b,"Claimed typed control target/page/property preimage changed.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease) {
    ValidateClaimedTarget(lease);lease.BeginApply(action);applied=true;lease.RequireApplying(action);
    if(noOp){lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind","control-properties"},{"no_op",true},{"after",before.Snapshot},{"native_setter_calls",0},{"original_history_captures",0},{"native_refreshes",0}};}
    NativeOperationTrace.BeforeMutation("typed-control-original-before-modify");
    if(before.View!=IntPtr.Zero){notify(before.Doc,before.View,1,1);originalHistoryCalls++;var notified=Capture(api,action);NativePageControlPreparation.Same(before.Values,notified.Values,"Original before-modify changed requested business properties.");NativeOriginalHistoryObservation.VerifyPage(preservationPage,Map(notified.Snapshot["page"]));preservationPage=Map(notified.Snapshot["page"]);}else docDirty(before.Doc,1);
    rootDirty(api.Common.Shared.RootDoc(),1);Marshal.WriteInt32(api.Common.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"),0);
    NativeOperationTrace.BeforeMutation("typed-control-original-property-setter");dispatcher.Invoke(delegate(IntPtr sink){setter(before.Selected,sink);});
    if(before.View!=IntPtr.Zero){NativeOperationTrace.BeforeMutation("typed-control-native-invalidate");invalidate(before.View,1);NativeOperationTrace.BeforeMutation("typed-control-native-update");update(before.View);}
    Selection after=Capture(api,action);VerifyExpectedState(after);
    lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind","control-properties"},{"after",after.Snapshot},{"native_getter_setter_used",true},{"original_history_captures",originalHistoryCalls},{"history_baseline","observed after original notification, before setter"},{"automatic_undo_redo_replay",false},{"full_persistence_acceptance_pending",true}};
   }
   void VerifyExpectedState(Selection after){NativeMemory.Require(after.Page==before.Page&&after.Doc==before.Doc&&after.Full==before.Full&&after.Selected==before.Selected&&after.View==before.View,"Typed setter changed native object ownership/identity.");
    NativePageControlPreparation.Same(expected,after.Values,"Typed property target postimage or untouched component values differ.");
    var b=preservationPage;var a=Map(after.Snapshot["page"]);NativePageControlPreparation.Same(b["attributes"],a["attributes"],"Typed setter changed page attributes.");NativePageControlPreparation.Same(b["top_level_controls"],a["top_level_controls"],"Typed setter changed control identity/geometry/raw state.");NativePageControlPreparation.Same(b["pages"],a["pages"],"Typed setter changed page identities.");
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(applied&&!disposed,"Apply must precede typed property Flush.");lease.BeginFlush(action);api.Common.Current();if(!noOp)VerifyExpectedState(Capture(api,action));int dirty=NativeMemory.I32(before.Doc,NativeLayout.Offset("document.modified"));NativeMemory.Require(dirty==0||dirty==1,"Typed page dirty state differs.");
    if(dirty==1&&!noOp){var save=api.Common.Bind<SaveData>("standard","WindowSaveData");NativeOperationTrace.BeforeMutation("typed-control-page-save-data");NativeMemory.Require(save(api.Context.WindowService,before.Page)&&NativeMemory.I32(before.Doc,NativeLayout.Offset("document.modified"))==0,"Typed property page saveData did not clean its document.");}
    if(dirty==1&&!noOp)VerifyExpectedState(Capture(api,action));lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1&&!noOp},{"root_save_called",false}};
   }
   public void Dispose(){if(disposed)return;disposed=true;if(dispatcher!=null){dispatcher.Dispose();dispatcher=null;}}
  }
 }
}
