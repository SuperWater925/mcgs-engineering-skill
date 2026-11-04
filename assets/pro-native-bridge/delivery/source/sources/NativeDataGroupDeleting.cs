// Direct original group deletion. Member variables remain independently module-owned.
// Candidate only: consolidated native acceptance is still required.
using System;using System.Collections;using System.Collections.Generic;using System.IO;
using System.Runtime.InteropServices;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeDataGroupDeleting {
  internal const string Kind="data-group-delete",AbiProfileSha="a27414f31ef574b0fb1de51516642cf7a89a99583ee64393781dcb569d1bd454";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr PP(IntPtr self,IntPtr value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VI(IntPtr self,int value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int RefCheck(IntPtr self,IntPtr path,IntPtr first);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool BP(IntPtr self,IntPtr value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool B0(IntPtr self);
  static Dictionary<string,object> M(object value){return NativePageControlPreparation.Map(value);}
  static int N(Dictionary<string,object> row,string key){return NativePageControlPreparation.Number(row,key);}
  static string S(Dictionary<string,object> row,string key){return NativePageControlPreparation.Text(row,key);}
  static void Need(bool value,string why){NativeMemory.Require(value,why);}
  static void Same(object wanted,object actual,string why){NativePageControlPreparation.Same(wanted,actual,why);}
  static bool Under(string path,string parent){return path==parent||path.StartsWith(parent+".",StringComparison.Ordinal);}
  static List<object> L(object input){var result=new List<object>();foreach(object value in(IEnumerable)input)result.Add(value);return result;}
  static void Contract(NativeDataEngineering.Api api){
   string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"data-recipe-device-prep","data-group-delete-abi-profile.json");
   Need(NativeMemory.Hash(file)==AbiProfileSha,"Native group-delete ABI contract differs.");
   var profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));
   Need(S(profile,"base_data_recipe_abi_sha256")==NativeDataEngineering.AbiProfileSha&&S(profile,"binary_sha256")==api.Engine.ImageSha256,"Native group-delete base/image differs.");
   Need(NativeMemory.Hash(Path.Combine(Path.GetDirectoryName(file),"data-group-delete-static-source.json"))==S(profile,"static_source_sha256"),"Native group-delete source proof differs.");
   api.Current();api.Table(api.DataService,"DataService");api.Check("DataDeleteIndices");
   Need(api.Engine.Virtual(api.DataService,8)==api.Engine.Address(0x45453),"Original group delete is not the exact original selected-index service slot.");
  }
  sealed class PathValue:IDisposable {
   internal readonly IntPtr Storage;readonly V0 destroy;bool valid,disposed;
   internal PathValue(NativeDataEngineering.Api api,IntPtr io){destroy=api.Shared.Bind<V0>("CStringDtor");var path=api.Bind<PP>("ObjectPath");Storage=Marshal.AllocHGlobal(4);Marshal.WriteInt32(Storage,0);try{Need(path(io,Storage)==Storage,"Native group path sret differs.");valid=true;Need(NativeUsableEditPermit.ReadCurrentCString(Storage,32768).Length>0,"Native group path is empty.");}catch{Dispose();throw;}}
   public void Dispose(){if(disposed)return;disposed=true;try{if(valid){valid=false;destroy(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
  }
  static Dictionary<string,object> Capture(NativeDataEngineering.Api api,NativeReferencedPageEditing.Api graphApi,Dictionary<string,object> action,RefCheck check){
   Contract(api);var target=M(action["target"]);Need(S(action,"kind")==Kind&&target.Count==3&&N(target,"module_id")==2,"Group delete needs the exact module/name/native ID target.");
   IntPtr group=api.Data(target);Need(NativeMemory.I32(group,0x14)==-1&&NativeMemory.Ptr(group,4)==api.DataManager,"Group delete target is not the actual module-owned native group.");
   var catalog=NativeDataLogicalCatalog.Data(api);Dictionary<string,object> record=null;foreach(var row in catalog)if(N(row,"native_id")==N(target,"native_id"))record=row;Need(record!=null,"Group disappeared from its full owner catalog.");
   string path;int status;using(var nativePath=new PathValue(api,group))using(var first=new NativeStrategyProfile.CString(api.Shared,"")){path=NativeUsableEditPermit.ReadCurrentCString(nativePath.Storage,32768);status=check(api.Context.ObjectModel,nativePath.Storage,first.Storage);}
   Need(status>=0&&status<=2,"Original group incoming-reference status is outside its contract.");
   var graph=NativeReferencedPageEditing.Graph(graphApi);var members=new List<object>();var memberNames=L(record["member_names"]);var memberIds=L(record["cached_member_ids"]);
   Need(memberNames.Count==memberIds.Count,"Native group member names/ID cache lengths differ.");
   for(int i=0;i<memberNames.Count;i++){Dictionary<string,object> member=null;foreach(var row in catalog)if(S(row,"name")==Convert.ToString(memberNames[i]))member=row;Need(member!=null&&N(member,"native_id")==Convert.ToInt32(memberIds[i])&&N(member,"native_id")!=N(record,"native_id"),"Native group contains a missing/aliased member identity.");members.Add(member);}
   return new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"kind",Kind},{"module_id",2},{"record",record},{"data_catalog",catalog},{"recipe_catalog",NativeDataLogicalCatalog.Recipes(api)},{"group_path",path},{"incoming_reference_status",status},{"reference_graph",graph},{"independently_owned_members",members},{"next_native_id",NativeMemory.I32(api.DataManager,0x38)},{"module_dirty",(int)Marshal.ReadByte(api.DataManager,0x94)},{"claim_preimage_uses_serialize",false}};
  }
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){var api=new NativeDataEngineering.Api(e,c,project);var graph=new NativeReferencedPageEditing.Api(e,c,project);return Capture(api,graph,action,api.Bind<RefCheck>("ReferenceCheck"));}
  internal static Prepared Prepare(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new Prepared(new NativeDataEngineering.Api(e,c,project),new NativeReferencedPageEditing.Api(e,c,project),action);}
  internal sealed class Prepared:INativePreparedPageControlEdit {
   readonly NativeDataEngineering.Api api;readonly NativeReferencedPageEditing.Api graphApi;readonly Dictionary<string,object> action,before;
   readonly RefCheck check;readonly BP remove;readonly VI rootDirty,dataDirty;readonly V0 refresh;readonly B0 save;
   readonly List<object> remaining=new List<object>();readonly List<string> expectedEdges=new List<string>();
   readonly IntPtr indices,oneIndex;bool applied,failed,disposed;string phase="prepared";
   internal Prepared(NativeDataEngineering.Api value,NativeReferencedPageEditing.Api references,Dictionary<string,object> request){api=value;graphApi=references;action=request;Need(S(action,"abi_profile_sha256")==AbiProfileSha,"Group delete action ABI differs.");
    check=api.Bind<RefCheck>("ReferenceCheck");remove=api.Bind<BP>("DataDeleteIndices");rootDirty=api.Shared.Bind<VI>("RootSetModified");dataDirty=api.Bind<VI>("DataSetDirty");refresh=api.Bind<V0>("DataRefresh");save=api.Bind<B0>("DataSave");api.Bind<PP>("ObjectPath");api.Shared.Bind<V0>("CStringDtor");
    before=Capture(api,graphApi,action,check);NativePageControlPreparation.Before(action,before);var after=M(action["after"]);Need(after.Count==1&&after.ContainsKey("exists")&&Object.Equals(after["exists"],false),"Group delete requires exists=false; no implicit member or type conversion operation is accepted.");Need(N(before,"incoming_reference_status")==0,"Referenced group deletion requires the original explicit reference-redirection workflow first.");
    int id=N(M(before["record"]),"native_id");foreach(object row in L(before["data_catalog"]))if(N(M(row),"native_id")!=id)remaining.Add(row);string path=S(before,"group_path");
    foreach(object valueEdge in L(M(before["reference_graph"])["edges"])){var edge=M(valueEdge);string source=S(edge,"source"),target=S(edge,"target");Need(!Under(target,path)||Under(source,path),"Complete registered graph still has an external group consumer.");if(!Under(source,path))expectedEdges.Add(source+"\0"+target);}expectedEdges.Sort(StringComparer.Ordinal);
    indices=Marshal.AllocHGlobal(12);try{oneIndex=Marshal.AllocHGlobal(4);Marshal.WriteInt32(indices,oneIndex.ToInt32());Marshal.WriteInt32(indices,4,NativeMemory.Add(oneIndex,4).ToInt32());Marshal.WriteInt32(indices,8,NativeMemory.Add(oneIndex,4).ToInt32());api.Freeze();ValidateBefore();}catch{Dispose();throw;}
   }
   public void ValidateBefore(){Need(!disposed&&!failed&&!applied,"Group delete is disposed/failed/already applied.");Same(before,Capture(api,graphApi,action,check),"Group deletion owner/catalog/member/consumer preimage changed.");api.GuardDataList();}
   void Step(string name){phase=name;NativeOperationTrace.BeforeMutation("usable-data-group-delete-"+name);}
   void Verify(){Same(remaining,NativeDataLogicalCatalog.Data(api),"Original group delete changed a member/foreign definition, ownership, ID or metadata.");Same(before["recipe_catalog"],NativeDataLogicalCatalog.Recipes(api),"Original group delete changed a recipe definition/cell.");Need(NativeMemory.I32(api.DataManager,0x38)==N(before,"next_native_id"),"Original group deletion changed the native allocator.");var actual=new List<string>();foreach(object valueEdge in L(NativeReferencedPageEditing.Graph(graphApi)["edges"])){var edge=M(valueEdge);actual.Add(S(edge,"source")+"\0"+S(edge,"target"));}actual.Sort(StringComparer.Ordinal);Same(expectedEdges,actual,"Original group deletion changed a registered edge outside the deleted group.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);try{IntPtr target=api.Data(M(action["target"]));var owned=api.DataObjects();int index=owned.IndexOf(target);Need(index>=0,"Native group index is absent.");Marshal.WriteInt32(oneIndex,index);Step("root-dirty");rootDirty(api.Root,1);Marshal.WriteInt32(api.Root,0x114,0);lease.RequireApplying(action);api.Check("DataDeleteIndices");Step("original-selected-index-worker");bool returned=remove(api.DataService,indices);target=IntPtr.Zero;Need(returned,"Original group deletion did not return success; no retry/rollback.");Verify();api.Check("DataSetDirty");Step("module-dirty");dataDirty(api.DataService,1);api.Check("DataRefresh");Step("original-list-refresh");refresh(api.DataService);api.GuardDataList();Verify();applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",Kind},{"deleted_native_id",N(M(before["record"]),"native_id")},{"deleted_name",S(M(before["record"]),"name")},{"member_variables_deleted",false},{"remaining_full_known_catalog_equal",true},{"native_type_conversion_called",false},{"target_pointer_read_after_delete",false},{"native_save_called",false},{"unified_acceptance_pending",true}};}catch{failed=true;NativeOperationTrace.SetPhase("usable-data-group-delete-failed-"+phase);throw;}}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){Need(applied&&!disposed&&!failed,"Group delete Apply must complete before Flush.");lease.BeginFlush(action);try{lease.RequireModulePersistence(action,2);api.Current();Verify();byte dirty=Marshal.ReadByte(api.DataManager,0x94);Need(dirty<=1,"Data dirty byte is outside its native domain.");bool called=false;if(dirty==1){api.Check("DataSave");Step("original-module-save");called=true;Need(save(api.DataService)&&Marshal.ReadByte(api.DataManager,0x94)==0,"Original group module save did not return/clear dirty.");}Verify();lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"native_module_save_called",called},{"root_save_called",false},{"disk_acceptance_pending",true}};}catch{failed=true;throw;}}
   public void Dispose(){if(disposed)return;disposed=true;if(oneIndex!=IntPtr.Zero)Marshal.FreeHGlobal(oneIndex);if(indices!=IntPtr.Zero)Marshal.FreeHGlobal(indices);}
  }
 }
}
