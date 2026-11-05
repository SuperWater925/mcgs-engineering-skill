// Independent additional source. Factory objects remain transient; persistent controls are native template clones.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class NativeStandardControlsExtensionProfile {
        const string ProfileHash="3b38a7bafd4d49cc93be51a2b14529c95c8f57924072e42db04f45582a5fc18a";
        const string TrialName="Codex控件接口试验",InputVariable="数字输入_十进制";
        const int PageTable=0xDED294,DocTable=0xDC4D94;
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Factory();
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr Clone(IntPtr self,IntPtr targetDoc);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Void0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VoidPointer(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VoidInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void SetRectangle(IntPtr self,IntPtr rectangle,IntPtr auxiliary);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool SaveData(IntPtr self,IntPtr page);

        sealed class Kind {
            internal string Name,Factory;internal int Primary,Object,Size,TypeId,DeletingEntry,RuntimeClass,FactoryEntry;
            internal Dictionary<string,object> Template;
        }
        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeStrategyProfile.Api Shared;
            internal readonly Dictionary<string,Kind> Kinds=new Dictionary<string,Kind>();
            readonly Dictionary<string,Dictionary<string,object>> functions=new Dictionary<string,Dictionary<string,object>>();
            internal Api(NativeEngine engine) {
                Engine=engine;Shared=new NativeStrategyProfile.Api(engine);Thread();
                string path=Path.Combine(NativeOperations.TaskRoot,"extensions","control","standard-controls-abi-guard-v3.json");
                NativeMemory.Require(NativeMemory.Hash(path)==ProfileHash,"Standard-control ABI guard hash differs.");
                var profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
                NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),engine.ImageSha256,"extensions__control__NativeStandardControlsExtensionProfile.v3:37:editor"),"Actual editor binary differs from standard-control ABI evidence.");
                foreach(object v in (IEnumerable)profile["functions"]){var f=(Dictionary<string,object>)v;functions.Add(Convert.ToString(f["name"]),f);Verify(f);}
                foreach(object v in (IEnumerable)profile["classes"]) {
                    var row=(Dictionary<string,object>)v;var kind=new Kind{Name=Convert.ToString(row["name"]),Factory=Convert.ToString(row["factory_name"]),Primary=NativeEngine.Number(row["primary"]),Object=NativeEngine.Number(row["iobject"]),
                        Size=NativeEngine.Number(row["size"]),TypeId=NativeEngine.Number(row["type_id"]),DeletingEntry=NativeEngine.Number(row["delete_entry_rva"]),
                        RuntimeClass=NativeEngine.Number(row["runtime_class_rva"]),FactoryEntry=NativeEngine.Number(row["factory_entry_rva"])};Kinds.Add(kind.Name,kind);
                }
                foreach(object v in (IEnumerable)profile["templates"]){var row=(Dictionary<string,object>)v;Kinds[Convert.ToString(row["class_name"])].Template=row;}
                string index=Path.Combine(Convert.ToString(profile["source_export"]),"index.json");NativeMemory.Require(NativeMemory.Hash(index)==Convert.ToString(profile["source_export_index_sha256"]),"Prepared source-template export index changed.");
            }
            internal void Thread(){NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Standard controls require the captured x86 UI thread.");}
            internal void Project(string expected) {
                Thread();string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
                // The Shared Api already verified actual module hashes once for this request.
                // Still reread the current native root/path and getter bytes before every call.
                var getter=functions["IdentityGetAfxApp"];Verify(getter);
                NativeMemory.Require(Shared.AddressOf("GetAfxApp")==Engine.Address(NativeEngine.Number(getter["rva"])),"Shared identity getter and guarded function differ.");
                IntPtr root=Shared.RootDoc();
                string current=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(root,0x24),2048);
                NativeMemory.Require(!String.IsNullOrEmpty(current),"Current native document has no project path.");
                NativeMemory.Require(Path.GetFullPath(expected).Equals(fixture,StringComparison.OrdinalIgnoreCase) && Path.GetFullPath(current).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Standard controls require the exact current owned fixture.");
            }
            void Verify(Dictionary<string,object> f) {
                string value=Convert.ToString(f["first32"]);var bytes=new byte[value.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(value.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                NativeCodeRelocation.RebaseDeltaInPlace(bytes,(IEnumerable)f["relocations"],unchecked((uint)(NativeMemory.U(Engine.ImageBase)-0x400000U)));
                NativeMemory.Require(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(Engine.Address(NativeEngine.Number(f["rva"])),bytes.Length)),"Standard-control native function bytes differ: "+f["name"]);
            }
            internal T Bind<T>(string name)where T:class {Project(Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));var f=functions[name];Verify(f);return Engine.Bind<T>(Engine.Address(NativeEngine.Number(f["rva"])));}
            internal IntPtr CreateFromRuntimeClass(Kind kind) {
                Project(Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));
                IntPtr runtime=Engine.Address(kind.RuntimeClass);NativeMemory.Readable(runtime,16);
                IntPtr className=NativeMemory.Ptr(runtime,0);Engine.Rva(className);
                NativeMemory.Require(NativeMemory.Ascii(className,80)==kind.Name && NativeMemory.I32(runtime,4)==kind.Size,"Live CRuntimeClass name/size differs.");
                IntPtr entry=NativeMemory.Ptr(runtime,12);NativeMemory.Require(entry==Engine.Address(kind.FactoryEntry),"Live CRuntimeClass factory pointer differs from extracted metadata.");
                var guard=functions[kind.Factory];Verify(guard);byte[] jump=NativeMemory.Bytes(entry,5);
                NativeMemory.Require(jump[0]==0xE9,"Expected the extracted CRuntimeClass factory E9 entry.");
                IntPtr body=NativeMemory.Add(entry,checked(5+BitConverter.ToInt32(jump,1)));
                NativeMemory.Require(body==Engine.Address(NativeEngine.Number(guard["rva"])),"Live CRuntimeClass E9 resolution differs from generated body guard.");
                // The actual CRuntimeClass pfnCreateObject is called, never an independently transcribed body constant.
                return Engine.Bind<Factory>(entry)();
            }
            internal void Slot(IntPtr value,int slot,int entry){NativeMemory.Require(Engine.Virtual(value,slot)==Engine.Address(entry),"Standard-control virtual entry differs at slot "+slot);}
            internal void Type(Kind kind,IntPtr complete) {
                Thread();NativeMemory.Readable(complete,kind.Size);
                NativeMemory.Require(NativeMemory.Ptr(complete,0)==Engine.Address(kind.Primary) && NativeMemory.Ptr(complete,4)==Engine.Address(kind.Object) && NativeMemory.I32(complete,0xC)==kind.TypeId,"Standard control class/type differs: "+kind.Name);
                IntPtr col=NativeMemory.Ptr(Engine.Address(kind.Object),-4),descriptor=NativeMemory.Ptr(col,12);
                NativeMemory.Require(NativeMemory.I32(col,4)==4 && NativeMemory.Ascii(NativeMemory.Add(descriptor,8),256)==".?AV"+kind.Name+"@@","Standard-control RTTI differs.");
                Slot(complete,1,kind.DeletingEntry);Slot(complete,21,0x24B63);Slot(complete,27,0x46CCC);Slot(complete,29,0x1ACD);
                // No IObject virtual calls are required to identify an unattached factory object.
            }
        }
        sealed class Page {internal IntPtr Object,Doc;internal int Id;internal string Name;}
        sealed class Source {internal Kind Kind;internal Page Page;internal IntPtr Complete;internal Dictionary<string,object> Snapshot;}
        static List<IntPtr> Controls(Api api,Page page){return api.Engine.Children(page.Object);}
        static int[] Rectangle(IntPtr value){return new int[]{NativeMemory.I32(value,0x80),NativeMemory.I32(value,0x84),NativeMemory.I32(value,0x88),NativeMemory.I32(value,0x8C)};}
        static bool EqualRect(int[] a,int[] b){for(int i=0;i<4;i++)if(a[i]!=b[i])return false;return true;}
        static Page GetPage(Api api,NativeContext context,int id,string name,bool required) {
            int count=0,hits=0;IntPtr found=IntPtr.Zero;
            foreach(IntPtr p in api.Engine.Children(context.WindowManager)) {
                count++;NativeMemory.Require(NativeMemory.Ptr(p,0)==api.Engine.Address(PageTable),"Native page class differs.");
                int archive=api.Bind<NativeEngine.ThisInt>("PageArchiveId")(p);if(archive!=id)continue;
                NativeMemory.Require(NativeStrategyProfile.ReadName(api.Shared,p)==name,"Expected source/target page name differs.");found=p;hits++;
            }
            if(!required && hits==0)return null;
            NativeMemory.Require(count==13 && hits==1,"Standard-control trial requires exactly13 pages and a unique source/target page.");
            api.Engine.Children(found);IntPtr doc=NativeMemory.Ptr(found,0x14);
            NativeMemory.Require(NativeMemory.Ptr(doc,0)==api.Engine.Address(DocTable) && NativeMemory.I32(doc,0x258)==id && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x25C),256)==name,"Loaded native page document identity differs.");
            return new Page{Object=found,Doc=doc,Id=id,Name=name};
        }
        static Dictionary<string,object> Snapshot(Api api,Kind kind,IntPtr complete,bool attached) {
            api.Type(kind,complete);var item=new Dictionary<string,object>{{"class",kind.Name},{"type_id",kind.TypeId},{"complete",NativeMemory.Hex(complete)},{"rectangle",Rectangle(complete)},
                {"owner_document",NativeMemory.Hex(NativeMemory.Ptr(complete,0x64))},{"registered",attached}};
            if(attached) {
                IntPtr obj=NativeMemory.Add(complete,4);int id=NativeStrategyProfile.ReadId(api.Shared,obj);NativeMemory.Require(id>=0 || id==-2,"Unclassified standard-control native ID.");
                item["name"]=NativeStrategyProfile.ReadName(api.Shared,obj);item["native_id"]=id;item["native_id_status"]=id>=0?"assigned":"unassigned_lookup_sentinel";
            }
            if(kind.Name=="CDrawEdit")item["input_variable"]=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(complete,0x11C),1024);
            return item;
        }
        static bool EqualSnapshot(Dictionary<string,object> a,Dictionary<string,object> b) {
            if(a.Count!=b.Count)return false;foreach(var row in a){object value;if(!b.TryGetValue(row.Key,out value))return false;if(row.Value is int[]){if(!(value is int[]) || !EqualRect((int[])row.Value,(int[])value))return false;}else if(!Object.Equals(row.Value,value))return false;}return true;
        }
        static Source GetSource(Api api,NativeContext context,Kind kind) {
            var t=kind.Template;Page page=GetPage(api,context,Convert.ToInt32(t["source_page_id"]),Convert.ToString(t["source_page_name"]),true);
            var controls=Controls(api,page);Projection(api,kind,controls);
            string wanted=Convert.ToString(t["source_control_name"]);int hits=0;IntPtr found=IntPtr.Zero;
            foreach(IntPtr obj in controls) {
                if(NativeMemory.Ptr(obj,0)!=api.Engine.Address(kind.Object))continue;
                if(NativeStrategyProfile.ReadName(api.Shared,obj)!=wanted)continue;found=NativeMemory.Add(obj,-4);hits++;
            }
            NativeMemory.Require(hits==1,"Source standard control is absent or not unique.");api.Type(kind,found);NativeMemory.Require(NativeMemory.Ptr(found,0x64)==page.Doc,"Source control owner differs.");
            var snapshot=Snapshot(api,kind,found,true);if(kind.Name=="CDrawEdit")NativeMemory.Require(Convert.ToString(snapshot["input_variable"])==InputVariable && Convert.ToInt32(t["binding_id"])==96 && Convert.ToInt32(t["binding_type"])==1,"Input template binding differs.");
            return new Source{Kind=kind,Page=page,Complete=found,Snapshot=snapshot};
        }
        static void Projection(Api api,Kind kind,List<IntPtr> controls) {
            var template=kind.Template;
            NativeMemory.Require(controls.Count==Convert.ToInt32(template["source_native_projection_count"]),"Source native group-leaf projection count differs from the prepared archive projection.");
            int index=0;
            foreach(object value in (IEnumerable)template["source_native_projection"]) {
                var expected=(Dictionary<string,object>)value;NativeMemory.Require(index<controls.Count,"Source native projection is truncated.");
                IntPtr obj=controls[index++];var actual=api.Engine.Describe(obj);
                NativeMemory.Require(Convert.ToInt32(actual["complete_offset"])==4 && Convert.ToString(actual["rtti"])==Convert.ToString(expected["rtti"]) &&
                    NativeMemory.I32(NativeMemory.Add(obj,-4),0xC)==Convert.ToInt32(expected["type_id"]) && NativeStrategyProfile.ReadName(api.Shared,obj)==Convert.ToString(expected["name"]),
                    "Source ordered native type/name projection differs at index "+(index-1));
            }
            NativeMemory.Require(index==controls.Count,"Source native projection has unexpected extra objects.");
        }
        static void SourceUnchanged(Api api,Source source){var controls=Controls(api,source.Page);Projection(api,source.Kind,controls);NativeMemory.Require(EqualSnapshot(source.Snapshot,Snapshot(api,source.Kind,source.Complete,true)) && controls.Contains(NativeMemory.Add(source.Complete,4)),"An original source-control snapshot changed.");}
        static Dictionary<string,object> LabelSnapshot(Api api,Page target) {
            IntPtr label=IntPtr.Zero;int hits=0;
            foreach(IntPtr obj in Controls(api,target))if(NativeMemory.Ptr(obj,0)==api.Engine.Address(0xD72EC4)){label=obj;hits++;}
            NativeMemory.Require(hits==1,"Dedicated target must retain exactly one verified label.");int id=NativeStrategyProfile.ReadId(api.Shared,label);
            string caption=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(label,0xE0),4096);NativeMemory.Require(caption=="进程内控件创建验证","Retained label caption preimage differs.");
            return new Dictionary<string,object>{{"iobject",NativeMemory.Hex(label)},{"name",NativeStrategyProfile.ReadName(api.Shared,label)},{"native_id",id},{"rectangle",Rectangle(NativeMemory.Add(label,-4))},{"caption",caption}};
        }
        static void Dirty(Api api,Page target){NativeStrategyProfile.MarkRootDirty(api.Shared);api.Slot(target.Doc,27,0x3A3C8);NativeOperationTrace.BeforeMutation("standard-controls-target-set-modified");api.Bind<VoidInt>("DocSetModified")(target.Doc,1);}
        static void DiskSame(string path,string sha){NativeMemory.Require(NativeMemory.Hash(path)==sha,"Fixture changed before the explicit standard-control flush.");}
        static void SetRect(Api api,Kind kind,IntPtr control,int[] value,IntPtr expectedOwner,bool transient,string phase) {
            api.Type(kind,control);NativeMemory.Require(NativeMemory.Ptr(control,0x64)==expectedOwner && ((transient && expectedOwner==IntPtr.Zero) || (!transient && expectedOwner!=IntPtr.Zero)),"Geometry owner/lifetime precondition differs.");
            NativeMemory.Require(value.Length==4 && value[0]>=0 && value[1]>=0 && value[2]>value[0] && value[3]>value[1] && value[2]<=480 && value[3]<=272,"Standard-control rectangle exceeds dedicated page bounds.");
            IntPtr rect=Marshal.AllocHGlobal(16);try{for(int i=0;i<4;i++)Marshal.WriteInt32(rect,i*4,value[i]);NativeOperationTrace.BeforeMutation(phase);api.Bind<SetRectangle>("NativeSetRect")(control,rect,IntPtr.Zero);}finally{Marshal.FreeHGlobal(rect);}
            NativeMemory.Require(EqualRect(Rectangle(control),value),"Standard-control rectangle native readback differs.");
        }
        static Dictionary<string,object> FactoryLifecycle(Api api,Kind kind,Page target) {
            int before=Controls(api,target).Count;NativeOperationTrace.BeforeMutation("transient-"+kind.Name+"-factory");IntPtr pointer=api.CreateFromRuntimeClass(kind);NativeMemory.Require(pointer!=IntPtr.Zero,"Standard-control factory returned null.");api.Type(kind,pointer);
            NativeMemory.Require(NativeMemory.Ptr(pointer,0x64)==IntPtr.Zero,"Transient factory object unexpectedly has a document owner.");
            NativeMemory.Require(Controls(api,target).Count==before,"Transient factory unexpectedly registered itself.");Dirty(api,target);
            NativeOperationTrace.BeforeMutation("transient-"+kind.Name+"-register");api.Bind<VoidPointer>("DocAdd")(target.Doc,pointer);
            var attached=Controls(api,target);NativeMemory.Require(attached.Count==before+1 && attached.Contains(NativeMemory.Add(pointer,4)) && NativeMemory.Ptr(pointer,0x64)==target.Doc,"Transient factory registration did not establish the dedicated owner.");
            // No defaults/property calls are used. Geometry and destruction run with a verified live owner.
            SetRect(api,kind,pointer,new int[]{10,10,110,40},target.Doc,false,"transient-"+kind.Name+"-geometry");var snap=Snapshot(api,kind,pointer,true);
            api.Type(kind,pointer);NativeOperationTrace.BeforeMutation("transient-"+kind.Name+"-detach");api.Bind<VoidPointer>("DocRemove")(target.Doc,pointer);
            var detached=Controls(api,target);NativeMemory.Require(detached.Count==before && !detached.Contains(NativeMemory.Add(pointer,4)) && NativeMemory.Ptr(pointer,0x64)==target.Doc,"Transient native detach/owner postcondition differs.");api.Type(kind,pointer);
            NativeOperationTrace.BeforeMutation("transient-"+kind.Name+"-native-delete");api.Bind<Void0>("NativeDelete")(pointer);pointer=IntPtr.Zero;
            NativeMemory.Require(Controls(api,target).Count==before,"Deleting the detached factory object changed the target list.");
            return new Dictionary<string,object>{{"class",kind.Name},{"snapshot_before_delete",snap},{"native_factory_attach_geometry_detach_delete_completed",true},{"count_history",new int[]{before,before+1,before}},
                {"temporarily_registered",true},{"retained_or_saved_as_a_control",false},{"native_id_queried_while_unattached",false},{"default_binding_validated",false}};
        }
        static Dictionary<string,object> CloneTemplate(Api api,Page target,Source source,int before,int[] rectangle) {
            NativeMemory.Require(Controls(api,target).Count==before,"Standard-control target preimage count differs.");SourceUnchanged(api,source);api.Type(source.Kind,source.Complete);Dirty(api,target);
            NativeMemory.Require(NativeMemory.I32(api.Engine.Address(0xFB21F8),0)==0,"Native clone mode is already active.");NativeOperationTrace.BeforeMutation("clone-template-"+source.Kind.Name);
            IntPtr copy=api.Bind<Clone>("NativeClone")(source.Complete,target.Doc);NativeMemory.Require(copy!=IntPtr.Zero && copy!=source.Complete,"Native cross-page template clone is not distinct.");
            NativeMemory.Require(NativeMemory.I32(api.Engine.Address(0xFB21F8),0)==0,"Native clone mode did not return to its preimage.");api.Type(source.Kind,copy);
            IntPtr owner=NativeMemory.Ptr(copy,0x64);NativeMemory.Require(owner==IntPtr.Zero || owner==target.Doc,"Cross-page clone carries another page owner.");
            NativeMemory.Require(!Controls(api,target).Contains(NativeMemory.Add(copy,4)),"Native clone registered itself before DocAdd.");
            NativeOperationTrace.BeforeMutation("register-template-"+source.Kind.Name);api.Bind<VoidPointer>("DocAdd")(target.Doc,copy);
            var controls=Controls(api,target);NativeMemory.Require(controls.Count==before+1 && controls.Contains(NativeMemory.Add(copy,4)) && NativeMemory.Ptr(copy,0x64)==target.Doc,"Native standard-control registration did not establish its exact owner.");
            SetRect(api,source.Kind,copy,rectangle,target.Doc,false,"attached-template-"+source.Kind.Name+"-rectangle");var after=Snapshot(api,source.Kind,copy,true);
            NativeMemory.Require(!String.IsNullOrEmpty(Convert.ToString(after["name"])) && Convert.ToString(after["name"])!=Convert.ToString(source.Snapshot["name"]),"Native template clone did not allocate a distinct target name.");
            if(source.Kind.Name=="CDrawEdit")NativeMemory.Require(Convert.ToString(after["input_variable"])==InputVariable,"Native cross-page input clone lost its variable binding.");
            var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);foreach(IntPtr obj in controls)NativeMemory.Require(names.Add(NativeStrategyProfile.ReadName(api.Shared,obj)),"Native destination control names are not unique.");SourceUnchanged(api,source);
            return new Dictionary<string,object>{{"class",source.Kind.Name},{"source",source.Snapshot},{"source_offline_template",source.Kind.Template},{"destination",after},{"geometry_and_binding_native_readback_verified",true},{"all_payload_bytes_verified",false}};
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine);api.Project(Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));
            Page target=GetPage(api,context,31,TrialName,false);Source button=GetSource(api,context,api.Kinds["CDrawButton"]),input=GetSource(api,context,api.Kinds["CDrawEdit"]);
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"target_exists",target!=null},{"target_control_count",target==null?-1:Controls(api,target).Count},
                {"button_source",button.Snapshot},{"input_source",input.Snapshot},{"button_offline_template",button.Kind.Template},{"input_offline_template",input.Kind.Template},{"abi_guard_sha256",ProfileHash},
                {"factory_lifecycle_executed",false},{"persistent_native_clone_executed",false},{"ready_requires_retained_label_count1",true}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine);api.Project(expected);NativeMemory.Require(NativeMemory.Ptr(api.Shared.RootDoc(),0x2D4)==context.ObjectModel,"Standard-control context differs from the current native root.");
            Page target=GetPage(api,context,31,TrialName,true);NativeMemory.Require(Controls(api,target).Count==1,"Standard-control trial requires precisely the retained label and rejects retries.");
            var labelBefore=LabelSnapshot(api,target);Source button=GetSource(api,context,api.Kinds["CDrawButton"]),input=GetSource(api,context,api.Kinds["CDrawEdit"]);string diskBefore=NativeMemory.Hash(expected);
            var factories=new List<object>{FactoryLifecycle(api,button.Kind,target),FactoryLifecycle(api,input.Kind,target)};DiskSame(expected,diskBefore);
            NativeMemory.Require(EqualSnapshot(labelBefore,LabelSnapshot(api,target)),"Retained label changed during transient factory lifecycles.");SourceUnchanged(api,button);SourceUnchanged(api,input);
            var buttonCopy=CloneTemplate(api,target,button,1,new int[]{24,110,200,166});DiskSame(expected,diskBefore);
            var inputCopy=CloneTemplate(api,target,input,2,new int[]{240,110,430,166});DiskSame(expected,diskBefore);
            NativeMemory.Require(Controls(api,target).Count==3 && EqualSnapshot(labelBefore,LabelSnapshot(api,target)),"Final standard-control count or retained label snapshot differs.");SourceUnchanged(api,button);SourceUnchanged(api,input);
            Dirty(api,target);engine.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");api.Slot(context.WindowService,12,0x21733);
            NativeOperationTrace.BeforeMutation("standard-controls-new-page-save-data");bool saved=api.Bind<SaveData>("WindowSaveData")(context.WindowService,target.Object);
            int modified=api.Shared.Bind<NativeEngine.ThisInt>("RootIsModified")(target.Doc);NativeMemory.Require(saved && modified==0,"Native standard-control page saveData failed its modified-state postcondition.");
            NativeOperationTrace.SetPhase("standard-controls-readback-complete");
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",true},{"target_page_id",31},{"target_page_name",TrialName},{"count_history",new int[]{1,2,3}},{"transient_factories",factories},
                {"button_copy",buttonCopy},{"input_copy",inputCopy},{"retained_label_unchanged",true},{"source_control_snapshots_unchanged",true},{"new_page_save_data_dispatched",saved},{"new_page_modified_after_flush",modified},
                {"pending_root_save",true},{"offline_payload_preservation_verified",false},{"reopen_verified",false},{"native_check_verified",false},{"runtime_binding_or_device_execution_verified",false},
                {"disk_sha256_before",diskBefore},{"disk_sha256_after_page_flush",NativeMemory.Hash(expected)},{"abi_guard_sha256",ProfileHash}};
        }
    }
}
