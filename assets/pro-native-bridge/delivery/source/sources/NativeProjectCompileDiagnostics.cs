// Raw-only existing error state. Never compiles, clears errors or invokes a vendor getter.
using System;using System.Collections;using System.Collections.Generic;using System.Globalization;using System.IO;using System.Runtime.InteropServices;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeProjectCompileDiagnostics {
  internal const string Kind="project-compile-diagnostics";
  internal const string ProfileSha="387b158d0cdb5cb525c02609c64058e0c5f2a933481ac3c8e1a73e7c30647b5c";
  static Dictionary<string,object> M(object value){return(Dictionary<string,object>)value;}
  static int N(object value){return NativeEngine.Number(value);}
  static string C(IntPtr value){return NativeUsableEditPermit.ReadCurrentCString(value,131072);}
  static string H(byte[] value){return BitConverter.ToString(value).Replace("-","").ToLowerInvariant();}
  static void Primary(NativeEngine e,IntPtr full,Dictionary<string,object> table){
   IntPtr vt=e.Address(N(table["vtable_rva"])),col=e.Address(N(table["col_rva"])),td=e.Address(N(table["type_descriptor_rva"]));
   NativeMemory.Require(full!=IntPtr.Zero&&NativeMemory.Ptr(full,0)==vt&&NativeMemory.Ptr(vt,-4)==col&&NativeMemory.I32(col,4)==0&&NativeMemory.Ptr(col,12)==td&&NativeMemory.Ascii(NativeMemory.Add(td,8),160)==Convert.ToString(table["rtti"]),"Compile diagnostic raw class/COL/RTTI differs.");
  }
  static Dictionary<string,object> Capture(NativeEngine e,NativeContext context,string project,Dictionary<string,object> action,Dictionary<string,object> profile){
   NativeMemory.Require(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&EngineEntry.ExpectedUiThreadId==NativeMemory.GetCurrentThreadId(),"Compile diagnostic is outside the captured x86 UI thread.");
   var target=M(action["target"]);NativeMemory.Require(Convert.ToString(action["kind"])==Kind&&target.ContainsKey("page_id")&&target.ContainsKey("page_name")&&target.Count==2,"Compile diagnostic needs only the exact page_id/page_name target.");
   int id=N(target["page_id"]);string name=Convert.ToString(target["page_name"]);NativeMemory.Require(id>=0&&!String.IsNullOrEmpty(name),"Compile diagnostic target identity is empty.");
   var tables=M(profile["tables"]);IntPtr app=e.Address(0xFBB578);Primary(e,app,M(tables["app"]));IntPtr root=NativeMemory.Ptr(app,0x520);Primary(e,root,M(tables["root"]));
   NativeMemory.Require(NativeMemory.Ptr(root,0x2D4)==context.ObjectModel&&Path.GetFullPath(C(NativeMemory.Add(root,0x24))).Equals(Path.GetFullPath(project),StringComparison.OrdinalIgnoreCase)&&Path.GetFullPath(project).Equals(NativeUsableEditPermit.Fixture,StringComparison.OrdinalIgnoreCase),"Compile diagnostic current project/root/model identity differs.");
   e.RequireTable(context.WindowManager,"UserWindowObjectManager.IObject");e.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");NativeMemory.Require(NativeMemory.Add(context.WindowManager,0x34)==context.WindowService,"Compile diagnostic window service/manager ownership differs.");
   IntPtr map=NativeMemory.Add(context.WindowManager,12),head=NativeMemory.Ptr(map,0);int count=NativeMemory.I32(map,4);string header=H(NativeMemory.Bytes(map,8));NativeMemory.Require(head!=IntPtr.Zero&&count>=0&&count<=4096,"Compile diagnostic raw page map head/count differs.");
   IntPtr previous=head,node=NativeMemory.Ptr(head,0),page=IntPtr.Zero;var nodes=new HashSet<uint>();var ids=new HashSet<int>();
   for(int i=0;i<count;i++){NativeMemory.Require(node!=IntPtr.Zero&&node!=head&&nodes.Add(NativeMemory.U(node))&&NativeMemory.Ptr(node,4)==previous,"Compile diagnostic raw page map cycle/link differs.");IntPtr candidate=NativeMemory.Ptr(node,12);Primary(e,candidate,M(tables["page"]));int current=NativeMemory.I32(candidate,16);NativeMemory.Require(ids.Add(current),"Compile diagnostic raw page IDs repeat.");if(current==id)page=candidate;previous=node;node=NativeMemory.Ptr(node,0);}
   NativeMemory.Require(node==head&&NativeMemory.Ptr(head,4)==previous&&header==H(NativeMemory.Bytes(map,8))&&page!=IntPtr.Zero,"Compile diagnostic page map changed or target is absent.");
   string pageName=C(NativeMemory.Add(page,12));NativeMemory.Require(pageName==name,"Compile diagnostic actual target page name differs.");IntPtr doc=NativeMemory.Ptr(page,20);NativeMemory.Require(doc!=IntPtr.Zero,"Compile diagnostic requires an already-loaded page; no lazy load.");Primary(e,doc,M(tables["document"]));NativeMemory.Require(NativeMemory.I32(doc,0x258)==id,"Compile diagnostic loaded document owner/page ID differs.");
   string documentName=C(NativeMemory.Add(doc,0x25C));return new Dictionary<string,object>{
    {"root",NativeMemory.Hex(root)},{"object_model",NativeMemory.Hex(context.ObjectModel)},{"project_path",C(NativeMemory.Add(root,0x24))},
    {"existing_error_owner_string1C8",C(NativeMemory.Add(root,0x1C8))},{"existing_error_text_string1CC",C(NativeMemory.Add(root,0x1CC))},{"existing_error_code1D0_raw_uint32",unchecked((uint)NativeMemory.I32(root,0x1D0))},
    {"page_id",id},{"page_name",pageName},{"page",NativeMemory.Hex(page)},{"document",NativeMemory.Hex(doc)},
    {"document_name_string25C",documentName},{"document_name_matches_page_name",documentName==pageName},{"document_compile114_raw_uint32",unchecked((uint)NativeMemory.I32(doc,0x114))}};
  }
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext context,string project,Dictionary<string,object> action){
   string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"project-services-prep","project-compile-diagnostics-abi-profile.json");NativeMemory.Require(File.Exists(file)&&(File.GetAttributes(file)&(FileAttributes.Directory|FileAttributes.ReparsePoint))==0&&NativeMemory.Hash(file)==ProfileSha,"Compile diagnostic ABI profile differs.");
   var profile=new JavaScriptSerializer{MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,System.Text.Encoding.UTF8));NativeMemory.Require(Convert.ToString(profile["binary_sha256"])==e.ImageSha256,"Compile diagnostic loaded editor image differs.");
   foreach(object value in(IEnumerable)profile["guards"]){var row=M(value);string hex=Convert.ToString(row["bytes"]);byte[] bytes=new byte[hex.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);foreach(object valueOffset in(IEnumerable)row["reloc_offsets"]){int at=N(valueOffset);NativeMemory.Require(at>=0&&at+4<=bytes.Length,"Compile diagnostic guard HIGHLOW crosses its exact prefix.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(bytes,at)+NativeMemory.U(e.ImageBase)-0x400000U)),0,bytes,at,4);}NativeMemory.Require(H(bytes)==H(NativeMemory.Bytes(e.Address(N(row["rva"])),bytes.Length)),"Original compile diagnostic writer/return code differs: "+Convert.ToString(row["name"]));}
   var before=Capture(e,context,project,action,profile);var after=Capture(e,context,project,action,profile);NativeMemory.Require(NativeUsableEditPermit.Json(before)==NativeUsableEditPermit.Json(after),"Existing compile error/page diagnostic changed between two raw reads; no atomic snapshot is claimed.");
   return new Dictionary<string,object>{{"abi_profile_sha256",ProfileSha},{"kind",Kind},{"state",after},{"raw_repeat_equal",true},{"raw_repeat_is_atomic_snapshot",false},{"error_age_or_causal_branch_inferred",false},{"native_getter_generate_F4_serializer_or_error_clear_called",false},{"native_write_attempted",false}};
  }
 }
}
