// Read-only extension: no native writes, no action constructors, no private ABI slot guesses.
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
    internal static class NativeStrategyExtensionProfile {
        const int ManagerRva=0xDDD094,BlockRva=0xE3B4DC;
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int CStringLength(IntPtr self);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr GetModuleHandleW(string name);
        [DllImport("kernel32.dll",EntryPoint="GetProcAddress")]static extern IntPtr GetProcAddressOrdinal(IntPtr module,IntPtr ordinal);

        internal sealed class ReadApi {
            internal readonly NativeEngine Engine;
            internal readonly NativeStrategyProfile.Api Existing;
            internal CStringLength Length {get{return functions.Bind<CStringLength>("CStringGetLength");}}
            readonly Dictionary<string,Dictionary<string,object>> tables=new Dictionary<string,Dictionary<string,object>>();
            readonly NativeLazyFunctionProfile functions;
            readonly string relative;
            bool tablesLoaded;
            internal ReadApi(NativeEngine engine):this(engine,"strategy-extension-read-guard.json") {}
            internal ReadApi(NativeEngine engine,string profileName) {
                Engine=engine;Existing=new NativeStrategyProfile.Api(engine);
                string sha;
                switch(profileName.Replace((char)92,'/')){
                    case "strategy-extension-read-guard.json":sha="f2f48e10cbed6217ac968af7e2c94ef668ebe9650cf8300a7d4c350af83c51f7";break;
                    case "strategy-extension-write-guard.json":sha="8dc56512ffa3340e2c210ba7eab0db1d36995a3390a535844a9a6319324e8ea6";break;
                    case "registration/registration-abi-guard.json":sha="31479a50b9ee412815f30791be6610b05ecc50d868e23ad292f41be6eb99f403";break;
                    case "delete/strategy-delete-abi-profile.json":sha="b03866d74291d74f13427e529d6a49e70da41f2e672c2beb602b10a8fe99dbd4";break;
                    default:throw new InvalidOperationException("Strategy read ABI path has no explicit compiled declaration.");
                }
                relative="extensions/strategy/"+profileName.Replace((char)92,'/');
                functions=new NativeLazyFunctionProfile(engine,relative,sha,"editor");
            }
            Dictionary<string,object> GuardTable(string name){
                if(!tablesLoaded){var profile=functions.Profile;NativeMemory.Require(Convert.ToInt32(profile["schema"])==1,"Unknown strategy read profile.");foreach(object value in (IEnumerable)profile["tables"]){var row=(Dictionary<string,object>)value;tables.Add(Convert.ToString(row["name"]),row);}tablesLoaded=true;}
                Dictionary<string,object> item;if(!tables.TryGetValue(name,out item))throw new NativeAbiUnavailableException("Missing requested strategy native table: "+name,relative,name);
                NativeAbiTargetProfiles.CheckFields(item,"vtable identity",relative,"rva","col_rva");
                IntPtr table=Engine.Address(NativeEngine.Number(item["rva"]));
                NativeMemory.Require(NativeMemory.Ptr(table,-4)==Engine.Address(NativeEngine.Number(item["col_rva"])),"Strategy read RTTI COL differs: "+name);
                
                return item;
            }
            internal bool HasTable(IntPtr instance,string name) {var table=GuardTable(name);return NativeMemory.Ptr(instance,0)==Engine.Address(NativeEngine.Number(table["rva"]));}
            internal IntPtr Method(string name){return functions.Address(name);}
            internal void Table(IntPtr instance,string name) {NativeMemory.Require(HasTable(instance,name),"Strategy native object table differs: "+name);}
            internal string MfcType(IntPtr instance) {
                IntPtr table=NativeMemory.Ptr(instance,0);Engine.Rva(table);IntPtr col=NativeMemory.Ptr(table,-4);Engine.Rva(col);
                NativeMemory.Require(NativeMemory.I32(col,4)==0,"Strategy source candidate has unexpected complete-object offset.");
                IntPtr type=NativeMemory.Ptr(col,12);Engine.Rva(type);return NativeMemory.Ascii(NativeMemory.Add(type,8),256);
            }
        }
        static byte[] Unhex(string value){var bytes=new byte[value.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(value.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);return bytes;}
        static string Hex(byte[] value){return BitConverter.ToString(value).Replace("-","").ToLowerInvariant();}
        static string Hash(byte[] value){using(var algorithm=SHA256.Create())return Hex(algorithm.ComputeHash(value));}

        internal static List<IntPtr> Rows(ReadApi api,IntPtr block) {
            IntPtr array=NativeMemory.Add(block,0x1C);api.Table(array,"RowArray");int count=NativeMemory.I32(array,8);
            NativeMemory.Require(count>=0 && count<=1024,"Strategy row count exceeds read bound.");
            IntPtr data=NativeMemory.Ptr(array,4);if(count!=0)NativeMemory.Readable(data,checked(count*4));
            var rows=new List<IntPtr>();var unique=new HashSet<uint>();
            for(int i=0;i<count;i++) {
                IntPtr row=NativeMemory.Ptr(data,i*4);NativeMemory.Require(row!=IntPtr.Zero && unique.Add(NativeMemory.U(row)),"Empty or repeated strategy row pointer.");
                api.Table(row,"Row");NativeMemory.Require(api.MfcType(row)==".?AVCStrategyRow@@","Strategy row RTTI differs.");rows.Add(row);
            }
            return rows;
        }
        internal static Dictionary<string,object> ReadProgram(ReadApi api,IntPtr program,int blockId,string blockName,int rowIndex) {
            api.Table(program,"Prog");NativeMemory.Require(api.MfcType(program)==".?AVCStgyFuncProg@@","Program RTTI differs.");
            IntPtr source=NativeMemory.Add(program,0x20),text=NativeMemory.Ptr(source,0);NativeMemory.Readable(NativeMemory.Add(text,-12),4);
            int length=api.Length(source);NativeMemory.Require(length>=0 && length<=131072,"Program source exceeds 128K UTF16 read bound.");
            NativeMemory.Require(length==NativeMemory.I32(text,-12),"CString native length/header disagree.");
            NativeMemory.Readable(text,checked(length*2+2));NativeMemory.Require(Marshal.ReadInt16(text,length*2)==0,"Native CString lacks length-anchored terminator.");
            byte[] raw=NativeMemory.Bytes(text,length*2);
            return new Dictionary<string,object>{{"block_id",blockId},{"block_name",blockName},{"native_row_index",rowIndex},{"native_function_address",NativeMemory.Hex(program)},
                {"source",Encoding.Unicode.GetString(raw)},{"source_utf16le_hex",Hex(raw)},{"source_utf16_code_units",length},{"source_utf16le_sha256",Hash(raw)},
                {"source_read_kind","guarded canonical CStgyFuncProg+0x20 CString exact length; no FindText"}};
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(String.Equals(Path.GetFullPath(NativePageDuplicateProfile.CurrentProjectPath(engine)),fixture,StringComparison.OrdinalIgnoreCase),"Strategy extension is limited to the isolated fixture.");
            var api=new ReadApi(engine);IntPtr root=api.Existing.RootDoc();int rootBefore=NativeMemory.I32(root,0x48),compileBefore=NativeMemory.I32(root,0x114);
            IntPtr manager=engine.Call<NativeEngine.CdeclModule>("GetModuleObject")(3);
            NativeMemory.Require(NativeMemory.Ptr(manager,0)==engine.Address(ManagerRva),"Strategy manager table differs.");
            var blocks=new List<object>();var programs=new List<object>();var seen=new HashSet<int>();int unknown=0;
            foreach(IntPtr block in engine.Children(manager)) {
                NativeMemory.Require(NativeMemory.Ptr(block,0)==engine.Address(BlockRva),"Strategy block IObject table differs.");
                api.Existing.MatchVirtual(block,9,"StartupName");api.Existing.MatchVirtual(block,14,"StartupId");api.Existing.MatchVirtual(block,20,"StrategyModule");
                int id=NativeStrategyProfile.ReadId(api.Existing,block);string name=NativeStrategyProfile.ReadName(api.Existing,block);
                NativeMemory.Require(seen.Add(id),"Strategy ID is not unique.");int dirtyBefore=Marshal.ReadByte(NativeMemory.Add(block,0x60));NativeMemory.Require(dirtyBefore<=1,"Unexpected block dirty flag.");
                List<IntPtr> rows=Rows(api,block);var functionTypes=new List<object>();int sourceCount=0;
                for(int i=0;i<rows.Count;i++) {
                    IntPtr function=NativeMemory.Ptr(rows[i],8);NativeMemory.Require(function!=IntPtr.Zero,"Strategy row has no native function.");
                    string type=api.MfcType(function);functionTypes.Add(new Dictionary<string,object>{{"native_row_index",i},{"function",NativeMemory.Hex(function)},{"rtti",type}});
                    if(api.HasTable(function,"Prog")){programs.Add(ReadProgram(api,function,id,name,i));sourceCount++;}else unknown++;
                }
                NativeMemory.Require(rows.Count==Rows(api,block).Count && dirtyBefore==Marshal.ReadByte(NativeMemory.Add(block,0x60)),"Strategy rows/dirty state changed during read.");
                blocks.Add(new Dictionary<string,object>{{"block_id",id},{"block_name",name},{"block_iobject",NativeMemory.Hex(block)},{"native_row_count",rows.Count},{"direct_program_count",sourceCount},{"dirty_before",dirtyBefore},{"dirty_after",dirtyBefore},{"native_row_functions",functionTypes}});
            }
            NativeMemory.Require(seen.Count>0 && seen.Count<=32,"Unexpected strategy block count.");
            NativeMemory.Require(rootBefore==NativeMemory.I32(root,0x48) && compileBefore==NativeMemory.I32(root,0x114),"Root state changed during source read.");
            return new Dictionary<string,object>{{"ok",true},{"blocks",blocks},{"programs",programs},{"block_count",blocks.Count},{"direct_program_count",programs.Count},{"non_program_row_function_count",unknown},
                {"raw_source_readback",true},{"native_write_called",false},{"write_attempted",false},{"root_modified_before",rootBefore},{"root_modified_after",NativeMemory.I32(root,0x48)},
                {"compile_valid_before",compileBefore},{"compile_valid_after",NativeMemory.I32(root,0x114)},{"mapping_note","Stable canonical blockID/native row index. Offline schema row/cell/action mapping requires independent source-by-source comparison; no offline index is guessed."}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            throw new InvalidOperationException("Strategy extension mutation is not prepared; readonly Inspect only.");
        }
        internal static Dictionary<string,object> InspectLifecycle(NativeEngine engine,NativeContext context) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(String.Equals(Path.GetFullPath(NativePageDuplicateProfile.CurrentProjectPath(engine)),fixture,StringComparison.OrdinalIgnoreCase),"Lifecycle inspection requires the isolated fixture.");
            var api=new ReadApi(engine,"strategy-extension-lifecycle-guard.json");IntPtr doc=api.Existing.RootDoc();
            int dirty=NativeMemory.I32(doc,0x48),compile=NativeMemory.I32(doc,0x114);
            IntPtr runtime=engine.Address(0xFAE118);
            NativeMemory.Require(NativeMemory.Ascii(NativeMemory.Ptr(runtime,0),64)=="CTriggerUser" && NativeMemory.I32(runtime,4)==0x24 && NativeMemory.I32(runtime,8)==0 && NativeMemory.Ptr(runtime,12)==engine.Address(0x5293C),"CTriggerUser native runtime factory metadata differs.");
            int nextId=engine.Bind<NativeEngine.ThisInt>(api.Method("NextStrategyId"))(doc);
            NativeMemory.Require(nextId>=3 && nextId<1000000,"Native next strategy ID is outside the fixture bound.");
            var rows=new List<object>();IntPtr manager=engine.Call<NativeEngine.CdeclModule>("GetModuleObject")(3);
            NativeMemory.Require(NativeMemory.Ptr(manager,0)==engine.Address(ManagerRva),"Lifecycle strategy manager table differs.");
            foreach(IntPtr block in engine.Children(manager)) {
                NativeMemory.Require(NativeMemory.Ptr(block,0)==engine.Address(BlockRva),"Lifecycle strategy block table differs.");
                int id=NativeStrategyProfile.ReadId(api.Existing,block);string name=NativeStrategyProfile.ReadName(api.Existing,block);
                IntPtr trigger=NativeMemory.Ptr(block,0xC);NativeMemory.Require(trigger!=IntPtr.Zero,"Strategy has no canonical trigger context.");
                string type=api.MfcType(trigger);NativeMemory.Require(type.StartsWith(".?AVCTrigger",StringComparison.Ordinal),"Canonical strategy context is not a native trigger object.");
                int linkedId=NativeMemory.I32(trigger,8);NativeMemory.Require(linkedId==id,"Canonical strategy and trigger IDs disagree.");
                string note=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(trigger,0x10),4096);
                rows.Add(new Dictionary<string,object>{{"block_id",id},{"block_name",name},{"block_iobject",NativeMemory.Hex(block)},
                    {"context",NativeMemory.Hex(trigger)},{"context_rtti",type},{"trigger_id",NativeMemory.I32(trigger,4)},{"strategy_id",linkedId},{"trigger_type",NativeMemory.I32(trigger,12)},
                    {"note",note},{"context_modified_byte",Marshal.ReadByte(NativeMemory.Add(trigger,0x20))}});
            }
            NativeMemory.Require(dirty==NativeMemory.I32(doc,0x48) && compile==NativeMemory.I32(doc,0x114),"Lifecycle inspection changed root state.");
            return new Dictionary<string,object>{{"ok",true},{"next_strategy_id",nextId},{"canonical_contexts",rows},{"user_context_native_factory_metadata_verified",true},
                {"factory_executed",false},{"add_rename_delete_executed",false},{"user_context_default_trigger_id",-1},{"default_negative_trigger_id_persistence_proven",false},
                {"root_modified_before",dirty},{"root_modified_after",NativeMemory.I32(doc,0x48)},{"compile_valid_before",compile},{"compile_valid_after",NativeMemory.I32(doc,0x114)},
                {"write_attempted",false},{"status","Lifecycle ABI/metadata inspected only; default context initialization and model ownership must be closed before mutation."}};
        }
    }
}
