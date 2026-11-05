// Same-class trigger context editing. Source candidate; no old trial/session/claim is used.




using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.Globalization;using System.IO;using System.Runtime.InteropServices;using System.Security.Cryptography;using System.Text;using System.Web.Script.Serialization;




namespace McgsInternalBridge {




 internal static class NativeStrategyTriggerContextEditing {




  internal const string Kind="strategy-trigger-context",FlushKind="strategy-trigger-context-flush",AbiProfileSha="c6cf61e9fe94c1c150a2eb30743a7bcf0e7becb7ce6d287c9e4929c63865f2f8";




  internal static readonly string[] Kinds={Kind,FlushKind};




  [UnmanagedFunctionPointer(CallingConvention.Cdecl)]internal delegate IntPtr Factory();




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate void V0(IntPtr p);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate void VI(IntPtr p,int n);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate void VP(IntPtr p,IntPtr q);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate void VIP(IntPtr p,int index,IntPtr q);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate IntPtr PP(IntPtr p,IntPtr q);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int I0(IntPtr p);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate int IP(IntPtr p,IntPtr q);




  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]internal delegate void Open(IntPtr p,int type,IntPtr sql,int options);




  [DllImport("kernel32.dll",ExactSpelling=true,EntryPoint="GetProcAddress")]static extern IntPtr Export(IntPtr module,IntPtr ordinal);




  [DllImport("kernel32.dll",ExactSpelling=true)]static extern IntPtr GlobalLock(IntPtr handle);




  [DllImport("kernel32.dll",ExactSpelling=true)]static extern bool GlobalUnlock(IntPtr handle);




  [DllImport("kernel32.dll",ExactSpelling=true)]static extern UIntPtr GlobalSize(IntPtr handle);




  static Dictionary<string,object>M(object x){return NativePageControlPreparation.Map(x);}static string S(Dictionary<string,object>d,string k){return NativePageControlPreparation.Text(d,k);}static int N(Dictionary<string,object>d,string k){return NativePageControlPreparation.Number(d,k);}static string J(object o){return NativeUsableEditPermit.Json(o);}static void Same(object a,object b,string why){NativePageControlPreparation.Same(a,b,why);}static void Need(bool v,string why){NativeMemory.Require(v,why);}static string Hex(byte[]b){return BitConverter.ToString(b).Replace("-","").ToLowerInvariant();}static string Hash(byte[]b){using(var h=SHA256.Create())return Hex(h.ComputeHash(b));}




  static List<object>L(object value){Need(value is IEnumerable&&!(value is string)&&!(value is IDictionary),"Trigger context words require arrays.");var r=new List<object>();foreach(object x in(IEnumerable)value)r.Add(x);return r;}static uint U(object v){Need(v is int||v is uint||v is long,"Trigger words require exact uint32 integers.");long n=Convert.ToInt64(v);Need(n>=0&&n<=UInt32.MaxValue,"Trigger word exceeds uint32.");return(uint)n;}static string Note(string s){Need(s!=null&&s.Length<=Int32.MaxValue/2-1&&s.IndexOf('\0')<0,"Trigger note is not bounded complete UTF16.");new UnicodeEncoding(false,false,true).GetBytes(s);return s;}




  internal sealed class Api {




   internal readonly NativeEngine Engine;internal readonly NativeContext Context;internal readonly NativeStrategyLifecycleProfile.Api Base;internal readonly string Project;internal readonly Dictionary<string,Dictionary<string,object>> Types=new Dictionary<string,Dictionary<string,object>>();readonly Dictionary<string,Dictionary<string,object>> guards=new Dictionary<string,Dictionary<string,object>>();internal readonly IntPtr Mfc;readonly Dictionary<string,object> calls=new Dictionary<string,object>();




