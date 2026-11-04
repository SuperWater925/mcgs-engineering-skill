// Offline ABI research: additional source only. Root owns the session/write authorization and final save.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class NativePageExtensionProfile {
        internal const string TargetName="Codex控件接口试验";
        const int PageTable=0xDED294,DocTable=0xDC4D94,ListTable=0xDBD7E4,FrameTable=0xDBC034;
        static int createAttempted;
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Void0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Int0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool Rename(IntPtr self,IntPtr oldName,IntPtr newName);

        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeStrategyProfile.Api Existing;
            internal readonly Dictionary<string,object> Profile;
            readonly Dictionary<string,IntPtr> functions=new Dictionary<string,IntPtr>();
            internal Api(NativeEngine engine) {
                Engine=engine;Existing=new NativeStrategyProfile.Api(engine);
                NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Page extension requires the captured x86 UI thread.");
                string path=Path.Combine(NativeOperations.TaskRoot,"extensions","page","page-extension-abi-profile.json");
                Profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path));
                NativeMemory.Require(Convert.ToInt32(Profile["schema"])==1 && NativeBinaryIdentity.Observe(Convert.ToString(Profile["binary_sha256"]),engine.ImageSha256,"extensions__page__NativePageExtensionProfile:29:editor"),"Page extension image/profile differs.");
                uint preferred=unchecked((uint)NativeEngine.Number(Profile["preferred_base"]));
                foreach(object value in (IEnumerable)Profile["functions"]) {
                    var row=(Dictionary<string,object>)value;string name=Convert.ToString(row["name"]),hex=Convert.ToString(row["bytes"]);
                    var bytes=new byte[hex.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                    foreach(object offset in (IEnumerable)row["reloc_offsets"]) {
                        int at=Convert.ToInt32(offset);NativeMemory.Require(at>=0 && at+4<=bytes.Length,"Page signature relocation exceeds prefix.");
                        uint current=unchecked(BitConverter.ToUInt32(bytes,at)+NativeMemory.U(engine.ImageBase)-preferred);Array.Copy(BitConverter.GetBytes(current),0,bytes,at,4);
                    }
                    IntPtr address=engine.Address(NativeEngine.Number(row["rva"]));
                    NativeMemory.Require(BitConverter.ToString(NativeMemory.Bytes(address,bytes.Length))==BitConverter.ToString(bytes),"Page extension ABI prefix differs: "+name);functions.Add(name,address);
                }
                engine.RequireTable(contextModel(engine),"ObjectModel");
            }
            IntPtr contextModel(NativeEngine engine){return NativeMemory.Ptr(Existing.RootDoc(),0x2D4);}
            internal T Bind<T>(string name)where T:class{return Marshal.GetDelegateForFunctionPointer(functions[name],typeof(T))as T;}
            internal void Method(IntPtr self,int slot,int thunk){NativeMemory.Require(slot>=0 && slot<=109,"Page virtual slot exceeds derived class range.");IntPtr table=NativeMemory.Ptr(self,0);Engine.Rva(table);NativeMemory.Require(NativeMemory.Ptr(table,slot*4)==Engine.Address(thunk),"Page virtual method differs at "+slot);}
            internal IntPtr Owner(NativeContext context) {
                IntPtr doc=Existing.RootDoc();NativeMemory.Require(NativeMemory.Ptr(doc,0x2D4)==context.ObjectModel,"Page context belongs to another root.");
                IntPtr app=Existing.Bind<NativeEngine.CdeclPointer>("GetAfxApp")();NativeMemory.Require(NativeMemory.Ptr(app,0x520)==doc,"Page owner root changed.");
                IntPtr frame=NativeMemory.Ptr(app,0x524);NativeMemory.Require(NativeMemory.Ptr(frame,0)==Engine.Address(FrameTable),"Page management frame type differs.");
                IntPtr array=NativeMemory.Add(frame,0x314);NativeMemory.Require(NativeMemory.I32(array,8)==5,"Expected five native management lists.");
                IntPtr data=NativeMemory.Ptr(array,4);NativeMemory.Readable(data,20);IntPtr list=NativeMemory.Ptr(data,8);
                NativeMemory.Require(NativeMemory.Ptr(list,0)==Engine.Address(ListTable),"Page manager list type differs.");Method(list,100,0x4AB6);return list;
            }
            internal Dictionary<int,IntPtr> Pages(NativeContext context) {
                var pages=new Dictionary<int,IntPtr>();var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach(IntPtr page in Engine.Children(context.WindowManager)) {
                    NativeMemory.Require(NativeMemory.Ptr(page,0)==Engine.Address(PageTable),"Unexpected native page type.");
                    Method(page,9,0x10825);Method(page,10,0xCEBE);int id=Bind<Int0>("PageArchiveId")(page);string name=NativeStrategyProfile.ReadName(Existing,page);
                    NativeMemory.Require(id>=0 && !pages.ContainsKey(id) && !String.IsNullOrEmpty(name) && names.Add(name),"Page ID/name is empty or repeated.");pages.Add(id,page);
                }
                NativeMemory.Require(pages.Count==Engine.Bind<NativeEngine.ThisInt>(Engine.Virtual(context.WindowManager,19))(context.WindowManager),"Page enumeration count differs.");return pages;
            }
            internal string Name(IntPtr page){return NativeStrategyProfile.ReadName(Existing,page);}
            internal void Context(NativeContext context,string expected) {
                string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
                NativeMemory.Require(Path.GetFullPath(expected).Equals(fixture,StringComparison.OrdinalIgnoreCase) && NativePageDuplicateProfile.CurrentProjectPath(Engine).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Page extension is restricted to the exact isolated fixture.");
                NativeMemory.Require(NativeMemory.Ptr(Existing.RootDoc(),0x2D4)==context.ObjectModel,"Page extension context changed.");Engine.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");Method(context.WindowService,5,0x538AF);
            }
            internal void Baseline(Dictionary<int,IntPtr> actual) {
                var baseline=(Dictionary<string,object>)Profile["baseline"];string path=Convert.ToString(baseline["index"]);
                NativeMemory.Require(NativeMemory.Hash(path)==Convert.ToString(baseline["index_sha256"]),"Prepared page baseline index differs.");
                var index=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path));
                NativeMemory.Require(Convert.ToString(index["sha256"])==Convert.ToString(baseline["project_sha256"]) && actual.Count==12,"Page baseline project/count differs.");
                int count=0;foreach(object value in (IEnumerable)index["rows"]) {
                    var row=(Dictionary<string,object>)value;if(Convert.ToString(row["table"])!="WndUser")continue;
                    int id=Convert.ToInt32(row["iID"]);NativeMemory.Require(row["iDeleteFlag"]!=null && Convert.ToInt32(row["iDeleteFlag"])==0 && actual.ContainsKey(id) && Name(actual[id])==Convert.ToString(row["strName"]),"A baseline page/delete flag differs.");count++;
                }
                NativeMemory.Require(count==12,"Expected12 native user rows with zero delete flags.");
            }
        }
        static List<object> Describe(Api api,Dictionary<int,IntPtr> pages) {
            var output=new List<object>();foreach(var row in pages)output.Add(new Dictionary<string,object>{{"id",row.Key},{"name",api.Name(row.Value)},{"address",NativeMemory.Hex(row.Value)}});return output;
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine);api.Context(context,Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));IntPtr owner=api.Owner(context);var pages=api.Pages(context);
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"owner",NativeMemory.Hex(owner)},{"page_count",pages.Count},{"pages",Describe(api,pages)},{"target_exists",Exists(api,pages,TargetName)},{"create_entry_static_verified",true},{"rename_entry_static_verified",true},{"native_create_executed",false},{"properties_delete_pending",true}};
        }
        static bool Exists(Api api,Dictionary<int,IntPtr> pages,string name){foreach(var page in pages)if(String.Equals(api.Name(page.Value),name,StringComparison.OrdinalIgnoreCase))return true;return false;}
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine);api.Context(context,expected);IntPtr owner=api.Owner(context);var before=api.Pages(context);api.Baseline(before);
            NativeMemory.Require(!Exists(api,before,TargetName),"Dedicated control test page already exists; no retry.");
            var oldNames=new Dictionary<int,string>();foreach(var row in before)oldNames.Add(row.Key,api.Name(row.Value));
            NativeMemory.Require(Interlocked.CompareExchange(ref createAttempted,1,0)==0,"Native new-page trial was already attempted in this engine revision.");
            bool attempted=false;string phase="native-page-create";
            try {
                attempted=true;NativeOperationTrace.BeforeMutation(phase);NativeStrategyProfile.MarkRootDirty(api.Existing);api.Bind<Void0>("PageNew")(owner);
                var after=api.Pages(context);NativeMemory.Require(after.Count==before.Count+1,"Native new-page method did not add exactly one page; no retry.");
                int newId=-1;IntPtr created=IntPtr.Zero;
                foreach(var row in after) {
                    if(before.ContainsKey(row.Key)){NativeMemory.Require(row.Value==before[row.Key] && api.Name(row.Value)==oldNames[row.Key],"An existing page identity changed during new-page creation.");continue;}
                    NativeMemory.Require(created==IntPtr.Zero && row.Key>30,"New native page ID is not one unique fresh fixture ID.");newId=row.Key;created=row.Value;
                }
                NativeMemory.Require(created!=IntPtr.Zero && engine.Children(created).Count==0,"New native page is absent or not blank.");
                IntPtr doc=NativeMemory.Ptr(created,0x14);NativeMemory.Require(NativeMemory.Ptr(doc,0)==engine.Address(DocTable) && NativeMemory.I32(doc,0x258)==newId,"New native page/document identity differs.");
                string generated=api.Name(created);phase="native-page-rename";NativeOperationTrace.SetPhase(phase);
                using(var oldName=new NativeStrategyProfile.CString(api.Existing,generated))using(var newName=new NativeStrategyProfile.CString(api.Existing,TargetName)) {
                    NativeOperationTrace.BeforeMutation(phase);NativeMemory.Require(api.Bind<Rename>("WindowServiceRename")(context.WindowService,oldName.Storage,newName.Storage),"Native window service rename refused the dedicated page.");
                }
                var renamed=api.Pages(context);NativeMemory.Require(renamed.Count==after.Count && renamed.ContainsKey(newId) && renamed[newId]==created && api.Name(created)==TargetName && engine.Children(created).Count==0,"Native page rename readback differs.");
                NativeMemory.Require(NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x25C),256)==TargetName,"Native page document name did not follow the rename.");
                foreach(var row in before)NativeMemory.Require(renamed[row.Key]==row.Value && api.Name(row.Value)==oldNames[row.Key],"An existing page changed during rename.");
                NativeOperationTrace.SetPhase("verified");
                return new Dictionary<string,object>{{"ok",true},{"write_attempted",true},{"native_business_method_called",true},{"phase","new-page-and-rename-readback-complete"},{"page_id",newId},{"page_name",TargetName},{"generated_name_before_rename",generated},{"page_iobject",NativeMemory.Hex(created)},{"loaded_document",NativeMemory.Hex(doc)},{"page_count_before",before.Count},{"page_count_after",renamed.Count},{"control_count",0},{"existing_page_identities_unchanged",true},{"native_new_page_executed",true},{"native_rename_executed",true},{"native_save_verified",false},{"offline_payload_verified",false},{"properties_delete_pending",true}};
            }catch(Exception error){error.Data["write_attempted"]=attempted;error.Data["phase"]=phase;throw;}
        }
    }
}
