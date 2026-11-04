// Read-only preflight for the new strategy writer's native CDBTrigger cursor ABI.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace McgsInternalBridge {
    internal static class NativeStrategyTriggerCursorProbe {
        const string GuardSha="8dc56512ffa3340e2c210ba7eab0db1d36995a3390a535844a9a6319324e8ea6";
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr P0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr P1(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Open(IntPtr self,int type,IntPtr sql,int options);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Find(IntPtr self,IntPtr criterion);
        static T Bind<T>(NativeEngine engine,NativeStrategyExtensionProfile.ReadApi api,string name)where T:class{return engine.Bind<T>(api.Method(name));}
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(NativePageDuplicateProfile.CurrentProjectPath(engine).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Trigger cursor probe requires the exact fixture.");
            string guard=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","strategy-extension-write-guard.json");NativeMemory.Require(NativeMemory.Hash(guard)==GuardSha,"Trigger cursor probe ABI guard differs.");
            var api=new NativeStrategyExtensionProfile.ReadApi(engine,"strategy-extension-write-guard.json");IntPtr root=api.Existing.RootDoc();NativeMemory.Require(NativeMemory.Ptr(root,0x2D4)==context.ObjectModel,"Trigger cursor probe root context differs.");
            int dirty=NativeMemory.I32(root,0x48),compile=NativeMemory.I32(root,0x114);IntPtr database=NativeMemory.Add(root,0x25C);
            NativeMemory.Require(Bind<I0>(engine,api,"DatabaseIsOpen")(database)==1 && Bind<P0>(engine,api,"CurrentProjectDatabase")(root)==database,"Trigger cursor probe requires the already open current native database.");
            IntPtr info=engine.Address(0xCFEF38);NativeMemory.Require(NativeMemory.Ascii(NativeMemory.Ptr(info,0),64)=="CDBTrigger" && NativeMemory.I32(info,4)==0xBC,"Trigger record native runtime class differs.");
            IntPtr storage=Marshal.AllocHGlobal(0xBC);bool constructed=false,opened=false;var result=new Dictionary<string,object>();
            try {
                for(int i=0;i<0xBC;i++)Marshal.WriteByte(storage,i,0);
                NativeMemory.Require(Bind<P1>(engine,api,"TriggerRecordCtor")(storage,database)==storage,"Native Trigger cursor constructor returned another object.");constructed=true;api.Table(storage,"TriggerRecord");
                opened=true;Bind<Open>(engine,api,"RecordOpen")(storage,-1,IntPtr.Zero,0);
                IntPtr filter=Marshal.StringToHGlobalUni("iID = 7");
                try{NativeMemory.Require(Bind<Find>(engine,api,"RecordFind")(storage,filter)!=0,"Known read-only Trigger row7 was not found.");}finally{Marshal.FreeHGlobal(filter);}
                NativeMemory.Require(NativeMemory.I32(storage,0x98)==7 && NativeMemory.I32(storage,0x9C)==6 && NativeMemory.I32(storage,0xA0)==2,"Known Trigger row7 does not refer to original strategy6/type2.");
                IntPtr noteStorage=NativeMemory.Add(storage,0xB0),note=NativeMemory.Ptr(noteStorage,0);NativeMemory.Readable(NativeMemory.Add(note,-12),4);int length=api.Length(noteStorage);
                NativeMemory.Require(length>=0 && length<=4096 && length==NativeMemory.I32(note,-12),"Trigger note length/header differs.");NativeMemory.Readable(note,length*2+2);NativeMemory.Require(Marshal.ReadInt16(note,length*2)==0,"Trigger note lacks a native terminator.");byte[] raw=NativeMemory.Bytes(note,length*2);
                result["record_id"]=7;result["strategy_id"]=6;result["trigger_type"]=2;result["note"]=Encoding.Unicode.GetString(raw);result["note_utf16le_hex"]=BitConverter.ToString(raw).Replace("-","").ToLowerInvariant();
            }finally {
                try{if(constructed){try{if(opened){opened=false;Bind<V0>(engine,api,"RecordClose")(storage);}}finally{constructed=false;Bind<V0>(engine,api,"TriggerRecordDtor")(storage);}}}finally{Marshal.FreeHGlobal(storage);}
            }
            NativeMemory.Require(Bind<I0>(engine,api,"DatabaseIsOpen")(database)==1 && dirty==NativeMemory.I32(root,0x48) && compile==NativeMemory.I32(root,0x114),"Readonly Trigger cursor lifecycle altered database/root state.");
            result["ok"]=true;result["write_attempted"]=false;result["native_trigger_cursor_ctor_open_find_close_dtor_verified"]=true;result["native_recordset_size"]=0xBC;result["root_modified_before"]=dirty;result["root_modified_after"]=NativeMemory.I32(root,0x48);result["compile_valid_before"]=compile;result["compile_valid_after"]=NativeMemory.I32(root,0x114);result["native_database_still_open"]=true;result["factory_or_init_executed"]=false;result["abi_guard_sha256"]=GuardSha;return result;
        }
    }
}
