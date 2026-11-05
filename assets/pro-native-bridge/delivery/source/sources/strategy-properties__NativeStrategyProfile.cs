// Derived only from the installed Pro binaries and the isolated fixture.
// Compile as an additional source with bootstrap/NativeOperations.cs.
// No vendor COM activation, library load, GUI command, or execution entry point.
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
    internal static class NativeStrategyProfile {
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr Ptr0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr Ptr1(IntPtr self,IntPtr argument);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr MatcherConstructor(IntPtr self,int pattern,int caseSensitive);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate void Void0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate void VoidInt(IntPtr self,int value);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate int Int0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)] delegate bool Bool0(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate int ReplaceText(IntPtr self,IntPtr oldText,IntPtr newText,IntPtr matcher);
        [UnmanagedFunctionPointer(CallingConvention.ThisCall)] [return:MarshalAs(UnmanagedType.I1)] delegate bool FindText(IntPtr self,IntPtr text,IntPtr matcher);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr GetModuleHandleW(string name);
        [DllImport("kernel32.dll",CharSet=CharSet.Ansi,ExactSpelling=true)] static extern IntPtr GetProcAddress(IntPtr module,string name);
        [DllImport("kernel32.dll",ExactSpelling=true,EntryPoint="GetProcAddress")] static extern IntPtr GetProcAddressOrdinal(IntPtr module,IntPtr ordinal);
        const string OldSource="' BRIDGE_PRO_SOURCE_INITIAL\r\n";
        const string NewSource="' BRIDGE_PRO_SOURCE_UPDATED\r\n";
        const string OldBody="' BRIDGE_PRO_SOURCE_INITIAL";
        const string NewBody="' BRIDGE_PRO_SOURCE_UPDATED";
        const string FixtureSha="1d4d401ad59a8fb6d18c33b9443cc3c2b533637e2b2cc9d0248c482e27f6aac6";
        const string SessionSha="e5743ba8076d99d18e0cddf2277914eb7908eb195dc8bb60873e4c9d94b38a6f";
        const string SessionSummarySha="a7f2ba7cfc6602492b091fe6c165e501fb4c2b6cb19a335379d32ef9690cf486";
        const string SessionComparisonSha="84e2466ef385105cc779f1b16c803ebf25e06a2c5fc1c5794a9f2717a3e29c00";
        const string SavedCopySha="c95adb7682a6921beff64ea384e69c12017498a60a9a867136e8d64a4815bf1f";
        const string SuccessfulWriteEvidenceSha="a5ea7c7d03fbad1088de4e291109f3cf025db8ff3b5d157e617e8259d505814b";
        const string AfterSaveInspectEvidenceSha="bb031205266e035dfce145c88f374f12a191b96c63d28111b1b88280328f8b3a";
        const string FailedPersistenceComparisonSha="ef816211966a5a147aba4e80b48d0da8595b517432dc6b550d7d154f8374fd83";
        const string SuccessfulWriteEngineSha="60030bed77deafe417a630cf2149a49239a81ca553dc6285528cd994da8059ec";
        const string ContinuationSessionSha="1bb9fdff06f88d8afea7eb77ad4949937017e3e4015c9f666154d0e78cabef19";
        const string ContinuationSummarySha="653a3ad345aa4f535fb20a3ec60a1128e506783d45a2648e856a330bcfda9892";
        const string ContinuationComparisonSha="dc2d803892e08bdb1640229afd01d46bcfd32c551e307f60b9ecc647399ff2fd";
        const string ContinuationDecisionSha="6fca01d770dfed5d195e91b69ae91215eb57dbf04c4750d7919ad57fb6123b07";
        const string LanguageBefore="binary:175862:4c67f54265220d9f8a405bfc6e9a748dbedee4dc2ba2f9475e288fb3e5c10904";
        const string LanguageAfter="binary:197316:83718e78f9eb967c390d652fd4f314b84ff5c20b82e8eba69cc378c8404c8e03";
        static int flushAttempted;
        const int RootDocVtableRva=0xD57684,ManagerVtableRva=0xDDD094,BlockVtableRva=0xE3B4DC;
        internal sealed class Api {
            internal readonly NativeEngine Engine;
            readonly NativeLazyFunctionProfile functions;
            internal Api(NativeEngine engine) {
                Engine=engine;
                NativeMemory.Require(IntPtr.Size==4,"Strategy ABI requires the actual x86 editor context.");
                NativeMemory.Require(EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Strategy operation is outside the host UI thread.");
                functions=NativeProjectIdentity.Functions(engine);
            }
            internal IntPtr AddressOf(string key){return functions.Address(key);}
            internal T Bind<T>(string key)where T:class{
                if(key=="RootIsModified"||key=="RootSetModified"){
                    IntPtr doc=RootDoc();MatchVirtual(doc,key=="RootIsModified"?26:27,key);
                    if(key=="RootSetModified")NativeMemory.Readable(NativeMemory.Add(doc,0x114),4);
                }
                return functions.Bind<T>(key);
            }
            internal void MatchVirtual(IntPtr instance,int slot,string key){NativeMemory.Require(Engine.Virtual(instance,slot)==ExpectedThunk(key),"Native virtual method differs: "+key);}
            IntPtr ExpectedThunk(string key) {
                int rva;
                switch(key) {
                    case "StartupName":rva=0x39F13;break; // 0x439F13 -> 0xE9BA00
                    case "StartupId":rva=0x28BBE;break; // 0x428BBE -> 0xE9BBF0
                    case "StrategyModule":rva=0x28F1F;break; // 0x428F1F -> 0xC24F50
                    case "BlockReplaceText":rva=0x2B1AC;break; // 0x42B1AC -> 0xE9BCA0
                    case "BlockFindText":rva=0x358FA;break; // 0x4358FA -> 0xE9BD30
                    case "RootIsModified":rva=0x3508A;break;
                    case "RootSetModified":rva=0x9665;break;
                    case "StrategyPreloadSaveData":rva=0x114A5;break;
                    case "StrategyPreloadSetDirty":rva=0x15186;break;
                    case "StrategyDataDirtyGetter":rva=0x4A54D;break;
                    default:throw new InvalidOperationException("Unknown virtual guard.");
                }
                return Engine.Address(rva);
            }
            internal IntPtr RootDoc() {
                return NativeProjectIdentity.RootDocument(Engine,functions);
            }
        }
        internal sealed class CString : IDisposable {
            readonly Api api;internal readonly IntPtr Storage;bool constructed;
            internal CString(Api value,string text) {
                api=value;api.Bind<Void0>("CStringDtor");api.Bind<Ptr0>("CStringDefaultCtor");api.Bind<Ptr1>("CStringAssignWide");Storage=Marshal.AllocHGlobal(4);Marshal.WriteInt32(Storage,0);
                try {
                    api.Bind<Ptr0>("CStringDefaultCtor")(Storage);constructed=true;
                    IntPtr wide=Marshal.StringToHGlobalUni(text);
                    try{api.Bind<Ptr1>("CStringAssignWide")(Storage,wide);}finally{Marshal.FreeHGlobal(wide);}
                }catch{Dispose();throw;}
            }
            CString(Api value){api=value;api.Bind<Void0>("CStringDtor");Storage=Marshal.AllocHGlobal(4);Marshal.WriteInt32(Storage,0);}
            internal static CString Name(Api api,IntPtr instance) {
                api.Bind<Ptr1>("StartupName");var result=new CString(api);try{api.MatchVirtual(instance,9,"StartupName");api.Bind<Ptr1>("StartupName")(instance,result.Storage);result.constructed=true;return result;}catch{result.Dispose();throw;}
            }
            internal static CString NameVirtual(Api api,IntPtr instance) {
                api.Engine.Describe(instance);
                var result=new CString(api);try{api.Engine.Bind<Ptr1>(api.Engine.Virtual(instance,9))(instance,result.Storage);result.constructed=true;return result;}catch{result.Dispose();throw;}
            }
            [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr KeyFactory(IntPtr output,int propertyId);
            internal static CString PropertyKey(Api api,int propertyId) {
                api.Bind<KeyFactory>("PropertyKeyName");var result=new CString(api);try{api.Bind<KeyFactory>("PropertyKeyName")(result.Storage,propertyId);result.constructed=true;return result;}catch{result.Dispose();throw;}
            }
            internal string Read() {
                IntPtr text=NativeMemory.Ptr(Storage,0);NativeMemory.Require(text!=IntPtr.Zero,"Native CString has no data.");var result=new StringBuilder();
                for(int i=0;i<256;i++){IntPtr at=NativeMemory.Add(text,2*i);NativeMemory.Readable(at,2);char c=(char)(ushort)Marshal.ReadInt16(at);if(c==0)return result.ToString();result.Append(c);}
                throw new InvalidOperationException("Native name exceeds trial bound.");
            }
            public void Dispose(){try{if(constructed){constructed=false;api.Bind<Void0>("CStringDtor")(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
        }
        sealed class Matcher : IDisposable {
            readonly Api api;internal readonly IntPtr Storage;bool constructed;
            internal Matcher(Api value) {
                api=value;api.Bind<Void0>("MatcherDtor");api.Bind<MatcherConstructor>("MatcherCtor");Storage=Marshal.AllocHGlobal(2);
                try{api.Bind<MatcherConstructor>("MatcherCtor")(Storage,0,1);constructed=true;NativeMemory.Require(Marshal.ReadByte(Storage)==0 && Marshal.ReadByte(Storage,1)==1,"Native TextOnly matcher differs.");}catch{Dispose();throw;}
            }
            public void Dispose(){try{if(constructed){constructed=false;api.Bind<Void0>("MatcherDtor")(Storage);}}finally{Marshal.FreeHGlobal(Storage);}}
        }
        internal static string ReadName(Api api,IntPtr instance){using(var name=CString.NameVirtual(api,instance))return name.Read();}
        internal static int ReadId(Api api,IntPtr instance){api.Engine.Describe(instance);return api.Engine.Bind<Int0>(api.Engine.Virtual(instance,14))(instance);}
        internal static string ReadBorrowedCString(IntPtr storage,int maximum) {
            IntPtr text=NativeMemory.Ptr(storage,0);NativeMemory.Require(text!=IntPtr.Zero,"Borrowed CString has no data.");var result=new StringBuilder();
            for(int i=0;i<maximum;i++){IntPtr at=NativeMemory.Add(text,2*i);NativeMemory.Readable(at,2);char c=(char)(ushort)Marshal.ReadInt16(at);if(c==0)return result.ToString();result.Append(c);}
            throw new InvalidOperationException("Borrowed CString exceeds bounded length.");
        }
        internal static int MarkRootDirty(Api api) {
            IntPtr root=api.RootDoc();int modified=api.Bind<Int0>("RootIsModified")(root);NativeMemory.Require(modified==0 || modified==1,"Unexpected root dirty state.");
            int compile=NativeMemory.I32(root,0x114);NativeMemory.Require(compile==0 || compile==1,"Unexpected compile-valid representation.");
            NativeOperationTrace.BeforeMutation("mark-root-dirty");
            api.Bind<VoidInt>("RootSetModified")(root,1);Marshal.WriteInt32(NativeMemory.Add(root,0x114),0);return modified;
        }
        static Dictionary<string,object> RequireSessionPreimage(string fixture) {
            string pristine=Path.Combine(NativeOperations.TaskRoot,"evidence","pristine-fixture.MCP");
            string directory=Path.Combine(NativeOperations.TaskRoot,"verification","session-open-baseline-0001");
            string summaryPath=Path.Combine(directory,"session-baseline-summary.json");
            string comparisonPath=Path.Combine(directory,"full-field-comparison.json");
            NativeMemory.Require(NativeMemory.Hash(pristine)==FixtureSha,"Immutable prepared pristine fixture differs.");
            NativeMemory.Require(NativeMemory.Hash(summaryPath)==SessionSummarySha && NativeMemory.Hash(comparisonPath)==SessionComparisonSha,
                "Approved session semantic-baseline evidence differs; do not replace it with an unreviewed hash.");
            var json=new JavaScriptSerializer();
            var summary=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(summaryPath,Encoding.UTF8));
            var comparison=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(comparisonPath,Encoding.UTF8));
            NativeMemory.Require(Convert.ToInt32(summary["schema"])==1 && Convert.ToBoolean(summary["ok"]) &&
                Convert.ToString(summary["pristine_sha256"])==FixtureSha && Convert.ToString(summary["session_sha256"])==SessionSha &&
                Convert.ToString(summary["shared_live_sha256"])==SessionSha && Convert.ToInt32(summary["table_count"])==12 &&
                Convert.ToInt32(summary["total_rows"])==158 && Convert.ToInt32(summary["total_fields"])==604 &&
                Convert.ToBoolean(summary["table_column_schemas_and_row_counts_equal"]) && Convert.ToBoolean(summary["all_field_fingerprints_equal"]) &&
                Convert.ToInt32(summary["changed_fields"])==0 && !Convert.ToBoolean(summary["project_written"]),
                "Approved session evidence does not prove the exact complete unchanged user-data baseline.");
            var guard=(Dictionary<string,object>)summary["reliable_session_guard"];
            NativeMemory.Require(Path.GetFullPath(Convert.ToString(guard["current_file"])).Equals(fixture,StringComparison.OrdinalIgnoreCase) &&
                Convert.ToString(guard["required_current_sha256"])==SessionSha &&
                Convert.ToBoolean(guard["source_unchanged_during_snapshot_and_capture"]) && Convert.ToBoolean(guard["latest_shared_hash_matches_snapshot"]) &&
                !Convert.ToBoolean(guard["permission_to_skip_complete_source_preimage"]),"Session guard identity or source-read stability differs.");
            string[] names={"Alarm","Data","DDEConnection","DDEConnectionPoint","SecurityGroup","SecurityUser","Stgy","System","Trigger","WndControl","WndDevice","WndUser"};
            int[] rows={0,0,0,0,32,1,1,106,5,1,1,11},columns={19,18,8,6,5,7,6,3,7,6,6,6};
            var expected=new Dictionary<string,int>();for(int i=0;i<names.Length;i++)expected.Add(names[i],i);
            var seen=new HashSet<string>();
            foreach(object item in (IEnumerable)summary["tables"]) {
                var table=(Dictionary<string,object>)item;string name=Convert.ToString(table["table"]);
                NativeMemory.Require(expected.ContainsKey(name) && seen.Add(name),"Session table inventory has an unexpected or duplicate table.");
                int i=expected[name];NativeMemory.Require(Convert.ToInt32(table["rows"])==rows[i] && Convert.ToInt32(table["columns"])==columns[i] &&
                    Convert.ToInt32(table["field_values"])==rows[i]*columns[i] && Convert.ToBoolean(table["all_fields_equal"]),
                    "Session table schema/row/field equality differs: "+name);
            }
            NativeMemory.Require(seen.Count==12 && Convert.ToBoolean(comparison["equal"]) && Convert.ToInt32(comparison["count"])==0 &&
                Convert.ToString(comparison["left_sha256"])==FixtureSha && Convert.ToString(comparison["right_sha256"])==SessionSha &&
                !Convert.ToBoolean(comparison["source_written"]),"Full-field comparison is not the approved zero-difference pair.");
            foreach(object ignored in (IEnumerable)comparison["changes"])throw new InvalidOperationException("Full-field comparison contains a change.");
            NativeMemory.Require(NativeMemory.Hash(fixture)==SessionSha,"Current shared fixture hash differs from the approved semantically pristine session snapshot.");
            return new Dictionary<string,object>{{"pristine_sha256",FixtureSha},{"session_sha256",SessionSha},
                {"summary_sha256",SessionSummarySha},{"comparison_sha256",SessionComparisonSha},
                {"tables",12},{"rows",158},{"fields",604},{"changed_fields",0},
                {"complete_live_source_preimage_still_required",true},{"physical_rewrite_cause_claimed",false}};
        }
        static IntPtr Startup(Api api) {
            IntPtr manager=api.Engine.Call<NativeEngine.CdeclModule>("GetModuleObject")(3);
            NativeMemory.Require(manager!=IntPtr.Zero && NativeMemory.Ptr(manager,0)==api.Engine.Address(ManagerVtableRva),"Strategy module manager differs.");
            var description=api.Engine.Describe(manager);NativeMemory.Require(Convert.ToString(description["rtti"])==".?AVStrategyObjectManager@@" && Convert.ToInt32(description["module"])==3,"Strategy manager RTTI/module differs.");
            IntPtr selected=IntPtr.Zero;int matched=0;
            foreach(IntPtr block in api.Engine.Children(manager)) {
                NativeMemory.Require(NativeMemory.Ptr(block,0)==api.Engine.Address(BlockVtableRva),"A strategy child is not the verified CStrategyBlock IObject base.");
                api.MatchVirtual(block,14,"StartupId");api.MatchVirtual(block,20,"StrategyModule");api.MatchVirtual(block,23,"BlockReplaceText");api.MatchVirtual(block,24,"BlockFindText");
                NativeMemory.Require(api.Bind<Int0>("StrategyModule")(block)==3,"Strategy child is from another module.");
                if(api.Bind<Int0>("StartupId")(block)!=0)continue;
                using(var name=CString.Name(api,block))NativeMemory.Require(name.Read()=="启动策略","Native strategy ID zero has an unexpected name.");
                selected=block;matched++;
            }
            NativeMemory.Require(matched==1,"Startup strategy identity is not unique.");return selected;
        }
        static IntPtr StrategyPreloadable(Api api,IntPtr target) {
            NativeMemory.Require(NativeMemory.Ptr(target,-4)==api.Engine.Address(0xE3B4B8),"Startup complete-object primary vtable differs.");
            IntPtr preload=NativeMemory.Add(target,4);
            NativeMemory.Require(NativeMemory.Ptr(preload,0)==api.Engine.Address(0xE3B56C),"Startup IPreLoadable secondary vtable differs.");
            api.MatchVirtual(preload,2,"StrategyPreloadSaveData");api.MatchVirtual(preload,3,"StrategyPreloadSetDirty");
            api.MatchVirtual(target,28,"StrategyDataDirtyGetter");return preload;
        }
        static int StrategyDataDirty(Api api,IntPtr target) {
            StrategyPreloadable(api,target);IntPtr at=NativeMemory.Add(target,0x60);NativeMemory.Readable(at,1);
            byte value=Marshal.ReadByte(at);NativeMemory.Require(value<=1 && api.Bind<Bool0>("StrategyDataDirtyGetter")(target)==(value!=0),
                "Startup dirty byte and guarded native getter disagree.");return value;
        }
        static void RequireLanguageDelta(Dictionary<string,object> delta) {
            NativeMemory.Require(Convert.ToString(delta["table"])=="System" && Convert.ToString(delta["key"])=="MCGSLINGUIST" &&
                Convert.ToString(delta["field"])=="lbContext" && Convert.ToString(delta["action"])=="field_changed" &&
                Convert.ToString(delta["before"])==LanguageBefore && Convert.ToString(delta["after"])==LanguageAfter,
                "Continuation delta is not the exact one reviewed language-registry field.");
        }
        static Dictionary<string,object> RequireFlushContinuationSession(string fixture) {
            string directory=Path.Combine(NativeOperations.TaskRoot,"verification","session-postcopy-baseline-0001");
            string summaryFile=Path.Combine(directory,"session-baseline-summary.json"),comparisonFile=Path.Combine(directory,"full-field-comparison.json");
            string decisionFile=Path.Combine(directory,"strategy-flush-continuation-decision.json");
            NativeMemory.Require(NativeMemory.Hash(summaryFile)==ContinuationSummarySha && NativeMemory.Hash(comparisonFile)==ContinuationComparisonSha &&
                NativeMemory.Hash(decisionFile)==ContinuationDecisionSha,"Post-copy continuation evidence or the root bounded decision differs.");
            var json=new JavaScriptSerializer();
            var summary=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(summaryFile,Encoding.UTF8));
            var comparison=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(comparisonFile,Encoding.UTF8));
            var decision=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(decisionFile,Encoding.UTF8));
            NativeMemory.Require(Convert.ToInt32(summary["schema"])==1 && !Convert.ToBoolean(summary["ok"]) &&
                !Convert.ToBoolean(summary["guard_rebase_allowed"]) && !Convert.ToBoolean(summary["all_field_fingerprints_equal"]) &&
                Convert.ToInt32(summary["field_change_count"])==1 && Convert.ToBoolean(summary["all_other_fields_unchanged"]) &&
                Convert.ToBoolean(summary["table_column_schemas_and_row_counts_equal"]) && Convert.ToInt32(summary["table_count"])==12 &&
                Convert.ToInt32(summary["row_count"])==159 && Convert.ToInt32(summary["field_count"])==610 &&
                Convert.ToString(summary["previous_sha256"])==SavedCopySha && Convert.ToString(summary["current_sha256"])==ContinuationSessionSha &&
                Convert.ToString(summary["current_shared_read_sha256"])==ContinuationSessionSha && Convert.ToBoolean(summary["current_shared_hash_matches_snapshot"]),
                "Post-copy baseline is not the exact explicitly incomplete one-field-change evidence.");
            NativeMemory.Require(!Convert.ToBoolean(comparison["equal"]) && Convert.ToInt32(comparison["count"])==1 &&
                Convert.ToString(comparison["left_sha256"])==SavedCopySha && Convert.ToString(comparison["right_sha256"])==ContinuationSessionSha &&
                !Convert.ToBoolean(comparison["source_written"]),"Post-copy comparison pair/count differs.");
            int changes=0;foreach(object item in (IEnumerable)comparison["changes"]){RequireLanguageDelta((Dictionary<string,object>)item);changes++;}
            NativeMemory.Require(changes==1,"Post-copy comparison must contain exactly the one accepted continuation delta.");
            changes=0;foreach(object item in (IEnumerable)summary["changes"]){RequireLanguageDelta((Dictionary<string,object>)item);changes++;}
            NativeMemory.Require(changes==1,"Post-copy summary must retain its exact one-field difference.");
            string[] names={"Alarm","Data","DDEConnection","DDEConnectionPoint","SecurityGroup","SecurityUser","Stgy","System","Trigger","WndControl","WndDevice","WndUser"};
            int[] rows={0,0,0,0,32,1,1,106,5,1,1,12},columns={19,18,8,6,5,7,6,3,7,6,6,6};
            var expected=new Dictionary<string,int>();for(int i=0;i<names.Length;i++)expected.Add(names[i],i);var seen=new HashSet<string>();
            foreach(object item in (IEnumerable)summary["tables"]) {
                var table=(Dictionary<string,object>)item;string name=Convert.ToString(table["table"]);
                NativeMemory.Require(expected.ContainsKey(name) && seen.Add(name),"Post-copy table inventory differs.");int i=expected[name];
                NativeMemory.Require(Convert.ToInt32(table["rows"])==rows[i] && Convert.ToInt32(table["columns"])==columns[i] &&
                    Convert.ToInt32(table["fields"])==rows[i]*columns[i] && Convert.ToBoolean(table["all_fields_equal"])==(name!="System"),
                    "Post-copy table dimensions or field-equality boundary differs.");
            }
            NativeMemory.Require(seen.Count==12,"Post-copy table inventory is incomplete.");
            NativeMemory.Require(Convert.ToInt32(decision["schema"])==1 && Convert.ToString(decision["decision_id"])=="root-strategy-dirty-continuation-0001" &&
                Path.GetFullPath(Convert.ToString(decision["current_file"])).Equals(fixture,StringComparison.OrdinalIgnoreCase) &&
                Convert.ToInt32(decision["process_id"])==Process.GetCurrentProcess().Id && Convert.ToInt32(decision["native_thread_id"])==NativeMemory.GetCurrentThreadId() &&
                Convert.ToString(decision["prior_saved_copy_sha256"])==SavedCopySha && Convert.ToString(decision["continuation_sha256"])==ContinuationSessionSha &&
                Convert.ToString(decision["summary_sha256"])==ContinuationSummarySha && Convert.ToString(decision["comparison_sha256"])==ContinuationComparisonSha &&
                !Convert.ToBoolean(decision["source_replace_permitted"]) && !Convert.ToBoolean(decision["direct_language_write_permitted"]) &&
                !Convert.ToBoolean(decision["full_validation"]) && Convert.ToBoolean(decision["language_semantics_pending"]) &&
                Convert.ToBoolean(decision["continue_strategy_dirty_only"]) && Convert.ToInt32(decision["other_field_values_unchanged"])==609 &&
                Convert.ToInt32(decision["table_count"])==12 && Convert.ToInt32(decision["row_count"])==159 && Convert.ToInt32(decision["field_count"])==610 &&
                Convert.ToBoolean(decision["persisted_strategy_fields_unchanged_from_prior_saved_copy"]) &&
                !Convert.ToBoolean(decision["summary_zero_difference_claimed"]) && Convert.ToBoolean(decision["summary_original_flags_must_remain_unchanged"]),
                "Root continuation decision does not permit only the already-authorized strategy dirty notification.");
            RequireLanguageDelta((Dictionary<string,object>)decision["accepted_delta"]);
            var actions=new HashSet<string>();foreach(object action in (IEnumerable)decision["allowed_actions"])NativeMemory.Require(actions.Add(Convert.ToString(action)),"Duplicate continuation action.");
            NativeMemory.Require(actions.Count==2 && actions.Contains("strategy-flush-test") && actions.Contains("native-save-root-only"),"Root continuation action scope differs.");
            NativeMemory.Require(NativeMemory.Hash(fixture)==ContinuationSessionSha,"Current shared fixture differs from the latest bounded continuation snapshot.");
            return new Dictionary<string,object>{{"current_sha256",ContinuationSessionSha},{"summary_sha256",ContinuationSummarySha},
                {"comparison_sha256",ContinuationComparisonSha},{"root_decision_sha256",ContinuationDecisionSha},
                {"accepted_delta",decision["accepted_delta"]},{"other_unchanged_field_values",609},
                {"original_summary_guard_rebase_allowed",false},{"full_validation",false},{"language_semantics_pending",true},
                {"scope","strategy dirty notification and subsequent root-only save; no repeated replace or direct language edit"}};
        }
        static Dictionary<string,object> RequireSuccessfulWriteBeforeFlush(Api api,IntPtr root,IntPtr target,string fixture) {
            string evidence=Path.Combine(NativeOperations.TaskRoot,"evidence");
            string writeFile=Path.Combine(evidence,"strategy_replace_test_001.json"),inspectFile=Path.Combine(evidence,"strategy_inspect_after_save_001.json");
            string comparisonFile=Path.Combine(NativeOperations.TaskRoot,"verification","final-readback-0001","comparison.json");
            NativeMemory.Require(NativeMemory.Hash(writeFile)==SuccessfulWriteEvidenceSha && NativeMemory.Hash(inspectFile)==AfterSaveInspectEvidenceSha &&
                NativeMemory.Hash(comparisonFile)==FailedPersistenceComparisonSha,"Approved successful-write / failed-persistence evidence differs.");
            var json=new JavaScriptSerializer();
            var write=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(writeFile,Encoding.UTF8));
            var inspect=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(inspectFile,Encoding.UTF8));
            var comparison=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(comparisonFile,Encoding.UTF8));
            int process=Process.GetCurrentProcess().Id,thread=NativeMemory.GetCurrentThreadId();
            foreach(var item in new[]{write,inspect}) {
                NativeMemory.Require(Convert.ToBoolean(item["ok"]) && Convert.ToInt32(item["strategy_id"])==0 &&
                    Convert.ToString(item["strategy_name"])=="启动策略" && Convert.ToInt32(item["process_id"])==process &&
                    Convert.ToInt32(item["native_thread_id"])==thread && Convert.ToString(item["engine_assembly"])=="McgsInternalEngine_0006.dll" &&
                    Convert.ToString(item["engine_sha256"])==SuccessfulWriteEngineSha &&
                    Convert.ToString(item["strategy_iobject"]).Equals(NativeMemory.Hex(target),StringComparison.OrdinalIgnoreCase) &&
                    Path.GetFullPath(Convert.ToString(item["actual_project"])).Equals(fixture,StringComparison.OrdinalIgnoreCase),
                    "Prior strategy evidence is not for this exact native object, process, UI thread and isolated project.");
            }
            NativeMemory.Require(Convert.ToInt32(write["changed_count"])==1 && Convert.ToBoolean(write["write_attempted"]) &&
                Convert.ToString(write["search_body_before"])==OldBody && Convert.ToString(write["search_body_after"])==NewBody &&
                Convert.ToBoolean(write["disk_unchanged_before_save"]) &&
                !Convert.ToBoolean(inspect["old_body_found"]) && Convert.ToBoolean(inspect["new_body_found"]) &&
                Convert.ToInt32(inspect["root_modified"])==0 && Convert.ToInt32(inspect["compile_valid_field"])==1 &&
                Convert.ToString(inspect["root_document"]).Equals(NativeMemory.Hex(root),StringComparison.OrdinalIgnoreCase),
                "Prior successful replacement/post-save source state differs; replacement must not be repeated.");
            NativeMemory.Require(Convert.ToString(comparison["before_sha256"])==FixtureSha && Convert.ToString(comparison["after_sha256"])==SavedCopySha,
                "Prior failed-persistence comparison no longer matches its original saved/copy snapshot.");
            var continuation=RequireFlushContinuationSession(fixture);
            return new Dictionary<string,object>{{"write_evidence_sha256",SuccessfulWriteEvidenceSha},{"after_save_inspect_sha256",AfterSaveInspectEvidenceSha},
                {"failed_persistence_comparison_sha256",FailedPersistenceComparisonSha},{"saved_copy_sha256",SavedCopySha},
                {"original_successful_replace_count",1},{"repeat_replace_allowed",false},{"same_process_and_UI_thread",true},{"continuation_session",continuation}};
        }
        internal static Dictionary<string,object> Flush(NativeEngine engine,string expectedProject) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(Path.GetFullPath(expectedProject).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Strategy flush is limited to its exact isolated fixture.");
            NativeMemory.Require(Interlocked.CompareExchange(ref flushAttempted,0,0)==0,"This engine revision already attempted the strategy flush; inspect evidence instead of retrying.");
            var api=new Api(engine);IntPtr root=api.RootDoc(),target=Startup(api),preload=StrategyPreloadable(api,target);
            var evidence=RequireSuccessfulWriteBeforeFlush(api,root,target,fixture);
            NativeMemory.Require(api.Bind<Int0>("RootIsModified")(root)==0 && NativeMemory.I32(root,0x114)==1,"Strategy flush requires the exact saved root state.");
            int dirtyBefore=StrategyDataDirty(api,target);
            using(var oldText=new CString(api,OldBody))using(var newText=new CString(api,NewBody))using(var matcher=new Matcher(api)) {
                var find=api.Bind<FindText>("BlockFindText");
                NativeMemory.Require(!find(target,oldText.Storage,matcher.Storage) && find(target,newText.Storage,matcher.Storage),
                    "Current native strategy is not the verified already-updated body; do not repeat replacement.");
                NativeMemory.Require(NativeMemory.Hash(fixture)==ContinuationSessionSha && Interlocked.CompareExchange(ref flushAttempted,1,0)==0,
                    "Saved/copy fixture or single-attempt guard changed before native flush.");
                MarkRootDirty(api);
                NativeOperationTrace.SetPhase("strategy-preloadable-set-dirty");api.Bind<VoidInt>("StrategyPreloadSetDirty")(preload,1);
                NativeMemory.Require(StrategyDataDirty(api,target)==1,"Native strategy block was not marked for serialization.");
                NativeOperationTrace.SetPhase("strategy-preloadable-save-data-void");api.Bind<Void0>("StrategyPreloadSaveData")(preload);
                int dirtyAfter=StrategyDataDirty(api,target);
                NativeMemory.Require(dirtyAfter==1 && !find(target,oldText.Storage,matcher.Storage) && find(target,newText.Storage,matcher.Storage) &&
                    api.Bind<Int0>("RootIsModified")(root)==1 && NativeMemory.I32(root,0x114)==0,
                    "Strategy flush did not retain updated source plus block/root dirty and compile-invalid state.");
                NativeOperationTrace.SetPhase("strategy-flush-dispatched-requires-native-save");
                return new Dictionary<string,object>{{"ok",true},{"strategy_iobject",NativeMemory.Hex(target)},{"preloadable",NativeMemory.Hex(preload)},
                    {"root_document",NativeMemory.Hex(root)},{"strategy_id",0},{"strategy_name","启动策略"},{"module",3},
                    {"block_dirty_before",dirtyBefore},{"block_dirty_after",dirtyAfter},{"root_modified",1},{"compile_valid_field",0},
                    {"old_body_found",false},{"new_body_found",true},{"replace_called",false},{"original_write_evidence",evidence},
                    {"preload_set_dirty_called",true},{"preload_save_data_void_dispatched",true},{"void_return_interpreted_as_success",false},
                    {"whole_native_save_required",true},{"native_save_verified",false},{"disk_persistence_verified",false},
                    {"source_raw_readback",false},{"write_attempted",true},{"native_business_method_called",true},
                    {"full_validation",false},{"language_semantics_pending",true},
                    {"disk_unchanged_before_whole_save",NativeMemory.Hash(fixture)==ContinuationSessionSha}};
            }
        }
        internal static Dictionary<string,object> Inspect(NativeEngine engine) {
            var api=new Api(engine);IntPtr root=api.RootDoc(),target=Startup(api);
            using(var oldText=new CString(api,OldSource))using(var newText=new CString(api,NewSource))
            using(var oldBody=new CString(api,OldBody))using(var newBody=new CString(api,NewBody))using(var matcher=new Matcher(api)) {
                return new Dictionary<string,object>{{"strategy_iobject",NativeMemory.Hex(target)},{"root_document",NativeMemory.Hex(root)},
                    {"strategy_id",0},{"strategy_name","启动策略"},{"module",3},{"root_modified",api.Bind<Int0>("RootIsModified")(root)},
                    {"compile_valid_field",NativeMemory.I32(root,0x114)},
                    {"block_data_modified",StrategyDataDirty(api,target)},
                    {"old_marker_found",api.Bind<FindText>("BlockFindText")(target,oldText.Storage,matcher.Storage)},
                    {"new_marker_found",api.Bind<FindText>("BlockFindText")(target,newText.Storage,matcher.Storage)},
                    {"old_body_found",api.Bind<FindText>("BlockFindText")(target,oldBody.Storage,matcher.Storage)},
                    {"new_body_found",api.Bind<FindText>("BlockFindText")(target,newBody.Storage,matcher.Storage)},
                    {"body_queries_are_not_direct_source_readback",true},{"write_attempted",false}};
            }
        }
        internal static Dictionary<string,object> DiagnoseSource(NativeEngine engine) {
            NativeOperationTrace.SetPhase("strategy-source-diagnose");
            var api=new Api(engine);IntPtr root=api.RootDoc(),target=Startup(api);
            int modified=api.Bind<Int0>("RootIsModified")(root),compile=NativeMemory.I32(root,0x114);
            var queries=new List<Dictionary<string,object>>();
            string[] keys={"old_full_crlf","old_body_no_line_end","old_full_lf","old_full_cr","old_marker_only",
                           "new_full_crlf","new_body_no_line_end","new_marker_only"};
            string[] texts={OldSource,OldBody, "' BRIDGE_PRO_SOURCE_INITIAL\n",
                            "' BRIDGE_PRO_SOURCE_INITIAL\r","BRIDGE_PRO_SOURCE_INITIAL",NewSource,
                            NewBody,"BRIDGE_PRO_SOURCE_UPDATED"};
            using(var matcher=new Matcher(api)) {
                var find=api.Bind<FindText>("BlockFindText");
                for(int i=0;i<texts.Length;i++)using(var text=new CString(api,texts[i])) {
                    string nativeQuery=text.Read();NativeMemory.Require(nativeQuery==texts[i],"Native search CString differs from its managed diagnostic input.");
                    queries.Add(new Dictionary<string,object>{{"key",keys[i]},{"text",texts[i]},
                        {"native_query_readback",nativeQuery},{"native_query_roundtrip_equal",true},
                        {"utf16le_hex",BitConverter.ToString(Encoding.Unicode.GetBytes(texts[i])).Replace("-","").ToLowerInvariant()},
                        {"found",find(target,text.Storage,matcher.Storage)}});
                }
            }
            NativeMemory.Require(api.Bind<Int0>("RootIsModified")(root)==modified && NativeMemory.I32(root,0x114)==compile,
                "Read-only strategy source diagnosis changed the root document state.");
            return new Dictionary<string,object>{{"ok",true},{"strategy_iobject",NativeMemory.Hex(target)},
                {"strategy_id",0},{"strategy_name","启动策略"},{"module",3},{"queries",queries},
                {"matcher_pattern",0},{"matcher_case_sensitive",true},{"matcher_semantics","plain native substring; no line-ending normalization"},
                {"root_modified_before",modified},{"root_modified_after",modified},
                {"compile_valid_before",compile},{"compile_valid_after",compile},
                {"source_field_pointer_walk_attempted",false},{"direct_source_bytes_acquired",false},
                {"write_attempted",false},{"native_business_method_called",true},
                {"scope","bounded findText diagnosis only; a short match alone is not a complete source preimage"}};
        }
        internal static Dictionary<string,object> Write(NativeEngine engine,string expectedProject) {
            string fixture=NativeEngineeringProjectScope.ExpectedProjectPath;
            NativeMemory.Require(Path.GetFullPath(expectedProject).Equals(fixture,StringComparison.OrdinalIgnoreCase),"Strategy write is limited to its prepared isolated fixture.");
            var sessionPreimage=RequireSessionPreimage(fixture);
            var api=new Api(engine);IntPtr root=api.RootDoc(),target=Startup(api);
            NativeMemory.Require(api.Bind<Int0>("RootIsModified")(root)==0,"Live project is already modified; the pristine fixture preimage is no longer sufficient.");
            int compileBefore=NativeMemory.I32(root,0x114);NativeMemory.Require(compileBefore==0 || compileBefore==1,"Unexpected compile-valid field representation.");
            using(var oldText=new CString(api,OldBody))using(var newText=new CString(api,NewBody))using(var matcher=new Matcher(api)) {
                var find=api.Bind<FindText>("BlockFindText");var replace=api.Bind<ReplaceText>("BlockReplaceText");
                NativeMemory.Require(find(target,oldText.Storage,matcher.Storage) && !find(target,newText.Storage,matcher.Storage),"Unique prepared source-marker preimage does not match.");
                NativeMemory.Require(NativeMemory.Hash(fixture)==SessionSha,"Session fixture changed immediately before the first native write.");
                // Replicates the proven root-document portion of 0xACE5A0.
                // Root C0DocManage has NO slot 0x180. This deliberately does not claim editor undo/title refresh.
                MarkRootDirty(api);
                NativeOperationTrace.SetPhase("strategy-replace");
                int count=replace(target,oldText.Storage,newText.Storage,matcher.Storage);
                NativeMemory.Require(count==1,"Native strategy replacement changed an unexpected number of fields: "+count);
                NativeMemory.Require(!find(target,oldText.Storage,matcher.Storage) && find(target,newText.Storage,matcher.Storage),"Native source-marker postimage does not match.");
                NativeMemory.Require(api.Bind<Int0>("RootIsModified")(root)==1 && NativeMemory.I32(root,0x114)==0,"Root document dirty/compile-invalid state was not retained.");
                NativeOperationTrace.SetPhase("verified");
                return new Dictionary<string,object>{{"ok",true},{"strategy_name","启动策略"},{"strategy_id",0},{"module",3},{"strategy_iobject",NativeMemory.Hex(target)},
                    {"changed_count",count},{"search_body_before",OldBody},{"search_body_after",NewBody},
                    {"search_bodies_are_complete_fixed_fixture_comments",true},{"native_line_endings_included_in_replacement",false},
                    {"direct_source_raw_readback",false},{"persisted_source_before_in_session_baseline",OldSource},
                    {"expected_persisted_source_after",NewSource},{"full_persisted_source_requires_offline_readback",true},
                    {"write_attempted",true},{"native_business_method_called",true},
                    {"root_modified",true},{"compile_valid_before",compileBefore},{"compile_valid_after",0},{"undo_verified",false},
                    {"native_save_verified",false},{"native_compile_verified",false},{"session_preimage",sessionPreimage},
                    {"disk_unchanged_before_save",NativeMemory.Hash(fixture)==SessionSha}};
            }
        }
    }
}
