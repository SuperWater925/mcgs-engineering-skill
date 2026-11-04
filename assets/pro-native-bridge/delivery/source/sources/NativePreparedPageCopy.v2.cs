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
    internal static class NativePreparedPageCopy {
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

        const string CopyAbi="3c55566a34cea3b5754a6060a9d84f9ac825f17189f76ab7569e2bee8967c065";
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
                string directory=Path.Combine(NativeOperations.TaskRoot,"static"); NativeMemory.Require(NativeMemory.Hash(Path.Combine(directory,"native-page-duplicate-abi-profile.json"))==CopyAbi,"Page-copy ABI proof changed.");
                var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"native-page-duplicate-abi-profile.json"),Encoding.UTF8));
                foreach(object row in (IEnumerable)profile["modules"]) {
                    var item=(Dictionary<string,object>)row;string name=Convert.ToString(item["name"]);
                    IntPtr handle=GetModuleHandleW(name);NativeMemory.Require(handle!=IntPtr.Zero,"Page ABI module is not already loaded: "+name);
                    ProcessModule found=null;foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==handle){found=loaded;break;}
                    NativeMemory.Require(found!=null && NativeBinaryIdentity.Observe(Convert.ToString(item["sha256"]),NativeMemory.Hash(found.FileName),"NativePreparedPageCopy.v2:55:module"),"Page ABI module differs from its inspected image: "+name);
                    modules.Add(name,handle);sizes.Add(name,found.ModuleMemorySize);preferred.Add(name,unchecked((uint)NativeEngine.Number(item["preferred_base"])));
                }
                NativeMemory.Require(modules["McgsSetPro.exe"]==Engine.ImageBase,"Page ABI and attached engine disagree.");
                AddFunctions((IEnumerable)profile["functions"],false);
                var save=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"document-dirty-save-abi-profile.json"),Encoding.UTF8));
                NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(save["binary_sha256"]),Engine.ImageSha256,"NativePreparedPageCopy.v2:61:editor"),"Save profile is for a different editor image.");
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
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr CStringAssign(IntPtr self,IntPtr wide);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool RenamePage(IntPtr self,IntPtr oldName,IntPtr newName);
        internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){var shared=new NativePageControlAbi(e,c,project);return Capture(new Api(e),shared,action);}
        internal static INativePreparedPageControlEdit Prepare(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new Prepared(new Api(e),new NativePageControlAbi(e,c,project),action);}
        static Dictionary<string,object> Capture(Api api,NativePageControlAbi shared,Dictionary<string,object> action){
            var target=NativePageControlPreparation.Map(action["target"]);NativeMemory.Require(NativePageControlPreparation.Text(target,"source_mode")=="persisted-archive","Page-copy source must explicitly name persisted-archive mode.");
            IntPtr page=shared.Page(target);int id=NativePageControlPreparation.Number(target,"page_id");IntPtr document=NativeMemory.Ptr(page,0x14);
            NativeMemory.Require(api.Strategy.Bind<NativeEngine.ThisInt>("RootIsModified")(document)==0,"Page-copy source has pending edits; persist the intended source in a planned batch before copying its archive.");
            string blob=PersistedSource(shared,target,id);var structure=new List<string>();var identities=new List<Dictionary<string,object>>();Snapshot(api,page,0,structure,identities,new HashSet<uint>(),new HashSet<int>(),false);structure.Sort(StringComparer.Ordinal);
            return new Dictionary<string,object>{{"abi_profile_sha256",CopyAbi},{"source_mode","persisted-archive"},{"persisted_source_blob_sha256",blob},{"source_page",shared.PageSnapshot(page)},{"source_structure",structure},{"source_identities",identities},{"owner",FindOwner(api,shared.Context).Report()}};
        }
        static string PersistedSource(NativePageControlAbi shared,Dictionary<string,object> target,int id){
            var proof=NativePageControlPreparation.Map(target["source_export_index"]);string path=Path.GetFullPath(NativePageControlPreparation.Text(proof,"file")),root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";
            NativeMemory.Require(path.StartsWith(root,StringComparison.OrdinalIgnoreCase)&&File.Exists(path)&&(File.GetAttributes(path)&(FileAttributes.Directory|FileAttributes.ReparsePoint))==0&&NativeMemory.Hash(path)==NativePageControlPreparation.Text(proof,"sha256"),"Page-copy source export proof path/hash differs.");
            var index=new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));NativeMemory.Require(Convert.ToString(index["sha256"])==NativeMemory.Hash(shared.Project)&&Convert.ToBoolean(index["source_unchanged"]),"Page-copy source export is not the current stable physical preimage.");string found=null;
            foreach(object value in (IEnumerable)index["rows"]){var row=NativePageControlPreparation.Map(value);if(Convert.ToString(row["table"])!="WndUser"||Convert.ToInt32(row["iID"])!=id)continue;NativeMemory.Require(found==null&&Convert.ToString(row["strName"])==NativePageControlPreparation.Text(target,"page_name")&&Convert.ToInt32(row["iDeleteFlag"])==0,"Page-copy source export row differs.");var blob=NativePageControlPreparation.Map(row["lbObjects"]);string name=Convert.ToString(blob["file"]);NativeMemory.Require(Path.GetFileName(name)==name,"Page-copy blob is not a local export filename.");found=Convert.ToString(blob["sha256"]);NativeMemory.Require(NativeMemory.Hash(Path.Combine(Path.GetDirectoryName(path),name))==found,"Page-copy source full archive proof differs.");}
            NativeMemory.Require(found!=null,"Page-copy source export row is absent.");return found;
        }
        sealed class OwnedMemoryFile : IDisposable {
            readonly Void0 destroy;internal IntPtr Storage;bool constructed;
            internal OwnedMemoryFile(Api api){var ctor=api.Bind<MemoryFileConstructor>("CMemFile_Ctor_ordinal566");destroy=api.Bind<Void0>("CMemFile_Dtor_ordinal1187");Storage=Marshal.AllocHGlobal(44);try{ctor(Storage,1024);constructed=true;}catch{Dispose();throw;}}
            public void Dispose(){if(Storage==IntPtr.Zero)return;try{if(constructed){constructed=false;destroy(Storage);}}finally{Marshal.FreeHGlobal(Storage);Storage=IntPtr.Zero;}}
        }
        sealed class OwnedArchive : IDisposable {
            readonly ArchiveConstructor constructor;readonly Void0 destroy;internal IntPtr Storage;bool constructed;
            internal OwnedArchive(Api api){constructor=api.Bind<ArchiveConstructor>("Native_CArchive_Ctor");destroy=api.Bind<Void0>("Native_CArchive_Dtor");Storage=Marshal.AllocHGlobal(72);}
            internal void Start(IntPtr file,uint mode){NativeMemory.Require(!constructed&&Storage!=IntPtr.Zero,"Owned archive is already constructed/disposed.");constructor(Storage,file,mode,0x400000,IntPtr.Zero);constructed=true;}
            internal void Finish(){if(constructed){constructed=false;destroy(Storage);}}
            public void Dispose(){if(Storage==IntPtr.Zero)return;try{Finish();}finally{Marshal.FreeHGlobal(Storage);Storage=IntPtr.Zero;}}
        }
        sealed class Prepared : INativePreparedPageControlEdit {
            readonly Api api;readonly NativePageControlAbi shared;readonly Dictionary<string,object> action,before;readonly Dictionary<int,IntPtr> pages;readonly Dictionary<int,string> names=new Dictionary<int,string>();readonly int sourceId;readonly Owner owner;
            readonly NativePreparedPageOperations.WindowNameCache nameCache;readonly WindowArchive archive;readonly Void0 seek;readonly VoidInt setRoot;readonly NativeEngine.ThisInt modified;readonly BoolPointer saveData;readonly RenamePage rename;readonly CStringAssign assign;
            OwnedMemoryFile file;OwnedArchive store,load;NativeStrategyProfile.CString oldName,newName;string requestedName;IntPtr copy,copyDoc;int newId=-1;bool applied,disposed;
            internal Prepared(Api a,NativePageControlAbi s,Dictionary<string,object> request){api=a;shared=s;action=request;NativeMemory.Require(NativePageControlPreparation.Text(action,"abi_profile_sha256")==CopyAbi,"Page-copy action ABI binding differs.");
                nameCache=new NativePreparedPageOperations.WindowNameCache(shared);archive=api.Bind<WindowArchive>("C0ManListUser_ArchiveWindow");seek=api.Bind<Void0>("Native_CFile_SeekToBegin");setRoot=api.Strategy.Bind<VoidInt>("RootSetModified");modified=api.Strategy.Bind<NativeEngine.ThisInt>("RootIsModified");saveData=shared.Bind<BoolPointer>("size","WindowSaveData");rename=shared.Bind<RenamePage>("page","WindowServiceRename");assign=api.Strategy.Bind<CStringAssign>("CStringAssignWide");api.Strategy.Bind<Void0>("CStringDtor");
                owner=FindOwner(api,shared.Context);api.Virtual(owner.List,92,WindowArchiveThunk);pages=Pages(api,shared.Context);foreach(var row in pages)names.Add(row.Key,NativeStrategyProfile.ReadName(api.Strategy,row.Value));sourceId=NativePageControlPreparation.Number(NativePageControlPreparation.Map(action["target"]),"page_id");
                try{before=Capture(api,shared,action);NativePageControlPreparation.Before(action,before);var after=NativePageControlPreparation.Map(action["after"]);object name;if(after.TryGetValue("page_name",out name)&&name!=null){requestedName=Convert.ToString(name);NativePageControlPreparation.Name(requestedName);foreach(string existing in names.Values)NativeMemory.Require(!String.Equals(existing,requestedName,StringComparison.OrdinalIgnoreCase),"Copied page name already exists.");oldName=new NativeStrategyProfile.CString(api.Strategy,"");newName=new NativeStrategyProfile.CString(api.Strategy,requestedName);}
                    file=new OwnedMemoryFile(api);store=new OwnedArchive(api);load=new OwnedArchive(api);store.Start(file.Storage,0);
                }catch{Dispose();throw;}
            }
            public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){NativeMemory.Require(!disposed&&!applied,"Prepared page-copy is disposed or already applied.");shared.Current();NativePageControlPreparation.Same(before,Capture(api,shared,action),"Page-copy preimage changed before Apply.");lease.BeginApply(action);applied=true;
                // The store branch reads the proven persisted source. No implicit RootSave/source flush occurs.
                NativeOperationTrace.BeforeMutation("parameterized-page-archive-store-owned-buffer");archive(owner.List,sourceId,store.Storage);store.Finish();seek(file.Storage);load.Start(file.Storage,1);
                NativeOperationTrace.BeforeMutation("parameterized-page-copy-root-dirty");setRoot(api.Strategy.RootDoc(),1);Marshal.WriteInt32(api.Strategy.RootDoc(),0x114,0);nameCache.Invalidate(lease,action);NativeOperationTrace.BeforeMutation("parameterized-page-archive-load-new");archive(owner.List,-1,load.Storage);load.Finish();
                var current=Pages(api,shared.Context);NativeMemory.Require(current.Count==pages.Count+1,"Native archive copy did not add exactly one page.");foreach(var row in pages)NativeMemory.Require(current.ContainsKey(row.Key)&&current[row.Key]==row.Value&&NativeStrategyProfile.ReadName(api.Strategy,row.Value)==names[row.Key],"Page copy altered an original page identity/name.");foreach(var row in current)if(!pages.ContainsKey(row.Key)){NativeMemory.Require(copy==IntPtr.Zero,"Page copy assigned more than one new ID.");newId=row.Key;copy=row.Value;}NativeMemory.Require(copy!=IntPtr.Zero,"Page copy returned no new page.");shared.Engine.Children(copy);copyDoc=shared.Document(copy,newId);
                if(requestedName!=null){assign(oldName.Storage,NativeMemory.Ptr(copyDoc,0x25C));NativeOperationTrace.BeforeMutation("parameterized-copied-page-rename");NativeMemory.Require(rename(shared.Context.WindowService,oldName.Storage,newName.Storage),"Copied page rename returned false; do not replay.");nameCache.Refresh(lease,action,copy,newName);NativeMemory.Require(NativeStrategyProfile.ReadName(api.Strategy,copy)==requestedName,"Copied page requested-name readback differs.");}
                string finalName=NativeStrategyProfile.ReadName(api.Strategy,copy);NativeMemory.Require(!String.IsNullOrWhiteSpace(finalName),"Copied page has an empty name.");foreach(string name in names.Values)NativeMemory.Require(!String.Equals(name,finalName,StringComparison.OrdinalIgnoreCase),"Copied page name collides with an original page.");
                var structure=new List<string>();var copiedIds=new List<Dictionary<string,object>>();Snapshot(api,copy,0,structure,copiedIds,new HashSet<uint>(),new HashSet<int>(),true);structure.Sort(StringComparer.Ordinal);NativePageControlPreparation.Same(before["source_structure"],structure,"Copied control structure/type/name projection differs from persisted source's clean native projection.");
                var sourceIds=new List<Dictionary<string,object>>();foreach(object value in (IEnumerable)before["source_identities"])sourceIds.Add(NativePageControlPreparation.Map(value));NativeMemory.Require(UnassignedCopyMatchesSource(sourceIds,copiedIds),"Copied unassigned lookup sentinel lacks the same source structure/name.");
                var sourceNow=new List<string>();var idsNow=new List<Dictionary<string,object>>();Snapshot(api,pages[sourceId],0,sourceNow,idsNow,new HashSet<uint>(),new HashSet<int>(),false);sourceNow.Sort(StringComparer.Ordinal);NativePageControlPreparation.Same(before["source_structure"],sourceNow,"Page copy altered source structure.");NativeMemory.Require(IdentityKeys(sourceIds)==IdentityKeys(idsNow),"Page copy altered source native IDs.");
                lease.RegisterCreatedPage(action,newId);lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind","page-copy"},{"new_page_id",newId},{"new_page_name",finalName},{"source_mode","persisted-archive"},{"persisted_source_blob_sha256",before["persisted_source_blob_sha256"]},{"copied_native_ids",copiedIds},{"root_save_called",false},{"implicit_source_flush_called",false},{"full_payload_acceptance_pending",true},{"automatic_retry",false}};
            }
            public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(applied&&!disposed,"Apply must precede page-copy Flush.");lease.BeginFlush(action);shared.Current();int dirty=modified(copyDoc);NativeMemory.Require(dirty==0||dirty==1,"Copied page dirty state differs.");if(dirty==1){NativeOperationTrace.BeforeMutation("parameterized-copied-page-save-data");NativeMemory.Require(saveData(shared.Context.WindowService,copy)&&modified(copyDoc)==0,"Copied page saveData did not clean its document.");}lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"root_save_called",false},{"full_payload_acceptance_pending",true}};}
            public void Dispose(){if(disposed)return;disposed=true;try{if(load!=null)load.Dispose();}finally{try{if(store!=null)store.Dispose();}finally{try{if(file!=null)file.Dispose();}finally{try{if(newName!=null)newName.Dispose();}finally{if(oldName!=null)oldName.Dispose();}}}}}
        }

    }
}
