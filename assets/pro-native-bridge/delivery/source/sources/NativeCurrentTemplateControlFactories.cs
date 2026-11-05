// Original installed RECT placement constructors/defaults, independent of a template.
// RuntimeClass no-arg constructors are archive LOAD constructors; they leave +58/+5C
// uninitialized and must not be substituted for the native UI creation constructors.
using System;using System.Collections;using System.Collections.Generic;using System.Globalization;
using System.IO;using System.Diagnostics;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal const string FactoryProfileSha="85708fdbb8d537dfc8f3e4f1e16aff0d9000074012a644e072e96f5da8691dbf";
  [UnmanagedFunctionPointer(CallingConvention.StdCall)]delegate IntPtr PlacementAllocate(uint bytes);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr PlacementConstructor(IntPtr self,IntPtr rectangle);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr BasePlacementConstructor(IntPtr self,int type,IntPtr rectangle);
  [DllImport("kernel32.dll",EntryPoint="GetProcAddress")]static extern IntPtr PlacementGetProcAddress(IntPtr module,IntPtr ordinal);
  const string FactoryRelative="coverage-20261101/usable-edit-0001/page-control-prep/native-control-placement-factory-abi-profile.v3.json";
  static Dictionary<string,object> FactoryContract(Api api,string name) {
   var profile=new NativeLazyFunctionProfile(api.Engine,FactoryRelative,FactoryProfileSha,"editor").Profile;
   NativeMemory.Require(Convert.ToInt32(profile["schema"])==1&&NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),api.Engine.ImageSha256,"NativeCurrentTemplateControlFactories:15:editor")&&Convert.ToString(profile["template_profile_sha256"])==ProfileSha&&Convert.ToInt32(profile["defaults_virtual_slot"])==28&&Convert.ToInt32(profile["defaults_reason"])==6,"Native control factory/defaults ABI differs.");
   NativeMemory.Require(Convert.ToBoolean(profile["placement_constructor_profile"]),"Native placement-constructor contract is absent.");
   Dictionary<string,object> selected=null;
   foreach(object row in (IEnumerable)profile["classes"]){var c=Map(row);if(Convert.ToString(c["class_name"])==name){NativeMemory.Require(selected==null,"Installed native class name repeats.");selected=c;}}
   NativeMemory.Require(selected!=null&&!Convert.ToBoolean(selected["external_component_dependency"]),"Blank creation requires a built-in installed native class; external component activation needs its own context adapter.");
   NativeAbiTargetProfiles.CheckDirectEntry(selected,"factory class",FactoryRelative);
   var required=new HashSet<int>();var byReference=new Dictionary<int,Dictionary<string,object>>();
   foreach(object value in (IEnumerable)profile["code_guards"]){var row=Map(value);var state=Map(row["_abi_resolution"]);object reference;if(state.TryGetValue("reference_rva",out reference))byReference.Add(Num(reference),row);}
   var visited=new HashSet<int>();foreach(string operation in new string[]{"factory","defaults","placement_constructor"})RequireFactoryGuards(Map(selected[operation]),profile,byReference,required,visited);
   var allocation=Map(profile["allocator"]);NativeAbiTargetProfiles.CheckEntry(allocation,"allocator",FactoryRelative);required.Add(Num(allocation["entry_rva"]));required.Add(Num(allocation["body_rva"]));
   foreach(object value in (IEnumerable)profile["code_guards"]){var row=Map(value);if(NativeAbiTargetProfiles.IsEntryResolved(row,FactoryRelative)&&required.Remove(Num(row["rva"])))FactoryBytes(api.Engine,row);}
   NativeMemory.Require(required.Count==0,"Requested native factory chain has no complete code guard coverage.");PlacementAllocatorAddress(api,allocation);
   NativeMemory.Require(Convert.ToBoolean(Map(selected["factory"])["abi_matches"])&&Convert.ToBoolean(Map(selected["defaults"])["abi_matches"]),"Native class factory/defaults ABI is not closed.");
   IntPtr runtime=api.Engine.Address(Num(selected["runtime_class_rva"]));NativeMemory.Require(NativeMemory.Ascii(NativeMemory.Ptr(runtime,0),128)==name&&NativeMemory.I32(runtime,4)==Num(selected["size"])&&NativeMemory.I32(runtime,8)==Num(selected["runtime_class_schema"])&&NativeMemory.Ptr(runtime,12)==api.Engine.Address(Num(Map(selected["factory"])["entry_rva"])),"Installed native runtime class factory/size/schema differs.");
   IntPtr vt=api.Engine.Address(Num(selected["primary_vtable_rva"]));NativeMemory.Require(NativeMemory.Ptr(vt,28*4)==api.Engine.Address(Num(Map(selected["defaults"])["entry_rva"])),"Installed native primary28 defaults entry differs.");
   var placement=Map(selected["placement_constructor"]);NativeMemory.Require(Convert.ToBoolean(placement["abi_matches"])&&(Num(placement["return_stack_bytes"])==4||(name=="CDrawObj"&&Num(placement["return_stack_bytes"])==8)),"Installed class placement constructor ABI is not closed.");selected["allocator"]=profile["allocator"];return selected;
  }
  // Historical disassembly VAs are used only as reference-role keys into attested guard rows.
  // Every runtime address below comes from a resolved row; no reference VA becomes a native pointer.
  static void RequireFactoryGuards(Dictionary<string,object> method,Dictionary<string,object> profile,Dictionary<int,Dictionary<string,object>> byReference,HashSet<int> required,HashSet<int> visited){
   NativeAbiTargetProfiles.CheckEntry(method,"factory method",FactoryRelative);int body=Num(method["body_rva"]);required.Add(Num(method["entry_rva"]));required.Add(body);if(!visited.Add(body))return;
   object raw;if(method.TryGetValue("chain_rvas",out raw))foreach(object value in (IEnumerable)raw)required.Add(Num(value));
   var calls=new List<object>();if(method.TryGetValue("parent_calls",out raw))foreach(object value in (IEnumerable)raw)calls.Add(value);
   if(method.TryGetValue("source_derivation",out raw)){var derivation=Map(raw);if(derivation.TryGetValue("calls",out raw))foreach(object value in (IEnumerable)raw)calls.Add(value);}
   foreach(object value in calls){var call=Map(value);if(!call.TryGetValue("jump_chain",out raw))continue;foreach(object historical in (IEnumerable)raw){int reference=Num(historical)-0x400000;Dictionary<string,object> guard;if(!byReference.TryGetValue(reference,out guard))continue;NativeAbiTargetProfiles.CheckEntry(guard,"factory dependency code guard",FactoryRelative);int actual=Num(guard["rva"]);required.Add(actual);
    foreach(object classValue in (IEnumerable)profile["classes"]){var cls=Map(classValue);foreach(string operation in new string[]{"factory","defaults","placement_constructor"}){var candidate=Map(cls[operation]);if(NativeAbiTargetProfiles.IsEntryResolved(candidate,FactoryRelative)&&(Num(candidate["entry_rva"])==actual||Num(candidate["body_rva"])==actual))RequireFactoryGuards(candidate,profile,byReference,required,visited);}}
   }}
  }
  static void FactoryBytes(NativeEngine engine,Dictionary<string,object> row) {
   NativeAbiTargetProfiles.CheckEntry(row,"factory code guard",FactoryRelative);string text=Convert.ToString(row["bytes"]);byte[] bytes=new byte[text.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(text.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
   bytes=NativeCodeRelocation.Rebase(bytes,(IEnumerable)row["reloc_offsets"],NativeMemory.U(engine.ImageBase),0x400000U);
   NativeMemory.Require(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(engine.Address(Num(row["rva"])),bytes.Length)),"Native factory/defaults code signature differs.");
  }
  static IntPtr PlacementAllocatorAddress(Api api,Dictionary<string,object> allocation) {
   NativeAbiTargetProfiles.CheckEntry(allocation,"allocator",FactoryRelative);NativeMemory.Require(Convert.ToString(allocation["calling_convention"])=="stdcall pointer(uint32 size)"&&Num(allocation["return_stack_bytes"])==4,"Original allocation wrapper ABI differs.");
   var m=Map(allocation["mfc"]);string expectedPath=Path.GetFullPath(Convert.ToString(m["path"]));ProcessModule module=null;
   foreach(ProcessModule item in Process.GetCurrentProcess().Modules)if(String.Equals(Path.GetFullPath(item.FileName),expectedPath,StringComparison.OrdinalIgnoreCase)){NativeMemory.Require(module==null||(module.BaseAddress==item.BaseAddress&&module.ModuleMemorySize==item.ModuleMemorySize),"Original allocator MFC module is ambiguous.");module=item;}
   NativeMemory.Require(module!=null&&module.ModuleMemorySize==Num(m["size_of_image"])&&NativeBinaryIdentity.Observe(Convert.ToString(m["sha256"]),NativeMemory.Hash(expectedPath),"NativeCurrentTemplateControlFactories:34:module"),"Original allocator MFC module/hash differs.");
   IntPtr expected=NativeMemory.Add(module.BaseAddress,Num(m["export_rva"]));NativeMemory.Require(NativeMemory.U(expected)>=NativeMemory.U(module.BaseAddress)&&(ulong)NativeMemory.U(expected)<(ulong)NativeMemory.U(module.BaseAddress)+(uint)module.ModuleMemorySize&&PlacementGetProcAddress(module.BaseAddress,new IntPtr(Num(m["ordinal"])))==expected&&NativeMemory.Ptr(api.Engine.Address(Num(allocation["operator_new_iat_rva"])),0)==expected,"Original allocator MFC1502 export/IAT differs.");
   var g=Map(m["guard"]);string hex=Convert.ToString(g["bytes"]);byte[] bytes=new byte[hex.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
   bytes=NativeCodeRelocation.Rebase(bytes,(IEnumerable)g["reloc_offsets"],NativeMemory.U(module.BaseAddress),unchecked((uint)Num(m["preferred_base"])));
   NativeMemory.Require(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(expected,bytes.Length)),"Original allocator MFC1502 prefix differs.");return api.Engine.Address(Num(allocation["entry_rva"]));
  }
  static Class InstalledClass(Api api,string name) {
   var profile=new NativeLazyFunctionProfile(api.Engine,"coverage-20261101/usable-edit-0001/page-control-prep/current-template-control-abi-profile.v2.json",ProfileSha,"editor").Profile;Class selected=null;
   foreach(object raw in (IEnumerable)profile["classes"]){var row=Map(raw);if(Convert.ToString(row["class_name"])==name){NativeMemory.Require(selected==null,"Installed CDraw class repeats.");NativeAbiTargetProfiles.CheckDirectEntry(row,"class",Api.TemplateRelative);NativeAbiTargetProfiles.CheckEntry(Map(row["primary"]),"vtable",Api.TemplateRelative);NativeAbiTargetProfiles.CheckEntry(Map(row["iobject"]),"vtable",Api.TemplateRelative);selected=new Class(row);}}
   NativeMemory.Require(selected!=null,"Installed CDraw class is absent.");return selected;
  }
  static Dictionary<string,object> CaptureFactory(Api api,Dictionary<string,object> action) {
   var target=Map(action["target"]);string name=NativePageControlPreparation.Text(target,"class");FactoryContract(api,name);IntPtr page=api.Shared.Page(target),doc=NativeMemory.Ptr(page,0x14);
   return new Dictionary<string,object>{{"abi_profile_sha256",FactoryProfileSha},{"class",name},{"target_page",api.Shared.PageSnapshot(page)},{"target_forest",SnapshotForest(api,doc)},{"view_state",api.ViewState(doc)},{"history_store_projection",NativeHistoryStoreProjection.Prepare(api.Engine,doc).Before}};
  }
  internal interface INativeFactoryPrepared:INativePreparedPageControlEdit {void ValidateBefore();}
  [ThreadStatic] static DirectFactoryCaptureScope directFactoryCapture;
  internal static DirectFactoryCaptureScope BeginDirectFactoryCapture(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){NativeMemory.Require(directFactoryCapture==null,"Direct factory capture nesting is not allowed.");var scope=new DirectFactoryCaptureScope(e,c,project,action);directFactoryCapture=scope;return scope;}
  internal sealed class DirectFactoryCaptureScope:IDisposable {
   readonly NativeEngine engine;readonly NativeContext context;readonly string project;readonly Dictionary<string,object> action;readonly int thread;Dictionary<string,object> before;string beforeDigest;bool taken,disposed;
   internal DirectFactoryCaptureScope(NativeEngine e,NativeContext c,string p,Dictionary<string,object> a){engine=e;context=c;project=p;action=a;thread=NativeMemory.GetCurrentThreadId();}
   internal bool Matches(NativeEngine e,NativeContext c,string p,Dictionary<string,object> a){return !disposed&&directFactoryCapture==this&&engine==e&&context==c&&Object.ReferenceEquals(action,a)&&NativeMemory.GetCurrentThreadId()==thread&&NativeUsableEditPermit.SamePath(project,p);}
   internal void Record(Dictionary<string,object> value){NativeMemory.Require(before==null,"Direct factory capture already recorded.");before=value;beforeDigest=NativeUsableEditPermit.Digest(value);}
   internal Dictionary<string,object> Take(){NativeMemory.Require(before!=null&&!taken&&NativeUsableEditPermit.Digest(before)==beforeDigest,"Direct factory captured before changed or was reused.");taken=true;return before;}
   public void Dispose(){if(disposed)return;disposed=true;if(directFactoryCapture==this)directFactoryCapture=null;}
  }
  internal static Dictionary<string,object> ReadFactory(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){var result=CaptureFactory(new Api(e,c,p),action);if(directFactoryCapture!=null&&directFactoryCapture.Matches(e,c,p,action))directFactoryCapture.Record(result);return result;}
  internal static INativeFactoryPrepared PrepareFactory(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return new PreparedFactory(new Api(e,c,p),action,p);}
  // UI-thread-only explicit scope. A caller groups only consecutive create
  // actions on this exact page; no native mutation is performed by Begin.
  [ThreadStatic] static FactoryBatchScope activeFactoryBatch;
  internal static FactoryBatchScope BeginFactoryBatch(NativeEngine e,NativeContext c,string project,Dictionary<string,object> target){
   NativeMemory.Require(activeFactoryBatch==null,"Factory batch nesting is not supported.");var scope=new FactoryBatchScope(e,c,project,target);if(!scope.HasView){scope.Dispose();return null;}activeFactoryBatch=scope;return scope;
  }
  internal sealed class FactoryBatchScope:IDisposable {
   readonly Api api;readonly IntPtr page,doc,view,root;readonly int thread;readonly VI invalidate;readonly V0 update;
   internal bool historyEntered,completed,disposed;internal int appliedCount;
   internal FactoryBatchScope(NativeEngine e,NativeContext c,string project,Dictionary<string,object> target){api=new Api(e,c,project);thread=NativeMemory.GetCurrentThreadId();page=api.Shared.Page(target);doc=NativeMemory.Ptr(page,0x14);view=api.View(doc);root=api.Shared.Shared.RootDoc();if(view!=IntPtr.Zero){invalidate=api.ViewBind<VI>("InvalidateView");update=api.ViewBind<V0>("UpdateView");}}
   internal bool HasView{get{return view!=IntPtr.Zero;}}
   internal void RequireTarget(NativeEngine engine,NativeContext context,IntPtr p,IntPtr d,IntPtr v,IntPtr r){NativeMemory.Require(!disposed&&!completed&&activeFactoryBatch==this&&NativeMemory.GetCurrentThreadId()==thread&&engine==api.Engine&&context==api.Context&&p==page&&d==doc&&v==view&&r==root&&api.View(doc)==view,"Factory batch page/document/view/thread changed.");api.Shared.Current();}
   internal bool NeedsHistory{get{return !historyEntered;}}
   internal void MarkHistoryReturned(){NativeMemory.Require(!historyEntered,"Factory batch history repeated.");historyEntered=true;}
   internal void RecordApplied(){appliedCount++;}
   internal Dictionary<string,object> Complete(){RequireTarget(api.Engine,api.Context,page,doc,view,root);NativeMemory.Require(appliedCount>0&&historyEntered,"Cannot complete an empty/incomplete factory batch.");var forest=SnapshotForest(api,doc);var pageBefore=api.Shared.PageSnapshot(page);NativeOperationTrace.BeforeMutation("native-factory-batch-invalidate");invalidate(view,1);NativeOperationTrace.BeforeMutation("native-factory-batch-update");update(view);NativePageControlPreparation.Same(forest,SnapshotForest(api,doc),"Factory batch final refresh changed the native forest.");var pageAfter=api.Shared.PageSnapshot(page);NativePageControlPreparation.Same(Map(pageBefore)["attributes"],Map(pageAfter)["attributes"],"Factory batch final refresh changed page attributes.");NativePageControlPreparation.Same(Map(pageBefore)["pages"],Map(pageAfter)["pages"],"Factory batch final refresh changed page identities.");completed=true;return new Dictionary<string,object>{{"ok",true},{"created_count",appliedCount},{"original_history_calls",1},{"final_refresh_calls",1},{"full_persistence_acceptance_pending",true}};}
   public void Dispose(){if(disposed)return;disposed=true;if(activeFactoryBatch==this)activeFactoryBatch=null;}
  }
  sealed class PreparedFactory:INativeFactoryPrepared {
   readonly NativeHistoryStoreProjection history;readonly FactoryBatchScope batch;readonly Api api;readonly Dictionary<string,object> action,before,contract;readonly Class cls;readonly IntPtr page,doc,root,view;readonly PlacementAllocate allocate;readonly PlacementConstructor construct;readonly BasePlacementConstructor baseConstruct;
   readonly VI defaults,rootDirty,docDirty,invalidate;readonly VP add;readonly BeforeModify notify;readonly V0 update;readonly RectSetter setRectangle;readonly SaveData save;readonly SetterForFactory setter;readonly IntPtr setterAddress;
   readonly List<Dictionary<string,object>> requestedProperties=new List<Dictionary<string,object>>();readonly int[] rectangle;readonly int[] attributes;IntPtr rectBuffer;NativeTypedPropertyDispatcher dispatcher;bool applied,disposed,validated;readonly bool directCapture;
   internal PreparedFactory(Api value,Dictionary<string,object> a,string project) {
    api=value;action=a;NativeMemory.Require(Convert.ToString(a["kind"])=="control-native-create"&&Convert.ToString(a["abi_profile_sha256"])==FactoryProfileSha,"Native factory action kind/profile differs.");
    var target=Map(a["target"]);string name=NativePageControlPreparation.Text(target,"class");contract=FactoryContract(api,name);cls=InstalledClass(api,name);directCapture=directFactoryCapture!=null&&directFactoryCapture.Matches(api.Engine,api.Context,project,a);before=directCapture?directFactoryCapture.Take():CaptureFactory(api,a);NativePageControlPreparation.Before(a,before);
    page=api.Shared.Page(target);doc=NativeMemory.Ptr(page,0x14);root=api.Shared.Shared.RootDoc();view=api.View(doc);batch=activeFactoryBatch;if(batch!=null)batch.RequireTarget(api.Engine,api.Context,page,doc,view,root);history=NativeHistoryStoreProjection.Prepare(api.Engine,doc);attributes=api.Shared.Attributes(doc);
    allocate=api.Engine.Bind<PlacementAllocate>(PlacementAllocatorAddress(api,Map(contract["allocator"])));var placement=Map(contract["placement_constructor"]);if(cls.Name=="CDrawObj")baseConstruct=api.Engine.Bind<BasePlacementConstructor>(api.Engine.Address(Num(placement["entry_rva"])));else construct=api.Engine.Bind<PlacementConstructor>(api.Engine.Address(Num(placement["entry_rva"])));defaults=api.Engine.Bind<VI>(api.Engine.Address(Num(Map(contract["defaults"])["entry_rva"])));
    var slots=new List<object>();foreach(object entry in (IEnumerable)cls.Object["entries"])slots.Add(entry);NativeMemory.Require(slots.Count>5,"Native control IObject setter slot is absent.");setterAddress=api.Engine.Address(Num(slots[5]));NativeMemory.Require(NativeMemory.Ptr(api.Engine.Address(Num(cls.Object["vtable_rva"])),20)==setterAddress,"Native control IObject setter table differs.");setter=api.Engine.Bind<SetterForFactory>(setterAddress);
    setRectangle=api.Bind<RectSetter>(cls,"set_rect");add=api.Shared.Bind<VP>("standard","DocAdd");rootDirty=api.Shared.Shared.Bind<VI>("RootSetModified");docDirty=api.Shared.Bind<VI>("standard","DocSetModified");if(view!=IntPtr.Zero)notify=api.ViewBind<BeforeModify>("DocBeforeModify");if(view!=IntPtr.Zero){invalidate=api.ViewBind<VI>("InvalidateView");update=api.ViewBind<V0>("UpdateView");}save=api.Shared.Bind<SaveData>("standard","WindowSaveData");api.Shared.Slot(api.Context.WindowService,12,0x21733);
    var after=Map(a["after"]);rectangle=NativePageControlPreparation.Rect(after,"rectangle",attributes[2],attributes[3]);
    try {
     rectBuffer=Marshal.AllocHGlobal(16);for(int i=0;i<4;i++)Marshal.WriteInt32(rectBuffer,4*i,rectangle[i]);object raw;
     if(after.TryGetValue("properties",out raw)){foreach(object property in (IEnumerable)raw)requestedProperties.Add(Map(property));if(requestedProperties.Count>0)dispatcher=new NativeTypedPropertyDispatcher(api.Shared.Shared,requestedProperties);}
    }catch{Dispose();throw;}
   }
   public void ValidateBefore(){NativeMemory.Require(!disposed&&!applied,"Native factory action is disposed/already entered.");NativePageControlPreparation.Same(before,CaptureFactory(api,action),"Native factory destination/class preimage changed before Claim/Apply.");validated=true;}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(!disposed&&!applied,"Native factory action is disposed/already entered.");if(!directCapture||!validated)ValidateBefore();validated=false;lease.BeginApply(action);applied=true;
    NativeOperationTrace.BeforeMutation("native-control-factory-original-before-modify");if(view!=IntPtr.Zero){if(batch==null||batch.NeedsHistory){history.ValidateBefore();notify(doc,view,1,1);history.OriginalStoreReturned();if(batch!=null)batch.MarkHistoryReturned();}else batch.RequireTarget(api.Engine,api.Context,page,doc,view,root);}else docDirty(doc,1);rootDirty(root,1);Marshal.WriteInt32(root,0x114,0);
    NativeOperationTrace.BeforeMutation("native-control-original-placement-allocation");IntPtr created=allocate(unchecked((uint)cls.Size));NativeMemory.Require(created!=IntPtr.Zero,"Original installed control allocation returned NULL.");
    NativeOperationTrace.BeforeMutation("native-control-original-rectangle-constructor");IntPtr returned=baseConstruct!=null?baseConstruct(created,cls.TypeId,rectBuffer):construct(created,rectBuffer);NativeMemory.Require(returned==created,"Original RECT constructor did not return its owned allocation.");Class actual=api.Type(created);NativeMemory.Require(actual.Name==cls.Name&&actual.TypeId==cls.TypeId&&NativeMemory.Ptr(created,0x64)==IntPtr.Zero&&!api.Shared.TopControls(doc).Contains(created),"Original RECT constructor returned another type/owner or an already registered object.");
    NativePageControlPreparation.Same(rectangle,NativePageControlAbi.Rectangle(created),"Original RECT constructor did not initialize its rectangle.");uint initialized58=unchecked((uint)NativeMemory.I32(created,0x58)),initialized5C=unchecked((uint)NativeMemory.I32(created,0x5C));if(cls.Name=="CDrawRect"||cls.Name=="CDrawLine"||cls.Name=="CDrawLabel")NativeMemory.Require(initialized58==0&&initialized5C==0,"Original primitive RECT constructor did not initialize its serialized flag DWORDs.");
    NativeOperationTrace.BeforeMutation("native-control-original-doc-insert");add(doc,created);NativeMemory.Require(api.Shared.TopControls(doc).Contains(created)&&NativeMemory.Ptr(created,0x64)==doc,"Original native control owner insertion failed.");
    NativeOperationTrace.BeforeMutation("native-control-class-specific-primary28-defaults");defaults(created,6);api.Type(created);
    NativeOperationTrace.BeforeMutation("native-control-class-specific-primary21-rectangle");setRectangle(created,rectBuffer,IntPtr.Zero);NativePageControlPreparation.Same(rectangle,NativePageControlAbi.Rectangle(created),"Original native created rectangle differs.");
    if(dispatcher!=null) {
     IntPtr obj=NativeMemory.Add(created,4);List<Dictionary<string,object>> original;using(var collector=new NativeTypedPropertyCollector(api.Engine))original=collector.Read(obj);
     var expected=new System.Web.Script.Serialization.JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Deserialize<List<Dictionary<string,object>>>(NativePageControlPreparation.Json(original));var seen=new HashSet<string>(StringComparer.Ordinal);
     foreach(var requested in requestedProperties){string key=Convert.ToString(requested["native_key"]);int tag=Convert.ToInt32(requested["native_type_tag"]);NativeMemory.Require(seen.Add(key)&&tag!=9,"Created property key repeats or needs a separate component lifecycle action.");Dictionary<string,object> match=null;foreach(var row in expected)if(Convert.ToString(row["native_owner"])==NativeMemory.Hex(obj)&&Convert.ToString(row["native_key"])==key){NativeMemory.Require(match==null,"Created property owner/key repeats.");match=row;}NativeMemory.Require(match!=null&&Convert.ToInt32(match["native_type_tag"])==tag,"Created class does not declare this requested key/tag.");object proposed=requested["value"];if(tag==1){var normalized=new Dictionary<string,object>(Map(proposed));int count=0;foreach(object row in (IEnumerable)normalized["rows"])count++;normalized["row_count"]=count;proposed=normalized;}match["value"]=proposed;}
     NativeMemory.Require(api.Engine.Virtual(obj,5)==setterAddress,"Created native setter differs from prepared class entry.");NativeOperationTrace.BeforeMutation("native-control-created-typed-properties");dispatcher.Invoke(delegate(IntPtr sink){setter(obj,sink);});
     using(var collector=new NativeTypedPropertyCollector(api.Engine))NativePageControlPreparation.Same(expected,collector.Read(obj),"Created typed property postimage or untouched component values differ.");
    }
    if(view!=IntPtr.Zero&&batch==null){NativeOperationTrace.BeforeMutation("native-control-created-invalidate");invalidate(view,1);NativeOperationTrace.BeforeMutation("native-control-created-update");update(view);}
    var afterNodes=api.Forest(doc);var previous=new List<object>();foreach(object row in (IEnumerable)history.AfterStoreSnapshot(before["target_forest"]))previous.Add(row);var retained=new List<object>();Node added=null;
    foreach(Node node in afterNodes){if(node.Full==created){NativeMemory.Require(added==null,"Created native object repeats in its ownership list.");added=node;}else retained.Add(Snapshot(api,node));}
    NativeMemory.Require(added!=null&&afterNodes.Count==previous.Count+1,"Factory did not add exactly one root control.");NativePageControlPreparation.Same(previous,retained,"Native factory altered an existing destination control/subtree.");NativePageControlPreparation.Same(attributes,api.Shared.Attributes(doc),"Native factory altered page attributes.");
    if(batch!=null)batch.RecordApplied();lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind","control-native-create"},{"created",Snapshot(api,added)},{"native_factory_called",false},{"runtime_class_load_constructor_called",false},{"original_placement_allocator_called",true},{"original_placement_constructor_called",true},{"constructor_initialized_serialized_flags",new Dictionary<string,object>{{"field_58_raw_uint32",initialized58},{"field_5C_raw_uint32",initialized5C}}},{"class_specific_defaults_reason",6},{"native_history_store_projection",history.Report()},{"full_persistence_acceptance_pending",true}};
   }
   [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void SetterForFactory(IntPtr self,IntPtr dispatcher);
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease) {
    NativeMemory.Require(applied&&!disposed,"Native factory Apply must precede Flush.");NativeMemory.Require(batch==null||batch.completed,"Complete the factory batch before explicit page save.");lease.BeginFlush(action);api.Shared.Current();int dirty=NativeMemory.I32(doc,0x48);NativeMemory.Require(dirty==0||dirty==1,"Native factory page dirty state differs.");
    if(dirty==1){NativeOperationTrace.BeforeMutation("native-control-created-page-save-data");NativeMemory.Require(save(api.Context.WindowService,page)&&NativeMemory.I32(doc,0x48)==0,"Native created-control page saveData did not clean its document.");}lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"root_save_called",false}};
   }
   public void Dispose(){if(disposed)return;disposed=true;try{if(dispatcher!=null){dispatcher.Dispose();dispatcher=null;}}finally{if(rectBuffer!=IntPtr.Zero){Marshal.FreeHGlobal(rectBuffer);rectBuffer=IntPtr.Zero;}}}
  }
 }
}
