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
            internal readonly CStringLength Length;
            readonly Dictionary<string,Dictionary<string,object>> tables=new Dictionary<string,Dictionary<string,object>>();
            readonly Dictionary<string,IntPtr> methods=new Dictionary<string,IntPtr>();
            internal ReadApi(NativeEngine engine):this(engine,"strategy-extension-read-guard.json") {}
            internal ReadApi(NativeEngine engine,string profileName) {
                Engine=engine;Existing=new NativeStrategyProfile.Api(engine);
                string file=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy",profileName);
                var profile=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));
                NativeMemory.Require(Convert.ToInt32(profile["schema"])==1,"Unknown strategy read profile.");
                var handles=new Dictionary<string,IntPtr>();var bases=new Dictionary<string,uint>();
                foreach(object row in (IEnumerable)profile["modules"]) {
                    var item=(Dictionary<string,object>)row;string name=Convert.ToString(item["name"]);IntPtr handle=GetModuleHandleW(name);
                    NativeMemory.Require(handle!=IntPtr.Zero,"Required module is not loaded: "+name);
                    string path=null;foreach(ProcessModule module in Process.GetCurrentProcess().Modules)if(module.BaseAddress==handle){path=module.FileName;break;}
                    NativeMemory.Require(path!=null && NativeMemory.Hash(path)==Convert.ToString(item["sha256"]),"Strategy read module SHA differs: "+name);
                    handles.Add(name,handle);bases.Add(name,unchecked((uint)NativeEngine.Number(item["preferred_base"])));
                }
                NativeMemory.Require(handles["McgsSetPro.exe"]==engine.ImageBase,"Strategy read editor identity differs.");
                IntPtr getLength=IntPtr.Zero;
                foreach(object row in (IEnumerable)profile["functions"]) {
                    var item=(Dictionary<string,object>)row;string module=Convert.ToString(item["module"]),name=Convert.ToString(item["name"]);
                    IntPtr at=NativeMemory.Add(handles[module],NativeEngine.Number(item["rva"]));byte[] expected=Unhex(Convert.ToString(item["bytes"]));
                    foreach(object offset in (IEnumerable)item["reloc_offsets"]) {
                        int index=Convert.ToInt32(offset);uint value=unchecked(BitConverter.ToUInt32(expected,index)+NativeMemory.U(handles[module])-bases[module]);
                        Array.Copy(BitConverter.GetBytes(value),0,expected,index,4);
                    }
                    NativeMemory.Require(Hex(NativeMemory.Bytes(at,expected.Length))==Hex(expected),"Strategy read ABI bytes differ: "+name);
                    methods.Add(name,at);
                    if(name=="CStringGetLength") {
                        NativeMemory.Require(GetProcAddressOrdinal(handles[module],new IntPtr(Convert.ToInt32(item["ordinal"])))==at,"CString length ordinal differs.");getLength=at;
                    }
                }
                NativeMemory.Require(getLength!=IntPtr.Zero,"Missing guarded CString length helper.");
                Length=(CStringLength)Marshal.GetDelegateForFunctionPointer(getLength,typeof(CStringLength));
                foreach(object row in (IEnumerable)profile["tables"]) {
                    var item=(Dictionary<string,object>)row;string name=Convert.ToString(item["name"]);IntPtr table=Engine.Address(NativeEngine.Number(item["rva"]));
                    NativeMemory.Require(NativeMemory.Ptr(table,-4)==Engine.Address(NativeEngine.Number(item["col_rva"])),"Strategy read RTTI COL differs: "+name);
                    int i=0;foreach(object entry in (IEnumerable)item["entries"]){IntPtr expected=entry==null?IntPtr.Zero:Engine.Address(NativeEngine.Number(entry));NativeMemory.Require(NativeMemory.Ptr(table,i*4)==expected,"Strategy read table differs: "+name+"/"+i);i++;}
                    tables.Add(name,item);
                }
            }
            internal bool HasTable(IntPtr instance,string name) {return NativeMemory.Ptr(instance,0)==Engine.Address(NativeEngine.Number(tables[name]["rva"]));}
            internal IntPtr Method(string name){return methods[name];}
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
