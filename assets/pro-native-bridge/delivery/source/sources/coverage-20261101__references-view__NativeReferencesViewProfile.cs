// Read-only protocol: current captured native objects, reference presence and drawing view.
// Does not invoke engineering mutations, modal commands, refresh, undo/redo or save.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
 internal static class NativeReferencesViewProfile {
  const string ProfileSha="17080ee4b19020f46c1547640ea6b72a5269eda5df2086e82d3e3e8a0007f4b6";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr P0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr PP(IntPtr self,IntPtr value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Query(IntPtr self,IntPtr target,IntPtr firstReference);
  static string Hex(byte[] bytes){return BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant();}
  static Dictionary<string,object> Load(string path){return new JavaScriptSerializer{MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));}
  sealed class Api {
   internal readonly NativeEngine Engine;internal readonly NativeContext Context;internal readonly NativeStrategyProfile.Api Shared;
   internal readonly Dictionary<string,object> Profile;internal readonly IntPtr Root;
   readonly Dictionary<string,IntPtr> methods=new Dictionary<string,IntPtr>();readonly IntPtr identity;readonly string identityBytes;
   internal Api(NativeEngine engine,NativeContext context){
    Engine=engine;Context=context;Shared=new NativeStrategyProfile.Api(engine);
    string file=Path.Combine(NativeOperations.TaskRoot,"coverage-20261101","references-view","references-view-abi-profile.json");NativeMemory.Require(NativeMemory.Hash(file)==ProfileSha,"References/view ABI profile differs.");Profile=Load(file);
    NativeMemory.Require(Convert.ToInt32(Profile["schema"])==1 && Convert.ToString(Profile["binary_sha256"])==engine.ImageSha256,"References/view installed image differs.");uint preferred=unchecked((uint)NativeEngine.Number(Profile["preferred_base"]));
    foreach(object value in (IEnumerable)Profile["functions"]){var f=(Dictionary<string,object>)value;string h=Convert.ToString(f["bytes"]);byte[] b=new byte[h.Length/2];for(int i=0;i<b.Length;i++)b[i]=Byte.Parse(h.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);foreach(object relocation in (IEnumerable)f["reloc_offsets"]){int at=Convert.ToInt32(relocation);NativeMemory.Require(at>=0 && at+4<=b.Length,"References/view prefix relocation is incomplete.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(b,at)+NativeMemory.U(engine.ImageBase)-preferred)),0,b,at,4);}IntPtr address=engine.Address(NativeEngine.Number(f["rva"]));NativeMemory.Require(Hex(NativeMemory.Bytes(address,b.Length))==Hex(b),"References/view native prefix differs: "+f["name"]);methods.Add(Convert.ToString(f["name"]),address);}
    identity=methods["GetAfxApp"];identityBytes=Hex(NativeMemory.Bytes(identity,32));Root=Shared.RootDoc();Current();Engine.RequireTable(context.ObjectModel,"ObjectModel");
    var proof=(Dictionary<string,object>)Profile["tree_proof"];string treefile=Path.GetFullPath(Convert.ToString(proof["file"])),task=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";
    NativeMemory.Require(treefile.StartsWith(task,StringComparison.OrdinalIgnoreCase) && NativeMemory.Hash(treefile)==Convert.ToString(proof["sha256"]),"Captured native tree file/hash differs.");var tree=Load(treefile);
    NativeMemory.Require(Convert.ToBoolean(tree["ok"]) && !Convert.ToBoolean(tree["write_attempted"]) && Convert.ToInt32(tree["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(tree["native_thread_id"])==EngineEntry.ExpectedUiThreadId && Convert.ToInt32(proof["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(proof["ui_thread_id"])==EngineEntry.ExpectedUiThreadId,"Captured native object identities belong to another live session.");
   }
   internal void Current(){NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"References/view requires captured x86 UI thread.");NativeMemory.Require(Shared.AddressOf("GetAfxApp")==identity && Hex(NativeMemory.Bytes(identity,32))==identityBytes && Shared.RootDoc()==Root && NativeMemory.Ptr(Root,0x2D4)==Context.ObjectModel,"References/view current getter/root/model differs.");string path=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(Root,0x24),2048),fixture=NativeEngineeringProjectScope.ExpectedProjectPath;NativeMemory.Require(!String.IsNullOrEmpty(path) && Path.GetFullPath(path).Equals(fixture,StringComparison.OrdinalIgnoreCase),"References/view requires current isolated fixture.");}
   internal T Bind<T>(string name)where T:class{Current();return Engine.Bind<T>(methods[name]);}
   internal IntPtr Target(Dictionary<string,object> value){Current();IntPtr p=new IntPtr(unchecked((int)Convert.ToUInt32(Convert.ToString(value["address"]).Substring(2),16)));var actual=Engine.Describe(p);NativeMemory.Require(Convert.ToString(actual["rtti"])==Convert.ToString(value["rtti"]) && Convert.ToInt32(actual["complete_offset"])==Convert.ToInt32(value["complete_offset"]) && Convert.ToInt32(actual["module"])==Convert.ToInt32(value["module"]) && NativeMemory.Ptr(p,0)==Engine.Address(NativeEngine.Number(value["vtable_rva"])) && NativeStrategyProfile.ReadName(Shared,p)==Convert.ToString(value["name"]),"Captured native target identity/type/name changed.");NativeMemory.Require(NativeStrategyProfile.ReadId(Shared,p)==Convert.ToInt32(value["native_identity_id"]),"Captured native identity getter changed.");return p;}
  }
  sealed class PathValue:IDisposable {
   readonly Api api;internal readonly IntPtr Storage;bool valid;
   internal PathValue(Api value,IntPtr obj){api=value;Storage=Marshal.AllocHGlobal(4);Marshal.WriteInt32(Storage,0);try{NativeMemory.Require(api.Bind<PP>("ObjectPath")(obj,Storage)==Storage,"Native object path sret differs.");valid=true;NativeMemory.Require(Text.Length>0,"Native object path empty.");}catch{Dispose();throw;}}
   internal string Text{get{return NativeStrategyProfile.ReadBorrowedCString(Storage,2048);}}
   public void Dispose(){try{if(valid){valid=false;api.Shared.Bind<Void0>("CStringDtor")(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
   [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Void0(IntPtr self);
  }
  internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context){
   var api=new Api(engine,context);int rootBefore=api.Shared.Bind<I0>("RootIsModified")(api.Root),compileBefore=NativeMemory.I32(api.Root,0x114);var values=new List<object>();IntPtr ownPage=IntPtr.Zero;
   foreach(object row in (IEnumerable)api.Profile["targets"]){var target=(Dictionary<string,object>)row;IntPtr obj=api.Target(target);if(Convert.ToString(target["role"])=="owned_page31")ownPage=obj;
    using(var path=new PathValue(api,obj))using(var first=new NativeStrategyProfile.CString(api.Shared,"")){int status=api.Bind<Query>("ReferencePresence")(context.ObjectModel,path.Storage,first.Storage);string firstPath=NativeStrategyProfile.ReadBorrowedCString(first.Storage,2048);NativeMemory.Require(status>=0 && status<=2 && ((status==0 && firstPath.Length==0)||(status>0 && firstPath.Length>0)),"Native reference status/first-linker output differs.");values.Add(new Dictionary<string,object>{{"role",target["role"]},{"name",target["name"]},{"object",NativeMemory.Hex(obj)},{"target_linker",path.Text},{"reference_status_code",status},{"has_external_reference",status!=0},{"first_reference_linker",firstPath},{"reference_count_claimed",false}});}}
   NativeMemory.Require(ownPage!=IntPtr.Zero && api.Bind<I0>("PageArchiveId")(ownPage)==31,"Owned page archive ID differs.");IntPtr doc=NativeMemory.Ptr(ownPage,0x14);NativeMemory.Require(NativeMemory.Ptr(doc,0)==engine.Address(0xDC4D94) && NativeMemory.I32(doc,0x258)==31 && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x25C),256)=="Codex控件接口试验","Owned loaded page document differs.");
   int pageBefore=api.Shared.Bind<I0>("RootIsModified")(doc);IntPtr view=api.Bind<P0>("GetDrawingView")(doc);string rtti="";bool viewDoc=false;
   if(view!=IntPtr.Zero){IntPtr vt=NativeMemory.Ptr(view,0),col=NativeMemory.Ptr(vt,-4),td=NativeMemory.Ptr(col,12);engine.Rva(vt);engine.Rva(col);engine.Rva(td);NativeMemory.Require(NativeMemory.I32(col,4)==0 && vt==engine.Address(0xD9041C),"Current native drawing-view primary type differs.");rtti=NativeMemory.Ascii(NativeMemory.Add(td,8),128);NativeMemory.Require(rtti==".?AVC0VwDraw@@","Current drawing-view RTTI differs.");viewDoc=api.Bind<P0>("DrawingViewGetDocument")(view)==doc;NativeMemory.Require(viewDoc,"Drawing view belongs to another native document.");}
   int rootAfter=api.Shared.Bind<I0>("RootIsModified")(api.Root),pageAfter=api.Shared.Bind<I0>("RootIsModified")(doc),compileAfter=NativeMemory.I32(api.Root,0x114);NativeMemory.Require(rootBefore==rootAfter && pageBefore==pageAfter && compileBefore==compileAfter,"Read-only reference/view inspection changed dirty/compile flags.");
   return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"references",values},{"native_reference_query_status_is_not_a_count",true},{"page_id",31},{"page_document",NativeMemory.Hex(doc)},{"view_present",view!=IntPtr.Zero},{"view",NativeMemory.Hex(view)},{"view_rtti",rtti},{"view_document_matches",viewDoc},{"root_modified_before",rootBefore},{"root_modified_after",rootAfter},{"page_modified_before",pageBefore},{"page_modified_after",pageAfter},{"compile_valid_before",compileBefore},{"compile_valid_after",compileAfter},{"dirty_compile_state_unchanged",true},{"undo_metadata_available",false},{"undo_availability","not_yet_statically_proven"},{"undo_or_redo_called",false},{"refresh_or_save_called",false},{"rename_or_delete_called",false},{"abi_guard_sha256",ProfileSha}};
  }
 }
}
