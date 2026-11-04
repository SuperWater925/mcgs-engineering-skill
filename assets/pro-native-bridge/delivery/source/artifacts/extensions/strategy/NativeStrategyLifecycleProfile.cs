// Additional source only. Root must bind the immutable fresh-session manifest before any trial.
// Existing canonical objects are read only. Only factory-owned temporary objects receive three
// scalar initialization stores that match the original native ArchiveStrategy/create-context path.
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
    internal static class NativeStrategyLifecycleProfile {
        const string AbiSha="8dc56512ffa3340e2c210ba7eab0db1d36995a3390a535844a9a6319324e8ea6";
        const string SessionSha="PENDING_ROOT_FRESH_SESSION_PROOF_SHA";
        const string BeforeName="BRIDGE_EXT_原生策略新建",AfterName="BRIDGE_EXT_策略接口验证";
        const string SourceBefore="' BRIDGE_PRO_SOURCE_UPDATED",SourceAfter="' BRIDGE_EXT_USER_STRATEGY_SOURCE";
        static int attempted;
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create0();
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VoidPointer(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VoidInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Void0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int IntPointer(IntPtr self,IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Int0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)]delegate bool NameSetter(IntPtr self,IntPtr name);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr PointerCString(IntPtr self,IntPtr name);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Replace(IntPtr self,IntPtr before,IntPtr after,IntPtr matcher);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr MatcherCtor(IntPtr self,int pattern,int caseSensitive);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr RowCtor(IntPtr self,IntPtr database);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void RecordOpen(IntPtr self,int type,IntPtr sql,int options);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int RecordFind(IntPtr self,IntPtr criterion);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr GetModuleHandleW(string module);

        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeContext Context;
            internal readonly NativeStrategyExtensionProfile.ReadApi Read;
            internal readonly IntPtr Root,Manager;
            internal readonly string Fixture;
            readonly Dictionary<string,Dictionary<string,object>> factories=new Dictionary<string,Dictionary<string,object>>();
            internal Api(NativeEngine engine,NativeContext context) {
                Engine=engine;Context=context;Fixture=Path.GetFullPath(Path.Combine(NativeOperations.TaskRoot,"fixtures","initial.MCP"));
                string guard=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","strategy-extension-write-guard.json");
                NativeMemory.Require(NativeMemory.Hash(guard)==AbiSha,"Strategy lifecycle ABI guard differs.");
                Read=new NativeStrategyExtensionProfile.ReadApi(engine,"strategy-extension-write-guard.json");Root=Read.Existing.RootDoc();
                NativeMemory.Require(NativeMemory.Ptr(Root,0x2D4)==context.ObjectModel,"Strategy lifecycle object model differs from the current document.");
                Manager=engine.Call<NativeEngine.CdeclModule>("GetModuleObject")(3);NativeMemory.Require(NativeMemory.Ptr(Manager,0)==engine.Address(0xDDD094),"Strategy manager differs.");
                var profile=Load(guard);foreach(object row in (IEnumerable)profile["native_factories"]){var item=(Dictionary<string,object>)row;string name=Convert.ToString(item["method"]);factories.Add(name,item);Factory(name);}
                Current();NativeMemory.Require(Bind<Int0>("DatabaseIsOpen")(NativeMemory.Add(Root,0x25C))==1,"Current native project database is not already open; do not repair/reopen it.");
                IntPtr rowClass=engine.Address(0xCFEF38);NativeMemory.Require(NativeMemory.Ascii(NativeMemory.Ptr(rowClass,0),64)=="CDBTrigger" && NativeMemory.I32(rowClass,4)==0xBC,"Native Trigger recordset class/size differs.");
            }
            internal void Current() {
                NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Strategy lifecycle is outside the captured x86 UI thread.");
                NativeMemory.Require(NativePageDuplicateProfile.CurrentProjectPath(Engine).Equals(Fixture,StringComparison.OrdinalIgnoreCase),"Strategy lifecycle native project differs from the isolated fixture.");
                NativeMemory.Require(Read.Existing.RootDoc()==Root && NativeMemory.Ptr(Root,0x2D4)==Context.ObjectModel,"Strategy lifecycle current root changed.");
            }
            static IntPtr Resolve(NativeEngine engine,IntPtr entry) {
                IntPtr current=entry;for(int i=0;i<8;i++){engine.Rva(current);NativeMemory.Readable(current,5);if(Marshal.ReadByte(current)!=0xE9)return current;current=NativeMemory.Add(current,checked(5+Marshal.ReadInt32(current,1)));}throw new InvalidOperationException("Native factory jump chain exceeds guard bound.");
            }
            internal IntPtr Factory(string name) {
                var item=factories[name];IntPtr runtime=Engine.Address(NativeEngine.Number(item["runtime_class_rva"])),table=Engine.Address(NativeEngine.Number(item["primary_vtable_rva"]));
                NativeMemory.Require(NativeMemory.Ascii(NativeMemory.Ptr(runtime,0),64)==Convert.ToString(item["class_name"]) && NativeMemory.I32(runtime,4)==Convert.ToInt32(item["size"]) && NativeMemory.I32(runtime,8)==Convert.ToInt32(item["schema"]),"Native factory class name/size/schema differs: "+name);
                IntPtr getter=NativeMemory.Ptr(table,0);NativeMemory.Require(getter==Engine.Address(NativeEngine.Number(item["runtime_class_getter_entry_rva"])) && Resolve(Engine,getter)==Read.Method(Convert.ToString(item["runtime_class_getter_method"])),"Native factory primary GetRuntimeClass mapping differs: "+name);
                IntPtr factory=NativeMemory.Ptr(runtime,12);NativeMemory.Require(factory==Engine.Address(NativeEngine.Number(item["factory_entry_rva"])) && Resolve(Engine,factory)==Read.Method(name) && Resolve(Engine,factory)==Engine.Address(NativeEngine.Number(item["resolved_body_rva"])),"Native CRuntimeClass pfn entry/body differs: "+name);
                return factory;
            }
            internal T Bind<T>(string name)where T:class {Current();return Engine.Bind<T>(factories.ContainsKey(name)?Factory(name):Read.Method(name));}
            internal void Slot(IntPtr value,int slot,int rva){NativeMemory.Require(Engine.Virtual(value,slot)==Engine.Address(rva),"Strategy lifecycle native virtual entry differs at slot "+slot);}
            internal List<IntPtr> Array(IntPtr array,string type) {
                Read.Table(array,type);int count=NativeMemory.I32(array,8);NativeMemory.Require(count>=0 && count<=128,"Strategy root array exceeds the isolated trial bound.");
                IntPtr data=NativeMemory.Ptr(array,4);if(count>0)NativeMemory.Readable(data,checked(count*4));
                var result=new List<IntPtr>();var distinct=new HashSet<uint>();for(int i=0;i<count;i++){IntPtr item=NativeMemory.Ptr(data,4*i);NativeMemory.Require(item!=IntPtr.Zero && distinct.Add(NativeMemory.U(item)),"Strategy root array has an empty/repeated pointer.");result.Add(item);}return result;
            }
            internal Dictionary<int,IntPtr> Blocks() {
                var result=new Dictionary<int,IntPtr>();var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach(IntPtr block in Engine.Children(Manager)) {
                    Read.Table(block,"BlockIObject");Read.Table(NativeMemory.Add(block,-4),"BlockComplete");Read.Table(NativeMemory.Add(block,4),"BlockPreloadable");
                    int id=NativeStrategyProfile.ReadId(Read.Existing,block);string name=NativeStrategyProfile.ReadName(Read.Existing,block);
                    NativeMemory.Require(id>=0 && !result.ContainsKey(id) && !String.IsNullOrEmpty(name) && names.Add(name),"Canonical strategy name/ID is not unique.");result.Add(id,block);
                }
                var stored=Array(NativeMemory.Add(Root,0x22C),"RootBlocks");NativeMemory.Require(stored.Count==result.Count,"Canonical and root strategy counts disagree.");
                foreach(IntPtr block in result.Values)NativeMemory.Require(stored.Contains(NativeMemory.Add(block,-4)),"Canonical strategy is absent from the root owning array.");return result;
            }
            internal IntPtr Program(IntPtr block,int id,string name,string source) {
                List<IntPtr> rows=NativeStrategyExtensionProfile.Rows(Read,block);NativeMemory.Require(rows.Count==1,"Template/owned strategy must have exactly one native row.");
                IntPtr program=NativeMemory.Ptr(rows[0],8);Read.Table(program,"Prog");
                var item=NativeStrategyExtensionProfile.ReadProgram(Read,program,id,name,0);
                NativeMemory.Require(Convert.ToString(item["source"])==source,"Exact native source preimage differs.");return program;
            }
            internal string ExactCString(IntPtr storage,int bound) {
                IntPtr text=NativeMemory.Ptr(storage,0);NativeMemory.Readable(NativeMemory.Add(text,-12),4);int count=Read.Length(storage);
                NativeMemory.Require(count>=0 && count<=bound && count==NativeMemory.I32(text,-12),"Condition CString length/header differs.");
                NativeMemory.Readable(text,checked(count*2+2));NativeMemory.Require(Marshal.ReadInt16(text,count*2)==0,"Condition CString lacks an exact-length terminator.");return Encoding.Unicode.GetString(NativeMemory.Bytes(text,count*2));
            }
            internal List<object> Conditions(IntPtr row) {
                Read.Table(row,"Row");IntPtr cell=NativeMemory.Ptr(row,4);Read.Table(cell,"Cell");IntPtr array=NativeMemory.Add(cell,4);Read.Table(array,"ConnArray");
                int count=NativeMemory.I32(array,8);NativeMemory.Require(count>=0 && count<=32,"Native condition array exceeds trial bound.");IntPtr data=NativeMemory.Ptr(array,4);if(count>0)NativeMemory.Readable(data,count*4);
                var result=new List<object>();for(int i=0;i<count;i++) {
                    IntPtr condition=NativeMemory.Ptr(data,i*4);Read.Table(condition,"ConditionIF");NativeMemory.Require(Read.MfcType(condition)==".?AVCStgyConnIF@@","Unsupported condition class in the isolated strategy preimage.");
                    IntPtr bytes=NativeMemory.Add(condition,0x18),mfc=GetModuleHandleW("mfc110u.dll");NativeMemory.Require(mfc!=IntPtr.Zero && NativeMemory.Ptr(bytes,0)==NativeMemory.Add(mfc,0x362B8),"Condition compiled member is not the guarded native MFC CByteArray.");
                    int size=NativeMemory.I32(bytes,8);NativeMemory.Require(size>=0 && size<=131072,"Condition compiled byte array exceeds trial bound.");IntPtr buffer=NativeMemory.Ptr(bytes,4);byte[] raw=size==0?new byte[0]:NativeMemory.Bytes(buffer,size);
                    int state=NativeMemory.I32(condition,8),mode=NativeMemory.I32(condition,0x2C);string label=ExactCString(NativeMemory.Add(condition,0x14),4096),expression=ExactCString(NativeMemory.Add(condition,0x30),16384);
                    string serialized=expression+"\u0001"+mode.ToString(CultureInfo.InvariantCulture);
                    result.Add(new Dictionary<string,object>{{"class_name","CStgyConnIF"},{"native_index",i},{"state_word",state},{"state_word_le_hex",Hex(BitConverter.GetBytes(state))},
                        {"label",label},{"label_utf16le_hex",Hex(Encoding.Unicode.GetBytes(label))},{"compiled_bytes",size},{"compiled_hex",Hex(raw)},
                        {"native_logic_index",mode},{"native_expression",expression},{"native_expression_utf16le_hex",Hex(Encoding.Unicode.GetBytes(expression))},
                        {"serialized_expression",serialized},{"serialized_expression_utf16le_hex",Hex(Encoding.Unicode.GetBytes(serialized))}});
                }return result;
            }
            internal string TemplateCondition(IntPtr block) {
                var rows=NativeStrategyExtensionProfile.Rows(Read,block);NativeMemory.Require(rows.Count==1,"Template condition requires one native row.");var values=Conditions(rows[0]);
                NativeMemory.Require(values.Count==1,"Template must retain exactly its one approved native condition.");var value=(Dictionary<string,object>)values[0];
                NativeMemory.Require(Convert.ToInt32(value["state_word"])==0 && Convert.ToString(value["label"])=="" && Convert.ToInt32(value["compiled_bytes"])==0 && Convert.ToString(value["compiled_hex"])=="" && Convert.ToInt32(value["native_logic_index"])==0 && Convert.ToString(value["native_expression"])=="" && Convert.ToString(value["serialized_expression_utf16le_hex"])=="01003000","Complete template condition field/byte preimage differs.");return Json(value);
            }
            internal void NativeName(IntPtr block,string name) {
                Read.Table(block,"BlockIObject");Slot(block,10,0xBF23);
                using(var text=new NativeStrategyProfile.CString(Read.Existing,name))NativeMemory.Require(Bind<NameSetter>("BlockSetName")(block,text.Storage),"Native strategy name setter refused the owned object.");
                NativeMemory.Require(NativeStrategyProfile.ReadName(Read.Existing,block)==name,"Native strategy name setter readback differs.");
            }
        }
        sealed class Matcher:IDisposable {
            readonly Api api;internal readonly IntPtr Pointer;bool valid;
            internal Matcher(Api value){api=value;Pointer=Marshal.AllocHGlobal(2);try{api.Read.Existing.Bind<MatcherCtor>("MatcherCtor")(Pointer,0,1);valid=true;NativeMemory.Require(Marshal.ReadByte(Pointer)==0 && Marshal.ReadByte(Pointer,1)==1,"Native text-only matcher differs.");}catch{Dispose();throw;}}
            public void Dispose(){try{if(valid){valid=false;api.Read.Existing.Bind<Void0>("MatcherDtor")(Pointer);}}finally{Marshal.FreeHGlobal(Pointer);}}
        }
        sealed class TriggerRow:IDisposable {
            readonly Api api;readonly IntPtr storage;bool constructed,opened;
            internal TriggerRow(Api value) {
                api=value;storage=Marshal.AllocHGlobal(0xBC);
                try {
                    for(int i=0;i<0xBC;i++)Marshal.WriteByte(storage,i,0);
                    IntPtr expected=NativeMemory.Add(api.Root,0x25C);NativeMemory.Require(api.Bind<Int0>("DatabaseIsOpen")(expected)==1,"Trigger postcheck database closed.");
                    NativeMemory.Require(api.Bind<CreateDatabasePointer>("CurrentProjectDatabase")(api.Root)==expected,"Trigger postcheck database owner differs.");
                    NativeMemory.Require(api.Bind<RowCtor>("TriggerRecordCtor")(storage,expected)==storage,"Native Trigger row constructor returned another object.");constructed=true;api.Read.Table(storage,"TriggerRecord");
                    opened=true;api.Bind<RecordOpen>("RecordOpen")(storage,-1,IntPtr.Zero,0);
                }catch{Dispose();throw;}
            }
            [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr CreateDatabasePointer(IntPtr self);
            internal void Verify(int recordId,int strategyId,string note) {
                IntPtr filter=Marshal.StringToHGlobalUni("iID = "+recordId.ToString(CultureInfo.InvariantCulture));
                try {NativeMemory.Require(api.Bind<RecordFind>("RecordFind")(storage,filter)!=0 && NativeMemory.I32(storage,0x98)==recordId && NativeMemory.I32(storage,0x9C)==strategyId && NativeMemory.I32(storage,0xA0)==3 && NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(storage,0xB0),4096)==note,"A fresh native Trigger cursor did not find the exact allocated User context row.");}
                finally{Marshal.FreeHGlobal(filter);}
            }
            public void Dispose(){try{if(constructed){try{if(opened){opened=false;api.Bind<Void0>("RecordClose")(storage);}}finally{constructed=false;api.Bind<Void0>("TriggerRecordDtor")(storage);}}}finally{Marshal.FreeHGlobal(storage);}}
        }
        static Dictionary<string,object> Load(string path){return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));}
        static string Json(object value){return new JavaScriptSerializer{MaxJsonLength=4*1024*1024,RecursionLimit=80}.Serialize(value);}
        static string Hex(byte[] value){return BitConverter.ToString(value).Replace("-","").ToLowerInvariant();}
        static string HashUtf8(string value){using(var algorithm=System.Security.Cryptography.SHA256.Create())return Hex(algorithm.ComputeHash(Encoding.UTF8.GetBytes(value)));}
        static Dictionary<string,object> Proof(Dictionary<string,object> value) {
            string path=Path.GetFullPath(Convert.ToString(value["file"])),root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";
            NativeMemory.Require(path.StartsWith(root,StringComparison.OrdinalIgnoreCase) && NativeMemory.Hash(path)==Convert.ToString(value["sha256"]),"Fresh strategy session proof file/hash differs.");return Load(path);
        }
        static Dictionary<string,object> Session(Api api) {
            string path=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","fresh-session-guard.json");
            NativeMemory.Require(NativeMemory.Hash(path)==SessionSha,"Strategy creation is blocked until the root's exact fresh-session proof is bound.");var session=Load(path);
            NativeMemory.Require(Convert.ToInt32(session["schema"])==1 && Convert.ToString(session["purpose"])=="owned-user-strategy-create-rename","Fresh strategy session purpose/schema differs.");
            NativeMemory.Require(Convert.ToInt32(session["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(session["ui_thread_id"])==EngineEntry.ExpectedUiThreadId,"Strategy creation is outside the captured fresh host session.");
            NativeMemory.Require(Path.GetFullPath(Convert.ToString(session["current_project"])).Equals(api.Fixture,StringComparison.OrdinalIgnoreCase) && Convert.ToString(session["editor_sha256"])==api.Engine.ImageSha256,"Fresh strategy session editor/project differs.");
            NativeMemory.Require(Convert.ToString(session["abi_guard_sha256"])==AbiSha && Convert.ToString(session["new_name_before"])==BeforeName && Convert.ToString(session["new_name_after"])==AfterName && Convert.ToString(session["new_source"])==SourceAfter,"Fresh strategy session action differs from this narrow trial.");
            NativeMemory.Require(session["user_trigger_only"] is bool && (bool)session["user_trigger_only"] && session["run_or_download"] is bool && !(bool)session["run_or_download"],"Strategy trial must remain an unexecuted User trigger.");
            var index=Proof((Dictionary<string,object>)session["baseline_index"]);var fingerprints=Proof((Dictionary<string,object>)session["baseline_fingerprints"]);
            string projectSha=Convert.ToString(session["project_sha256"]);
            NativeMemory.Require(Convert.ToString(index["sha256"])==projectSha && Convert.ToBoolean(index["source_unchanged"]) && Convert.ToString(index["project_family"])=="Pro","Fresh strategy baseline identity differs.");
            NativeMemory.Require(Convert.ToString(fingerprints["sha256"])==projectSha && Convert.ToBoolean(fingerprints["source_unchanged"]) && Convert.ToString(fingerprints["project_family"])=="Pro" && Json(index["tables"])==Json(fingerprints["tables"]),"Fresh complete fingerprints do not describe the same project/schema capture.");
            NativeMemory.Require(Convert.ToBoolean(fingerprints["all_field_values_fingerprinted"]) && Convert.ToBoolean(fingerprints["account_values_withheld"]) && Convert.ToString(fingerprints["mode"])=="ACE Mode=Read","Fresh strategy baseline lacks complete read-only fingerprints.");
            NativeMemory.Require(NativeMemory.Hash(api.Fixture)==projectSha,"Current strategy fixture differs from the fresh complete baseline.");
            var source=Proof((Dictionary<string,object>)session["native_source_read"]);var comparison=Proof((Dictionary<string,object>)session["native_source_comparison"]);var inspection=Proof((Dictionary<string,object>)session["native_lifecycle_inspection"]);var template=Proof((Dictionary<string,object>)session["native_creation_inspection"]);
            foreach(var result in new[]{source,inspection,template})NativeMemory.Require(Convert.ToBoolean(result["ok"]) && !Convert.ToBoolean(result["write_attempted"]) && Convert.ToInt32(result["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(result["native_thread_id"])==EngineEntry.ExpectedUiThreadId,"Fresh native source/lifecycle/template proof is outside this UI session.");
            NativeMemory.Require(Convert.ToBoolean(comparison["ok"]) && Convert.ToBoolean(comparison["all_exact_utf16_bytes_equal"]) && Convert.ToInt32(comparison["programs"])==9 && Convert.ToString(comparison["export_sha256"])==projectSha,"Fresh exact-source comparison is not the complete nine-script baseline.");
            NativeMemory.Require(Convert.ToString(comparison["native_response_sha256"])==Convert.ToString(((Dictionary<string,object>)session["native_source_read"])["sha256"]),"Fresh source comparison references another native response.");
            NativeMemory.Require(Convert.ToInt32(source["block_count"])==5 && Convert.ToInt32(source["direct_program_count"])==9 && Convert.ToInt32(inspection["next_strategy_id"])==15,"Fresh strategy model count/next-ID differs.");
            NativeMemory.Require(NativeMemory.I32(api.Root,0x48)==Convert.ToInt32(inspection["root_modified_after"]) && NativeMemory.I32(api.Root,0x114)==Convert.ToInt32(inspection["compile_valid_after"]),"Native root flags changed since the fresh strategy inspection.");
            NativeMemory.Require(Convert.ToInt32(session["expected_next_strategy_id"])==15 && Convert.ToString(template["template_condition_json"])==api.TemplateCondition(api.Blocks()[0]),"Expected own strategy ID or full native template-condition proof differs.");
            NativeMemory.Require(Convert.ToString(template["old_strategy_snapshot_utf8_sha256"])==HashUtf8(Snapshot(api,api.Blocks())),"Complete old strategy/condition/source snapshot changed since fresh native creation inspection.");
            var triggerIds=new HashSet<int>();foreach(object item in (IEnumerable)index["rows"]){var row=(Dictionary<string,object>)item;if(Convert.ToString(row["table"])!="Trigger")continue;int recordId=Convert.ToInt32(row["iID"]);NativeMemory.Require(recordId>=0 && triggerIds.Add(recordId),"Baseline Trigger record IDs are invalid/repeated.");}
            NativeMemory.Require(triggerIds.Count==5,"Strategy creation requires the five exact baseline Trigger rows.");session["_baseline_trigger_ids"]=triggerIds;
            string id=Convert.ToString(session["trial_id"]);Guid parsed;NativeMemory.Require(Guid.TryParse(id,out parsed),"Strategy session requires a unique trial GUID.");return session;
        }
        static string Snapshot(Api api,Dictionary<int,IntPtr> originals) {
            var ids=new List<int>(originals.Keys);ids.Sort();var blocks=new List<object>();
            foreach(int id in ids) {
                IntPtr block=originals[id];string name=NativeStrategyProfile.ReadName(api.Read.Existing,block);IntPtr trigger=NativeMemory.Ptr(block,0xC);
                string triggerType=api.Read.MfcType(trigger),triggerTail="";
                if(triggerType==".?AVCTriggerLoop@@")triggerTail=Hex(NativeMemory.Bytes(NativeMemory.Add(trigger,0x24),32));
                else NativeMemory.Require(triggerType==".?AVCTriggerStart@@" || triggerType==".?AVCTriggerEnd@@","Unsupported existing trigger subtype in the isolated complete preimage.");
                var source=new List<object>();List<IntPtr> rows=NativeStrategyExtensionProfile.Rows(api.Read,block);
                var conditions=new List<object>();for(int i=0;i<rows.Count;i++){IntPtr prog=NativeMemory.Ptr(rows[i],8);api.Read.Table(prog,"Prog");source.Add(NativeStrategyExtensionProfile.ReadProgram(api.Read,prog,id,name,i));conditions.Add(api.Conditions(rows[i]));}
                blocks.Add(new Dictionary<string,object>{{"id",id},{"name",name},{"comment",api.ExactCString(NativeMemory.Add(block,0x10),4096)},{"iobject",NativeMemory.Hex(block)},{"context",NativeMemory.Hex(trigger)},
                    {"context_rtti",triggerType},{"trigger_subtype_tail_hex",triggerTail},{"trigger_id",NativeMemory.I32(trigger,4)},{"strategy_id",NativeMemory.I32(trigger,8)},{"trigger_type",NativeMemory.I32(trigger,12)},
                    {"note",NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(trigger,0x10),4096)},{"common_tail",new int[]{NativeMemory.I32(trigger,0x14),NativeMemory.I32(trigger,0x18),NativeMemory.I32(trigger,0x1C)}},
                    {"block_dirty",Marshal.ReadByte(NativeMemory.Add(block,0x60))},{"trigger_dirty",Marshal.ReadByte(NativeMemory.Add(trigger,0x20))},{"conditions",conditions},{"programs",source}});
            }return Json(blocks);
        }
        static void ExistingUnchanged(Api api,Dictionary<int,IntPtr> originals,string snapshot) {
            var current=api.Blocks();foreach(var row in originals)NativeMemory.Require(current.ContainsKey(row.Key) && current[row.Key]==row.Value,"An existing strategy identity changed.");
            NativeMemory.Require(Snapshot(api,originals)==snapshot,"An existing strategy name/context/source/dirty state changed during the owned trial.");
        }
        static void WriteAttempt(string file,Dictionary<string,object> record){try{File.WriteAllText(file,Json(record),new UTF8Encoding(false));}catch{/* Diagnostic logging cannot replace the original native error. */}}
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine,context);var blocks=api.Blocks();bool prefix=false;foreach(IntPtr block in blocks.Values)if(NativeStrategyProfile.ReadName(api.Read.Existing,block).StartsWith("BRIDGE_EXT_",StringComparison.Ordinal))prefix=true;
            NativeMemory.Require(blocks.ContainsKey(0),"Startup template is absent.");api.Program(blocks[0],0,"启动策略",SourceBefore);string condition=api.TemplateCondition(blocks[0]),snapshot=Snapshot(api,blocks);
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"strategy_count",blocks.Count},{"trigger_context_count",api.Array(NativeMemory.Add(api.Root,0x240),"RootTriggers").Count},
                {"next_strategy_id",api.Bind<Int0>("NextStrategyId")(api.Root)},{"owned_prefix_already_present",prefix},{"new_name_before",BeforeName},{"new_name_after",AfterName},{"new_source",SourceAfter},
                {"user_trigger_only",true},{"template_condition_json",condition},{"old_strategy_snapshot_utf8_sha256",HashUtf8(snapshot)},{"native_factory_runtime_class_pfn_entry_and_body_verified",true},{"template_condition_runtime_semantics_interpreted",false},{"factory_or_init_executed",false},{"abi_guard_sha256",AbiSha},{"fresh_session_guard_bound",SessionSha.Length==64},{"lifecycle_writer_ready",false}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine,context);NativeMemory.Require(Path.GetFullPath(expected).Equals(api.Fixture,StringComparison.OrdinalIgnoreCase),"Strategy writer expected-project differs.");
            var session=Session(api);var originals=api.Blocks();NativeMemory.Require(originals.Count==5 && originals.ContainsKey(0),"Strategy creation requires the original five canonical blocks.");
            foreach(IntPtr block in originals.Values)NativeMemory.Require(!NativeStrategyProfile.ReadName(api.Read.Existing,block).StartsWith("BRIDGE_EXT_",StringComparison.Ordinal),"An owned strategy already exists; do not replay this trial.");
            NativeMemory.Require(NativeStrategyProfile.ReadName(api.Read.Existing,originals[0])=="启动策略","Startup template name differs.");api.Program(originals[0],0,"启动策略",SourceBefore);
            var oldContexts=api.Array(NativeMemory.Add(api.Root,0x240),"RootTriggers");NativeMemory.Require(oldContexts.Count==5,"Strategy creation requires five original trigger contexts.");
            int next=api.Bind<Int0>("NextStrategyId")(api.Root);NativeMemory.Require(next==15 && !originals.ContainsKey(next),"Native new strategy ID differs from the fresh proof.");
            string originalSnapshot=Snapshot(api,originals),conditionSnapshot=api.TemplateCondition(originals[0]);NativeMemory.Require(Interlocked.CompareExchange(ref attempted,1,0)==0,"This engine already attempted its strategy creation trial.");
            string directory=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","attempts");Directory.CreateDirectory(directory);
            string attemptFile=Path.Combine(directory,Convert.ToString(session["trial_id"])+".json");
            var record=new Dictionary<string,object>{{"process_id",Process.GetCurrentProcess().Id},{"ui_thread_id",EngineEntry.ExpectedUiThreadId},{"session_guard_sha256",SessionSha},{"strategy_id",next},{"phase","preflight-complete"}};
            using(var stream=new FileStream(attemptFile,FileMode.CreateNew,FileAccess.Write,FileShare.Read)){byte[] data=Encoding.UTF8.GetBytes(Json(record));stream.Write(data,0,data.Length);}
            IntPtr temporary=IntPtr.Zero,user=IntPtr.Zero,created=IntPtr.Zero;bool adopted=false;
            try {
                NativeOperationTrace.BeforeMutation("strategy-owned-native-block-create");record["phase"]="owned-block-create";WriteAttempt(attemptFile,record);
                temporary=api.Bind<Create0>("CreateBlock")();NativeMemory.Require(temporary!=IntPtr.Zero,"Native block factory returned null.");api.Read.Table(temporary,"BlockComplete");api.Read.Table(NativeMemory.Add(temporary,4),"BlockIObject");
                record["temporary_block"]=NativeMemory.Hex(temporary);api.Bind<VoidPointer>("BlockDeepCopy")(temporary,NativeMemory.Add(originals[0],-4));
                NativeMemory.Require(!api.Array(NativeMemory.Add(api.Root,0x22C),"RootBlocks").Contains(temporary),"Native temporary block unexpectedly attached itself.");
                NativeMemory.Require(NativeMemory.Ptr(temporary,0x10)==NativeMemory.Ptr(originals[0],0xC) && NativeMemory.I32(temporary,0x34)==0,"Native startup deep-copy metadata preimage differs.");
                api.Program(NativeMemory.Add(temporary,4),0,"启动策略",SourceBefore);NativeMemory.Require(api.TemplateCondition(NativeMemory.Add(temporary,4))==conditionSnapshot,"Deep-copied template condition differs.");ExistingUnchanged(api,originals,originalSnapshot);
                NativeOperationTrace.SetPhase("strategy-owned-user-context-create");record["phase"]="owned-user-context-create";WriteAttempt(attemptFile,record);
                user=api.Bind<Create0>("CreateUserContext")();NativeMemory.Require(user!=IntPtr.Zero,"Native User context factory returned null.");api.Read.Table(user,"UserContext");
                NativeMemory.Require(api.Read.MfcType(user)==".?AVCTriggerUser@@" && NativeMemory.I32(user,4)==-1 && NativeMemory.I32(user,8)==-1 && NativeMemory.I32(user,12)==3,"Fresh native User context differs.");
                NativeMemory.Require(!oldContexts.Contains(user),"Fresh User context aliases an existing context.");record["new_context"]=NativeMemory.Hex(user);
                // These three stores initialize only private unregistered factory-owned objects.
                // Their exact native counterparts are ABF8CD..ABF8DB / AC0BD1..AC0BF2.
                NativeOperationTrace.SetPhase("strategy-owned-temporary-metadata-initialize");
                Marshal.WriteInt32(temporary,0x10,user.ToInt32());Marshal.WriteInt32(temporary,0x34,next);Marshal.WriteInt32(user,8,next);
                NativeMemory.Require(NativeMemory.Ptr(temporary,0x10)==user && NativeMemory.I32(temporary,0x34)==next && NativeMemory.I32(user,8)==next,"Owned temporary identity initialization differs.");
                api.NativeName(NativeMemory.Add(temporary,4),BeforeName);
                using(var before=new NativeStrategyProfile.CString(api.Read.Existing,SourceBefore))using(var after=new NativeStrategyProfile.CString(api.Read.Existing,SourceAfter))using(var matcher=new Matcher(api)) {
                    api.Slot(NativeMemory.Add(temporary,4),23,0x2B1AC);
                    NativeMemory.Require(api.Engine.Bind<Replace>(api.Engine.Virtual(NativeMemory.Add(temporary,4),23))(NativeMemory.Add(temporary,4),before.Storage,after.Storage,matcher.Pointer)==1,"Owned temporary source replacement was not exactly one comment.");
                }
                api.Program(NativeMemory.Add(temporary,4),next,BeforeName,SourceAfter);NativeMemory.Require(api.TemplateCondition(NativeMemory.Add(temporary,4))==conditionSnapshot,"Owned source replacement changed the retained template condition.");ExistingUnchanged(api,originals,originalSnapshot);
                NativeStrategyProfile.MarkRootDirty(api.Read.Existing);NativeOperationTrace.BeforeMutation("strategy-user-trigger-init-native-database");record["phase"]="native-trigger-init-persistent-write";WriteAttempt(attemptFile,record);
                api.Bind<VoidInt>("ContextInit")(user,-1);
                NativeMemory.Require(NativeMemory.I32(user,4)>=0 && !((HashSet<int>)session["_baseline_trigger_ids"]).Contains(NativeMemory.I32(user,4)) && NativeMemory.I32(user,8)==next && NativeMemory.I32(user,12)==3,"Native User trigger allocation is not one new record linked to the expected own strategy; do not retry.");
                record["trigger_record_id"]=NativeMemory.I32(user,4);NativeOperationTrace.SetPhase("strategy-new-trigger-fresh-native-cursor-verify");
                using(var triggerRow=new TriggerRow(api))triggerRow.Verify(NativeMemory.I32(user,4),next,NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(user,0x10),4096));
                record["native_trigger_fresh_cursor_verified"]=true;NativeOperationTrace.SetPhase("strategy-owned-user-note-to-comment");record["phase"]="owned-native-cstring-user-note-comment";WriteAttempt(attemptFile,record);
                // Original AC0BF5..AC0C02 copies new context.note to private full block.comment.
                string userNote=api.ExactCString(NativeMemory.Add(user,0x10),4096);
                api.Read.Existing.Bind<VoidPointer>("CStringAssignCopy")(NativeMemory.Add(temporary,0x14),NativeMemory.Add(user,0x10));
                NativeMemory.Require(api.ExactCString(NativeMemory.Add(temporary,0x14),4096)==userNote,"Private User strategy comment differs from its native trigger note.");ExistingUnchanged(api,originals,originalSnapshot);
                NativeOperationTrace.BeforeMutation("strategy-root-add-own-block-context");record["phase"]="root-add";WriteAttempt(attemptFile,record);
                NativeMemory.Require(api.Bind<IntPointer>("RootAddStrategy")(api.Root,temporary)==1,"RootAddStrategy refused the initialized own strategy.");
                var added=api.Blocks();NativeMemory.Require(added.Count==6 && added.ContainsKey(next),"Native RootAdd did not add exactly one strategy.");created=added[next];
                NativeMemory.Require(created!=NativeMemory.Add(temporary,4) && NativeMemory.Ptr(created,0xC)==user,"RootAdd did not deep-copy the block while retaining its new context.");
                var contexts=api.Array(NativeMemory.Add(api.Root,0x240),"RootTriggers");NativeMemory.Require(contexts.Count==6 && contexts.Contains(user),"RootAdd did not adopt the new trigger context.");foreach(IntPtr old in oldContexts)NativeMemory.Require(contexts.Contains(old),"RootAdd removed an original context.");adopted=true;
                NativeMemory.Require(NativeStrategyProfile.ReadName(api.Read.Existing,created)==BeforeName && api.ExactCString(NativeMemory.Add(created,0x10),4096)==userNote,"New canonical strategy name/comment differs.");api.Program(created,next,BeforeName,SourceAfter);
                NativeOperationTrace.BeforeMutation("strategy-own-new-object-name-setter");record["phase"]="rename-only-owned-new-object";WriteAttempt(attemptFile,record);api.NativeName(created,AfterName);
                api.Slot(api.Manager,16,0x2ABFD);using(var before=new NativeStrategyProfile.CString(api.Read.Existing,BeforeName))using(var after=new NativeStrategyProfile.CString(api.Read.Existing,AfterName)) {
                    var find=api.Engine.Bind<PointerCString>(api.Engine.Virtual(api.Manager,16));NativeMemory.Require(find(api.Manager,before.Storage)==IntPtr.Zero && find(api.Manager,after.Storage)==created,"Native strategy manager name lookup did not follow the own-object rename.");
                }
                NativeStrategyProfile.MarkRootDirty(api.Read.Existing);NativeOperationTrace.BeforeMutation("strategy-own-block-dirty-notify");record["phase"]="native-dirty-and-list-notify";WriteAttempt(attemptFile,record);
                IntPtr preload=NativeMemory.Add(created,4);api.Read.Table(preload,"BlockPreloadable");api.Read.Existing.MatchVirtual(preload,2,"StrategyPreloadSaveData");api.Read.Existing.Bind<Void0>("StrategyPreloadSaveData")(preload);
                ExistingUnchanged(api,originals,originalSnapshot);api.Program(created,next,AfterName,SourceAfter);NativeMemory.Require(api.TemplateCondition(created)==conditionSnapshot && api.ExactCString(NativeMemory.Add(created,0x10),4096)==userNote,"RootAdd/rename/notify changed the retained condition or User comment.");
                NativeMemory.Require(api.Blocks().Count==6 && NativeMemory.I32(api.Root,0x48)==1 && NativeMemory.I32(api.Root,0x114)==0 && Marshal.ReadByte(NativeMemory.Add(created,0x60))==1,"Owned new strategy final native state differs.");
                // Original CStrategyBlock::~CStrategyBlock releases rows/CStrings, not context+10.
                // The context is now in the root owning array and must not be separately deleted.
                api.Read.Table(temporary,"BlockComplete");api.Slot(temporary,1,0x511BD);NativeOperationTrace.SetPhase("strategy-owned-temporary-block-destroy");api.Bind<VoidInt>("BlockDeleteOwned")(temporary,1);temporary=IntPtr.Zero;
                NativeMemory.Require(api.Array(NativeMemory.Add(api.Root,0x240),"RootTriggers").Contains(user) && NativeMemory.Ptr(created,0xC)==user,"Temporary destructor disturbed the adopted context.");
                record["phase"]="verified-memory-pending-root-save";record["context_adopted"]=true;record["temporary_block_destroyed"]=true;record["strategy_name"]=AfterName;WriteAttempt(attemptFile,record);NativeOperationTrace.SetPhase("strategy-created-renamed-memory-verified");
                return new Dictionary<string,object>{{"ok",true},{"native_strategy_create_verified",true},{"native_new_owned_strategy_name_setter_verified",true},{"strategy_id",next},{"trigger_record_id",NativeMemory.I32(user,4)},
                    {"strategy_name_before_rename",BeforeName},{"strategy_name",AfterName},{"strategy_comment",userNote},{"strategy_comment_matches_native_user_note",true},{"source",SourceAfter},{"trigger_class","CTriggerUser"},{"trigger_type",3},{"template_condition_json",conditionSnapshot},{"template_condition_exactly_retained",true},{"template_condition_runtime_semantics_interpreted",false},
                    {"strategy_count_before",5},{"strategy_count_after",6},{"existing_strategy_snapshot_unchanged",true},{"native_trigger_record_fresh_cursor_verified",true},{"root_context_adoption_verified",true},{"temporary_block_destroyed",true},
                    {"new_iobject",NativeMemory.Hex(created)},{"new_context",NativeMemory.Hex(user)},{"pending_root_save",true},{"offline_full_field_verified",false},{"native_configuration_check_verified",false},{"reopen_persistence_verified",false},
                    {"run_or_download_executed",false},{"existing_reference_rename_verified",false},{"strategy_delete_executed",false},{"attempt_evidence",attemptFile},{"session_guard_sha256",SessionSha},{"abi_guard_sha256",AbiSha},{"write_attempted",true}};
            }catch(Exception error) {
                record["phase"]=NativeOperationTrace.Phase;record["error"]=error.GetType().FullName+": "+error.Message;record["context_adopted_confirmed"]=adopted;
                record["temporary_block_pointer"]=NativeMemory.Hex(temporary);record["context_pointer"]=NativeMemory.Hex(user);record["automatic_native_cleanup_or_rollback_attempted"]=false;
                record["recovery_note"]="Stop for inspection. No guessed cleanup of potentially adopted objects and no replay of Init(-1). Trigger DB writes may precede root model insertion.";WriteAttempt(attemptFile,record);throw;
            }
        }
    }
}
