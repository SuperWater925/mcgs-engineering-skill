// Additional source only. No queue submission, host activation or GUI actions.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class NativeControlExtensionProfile {
        const string GuardSha="ddb36d9e4734ebbe2cdb7365f3aaaa6a0122571994233332b7e98fd3e870df01";
        const string PageName="Codex控件接口试验", Caption="进程内控件创建验证";
        const int PageId=31,PageCount=13,LabelPrimary=0xD72D8C,LabelObject=0xD72EC4,PageTable=0xDED294,DocTable=0xDC4D94;
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create();
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr Clone(IntPtr self,IntPtr doc);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Void0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VoidPointer(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VoidInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void SetRect(IntPtr self,IntPtr rectangle,IntPtr auxiliary);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool SaveData(IntPtr self,IntPtr page);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr CStringAssign(IntPtr self,IntPtr wide);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool StringDispatch(IntPtr self,IntPtr key,IntPtr value);
        [DllImport("kernel32.dll",SetLastError=true)]static extern IntPtr VirtualAlloc(IntPtr address,UIntPtr size,uint type,uint protect);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool VirtualProtect(IntPtr address,UIntPtr size,uint protection,out uint previous);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool VirtualFree(IntPtr address,UIntPtr size,uint freeType);
        [DllImport("kernel32.dll")]static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool FlushInstructionCache(IntPtr process,IntPtr address,UIntPtr size);

        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeStrategyProfile.Api Shared;
            readonly Dictionary<string,Dictionary<string,object>> functions=new Dictionary<string,Dictionary<string,object>>();
            internal Api(NativeEngine engine) {
                Engine=engine;Thread();Shared=new NativeStrategyProfile.Api(engine);
                string path=Path.Combine(NativeOperations.TaskRoot,"extensions","control","control-abi-guard-v2.json");
                NativeMemory.Require(NativeMemory.Hash(path)==GuardSha,"Control ABI guard profile hash differs.");
                var profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
                NativeMemory.Require(engine.ImageSha256==Convert.ToString(profile["binary_sha256"]),"Control native ABI was derived from a different actual editor binary.");
                foreach(object value in (IEnumerable)profile["functions"]) {
                    var f=(Dictionary<string,object>)value;functions.Add(Convert.ToString(f["name"]),f);Verify(f);
                }
            }
            internal void Thread(){NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Control operation is outside the captured x86 host UI thread.");}
            internal void Project(string expected) {
                Thread();string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
                NativeMemory.Require(Path.GetFullPath(expected).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Control trial requires the exact owned fixture.");
                NativeMemory.Require(NativePageDuplicateProfile.CurrentProjectPath(Engine).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Current native project differs from the control fixture.");
            }
            void Verify(Dictionary<string,object> f) {
                int rva=NativeEngine.Number(f["rva"]);string hex=Convert.ToString(f["first32"]);byte[] want=new byte[hex.Length/2];
                for(int i=0;i<want.Length;i++)want[i]=Byte.Parse(hex.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                foreach(object value in (IEnumerable)f["relocations"]) {
                    int at=NativeEngine.Number(value);uint actual=unchecked(BitConverter.ToUInt32(want,at)+NativeMemory.U(Engine.ImageBase)-0x400000U);
                    Array.Copy(BitConverter.GetBytes(actual),0,want,at,4);
                }
                NativeMemory.Require(BitConverter.ToString(want)==BitConverter.ToString(NativeMemory.Bytes(Engine.Address(rva),want.Length)),"Control method bytes differ: "+f["name"]);
            }
            internal T Bind<T>(string name)where T:class {Project(Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));var f=functions[name];Verify(f);return Engine.Bind<T>(Engine.Address(NativeEngine.Number(f["rva"])));}
            internal void Slot(IntPtr obj,int slot,int entryRva) {Thread();NativeMemory.Require(Engine.Virtual(obj,slot)==Engine.Address(entryRva),"Control virtual entry differs at slot "+slot);}
            internal void Label(IntPtr complete) {
                Thread();NativeMemory.Readable(complete,0x188);
                NativeMemory.Require(NativeMemory.Ptr(complete,0)==Engine.Address(LabelPrimary) && NativeMemory.Ptr(complete,4)==Engine.Address(LabelObject),"Expected the verified complete CDrawLabel with IObject at +4.");
                var info=Engine.Describe(NativeMemory.Add(complete,4));NativeMemory.Require(Convert.ToString(info["rtti"])==".?AVCDrawLabel@@","Control RTTI differs.");
                Slot(complete,0,0x3EF27);Slot(complete,21,0x459F8);Slot(complete,27,0x46CCC);Slot(complete,28,0x33A2D);Slot(complete,29,0x1ACD);
                Slot(NativeMemory.Add(complete,4),5,0x3B895);
            }
        }
        sealed class Target {internal IntPtr Page,Doc;internal List<IntPtr> Controls;}
        static Target Locate(Api api,NativeContext context,bool requireEmpty) {
            int total=0,hits=0;IntPtr found=IntPtr.Zero;
            foreach(IntPtr page in api.Engine.Children(context.WindowManager)) {
                total++;NativeMemory.Require(NativeMemory.Ptr(page,0)==api.Engine.Address(PageTable),"Window object class differs.");
                int id=api.Bind<NativeEngine.ThisInt>("PageArchiveId")(page);string name=NativeStrategyProfile.ReadName(api.Shared,page);
                if(name!=PageName)continue;NativeMemory.Require(id==PageId,"Dedicated control page archive ID differs.");found=page;hits++;
            }
            NativeMemory.Require(total==PageCount && hits==1,"Control trial requires exactly13 pages and one dedicated new page.");
            var controls=new List<IntPtr>(api.Engine.Children(found));
            IntPtr doc=NativeMemory.Ptr(found,0x14);NativeMemory.Readable(doc,0x2D4);
            NativeMemory.Require(NativeMemory.Ptr(doc,0)==api.Engine.Address(DocTable),"Dedicated page is not the verified C0DocUser.");
            NativeMemory.Require(NativeMemory.I32(doc,0x258)==PageId && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(doc,0x25C),256)==PageName,"Loaded control-page document identity differs.");
            if(requireEmpty)NativeMemory.Require(controls.Count==0,"Control trial preimage requires an empty dedicated page; no automatic retry is allowed.");
            return new Target{Page=found,Doc=doc,Controls=controls};
        }
        static int[] Rect(IntPtr complete) {return new int[]{NativeMemory.I32(complete,0x80),NativeMemory.I32(complete,0x84),NativeMemory.I32(complete,0x88),NativeMemory.I32(complete,0x8C)};}
        static bool EqualRect(int[] a,int[] b){if(a.Length!=4||b.Length!=4)return false;for(int i=0;i<4;i++)if(a[i]!=b[i])return false;return true;}
        static bool SameLabel(Dictionary<string,object> a,Dictionary<string,object> b) {
            foreach(string key in new string[]{"rtti","complete","iobject","name","native_id","native_id_status","caption","owner_doc"})if(!Object.Equals(a[key],b[key]))return false;
            return EqualRect((int[])a["rectangle"],(int[])b["rectangle"]);
        }
        static Dictionary<string,object> Describe(Api api,IntPtr complete) {
            api.Label(complete);IntPtr obj=NativeMemory.Add(complete,4);int id=NativeStrategyProfile.ReadId(api.Shared,obj);
            NativeMemory.Require(id>=0 || id==-2,"Native label ID returned an unclassified negative value.");
            return new Dictionary<string,object>{{"rtti",".?AVCDrawLabel@@"},{"complete",NativeMemory.Hex(complete)},{"iobject",NativeMemory.Hex(obj)},
                {"name",NativeStrategyProfile.ReadName(api.Shared,obj)},{"native_id",id},{"native_id_status",id>=0?"assigned":id==-2?"unassigned_lookup_sentinel":"unexpected_negative"},
                {"rectangle",Rect(complete)},{"caption",NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(complete,0xE4),4096)},
                {"owner_doc",NativeMemory.Hex(NativeMemory.Ptr(complete,0x64))}};
        }
        static void Rectangle(Api api,IntPtr label,int[] value,string phase) {
            api.Label(label);NativeMemory.Require(NativeMemory.Ptr(label,0x64)!=IntPtr.Zero,"Geometry setter requires a registered owner in this trial.");NativeMemory.Require(value.Length==4 && value[0]>=0 && value[1]>=0 && value[2]>value[0] && value[3]>value[1] && value[2]<=480 && value[3]<=272,"Control rectangle is outside the fixed trial bounds.");
            IntPtr rect=Marshal.AllocHGlobal(16);
            try {for(int i=0;i<4;i++)Marshal.WriteInt32(rect,i*4,value[i]);NativeOperationTrace.BeforeMutation(phase);api.Bind<SetRect>("LabelSetRect")(label,rect,IntPtr.Zero);}
            finally{Marshal.FreeHGlobal(rect);}
            NativeMemory.Require(EqualRect(Rect(label),value),"Native label rectangle readback differs.");
        }
        static List<IntPtr> Controls(Api api,Target target,int expected) {
            var all=new List<IntPtr>(api.Engine.Children(target.Page));NativeMemory.Require(all.Count==expected,"Dedicated page control count differs.");return all;
        }
        static bool Contains(List<IntPtr> all,IntPtr complete){return all.Contains(NativeMemory.Add(complete,4));}
        static void Dirty(Api api,Target target) {
            NativeStrategyProfile.MarkRootDirty(api.Shared);api.Slot(target.Doc,27,0x3A3C8);
            NativeOperationTrace.BeforeMutation("control-page-set-modified");api.Bind<VoidInt>("DocSetModified")(target.Doc,1);
        }
        static void DiskUnchanged(string project,string sha){NativeMemory.Require(NativeMemory.Hash(project)==sha,"Fixture changed during the control trial before its explicit flush.");}

        // Same verified 13-slot IPropertyDispatcher shape as the prior real label trial.
        // Only property45 string is accepted; every other typed request returns false.
        sealed class Dispatcher : IDisposable {
            internal IntPtr Instance,Vtable;IntPtr code,wide;readonly Api api;readonly string key;StringDispatch callback;bool disposed;
            internal int Matches;internal readonly List<string> Errors=new List<string>();
            internal Dispatcher(Api value,string expectedKey) {
                api=value;key=expectedKey;
                try {
                    Instance=Marshal.AllocHGlobal(8);Vtable=Marshal.AllocHGlobal(52);Marshal.WriteInt32(Instance,0,Vtable.ToInt32());Marshal.WriteInt32(Instance,4,0x43545831);
                    wide=Marshal.StringToHGlobalUni(Caption);callback=OnString;IntPtr address=Marshal.GetFunctionPointerForDelegate(callback);
                    var bytes=new List<byte>();var offsets=new int[13];int[] clean={4,8,8,8,8,8,8,8,12,8,12,8,8};
                    for(int i=0;i<13;i++){offsets[i]=bytes.Count;if(i==9){bytes.AddRange(new byte[]{0x58,0x51,0x50,0xB8});bytes.AddRange(BitConverter.GetBytes(address.ToInt32()));bytes.AddRange(new byte[]{0xFF,0xE0});}else bytes.AddRange(new byte[]{0x33,0xC0,0xC2,(byte)clean[i],0});}
                    code=VirtualAlloc(IntPtr.Zero,new UIntPtr(4096),0x3000,0x04);NativeMemory.Require(code!=IntPtr.Zero,"Cannot allocate private control dispatcher thunks.");
                    Marshal.Copy(bytes.ToArray(),0,code,bytes.Count);uint old;NativeMemory.Require(VirtualProtect(code,new UIntPtr(4096),0x20,out old),"Cannot seal private control dispatcher thunks.");
                    NativeMemory.Require(FlushInstructionCache(GetCurrentProcess(),code,new UIntPtr((uint)bytes.Count)),"Cannot publish private control dispatcher thunks.");
                    for(int i=0;i<13;i++)Marshal.WriteInt32(Vtable,i*4,NativeMemory.Add(code,offsets[i]).ToInt32());
                }catch{Dispose();throw;}
            }
            bool OnString(IntPtr self,IntPtr nativeKey,IntPtr output) {
                try {api.Thread();NativeMemory.Require(self==Instance && NativeMemory.I32(self,4)==0x43545831,"Control dispatcher self differs.");
                    if(NativeStrategyProfile.ReadBorrowedCString(nativeKey,256)!=key)return false;
                    NativeMemory.Readable(output,4);api.Shared.Bind<CStringAssign>("CStringAssignWide")(output,wide);Matches++;return true;
                }catch(Exception e){Errors.Add(e.GetType().FullName+": "+e.Message);return false;}
            }
            public void Dispose(){if(disposed)return;disposed=true;GC.KeepAlive(callback);if(code!=IntPtr.Zero){VirtualFree(code,UIntPtr.Zero,0x8000);code=IntPtr.Zero;}if(wide!=IntPtr.Zero){Marshal.FreeHGlobal(wide);wide=IntPtr.Zero;}Marshal.FreeHGlobal(Vtable);Marshal.FreeHGlobal(Instance);callback=null;}
        }

        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine);string fixture=Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP");api.Project(fixture);
            bool exists=false;int pageCount=0;
            foreach(IntPtr page in engine.Children(context.WindowManager)) {pageCount++;if(NativeStrategyProfile.ReadName(api.Shared,page)==PageName)exists=true;}
            if(!exists)return new Dictionary<string,object>{{"ok",true},{"target_exists",false},{"page_count",pageCount},{"required_page_id",PageId},{"required_page_name",PageName},
                {"requires_dedicated_empty_page_before_trial",true},{"ready_for_mutation",false},{"write_attempted",false},{"abi_guard_sha256",GuardSha},
                {"implemented_types",new string[]{"CDrawLabel"}},{"standard_button_and_input_box_verified",false}};
            Target target=Locate(api,context,false);var items=new List<object>();foreach(IntPtr item in target.Controls)items.Add(Describe(api,NativeMemory.Add(item,-4)));
            return new Dictionary<string,object>{{"ok",true},{"target_exists",true},{"page_id",PageId},{"page_name",PageName},{"page_iobject",NativeMemory.Hex(target.Page)},{"page_document",NativeMemory.Hex(target.Doc)},
                {"control_count",target.Controls.Count},{"controls",items},{"requires_empty_before_trial",true},{"write_attempted",false},{"abi_guard_sha256",GuardSha},
                {"implemented_types",new string[]{"CDrawLabel"}},{"standard_button_and_input_box_verified",false}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine);api.Project(expected);Target target=Locate(api,context,true);string diskBefore=NativeMemory.Hash(expected);
            var countHistory=new List<int>{0};var operations=new List<object>();
            // Any partial failure propagates immediately; there is no retry or guessed rollback.
            NativeOperationTrace.BeforeMutation("control-create-label");IntPtr created=api.Bind<Create>("LabelFactory")();NativeMemory.Require(created!=IntPtr.Zero,"Native label factory returned null.");api.Label(created);
            NativeMemory.Require(NativeMemory.Ptr(created,0x64)==IntPtr.Zero,"Fresh native label unexpectedly has an owner.");
            // Native defaults base820680 unconditionally dereferences owner+64 at82085A.
            // Match the native lifetime: attach first, then perform owner-dependent calls.
            DiskUnchanged(expected,diskBefore);Dirty(api,target);api.Label(created);
            NativeOperationTrace.BeforeMutation("control-add-created-label-before-owner-dependent-calls");api.Bind<VoidPointer>("DocAddControl")(target.Doc,created);
            NativeMemory.Require(Contains(Controls(api,target,1),created) && NativeMemory.Ptr(created,0x64)==target.Doc,"Native created-label registration did not establish its exact owner.");countHistory.Add(1);
            api.Label(created);NativeMemory.Require(NativeMemory.Ptr(created,0x64)==target.Doc,"Native defaults require the attached dedicated page owner.");
            NativeOperationTrace.BeforeMutation("control-apply-native-default-font-attached");api.Bind<VoidInt>("LabelApplyDefaults")(created,6);
            Rectangle(api,created,new int[]{24,24,344,84},"control-created-rectangle");
            NativeMemory.Require(NativeMemory.Ptr(created,0x64)==target.Doc,"Caption setter requires the attached dedicated page owner.");
            using(var property=NativeStrategyProfile.CString.PropertyKey(api.Shared,45))using(var dispatcher=new Dispatcher(api,property.Read())) {
                NativeOperationTrace.BeforeMutation("control-created-caption-property45");api.Bind<VoidPointer>("LabelSetProperty")(NativeMemory.Add(created,4),dispatcher.Instance);
                NativeMemory.Require(dispatcher.Matches==1 && dispatcher.Errors.Count==0,"Created-label native caption dispatcher did not match exactly once.");
            }
            NativeMemory.Require(NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(created,0xE4),4096)==Caption,"Created-label native caption readback differs.");
            DiskUnchanged(expected,diskBefore);api.Label(created);
            NativeMemory.Require(Contains(Controls(api,target,1),created) && NativeMemory.Ptr(created,0x64)==target.Doc,"Attached created-label identity changed during configuration.");
            var original=Describe(api,created);operations.Add(new Dictionary<string,object>{{"operation","native-create-and-register"},{"result",original}});
            DiskUnchanged(expected,diskBefore);api.Project(expected);api.Label(created);
            NativeMemory.Require(NativeMemory.I32(engine.Address(0xFB21F8),0)==0,"Native control-clone serializer mode is already active.");
            NativeOperationTrace.BeforeMutation("control-native-deep-clone");IntPtr copy=api.Bind<Clone>("LabelClone")(created,target.Doc);
            NativeMemory.Require(NativeMemory.I32(engine.Address(0xFB21F8),0)==0,"Native control-clone serializer mode did not return to its preimage.");
            NativeMemory.Require(copy!=IntPtr.Zero && copy!=created,"Native clone did not return a distinct object.");api.Label(copy);
            NativeMemory.Require(!Contains(Controls(api,target,1),copy),"Native clone unexpectedly attached itself before registration.");
            NativeMemory.Require(EqualRect(Rect(copy),Rect(created)) && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(copy,0xE4),4096)==Caption,"Native cloned label differs in geometry or caption.");
            string sourceName=NativeStrategyProfile.ReadName(api.Shared,NativeMemory.Add(created,4)),copyName=NativeStrategyProfile.ReadName(api.Shared,NativeMemory.Add(copy,4));
            NativeMemory.Require(!String.IsNullOrEmpty(sourceName) && !String.IsNullOrEmpty(copyName) && sourceName!=copyName,"Native clone did not generate a distinct nonempty control name.");
            Dirty(api,target);NativeOperationTrace.BeforeMutation("control-register-clone");api.Bind<VoidPointer>("DocAddControl")(target.Doc,copy);
            NativeMemory.Require(Contains(Controls(api,target,2),created) && Contains(Controls(api,target,2),copy) && NativeMemory.Ptr(copy,0x64)==target.Doc,"Native clone registration failed.");countHistory.Add(2);
            operations.Add(new Dictionary<string,object>{{"operation","native-clone-and-register"},{"result",Describe(api,copy)}});
            DiskUnchanged(expected,diskBefore);api.Project(expected);Dirty(api,target);Rectangle(api,copy,new int[]{50,110,430,180},"control-clone-position-size");
            NativeMemory.Require(EqualRect(Rect(created),new int[]{24,24,344,84}),"Changing the cloned label moved the source.");
            var copyBeforeDelete=Describe(api,copy);operations.Add(new Dictionary<string,object>{{"operation","native-position-size"},{"result",copyBeforeDelete}});
            DiskUnchanged(expected,diskBefore);api.Project(expected);api.Label(copy);Dirty(api,target);NativeOperationTrace.BeforeMutation("control-remove-native-clone");api.Bind<VoidPointer>("DocRemoveControl")(target.Doc,copy);
            var remaining=Controls(api,target,1);NativeMemory.Require(Contains(remaining,created) && !Contains(remaining,copy),"Native clone removal did not leave precisely the created label.");countHistory.Add(1);
            api.Label(copy);NativeOperationTrace.BeforeMutation("control-delete-detached-clone");api.Bind<Void0>("LabelDelete")(copy);copy=IntPtr.Zero;
            var final=Describe(api,created);NativeMemory.Require(SameLabel(original,final),"Preserved created label snapshot changed during clone deletion.");
            operations.Add(new Dictionary<string,object>{{"operation","native-detach-and-delete-clone"},{"remaining_created_label",final}});
            DiskUnchanged(expected,diskBefore);api.Project(expected);Dirty(api,target);
            engine.RequireTable(context.WindowService,"UserWindowObjectManager.IUserWindowService");api.Slot(context.WindowService,12,0x21733);
            int dirtyBefore=api.Shared.Bind<NativeEngine.ThisInt>("RootIsModified")(target.Doc);NativeMemory.Require(dirtyBefore==1,"Dedicated page was not marked for native persistence.");
            NativeOperationTrace.BeforeMutation("control-trial-page-save-data");bool flushed=api.Bind<SaveData>("WindowSaveData")(context.WindowService,target.Page);
            int dirtyAfter=api.Shared.Bind<NativeEngine.ThisInt>("RootIsModified")(target.Doc);NativeMemory.Require(flushed && dirtyAfter==0,"Native dedicated-page saveData did not clear its modified state.");
            NativeMemory.Require(Contains(Controls(api,target,1),created),"Dedicated-page native flush lost the created label.");NativeOperationTrace.SetPhase("control-trial-native-readback-complete");
            return new Dictionary<string,object>{{"ok",true},{"page_id",PageId},{"page_name",PageName},{"page_iobject",NativeMemory.Hex(target.Page)},{"page_document",NativeMemory.Hex(target.Doc)},
                {"control_count_history",countHistory},{"operations",operations},{"created_label",final},{"deleted_clone_before_delete",copyBeforeDelete},
                {"native_create_verified",true},{"native_clone_geometry_caption_identity_verified",true},{"native_clone_payload_bytes_verified",false},{"native_position_size_verified",true},{"native_detach_delete_verified",true},{"original_label_snapshot_unchanged",true},
                {"page_save_data_dispatched",flushed},{"page_modified_before_flush",dirtyBefore},{"page_modified_after_flush",dirtyAfter},
                {"pending_root_save",true},{"reopen_persistence_verified",false},{"native_check_verified",false},{"runtime_build_verified",false},{"undo_verified",false},
                {"disk_sha256_before",diskBefore},{"disk_sha256_after_page_flush",NativeMemory.Hash(expected)},{"abi_guard_sha256",GuardSha},{"write_attempted",true}};
        }
    }
}
