// Additional-source implementation; compile only until the root agent's consolidated trial.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
    internal static class NativeLabelProfile {
        const int PageTableRva=0xDED294,LabelTableRva=0xD72EC4;
        const string Before="Pro统一功能验证",After="Pro进程内接口验证";
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int NativeInt(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void SetProperty(IntPtr self,IntPtr dispatcher);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr CStringAssign(IntPtr self,IntPtr wide);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool StringDispatch(IntPtr self,IntPtr key,IntPtr value);
        [DllImport("kernel32.dll",SetLastError=true)]static extern IntPtr VirtualAlloc(IntPtr address,UIntPtr size,uint type,uint protect);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool VirtualProtect(IntPtr address,UIntPtr size,uint protection,out uint previous);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool VirtualFree(IntPtr address,UIntPtr size,uint freeType);
        [DllImport("kernel32.dll")]static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool FlushInstructionCache(IntPtr process,IntPtr address,UIntPtr size);
        sealed class Target {
            internal IntPtr Page,Label;internal int LabelId;internal string Name,Caption;
        }
        static void Method(NativeStrategyProfile.Api api,IntPtr instance,int slot,string expected) {
            NativeMemory.Require(api.Engine.Virtual(instance,slot)==api.AddressOf(expected),"Label/page native virtual entry differs: "+expected);
        }
        static Target Locate(NativeStrategyProfile.Api api,NativeContext context) {
            IntPtr page=IntPtr.Zero;int pages=0;
            foreach(IntPtr candidate in api.Engine.Children(context.WindowManager)) {
                NativeMemory.Require(NativeMemory.Ptr(candidate,0)==api.Engine.Address(PageTableRva),"Window child is not the verified UserWindowObject.");
                Method(api,candidate,9,"PageNameEntry");Method(api,candidate,14,"PageIdEntry");
                if(api.Bind<NativeInt>("PageArchiveId")(candidate)!=2)continue;
                NativeMemory.Require(NativeStrategyProfile.ReadName(api,candidate)=="首页","Window ID two has an unexpected native name.");page=candidate;pages++;
            }
            NativeMemory.Require(pages==1,"Target page identity is not unique.");
            IntPtr label=IntPtr.Zero;int labels=0;
            foreach(IntPtr candidate in api.Engine.Children(page)) {
                var description=api.Engine.Describe(candidate);
                if(Convert.ToString(description["rtti"])!=".?AVCDrawLabel@@")continue;
                NativeMemory.Require(NativeMemory.Ptr(candidate,0)==api.Engine.Address(LabelTableRva),"CDrawLabel IObject vtable differs.");
                Method(api,candidate,5,"LabelSetPropertyEntry");Method(api,candidate,9,"LabelNameEntry");Method(api,candidate,14,"LabelIdEntry");
                if(NativeStrategyProfile.ReadName(api,candidate)!="控件13")continue;
                label=candidate;labels++;
            }
            NativeMemory.Require(labels==1,"Target label name/type is not unique on the selected page.");
            string caption=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(label,0xE0),4096);
            return new Target{Page=page,Label=label,LabelId=NativeStrategyProfile.ReadId(api,label),Name="控件13",Caption=caption};
        }
        // Each object is allocated privately and exists only for one synchronous native setProperty call.
        sealed class Dispatcher : IDisposable {
            internal readonly IntPtr Instance,Vtable;IntPtr code,wide;readonly NativeStrategyProfile.Api api;readonly string expectedKey;
            StringDispatch rootedCallback;internal int StringCalls,MatchedCalls;internal readonly List<string> Errors=new List<string>();bool disposed;
            internal Dispatcher(NativeStrategyProfile.Api native,string key) {
                api=native;expectedKey=key;Instance=IntPtr.Zero;Vtable=IntPtr.Zero;
                try {
                    Instance=Marshal.AllocHGlobal(8);Vtable=Marshal.AllocHGlobal(13*4);
                    Marshal.WriteInt32(Instance,0,Vtable.ToInt32());Marshal.WriteInt32(Instance,4,0x4C424C31);wide=Marshal.StringToHGlobalUni(After);
                    rootedCallback=OnString;
                    IntPtr callback=Marshal.GetFunctionPointerForDelegate(rootedCallback);
                    var bytes=new List<byte>();var offsets=new int[13];
                    int[] clean={4,8,8,8,8,8,8,8,12,8,12,8,8};
                    for(int i=0;i<13;i++) {
                        offsets[i]=bytes.Count;
                        if(i==9) { // pop return; push ECX/self; restore return; tail-jump to StdCall(self,key,out).
                            bytes.AddRange(new byte[]{0x58,0x51,0x50,0xB8});bytes.AddRange(BitConverter.GetBytes(callback.ToInt32()));bytes.Add(0xFF);bytes.Add(0xE0);
                        }else bytes.AddRange(new byte[]{0x33,0xC0,0xC2,(byte)clean[i],0});
                    }
                    code=VirtualAlloc(IntPtr.Zero,new UIntPtr(4096),0x3000,0x04);NativeMemory.Require(code!=IntPtr.Zero,"Cannot allocate private dispatcher thunk memory.");
                    Marshal.Copy(bytes.ToArray(),0,code,bytes.Count);uint oldProtection;
                    NativeMemory.Require(VirtualProtect(code,new UIntPtr(4096),0x20,out oldProtection),"Cannot seal dispatcher thunks as RX.");
                    NativeMemory.Require(FlushInstructionCache(GetCurrentProcess(),code,new UIntPtr((uint)bytes.Count)),"Cannot publish dispatcher thunk instructions.");
                    for(int i=0;i<13;i++)Marshal.WriteInt32(Vtable,i*4,NativeMemory.Add(code,offsets[i]).ToInt32());
                }catch{Dispose();throw;}
            }
            bool OnString(IntPtr self,IntPtr key,IntPtr value) {
                try {
                    StringCalls++;
                    NativeMemory.Require(self==Instance && NativeMemory.I32(self,4)==0x4C424C31,"Dispatcher self identity differs.");
                    string name=NativeStrategyProfile.ReadBorrowedCString(key,256);if(!String.Equals(name,expectedKey,StringComparison.Ordinal))return false;
                    NativeMemory.Readable(value,4);api.Bind<CStringAssign>("CStringAssignWide")(value,wide);MatchedCalls++;return true;
                }catch(Exception error){Errors.Add(error.GetType().FullName+": "+error.Message);return false;}
            }
            public void Dispose() {
                if(disposed)return;disposed=true;
                try{GC.KeepAlive(rootedCallback);}finally{
                    if(code!=IntPtr.Zero){VirtualFree(code,UIntPtr.Zero,0x8000);code=IntPtr.Zero;}
                    if(wide!=IntPtr.Zero){Marshal.FreeHGlobal(wide);wide=IntPtr.Zero;}
                    Marshal.FreeHGlobal(Vtable);Marshal.FreeHGlobal(Instance);rootedCallback=null;
                }
            }
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new NativeStrategyProfile.Api(engine);Target target=Locate(api,context);
            using(var key=NativeStrategyProfile.CString.PropertyKey(api,45)) {
                return new Dictionary<string,object>{{"page_id",2},{"page_name","首页"},{"page_iobject",NativeMemory.Hex(target.Page)},
                    {"control_name",target.Name},{"control_native_id",target.LabelId},{"control_iobject",NativeMemory.Hex(target.Label)},
                    {"caption",target.Caption},{"caption_matches_expected_before",target.Caption==Before},{"property_id",45},{"property_key",key.Read()},{"write_attempted",false}};
            }
        }
        internal static Dictionary<string,object> Write(NativeEngine engine,NativeContext context,string expectedProject) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(Path.GetFullPath(expectedProject).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Label write is limited to its prepared isolated fixture.");
            var api=new NativeStrategyProfile.Api(engine);Target target=Locate(api,context);NativeMemory.Require(target.Caption==Before,"Native label caption preimage differs.");
            string diskBefore=NativeMemory.Hash(fixture);bool attempted=false;string phase="dispatcher-preparation";
            using(var key=NativeStrategyProfile.CString.PropertyKey(api,45))using(var dispatcher=new Dispatcher(api,key.Read())) {
                try {
                    phase="mark-root-dirty";attempted=true;int modifiedBefore=NativeStrategyProfile.MarkRootDirty(api);
                    phase="native-label-setProperty";NativeOperationTrace.SetPhase("label-set-property");engine.Bind<SetProperty>(engine.Virtual(target.Label,5))(target.Label,dispatcher.Instance);
                    phase="native-label-readback";string caption=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(target.Label,0xE0),4096);
                    NativeMemory.Require(dispatcher.Errors.Count==0,"Managed dispatcher callback reported: "+String.Join("; ",dispatcher.Errors.ToArray()));
                    NativeMemory.Require(dispatcher.MatchedCalls==1 && caption==After,"Native label setter did not produce the expected caption exactly once.");
                    NativeOperationTrace.SetPhase("verified");
                    return new Dictionary<string,object>{{"ok",true},{"write_attempted",true},{"phase","native-label-readback-complete"},{"page_id",2},{"page_name","首页"},
                        {"control_name",target.Name},{"control_native_id",target.LabelId},{"control_iobject",NativeMemory.Hex(target.Label)},{"property_id",45},{"property_key",key.Read()},
                        {"caption_before",Before},{"caption_after",caption},{"string_dispatch_calls",dispatcher.StringCalls},{"matched_dispatch_calls",dispatcher.MatchedCalls},
                        {"root_modified_before",modifiedBefore},{"root_modified_after",1},{"compile_valid_after",0},{"native_business_method_called",true},
                        {"native_save_verified",false},{"native_compile_verified",false},{"undo_verified",false},{"disk_unchanged_before_save",NativeMemory.Hash(fixture)==diskBefore}};
                }catch(Exception error){error.Data["write_attempted"]=attempted;error.Data["phase"]=phase;throw;}
            }
        }
    }
}
