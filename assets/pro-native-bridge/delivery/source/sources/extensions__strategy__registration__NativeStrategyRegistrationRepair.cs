// Own-object UI-list registration only. No factory/Init/RootAdd/replacement/save is invoked.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class NativeStrategyRegistrationRepair {
        const string AbiSha="31479a50b9ee412815f30791be6610b05ecc50d868e23ad292f41be6eb99f403";
        const string SessionSha="0f99068bc61a3bd4069a893387e4829f61be286fd50ae124450a8bb62a8bad18";
        const string Name="BRIDGE_EXT_策略接口验证",Source="' BRIDGE_EXT_USER_STRATEGY_SOURCE";
        static int attempted;
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int I1(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Insert(IntPtr self,IntPtr fullBlock);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Select(IntPtr self,int row);
        static Dictionary<string,object> Read(string path){return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));}
        static string Json(object value){return new JavaScriptSerializer{MaxJsonLength=4*1024*1024,RecursionLimit=80}.Serialize(value);}
        static string Sha(string value){using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-","").ToLowerInvariant();}
        sealed class Api {
            internal readonly NativeEngine Engine;internal readonly NativeContext Context;internal readonly NativeStrategyExtensionProfile.ReadApi Native;
            internal readonly IntPtr Root,Owner,Block,Trigger;internal readonly string Fixture,Snapshot;internal readonly Dictionary<string,object> Created;
            readonly IntPtr identityGetter;readonly byte[] identityBytes;
            internal Api(NativeEngine engine,NativeContext context) {
                Engine=engine;Context=context;Fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
                string guard=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","registration","registration-abi-guard.json");NativeMemory.Require(NativeMemory.Hash(guard)==AbiSha,"Registration ABI guard differs.");
                Native=new NativeStrategyExtensionProfile.ReadApi(engine,"registration/registration-abi-guard.json");
                var identity=(Dictionary<string,object>)Read(guard)["identity_getter"];identityGetter=engine.Address(NativeEngine.Number(identity["rva"]));string text=Convert.ToString(identity["expected_first_32_bytes"]);identityBytes=new byte[text.Length/2];
                for(int i=0;i<identityBytes.Length;i++)identityBytes[i]=Byte.Parse(text.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);
                NativeCodeRelocation.RebaseDeltaInPlace(identityBytes,(IEnumerable)identity["relocatable_dword_offsets_in_first32"],unchecked((uint)(NativeMemory.U(engine.ImageBase)-0x400000U)));
                Root=Native.Existing.RootDoc();Current();
                IntPtr app=Native.Existing.Bind<NativeEngine.CdeclPointer>("GetAfxApp")();NativeMemory.Require(NativeMemory.Ptr(app,0x520)==Root,"Registration application root differs.");
                IntPtr frame=NativeMemory.Ptr(app,0x524);NativeMemory.Require(NativeMemory.Ptr(frame,0)==engine.Address(0xDBC034),"Registration management frame differs.");
                IntPtr array=NativeMemory.Add(frame,0x314);NativeMemory.Require(NativeMemory.I32(array,8)==5,"Registration expected five native management lists.");IntPtr data=NativeMemory.Ptr(array,4),found=IntPtr.Zero;NativeMemory.Readable(data,20);
                for(int i=0;i<5;i++){IntPtr item=NativeMemory.Ptr(data,4*i);if(Native.HasTable(item,"StrategyList")){NativeMemory.Require(found==IntPtr.Zero,"Registration strategy-list owner repeats.");found=item;}}NativeMemory.Require(found!=IntPtr.Zero,"Registration strategy-list owner absent.");Owner=found;Native.Table(Owner,"StrategyList");
                IntPtr manager=engine.Call<NativeEngine.CdeclModule>("GetModuleObject")(3);NativeMemory.Require(NativeMemory.Ptr(manager,0)==engine.Address(0xDDD094),"Registration strategy manager differs.");
                IntPtr selected=IntPtr.Zero;int count=0;var ids=new HashSet<int>();foreach(IntPtr item in engine.Children(manager)){count++;Native.Table(item,"BlockIObject");int id=NativeStrategyProfile.ReadId(Native.Existing,item);NativeMemory.Require(ids.Add(id),"Registration duplicate canonical strategy ID.");if(id==15)selected=item;}
                NativeMemory.Require(count==6 && selected!=IntPtr.Zero && ids.SetEquals(new int[]{0,1,2,6,14,15}),"Registration requires exactly the created six-strategy model.");Block=selected;
                NativeMemory.Require(NativeStrategyProfile.ReadName(Native.Existing,Block)==Name,"Only the already-created own strategy15 is eligible.");
                Native.Table(NativeMemory.Add(Block,-4),"BlockComplete");Trigger=NativeMemory.Ptr(Block,0xC);Native.Table(Trigger,"UserContext");NativeMemory.Require(NativeMemory.I32(Trigger,8)==15 && NativeMemory.I32(Trigger,12)==3,"Own strategy User context differs.");
                var rows=NativeStrategyExtensionProfile.Rows(Native,Block);NativeMemory.Require(rows.Count==1,"Created strategy row count differs.");IntPtr program=NativeMemory.Ptr(rows[0],8);Native.Table(program,"Prog");var source=NativeStrategyExtensionProfile.ReadProgram(Native,program,15,Name,0);NativeMemory.Require(Convert.ToString(source["source"])==Source,"Created own strategy complete source differs.");
                string path=Path.Combine(NativeOperations.TaskRoot,"extensions","run-0002","strategy-create-rename-result.json");Created=Read(path);
                NativeMemory.Require(Convert.ToBoolean(Created["ok"]) && Convert.ToBoolean(Created["native_strategy_create_verified"]) && Convert.ToBoolean(Created["root_context_adoption_verified"]) && Convert.ToInt32(Created["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(Created["native_thread_id"])==EngineEntry.ExpectedUiThreadId,"Registration creation result is not from this successful current host session.");
                NativeMemory.Require(Convert.ToInt32(Created["strategy_id"])==15 && Convert.ToInt32(Created["trigger_record_id"])==NativeMemory.I32(Trigger,4) && Convert.ToString(Created["new_iobject"]).Equals(NativeMemory.Hex(Block),StringComparison.OrdinalIgnoreCase) && Convert.ToString(Created["new_context"]).Equals(NativeMemory.Hex(Trigger),StringComparison.OrdinalIgnoreCase),"Registration current owned object differs from its creation evidence.");
                Snapshot=Json(NativeStrategyExtensionProfile.Inspect(engine,context));
            }
            internal void Current(){NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Registration requires the actual captured UI thread.");NativeMemory.Require(Native.Existing.AddressOf("GetAfxApp")==identityGetter && BitConverter.ToString(NativeMemory.Bytes(identityGetter,identityBytes.Length))==BitConverter.ToString(identityBytes),"Registration identity getter bytes/pointer differ.");IntPtr current=Native.Existing.RootDoc();NativeMemory.Require(current==Root && NativeMemory.Ptr(Root,0)==Engine.Address(0xD57684) && NativeMemory.Ptr(Root,0x2D4)==Context.ObjectModel,"Registration current root/model differs.");string path=NativeStrategyProfile.ReadBorrowedCString(NativeMemory.Add(current,0x24),2048);NativeMemory.Require(!String.IsNullOrEmpty(path) && Path.GetFullPath(path).Equals(Fixture,StringComparison.OrdinalIgnoreCase),"Registration current native project differs.");}
            internal T Bind<T>(string name)where T:class{Current();return Engine.Bind<T>(Native.Method(name));}
            internal Dictionary<int,int> Rows(bool registered) {
                int expected=registered?6:5;NativeMemory.Require(Bind<I0>("StrategyListCount")(Owner)==expected,"Registration native UI-list count differs.");
                var values=new Dictionary<int,int>();var unique=new HashSet<int>();foreach(int id in new int[]{0,1,2,6,14}){int row=Bind<I1>("StrategyListFindId")(Owner,id);NativeMemory.Require(row>=0 && row<expected && unique.Add(row),"An original strategy UI-list row is missing/repeated.");values.Add(id,row);}
                int own=Bind<I1>("StrategyListFindId")(Owner,15);NativeMemory.Require(registered?own>=0 && own<6 && unique.Add(own):own==-1,"Own strategy UI row has an unexpected registration preimage.");values.Add(15,own);return values;
            }
            internal void Unchanged(){NativeMemory.Require(Json(NativeStrategyExtensionProfile.Inspect(Engine,Context))==Snapshot,"Native strategy source/model state changed during UI-only registration.");}
        }
        static Dictionary<string,int> ReportRows(Dictionary<int,int> values){var result=new Dictionary<string,int>();foreach(var item in values)result.Add(item.Key.ToString(CultureInfo.InvariantCulture),item.Value);return result;}
        static Dictionary<string,object> Proof(Dictionary<string,object> value){string path=Path.GetFullPath(Convert.ToString(value["file"])),root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";NativeMemory.Require(path.StartsWith(root,StringComparison.OrdinalIgnoreCase) && NativeMemory.Hash(path)==Convert.ToString(value["sha256"]),"Registration full-baseline proof file/hash differs.");return Read(path);}
        internal static Dictionary<string,object> Inspect(NativeEngine engine,NativeContext context) {
            var api=new Api(engine,context);var rows=api.Rows(false);return new Dictionary<string,object>{{"ok",true},{"write_attempted",false},{"strategy_id",15},{"strategy_name",Name},{"root_strategy_count",6},{"native_strategy_list_count",5},{"strategy_list_owner",NativeMemory.Hex(api.Owner)},{"list_rows",ReportRows(rows)},{"current_strategy_snapshot_sha256",Sha(api.Snapshot)},{"native_list_insert_executed",false},{"factory_or_init_or_rootadd_executed",false},{"abi_guard_sha256",AbiSha}};
        }
        internal static Dictionary<string,object> RunTrial(NativeEngine engine,NativeContext context,string expected) {
            var api=new Api(engine,context);NativeMemory.Require(Path.GetFullPath(expected).Equals(api.Fixture,StringComparison.OrdinalIgnoreCase),"Registration requested fixture differs.");var before=api.Rows(false);
            string file=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","registration","fresh-session-guard.json");NativeMemory.Require(NativeMemory.Hash(file)==SessionSha,"Registration is blocked until root binds the exact fresh-session proof.");var session=Read(file);
            NativeMemory.Require(Convert.ToInt32(session["schema"])==1 && Convert.ToString(session["purpose"])=="repair-created-user-strategy-registration" && Convert.ToInt32(session["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(session["ui_thread_id"])==EngineEntry.ExpectedUiThreadId && Path.GetFullPath(Convert.ToString(session["fixture_path"])).Equals(api.Fixture,StringComparison.OrdinalIgnoreCase),"Registration proof belongs to another purpose/session/project.");
            var index=Proof((Dictionary<string,object>)session["baseline_index"]);var fingerprints=Proof((Dictionary<string,object>)session["baseline_fingerprints"]);string projectSha=Convert.ToString(session["project_sha256"]);foreach(var baseline in new[]{index,fingerprints})NativeMemory.Require(Convert.ToString(baseline["sha256"])==projectSha && Convert.ToBoolean(baseline["source_unchanged"]) && Convert.ToString(baseline["project_family"])=="Pro","Registration complete baseline belongs to a different file.");NativeMemory.Require(Convert.ToBoolean(fingerprints["all_field_values_fingerprinted"]) && Convert.ToString(fingerprints["mode"])=="ACE Mode=Read" && Json(index["tables"])==Json(fingerprints["tables"]) && NativeMemory.Hash(api.Fixture)==projectSha,"Registration complete same-schema baseline/current project differs.");
            string creation=Path.Combine(NativeOperations.TaskRoot,"extensions","run-0002","strategy-create-rename-result.json");NativeMemory.Require(NativeMemory.Hash(creation)==Convert.ToString(session["creation_result_sha256"]) && Convert.ToString(session["expected_snapshot_sha256"])==Sha(api.Snapshot) && Convert.ToString(session["abi_guard_sha256"])==AbiSha,"Registration proof hashes/action differ.");
            string inspect=Path.GetFullPath(Convert.ToString(session["inspection_file"])),root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";NativeMemory.Require(inspect.StartsWith(root,StringComparison.OrdinalIgnoreCase) && NativeMemory.Hash(inspect)==Convert.ToString(session["inspection_sha256"]),"Registration readonly inspection file differs.");var preflight=Read(inspect);
            NativeMemory.Require(Convert.ToBoolean(preflight["ok"]) && !Convert.ToBoolean(preflight["write_attempted"]) && Convert.ToInt32(preflight["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(preflight["native_thread_id"])==EngineEntry.ExpectedUiThreadId && Convert.ToString(preflight["current_strategy_snapshot_sha256"])==Sha(api.Snapshot),"Registration readonly proof is not from the current unchanged model.");
            NativeMemory.Require(Interlocked.CompareExchange(ref attempted,1,0)==0,"Registration already attempted in this engine; do not repeat insertion.");
            NativeOperationTrace.BeforeMutation("strategy-own15-native-ui-list-insert");int row=api.Bind<Insert>("RegisterOwnStrategyList")(api.Owner,NativeMemory.Add(api.Block,-4));
            NativeMemory.Require(row>=0 && row<6,"Native strategy UI-list insertion returned an invalid row.");var registered=api.Rows(true);NativeMemory.Require(registered[15]==row,"Native inserted row does not match own strategy15.");foreach(var old in before)if(old.Key!=15)NativeMemory.Require(registered[old.Key]==old.Value+(old.Value>=row?1:0),"Native insertion did not preserve the exact original row order.");api.Unchanged();
            NativeOperationTrace.BeforeMutation("strategy-own15-native-ui-list-select");api.Bind<Select>("SelectOwnStrategyListRow")(api.Owner,row);registered=api.Rows(true);api.Unchanged();NativeOperationTrace.SetPhase("strategy-own15-full-native-registration-verified");
            return new Dictionary<string,object>{{"ok",true},{"write_attempted",true},{"strategy_id",15},{"strategy_name",Name},{"root_strategy_count",6},{"native_strategy_list_before",5},{"native_strategy_list_after",6},{"native_registered_row",row},{"list_rows_after",ReportRows(registered)},{"native_strategy_ui_registration_verified",true},{"existing_ui_ids_all_present_once",true},{"strategy_model_source_snapshot_unchanged",true},{"factory_or_init_or_rootadd_executed",false},{"native_save_executed",false},{"abi_guard_sha256",AbiSha},{"session_guard_sha256",SessionSha}};
        }
    }
}