   internal VIP RootSet{get{return Bind<VIP>("RootSetContext");}}   internal VP Copy{get{return Bind<VP>("ContextCopy");}}   internal VP RowWrite{get{return Bind<VP>("ContextSerializeToRow");}}   internal VP RowLoad{get{return Bind<VP>("ContextDeserializeFromRow");}}   internal VI ContextDirty{get{return Bind<VI>("ContextSetDirty");}}   internal VI RootDirty{get{return Base.Read.Existing.Bind<VI>("RootSetModified");}}   internal VP Assign{get{return Base.Read.Existing.Bind<VP>("CStringAssignCopy");}}   internal V0 RecordEdit{get{return Bind<V0>("RecordEdit");}}   internal V0 RecordUpdate{get{return Bind<V0>("RecordUpdate");}}   internal IP FieldNull{get{return Bind<IP>("TriggerFieldIsNull");}}   internal PP RecordCtor{get{return Base.Bind<PP>("TriggerRecordCtor");}}   internal Open RecordOpen{get{return Base.Bind<Open>("RecordOpen");}}   internal IP RecordFind{get{return Base.Bind<IP>("RecordFind");}}   internal V0 RecordClose{get{return Base.Bind<V0>("RecordClose");}}   internal V0 RecordDtor{get{return Base.Bind<V0>("TriggerRecordDtor");}}   internal I0 RecordBof{get{return Extra<I0>("RecordBof",0x65570);}}   internal I0 RecordEof{get{return Extra<I0>("RecordEof",0x655B0);}}   internal V0 RecordFirst{get{return Extra<V0>("RecordFirst",0x656D0);}}   internal V0 RecordNext{get{return Extra<V0>("RecordNext",0x656A0);}}




