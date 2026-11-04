using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    public static class EngineEntry {
        [ThreadStatic]internal static int ExpectedUiThreadId;
        public static Dictionary<string,object> PrepareRequest(Dictionary<string,object> request){return NativeRequestPipeline.Prepare(request);}
        public static Dictionary<string,object> FinalizeResponse(Dictionary<string,object> request,Dictionary<string,object> response){return NativeRequestPipeline.Finish(request,response);}
        public static Dictionary<string,object> Dispatch(Dictionary<string,object> request,object datObj,int uiThreadId) {
            NativeMemory.Require(uiThreadId>0 && NativeMemory.GetCurrentThreadId()==uiThreadId,"Engine entry is outside captured host UI thread.");
            NativeMemory.Require(ExpectedUiThreadId==0,"Nested engine entry is refused before changing the active request scope or trace.");ExpectedUiThreadId=uiThreadId;
            NativeOperationTrace.MutationAttempted=false;NativeOperationTrace.Phase="preconditions";NativeBinaryIdentity.Begin(request);
            NativeRequestPipeline.NativeStarted(request);
            try {
                NativeEngineeringProjectScope.Enter(request); NativeOperationTrace.Begin(request);
                var result=NativeOperations.Dispatch(request,datObj);
                result["write_attempted"]=NativeOperationTrace.MutationAttempted;result["operation_phase"]=NativeOperationTrace.Phase;result["vendor_binary_identity"]=NativeBinaryIdentity.Snapshot();return NativeRequestPipeline.IsPrepared(request)?result:NativeEngineeringLargeReceipt.Pack(request,result);
            } catch(Exception e) {
                return new Dictionary<string,object>{{"ok",false},{"error",e.Message},{"error_type",e.GetType().Name},{"hresult","0x"+e.HResult.ToString("X8")},
                    {"write_attempted",NativeOperationTrace.MutationAttempted},{"operation_phase",NativeOperationTrace.Phase},{"managed_stack",e.StackTrace},{"comparison_evidence",NativeEngineeringComparisonEvidence.Metadata(e)},{"vendor_binary_identity",NativeBinaryIdentity.Snapshot()},
                    {"project_writes_quarantined",true},{"writer_ready",false},{"project_write_gate_policy",NativeProjectWriteGate.Policy}};
            } finally{try{NativeEngineeringProjectScope.Exit();}finally{try{NativeOperationTrace.End(request);}finally{NativeBinaryIdentity.End();ExpectedUiThreadId=0;}}}
        }
    }
    internal static class NativeOperationTrace {
        [ThreadStatic]internal static bool MutationAttempted;
        [ThreadStatic]internal static string Phase;
        [ThreadStatic]static string operation;
        [ThreadStatic]static NativeRequestPipeline.TraceWriter writer;
        internal static void Begin(Dictionary<string,object> request) {
            object value;operation=request!=null && request.TryGetValue("op",out value)?Convert.ToString(value,CultureInfo.InvariantCulture):"";
            writer=new NativeRequestPipeline.TraceWriter(Path.Combine(NativeOperations.TaskRoot,"extensions","native-operation-trace.jsonl"));
            Record();
        }
        internal static void End(Dictionary<string,object> request){var current=writer;writer=null;NativeRequestPipeline.NativeFinished(request,current);if(current!=null&&!NativeRequestPipeline.IsPrepared(request))current.Drain();}
        internal static void BeforeMutation(string phase){MutationAttempted=true;Phase=phase;Record();}
        internal static void SetPhase(string phase){Phase=phase;Record();}
        static void Record() {
            // Capture the phase on the UI thread; the background writer publishes it.
            // The durable queue claim remains authoritative on timeout or process exit.
            var row=new Dictionary<string,object>{{"utc",DateTime.UtcNow.ToString("o",CultureInfo.InvariantCulture)},
                {"process_id",Process.GetCurrentProcess().Id},{"native_thread_id",NativeMemory.GetCurrentThreadId()},
                {"engine",typeof(NativeOperationTrace).Assembly.ManifestModule.Name},{"op",operation},{"phase",Phase},{"write_attempted",MutationAttempted}};
            if(writer!=null)writer.Add(row);
        }
    }
    internal static partial class NativeOperations {
        internal const string TaskRoot=@"D:\unbound-task-root";
        internal static Dictionary<string,object> Dispatch(Dictionary<string,object> request,object datObj) {
            NativeMemory.Require(EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Native operation is outside host UI thread.");
            NativeMemory.Require(IntPtr.Size==4,"Expected x86 editor process.");
            NativeMemory.Require(request!=null,"Expected request object.");
            string op=Text(request,"op");
            if(op=="ping")return new Dictionary<string,object>{{"ok",true},{"op",op},{"host_bits",32},{"ui_thread_id",EngineEntry.ExpectedUiThreadId},{"native_business_method_called",false},{"project_writes_quarantined",true},{"writer_ready",false},{"project_write_gate_policy",NativeProjectWriteGate.Policy}};
            string expected=Path.GetFullPath(Text(request,"expected_project"));
            string allowed=Path.GetFullPath(TaskRoot).TrimEnd('\\')+"\\";
            bool currentEngineering=op=="engineering-edit-inspect"||op=="engineering-edit-batch"||op=="engineering-project-lifecycle-read"||op=="engineering-project-close-reopen-original";
            if(!currentEngineering)NativeMemory.Require(expected.StartsWith(allowed,StringComparison.OrdinalIgnoreCase),"Legacy trial operation requires its original workspace.");
            NativeMemory.Require(File.Exists(expected),"Expected isolated project is absent.");
            string policyRefusal = NativeProjectWriteGate.RejectionReason(op);
            if (policyRefusal != null) {
                NativeOperationTrace.SetPhase("project-write-preimage-gate-refused");
                throw new InvalidOperationException(policyRefusal);
            }
            if(op=="page-owner-inspect" || op=="native-save" || op=="native-save-root-only" || op=="page-copy-test")RequirePageFixture(expected);
            if(op=="page-copy-test")RequirePageSourceId(request);
            var engine=new NativeEngine();
            NativeOperationTrace.SetPhase("native-project-identity");
            // datObj remains in the stable loader signature only; identity and business calls use native state.
            string actual=NativePageDuplicateProfile.CurrentProjectPath(engine);
            NativeMemory.Require(!String.IsNullOrEmpty(actual) && Path.GetFullPath(actual).Equals(expected,StringComparison.OrdinalIgnoreCase),"Current native project identity does not match isolated trial.");
            NativeEngineeringProjectScope.BindNativeIdentity(actual);var context=engine.Attach();
            NativeOperationTrace.SetPhase("attached");
            Dictionary<string,object> result=null;
            if(op=="native-read-tree") {
                result=new Dictionary<string,object>{{"ok",true},{"op",op},{"write_attempted",false},{"native_business_method_called",true},
                    {"engine_image_base",NativeMemory.Hex(engine.ImageBase)},{"engine_image_sha256",engine.ImageSha256},
                    {"user_window_service",NativeMemory.Hex(context.WindowService)},{"window_manager",NativeMemory.Hex(context.WindowManager)},
                    {"root",NativeMemory.Hex(context.Root)},{"nodes",engine.ReadTree(context.Root)}};
            } else DispatchAdditional(request,datObj,engine,context,ref result);
            NativeMemory.Require(result!=null,"Unsupported internal engineering operation: "+op);
            if(!result.ContainsKey("ok"))result["ok"]=true;
            result["legacy_project_writes_quarantined"]=true;result["project_writes_quarantined"]=op!="engineering-edit-batch"&&op!="engineering-project-close-reopen-original";result["writer_ready"]=(op=="engineering-edit-batch"||op=="engineering-project-close-reopen-original") && Convert.ToBoolean(result["ok"]);result["project_write_gate_policy"]=NativeProjectWriteGate.Policy;
            result["actual_project"]=actual;result["identity_source"]="native C0DocManage/CDocument path";result["internal_engineering_api"]=true;
            return result;
        }
        static partial void DispatchAdditional(Dictionary<string,object> request,object datObj,NativeEngine engine,NativeContext context,ref Dictionary<string,object> result);
        internal static string Text(Dictionary<string,object> request,string key) {
            object value;NativeMemory.Require(request.TryGetValue(key,out value),"Missing request field: "+key);
            return Convert.ToString(value,CultureInfo.InvariantCulture);
        }
        internal static void RequirePageFixture(string expected) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(Path.GetFullPath(expected).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Page operations require the exact owned fixtures/initial.MCP target.");
        }
        internal static void RequirePageSourceId(Dictionary<string,object> request) {
            object source;
            if(request.TryGetValue("source_archive_id",out source))NativeMemory.Require(Convert.ToInt32(source,CultureInfo.InvariantCulture)==2,"Page copy permits only source archive ID2.");
        }
    }

    internal sealed class NativeContext {
        internal IntPtr WindowService,WindowManager,Root,ObjectModel;
    }

    internal static class NativeMemory {
        [DllImport("kernel32.dll")]internal static extern int GetCurrentThreadId();
        [StructLayout(LayoutKind.Sequential)]struct MemoryInfo {
            public IntPtr BaseAddress,AllocationBase;public uint AllocationProtect;public UIntPtr RegionSize;public uint State,Protect,Type;
        }
        [DllImport("kernel32.dll",SetLastError=true)]static extern UIntPtr VirtualQuery(IntPtr address,out MemoryInfo info,UIntPtr length);
        internal static void Require(bool valid,string message){if(!valid)throw new InvalidOperationException(message);}
        internal static uint U(IntPtr value){return unchecked((uint)value.ToInt32());}
        internal static IntPtr Add(IntPtr pointer,int bytes) {
            long address=(long)U(pointer)+bytes;Require(address>=0 && address<=UInt32.MaxValue,"Native pointer arithmetic overflow.");return new IntPtr(unchecked((int)(uint)address));
        }
        internal static string Hex(IntPtr value){return "0x"+U(value).ToString("X8");}
        internal static void Readable(IntPtr pointer,int length) {
            Require(pointer!=IntPtr.Zero && length>=0 && length<=1024*1024,"Invalid native read range.");
            ulong cursor=U(pointer),end=cursor+(uint)length;Require(end<=UInt32.MaxValue,"Native read overflow.");
            while(cursor<end) {
                MemoryInfo info;UIntPtr size=VirtualQuery(new IntPtr(unchecked((int)(uint)cursor)),out info,new UIntPtr((uint)Marshal.SizeOf(typeof(MemoryInfo))));
                Require(size!=UIntPtr.Zero && info.State==0x1000 && (info.Protect&0x100)==0 && (info.Protect&0xFF)!=1 && info.Protect!=0,"Native range is not committed/readable.");
                ulong next=(ulong)U(info.BaseAddress)+info.RegionSize.ToUInt64();Require(next>cursor,"Native memory query did not advance.");cursor=Math.Min(next,end);
            }
        }
        internal static int I32(IntPtr value,int offset){IntPtr p=Add(value,offset);Readable(p,4);return Marshal.ReadInt32(p);}
        internal static IntPtr Ptr(IntPtr value,int offset){return new IntPtr(I32(value,offset));}
        internal static byte[] Bytes(IntPtr value,int length){Readable(value,length);var bytes=new byte[length];Marshal.Copy(value,bytes,0,length);return bytes;}
        internal static string Ascii(IntPtr value,int maximum) {
            var bytes=new List<byte>();
            for(int i=0;i<maximum;i++){Readable(Add(value,i),1);byte b=Marshal.ReadByte(value,i);if(b==0)return Encoding.ASCII.GetString(bytes.ToArray());Require(b>=32 && b<=126,"Invalid RTTI type string.");bytes.Add(b);}
            throw new InvalidOperationException("RTTI string exceeds bound.");
        }
        internal static string Hash(string path){string requestHash;if(NativeEngineeringFileHashes.TryHash(path,out requestHash))return requestHash;using(var sha=SHA256.Create())using(var file=File.Open(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))return BitConverter.ToString(sha.ComputeHash(file)).Replace("-","").ToLowerInvariant();}
    }

    internal sealed class NativeEngine {
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]internal delegate IntPtr CdeclPointer();
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]internal delegate IntPtr CdeclModule(int id);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate IntPtr ThisPointer(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate IntPtr ThisPointerPointer(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int ThisInt(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate void ThisVoid(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]internal delegate bool ThisBoolPointer(IntPtr self,IntPtr value);
        internal readonly IntPtr ImageBase;internal readonly string ImageSha256;
        readonly int imageSize,preferredBase;
        readonly Dictionary<string,Dictionary<string,object>> functions=new Dictionary<string,Dictionary<string,object>>();
        readonly Dictionary<string,Dictionary<string,object>> tables=new Dictionary<string,Dictionary<string,object>>();
        internal NativeEngine() {
            string executable=Process.GetCurrentProcess().MainModule.FileName;
            ImageBase=Process.GetCurrentProcess().MainModule.BaseAddress;
            var json=new JavaScriptSerializer();
            var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(NativeOperations.TaskRoot,"static","read-tree-guard-profile.json"),Encoding.UTF8));
            var binary=(Dictionary<string,object>)profile["binary"];
            preferredBase=Number(binary["image_base"]);ImageSha256=NativeMemory.Hash(executable);
            NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(binary["sha256"]),ImageSha256,"NativeOperations.functional:165:editor"),"Loaded editor differs from the locally derived internal ABI profile; extract its actual structure first.");
            int pe=NativeMemory.I32(ImageBase,0x3C);NativeMemory.Require(NativeMemory.I32(ImageBase,pe)==0x4550,"Invalid editor PE image.");
            imageSize=NativeMemory.I32(ImageBase,pe+24+56);NativeMemory.Require(imageSize>0 && imageSize<256*1024*1024,"Invalid editor image size.");
            foreach(object entry in (IEnumerable)profile["functions"]) {
                var item=(Dictionary<string,object>)entry;functions.Add(Convert.ToString(item["name"]),item);VerifyFunction(item);
            }
            foreach(object entry in (IEnumerable)profile["vtable_guards"]) {
                var item=(Dictionary<string,object>)entry;tables.Add(Convert.ToString(item["name"]),item);VerifyTable(item);
            }
        }
        internal static int Number(object value) {
            string text=Convert.ToString(value,CultureInfo.InvariantCulture);return text.StartsWith("0x",StringComparison.OrdinalIgnoreCase)?unchecked((int)UInt32.Parse(text.Substring(2),NumberStyles.HexNumber,CultureInfo.InvariantCulture)):Convert.ToInt32(value,CultureInfo.InvariantCulture);
        }
        internal IntPtr Address(int rva){NativeMemory.Require(rva>=0 && rva<imageSize,"RVA is outside editor image.");return NativeMemory.Add(ImageBase,rva);}
        internal int Rva(IntPtr pointer){long value=(long)NativeMemory.U(pointer)-NativeMemory.U(ImageBase);NativeMemory.Require(value>=0 && value<imageSize,"Pointer is outside editor image.");return (int)value;}
        internal IntPtr Function(string name){return Address(Number(functions[name]["rva"]));}
        internal T Bind<T>(IntPtr function)where T:class{Rva(function);NativeMemory.Readable(function,1);return Marshal.GetDelegateForFunctionPointer(function,typeof(T))as T;}
        internal T Call<T>(string name)where T:class{return Bind<T>(Function(name));}
        static byte[] ParseHex(string text){var result=new byte[text.Length/2];for(int i=0;i<result.Length;i++)result[i]=Byte.Parse(text.Substring(i*2,2),NumberStyles.HexNumber);return result;}
        void VerifyFunction(Dictionary<string,object> item) {
            var expected=ParseHex(Convert.ToString(item["expected_first_32_bytes"]));
            foreach(object offset in (IEnumerable)item["relocatable_dword_offsets_in_first32"]) {
                int at=Number(offset);uint address=unchecked(BitConverter.ToUInt32(expected,at)+NativeMemory.U(ImageBase)-(uint)preferredBase);
                Array.Copy(BitConverter.GetBytes(address),0,expected,at,4);
            }
            byte[] actual=NativeMemory.Bytes(Address(Number(item["rva"])),expected.Length);
            NativeMemory.Require(BitConverter.ToString(actual)==BitConverter.ToString(expected),"Internal function signature differs: "+item["name"]);
        }
        void VerifyTable(Dictionary<string,object> item) {
            IntPtr table=Address(Number(item["rva"]));
            NativeMemory.Require(NativeMemory.Ptr(table,-4)==Address(Number(item["col_rva"])),"RTTI COL differs: "+item["name"]);
            int i=0;foreach(object slot in (IEnumerable)item["slot_entry_rvas"]){NativeMemory.Require(NativeMemory.Ptr(table,4*i)==Address(Number(slot)),"Vtable slot differs: "+item["name"]+"/"+i);i++;}
        }
        internal void RequireTable(IntPtr instance,string name) {
            NativeMemory.Readable(instance,4);NativeMemory.Require(NativeMemory.Ptr(instance,0)==Address(Number(tables[name]["rva"])),"Unexpected native object type: "+name);
        }
        internal IntPtr Virtual(IntPtr instance,int slot) {
            NativeMemory.Require(slot>=0 && slot<=32,"Invalid IObject virtual slot.");
            IntPtr table=NativeMemory.Ptr(instance,0);Rva(table);IntPtr method=NativeMemory.Ptr(table,4*slot);Rva(method);return method;
        }
        internal NativeContext Attach() {
            IntPtr service=Call<CdeclPointer>("GetUserWindowService")();NativeMemory.Require(service!=IntPtr.Zero,"No current user-window service.");
            RequireTable(service,"UserWindowObjectManager.IUserWindowService");
            IntPtr manager=NativeMemory.Add(service,-0x34);RequireTable(manager,"UserWindowObjectManager.IObject");
            NativeMemory.Require(Call<CdeclModule>("GetModuleObject")(0)==manager,"Module getter and service RTTI disagree.");
            IntPtr root=Bind<ThisPointer>(Virtual(manager,15))(manager);RequireTable(root,"ObjectRoot.IObject");
            NativeMemory.Require(Bind<ThisInt>(Virtual(manager,20))(manager)==0,"Unexpected window module.");
            NativeMemory.Require(Bind<ThisInt>(Virtual(root,20))(root)==12 && Bind<ThisPointer>(Virtual(root,15))(root)==IntPtr.Zero,"Unexpected project-root identity.");
            IntPtr model=Call<CdeclPointer>("GetCurrentObjectModel")();RequireTable(model,"ObjectModel");
            NativeMemory.Require(Call<ThisPointer>("ObjectModel_getRoot")(model)==root,"Document model and parent root disagree.");
            return new NativeContext{WindowService=service,WindowManager=manager,Root=root,ObjectModel=model};
        }
        internal Dictionary<string,object> Describe(IntPtr instance) {
            return NativeObjectTraversal.Describe(instance,Rva,delegate(IntPtr value,int slot){return Bind<ThisInt>(Virtual(value,slot))(value);});
        }
        internal List<IntPtr> Children(IntPtr owner) {
            return NativeObjectTraversal.Children(owner,Describe,
                delegate(IntPtr iter,IntPtr value){Call<ThisPointerPointer>("IObjectIter_ctor")(iter,value);},
                delegate(IntPtr value,IntPtr iter){return Bind<ThisBoolPointer>(Virtual(value,17))(value,iter);},
                delegate(IntPtr value,IntPtr iter){return Bind<ThisBoolPointer>(Virtual(value,18))(value,iter);},
                delegate(IntPtr iter){Call<ThisVoid>("IObjectIter_dtor")(iter);});
        }
        internal List<object> ReadTree(IntPtr root) {
            var output=new List<object>();var visited=new HashSet<uint>();ReadTreeNode(root,0,"",output,visited);return output;
        }
        void ReadTreeNode(IntPtr node,int depth,string parent,List<object> output,HashSet<uint> visited) {
            NativeMemory.Require(depth<=16 && output.Count<4096,"Native tree exceeds bounded fixture size.");
            if(!visited.Add(NativeMemory.U(node))){output.Add(new Dictionary<string,object>{{"address",NativeMemory.Hex(node)},{"reference",true},{"parent",parent}});return;}
            var description=Describe(node);description["depth"]=depth;description["parent"]=parent;output.Add(description);
            foreach(IntPtr child in Children(node))ReadTreeNode(child,depth+1,NativeMemory.Hex(node),output,visited);
        }
    }
    // BEGIN_NATIVE_PROJECT_WRITE_GATE_0044
    internal static class NativeProjectWriteGate {
        internal const string Policy = "explicit-permit-candidate-legacy-writers-quarantined";
        internal const string InventorySha256 = "08df3a1bd6e3eaeab299d4c34e90de3bd0daccf0f096fd183b64eb8a6973669c";
        static readonly HashSet<string> ReadOnly = new HashSet<string>(StringComparer.Ordinal) {
            "coverage-button-references-inspect",
            "coverage-control-geometry-inspect",
            "coverage-headless-reference-rename-inspect",
            "coverage-label-base-scalars-preflight",
            "coverage-label-base-scalars-read",
            "coverage-fixed-three-metadata-preflight",
            "coverage-fixed-three-metadata-read",
            "coverage-label-base-scalars-cached-preflight",
            "coverage-label-base-scalars-cached-read",
            "coverage-label-property-metadata-preflight",
            "coverage-label-property-metadata-read",
            "coverage-live-label-inspect",
            "coverage-live-page31-flush-inspect",
            "coverage-mainctrl-persistence-inspect",
            "coverage-reference-rename-inspect",
            "coverage-references-view-inspect",
            "coverage-references-view-v2",
            "ext-control-inspect",
            "ext-page-delete-inspect",
            "ext-page-inspect",
            "ext-page-size-inspect",
            "ext-standard-controls-inspect",
            "ext-strategy-creation-inspect",
            "ext-strategy-delete-inspect",
            "ext-strategy-lifecycle-inspect",
            "ext-strategy-registration-inspect",
            "ext-strategy-source-read",
            "ext-trigger-cursor-inspect",
            "native-read-tree",
            "native-read-tree-named",
            "page-owner-inspect",
            "ping",
            "strategy-inspect",
            "strategy-source-diagnose"
        };
        static readonly HashSet<string> ProjectWriters = new HashSet<string>(StringComparer.Ordinal) {
            "coverage-headless-reference-rename-trial",
            "coverage-live-label-trial",
            "coverage-live-page31-flush",
            "coverage-mainctrl-restore",
            "coverage-reference-rename-trial",
            "ext-control-trial",
            "ext-page-create-trial",
            "ext-page-delete-trial",
            "ext-page-size-trial",
            "ext-standard-controls-trial",
            "ext-strategy-create-trial",
            "ext-strategy-delete-trial",
            "ext-strategy-registration-trial",
            "label-set-test",
            "native-save",
            "native-save-root-only",
            "page-copy-test",
            "strategy-flush-test",
            "strategy-replace-test"
        };
        internal static string RejectionReason(string operation) {
            if (operation == "engineering-edit-inspect" || operation == "engineering-edit-batch" || operation == "engineering-project-lifecycle-read" || operation == "engineering-project-close-reopen-original") return null;
            if (operation != null && ReadOnly.Contains(operation)) return null;
            if (operation != null && ProjectWriters.Contains(operation))
                return "Project write/save operation is quarantined pending a complete native preimage permit; no project mutation was entered.";
            if (operation == "coverage-property-key-cache-warmup")
                return "Cache-initialization entry is quarantined; recorded attempts must be audited before any new initialization is planned.";
            if (operation == "label-inspect")
                return "Legacy label-inspect may implicitly enter a native cache getter; use the explicit metadata preflight instead.";
            return "Operation is not in the frozen read-only allowlist; project writes remain quarantined pending a native preimage permit.";
        }
    }
    // END_NATIVE_PROJECT_WRITE_GATE_0044

}
