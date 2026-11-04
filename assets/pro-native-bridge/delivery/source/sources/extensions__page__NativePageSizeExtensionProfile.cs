// Exact-layout adapter for two native document int32 fields on owned page31 only.
// It is not a generic IObject property setter. No GUI, basic-block jump or fake dialog.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class NativePageSizeExtensionProfile {
        const string ProfileSha="f796de7910b332cde37cfe5ed5bd325063f96600b59dff861a4fc91de612df7f";
        const string PageName="Codex控件接口试验";const int Width=464,Height=248;
        static int attempted;
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr P0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool Save(IntPtr self,IntPtr page);
        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeStrategyProfile.Api Shared;
            readonly Dictionary<string,IntPtr> functions=new Dictionary<string,IntPtr>();
            internal Api(NativeEngine engine) {
                Engine=engine;Shared=new NativeStrategyProfile.Api(engine);NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Page-size adapter requires the captured x86 UI thread.");
                string path=Path.Combine(NativeOperations.TaskRoot,"extensions","page","page-size-abi-profile.json");NativeMemory.Require(NativeMemory.Hash(path)==ProfileSha,"Page-size ABI profile differs.");var profile=Read(path);
                NativeMemory.Require(Convert.ToInt32(profile["schema"])==1 && NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),engine.ImageSha256,"extensions__page__NativePageSizeExtensionProfile:28:editor"),"Page-size editor image differs.");uint preferred=unchecked((uint)NativeEngine.Number(profile["preferred_base"]));
                foreach(object value in (IEnumerable)profile["functions"]) {
                    var row=(Dictionary<string,object>)value;string hex=Convert.ToString(row["bytes"]);byte[] bytes=new byte[hex.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                    foreach(object offset in (IEnumerable)row["reloc_offsets"]){int at=Convert.ToInt32(offset);NativeMemory.Require(at>=0 && at+4<=bytes.Length,"Size ABI relocation exceeds its prefix.");Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(bytes,at)+NativeMemory.U(engine.ImageBase)-preferred)),0,bytes,at,4);}
                    IntPtr address=engine.Address(NativeEngine.Number(row["rva"]));NativeMemory.Require(BitConverter.ToString(NativeMemory.Bytes(address,bytes.Length))==BitConverter.ToString(bytes),"Page-size native prefix differs: "+row["name"]);functions.Add(Convert.ToString(row["name"]),address);
                }
            }
            internal T Bind<T>(string name)where T:class{return Marshal.GetDelegateForFunctionPointer(functions[name],typeof(T))as T;}
            internal static Dictionary<string,object> Read(string path){return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path));}
            internal void Project(NativeContext context,string expected) {
                string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;NativeMemory.Require(Path.GetFullPath(expected).Equals(fixture,StringComparison.OrdinalIgnoreCase) && NativePageDuplicateProfile.CurrentProjectPath(Engine).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Size adapter requires the exact isolated fixture.");
                NativeMemory.Require(NativeMemory.Ptr(Shared.RootDoc(),0x2D4)==context.ObjectModel,"Page-size context changed.");Engine.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");NativeMemory.Require(Engine.Virtual(context.WindowService,12)==Engine.Address(0x21733),"Window saveData entry differs.");
            }
            internal Dictionary<int,IntPtr> Pages(NativeContext context) {
                var result=new Dictionary<int,IntPtr>();foreach(IntPtr page in Engine.Children(context.WindowManager)){NativeMemory.Require(NativeMemory.Ptr(page,0)==Engine.Address(0xDED294),"Page IObject type differs.");int id=Bind<I0>("PageArchiveId")(page);NativeMemory.Require(id>=0 && !result.ContainsKey(id),"Page native IDs repeat.");result.Add(id,page);}NativeMemory.Require(result.Count==13 && result.ContainsKey(31),"Size adapter requires the existing13 pages and owned page31.");return result;
            }
            internal string Name(IntPtr page){return NativeStrategyProfile.ReadName(Shared,page);}
        }
        sealed class Target {internal IntPtr Page,Doc;internal Dictionary<int,IntPtr> Pages;internal Dictionary<int,string> Names;internal string Controls;internal int[] Attributes;}
        static string Json(object value){return new JavaScriptSerializer{MaxJsonLength=2*1024*1024}.Serialize(value);}
        static int[] Attributes(IntPtr doc){var values=new int[17];for(int i=0;i<values.Length;i++)values[i]=NativeMemory.I32(doc,0x268+4*i);return values;}
        static string Controls(Api api,IntPtr page) {
            var rows=new List<object>();var kinds=new Dictionary<string,int>{{".?AVCDrawLabel@@",0},{".?AVCDrawButton@@",0},{".?AVCDrawEdit@@",0}};
            var controls=api.Engine.Children(page);NativeMemory.Require(controls.Count==3,"Size adapter requires exactly the retained label/button/input.");
            foreach(IntPtr obj in controls) {
                var description=api.Engine.Describe(obj);string kind=Convert.ToString(description["rtti"]);NativeMemory.Require(kinds.ContainsKey(kind) && Convert.ToInt32(description["complete_offset"])==4,"Unexpected control type/offset on the owned page.");kinds[kind]++;
                IntPtr complete=NativeMemory.Add(obj,-4);int left=NativeMemory.I32(complete,0x80),top=NativeMemory.I32(complete,0x84),right=NativeMemory.I32(complete,0x88),bottom=NativeMemory.I32(complete,0x8C);
                NativeMemory.Require(left>=0 && top>=0 && right>left && bottom>top && right<=Width && bottom<=Height,"An existing control would fall outside464x248.");
                rows.Add(new Dictionary<string,object>{{"object",NativeMemory.Hex(obj)},{"rtti",kind},{"name",NativeStrategyProfile.ReadName(api.Shared,obj)},{"rectangle",new int[]{left,top,right,bottom}}});
            }
            foreach(int count in kinds.Values)NativeMemory.Require(count==1,"Owned page must have exactly one of each prepared control class.");return Json(rows);
        }
        static Target Locate(Api api,NativeContext context) {
            var pages=api.Pages(context);IntPtr page=pages[31];NativeMemory.Require(api.Name(page)==PageName,"Owned page31 name differs.");var names=new Dictionary<int,string>();foreach(var row in pages)names.Add(row.Key,api.Name(row.Value));
            string controls=Controls(api,page);IntPtr doc=NativeMemory.Ptr(page,0x14);NativeMemory.Require(NativeMemory.Ptr(doc,0)==api.Engine.Address(0xDC4D94) && NativeMemory.I32(doc,0x258)==31 && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x25C),256)==PageName,"Owned loaded document identity differs.");
            NativeMemory.Require(api.Shared.Bind<I0>("RootIsModified")(doc)==0,"Owned page has unflushed edits; establish a fresh checkpoint first.");
            NativeMemory.Require(NativeMemory.Ptr(NativeMemory.Ptr(doc,0),27*4)==api.Engine.Address(0x3A3C8),"Page modified-state virtual entry differs.");
            NativeMemory.Require(api.Bind<P0>("GetUserView")(doc)==IntPtr.Zero,"Owned page already has a native user view; optional resize/refresh path is not included in this adapter.");
            return new Target{Page=page,Doc=doc,Pages=pages,Names=names,Controls=controls,Attributes=Attributes(doc)};
        }
        static void Preserve(Api api,NativeContext context,Target target,bool sized) {
            var current=api.Pages(context);foreach(var row in target.Pages)NativeMemory.Require(current[row.Key]==row.Value && api.Name(row.Value)==target.Names[row.Key],"An existing page identity/name changed during size adaptation.");
            NativeMemory.Require(Controls(api,target.Page)==target.Controls,"A control identity/type/name/rectangle changed during size adaptation.");var values=Attributes(target.Doc);
            for(int i=0;i<values.Length;i++)NativeMemory.Require(values[i]==(sized && i==2?Width:sized && i==3?Height:target.Attributes[i]),"Unexpected native document attribute changed at+0x"+(0x268+4*i).ToString("X"));
            NativeMemory.Require(api.Bind<P0>("GetUserView")(target.Doc)==IntPtr.Zero,"A native user view appeared during size adaptation.");
        }
        static Dictionary<string,object> Proof(Dictionary<string,object> entry) {
            string path=Path.GetFullPath(Convert.ToString(entry["file"])),root=Path.GetFullPath(Path.Combine(NativeOperations.TaskRoot,"extensions"))+Path.DirectorySeparatorChar;
            NativeMemory.Require(path.StartsWith(root,StringComparison.OrdinalIgnoreCase) && NativeMemory.Hash(path)==Convert.ToString(entry["sha256"]),"Page-size proof file/hash differs.");return Api.Read(path);
        }
        static void Session(Api api,Target target,string expected) {
            string path=Path.Combine(NativeOperations.TaskRoot,"extensions","page","page-size-session-baseline.json");NativeMemory.Require(File.Exists(path),"Fresh page-size-session-baseline.json is required before either field is written.");var guard=Api.Read(path);
            NativeMemory.Require(Convert.ToInt32(guard["schema"])==1 && Convert.ToString(guard["purpose"])=="native-owned-page31-size" && Convert.ToInt32(guard["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(guard["ui_thread_id"])==EngineEntry.ExpectedUiThreadId,"Page-size session purpose/process/thread differs.");
            NativeMemory.Require(Path.GetFullPath(Convert.ToString(guard["fixture_path"])).Equals(Path.GetFullPath(expected),StringComparison.OrdinalIgnoreCase),"Page-size session project differs.");
            var index=Proof((Dictionary<string,object>)guard["baseline_index"]);string sourceSha=Convert.ToString(guard["project_sha256"]);NativeMemory.Require(Convert.ToString(index["project_family"])=="Pro" && Convert.ToBoolean(index["source_unchanged"]) && Convert.ToString(index["sha256"])==sourceSha && NativeMemory.Hash(expected)==sourceSha,"Page-size baseline is not the current stable project capture.");
            int hits=0;foreach(object value in (IEnumerable)index["rows"]) {var row=(Dictionary<string,object>)value;if(Convert.ToString(row["table"])!="WndUser" || Convert.ToInt32(row["iID"])!=31)continue;hits++;NativeMemory.Require(Convert.ToString(row["strName"])==PageName && Convert.ToInt32(row["iDeleteFlag"])==0,"Owned page baseline row differs.");var blob=(Dictionary<string,object>)row["lbObjects"];string file=Convert.ToString(blob["file"]),directory=Path.GetDirectoryName(Path.GetFullPath(Convert.ToString(((Dictionary<string,object>)guard["baseline_index"])["file"])));NativeMemory.Require(Path.GetFileName(file)==file && Convert.ToString(blob["sha256"])==Convert.ToString(guard["page_blob_sha256"]) && NativeMemory.Hash(Path.Combine(directory,file))==Convert.ToString(blob["sha256"]),"Owned page full BLOB preimage differs.");}
            var inspection=Proof((Dictionary<string,object>)guard["native_inspection"]);NativeMemory.Require(Convert.ToBoolean(inspection["ok"]) && !Convert.ToBoolean(inspection["write_attempted"]) && Convert.ToInt32(inspection["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(inspection["native_thread_id"])==EngineEntry.ExpectedUiThreadId && Convert.ToInt32(inspection["page_id"])==31 && Convert.ToBoolean(inspection["no_user_view"]) && Convert.ToString(inspection["control_snapshot"])==target.Controls,"Page-size native preflight proof differs.");
            NativeMemory.Require(hits==1 && Convert.ToInt32(guard["width_before"])==target.Attributes[2] && Convert.ToInt32(guard["height_before"])==target.Attributes[3] && Convert.ToInt32(inspection["width"])==target.Attributes[2] && Convert.ToInt32(inspection["height"])==target.Attributes[3],"Page-size exact native preimage differs.");NativeMemory.Require(target.Attributes[2]>0 && target.Attributes[3]>0 && (target.Attributes[2]!=Width || target.Attributes[3]!=Height),"Page is already the requested size or has invalid dimensions.");
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine);api.Project(context,Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));var target=Locate(api,context);
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"page_id",31},{"page_name",PageName},{"page_iobject",NativeMemory.Hex(target.Page)},{"loaded_document",NativeMemory.Hex(target.Doc)},{"width",target.Attributes[2]},{"height",target.Attributes[3]},{"requested_width",Width},{"requested_height",Height},{"no_user_view",true},{"control_count",3},{"control_snapshot",target.Controls},{"other_attributes_snapshot",target.Attributes},{"abi_guard_sha256",ProfileSha},{"internal_field_adapter",true},{"generic_iobject_property_api_claimed",false}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine);api.Project(context,expected);var target=Locate(api,context);Session(api,target,expected);NativeMemory.Require(Interlocked.CompareExchange(ref attempted,1,0)==0,"Page-size adaptation was already attempted in this engine.");
            NativeStrategyProfile.MarkRootDirty(api.Shared);NativeOperationTrace.BeforeMutation("page31-owned-runtime-width464");Marshal.WriteInt32(target.Doc,0x270,Width);NativeOperationTrace.BeforeMutation("page31-owned-runtime-height248");Marshal.WriteInt32(target.Doc,0x274,Height);Preserve(api,context,target,true);
            NativeMemory.Require(NativeMemory.Ptr(NativeMemory.Ptr(target.Doc,0),27*4)==engine.Address(0x3A3C8),"Page modified-state virtual entry differs.");NativeOperationTrace.BeforeMutation("page31-size-doc-set-modified");api.Bind<VInt>("DocSetModified")(target.Doc,1);
            NativeOperationTrace.BeforeMutation("page31-size-native-save-data");bool saved=api.Bind<Save>("WindowSaveData")(context.WindowService,target.Page);NativeMemory.Require(saved && api.Shared.Bind<I0>("RootIsModified")(target.Doc)==0,"Native size saveData did not leave the page clean.");Preserve(api,context,target,true);NativeOperationTrace.SetPhase("page31-size-memory-and-page-flush-verified");
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",true},{"page_id",31},{"page_name",PageName},{"width_before",target.Attributes[2]},{"height_before",target.Attributes[3]},{"width_after",Width},{"height_after",Height},{"control_snapshot_unchanged",true},{"other_17_attribute_fields_unchanged_except_width_height",true},{"no_user_view",true},{"native_page_save_data",saved},{"page_modified_after_flush",0},{"internal_field_adapter",true},{"generic_iobject_property_api_claimed",false},{"pending_root_save",true},{"full_blob_preservation_verified",false},{"native_configuration_check_verified",false},{"reopen_verified",false}};
        }
    }
}