   internal Api(NativeEngine e,NativeContext c,string project){Engine=e;Context=c;Project=Path.GetFullPath(project);Base=new NativeStrategyLifecycleProfile.Api(e,c);Current();string path=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"strategy-prep","trigger-context-prep","strategy-trigger-context-abi-profile.v3.json");Need(File.Exists(path)&&NativeLazyFunctionProfile.SourceHash(path)==AbiProfileSha,"Trigger context profile differs.");var p=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue}.Deserialize<Dictionary<string,object>>(NativeLazyFunctionProfile.ReadText(path));Need(NativeBinaryIdentity.Observe(S(p,"image_sha256"),e.ImageSha256,"NativeStrategyTriggerContextEditing:121:editor")&&NativeLazyFunctionProfile.SourceHash(Path.Combine(NativeOperations.TaskRoot,"extensions","strategy","strategy-extension-write-guard.json"))==S(p,"base_reader_sha256"),"Trigger context base/image differs.");foreach(ProcessModule mod in Process.GetCurrentProcess().Modules)if(NativeLazyFunctionProfile.SameModule(mod,Path.GetFullPath(@"C:\unbound-install-root\Program\mfc110u.dll"))){Need(Mfc==IntPtr.Zero||Mfc==mod.BaseAddress,"Trigger MFC owner ambiguous.");Mfc=mod.BaseAddress;}Need(Mfc!=IntPtr.Zero&&NativeBinaryIdentity.Observe(S(p,"mfc_sha256"),NativeMemory.Hash(@"C:\unbound-install-root\Program\mfc110u.dll"),"NativeStrategyTriggerContextEditing:121:module"),"Trigger original MFC is not already exact/loaded.");foreach(object x in(IEnumerable)p["guards"]){var f=M(x);guards.Add(S(f,"name"),f);}foreach(object x in(IEnumerable)p["types"]){var t=M(x);Types.Add(S(t,"rtti"),t);}}




   internal void Current(){Base.Current();Need(Project.Equals(NativeUsableEditPermit.Fixture,StringComparison.OrdinalIgnoreCase),"Trigger context project differs.");}




   internal void Check(string name){Current();var f=guards[name];NativeLazyFunctionProfile.CheckRow(f,"trigger method");bool isMfc=S(f,"module")=="mfc110u.dll";IntPtr b=isMfc?Mfc:Engine.ImageBase;string h=S(f,"bytes");byte[] raw=new byte[h.Length/2];for(int i=0;i<raw.Length;i++)raw[i]=Byte.Parse(h.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeCodeRelocation.RebaseDeltaInPlace(raw,(IEnumerable)f["reloc_offsets"],unchecked((uint)(NativeMemory.U(b)-(isMfc?0x10000000U:0x400000U))));Need(Hex(raw)==Hex(NativeMemory.Bytes(NativeMemory.Add(b,N(f,"rva")),raw.Length)),"Trigger context code differs: "+name);}




   T Bind<T>(string name)where T:class{Check(name);var f=guards[name];NativeLazyFunctionProfile.CheckRow(f,"trigger method");IntPtr at=NativeMemory.Add(S(f,"module")=="mfc110u.dll"?Mfc:Engine.ImageBase,N(f,"rva"));return Marshal.GetDelegateForFunctionPointer(at,typeof(T))as T;}




   T Extra<T>(string name,int rva)where T:class{Need(guards.ContainsKey(name),"Trigger cursor helper requires its own code guard: "+name);Need(N(guards[name],"rva")==rva,"Trigger cursor method RVA differs.");return Bind<T>(name);}




   internal void ValidateType(Dictionary<string,object> t){NativeLazyFunctionProfile.CheckIdentity(t,"runtime_class_rva","vtable_rva","col_rva","type_rva");IntPtr rt=Engine.Address(N(t,"runtime_class_rva")),vt=Engine.Address(N(t,"vtable_rva"));Need(NativeMemory.I32(rt,4)==N(t,"size")&&NativeMemory.I32(rt,8)==0&&NativeMemory.Ascii(NativeMemory.Ptr(rt,0),64)=="CTrigger"+S(t,"name"),"Trigger runtime class layout differs.");IntPtr col=Engine.Address(N(t,"col_rva")),td=Engine.Address(N(t,"type_rva"));Need(NativeMemory.Ptr(vt,-4)==col&&NativeMemory.I32(col,4)==0&&NativeMemory.Ptr(col,12)==td&&NativeMemory.Ascii(NativeMemory.Add(td,8),128)==S(t,"rtti"),"Trigger complete COL/offset/type differs.");}
   internal void ValidateFactory(Dictionary<string,object> t){ValidateType(t);NativeLazyFunctionProfile.CheckIdentity(t,"factory_entry_rva");Need(NativeMemory.Ptr(Engine.Address(N(t,"runtime_class_rva")),12)==Engine.Address(N(t,"factory_entry_rva")),"Trigger exact native runtime factory differs.");}




   internal Dictionary<string,object> Type(IntPtr p){Current();string rtti=Base.Read.MfcType(p);Need(Types.ContainsKey(rtti),"Uncovered trigger subtype.");var t=Types[rtti];ValidateType(t);Need(NativeMemory.Ptr(p,0)==Engine.Address(N(t,"vtable_rva"))&&NativeMemory.I32(p,12)==N(t,"native_type"),"Trigger class/type differs.");return t;}




   internal Factory Maker(Dictionary<string,object> t){ValidateFactory(t);Check(S(t,"name")+"Factory");return Engine.Bind<Factory>(Engine.Address(N(t,"factory_rva")));}internal VI Destroyer(Dictionary<string,object> t){Check(S(t,"name")+"DeletingDtor");return Engine.Bind<VI>(Engine.Address(N(t,"deleting_dtor_rva")));}




   internal Dictionary<string,object> Fields(IntPtr p){var t=Type(p);var b=new List<object>();foreach(int off in new[]{0x14,0x18,0x1C})b.Add(unchecked((uint)NativeMemory.I32(p,off)));var loop=new List<object>();if(N(t,"native_type")==2)for(int off=0x24;off<0x48;off+=4)loop.Add(unchecked((uint)NativeMemory.I32(p,off)));return new Dictionary<string,object>{{"native_record_id",NativeMemory.I32(p,4)},{"strategy_id",NativeMemory.I32(p,8)},{"native_type",NativeMemory.I32(p,12)},{"rtti",S(t,"rtti")},{"note",NativeUsableEditPermit.ReadCurrentCString(NativeMemory.Add(p,0x10),131072)},{"serialized_base_words_uint32",b},{"serialized_loop_words_uint32",loop}};}




   internal List<object> Catalog(){var blocks=Base.Blocks();var array=Base.Array(NativeMemory.Add(Base.Root,0x22C),"RootBlocks");var contexts=Base.Array(NativeMemory.Add(Base.Root,0x240),"RootTriggers");Need(array.Count==contexts.Count,"Strategy/context ownership counts differ.");var rows=new List<object>();for(int i=0;i<array.Count;i++){IntPtr block=array[i],p=NativeMemory.Ptr(block,0x10);Need(contexts.Contains(p),"Block context is outside root ownership.");int id=NativeStrategyProfile.ReadId(Base.Read.Existing,NativeMemory.Add(block,4));Need(blocks.ContainsKey(id)&&blocks[id]==NativeMemory.Add(block,4)&&NativeMemory.I32(p,8)==id,"Trigger/block native identity differs.");var f=Fields(p);rows.Add(new Dictionary<string,object>{{"root_block_index",i},{"block_id",id},{"block_name",NativeStrategyProfile.ReadName(Base.Read.Existing,NativeMemory.Add(block,4))},{"block_complete",NativeMemory.Hex(block)},{"context",NativeMemory.Hex(p)},{"fields",f},{"dirty_byte",(int)Marshal.ReadByte(p,0x20)},{"complete_raw_hex",Hex(NativeMemory.Bytes(p,N(Type(p),"size")))}});}return rows;}




   internal Dictionary<string,object> Find(List<object> rows,int id,string name){Dictionary<string,object> found=null;foreach(object x in rows){var r=M(x);if(N(r,"block_id")==id){Need(found==null&&S(r,"block_name")==name,"Trigger target id/name is not unique/exact.");found=r;}}Need(found!=null,"Trigger target absent.");return found;}




  }




  sealed class Cursor:IDisposable {




   readonly Api api;internal readonly IntPtr Storage;bool ctorReturned,openReturned,uncertain,disposed;




   internal Cursor(Api a){api=a;Storage=Marshal.AllocHGlobal(0xBC);try{for(int i=0;i<0xBC;i++)Marshal.WriteByte(Storage,i,0);uncertain=true;Need(api.RecordCtor(Storage,NativeMemory.Add(api.Base.Root,0x25C))==Storage,"Trigger record constructor returned another object.");ctorReturned=true;api.Base.Read.Table(Storage,"TriggerRecord");uncertain=false;uncertain=true;api.RecordOpen(Storage,-1,IntPtr.Zero,0);openReturned=true;uncertain=false;}catch{Dispose();throw;}}




   internal void Call(Action f){Need(!uncertain&&!disposed,"Trigger cursor lifecycle is unknown/closed.");uncertain=true;f();uncertain=false;}




   internal void Locate(int id){IntPtr f=Marshal.StringToHGlobalUni("iID = "+id.ToString(CultureInfo.InvariantCulture));try{Call(delegate{Need(api.RecordFind(Storage,f)!=0&&NativeMemory.I32(Storage,0x98)==id,"Exact existing Trigger record not found.");});}finally{Marshal.FreeHGlobal(f);}}




   internal Dictionary<string,object> Value(){api.Base.Read.Table(Storage,"TriggerRecord");IntPtr binary=NativeMemory.Add(Storage,0xA4);Need(NativeMemory.Ptr(binary,0)==NativeMemory.Add(api.Mfc,0x375F8),"Trigger cursor BLOB is not original CLongBinary.");api.Check("TriggerFieldIsNull");int n=NativeMemory.I32(binary,8);Need(n>=0&&n<=4*1024*1024,"Trigger BLOB bound exceeded.");byte[] bytes=new byte[0];if(n>0){IntPtr h=NativeMemory.Ptr(binary,4);Need(h!=IntPtr.Zero&&GlobalSize(h).ToUInt64()>=(uint)n,"Trigger BLOB handle/size differs.");IntPtr p=GlobalLock(h);Need(p!=IntPtr.Zero,"Cannot lock own Trigger cursor BLOB.");try{bytes=NativeChunkedRawMemory.Read(p,n);}finally{GlobalUnlock(h);}}int n1=api.FieldNull(Storage,NativeMemory.Add(Storage,0xB4)),n2=api.FieldNull(Storage,NativeMemory.Add(Storage,0xB8));Need((n1==0||n1==1)&&(n2==0||n2==1),"Trigger SQL-null flag differs.");return new Dictionary<string,object>{{"id",NativeMemory.I32(Storage,0x98)},{"strategy_id",NativeMemory.I32(Storage,0x9C)},{"type",NativeMemory.I32(Storage,0xA0)},{"binary_bytes",n},{"binary_sha256",Hash(bytes)},{"note",NativeUsableEditPermit.ReadCurrentCString(NativeMemory.Add(Storage,0xB0),131072)},{"temp1_native",NativeMemory.I32(Storage,0xB4)},{"temp2_native",NativeMemory.I32(Storage,0xB8)},{"temp1_sql_null",n1==1},{"temp2_sql_null",n2==1}};}




   internal List<object> All(){var result=new List<object>();Call(delegate{Need(api.RecordBof(Storage)==0,"Trigger table is unavailable/empty.");api.RecordFirst(Storage);var seen=new HashSet<int>();while(api.RecordEof(Storage)==0){Need(seen.Add(NativeMemory.I32(Storage,0x98)),"Trigger row bound/id uniqueness differs.");result.Add(Value());api.RecordNext(Storage);}});result.Sort(delegate(object x,object y){return N(M(x),"id").CompareTo(N(M(y),"id"));});return result;}




   public void Dispose(){if(disposed)return;disposed=true;if(uncertain)return;try{if(openReturned){uncertain=true;api.RecordClose(Storage);openReturned=false;uncertain=false;}if(ctorReturned){uncertain=true;api.RecordDtor(Storage);ctorReturned=false;uncertain=false;}}finally{if(!uncertain)Marshal.FreeHGlobal(Storage);}}




  }




  static List<object> Db(Api api){using(var c=new Cursor(api))return c.All();}static Dictionary<string,object> Row(List<object> rows,int id){foreach(object x in rows){var r=M(x);if(N(r,"id")==id)return r;}throw new InvalidOperationException("Trigger record absent from full cursor snapshot.");}




  static Dictionary<string,object> Read(Api api,Dictionary<string,object> action){Need(Array.IndexOf(Kinds,S(action,"kind"))>=0,"Trigger context kind differs.");var target=M(action["target"]);int id=N(target,"block_id");var catalog=api.Catalog();var item=api.Find(catalog,id,S(target,"block_name"));var open=NativeStrategyWorkingModelEditing.OpenBlockIds(api.Engine,api.Context,api.Project);var ids=new List<int>(open);ids.Sort();var db=Db(api);var row=Row(db,N(M(item["fields"]),"native_record_id"));Need(N(row,"strategy_id")==id&&N(row,"type")==N(M(item["fields"]),"native_type"),"Native trigger row identity/type differs.");return new Dictionary<string,object>{{"kind",S(action,"kind")},{"abi_profile_sha256",AbiProfileSha},{"target",item},{"context_catalog",catalog},{"trigger_native_rows",db},{"open_strategy_ids",ids},{"same_id_working_document_open",open.Contains(id)},{"strategy_sources",NativeStrategyWorkingModelEditing.InspectAll(api.Engine,api.Context,api.Project)},{"complete_context_serialized_fields_captured",true},{"base_word_business_semantics_verified",false},{"loop_schedule_all_ui_semantics_verified",false},{"write_attempted",false}};}




  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return Read(new Api(e,c,project),action);}internal static Prepared Prepare(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new Prepared(new Api(e,c,project),action);}




  internal sealed class Prepared:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {




   readonly Api api;readonly string kind;readonly Dictionary<string,object> action,before,wanted,type;readonly IntPtr canonical;readonly int id,index,recordId;readonly Factory factory;readonly VI destroy;readonly NativeStrategyProfile.CString note;readonly List<object> baseWords,loopWords;string disk,pendingOwnStorage;IntPtr owned,verification;bool failed,applied,disposed;string phase;bool cloneReturned,rootSetReturned,rowUpdateReturned;




   internal Prepared(Api a,Dictionary<string,object> request){api=a;action=request;kind=S(action,"kind");Need(S(action,"abi_profile_sha256")==AbiProfileSha,"Trigger context action ABI differs.");disk=NativeMemory.Hash(NativeUsableEditPermit.Fixture);before=Read(api,action);NativePageControlPreparation.Before(action,before);Need(Object.Equals(before["same_id_working_document_open"],false),"Close/finish the original working strategy document before canonical trigger editing; do not overwrite its pending context.");var target=M(before["target"]);id=N(target,"block_id");index=N(target,"root_block_index");wanted=new Dictionary<string,object>(M(target["fields"]));recordId=N(wanted,"native_record_id");canonical=NativeMemory.Ptr(NativeMemory.Add(api.Base.Blocks()[id],-4),0x10);type=api.Type(canonical);factory=api.Maker(type);destroy=api.Destroyer(type);var after=M(action["after"]);if(kind==FlushKind){Need(after.Count==0&&N(target,"dirty_byte")==1,"Deferred trigger flush requires an exact already-dirty preimage and empty after.");baseWords=L(wanted["serialized_base_words_uint32"]);loopWords=L(wanted["serialized_loop_words_uint32"]);}else{Need(after.Count==3&&after.ContainsKey("note")&&after.ContainsKey("serialized_base_words_uint32")&&after.ContainsKey("serialized_loop_words_uint32"),"Trigger after requires exact note/all three base words/all loop tail words.");baseWords=L(after["serialized_base_words_uint32"]);loopWords=L(after["serialized_loop_words_uint32"]);wanted["note"]=Note(S(after,"note"));wanted["serialized_base_words_uint32"]=baseWords;wanted["serialized_loop_words_uint32"]=loopWords;Need(J(wanted)!=J(target["fields"]),"Trigger context action has no change.");}Need(baseWords.Count==3&&loopWords.Count==(N(type,"native_type")==2?9:0),"Trigger complete serialized word count differs.");foreach(object x in baseWords)U(x);foreach(object x in loopWords)U(x);if(loopWords.Count>0){uint mode=U(loopWords[0]),selector=U(loopWords[3]);Need(mode<=1&&(mode==0?selector<=65535:selector<=4),"Loop desired state is outside the original exact STORE/LOAD codec range; no normalization is inferred.");}note=new NativeStrategyProfile.CString(api.Base.Read.Existing,S(wanted,"note"));try{Need(NativeUsableEditPermit.ReadCurrentCString(note.Storage,131072)==S(wanted,"note"),"Owned trigger note differs.");ValidateBefore();}catch{note.Dispose();throw;}}




   void Current(){Need(!disposed&&!failed,"Trigger context preparation failed/disposed.");api.Current();Need(NativeMemory.Hash(NativeUsableEditPermit.Fixture)==(pendingOwnStorage??disk),"Trigger context storage changed outside its explicit own persistence boundary.");Need(!NativeStrategyWorkingModelEditing.OpenBlockIds(api.Engine,api.Context,api.Project).Contains(id),"A same-id native working document appeared; stop before canonical context mutation.");Need(NativeMemory.Ptr(NativeMemory.Add(api.Base.Blocks()[id],-4),0x10)==canonical,"Canonical context owner changed.");api.Type(canonical);}




   public void ValidateBefore(){Current();Need(!applied,"Trigger context was already applied.");Same(before,Read(api,action),"Complete trigger/DAO/source/working-view preimage changed.");}




   public void ValidatePersistence(NativeUsableEditPermit.Plan p){if(p.Commit)p.RequireRelatedStrategyPersistence(action,id);}




   void Step(string method){Current();api.Check(method);phase=method;NativeOperationTrace.BeforeMutation("usable-strategy-trigger-"+method);}




   void PreserveOtherContexts(){var now=api.Catalog();var previous=L(before["context_catalog"]);Need(now.Count==previous.Count,"Trigger context ownership count changed.");for(int i=0;i<now.Count;i++){var r=M(now[i]);var old=M(previous[i]);if(N(r,"block_id")!=id)Same(old,r,"Another complete trigger context changed.");else{Need(S(r,"context")==S(old,"context")&&S(r,"block_complete")==S(old,"block_complete")&&N(r,"root_block_index")==index&&S(r,"block_name")==S(old,"block_name"),"Target trigger ownership changed.");Same(wanted,r["fields"],"Original trigger copy did not preserve exact intended full serialized fields.");string raw=S(r,"complete_raw_hex"),was=S(old,"complete_raw_hex");for(int off=0;off<raw.Length/2;off++)if(!(off>=0x10&&off<0x14)&&off!=0x20&&!(off>=0x14&&off<0x20)&&!(loopWords.Count>0&&off>=0x24&&off<0x48))Need(raw.Substring(off*2,2)==was.Substring(off*2,2),"Trigger copy changed an unplanned complete/padding byte.");}}Same(before["strategy_sources"],NativeStrategyWorkingModelEditing.InspectAll(api.Engine,api.Context,api.Project),"Trigger edit changed canonical strategy source/row/condition catalog.");}




   void ConfigurePrivate(){api.Assign(NativeMemory.Add(owned,0x10),note.Storage);for(int i=0;i<3;i++)Marshal.WriteInt32(owned,0x14+checked(i*4),unchecked((int)U(baseWords[i])));for(int i=0;i<loopWords.Count;i++)Marshal.WriteInt32(owned,0x24+checked(i*4),unchecked((int)U(loopWords[i])));if(loopWords.Count>0&&U(loopWords[0])==0)Marshal.WriteInt32(owned,0x30,unchecked((int)U(loopWords[3])-1));}




   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);try{if(kind==FlushKind){applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",kind},{"edit_replayed",false},{"apply_project_mutator_calls",0}};}lease.RequireApplying(action);NativeOperationTrace.BeforeMutation("usable-strategy-trigger-root-dirty");api.RootDirty(api.Base.Root,1);Marshal.WriteInt32(api.Base.Root,0x114,0);Step(S(type,"name")+"Factory");owned=factory();Need(owned!=IntPtr.Zero&&owned!=canonical&&!api.Base.Array(NativeMemory.Add(api.Base.Root,0x240),"RootTriggers").Contains(owned),"Private trigger factory aliased canonical/root ownership.");api.Type(owned);Step("ContextCopy");api.Copy(owned,canonical);cloneReturned=true;Need(N(M(api.Fields(owned)),"native_record_id")==recordId&&NativeMemory.I32(owned,8)==id&&Marshal.ReadByte(canonical,0x20)==1,"Original owned clone identity/target dirty projection differs.");lease.RequireApplying(action);ConfigurePrivate();Step("RootSetContext");api.RootSet(api.Base.Root,index,owned);rootSetReturned=true;PreserveOtherContexts();Same(before["trigger_native_rows"],Db(api),"Memory-only original trigger copy changed a stored Trigger row.");Step(S(type,"name")+"DeletingDtor");destroy(owned,1);owned=IntPtr.Zero;applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",kind},{"target_context",NativeMemory.Hex(canonical)},{"fields_after",api.Fields(canonical)},{"original_root_set_context_returned",rootSetReturned},{"private_clone_returned",cloneReturned},{"original_copy_source_dirty_side_effect_expected",true},{"canonical_fields_written_raw",false},{"stored_trigger_rows_unchanged",true},{"pending_explicit_trigger_row_flush",true},{"actual_unified_acceptance_pending",true}};}catch{failed=true;NativeOperationTrace.SetPhase("usable-strategy-trigger-failed-"+phase+"-owned-"+NativeMemory.Hex(owned));throw;}}




   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){Current();Need(applied,"Trigger Apply must complete before Flush.");lease.BeginFlush(action);try{lease.RequireRelatedStrategyPersistence(action,id);PreserveOtherContexts();Same(before["trigger_native_rows"],Db(api),"Stored Trigger preimage changed before exact row Edit.");Step(S(type,"name")+"Factory");owned=factory();Need(owned!=IntPtr.Zero&&owned!=canonical&&!api.Base.Array(NativeMemory.Add(api.Base.Root,0x240),"RootTriggers").Contains(owned),"Private trigger serialization source aliased root ownership.");api.Type(owned);Step("ContextCopy");api.Copy(owned,canonical);ConfigurePrivate();using(var cursor=new Cursor(api)){cursor.Locate(recordId);Same(Row(L(before["trigger_native_rows"]),recordId),cursor.Value(),"Exact stored Trigger row changed before Edit.");Step("RecordEdit");cursor.Call(delegate{api.RecordEdit(cursor.Storage);});Step("ContextSerializeToRow");cursor.Call(delegate{api.RowWrite(owned,cursor.Storage);});Step("RecordUpdate");cursor.Call(delegate{api.RecordUpdate(cursor.Storage);});rowUpdateReturned=true;}pendingOwnStorage=NativeMemory.Hash(NativeUsableEditPermit.Fixture);var afterRows=Db(api);var prior=L(before["trigger_native_rows"]);Need(afterRows.Count==prior.Count,"Trigger Update changed stored row count.");foreach(object x in prior){var old=M(x);var now=Row(afterRows,N(old,"id"));if(N(old,"id")!=recordId)Same(old,now,"Trigger Update changed another stored row/BLOB.");else{Need(N(now,"id")==recordId&&N(now,"strategy_id")==id&&N(now,"type")==N(type,"native_type")&&S(now,"note")==S(wanted,"note"),"Stored Trigger identity/note differs.");foreach(string k in new[]{"temp1_native","temp2_native","temp1_sql_null","temp2_sql_null"})Same(old[k],now[k],"Trigger Update changed an unrelated nullable temp field.");}}Step(S(type,"name")+"Factory");verification=factory();Need(verification!=IntPtr.Zero&&verification!=canonical&&verification!=owned&&!api.Base.Array(NativeMemory.Add(api.Base.Root,0x240),"RootTriggers").Contains(verification),"Fresh stored context verifier aliased root ownership.");using(var cursor=new Cursor(api)){cursor.Locate(recordId);Step("ContextDeserializeFromRow");cursor.Call(delegate{api.RowLoad(verification,cursor.Storage);});}Same(wanted,api.Fields(verification),"Fresh original Trigger-row deserialization did not recover complete intended context.");Step(S(type,"name")+"DeletingDtor");destroy(verification,1);verification=IntPtr.Zero;Step(S(type,"name")+"DeletingDtor");destroy(owned,1);owned=IntPtr.Zero;Step("ContextSetDirty");api.ContextDirty(canonical,0);Need(Marshal.ReadByte(canonical,0x20)==0,"Original context dirty clear did not complete; refuse Flush completion to prevent another RootSave STORE.");PreserveOtherContexts();Need(pendingOwnStorage!=null&&NativeMemory.Hash(NativeUsableEditPermit.Fixture)==pendingOwnStorage,"Trigger storage changed during own postimage verification.");disk=pendingOwnStorage;pendingOwnStorage=null;lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"original_existing_trigger_row_update_returned",rowUpdateReturned},{"actual_context_dirty_byte_after_flush",(int)Marshal.ReadByte(canonical,0x20)},{"trigger_rows_after",afterRows},{"fresh_original_row_deserialization_exact",true},{"owned_storage_serialization_codec_inverse",true},{"own_persistence_boundary","RecordEdit -> ContextSerializeToRow -> RecordUpdate -> fresh full row/other rows/decoded context verification"},{"own_persistence_storage_sha256",disk},{"root_save_called",false},{"actual_unified_acceptance_pending",true}};}catch{failed=true;NativeOperationTrace.SetPhase("usable-strategy-trigger-flush-failed-"+phase+"-owned-verifier-"+NativeMemory.Hex(verification));throw;}}




   public void Dispose(){if(disposed)return;disposed=true;if(note!=null)note.Dispose();/* Native owned objects are destroyed on the proved normal path only; uncertain ownership is retained for diagnosis. */}




  }




 }




}




