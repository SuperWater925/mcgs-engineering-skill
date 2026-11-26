// Original whole-project Root85 API. Preserves the worker's own UI and exceptions.
// This is NOT a headless checker and never calls the menu/save-confirm wrappers.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.Globalization;using System.IO;using System.Runtime.InteropServices;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeDomainProjectCheck {
  internal const string Kind="project-check-original-root85";
  internal const string AbiProfileSha="c676217196abd99737c961f6f46b9803e0c4ee37852d965cf1a580d611e1a4a5";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int CheckWorker(IntPtr root);
  [UnmanagedFunctionPointer(CallingConvention.Cdecl)]internal delegate IntPtr MainWindow();
  static Dictionary<string,object> M(object value){return NativePageControlPreparation.Map(value);}
  static string S(Dictionary<string,object> value,string key){return Convert.ToString(value[key],CultureInfo.InvariantCulture);}
  static int N(object value){return NativeEngine.Number(value);}
  static string H(byte[] value){return BitConverter.ToString(value).Replace("-","").ToLowerInvariant();}
  static string C(IntPtr value){return NativeUsableEditPermit.ReadCurrentCString(value,131072);}
  static void Need(bool value,string text){NativeMemory.Require(value,text);}
  static void Target(Dictionary<string,object> action){var target=M(action["target"]);Need(S(action,"kind")==Kind&&target.Count==1&&target.ContainsKey("whole_project")&&Object.Equals(target["whole_project"],true),"Original project check requires only target.whole_project=true.");}
  sealed class Api {
   internal readonly NativeEngine Engine;internal readonly NativeContext Context;internal readonly string Project;internal readonly IntPtr App,Root,Main;
   readonly Dictionary<string,object> profile;internal readonly CheckWorker Worker;
   internal Api(NativeEngine e,NativeContext c,string project){Engine=e;Context=c;Project=Path.GetFullPath(project);Need(Project.Equals(NativeEngineeringProjectScope.ExpectedProjectPath,StringComparison.OrdinalIgnoreCase),"Original check project differs from this explicit request scope.");string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"project-services-prep","domain-project-check-0001","project-check-domain-abi-profile.json");Need(File.Exists(file)&&(File.GetAttributes(file)&(FileAttributes.Directory|FileAttributes.ReparsePoint))==0&&NativeMemory.Hash(file)==AbiProfileSha,"Original Root85 project-check ABI profile differs.");profile=new JavaScriptSerializer{MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));Need(N(profile["schema"])==1&&NativeBinaryIdentity.Observe(S(profile,"binary_sha256"),e.ImageSha256,"NativeDomainProjectCheck:20:editor"),"Original project-check binary/schema differs.");CheckGuards();App=e.Address(0xFBB578);Primary(App,"app");Root=NativeMemory.Ptr(App,NativeLayout.Offset("app.root_document"));Primary(Root,"root");Current();var worker=M(profile["worker"]);Need(N(worker["root_virtual_slot"])==85&&NativeMemory.Ptr(NativeMemory.Ptr(Root,0),85*4)==e.Address(N(worker["slot_entry_rva"])),"Root85 native virtual entry differs.");Worker=e.Bind<CheckWorker>(e.Address(N(worker["rva"])));/* Original read-only Afx main-window getter, not GUI recovery. Its original worker also depends on this actual C0FrmMain object. */Main=e.Bind<MainWindow>(e.Address(N(profile["main_window_getter_rva"])))();Need(Main!=IntPtr.Zero,"Original Root85 has no existing main-frame object; do not invoke a worker that dereferences it.");Primary(Main,"main_window");}
   void Primary(IntPtr value,string key){var t=M(M(profile["tables"])[key]);IntPtr vt=Engine.Address(N(t["vtable_rva"])),col=Engine.Address(N(t["col_rva"])),td=Engine.Address(N(t["type_descriptor_rva"]));Need(value!=IntPtr.Zero&&NativeMemory.Ptr(value,0)==vt&&NativeMemory.Ptr(vt,-4)==col&&NativeMemory.I32(col,4)==0&&NativeMemory.Ptr(col,12)==td&&NativeMemory.Ascii(NativeMemory.Add(td,8),160)==S(t,"rtti"),"Original project-check "+key+" vtable/COL/RTTI differs.");}
   internal void CheckGuards(){Need(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&EngineEntry.ExpectedUiThreadId==NativeMemory.GetCurrentThreadId(),"Original Root85 check requires the captured x86 UI thread.");foreach(object raw in(IEnumerable)profile["guards"]){var g=M(raw);string text=S(g,"bytes");byte[] bytes=new byte[text.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(text.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeCodeRelocation.RebaseDeltaInPlace(bytes,(IEnumerable)g["reloc_offsets"],unchecked((uint)(NativeMemory.U(Engine.ImageBase)-0x400000U)));Need(H(bytes)==H(NativeMemory.Bytes(Engine.Address(N(g["rva"])),bytes.Length)),"Original project-check native body differs: "+S(g,"name"));}}
   internal void Current(){Need(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId==NativeMemory.GetCurrentThreadId(),"Original project check UI thread changed.");Primary(App,"app");Need(NativeMemory.Ptr(App,NativeLayout.Offset("app.root_document"))==Root,"Original project-check root owner changed.");Primary(Root,"root");Need(NativeMemory.Ptr(Root,NativeLayout.Offset("root.object_model"))==Context.ObjectModel&&Path.GetFullPath(C(NativeMemory.Add(Root,0x24))).Equals(Project,StringComparison.OrdinalIgnoreCase)&&Project.Equals(NativeEngineeringProjectScope.ExpectedProjectPath,StringComparison.OrdinalIgnoreCase),"Original project-check live project/root/ObjectModel differs.");}
   internal Dictionary<string,object> State(){Current();Primary(Main,"main_window");return new Dictionary<string,object>{{"process_id",Process.GetCurrentProcess().Id},{"native_thread_id",NativeMemory.GetCurrentThreadId()},{"actual_project",Project},{"project_sha256",NativeMemory.Hash(Project)},{"root",NativeMemory.Hex(Root)},{"main_frame_object",NativeMemory.Hex(Main)},{"main_frame_hwnd_raw",NativeMemory.Hex(NativeMemory.Ptr(Main,0x20))},{"root_modified",NativeMemory.I32(Root,NativeLayout.Offset("document.modified"))},{"root_compile_valid_raw",NativeMemory.I32(Root,NativeLayout.Offset("document.compile_valid"))},{"last_error_owner",C(NativeMemory.Add(Root,0x1C8))},{"last_error_text",C(NativeMemory.Add(Root,0x1CC))},{"first_error_code_raw_uint32",unchecked((uint)NativeMemory.I32(Root,0x1D0))},{"error_count",null},{"warning_count",null},{"error_warning_counts_known",false},{"last_diagnostic_is_complete_error_list",false}};}
   internal Dictionary<string,object> Read(){var state=State();var summary=NativeUsableEditPermit.Capture(Engine,Context);return new Dictionary<string,object>{{"kind",Kind},{"abi_profile_sha256",AbiProfileSha},{"state",state},{"native_summary",summary},{"ready_if_finally_saved",N(state["root_modified"])==0},{"original_worker_ready_with_existing_window",N(state["root_modified"])==0&&NativeMemory.Ptr(Main,0x20)!=IntPtr.Zero},{"calls_full_project_check_in_read",false},{"uses_cached_compile_as_a_new_check",false},{"headless",false},{"original_worker_may_show_modal_UI",true},{"complete_error_warning_counts_known",false}};}
   internal NativeProjectCheckReport PrepareReport(){
    foreach(object value in (IEnumerable)profile["guards"]){
     var guard=M(value);
     if(S(guard,"name")=="WholeModuleCompilePipeline"){
      var worker=M(profile["worker"]);
      return new NativeProjectCheckReport(Engine,Root,Main,Engine.Address(N(worker["rva"])),Engine.Address(N(guard["rva"])));
     }
    }
    throw new InvalidOperationException("The bound Root85 profile lacks the whole-module pipeline role.");
   }
  }
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){Target(action);return new Api(e,c,p).Read();}
  internal static Prepared Prepare(NativeEngine e,NativeContext c,string p,Dictionary<string,object> action){return new Prepared(e,c,p,action);}
  internal sealed class Prepared:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly Api api;readonly Dictionary<string,object> action,before;readonly string disk;bool applied,disposed,failed,entered,returned;int workerResult=Int32.MinValue;Dictionary<string,object> after;
   internal Prepared(NativeEngine e,NativeContext c,string p,Dictionary<string,object> a){Target(a);Need(S(a,"abi_profile_sha256")==AbiProfileSha,"Project-check action ABI differs.");action=a;api=new Api(e,c,p);before=api.Read();NativePageControlPreparation.Before(a,before);var state=M(before["state"]);Need(N(state["root_modified"])==0,"Complete final project saving before the original Root85 check.");Need(NativeMemory.Ptr(api.Main,0x20)!=IntPtr.Zero,"Original Root85 requires its existing main-frame HWND; Read may report zero, but Prepare does not force a UI worker on the windowless instance.");disk=S(state,"project_sha256");var wanted=M(a["after"]);Need(wanted.Count==6,"Project-check after requires all six explicit worker scope acknowledgements.");foreach(string key in new[]{"run_original_root85","confirm_project_already_saved","allow_original_worker_ui","allow_original_worker_persistence","preserve_original_warnings_and_exceptions","accept_unknown_error_warning_counts"})Need(wanted.ContainsKey(key)&&Object.Equals(wanted[key],true),"Original Root85 project-check scope is not explicit: "+key);ValidateBefore();}
   public void ValidateBefore(){Need(!applied&&!failed&&!disposed,"Original project-check preparation has already entered/failed/disposed.");api.CheckGuards();NativePageControlPreparation.Same(before,api.Read(),"Current complete project/check preimage changed after preparation.");Need(NativeMemory.I32(api.Root,NativeLayout.Offset("document.modified"))==0&&NativeMemory.Hash(api.Project)==disk&&NativeMemory.Ptr(api.Main,0x20)!=IntPtr.Zero,"Final saved project SHA/modified state or existing main-frame HWND changed before check.");}
   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){Need(plan.Actions.Count==1&&!plan.Commit&&!plan.RootSaveAllowed,"Original project check is one explicit commit=false/root_save=false action after final persistence; bridge must not run Flush/RootSave.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){
    ValidateBefore();lease.BeginApply(action);
    try{
     lease.RequireApplying(action);api.Current();
     Need(NativeMemory.I32(api.Root,NativeLayout.Offset("document.modified"))==0&&NativeMemory.Hash(api.Project)==disk&&NativeMemory.Ptr(api.Main,0x20)!=IntPtr.Zero,"Saved project identity/SHA or original main-frame HWND changed immediately before Root85.");
     NativeProjectCheckReport report=null;
     Dictionary<string,object> diagnostics=null;
     string unavailable=null;
     try{report=api.PrepareReport();}catch(Exception error){if(!NativeProjectCheckReport.OptionalFailure(error))throw;unavailable=error.Message;}
     NativeOperationTrace.BeforeMutation("original-domain-full-project-check-root85-original-ui-semantics");
     entered=true;workerResult=api.Worker(api.Root);returned=true;
     Need(workerResult==0||workerResult==1,"Original Root85 returned outside its fixed original return contract; no retry.");
     after=api.State();bool passed=workerResult==0&&N(after["root_compile_valid_raw"])==1;
     if(!passed)unavailable="Root85 may have exited before finalizing this run's diagnostics.";
     else if(report!=null){try{diagnostics=report.ReadCompleted();}catch(Exception error){if(!NativeProjectCheckReport.OptionalFailure(error))throw;unavailable=error.Message;}}
     if(diagnostics!=null){
      after["error_count"]=diagnostics["error_count"];after["warning_count"]=diagnostics["warning_count"];
      after["error_warning_counts_known"]=true;
     }
     applied=true;lease.CompleteApply(action);
     return new Dictionary<string,object>{{"ok",true},{"kind",Kind},{"original_full_project_worker_called",true},{"original_worker_call_entered",entered},{"original_worker_returned",returned},{"original_worker_return_int32",workerResult},{"native_check_passed",passed},{"native_check_pass_criterion","this fresh normally returned Root85 result0 and its after compile-valid1; never a cached before flag"},{"state_before",before["state"]},{"state_after",after},{"last_original_root_diagnostic",new Dictionary<string,object>{{"owner",after["last_error_owner"]},{"text",after["last_error_text"]},{"first_code_raw_uint32",after["first_error_code_raw_uint32"]}}},
      {"error_count",diagnostics==null?null:diagnostics["error_count"]},{"warning_count",diagnostics==null?null:diagnostics["warning_count"]},{"error_warning_counts_known",diagnostics!=null},{"all_error_warning_records_covered",diagnostics!=null},{"original_diagnostic_report",diagnostics},{"diagnostics_unavailable_reason",unavailable},
      {"original_ui_semantics_preserved",true},{"headless",false},{"modal_UI_may_have_run",true},{"menu_handler_called",false},{"save_confirmation_wrapper_called",false},{"bridge_flush_or_root_save_called",false},{"original_worker_may_persist_or_compact",true},{"project_sha256_before_worker",disk},{"project_sha256_after_worker",after["project_sha256"]},{"automatic_retry_or_rollback",false},{"final_file_and_close_reopen_acceptance_pending",true}};
    }catch{failed=true;throw;}
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){throw new InvalidOperationException("Original Root85 project-check action has no bridge Flush/RootSave. Use its explicit commit=false plan only.");}
   internal Dictionary<string,object> Status(){return new Dictionary<string,object>{{"kind",Kind},{"original_worker_call_entered",entered},{"original_worker_returned",returned},{"original_worker_return_int32",workerResult},{"state_after",after},{"failed",failed},{"native_outcome_unknown",entered&&!returned},{"automatic_retry_or_rollback",false}};}
   public void Dispose(){disposed=true;/* All native worker-owned contexts are owned and cleaned by the original worker, never guessed freed here. */}
  }
 }

 // Optional post-projection for the original whole-project worker. All role
 // addresses are derived from live relative calls and the owned object's RTTI.
 // The recognized instruction positions describe this pipeline layout only.
 // A different optional layout never feeds a call or blocks Root85 itself.
 internal sealed class NativeProjectCheckReport {
  delegate bool ResourceLanguage(IntPtr module,IntPtr type,IntPtr name,ushort language,IntPtr context);
  [DllImport("kernel32.dll", ExactSpelling=true)]
  static extern bool EnumResourceLanguagesW(IntPtr module,IntPtr type,IntPtr name,ResourceLanguage callback,IntPtr context);
  [DllImport("kernel32.dll", ExactSpelling=true)]
  static extern IntPtr FindResourceExW(IntPtr module,IntPtr type,IntPtr name,ushort language);
  [DllImport("kernel32.dll")]
  static extern uint SizeofResource(IntPtr module,IntPtr resource);
  [DllImport("kernel32.dll")]
  static extern IntPtr LoadResource(IntPtr module,IntPtr resource);
  [DllImport("kernel32.dll")]
  static extern IntPtr LockResource(IntPtr resourceData);
  [DllImport("user32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
  static extern int GetClassNameW(IntPtr window,StringBuilder value,int capacity);
  [DllImport("user32.dll")]
  static extern int GetWindowThreadProcessId(IntPtr window,out uint process);
  [DllImport("user32.dll")]
  static extern IntPtr GetWindow(IntPtr window,uint command);

  const string ReporterType=".?AVObjectErrorDlg@@";
  const int MaxRows=65536, MaxCells=512, MaxTextUnits=1048576;
  readonly NativeEngine engine;
  readonly IntPtr root, reporter, mainWindow, silentCounter;
  readonly int reporterOffset, secondaryOffset, windowOffset, reportTreeOffset;
  readonly int errorOffset, warningOffset, treeValueOffset, listValueOffset;
  readonly uint warningResource;
  readonly int thread;

  internal static bool OptionalFailure(Exception error){return error is InvalidOperationException||error is ArgumentException||error is OverflowException||error is ExternalException||error is EntryPointNotFoundException;}
  static void Need(bool condition,string reason){NativeMemory.Require(condition,reason);}
  static byte[] Hex(string text){var bytes=new byte[text.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(text.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);return bytes;}
  IntPtr Code(IntPtr method,int offset,int size){var address=NativeMemory.Add(method,offset);engine.Rva(address);engine.Rva(NativeMemory.Add(address,size-1));return address;}
  void Expect(IntPtr method,int offset,string expected,string role){
   byte[] bytes=Hex(expected), actual=NativeMemory.Bytes(Code(method,offset,bytes.Length),bytes.Length);
   for(int i=0;i<bytes.Length;i++)Need(actual[i]==bytes[i],"Unrecognized native check report role: "+role+".");
  }
  IntPtr Body(IntPtr pointer){
   for(int depth=0;depth<6;depth++){
    var code=NativeMemory.Bytes(Code(pointer,0,5),5);
    if(code[0]!=0xe9)return pointer;
    pointer=NativeMemory.Add(pointer,checked(5+BitConverter.ToInt32(code,1)));
   }
   throw new InvalidOperationException("Native check report role has no bounded thunk body.");
  }
  IntPtr Called(IntPtr method,int offset){
   var address=Code(method,offset,5);byte[] code=NativeMemory.Bytes(address,5);
   Need(code[0]==0xe8,"Native check report role lacks the original relative call.");
   return Body(NativeMemory.Add(address,checked(5+BitConverter.ToInt32(code,1))));
  }
  int Field(IntPtr method,int offset,string opcode,string role){
   Expect(method,offset,opcode,role);return NativeMemory.I32(Code(method,offset+opcode.Length/2,4),0);
  }
  int SmallField(IntPtr method,int offset,string opcode,string role){
   Expect(method,offset,opcode,role);return Marshal.ReadByte(Code(method,offset+opcode.Length/2,1));
  }
  void ImageRange(IntPtr address,int size){engine.Rva(address);engine.Rva(NativeMemory.Add(address,size-1));NativeMemory.Readable(address,size);}
  static IntPtr Ptr(byte[] raw,int offset){return new IntPtr(BitConverter.ToInt32(raw,offset));}
  IntPtr TypeTable(IntPtr obj,int offset){
   IntPtr table=NativeMemory.Ptr(obj,offset);ImageRange(NativeMemory.Add(table,-4),5*4+4);
   IntPtr col=NativeMemory.Ptr(table,-4);ImageRange(col,20);
   Need(NativeMemory.I32(col,0)==0&&NativeMemory.I32(col,4)==offset&&NativeMemory.I32(col,8)==0,"Native check report base/complete-object adjustment differs.");
   IntPtr type=NativeMemory.Ptr(col,12);ImageRange(type,8+ReporterType.Length+1);
   Need(NativeMemory.Ascii(NativeMemory.Add(type,8),ReporterType.Length+1)==ReporterType,"Native check report owner RTTI differs.");
   return table;
  }

  internal NativeProjectCheckReport(NativeEngine engine,IntPtr root,IntPtr main,IntPtr worker,IntPtr pipeline){
   this.engine=engine;this.root=root;
   thread=NativeMemory.GetCurrentThreadId();
   Need(thread==EngineEntry.ExpectedUiThreadId&&IntPtr.Size==4,"Native check report is outside the captured x86 editor UI thread.");
   Need(Called(worker,0xe5)==Body(pipeline),"Root85 no longer leads to the selected whole-module report pipeline.");
   Expect(pipeline,0x151,"6a018d4d9c","enabled report generator construction");
   IntPtr constructor=Called(pipeline,0x156), finish=Called(pipeline,0x2a9);
   Need(Called(pipeline,0x2e1)==finish,"Native check no longer closes the same report on both normal generator paths.");
   Need(Field(constructor,0x58,"8b88","generator root owner")==NativeLayout.Offset("app.root_document"),"Native generator root owner field differs.");
   Expect(constructor,0x66,"894140","generator report receiver");
   Expect(constructor,0x6f,"884244","generator report enable flag");
   IntPtr owner=Called(constructor,0x5e), reset=Called(constructor,0xa7);
   reporterOffset=Field(owner,0x21,"8b88","root's report owner field");
   secondaryOffset=Field(owner,0x4a,"81c2","borrowed report interface");
   windowOffset=SmallField(owner,0x27,"8b51","report HWND field");
   Need(reporterOffset>0&&reporterOffset<1024&&secondaryOffset>0&&secondaryOffset<512&&windowOffset>0&&windowOffset<128
        &&Field(owner,0x38,"8b88","existing report owner")==reporterOffset&&Field(owner,0xa5,"81c2","created report interface")==secondaryOffset,
        "Native check report owner and interface fields disagree.");
   mainWindow=NativeMemory.Ptr(main,windowOffset);
   VerifyWindow(mainWindow);
   Expect(reset,0xa,"0fb64844","reset enable flag");Expect(reset,0x23,"83784000","reset receiver");
   Expect(reset,0x37,"8b4204ffd0","original Reset virtual call");
   Expect(finish,0x3c,"83794000","finish receiver");Expect(finish,0x1fe,"8b4210ffd0","original Finish virtual call");
   IntPtr silence=Called(reset,0x12);
   Need(Called(finish,0x28)==silence,"Native check report Reset and Finish no longer share the suppression field.");
   silentCounter=new IntPtr(Field(silence,4,"833d","silent-layer count"));
   Expect(silence,10,"007e09c745fc01000000eb07c745fc00000000","silent-layer predicate");
   ImageRange(silentCounter,4);
   Need(NativeMemory.I32(silentCounter,0)==0,"The original check is using a silent generator scope.");
   reporter=NativeMemory.Ptr(root,reporterOffset);
   TypeTable(reporter,0);IntPtr interfaceTable=TypeTable(reporter,secondaryOffset);
   IntPtr clear=Body(NativeMemory.Ptr(interfaceTable,4)), summary=Body(NativeMemory.Ptr(interfaceTable,16));
   Need(Field(summary,0x2b,"81e9","report Finish complete object")==secondaryOffset,"Native check report Finish object adjustment differs.");
   int relativeTree=SmallField(clear,0x3f,"83c2","report Reset tree");
   Need(SmallField(summary,0x39,"83c0","report Finish tree")==relativeTree,"Native check report Reset and Finish use different trees.");
   IntPtr recount=Called(summary,0x31);
   reportTreeOffset=Field(recount,0x345,"81c1","reported count tree");
   warningOffset=Field(recount,0x395,"8981","warning count writer");
   errorOffset=Field(recount,0x3b5,"8981","error count writer");
   Need(reportTreeOffset==secondaryOffset+relativeTree
        &&warningOffset==secondaryOffset+SmallField(summary,0x1af,"8b51","summary warning field")
        &&errorOffset==secondaryOffset+SmallField(summary,0x1b6,"8b48","summary error field")
        &&warningOffset==secondaryOffset+SmallField(clear,0xa,"c740","Reset warning field")
        &&errorOffset==secondaryOffset+SmallField(clear,0x14,"c741","Reset error field")
        &&errorOffset!=warningOffset&&warningOffset==Field(recount,0x3ac,"2b82","error minus warnings arithmetic"),
        "Native check report Clear, Count and Finish fields disagree.");
   Expect(clear,0xd,"00000000","Reset warning value");Expect(clear,0x17,"00000000","Reset error value");
   Expect(Called(recount,0x34b),0xa,"8b4004","MSVC report tree count");
   IntPtr countIf=Called(Called(recount,0x38a),0x31), predicate=Called(countIf,0x4b);
   warningResource=checked((uint)Field(predicate,0x52,"68","original warning severity resource"));
   Need(warningResource>0&&warningResource<=UInt16.MaxValue,"Native check report severity resource is outside its original range.");
   IntPtr rowAccessor=Called(Called(Called(countIf,0x38),0xa),0xd);
   treeValueOffset=SmallField(rowAccessor,6,"83c0","native tree node payload");
   IntPtr stringAccessor=Called(Called(Called(predicate,0x4c),0xa),0xd);
   listValueOffset=SmallField(stringAccessor,6,"83c0","native string-list node payload");
   Expect(Called(countIf,0x40),0x14,"83c004","native report row string-list member");
   Need(treeValueOffset==16&&listValueOffset==8,"Native check report node layout differs from the supported MSVC tree/string list.");
  }

  void VerifyWindow(IntPtr window){
   uint process;
   Need(window!=IntPtr.Zero&&GetWindowThreadProcessId(window,out process)==thread&&process==(uint)Process.GetCurrentProcess().Id,"Native check report HWND is not owned by this editor UI thread.");
  }
  static string Cell(IntPtr field,Snapshot snapshot){
   IntPtr data=NativeMemory.Ptr(field,0);
   int length=NativeMemory.I32(data,-12),capacity=NativeMemory.I32(data,-8);
   Need(length>=0&&length<=capacity&&capacity<Int32.MaxValue/2&&length<=MaxTextUnits-snapshot.TextUnits,"Native check report string has an unverified extent.");
   snapshot.TextUnits+=length;
   var raw=NativeMemory.Bytes(data,checked(length*2+2));
   Need(raw[length*2]==0&&raw[length*2+1]==0,"Native check report CString has no terminator.");
   var text=new char[length];for(int i=0;i<length;i++)text[i]=(char)(raw[i*2]|raw[i*2+1]<<8);
   return new string(text);
  }
  sealed class Snapshot {
   internal readonly List<object> Rows=new List<object>();
   internal readonly HashSet<uint> Nodes=new HashSet<uint>();
   internal readonly List<uint> Traversal=new List<uint>();
   internal IntPtr Min,Max;
   internal int TextUnits,Warnings,Errors;
  }
  List<string> Cells(IntPtr nativeList,Snapshot snapshot){
   byte[] list=NativeMemory.Bytes(nativeList,8);IntPtr head=Ptr(list,0);
   int count=BitConverter.ToInt32(list,4);
   Need(count>0&&count<=MaxCells&&snapshot.Nodes.Add(NativeMemory.U(head)),"Native check report row string-list identity or count is unverified.");
   byte[] sentinel=NativeMemory.Bytes(head,8);IntPtr node=Ptr(sentinel,0),previous=head;
   var cells=new List<string>(count);
   for(int i=0;i<count;i++){
    Need(node!=head&&snapshot.Nodes.Add(NativeMemory.U(node)),"Native check report row string-list repeats a node.");
    byte[] links=NativeMemory.Bytes(node,listValueOffset+4);
    Need(Ptr(links,4)==previous,"Native check report row string-list back link differs.");
    snapshot.Traversal.Add(NativeMemory.U(node));
    cells.Add(Cell(NativeMemory.Add(node,listValueOffset),snapshot));
    previous=node;node=Ptr(links,0);
   }
   Need(node==head&&previous==Ptr(sentinel,4),"Native check report row string-list extent differs.");
   return cells;
  }
  void Tree(IntPtr node,IntPtr parent,IntPtr head,int count,int depth,Snapshot snapshot){
   if(node==head)return;
   Need(depth<64&&snapshot.Rows.Count<count&&snapshot.Nodes.Add(NativeMemory.U(node)),"Native check report tree repeats a node or exceeds its original extent.");
   byte[] table=NativeMemory.Bytes(node,treeValueOffset+12);
   Need(table[13]==0&&table[12]<=1&&Ptr(table,4)==parent,"Native check report tree node parent or flags differ.");
   Tree(Ptr(table,0),node,head,count,depth+1,snapshot);
   if(snapshot.Rows.Count==0)snapshot.Min=node;
   snapshot.Max=node;
   snapshot.Traversal.Add(NativeMemory.U(node));
   var cells=Cells(NativeMemory.Add(node,treeValueOffset+4),snapshot);
   snapshot.Rows.Add(new Dictionary<string,object>{{"native_key_raw_uint32",BitConverter.ToUInt32(table,treeValueOffset)},{"native_cells",cells}});
   Tree(Ptr(table,8),node,head,count,depth+1,snapshot);
  }
  Snapshot Capture(){
   Need(NativeMemory.GetCurrentThreadId()==thread&&NativeMemory.I32(silentCounter,0)==0&&NativeMemory.Ptr(root,reporterOffset)==reporter,"The native check report owner, UI thread or silent scope changed.");
   TypeTable(reporter,0);TypeTable(reporter,secondaryOffset);
   IntPtr window=NativeMemory.Ptr(reporter,windowOffset);VerifyWindow(window);
   Need(GetWindow(window,4)==mainWindow,"Native check report HWND owner differs from the original main window.");
   var className=new StringBuilder(32);
   Need(GetClassNameW(window,className,className.Capacity)>0&&className.ToString()=="#32770","Native check reporter no longer owns the original dialog class.");
   IntPtr tree=NativeMemory.Add(reporter,reportTreeOffset);
   byte[] header=NativeMemory.Bytes(tree,8);IntPtr head=Ptr(header,0);int count=BitConverter.ToInt32(header,4);
   int errors=NativeMemory.I32(reporter,errorOffset),warnings=NativeMemory.I32(reporter,warningOffset);
   Need(count>=0&&count<=MaxRows&&errors>=0&&warnings>=0&&(long)errors+warnings==count,"Native check report summary and complete tree count differ.");
   byte[] sentinel=NativeMemory.Bytes(head,16);
   Need(sentinel[13]==1&&sentinel[12]<=1,"Native check report tree sentinel differs.");
   var result=new Snapshot{Min=head,Max=head,Errors=errors,Warnings=warnings};result.Nodes.Add(NativeMemory.U(head));
   Tree(Ptr(sentinel,4),head,head,count,0,result);
   Need(result.Rows.Count==count&&result.Min==Ptr(sentinel,0)&&result.Max==Ptr(sentinel,8),
        "Native check report whole-tree extent differs from the original summary.");
   return result;
  }
  HashSet<string> WarningLabels(){
   var module=engine.ImageBase;
   // The original MCGS string helper can use a different language from the
   // generic Windows fallback. Read exact variants of its RT_STRING ID.
   var type=new IntPtr(6);
   var block=new IntPtr(checked((int)(warningResource/16+1)));
   var languages=new HashSet<ushort>();
   Need(EnumResourceLanguagesW(module,type,block,(image,resourceType,name,language,context)=>{languages.Add(language);return true;},IntPtr.Zero)&&languages.Count>0,
        "The original warning severity string has no readable resource languages.");
   var labels=new HashSet<string>(StringComparer.Ordinal);
   foreach(ushort language in languages){
    IntPtr resource=FindResourceExW(module,type,block,language);
    Need(resource!=IntPtr.Zero,"An enumerated original warning resource could not be found.");
    uint size=SizeofResource(module,resource);
    Need(size>=32&&size<=(UInt16.MaxValue*2+2)*16&&size%2==0,"The original warning string resource has an unexpected extent.");
    IntPtr data=LockResource(LoadResource(module,resource));
    ImageRange(data,(int)size);
    byte[] raw=NativeMemory.Bytes(data,(int)size);
    int offset=0;
    for(uint i=0;i<=warningResource%16;i++){
     Need(offset<=raw.Length-2,"The original warning string resource is truncated.");
     int bytes=BitConverter.ToUInt16(raw,offset)*2;
     offset+=2;
     Need(bytes<=raw.Length-offset,"The original warning string exceeds its resource.");
     if(i==warningResource%16&&bytes>0)labels.Add(Encoding.Unicode.GetString(raw,offset,bytes));
     offset+=bytes;
    }
   }
   return labels;
  }
  static string SeverityLabel(Dictionary<string,object> row){return ((List<string>)row["native_cells"])[0];}
  static void Classify(Snapshot snapshot,HashSet<string> warningLabels){
   string warningLabel=null;
   if(snapshot.Errors>0&&snapshot.Warnings>0){
    var occurrences=new Dictionary<string,int>(StringComparer.Ordinal);
    foreach(Dictionary<string,object> row in snapshot.Rows){
     string label=SeverityLabel(row);int count;occurrences.TryGetValue(label,out count);
     occurrences[label]=count+1;
    }
    foreach(string label in warningLabels){
     int count;
     if(!occurrences.TryGetValue(label,out count)||count!=snapshot.Warnings)continue;
     Need(warningLabel==null,"Native check report mixed severities have multiple original-language matches.");
     warningLabel=label;
    }
    Need(warningLabel!=null,"Native check report mixed severities do not match the original warning resources and counts.");
   }
   foreach(Dictionary<string,object> row in snapshot.Rows)
    row["severity"]=snapshot.Errors==0||warningLabel!=null&&String.Equals(SeverityLabel(row),warningLabel,StringComparison.Ordinal)?"warning":"error";
  }
  internal Dictionary<string,object> ReadCompleted(){
   var first=Capture();var second=Capture();
   Need(first.Errors==second.Errors&&first.Warnings==second.Warnings&&first.Traversal.Count==second.Traversal.Count&&first.Nodes.SetEquals(second.Nodes)
        &&NativeUsableEditPermit.Json(first.Traversal)==NativeUsableEditPermit.Json(second.Traversal)
        &&NativeUsableEditPermit.Json(first.Rows)==NativeUsableEditPermit.Json(second.Rows),"Native check report changed during the same UI-thread readback.");
   Classify(second,second.Errors>0&&second.Warnings>0?WarningLabels():null);
   return new Dictionary<string,object>{{"source","original-Root85-ObjectErrorDlg-completed-report"},{"same_check_operation_verified",true},{"error_count",second.Errors},{"warning_count",second.Warnings},{"all_native_rows",second.Rows}};
  }
 }
}
