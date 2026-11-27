// Window document settings: bounded original-dialog field adaptation, original dirty/save/refresh.
// Event values are preserved and exposed here; no event setter/serializer is guessed.
using System;using System.Collections;using System.Collections.Generic;using System.Diagnostics;using System.Globalization;using System.IO;using System.Runtime.InteropServices;using System.Text;using System.Text.RegularExpressions;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeReferencedPageEditing {
  internal static Dictionary<string,object> PagePropertiesMainRead(Api api,out IntPtr manager,out IntPtr doc){return MainSnapshot(api,out manager,out doc);}
  internal static object PagePropertiesMainValues(object value){return Semantic(value);}
  internal static List<object> PagePropertiesButtons(Api api,IntPtr doc){return Buttons(api,doc);}
 }
 internal static class NativePageDocumentProperties {
  internal const string Kind="page-document-properties",AbiProfileSha="d383ce0d2595b4d08efc6526d1f940caca5aadb7fc405020af247f3d38313965";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VI(IntPtr self,int value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VII(IntPtr self,int mask,int value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void VPP(IntPtr self,IntPtr first,IntPtr second);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void V0(IntPtr self);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void BeforeModify(IntPtr self,IntPtr view,int capture,int dirty);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate IntPtr PP(IntPtr self,IntPtr value);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate int Save(IntPtr self,IntPtr database);
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)][return:MarshalAs(UnmanagedType.I1)]delegate bool GeneratePage(IntPtr self);
  static Dictionary<string,object>M(object v){return NativePageControlPreparation.Map(v);}static string S(Dictionary<string,object>d,string k){return NativePageControlPreparation.Text(d,k);}static int N(Dictionary<string,object>d,string k){return NativePageControlPreparation.Number(d,k);}static string C(IntPtr p,int n){return NativeUsableEditPermit.ReadCurrentCString(p,n);}static void Same(object a,object b,string m){NativePageControlPreparation.Same(a,b,m);}
  static uint Bits(object value){NativeMemory.Require(value is int||value is long||value is uint,"Page property requires an integer native DWORD.");long n=Convert.ToInt64(value,CultureInfo.InvariantCulture);NativeMemory.Require(n>=Int32.MinValue&&n<=UInt32.MaxValue,"Page property DWORD is outside its original width.");return unchecked((uint)n);}
  static string Text(object value,int max){NativeMemory.Require(value is string,"Page document text requires a string.");string text=(string)value;NativeMemory.Require(text.Length<=max&&text.IndexOf('\0')<0,"Page document text bound/NUL differs.");new UnicodeEncoding(false,false,true).GetBytes(text);return text;}
  static string Hash(byte[] bytes){using(var h=System.Security.Cryptography.SHA256.Create())return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
  static string Bytes(IntPtr p,int n){return n==0?"":BitConverter.ToString(NativeChunkedRawMemory.Read(p,n)).Replace("-","").ToLowerInvariant();}
  internal sealed class Api {
   internal readonly NativePageControlAbi Pages;internal readonly NativeReferencedPageEditing.Api Refs;internal readonly NativeEngine Engine;internal readonly NativeContext Context;internal readonly Dictionary<string,object> Profile;
   readonly Dictionary<string,IntPtr> addresses=new Dictionary<string,IntPtr>();readonly Dictionary<string,Dictionary<string,object>> guards=new Dictionary<string,Dictionary<string,object>>();readonly IntPtr mfc;
   internal Api(NativeEngine e,NativeContext c,string project){Engine=e;Context=c;Pages=new NativePageControlAbi(e,c,project);Refs=new NativeReferencedPageEditing.Api(e,c,project);string path=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"page-control-prep","page-document-properties-abi-profile.v2.json");NativeMemory.Require(File.Exists(path)&&(File.GetAttributes(path)&(FileAttributes.Directory|FileAttributes.ReparsePoint))==0&&NativeLazyFunctionProfile.SourceHash(path)==AbiProfileSha,"Page document ABI profile differs.");Profile=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue}.Deserialize<Dictionary<string,object>>(NativeLazyFunctionProfile.ReadText(path));NativeMemory.Require(NativeBinaryIdentity.Observe(S(Profile,"binary_sha256"),e.ImageSha256,"NativePageDocumentProperties.v3:26:editor"),"Page document editor SHA differs.");foreach(object v in(IEnumerable)Profile["functions"]){var f=M(v);string key=S(f,"name");guards.Add(key,f);}var mf=M(Profile["mfc"]);string mp=Path.GetFullPath(S(mf,"path"));foreach(ProcessModule module in Process.GetCurrentProcess().Modules)if(NativeLazyFunctionProfile.SameModule(module,mp)){NativeMemory.Require(mfc==IntPtr.Zero||mfc==module.BaseAddress,"Page event array MFC module is ambiguous.");mfc=module.BaseAddress;}NativeMemory.Require(mfc!=IntPtr.Zero&&NativeBinaryIdentity.Observe(S(mf,"sha256"),NativeMemory.Hash(mp),"NativePageDocumentProperties.v3:26:module"),"Page event MFC array owner differs.");}
   internal void Check(string key){Pages.Current();var f=guards[key];NativeLazyFunctionProfile.CheckRow(f,"function");addresses[key]=Engine.Address(N(f,"rva"));string h=S(f,"bytes");byte[] b=new byte[h.Length/2];for(int i=0;i<b.Length;i++)b[i]=Byte.Parse(h.Substring(2*i,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeCodeRelocation.RebaseDeltaInPlace(b,(IEnumerable)f["reloc_offsets"],unchecked((uint)(NativeMemory.U(Engine.ImageBase)-0x400000U)));NativeMemory.Require(BitConverter.ToString(b)==BitConverter.ToString(NativeMemory.Bytes(addresses[key],b.Length)),"Page document native code differs: "+key);}
   internal T Bind<T>(string key)where T:class{Check(key);return Engine.Bind<T>(addresses[key]);}
   internal void Table(IntPtr p,string key){var t=M(M(Profile["tables"])[key]);NativeLazyFunctionProfile.CheckIdentity(t,"rva","col_rva","type_rva");IntPtr vt=Engine.Address(N(t,"rva")),col=Engine.Address(N(t,"col_rva"));NativeMemory.Require(p!=IntPtr.Zero&&NativeMemory.Ptr(p,0)==vt&&NativeMemory.Ptr(vt,-4)==col&&NativeMemory.I32(col,4)==N(t,"complete_offset")&&NativeMemory.Ptr(col,12)==Engine.Address(N(t,"type_rva"))&&NativeMemory.Ascii(NativeMemory.Add(NativeMemory.Ptr(col,12),8),256)==S(t,"rtti"),"Page document/event RTTI differs: "+key);int i=0;foreach(object slot in(IEnumerable)t["slots"]){NativeMemory.Require(NativeMemory.Ptr(vt,checked(i*4))==(slot==null?IntPtr.Zero:Engine.Address(NativeEngine.Number(slot))),"Page event virtual slot differs: "+key+"/"+i);i++;}}
   internal void MfcArray(IntPtr p,string key){var t=M(M(Profile["mfc"])[key]);IntPtr vt=NativeMemory.Add(mfc,N(t,"rva")),col=NativeMemory.Add(mfc,N(t,"col_rva"));NativeMemory.Require(NativeMemory.Ptr(p,0)==vt&&NativeMemory.Ptr(vt,-4)==col&&NativeMemory.I32(col,4)==N(t,"complete_offset")&&NativeMemory.Ptr(col,12)==NativeMemory.Add(mfc,N(t,"type_rva"))&&NativeMemory.Ascii(NativeMemory.Add(NativeMemory.Ptr(col,12),8),256)==S(t,"rtti"),"Page event MFC array type differs: "+key);}
  }
  static void Readable(IntPtr pointer,int length){for(int offset=0;offset<length;){int n=Math.Min(1024*1024,length-offset);NativeMemory.Readable(NativeMemory.Add(pointer,offset),n);offset=checked(offset+n);}}
  static Tuple<IntPtr,int> Header(IntPtr p,int elementSize){IntPtr b=NativeMemory.Ptr(p,4);int n=NativeMemory.I32(p,8),cap=NativeMemory.I32(p,12);NativeMemory.Require(n>=0&&cap>=n&&(n==0||b!=IntPtr.Zero)&&elementSize>0&&(long)n*elementSize<=Int32.MaxValue,"Page event array header differs.");if(n>0)Readable(b,checked(n*elementSize));return Tuple.Create(b,n);}
  static object IntArray(NativeEngine e,IntPtr p){NativeMemory.Require(NativeMemory.Ptr(p,0)==e.Address(0xCEAFA8),"Page event integer array type differs.");var h=Header(p,4);var values=new List<object>();for(int i=0;i<h.Item2;i++)values.Add(unchecked((uint)NativeMemory.I32(h.Item1,4*i)));return values;}
  static object StringArray(Api a,IntPtr p){a.MfcArray(p,"StringArray");var h=Header(p,4);var values=new List<object>();for(int i=0;i<h.Item2;i++)values.Add(C(NativeMemory.Add(h.Item1,4*i),262144));return values;}
  static object ByteArray(Api a,IntPtr p){a.MfcArray(p,"ByteArray");var h=Header(p,1);return Bytes(h.Item1,h.Item2);}
  static List<object> Events(Api a,IntPtr owner,int offset=0x244){IntPtr array=NativeMemory.Add(owner,offset);a.Table(array,"EventPointerArray");byte[] header=NativeMemory.Bytes(array,20);var h=Header(array,4);NativeMemory.Require(h.Item2>=0,"Page event count exceeds bounded native read.");var result=new List<object>();var seen=new HashSet<uint>();for(int i=0;i<h.Item2;i++){IntPtr p=NativeMemory.Ptr(h.Item1,4*i);a.Table(p,"Event");NativeMemory.Require(seen.Add(NativeMemory.U(p)),"Page events share a duplicate owning pointer.");a.Table(NativeMemory.Add(p,0x58),"EventPayload");result.Add(new Dictionary<string,object>{{"index",i},{"object",NativeMemory.Hex(p)},{"int4",unchecked((uint)NativeMemory.I32(p,4))},{"string8",C(NativeMemory.Add(p,8),262144)},{"intC",unchecked((uint)NativeMemory.I32(p,12))},{"string10",C(NativeMemory.Add(p,16),262144)},{"word14",unchecked((ushort)Marshal.ReadInt16(p,20))},{"strings1C",StringArray(a,NativeMemory.Add(p,0x1C))},{"ints30",IntArray(a.Engine,NativeMemory.Add(p,0x30))},{"ints44",IntArray(a.Engine,NativeMemory.Add(p,0x44))},{"payload58_hex",ByteArray(a,NativeMemory.Add(p,0x5C))},{"string70",C(NativeMemory.Add(p,0x70),1048576)},{"bytes74_hex",ByteArray(a,NativeMemory.Add(p,0x74))},{"runtime_byte88",(int)Marshal.ReadByte(p,0x88)},{"raw_complete_hex",Bytes(p,0x8C)}});}NativeMemory.Require(Bytes(array,20)==BitConverter.ToString(header).Replace("-","").ToLowerInvariant(),"Page event array header changed during read.");return result;}
  static Dictionary<string,object> CommonEvents(Api a,IntPtr doc){var sources=new Dictionary<string,object>();foreach(int off in new[]{0x150,0x154,0x15C})sources.Add("0x"+off.ToString("X"),C(NativeMemory.Add(doc,off),1048576));var binaries=new Dictionary<string,object>();foreach(int off in new[]{0x160,0x174,0x188})binaries.Add("0x"+off.ToString("X"),ByteArray(a,NativeMemory.Add(doc,off)));return new Dictionary<string,object>{{"sources",sources},{"scalar158_raw_uint32",unchecked((uint)NativeMemory.I32(doc,0x158))},{"binary_arrays",binaries},{"source_business_names_inferred",false}};}
  static Dictionary<string,object> Password(IntPtr doc){string text=C(NativeMemory.Add(doc,0x2B4),32767);return new Dictionary<string,object>{{"gate",NativeMemory.I32(doc,0x2B0)},{"utf16_length",text.Length},{"utf16_sha256",Hash(Encoding.Unicode.GetBytes(text))},{"plaintext_disclosed",false}};}
  static void ReadCommonWindow(IntPtr doc,Dictionary<string,object> snapshot){
   int offset;
   try{offset=NativeLayout.Offset("document.common_window_id");}
   catch(NativeAbiUnavailableException){snapshot["common_window_unavailable"]="locator_unresolved";return;}
   int id=NativeMemory.I32(doc,offset);
   if(id==-1){snapshot["common_window"]=null;return;}
   object name=null;
   foreach(object raw in (IEnumerable)M(snapshot["page"])["pages"]){
    var page=M(raw);
    if(N(page,"id")==id){name=page["name"];break;}
   }
   snapshot["common_window"]=new Dictionary<string,object>{{"id",id},{"name",name}};
  }
  static bool CommonWindowRequest(Dictionary<string,object> action,out object selection){
   selection=null;
   object after, fields;
   if(!action.TryGetValue("after",out after))return false;
   var desired=after as Dictionary<string,object>;
   if(desired==null||!desired.TryGetValue("fields",out fields))return false;
   var selected=fields as Dictionary<string,object>;
   return selected!=null&&selected.TryGetValue("common_window",out selection);
  }
  static Dictionary<string,object> Read(Api a,Dictionary<string,object> action){NativeMemory.Require(S(action,"kind")==Kind,"Page document property kind differs.");var target=M(action["target"]);IntPtr page=a.Pages.Page(target),doc=a.Pages.Document(page,N(target,"page_id"));var words=new Dictionary<string,object>();for(int i=4;i<=20;i++)words.Add(i.ToString(CultureInfo.InvariantCulture),unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.attributes")+(i-4)*4)));IntPtr manager,main;var mainState=NativeReferencedPageEditing.PagePropertiesMainRead(a.Refs,out manager,out main);var result=new Dictionary<string,object>{{"abi_profile_sha256",AbiProfileSha},{"page",a.Pages.PageSnapshot(page)},{"description",C(NativeMemory.Add(doc,0x260),131072)},{"read_only_string264",C(NativeMemory.Add(doc,0x264),131072)},{"native_I4_properties",words},{"password",Password(doc)},{"events",Events(a,doc)},{"common_events",CommonEvents(a,doc)},{"draw_tree",NativeUsableEditPermit.CurrentDrawControls(a.Engine,doc,N(target,"page_id"))},{"history_store_projection",NativeHistoryStoreProjection.Prepare(a.Engine,doc).Before},{"main_control",mainState},{"no_language_mutator_called",true},{"language_catalog_serialized_or_verified",false},{"full_serialization_preimage",false}};
   object commonWindow;
   if(target.TryGetValue("include_common_window",out commonWindow)){
    NativeMemory.Require(commonWindow is bool,"include_common_window must be Boolean.");
    if(Object.Equals(commonWindow,true))ReadCommonWindow(doc,result);
   }
   object selection;
   if(CommonWindowRequest(action,out selection))
    result["common_window_change"]=CommonWindowEdit.Capture(a,page,doc,result,selection);
   return result;
  }
  sealed class CommonWindowEdit {
   const string GenerateProfile="coverage-20261101/usable-edit-0001/page-control-prep/complex-control-prep/reference-sync-abi-profile.json";
   const string CompiledProgramHeader="000000000000000000000000";
   const string CompiledEmptyEvent=CompiledProgramHeader+"01";
   readonly Api api;
   readonly IntPtr page,doc,view;
   readonly int owner,offset,target;
   readonly GeneratePage generate;
   readonly NativeLazyFunctionProfile profile;
   readonly NativeEngine.ThisPointer getView;
   readonly NativePageViewOperations.Api views;
   readonly object expectedEdges,hostControls;
   internal readonly bool ScriptedHost,NeutralPageClick,ConstantPageClick,WindowPageClick;
   internal readonly int ScriptWindowReferenceCount,ScriptRandomCallCount;
   internal readonly object Selection;
   internal int VerifiedInputLimitProjections{get;private set;}
   internal bool PopulatedHost{get{return hostControls!=null;}}

   static readonly HashSet<string> ProvenHostClasses=new HashSet<string>(StringComparer.Ordinal){
    "CDrawLabel","CDrawRect","CDrawEdit","CDrawMulBtn","CDrawUnit","CDrawBitmap","CDrawButton","CDrawRotateTbl"};

   static string ControlStateDigest(object state){return Hash(Encoding.UTF8.GetBytes(NativeUsableEditPermit.Json(state)));}

   // This CAniInput layout retains the user-facing limits but materializes
   // their two number programs the first time the original compiler runs.
   // The literals below are comparison postimages, never written to native state.
   static string OriginalInputLimitPostimage(Dictionary<string,object> state,string rtti){
    if(rtti!=".?AVCDrawLabel@@"||((IList)state["events"]).Count!=0)return null;
    var items=(IList)state["animations"];
    if(items.Count!=2)return null;
    var output=M(items[0]);var input=M(items[1]);
    if(S(output,"class")!="CAniOutput"||S(input,"class")!="CAniInput")return null;
    var words=M(input["words_uint32"]);
    var strings=M(input["strings"]);
    var bytes=M(input["byte_arrays_hex"]);
    string binding=S(strings,"2c");
    if(binding.Length==0||S(M(output["strings"]),"2c")!=binding||N(input,"enabled_raw_byte")!=10||
       Bits(words["30"])!=0||Bits(words["54"])!=0||Bits(words["88"])==0||
       Bits(words["4c"])!=0x501502F9U||Bits(words["50"])!=0xD01502F9U||
       S(strings,"58")!="1e+010"||S(strings,"5c")!="-1e+010"||
       S(bytes,"14")!=""||S(bytes,"60")!=""||S(bytes,"74")!="")return null;
    bytes["60"]="030000000000000001000000030000000000000012000000205fa002422c0000000001";
    bytes["74"]="030000000000000001000000030000000000000012000000205fa002c22c0000000001";
    return ControlStateDigest(state);
   }

   static List<object> MeterPrograms(Api api,IntPtr full){
    var programs=new List<object>();
    NativeMemory.Require(NativeMemory.I32(full,NativeLayout.Offset("control.rotate_meter.conditional_image"))==0,
      "An enabled independent instrument image compiler needs its own preservation proof.");
    for(int i=0;i<6;i++){
     string suffix=i.ToString(CultureInfo.InvariantCulture);
     int source=NativeLayout.Offset("control.rotate_meter.source_"+suffix);
     int cache=NativeLayout.Offset("control.rotate_meter.program_"+suffix);
     NativeMemory.Require(cache==source+4,"Original instrument source and CByteArray roles differ.");
     programs.Add(new Dictionary<string,object>{{"source",C(NativeMemory.Add(full,source),1048576)},
       {"program",ByteArray(api,NativeMemory.Add(full,cache))}});
    }
    return programs;
   }

   // Use the same class/dispatch roles as original reference generation.
   static List<object> HostControls(Api api,IntPtr doc,IEnumerable drawTree,NativeLazyFunctionProfile profile,bool projectInputLimits=false){
    var declarations=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);
    foreach(object raw in (IEnumerable)profile.Profile["control_classes"]){
     var row=M(raw);
     string name=S(row,"class_name");
     if(ProvenHostClasses.Contains(name))declarations.Add(".?AV"+name+"@@",row);
    }
    var animations=new NativeAnimationListEditing.OwnedApi(api.Engine,api.Pages.Shared);
    var records=new List<object>();
    List<object> buttons=null;
    foreach(object raw in drawTree){
     var drawing=M(raw);
     string rtti=S(drawing,"rtti");
     Dictionary<string,object> known;
     if(!declarations.TryGetValue(rtti,out known))
      throw new InvalidOperationException("The common window host contains a drawing without a verified compiler contract: "+rtti);
     IntPtr full=new IntPtr(N(drawing,"complete"));
     IntPtr primary=api.Engine.Address(N(known,"primary_rva"));
     IntPtr instance=NativeMemory.Add(full,4);
     IntPtr objectTable=api.Engine.Address(N(known,"iobject_rva"));
     NativeMemory.Require(NativeMemory.Ptr(full,0)==primary&&NativeMemory.Ptr(instance,0)==objectTable&&
       NativeMemory.I32(full,NativeLayout.Offset("control.type_id"))==N(known,"type_id")&&
       NativeMemory.Ptr(objectTable,84)==api.Engine.Address(N(known,"generate_entry_rva"))&&
       NativeMemory.Ptr(primary,124)==api.Engine.Address(N(known,"compile31_entry_rva")),
       "Original common window host drawing compiler identity differs: "+rtti);
     // Allocation addresses are diagnostic; event source and compiled arrays remain exact.
     var events=Events(api,full,0x30);
     foreach(object value in events)M(value).Remove("raw_complete_hex");
     object values;
     using(var properties=new NativeTypedPropertyCollector(api.Engine))
      values=properties.Read(instance);
     var state=new Dictionary<string,object>{{"properties",values},{"events",events},
       {"animations",animations.Records(full)}};
     if(rtti==".?AVCDrawRotateTbl@@"){
      profile.Address("CDrawRotateTblCompile31Body");
      state["instrument_programs"]=MeterPrograms(api,full);
     }
     if(rtti==".?AVCDrawButton@@"){
      if(buttons==null)buttons=NativeReferencedPageEditing.PagePropertiesButtons(api.Refs,doc);
      object selected=buttons.Find(value=>Object.Equals(M(value)["complete"],drawing["complete"]));
      NativeMemory.Require(selected!=null,"Original standard button action arrays are absent.");
      state["button_actions"]=selected;
     }
     var record=new Dictionary<string,object>{{"control",drawing["complete"]},{"rtti",rtti},
       {"state_sha256",ControlStateDigest(state)}};
     if(projectInputLimits){
      string postimage=OriginalInputLimitPostimage(state,rtti);
      if(postimage!=null)record["original_input_limit_postimage_sha256"]=postimage;
     }
     records.Add(record);
    }
    return records;
   }

   static Dictionary<string,object> Identity(Api api,Dictionary<int,IntPtr> pages,object input){
    if(input==null)return null;
    var key=M(input);object id;
    NativeMemory.Require(key.Count==2&&key.TryGetValue("id",out id)&&id is int&&key.ContainsKey("name"),
      "A common window requires exactly its page ID and exact current name.");
    int number=N(key,"id");
    NativeMemory.Require(number>=0&&pages.ContainsKey(number),"Common window ID is absent from the current project.");
    IntPtr page=pages[number];
    string name=NativeStrategyProfile.ReadName(api.Pages.Shared,page);
    NativeMemory.Require(name==S(key,"name"),"Common window name does not match its current ID.");
    api.Pages.Document(page,number);
    return new Dictionary<string,object>{{"id",number},{"name",name}};
   }
   static int Id(object value){return value==null?-1:N(M(value),"id");}
   static string Edge(object raw){var row=M(raw);return S(row,"source")+"\0"+S(row,"target");}
   static List<string> Edges(Api api){
    var result=new List<string>();
    foreach(object row in (IEnumerable)NativeReferencedPageEditing.Graph(api.Refs)["edges"])result.Add(Edge(row));
    result.Sort(StringComparer.Ordinal);
    return result;
   }
   static readonly string[] SourceFields={"0x150","0x154","0x15C"},CacheFields={"0x160","0x174","0x188"};
   const string Identifier=@"[\p{L}_][\p{L}\p{Nd}_]*",Space=@"[ \t]*",Number=@"[+-]?[0-9]+";
   const string StatementEnd=Space+"(?:'.*)?$";
   static readonly Regex Assignment=new Regex(
    "^"+Space+"(?<destination>"+Identifier+")"+Space+"="+Space+
    @"(?:""[^""]*""|(?:(?<operand>"+Identifier+")|"+Number+")(?:"+Space+@"[+-]"+Space+
    "(?:(?<operand>"+Identifier+")|"+Number+"))?)"+StatementEnd,RegexOptions.CultureInvariant);
   static readonly Regex SimpleCondition=new Regex(
    "^"+Space+@"if[ \t]+(?<operand>"+Identifier+")"+Space+@"(?:<=|>=|<>|<|>|=)"+Space+Number+
    @"[ \t]+then"+StatementEnd,RegexOptions.IgnoreCase|RegexOptions.CultureInvariant);
   static readonly Regex EndCondition=new Regex("^"+Space+"endif"+StatementEnd,RegexOptions.IgnoreCase|RegexOptions.CultureInvariant);
   static readonly Regex EmptyLine=new Regex("^"+StatementEnd,RegexOptions.CultureInvariant);
   static readonly Regex CommentOnlyClick=new Regex(@"\A[ \t]*'[^\r\n]*(?:\r\n|\n)?\z",RegexOptions.CultureInvariant);
   static readonly Regex ConstantClickAssignment=new Regex(
    "^"+Space+"(?<destination>"+Identifier+")"+Space+"="+Space+"(?<value>"+Number+")"+StatementEnd,
    RegexOptions.CultureInvariant);
   static readonly Regex SetWindowModeOne=new Regex(
    "^"+Space+"!SetWindow"+Space+@"\("+Space+"(?<window>"+Identifier+")"+Space+","+Space+"1"+Space+@"\)"+StatementEnd,
    RegexOptions.IgnoreCase|RegexOptions.CultureInvariant);
   static readonly Regex RandomAssignment=new Regex(
    "^"+Space+"(?<destination>"+Identifier+")"+Space+"="+Space+"!Rand"+Space+@"\("+
    Space+"(?<low>"+Number+")"+Space+","+Space+"(?<high>"+Number+")"+Space+@"\)"+StatementEnd,
    RegexOptions.IgnoreCase|RegexOptions.CultureInvariant);
   static readonly Regex RandomCallWire=new Regex(
    "11(?<low>[0-9a-f]{8})4711(?<high>[0-9a-f]{8})4707(?<operator>[0-9a-f]{8})0300000002000000",
    RegexOptions.CultureInvariant);

   // The saved E-series cache has operand word 15 here. The live original
   // designer can expose zero at that word immediately after opening it.
   // The source name, current ID and complete direct graph must still agree.
   const string SetWindowModeOneProgramPrefix="0000000000000000000000000bffffffff01feffffff11010000004707";

   static bool HasSources(object raw){
    foreach(object value in M(M(raw)["sources"]).Values)
     if(!Object.Equals(value,""))return true;
    return false;
   }
   internal static Dictionary<string,object> HostEvents(object raw){
    var events=M(raw);
    var sources=M(events["sources"]);
    var original=M(events["binary_arrays"]);
    var arrays=new Dictionary<string,object>();
    for(int i=0;i<SourceFields.Length;i++){
     string source=S(sources,SourceFields[i]), cache=S(original,CacheFields[i]);
     if(source.Length==0){
      NativeMemory.Require(cache==""||cache==CompiledEmptyEvent,
        "The empty common-window host event has an unexpected native cache.");
      cache="";
     }else NativeMemory.Require(cache!=""&&cache!=CompiledEmptyEvent,
       "The common-window host script requires its existing original compiled program.");
     arrays.Add(CacheFields[i],cache);
    }
    var projected=new Dictionary<string,object>(events);
    projected["binary_arrays"]=arrays;
    return projected;
   }

   static List<string> ActiveScriptLines(string script){
    var result=new List<string>();
    using(var reader=new StringReader(script)){
     string line;
     while((line=reader.ReadLine())!=null)
      if(!EmptyLine.IsMatch(line))result.Add(line);
    }
    return result;
   }

   static void CollectScriptNames(IEnumerable<string> lines,HashSet<string> names,List<Tuple<int,int>> randomCalls){
    int depth=0;
    foreach(string line in lines){
     if(EndCondition.IsMatch(line)){
      NativeMemory.Require(depth>0,"Unexpected EndIf in the common-window host script.");
      depth--;continue;
     }
     Match condition=SimpleCondition.Match(line);
     if(condition.Success){
      depth++;
      names.Add(condition.Groups["operand"].Value);
      continue;
     }
     Match random=RandomAssignment.Match(line);
     if(random.Success){
      int low=0,high=0;
      NativeMemory.Require(Int32.TryParse(random.Groups["low"].Value,NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out low)&&
        Int32.TryParse(random.Groups["high"].Value,NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out high),
        "The two original Rand arguments must be signed 32-bit numeric literals.");
      randomCalls.Add(Tuple.Create(low,high));
      names.Add(random.Groups["destination"].Value);
      continue;
     }
     Match assignment=Assignment.Match(line);
     NativeMemory.Require(assignment.Success,
      "The common-window host script is outside the supported scalar statements, Rand assignment or standalone SetWindow call.");
     names.Add(assignment.Groups["destination"].Value);
     foreach(System.Text.RegularExpressions.Capture operand in assignment.Groups["operand"].Captures)names.Add(operand.Value);
    }
    NativeMemory.Require(depth==0,"Unclosed If in the common-window host script.");
   }

   static string NativeI4Hex(int value){return BitConverter.ToString(BitConverter.GetBytes(value)).Replace("-","").ToLowerInvariant();}

   static void VerifyRandomPrograms(string cache,List<Tuple<int,int>> expected){
    int index=0;
    foreach(Match candidate in RandomCallWire.Matches(cache)){
     if(candidate.Index%2!=0)continue;
     NativeMemory.Require(index<expected.Count&&candidate.Groups["low"].Value==NativeI4Hex(expected[index].Item1)&&
       candidate.Groups["high"].Value==NativeI4Hex(expected[index].Item2),
       "An original Rand program call's two compiled literals differ from its source.");
     string current=candidate.Groups["operator"].Value;
     NativeMemory.Require(current=="02000000",
       "Current Rand compiled call encoding is unverified: "+current+". Its current cache can be read with page-document-properties.");
     index++;
    }
    NativeMemory.Require(index==expected.Count,"The original Rand script has no complete matching set of compiled integer calls.");
   }

   static string ScriptWindowEdge(Api api,Dictionary<int,IntPtr> pages,string ownerPath,string name,string cache,bool pageClick=false){
    IntPtr target=IntPtr.Zero;
    int targetId=-1;
    foreach(var page in pages)
     if(NativeStrategyProfile.ReadName(api.Pages.Shared,page.Value)==name){
      NativeMemory.Require(target==IntPtr.Zero,"The original SetWindow script target name is not unique.");
      target=page.Value;targetId=page.Key;
     }
    NativeMemory.Require(target!=IntPtr.Zero&&targetId>=0,"The original SetWindow script target page is absent.");
    api.Pages.Document(target,targetId);
    if(pageClick){
     // Distinct pages 2 and 21 compiled to the same CEventDispatch program. The
     // page name and the original registered edge establish the target identity.
     const string dispatchSuffix="03000000020000000001";
     NativeMemory.Require(cache==SetWindowModeOneProgramPrefix+"00000000"+dispatchSuffix||
       cache==SetWindowModeOneProgramPrefix+"02000000"+dispatchSuffix,
       "The original page Click SetWindow cache differs from its observed compiled mode-1 shape.");
    }else{
     string suffix="03000000"+NativeI4Hex(targetId)+"0001";
     NativeMemory.Require(cache==SetWindowModeOneProgramPrefix+"0f000000"+suffix||
       cache==SetWindowModeOneProgramPrefix+"00000000"+suffix,
       "The original SetWindow script cache differs from the current target ID and compiled mode-1 shape.");
    }
    return ownerPath+"\0"+api.Refs.Path(target);
   }

   static List<string> ScriptEdges(Api api,Dictionary<int,IntPtr> pages,object raw,string ownerPath,List<string> windows,out int randomCallCount){
    randomCallCount=0;
    var events=M(raw);
    var sources=M(events["sources"]);
    var caches=M(events["binary_arrays"]);
    var names=new HashSet<string>(StringComparer.Ordinal);
    for(int i=0;i<SourceFields.Length;i++){
     var lines=ActiveScriptLines(S(sources,SourceFields[i]));
     Match call=lines.Count==1?SetWindowModeOne.Match(lines[0]):Match.Empty;
     if(!call.Success){
      var randomCalls=new List<Tuple<int,int>>();
      CollectScriptNames(lines,names,randomCalls);
      if(randomCalls.Count>0)VerifyRandomPrograms(S(caches,CacheFields[i]),randomCalls);
      randomCallCount+=randomCalls.Count;
      continue;
     }
     string edge=ScriptWindowEdge(api,pages,ownerPath,call.Groups["window"].Value,S(caches,CacheFields[i]));
     if(!windows.Contains(edge))windows.Add(edge);
    }
    var edges=new List<string>();
    if(names.Count==0)return edges;
    var data=new NativeDataEngineering.Api(api.Engine,api.Context,api.Pages.Project);
    foreach(IntPtr variable in data.DataObjects()){
     string name=C(NativeMemory.Add(variable,8),256);
     if(!names.Remove(name))continue;
     int kind=NativeMemory.I32(variable,0x14);
     NativeMemory.Require(kind>=1&&kind<=3,"An original common-window host script uses a non-scalar data object: "+name);
     edges.Add(ownerPath+"\0"+api.Refs.Path(variable));
    }
    NativeMemory.Require(names.Count==0,"A common-window host script name is absent from the original scalar data objects.");
    edges.Sort(StringComparer.Ordinal);
    return edges;
   }
   static string PageClickEdge(Api api,Dictionary<int,IntPtr> pages,IList events,string ownerPath,out bool setWindow){
    setWindow=false;
    if(events.Count==0)return null;
    NativeMemory.Require(events.Count==1,"Common window editing accepts at most one compiled page Click.");
    var click=M(events[0]);
    NativeMemory.Require(N(click,"index")==0&&Bits(click["int4"])==0x12U&&
      Bits(click["intC"])==0&&S(click,"string8")=="Click"&&S(click,"string10")==""&&
      Object.Equals(click["word14"],UInt16.MaxValue)&&
      ((IList)click["strings1C"]).Count==0&&((IList)click["ints30"]).Count==0&&
      ((IList)click["ints44"]).Count==0&&S(click,"payload58_hex")==""&&N(click,"runtime_byte88")==0,
      "Common window editing requires the original unbound page Click without arguments or additional payload.");
    string source=S(click,"string70"),cache=S(click,"bytes74_hex");
    if(CommentOnlyClick.IsMatch(source)){
     NativeMemory.Require(cache==CompiledEmptyEvent,"The original comment-only page Click must have its exact compiled EOF.");
     return null;
    }
    var lines=ActiveScriptLines(source);
    Match call=lines.Count==1?SetWindowModeOne.Match(lines[0]):Match.Empty;
    if(call.Success){
     setWindow=true;
     return ScriptWindowEdge(api,pages,ownerPath,call.Groups["window"].Value,cache,pageClick:true);
    }
    Match assignment=lines.Count==1?ConstantClickAssignment.Match(lines[0]):Match.Empty;
    int value=0;
    NativeMemory.Require(assignment.Success&&Int32.TryParse(assignment.Groups["value"].Value,
      NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out value),
      "The original page Click needs a comment, signed integer assignment or standalone SetWindow(name,1).");
    string name=assignment.Groups["destination"].Value;
    var data=new NativeDataEngineering.Api(api.Engine,api.Context,api.Pages.Project);
    IntPtr variable=data.DataObjects().Find(p=>C(NativeMemory.Add(p,8),256)==name);
    NativeMemory.Require(variable!=IntPtr.Zero&&NativeMemory.I32(variable,0x14)==2,
      "The original page Click assignment destination must be a current scalar numeric data object.");
    int id=NativeMemory.I32(variable,0xA4);
    string expected=CompiledProgramHeader+"11"+NativeI4Hex(value)+"473e"+NativeI4Hex(id)+"01";
    NativeMemory.Require(id>=0&&cache==expected,
      "The original page Click program differs from the exact constant and current numeric object ID.");
    return ownerPath+"\0"+api.Refs.Path(variable);
   }
   internal static Dictionary<string,object> Capture(Api api,IntPtr page,IntPtr doc,Dictionary<string,object> snapshot,object rawSelection){
    var request=M(rawSelection);
    NativeMemory.Require(request.Count==2&&request.ContainsKey("source")&&request.ContainsKey("target"),
      "Common window change requires exactly source and target; null represents no selection.");
    var pageState=M(snapshot["page"]);int owner=N(pageState,"page_id");
    NativeMemory.Require(NativeEngine.Number(pageState["view"])!=0&&N(M(snapshot["password"]),"utf16_length")==0,
      "The scoped common window edit requires the unprotected loaded host in its original designer.");
    var pageEvents=(IList)snapshot["events"];
    bool scripted=HasSources(snapshot["common_events"]);
    HostEvents(snapshot["common_events"]);
    int offset=NativeLayout.Offset("document.common_window_id_write");
    NativeMemory.Require(offset==NativeLayout.Offset("document.common_window_id"),"Common window read and original store fields disagree.");
    if(scripted)NativeMemory.Require(offset==NativeLayout.Offset("document.common_window_script_compile"),
      "The original common-window host script compiler roles differ.");
    var pages=api.Pages.Pages();
    var source=Identity(api,pages,request["source"]);
    var target=Identity(api,pages,request["target"]);
    int oldId=Id(source),newId=Id(target);
    NativeMemory.Require(NativeMemory.I32(doc,offset)==oldId&&oldId!=newId,
      "Common window source differs from the current configuration or target makes no change.");
    if(newId!=-1){
     IntPtr canvas=api.Pages.Document(pages[newId],newId);
     // The original public-layer draw loop reassigns a CDrawAlm drawing owner.
     // That shared drawing state is not included in this narrower edit contract.
     foreach(var control in NativeUsableEditPermit.CurrentDrawControls(api.Engine,canvas,newId))
      NativeMemory.Require(!S(control,"rtti").StartsWith(".?AVCDrawAlm",StringComparison.Ordinal),
        "The public window contains an alarm drawing with special shared owner behavior.");
    }

    var chain=new List<object>();
    var seen=new HashSet<int>{owner};
    for(int id=newId;id!=-1;){
     NativeMemory.Require(seen.Add(id)&&pages.ContainsKey(id),"Common window target chain is cyclic or contains a missing page.");
     IntPtr linked=pages[id];
     int next=NativeMemory.I32(api.Pages.Document(linked,id),offset);
     chain.Add(new Dictionary<string,object>{{"id",id},{"name",NativeStrategyProfile.ReadName(api.Pages.Shared,linked)},{"next_id",next}});
     id=next;
    }
    string ownerPath=api.Refs.Path(page);
    bool pageClickSetsWindow;
    string pageClickEdge=PageClickEdge(api,pages,pageEvents,ownerPath,out pageClickSetsWindow);
    string from=oldId==-1?null:ownerPath+"\0"+api.Refs.Path(pages[oldId]);
    string to=newId==-1?null:ownerPath+"\0"+api.Refs.Path(pages[newId]);
    var graph=Edges(api);
    var windowEdges=new List<string>();
    int randomCalls=0;
    var scriptEdges=scripted?ScriptEdges(api,pages,snapshot["common_events"],ownerPath,windowEdges,out randomCalls):new List<string>();
    var independent=new HashSet<string>(scriptEdges,StringComparer.Ordinal);
    independent.UnionWith(windowEdges);
    if(pageClickEdge!=null)independent.Add(pageClickEdge);
    var expectedBefore=new HashSet<string>(independent,StringComparer.Ordinal);
    if(from!=null)expectedBefore.Add(from);
    var observed=graph.FindAll(edge=>edge.StartsWith(ownerPath+"\0",StringComparison.Ordinal));
    var expectedDirect=new List<string>(expectedBefore);expectedDirect.Sort(StringComparer.Ordinal);
    Same(expectedDirect,observed,"Host direct references differ from its verified script and common-window targets.");
    var expected=new List<string>(graph);
    if(from!=null&&!independent.Contains(from))expected.Remove(from);
    if(to!=null&&!independent.Contains(to))expected.Add(to);
    expected.Sort(StringComparer.Ordinal);
    var captured=new Dictionary<string,object>{{"source",source},{"target",target},{"target_chain",chain},
      {"registered_reference_edges",graph},{"expected_registered_reference_edges",expected}};
    if(pageClickEdge!=null)captured[pageClickSetsWindow?"compiled_page_click_set_window_edge":"compiled_constant_page_click_data_edge"]=pageClickEdge;
    else if(pageEvents.Count!=0)captured["compiled_neutral_page_click"]=true;
    if(scripted)captured["script_data_reference_edges"]=scriptEdges;
    if(randomCalls>0)captured["script_random_call_count"]=randomCalls;
    if(windowEdges.Count>0){
     windowEdges.Sort(StringComparer.Ordinal);
     captured["script_window_reference_edges"]=windowEdges;
    }
    if(((IList)pageState["top_level_controls"]).Count!=0){
     NativeMemory.Require(NativeLayout.Offset("document.common_window_id_nonempty_compile")==offset,
       "The populated-host original compiler and common-window store disagree.");
     var compiler=new NativeLazyFunctionProfile(api.Engine,GenerateProfile,NativeReferencedPageEditing.ReferenceSyncProfileSha,"editor");
     captured["populated_host_controls"]=HostControls(api,doc,(IEnumerable)snapshot["draw_tree"],compiler,true);
    }
    return captured;
   }
   internal CommonWindowEdit(Api a,IntPtr p,IntPtr d,Dictionary<string,object> snapshot){
    api=a;page=p;doc=d;owner=N(M(snapshot["page"]),"page_id");
    offset=NativeLayout.Offset("document.common_window_id_write");
    var proof=M(snapshot["common_window_change"]);
    Selection=proof["target"];target=Id(Selection);expectedEdges=proof["expected_registered_reference_edges"];
    ScriptedHost=proof.ContainsKey("script_data_reference_edges");
    NeutralPageClick=proof.ContainsKey("compiled_neutral_page_click");
    ConstantPageClick=proof.ContainsKey("compiled_constant_page_click_data_edge");
    WindowPageClick=proof.ContainsKey("compiled_page_click_set_window_edge");
    ScriptWindowReferenceCount=proof.ContainsKey("script_window_reference_edges")?((IList)proof["script_window_reference_edges"]).Count:0;
    ScriptRandomCallCount=proof.ContainsKey("script_random_call_count")?N(proof,"script_random_call_count"):0;
    proof.TryGetValue("populated_host_controls",out hostControls);
    getView=a.Pages.Bind<NativeEngine.ThisPointer>("size","GetUserView");
    view=getView(doc);
    views=new NativePageViewOperations.Api(a.Engine,a.Context,a.Pages.Project);
    profile=new NativeLazyFunctionProfile(a.Engine,GenerateProfile,NativeReferencedPageEditing.ReferenceSyncProfileSha,"editor");
    generate=profile.Bind<GeneratePage>("PageGenerateEntry");
    GuardGenerate();
   }
   void GuardView(){
    views.Current();IntPtr frame;
    NativeMemory.Require(api.Pages.Document(page,owner)==doc&&view!=IntPtr.Zero&&getView(doc)==view&&
      views.Probe(doc,out frame)&&Object.Equals(views.ActiveFrame(frame)["exact_page_is_active"],true),
      "Activate the selected common-window host in the Pro designer before editing it.");
   }
   void GuardGenerate(){
    GuardView();
    profile.Address("PageGenerateBody");profile.Address("UserDocCompile85Body");
    api.Engine.VerifyVirtual(NativeMemory.Ptr(page,0),21,profile.Address("PageGenerateEntry"),GenerateProfile,"PageGenerateEntry");
    api.Engine.VerifyVirtual(NativeMemory.Ptr(doc,0),85,profile.Address("UserDocCompile85Entry"),GenerateProfile,"UserDocCompile85Entry");
   }
   internal void Apply(NativeUsableEditPermit.Lease lease,Dictionary<string,object> action){
    lease.RequireApplying(action);
    GuardGenerate();
    NativeOperationTrace.BeforeMutation("page-common-window-original-dialog-id-store");
    Marshal.WriteInt32(doc,offset,target);
    NativeOperationTrace.BeforeMutation("page-common-window-original-owner-generate");
    NativeMemory.Require(generate(page),"Original common window page generation failed; read the actual state before any further action.");
    NativeStrategyProfile.MarkRootDirty(api.Pages.Shared);
   }
   internal void Verify(IEnumerable drawTree){
    GuardView();
    NativeMemory.Require(NativeMemory.I32(doc,offset)==target,"The exact host and selected common window differ.");
    Same(expectedEdges,Edges(api),"The original common window edit did not produce the exact registered edge replacement.");
    if(PopulatedHost)VerifyHostControls(drawTree);
   }
   void VerifyHostControls(IEnumerable drawTree){
    var current=HostControls(api,doc,drawTree,profile);
    var expected=new List<object>();
    int projected=0;
    foreach(object raw in (IEnumerable)hostControls){
     var row=new Dictionary<string,object>(M(raw));
     object originalCompilerPostimage;
     if(row.TryGetValue("original_input_limit_postimage_sha256",out originalCompilerPostimage)){
      row.Remove("original_input_limit_postimage_sha256");
      if(expected.Count<current.Count&&Object.Equals(M(current[expected.Count])["state_sha256"],originalCompilerPostimage)){
       row["state_sha256"]=originalCompilerPostimage;
       projected++;
      }
     }
     expected.Add(row);
    }
    Same(expected,current,
      "The original common window edit changed a host drawing's known properties, event values or animation cache.");
    VerifiedInputLimitProjections=projected;
   }
  }
  internal static Dictionary<string,object> Read(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return Read(new Api(e,c,project),action);}
  internal static Prepared Prepare(NativeEngine e,NativeContext c,string project,Dictionary<string,object> action){return new Prepared(new Api(e,c,project),action);}
  internal sealed class Prepared:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly NativeHistoryStoreProjection historyState;readonly CommonWindowEdit commonWindow;readonly Api api;readonly Dictionary<string,object> action,before,after,fields;readonly IntPtr page,doc,mainManager,mainDoc;readonly VI invalidate;readonly BeforeModify beforeModify;readonly V0 update;readonly VII flags;readonly VPP aux;readonly Save savePage,saveMain;readonly PP assign;readonly Dictionary<int,uint> writes=new Dictionary<int,uint>();readonly Dictionary<int,NativeStrategyProfile.CString> eventSources=new Dictionary<int,NativeStrategyProfile.CString>();uint? eventScalar;readonly List<NativeStrategyProfile.CString> owned=new List<NativeStrategyProfile.CString>();NativeStrategyProfile.CString description,password;IntPtr auxId,auxValue;readonly bool mainAffected,historyProjectionRequested;readonly uint historyBefore;bool applied,failed,disposed;
   internal Prepared(Api a,Dictionary<string,object> request){api=a;action=request;after=M(action["after"]);historyProjectionRequested=after.ContainsKey("history_property13_projection");NativeMemory.Require(S(request,"abi_profile_sha256")==AbiProfileSha&&after.Count==(historyProjectionRequested?2:1)&&after.ContainsKey("fields"),"Page document properties requires only fields and its exact ABI.");fields=M(after["fields"]);NativeMemory.Require(fields.Count>0,"Page document property edit is empty.");NativeMemory.Require(!fields.ContainsKey("common_window")||fields.Count==1,"Common window selection must be the only edited property in this action.");page=api.Pages.Page(M(action["target"]));doc=api.Pages.Document(page,N(M(action["target"]),"page_id"));historyState=NativeHistoryStoreProjection.Prepare(api.Engine,doc);before=Read(api,action);NativePageControlPreparation.Before(action,before);historyBefore=unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated")));if(historyProjectionRequested){var projection=M(after["history_property13_projection"]);NativeMemory.Require(projection.Count==2&&projection.ContainsKey("before_raw_uint32")&&projection.ContainsKey("after_raw_uint32")&&Bits(projection["before_raw_uint32"])==historyBefore&&Bits(projection["after_raw_uint32"])==0,"Original history property13 projection requires exact before and only native after0.");}NativeReferencedPageEditing.PagePropertiesMainRead(api.Refs,out mainManager,out mainDoc);beforeModify=api.Bind<BeforeModify>("UserDocBeforeModify");api.Pages.Slot(doc,96,0x3CBE6);flags=api.Bind<VII>("DocFlagsSet");invalidate=api.Bind<VI>("ViewInvalidate");update=api.Bind<V0>("ViewUpdate");aux=api.Bind<VPP>("MainAuxPresenceUpdate");savePage=api.Bind<Save>("UserDocSave");saveMain=api.Bind<Save>("MainDocSave");assign=api.Pages.Shared.Bind<PP>("CStringAssignCopy");
    try{if(fields.ContainsKey("common_window"))commonWindow=new CommonWindowEdit(a,page,doc,before);foreach(var field in fields){if(field.Key=="common_window")continue;if(field.Key=="description"){description=Own(Text(field.Value,131072));continue;}if(field.Key=="password"){password=Own(Text(field.Value,32767));continue;}if(field.Key=="event_source150"||field.Key=="event_source154"||field.Key=="event_source15C"){int off=Int32.Parse(field.Key.Substring(12),NumberStyles.HexNumber,CultureInfo.InvariantCulture);eventSources.Add(off,Own(Text(field.Value,1048576)));continue;}if(field.Key=="event_scalar158"){eventScalar=Bits(field.Value);continue;}int index;NativeMemory.Require(Int32.TryParse(field.Key,NumberStyles.None,CultureInfo.InvariantCulture,out index)&&index>=4&&index<=20&&index!=13,"Unsupported page property index; name/string264/generated13 use separate original operations.");uint value=Bits(field.Value);if(index==16)NativeMemory.Require(((value^unchecked((uint)NativeMemory.I32(doc,0x298)))&~3U)==0,"Only original-dialog flag bits1 and2 may change; other native flag bits are retained.");if(index==12)NativeMemory.Require(value<=1,"Original page/MainCtrl auxiliary membership is a Boolean checkbox.");if(index==18)NativeMemory.Require(value<=6,"Window layout selection is outside original seven-case switch.");writes.Add(index,value);}mainAffected=writes.ContainsKey(12)&&writes[12]!=unchecked((uint)NativeMemory.I32(doc,0x288));if(writes.ContainsKey(18)&&writes[18]!=unchecked((uint)NativeMemory.I32(doc,0x2A0)))NativeMemory.Require(writes.ContainsKey(19)&&writes.ContainsKey(20),"Changing original layout mode requires explicit client-width/height postimages19/20; no default placement is guessed.");int width=writes.ContainsKey(6)?unchecked((int)writes[6]):NativeMemory.I32(doc,0x270),height=writes.ContainsKey(7)?unchecked((int)writes[7]):NativeMemory.I32(doc,0x274);NativeMemory.Require(width>=1&&height>=1&&width<=32767&&height<=32767,"Page dimensions are outside native bounded geometry.");if(writes.ContainsKey(6)||writes.ContainsKey(7))foreach(var control in NativeUsableEditPermit.CurrentDrawControls(api.Engine,doc,N(M(action["target"]),"page_id"))){var rect=(IEnumerable)control["rectangle"];var values=new List<int>();foreach(object value in rect)values.Add(NativeEngine.Number(value));NativeMemory.Require(values.Count==4&&values[0]>=0&&values[1]>=0&&values[2]<=width&&values[3]<=height,"Page property dimensions would place an existing control outside the page.");}if(mainAffected){a.Table(NativeMemory.Add(mainManager,0x34),"MainService");NativeMemory.Require(NativeMemory.Ptr(mainManager,0x38)==mainDoc&&Marshal.ReadByte(mainDoc,0x154)==0,"Original MainCtrl callback requires already-loaded nonpreview document.");auxId=Marshal.AllocHGlobal(4);auxValue=Marshal.AllocHGlobal(4);Marshal.WriteInt32(auxId,NativeMemory.I32(doc,NativeLayout.Offset("document.archive_id")));Marshal.WriteInt32(auxValue,unchecked((int)writes[12]));}ValidateBefore();}catch{Dispose();throw;}
   }
   NativeStrategyProfile.CString Own(string value){var text=new NativeStrategyProfile.CString(api.Pages.Shared,value);owned.Add(text);NativeMemory.Require(C(text.Storage,1048576)==value,"Owned page property CString differs.");return text;}
   internal void ValidateBefore(){NativeMemory.Require(!disposed&&!applied&&!failed,"Page property preparation is disposed/applied/failed.");Same(before,Read(api,action),"Page property/full-known-event/MainCtrl preimage changed after prepare.");NativeMemory.Require(unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated")))==historyBefore&&(historyBefore==0||historyProjectionRequested),"Original history property13 reset needs its explicit exact projection permission.");}
   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){if(plan.Commit&&mainAffected)plan.RequireMainControlPersistence(action);}
   object ExpectedWords(){var words=new Dictionary<string,object>(M(before["native_I4_properties"]));foreach(var value in writes)words[value.Key.ToString(CultureInfo.InvariantCulture)]=value.Value;if(historyProjectionRequested)words["13"]=0U;return words;}
   void Verify(bool savedMain){api.Pages.Current();var drawTree=NativeUsableEditPermit.CurrentDrawControls(api.Engine,doc,N(M(action["target"]),"page_id"));if(commonWindow!=null)commonWindow.Verify(drawTree);NativeMemory.Require(api.Pages.Document(page,N(M(action["target"]),"page_id"))==doc,"Page document identity changed.");var words=new Dictionary<string,object>();for(int i=4;i<=20;i++)words.Add(i.ToString(CultureInfo.InvariantCulture),unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.attributes")+(i-4)*4)));Same(ExpectedWords(),words,"Page properties changed an unplanned native setting.");Same(description==null?before["description"]:C(description.Storage,131072),C(NativeMemory.Add(doc,0x260),131072),"Page description differs.");Same(before["read_only_string264"],C(NativeMemory.Add(doc,0x264),131072),"Untouched page string264 changed.");if(password==null)Same(before["password"],Password(doc),"Page password metadata changed without permission.");else{var expected=new Dictionary<string,object>{{"gate",checked(C(password.Storage,32767).Length*2+2)},{"utf16_length",C(password.Storage,32767).Length},{"utf16_sha256",Hash(Encoding.Unicode.GetBytes(C(password.Storage,32767)))},{"plaintext_disclosed",false}};Same(expected,Password(doc),"Page password original CString/gate update differs.");}var commonExpected=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue}.Deserialize<Dictionary<string,object>>(NativeUsableEditPermit.Json(before["common_events"]));foreach(var value in eventSources)M(commonExpected["sources"])["0x"+value.Key.ToString("X")]=C(value.Value.Storage,1048576);if(eventScalar.HasValue)commonExpected["scalar158_raw_uint32"]=eventScalar.Value;var commonActual=CommonEvents(api,doc);if(commonWindow!=null)Same(CommonWindowEdit.HostEvents(commonExpected),CommonWindowEdit.HostEvents(commonActual),"The common window edit changed host page scripts, parameters or existing compiled program content.");else Same(commonExpected,commonActual,"Window common event source/parameter/cache differs from the exact expected edit.");Same(before["events"],Events(api,doc),"Page settings changed a native event/compiled payload/runtime byte.");Same(historyState.AfterStoreSnapshot(before["draw_tree"]),drawTree,"Page settings changed a nested control owner/geometry/raw state.");var oldPage=M(before["page"]);Same(oldPage["pages"],api.Pages.PageRows(),"Page settings changed page list/name/ID.");Same(historyState.AfterStoreSnapshot(oldPage["top_level_controls"]),api.Pages.ControlRows(doc),"Page settings changed a top-level control owner/geometry/raw state.");IntPtr manager,currentDoc;var current=NativeReferencedPageEditing.PagePropertiesMainRead(api.Refs,out manager,out currentDoc);NativeMemory.Require(manager==mainManager&&currentDoc==mainDoc,"MainCtrl callback document identity changed.");var expectedMain=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue}.Deserialize<Dictionary<string,object>>(NativeUsableEditPermit.Json(before["main_control"]));if(mainAffected){var array=M(M(expectedMain["arrays"])["AuxIds"]);var values=new List<object>();int id=NativeMemory.I32(doc,NativeLayout.Offset("document.archive_id"));bool found=false;foreach(object value in(IEnumerable)array["values"]){if(Bits(value)==unchecked((uint)id)){found=true;if(writes[12]==0)continue;}values.Add(value);}if(!found&&writes[12]!=0)values.Add(unchecked((uint)id));array["values"]=values;array["count"]=values.Count;array["capacity"]=M(M(current["arrays"])["AuxIds"])["capacity"];}if(savedMain)M(expectedMain["settings_strings"])["0x168"]=unchecked((int)Bits(M(expectedMain["settings_scalars"])["0x150"])).ToString(CultureInfo.InvariantCulture);Same(NativeReferencedPageEditing.PagePropertiesMainValues(expectedMain),NativeReferencedPageEditing.PagePropertiesMainValues(current),"Page settings callback changed MainCtrl beyond the exact page-ID auxiliary membership.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);try{NativeMemory.Require(unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated")))==historyBefore&&(historyBefore==0||historyProjectionRequested),"Original history property13 preimage/permission differs.");api.Check("OriginalHistoryGenerated13Store");api.Pages.Slot(doc,96,0x3CBE6);api.Check("UserDocBeforeModify");NativeOperationTrace.BeforeMutation("usable-page-document-properties-original-before-modify");historyState.ValidateBefore();beforeModify(doc,IntPtr.Zero,1,1);historyState.OriginalStoreReturned();NativeMemory.Require(NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated"))==0,"Original history serializer did not return exact property13 raw0 projection.");if(commonWindow!=null)commonWindow.Apply(lease,action);foreach(var source in eventSources){lease.RequireApplying(action);NativeOperationTrace.BeforeMutation("usable-original-window-dialog-event-source-"+source.Key.ToString("X"));assign(NativeMemory.Add(doc,source.Key),source.Value.Storage);}if(eventScalar.HasValue){NativeOperationTrace.BeforeMutation("usable-original-window-dialog-event-scalar158");Marshal.WriteInt32(doc,0x158,unchecked((int)eventScalar.Value));}foreach(var field in writes){lease.RequireApplying(action);if(field.Key==16){api.Check("DocFlagsSet");for(int bit=1;bit<=2;bit*=2){NativeOperationTrace.BeforeMutation("usable-original-window-dialog-flag-"+bit);flags(doc,bit,(field.Value&(uint)bit)!=0?1:0);}}else{api.Check("OriginalWindowPropertyCommand");api.Check("OriginalDocGeometryStyleStores");NativeOperationTrace.BeforeMutation("usable-original-window-dialog-I4-property-"+field.Key);Marshal.WriteInt32(doc,0x268+(field.Key-4)*4,unchecked((int)field.Value));}}if(description!=null){NativeOperationTrace.BeforeMutation("usable-original-window-dialog-description");assign(NativeMemory.Add(doc,0x260),description.Storage);}if(password!=null){api.Check("OriginalDocPasswordStores");NativeOperationTrace.BeforeMutation("usable-original-window-dialog-password");assign(NativeMemory.Add(doc,0x2B4),password.Storage);Marshal.WriteInt32(doc,0x2B0,checked(C(password.Storage,32767).Length*2+2));}if(mainAffected){lease.RequireApplying(action);api.Check("MainAuxPresenceUpdate");NativeOperationTrace.BeforeMutation("usable-original-window-dialog-mainctrl-aux-presence");aux(NativeMemory.Add(mainManager,0x34),auxId,auxValue);}IntPtr view=api.Pages.Bind<NativeEngine.ThisPointer>("size","GetUserView")(doc);if(view!=IntPtr.Zero){api.Table(view,"DrawingView");NativeMemory.Require(NativeMemory.Ptr(view,0x74)==doc,"Original page drawing view belongs to another document.");api.Check("ViewInvalidate");NativeOperationTrace.BeforeMutation("usable-page-properties-original-view-invalidate");invalidate(view,1);api.Check("ViewUpdate");NativeOperationTrace.BeforeMutation("usable-page-properties-original-view-update");update(view);}Verify(false);applied=true;lease.CompleteApply(action);var result=NativePageControlPreparation.Result(Kind);result["native_I4_properties"]=ExpectedWords();result["original_history_property13_projection"]=new Dictionary<string,object>{{"explicitly_permitted",historyProjectionRequested},{"before_raw_uint32",historyBefore},{"after_raw_uint32",unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated")))},{"adapter_wrote_field_directly",commonWindow!=null}};if(commonWindow!=null){result["common_window"]=commonWindow.Selection;result["common_window_original_graph_regenerated"]=true;result["common_window_original_view_refreshed"]=true;result["common_window_original_empty_event_cache_projection"]=true;result["common_window_populated_host_control_state_verified"]=commonWindow.PopulatedHost;result["common_window_original_input_limit_cache_projection_count"]=commonWindow.VerifiedInputLimitProjections;result["common_window_scripted_host_preserved"]=commonWindow.ScriptedHost;if(commonWindow.NeutralPageClick)result["common_window_neutral_page_click_preserved"]=true;if(commonWindow.ConstantPageClick)result["common_window_constant_page_click_preserved"]=true;if(commonWindow.WindowPageClick)result["common_window_set_window_page_click_preserved"]=true;result["common_window_original_script_window_reference_count"]=commonWindow.ScriptWindowReferenceCount;result["common_window_original_script_random_call_count"]=commonWindow.ScriptRandomCallCount;result["common_window_overlay_verified"]=false;}result["main_control_aux_membership_callback"]=mainAffected;result["common_event_sources_changed"]=eventSources.Count;result["common_event_scalar_changed"]=eventScalar.HasValue;result["dispatch_event_setter_called"]=false;result["source_binary_recompile_deferred_to_original_final_check"]=eventSources.Count>0||eventScalar.HasValue;result["language_mutator_called"]=false;result["doc85_compile_called"]=commonWindow!=null;result["password_plaintext_disclosed"]=false;return result;}catch{failed=true;throw;}}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(applied&&!failed&&!disposed,"Page settings Apply must complete before Flush.");lease.BeginFlush(action);try{Verify(false);api.Pages.Slot(doc,83,0x23308);api.Check("UserDocSave");NativeOperationTrace.BeforeMutation("usable-page-properties-original-doc83");int pageReturn=savePage(doc,IntPtr.Zero);NativeMemory.Require(pageReturn==0&&NativeMemory.I32(doc,NativeLayout.Offset("document.modified"))==0,"Original UserDoc83 did not return success/clean.");bool saved=false;if(mainAffected){lease.RequireMainControlPersistence(action);api.Pages.Slot(mainDoc,83,0x118B);api.Check("MainDocSave");NativeOperationTrace.BeforeMutation("usable-page-properties-original-mainctrl-doc83");NativeMemory.Require(saveMain(mainDoc,IntPtr.Zero)==0&&NativeMemory.I32(mainDoc,NativeLayout.Offset("document.modified"))==0,"Original related MainCtrl Doc83 did not return success/clean.");saved=true;}Verify(saved);lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"native_page_doc83_return",pageReturn},{"main_control_doc83_saved",saved},{"full_serialization_acceptance_pending",true},{"root_save_called",false}};}catch{failed=true;throw;}}
   public void Dispose(){if(disposed)return;disposed=true;for(int i=owned.Count-1;i>=0;i--)owned[i].Dispose();owned.Clear();if(auxId!=IntPtr.Zero){Marshal.FreeHGlobal(auxId);auxId=IntPtr.Zero;}if(auxValue!=IntPtr.Zero){Marshal.FreeHGlobal(auxValue);auxValue=IntPtr.Zero;}}
  }
 }
}
