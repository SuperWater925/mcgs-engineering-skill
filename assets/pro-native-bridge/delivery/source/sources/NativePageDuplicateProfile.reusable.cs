// Exact-build internal ABI evidence is in native-page-duplicate-abi-profile.json.
// Additional source only. This file has no execution/registration/activation entry point.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static partial class NativePageDuplicateProfile {
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr Pointer0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr PointerInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr PointerRef(IntPtr self,ref IntPtr position);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate int SaveDocument(IntPtr self,IntPtr path);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr MemoryFileConstructor(IntPtr self,uint growth);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr ArchiveConstructor(IntPtr self,IntPtr file,uint mode,int bufferSize,IntPtr buffer);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate void Void0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate void VoidInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)] delegate bool BoolPointer(IntPtr self,IntPtr argument);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate void WindowArchive(IntPtr self,int sourceId,IntPtr archive);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr GetModuleHandleW(string name);
        [DllImport("kernel32.dll",EntryPoint="GetProcAddress",ExactSpelling=true)] static extern IntPtr GetProcAddressOrdinal(IntPtr module,IntPtr ordinal);

        const int RootDocVtable=0xD57684,TemplateVtable=0xDBABC4,ControlDocVtable=0xDC4F8C;
        const int MenuViewVtable=0xDCA78C,WindowListVtable=0xDBD7E4,PageVtable=0xDED294,WindowDocumentVtable=0xDC4D94;
        const int ManageFrameVtable=0xDBC034;
        const int FirstDocumentThunk=0xB304EE,NextDocumentThunk=0xB304F4;
        const int SaveDocumentThunk=0x5539E,WindowArchiveThunk=0xE14C;
        static int copyInProgress,copyLoadAttempted;

        sealed class Api {
            internal readonly NativeEngine Engine;
            internal readonly NativeStrategyProfile.Api Strategy;
            readonly Dictionary<string,IntPtr> functions=new Dictionary<string,IntPtr>();
            readonly Dictionary<string,IntPtr> modules=new Dictionary<string,IntPtr>();
            readonly Dictionary<string,uint> preferred=new Dictionary<string,uint>();
            readonly Dictionary<string,int> sizes=new Dictionary<string,int>();

            internal Api(NativeEngine engine) {
                Engine=engine;Strategy=new NativeStrategyProfile.Api(engine);
                NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,
                    "Page ABI requires the captured x86 host UI thread.");
                var json=new JavaScriptSerializer();
                string directory=Path.Combine(NativeOperations.TaskRoot,"static");
                var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"native-page-duplicate-abi-profile.json"),Encoding.UTF8));
                foreach(object row in (IEnumerable)profile["modules"]) {
                    var item=(Dictionary<string,object>)row;string name=Convert.ToString(item["name"]);
                    IntPtr handle=GetModuleHandleW(name);NativeMemory.Require(handle!=IntPtr.Zero,"Page ABI module is not already loaded: "+name);
                    ProcessModule found=null;foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==handle){found=loaded;break;}
                    NativeMemory.Require(found!=null && NativeMemory.Hash(found.FileName)==Convert.ToString(item["sha256"]),"Page ABI module differs from its inspected image: "+name);
                    modules.Add(name,handle);sizes.Add(name,found.ModuleMemorySize);preferred.Add(name,unchecked((uint)NativeEngine.Number(item["preferred_base"])));
                }
                NativeMemory.Require(modules["McgsSetPro.exe"]==Engine.ImageBase,"Page ABI and attached engine disagree.");
                AddFunctions((IEnumerable)profile["functions"],false);
                var save=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"document-dirty-save-abi-profile.json"),Encoding.UTF8));
                NativeMemory.Require(Convert.ToString(save["binary_sha256"])==Engine.ImageSha256,"Save profile is for a different editor image.");
                AddFunctions((IEnumerable)save["functions"],true);
            }
            void AddFunctions(IEnumerable entries,bool saveFormat) {
                foreach(object row in entries) {
                    var item=(Dictionary<string,object>)row;string name=Convert.ToString(item["name"]);
                    string module=saveFormat?"McgsSetPro.exe":Convert.ToString(item["module"]);
                    int rva=NativeEngine.Number(item["rva"]);NativeMemory.Require(rva>=0 && rva<sizes[module],"Page function RVA is outside module.");
                    IntPtr address=NativeMemory.Add(modules[module],rva);
                    string bytesKey=saveFormat?"expected_first32":"first32",offsetKey="relocation_offsets";
                    byte[] expected=ParseHex(Convert.ToString(item[bytesKey]));
                    foreach(object offset in (IEnumerable)item[offsetKey]) {
                        int at=NativeEngine.Number(offset);NativeMemory.Require(at>=0 && at+4<=expected.Length,"Invalid function relocation span.");
                        uint value=unchecked(BitConverter.ToUInt32(expected,at)+NativeMemory.U(modules[module])-preferred[module]);
                        Array.Copy(BitConverter.GetBytes(value),0,expected,at,4);
                    }
                    NativeMemory.Require(BitConverter.ToString(NativeMemory.Bytes(address,expected.Length))==BitConverter.ToString(expected),"Page function signature differs: "+name);
                    if(item.ContainsKey("ordinal"))NativeMemory.Require(GetProcAddressOrdinal(modules[module],new IntPtr(NativeEngine.Number(item["ordinal"])))==address,"Page MFC export differs: "+name);
                    functions.Add(name,address);
                }
            }
            static byte[] ParseHex(string text){var bytes=new byte[text.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(text.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);return bytes;}
            internal T Bind<T>(string name)where T:class{return BindAddress<T>(functions[name]);}
            internal T BindAddress<T>(IntPtr address)where T:class {
                bool inside=false;foreach(var module in modules){long delta=(long)NativeMemory.U(address)-NativeMemory.U(module.Value);if(delta>=0 && delta<sizes[module.Key])inside=true;}
                NativeMemory.Require(inside,"Unverified page native function address.");NativeMemory.Readable(address,1);
                return Marshal.GetDelegateForFunctionPointer(address,typeof(T))as T;
            }
            internal void Type(IntPtr instance,string expected,int expectedVtable) {
                NativeMemory.Require(instance!=IntPtr.Zero && NativeMemory.Ptr(instance,0)==Engine.Address(expectedVtable),"Page context vtable differs: "+expected);
                NativeMemory.Require(Rtti(instance)==expected,"Page context RTTI differs: "+expected);
            }
            internal string Rtti(IntPtr instance) {
                IntPtr table=NativeMemory.Ptr(instance,0);Engine.Rva(table);
                IntPtr col=NativeMemory.Ptr(table,-4);Engine.Rva(col);
                NativeMemory.Require(NativeMemory.I32(col,0)==0 && NativeMemory.I32(col,4)==0,"Expected a primary x86 RTTI object.");
                IntPtr type=NativeMemory.Ptr(col,12);Engine.Rva(type);return NativeMemory.Ascii(NativeMemory.Add(type,8),256);
            }
            internal IntPtr Virtual(IntPtr instance,int slot,int expectedThunk) {
                NativeMemory.Require(slot>=0 && slot<=104,"Page virtual slot exceeds the derived range.");
                IntPtr table=NativeMemory.Ptr(instance,0);Engine.Rva(table);IntPtr function=NativeMemory.Ptr(table,4*slot);
                NativeMemory.Require(function==Engine.Address(expectedThunk),"Page virtual method differs at slot "+slot);return function;
            }
        }

        sealed class Owner {
            internal IntPtr App,Frame,List;
            internal Dictionary<string,object> Report(){return new Dictionary<string,object>{{"app",NativeMemory.Hex(App)},{"manage_frame",NativeMemory.Hex(Frame)},
                {"manage_frame_rtti",".?AVC0FrmManage@@"},{"user_window_list",NativeMemory.Hex(List)},{"owner_rtti",".?AVC0ManListUser@@"}};}
        }
        static Dictionary<string,object> DescribePointer(Api api,IntPtr pointer) {
            var data=new Dictionary<string,object>{{"address",NativeMemory.Hex(pointer)}};
            try {
                NativeMemory.Require(pointer!=IntPtr.Zero,"Null pointer.");
                IntPtr table=NativeMemory.Ptr(pointer,0);data["vtable"]=NativeMemory.Hex(table);api.Engine.Rva(table);
                data["vtable_rva"]=NativeMemory.Hex(new IntPtr(unchecked((int)(NativeMemory.U(table)-NativeMemory.U(api.Engine.ImageBase)))));
                IntPtr col=NativeMemory.Ptr(table,-4);api.Engine.Rva(col);data["rtti_locator"]=NativeMemory.Hex(col);
                data["rtti_subobject_offset"]=NativeMemory.I32(col,4);
                IntPtr type=NativeMemory.Ptr(col,12);api.Engine.Rva(type);data["rtti"]=NativeMemory.Ascii(NativeMemory.Add(type,8),256);
            }catch(Exception error){data["diagnostic_error"]=error.Message;}
            return data;
        }
        static Owner FindOwner(Api api,NativeContext context,Dictionary<string,object> diagnostic=null) {
            if(diagnostic==null)diagnostic=new Dictionary<string,object>();
            IntPtr rootDoc=api.Strategy.RootDoc();
            diagnostic["root_document"]=DescribePointer(api,rootDoc);
            NativeMemory.Require(NativeMemory.Ptr(rootDoc,0)==api.Engine.Address(RootDocVtable) && NativeMemory.Ptr(rootDoc,0x2D4)==context.ObjectModel,"Root document and attached object model disagree.");
            IntPtr app=api.Bind<NativeEngine.CdeclPointer>("Host_GetApp")();
            diagnostic["app"]=DescribePointer(api,app);
            NativeMemory.Require(NativeMemory.Ptr(app,0x520)==rootDoc,"Application and native data-centre document disagree.");
            diagnostic["app_main_window_0x20"]=DescribePointer(api,NativeMemory.Ptr(app,0x20));
            IntPtr frame=NativeMemory.Ptr(app,0x524);diagnostic["app_manage_frame_0x524"]=DescribePointer(api,frame);
            // AB21B0 constructs C0FrmManage; AB22AB stores that this in app+524.
            // Its native construction appends five list objects to this+314;
            // the third append AB4862/AB48A8 is C0ManListUser (AB9E80).
            api.Type(frame,".?AVC0FrmManage@@",ManageFrameVtable);
            IntPtr array=NativeMemory.Add(frame,0x314);int lists=NativeMemory.I32(array,8);
            diagnostic["list_array_address"]=NativeMemory.Hex(array);diagnostic["list_count"]=lists;
            NativeMemory.Require(lists==5,"Expected the five native management lists.");
            IntPtr listData=NativeMemory.Ptr(array,4);NativeMemory.Readable(listData,4*lists);diagnostic["list_array_data"]=NativeMemory.Hex(listData);
            var entries=new List<Dictionary<string,object>>();
            for(int i=0;i<lists;i++){var item=DescribePointer(api,NativeMemory.Ptr(listData,i*4));item["index"]=i;entries.Add(item);}
            diagnostic["list_entries"]=entries;
            IntPtr list=NativeMemory.Ptr(listData,2*4);
            api.Type(list,".?AVC0ManListUser@@",WindowListVtable);api.Virtual(list,92,WindowArchiveThunk);
            return new Owner{App=app,Frame=frame,List=list};
        }
        internal static Dictionary<string,object> InspectOwner(NativeEngine engine,NativeContext context) {
            NativeOperationTrace.SetPhase("page-owner-inspect");var api=new Api(engine);var diagnostic=new Dictionary<string,object>();
            try {
                Owner owner=FindOwner(api,context,diagnostic);var result=owner.Report();result["ok"]=true;
                result["window_count"]=engine.Bind<NativeEngine.ThisInt>(engine.Virtual(context.WindowManager,19))(context.WindowManager);
                result["native_document_path"]=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(api.Strategy.RootDoc(),0x24),2048);
                result["diagnostics"]=diagnostic;result["write_attempted"]=false;result["native_business_method_called"]=true;return result;
            }catch(Exception error){return new Dictionary<string,object>{{"ok",false},{"error",error.Message},{"error_type",error.GetType().Name},{"diagnostics",diagnostic},{"write_attempted",false},{"native_business_method_called",true}};}
        }

        static string Fixture(string expected) {
            string wanted=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(Path.GetFullPath(expected).Equals(wanted,StringComparison.OrdinalIgnoreCase) && File.Exists(wanted),"Page save/duplicate is restricted to fixtures/initial.MCP.");return wanted;
        }
        internal static string CurrentProjectPath(NativeEngine engine) {
            // Identity is acquired before any Attach, tree walk, page-owner lookup or public Automation access.
            return CurrentProjectPath(new Api(engine));
        }
        static string CurrentProjectPath(Api api) {
            IntPtr doc=api.Strategy.RootDoc();
            string value=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x24),2048);
            NativeMemory.Require(!String.IsNullOrEmpty(value),"Current native document has no project path.");return Path.GetFullPath(value);
        }
        internal static Dictionary<string,object> FlushWindowData(NativeEngine engine,NativeContext context,string expectedProject,int pageId=2) {
            string path=Fixture(expectedProject);return FlushWindowData(new Api(engine),context,path,pageId);
        }
        static Dictionary<string,object> FlushWindowData(Api api,NativeContext context,string path,int pageId) {
            NativeMemory.Require(pageId==2 && CurrentProjectPath(api).Equals(path,StringComparison.OrdinalIgnoreCase),"Window flush requires the exact current fixture and source ID2.");
            NativeMemory.Require(NativeMemory.Ptr(api.Strategy.RootDoc(),0x2D4)==context.ObjectModel,"Window flush context belongs to a different native document.");
            var pages=Pages(api,context);NativeMemory.Require((pages.Count==11 || pages.Count==12) && pages.ContainsKey(2),"Window flush requires the prepared11/12-page fixture.");
            IntPtr page=pages[2];NativeMemory.Require(NativeStrategyProfile.ReadName(api.Strategy,page)=="首页","Window flush source page name differs.");
            // The normal IObject page enumeration has already taken its native lazy-load path.
            IntPtr document=NativeMemory.Ptr(page,0x14);api.Type(document,".?AVC0DocUser@@",WindowDocumentVtable);
            NativeMemory.Require(NativeMemory.I32(document,0x258)==2 && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(document,0x25C),256)=="首页","Loaded native page document identity differs.");
            api.Virtual(document,26,0x3508A);api.Virtual(document,27,0x3A3C8);
            api.Engine.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");api.Virtual(context.WindowService,12,0x21733);
            int before=api.Strategy.Bind<NativeEngine.ThisInt>("RootIsModified")(document);NativeMemory.Require(before==0 || before==1,"Loaded page dirty-state representation differs.");
            NativeOperationTrace.BeforeMutation("native-window2-set-modified");api.Bind<VoidInt>("C0DocUser_SetModified")(document,1);
            NativeMemory.Require(api.Strategy.Bind<NativeEngine.ThisInt>("RootIsModified")(document)==1,"Loaded page was not marked for native save.");
            NativeOperationTrace.SetPhase("native-window2-save-data");bool dispatched=api.Bind<BoolPointer>("UserWindowService_SaveData")(context.WindowService,page);
            NativeMemory.Require(dispatched,"Native user-window service refused the source-page saveData dispatch.");
            int after=api.Strategy.Bind<NativeEngine.ThisInt>("RootIsModified")(document);
            NativeMemory.Require(after==0,"Native page saveData left the loaded page modified; whole-project save was not attempted.");
            return new Dictionary<string,object>{{"page_id",2},{"page_name","首页"},{"page_iobject",NativeMemory.Hex(page)},{"loaded_document",NativeMemory.Hex(document)},
                {"modified_before",before},{"modified_after",after},{"save_data_dispatched",dispatched},{"disk_persistence_verified",false}};
        }
        internal static Dictionary<string,object> Save(NativeEngine engine,string exactExpectedProject) {
            string path=Fixture(exactExpectedProject);var api=new Api(engine);return Save(api,path);
        }
        internal static Dictionary<string,object> SaveRootOnly(NativeEngine engine,string exactExpectedProject) {
            string path=Fixture(exactExpectedProject);var api=new Api(engine);return Save(api,path,null,false);
        }
        static Dictionary<string,object> Save(Api api,string path,NativeContext context=null,bool forceSourcePageFlush=true) {
            IntPtr doc=api.Strategy.RootDoc();
            NativeMemory.Require(CurrentProjectPath(api).Equals(path,StringComparison.OrdinalIgnoreCase),"Native document path differs from the exact isolated save target.");
            IntPtr virtualMethod=api.Virtual(doc,34,SaveDocumentThunk);
            string before=NativeMemory.Hash(path);Dictionary<string,object> flush=null;
            if(forceSourcePageFlush){if(context==null)context=api.Engine.Attach();flush=FlushWindowData(api,context,path,2);}
            NativeMemory.Require(api.Strategy.RootDoc()==doc && CurrentProjectPath(api).Equals(path,StringComparison.OrdinalIgnoreCase),"Native project changed while flushing source-page data.");
            IntPtr wide=Marshal.StringToHGlobalUni(path);int result;
            try {
                NativeOperationTrace.BeforeMutation("native-save-current-project");
                // The guarded direct body is the exact target of the verified virtual thunk.
                result=api.Bind<SaveDocument>("C0DocManage_OnSaveDocument")(doc,wide);
            }finally{Marshal.FreeHGlobal(wide);}
            NativeMemory.Require(result!=0,"Native OnSaveDocument reported failure; no retry was performed.");
            NativeMemory.Require(api.Strategy.Bind<NativeEngine.ThisInt>("RootIsModified")(doc)==0,"Native save returned success but root remains modified.");
            NativeOperationTrace.SetPhase("native-save-returned-success");
            return new Dictionary<string,object>{{"ok",true},{"path",path},{"root_document",NativeMemory.Hex(doc)},{"native_virtual",NativeMemory.Hex(virtualMethod)},
                {"native_return",result},{"source_page_flush_forced",forceSourcePageFlush},{"source_page_flush",flush},{"sha256_before",before},{"sha256_after",NativeMemory.Hash(path)},{"root_modified",0},
                {"native_save_return_verified",true},{"reopen_persistence_verified",false},{"write_attempted",true}};
        }

        sealed class MemoryFile : IDisposable {
            readonly Api api;internal readonly IntPtr Storage;bool constructed;
            internal MemoryFile(Api value){api=value;Storage=Marshal.AllocHGlobal(44);try{api.Bind<MemoryFileConstructor>("CMemFile_Ctor_ordinal566")(Storage,1024);constructed=true;}catch{Dispose();throw;}}
            public void Dispose(){try{if(constructed){constructed=false;api.Bind<Void0>("CMemFile_Dtor_ordinal1187")(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
        }
        sealed class Archive : IDisposable {
            readonly Api api;internal readonly IntPtr Storage;bool constructed;
            internal Archive(Api value,IntPtr file,uint mode){api=value;Storage=Marshal.AllocHGlobal(72);try{api.Bind<ArchiveConstructor>("Native_CArchive_Ctor")(Storage,file,mode,0x400000,IntPtr.Zero);constructed=true;}catch{Dispose();throw;}}
            public void Dispose(){try{if(constructed){constructed=false;api.Bind<Void0>("Native_CArchive_Dtor")(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
        }
        static Dictionary<int,IntPtr> Pages(Api api,NativeContext context) {
            var pages=new Dictionary<int,IntPtr>();
            foreach(IntPtr page in api.Engine.Children(context.WindowManager)) {
                api.Type(page,".?AVUserWindowObject@@",PageVtable);int id=api.Engine.Call<NativeEngine.ThisInt>("UserWindow_ID")(page);
                NativeMemory.Require(id>=0 && !pages.ContainsKey(id),"Window IDs are not unique nonnegative values.");pages.Add(id,page);
            }
            return pages;
        }
        static void Snapshot(Api api,IntPtr parent,int depth,List<string> structure,List<Dictionary<string,object>> identities,HashSet<uint> visited,HashSet<int> pageIds,bool requireUniqueIds) {
            NativeMemory.Require(depth<=16 && structure.Count<=512 && visited.Add(NativeMemory.U(parent)),"Page subtree is cyclic or exceeds its trial bound.");
            foreach(IntPtr child in api.Engine.Children(parent)) {
                var data=api.Engine.Describe(child);string name=NativeStrategyProfile.ReadName(api.Strategy,child);int id=NativeStrategyProfile.ReadId(api.Strategy,child);
                NativeMemory.Require(id>=0 || id==-2,"Unexpected negative control identity sentinel.");
                if(requireUniqueIds && id>=0)NativeMemory.Require(pageIds.Add(id),"Assigned copied control identities are not unique within their page.");
                string type=Convert.ToString(data["rtti"]);
                structure.Add(depth.ToString(CultureInfo.InvariantCulture)+"|"+type+"|"+name);
                identities.Add(new Dictionary<string,object>{{"depth",depth},{"rtti",type},{"name",name},{"native_id",id},
                    {"native_id_status",id>=0?"assigned":"unassigned_lookup_sentinel"},{"address",NativeMemory.Hex(child)}});
                Snapshot(api,child,depth+1,structure,identities,visited,pageIds,requireUniqueIds);
            }
        }
        static string IdentityKeys(List<Dictionary<string,object>> identities) {
            var keys=new List<string>();foreach(var item in identities)keys.Add(Convert.ToString(item["depth"],CultureInfo.InvariantCulture)+"|"+
                Convert.ToString(item["rtti"])+"|"+Convert.ToString(item["name"])+"|"+Convert.ToString(item["native_id"],CultureInfo.InvariantCulture));
            keys.Sort(StringComparer.Ordinal);return String.Join("\n",keys.ToArray());
        }
        static string StructureIdentityKey(Dictionary<string,object> item) {
            return Convert.ToString(item["depth"],CultureInfo.InvariantCulture)+"|"+Convert.ToString(item["rtti"])+"|"+Convert.ToString(item["name"]);
        }
        static bool UnassignedCopyMatchesSource(List<Dictionary<string,object>> source,List<Dictionary<string,object>> copied) {
            var available=new Dictionary<string,int>(StringComparer.Ordinal);
            foreach(var item in source)if(Convert.ToInt32(item["native_id"],CultureInfo.InvariantCulture)==-2){string key=StructureIdentityKey(item);int count;available.TryGetValue(key,out count);available[key]=count+1;}
            foreach(var item in copied)if(Convert.ToInt32(item["native_id"],CultureInfo.InvariantCulture)==-2){string key=StructureIdentityKey(item);int count;if(!available.TryGetValue(key,out count)||count<=0)return false;available[key]=count-1;}
            return true;
        }
        internal static Dictionary<string,object> Duplicate(NativeEngine engine,NativeContext context,string expectedProject,int sourceArchiveId=2) {
            string path=Fixture(expectedProject);NativeMemory.Require(sourceArchiveId==2,"Only prepared source window ID2 is permitted.");
            NativeMemory.Require(Interlocked.CompareExchange(ref copyInProgress,1,0)==0,"A page copy is already in progress.");
            try {
                NativeMemory.Require(Interlocked.CompareExchange(ref copyLoadAttempted,0,0)==0,"This engine revision already attempted a page load/copy; inspect evidence instead of retrying.");
                var api=new Api(engine);Owner owner=FindOwner(api,context);var before=Pages(api,context);
                NativeMemory.Require(before.Count==11 && engine.Bind<NativeEngine.ThisInt>(engine.Virtual(context.WindowManager,19))(context.WindowManager)==11,
                    "Duplicate requires the exact11-window preimage; a12-window result or other state is rejected.");
                NativeMemory.Require(before.ContainsKey(2) && NativeStrategyProfile.ReadName(api.Strategy,before[2])=="首页","Prepared source window ID2/name differs.");
                var sourceSnapshot=new List<string>();var beforeSourceIds=new List<Dictionary<string,object>>();
                Snapshot(api,before[2],0,sourceSnapshot,beforeSourceIds,new HashSet<uint>(),new HashSet<int>(),false);sourceSnapshot.Sort(StringComparer.Ordinal);
                var savedSource=Save(api,path,context); // Archive store reads the persisted source page, not a possibly dirty page instance.
                NativeMemory.Require(FindOwner(api,context).List==owner.List,"Host page-manager context changed during native save.");
                api.Virtual(owner.List,92,WindowArchiveThunk);
                var archiveCall=api.Bind<WindowArchive>("C0ManListUser_ArchiveWindow");
                using(var file=new MemoryFile(api)) {
                    NativeOperationTrace.SetPhase("page-archive-store");
                    using(var store=new Archive(api,file.Storage,0))archiveCall(owner.List,2,store.Storage);
                    api.Bind<Void0>("Native_CFile_SeekToBegin")(file.Storage);
                    using(var load=new Archive(api,file.Storage,1)) {
                        NativeMemory.Require(Interlocked.CompareExchange(ref copyLoadAttempted,1,0)==0,"A page-copy load has already been attempted.");
                        NativeStrategyProfile.MarkRootDirty(api.Strategy);
                        NativeOperationTrace.BeforeMutation("page-archive-load-new-window");
                        archiveCall(owner.List,-1,load.Storage);
                    }
                }
                NativeOperationTrace.SetPhase("page-copy-postconditions");var after=Pages(api,context);
                NativeMemory.Require(after.Count==12 && engine.Bind<NativeEngine.ThisInt>(engine.Virtual(context.WindowManager,19))(context.WindowManager)==12,"Native copy did not produce exactly one additional window.");
                int newId=-1,added=0;foreach(var page in before)NativeMemory.Require(after.ContainsKey(page.Key),"An original window vanished during native copy.");
                foreach(var page in after)if(!before.ContainsKey(page.Key)){newId=page.Key;added++;}
                NativeMemory.Require(added==1 && newId!=2,"New page identity is not unique.");
                string newName=NativeStrategyProfile.ReadName(api.Strategy,after[newId]);NativeMemory.Require(!String.IsNullOrEmpty(newName),"Copied window has no name.");
                foreach(var page in before)NativeMemory.Require(NativeStrategyProfile.ReadName(api.Strategy,page.Value)!=newName,"Copied page name collides with an existing window.");
                var newSnapshot=new List<string>();var copiedIds=new List<Dictionary<string,object>>();
                Snapshot(api,after[newId],0,newSnapshot,copiedIds,new HashSet<uint>(),new HashSet<int>(),true);newSnapshot.Sort(StringComparer.Ordinal);
                NativeMemory.Require(sourceSnapshot.Count==newSnapshot.Count && String.Join("\n",sourceSnapshot.ToArray())==String.Join("\n",newSnapshot.ToArray()),"Copied control structure/types/names differ from source; no automatic retry.");
                NativeMemory.Require(UnassignedCopyMatchesSource(beforeSourceIds,copiedIds),"Copied -2 lookup sentinel lacks the same source control structure/name sentinel.");
                NativeStrategyProfile.MarkRootDirty(api.Strategy);var savedCopy=Save(api,path,context);
                var sourceAfterStructure=new List<string>();var afterSourceIds=new List<Dictionary<string,object>>();
                Snapshot(api,after[2],0,sourceAfterStructure,afterSourceIds,new HashSet<uint>(),new HashSet<int>(),false);sourceAfterStructure.Sort(StringComparer.Ordinal);
                NativeMemory.Require(String.Join("\n",sourceSnapshot.ToArray())==String.Join("\n",sourceAfterStructure.ToArray()) && IdentityKeys(beforeSourceIds)==IdentityKeys(afterSourceIds),
                    "Original source-page structure or native identities changed during native copy/save.");
                NativeOperationTrace.SetPhase("page-copy-native-save-complete");var report=owner.Report();
                report["ok"]=true;report["source_page_id"]=2;report["source_page_name"]="首页";report["before_window_count"]=11;report["after_window_count"]=12;
                report["new_page_id"]=newId;report["new_page_name"]=newName;report["source_control_snapshot"]=sourceSnapshot;report["copied_control_snapshot"]=newSnapshot;
                report["control_structure_snapshot_equal"]=true;report["source_native_ids_unchanged"]=true;report["copied_assigned_native_ids_page_unique"]=true;
                report["copied_unassigned_lookup_sentinels_match_source"]=true;
                report["before_source_native_ids"]=beforeSourceIds;report["after_source_native_ids"]=afterSourceIds;report["copied_native_ids"]=copiedIds;
                report["binding_preservation_requires_offline_readback"]=true;
                report["source_save"]=savedSource;report["copy_save"]=savedCopy;report["native_save_return_verified"]=true;report["reopen_persistence_verified"]=false;
                report["write_attempted"]=true;report["native_business_method_called"]=true;return report;
            }finally{Interlocked.Exchange(ref copyInProgress,0);}
        }
    }
}
