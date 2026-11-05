// Deferred native dependencies. Loading a profile never resolves or calls an unused entry.
// Bound profile/index SHA, requested-row resolution, module identity and native byte/export guards remain mandatory.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
 internal sealed class NativeLazyFunctionProfile {
  sealed class RequestOwner {internal IntPtr Handle;internal string Sha;}
  [ThreadStatic]static Dictionary<string,RequestOwner> requestOwners;
  internal static void BeginRequest(){requestOwners=new Dictionary<string,RequestOwner>(StringComparer.OrdinalIgnoreCase);}
  internal static void EndRequest(){requestOwners=null;}
  static RequestOwner RequestModule(string roleOrPath){RequestOwner result;if(requestOwners!=null&&requestOwners.TryGetValue(roleOrPath,out result))return result;IntPtr handle=NativeAbiTargetProfiles.ModuleHandle(roleOrPath);result=new RequestOwner{Handle=handle};if(handle!=IntPtr.Zero){foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==handle){result.Sha=SourceHash(loaded.FileName);break;}NativeMemory.Require(result.Sha!=null,"Resolved native module has no current loaded image.");}if(requestOwners!=null)requestOwners.Add(roleOrPath,result);return result;}
  internal static bool SameModule(ProcessModule loaded,string roleOrPath){var expected=RequestModule(roleOrPath);return loaded.BaseAddress==expected.Handle&&expected.Sha!=null&&SourceHash(loaded.FileName)==expected.Sha;}
  internal static bool ModulePathMatches(string loadedPath,string roleOrPath){var expected=RequestModule(roleOrPath);if(expected.Handle==IntPtr.Zero)return false;foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(String.Equals(Path.GetFullPath(loaded.FileName),Path.GetFullPath(loadedPath),StringComparison.OrdinalIgnoreCase))return loaded.BaseAddress==expected.Handle&&SourceHash(loaded.FileName)==expected.Sha;return false;}
  internal static string SourceHash(string file){using(var stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read))using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();}
  internal static string ReadText(string file){return NativeAbiTargetProfiles.ReadLazyAllText(file,SourceHash(file));}
  internal static string EntryProfile(Dictionary<string,object> row){object raw;var state=row.TryGetValue("_abi_resolution",out raw)?raw as Dictionary<string,object>:null;if(state==null||!state.TryGetValue("profile",out raw)||!(raw is string))throw new InvalidDataException("A native row has no bound profile identity.");return(string)raw;}
  internal static void CheckRow(Dictionary<string,object> row,string kind){NativeAbiTargetProfiles.CheckEntry(row,kind,EntryProfile(row));}
  internal static void CheckIdentity(Dictionary<string,object> row,params string[] fields){NativeAbiTargetProfiles.CheckFields(row,"identity",EntryProfile(row),fields);}
  internal readonly NativeEngine Engine;internal readonly string Relative;
  readonly string expectedSha,format;
  Dictionary<string,object> profile;
  readonly Dictionary<string,Dictionary<string,object>> functions=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);
  readonly HashSet<string> ambiguousFunctions=new HashSet<string>(StringComparer.Ordinal);
  readonly Dictionary<string,Dictionary<string,object>> moduleRows=new Dictionary<string,Dictionary<string,object>>(StringComparer.OrdinalIgnoreCase);
  readonly Dictionary<string,IntPtr> handles=new Dictionary<string,IntPtr>(StringComparer.OrdinalIgnoreCase);
  readonly Dictionary<string,uint> preferred=new Dictionary<string,uint>(StringComparer.OrdinalIgnoreCase);
  readonly Dictionary<string,int> sizes=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);
  [DllImport("kernel32.dll",CharSet=CharSet.Ansi,ExactSpelling=true)]static extern IntPtr GetProcAddress(IntPtr module,string name);
  [DllImport("kernel32.dll",EntryPoint="GetProcAddress",ExactSpelling=true)]static extern IntPtr GetProcAddressOrdinal(IntPtr module,IntPtr ordinal);
  internal NativeLazyFunctionProfile(NativeEngine engine,string relative,string sha,string rowFormat){Engine=engine;Relative=relative;expectedSha=sha;format=rowFormat;}
  internal Dictionary<string,object> Profile {get{Load();return profile;}}
  // Profiles use both arrays of named declarations and maps of declarations/evidence.
  // Map keys supply only a name: an address in a key, scalar method value, or
  // disassembly record is never promoted to a callable RVA declaration.
  internal static List<Dictionary<string,object>> ProfileRows(object raw,string collection,bool requireRecords){
   var result=new List<Dictionary<string,object>>();
   var map=raw as Dictionary<string,object>;
   if(map!=null){
    foreach(var item in map){
     if(item.Key=="_abi_resolution")continue;
     var row=item.Value as Dictionary<string,object>;
     if(row==null){if(requireRecords)throw new InvalidDataException("Native profile "+collection+" map entry is not a record: "+item.Key);continue;}
     if(!row.ContainsKey("name")){var named=new Dictionary<string,object>(row,StringComparer.Ordinal);named.Add("name",item.Key);row=named;}
     result.Add(row);
    }
    return result;
   }
   var list=raw as IList;
   if(list==null)throw new InvalidDataException("Native profile "+collection+" must be a record list or map.");
   foreach(object value in list){var row=value as Dictionary<string,object>;if(row==null){if(requireRecords)throw new InvalidDataException("Native profile "+collection+" list entry is not a record.");continue;}result.Add(row);}
   return result;
  }
  static string RowName(Dictionary<string,object> row,string collection){object raw;string name=row.TryGetValue("name",out raw)?raw as string:null;if(String.IsNullOrEmpty(name))throw new InvalidDataException("Native profile "+collection+" declaration has no explicit name or map key.");return name;}
  // Pure managed normalization, also exercised against the delivered real profiles.
  // The original profile and each row's bound resolution contract remain untouched.
  internal static Dictionary<string,Dictionary<string,object>>[] IndexCollections(Dictionary<string,object> parsed){
   var modules=new Dictionary<string,Dictionary<string,object>>(StringComparer.OrdinalIgnoreCase);
   var calls=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);
   var ambiguous=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);
   object raw;
   if(parsed.TryGetValue("modules",out raw))foreach(var row in ProfileRows(raw,"modules",true))modules.Add(RowName(row,"modules"),row);
   foreach(string key in new[]{"functions","methods"}){
    if(!parsed.TryGetValue(key,out raw))continue;
    foreach(var row in ProfileRows(raw,key,false)){
     if(!row.ContainsKey("rva"))continue;
     string name=RowName(row,key);
     if(key=="methods"&&calls.ContainsKey(name))continue;
     if(calls.ContainsKey(name)){ambiguous[name]=row;continue;}
     calls.Add(name,row);
    }
   }
   return new[]{modules,calls,ambiguous};
  }
  void Load(){
   if(profile!=null)return;
   string file=Path.Combine(NativeOperations.TaskRoot,Relative.Replace('/',Path.DirectorySeparatorChar));
   var parsed=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(NativeAbiTargetProfiles.ReadLazyAllText(file,expectedSha));
   var indexed=IndexCollections(parsed);
   object raw;
   if(parsed.TryGetValue("binary_sha256",out raw))NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(raw),Engine.ImageSha256,"NativeLazyFunctionProfile:"+Relative+":editor"),"Native profile belongs to another editor image: "+Relative);
   foreach(var item in indexed[0])moduleRows.Add(item.Key,item.Value);
   foreach(var item in indexed[1])functions.Add(item.Key,item.Value);
   foreach(var item in indexed[2])ambiguousFunctions.Add(item.Key);
   profile=parsed;
  }
  internal bool Has(string name){Load();return functions.ContainsKey(name)&&!ambiguousFunctions.Contains(name);}
  IntPtr Module(string name){
   IntPtr handle;if(handles.TryGetValue(name,out handle))return handle;
   handle=NativeAbiTargetProfiles.ModuleHandle(name);if(handle==IntPtr.Zero)throw NativeAbiTargetProfiles.Problem("deployment","Required native module is not already loaded: "+name,Relative,name);
   ProcessModule found=null;foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==handle){found=loaded;break;}
   if(found==null)throw NativeAbiTargetProfiles.Problem("deployment","Required native module has no loaded image: "+name,Relative,name);
   Dictionary<string,object> row;
   uint imageBase;
   if(moduleRows.TryGetValue(name,out row)){
    NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(row["sha256"]),NativeMemory.Hash(found.FileName),"NativeLazyFunctionProfile:"+Relative+":"+name),"Native module observation failed: "+name);
    imageBase=unchecked((uint)NativeEngine.Number(row["preferred_base"]));
   }else{
    if(handle!=Engine.ImageBase)throw new NativeAbiUnavailableException("Profile has no explicit ABI module declaration: "+name,Relative,name);
    object value;imageBase=profile.TryGetValue("preferred_base",out value)?unchecked((uint)NativeEngine.Number(value)):0x400000U;
   }
   if(name.Equals("McgsSetPro.exe",StringComparison.OrdinalIgnoreCase))NativeAbiTargetProfiles.RequireIdentity(handle==Engine.ImageBase,"Native profile and attached editor disagree.",Relative,name);
   handles.Add(name,handle);preferred.Add(name,imageBase);sizes.Add(name,found.ModuleMemorySize);return handle;
  }
  Dictionary<string,object> CodeGuard(string module,int rva){foreach(string key in new[]{"code_guards","functions"}){object raw;if(!profile.TryGetValue(key,out raw))continue;foreach(var row in ProfileRows(raw,key,false)){object address,owner;if(!row.TryGetValue("rva",out address)||EngineNumber(address)!=rva||!row.ContainsKey("bytes"))continue;string role=row.TryGetValue("module",out owner)?Convert.ToString(owner):"McgsSetPro.exe";if(role==module)return row;}}throw new NativeAbiUnavailableException("Requested native method has no byte guard in its own profile.",Relative,module+":"+rva);}
  static int EngineNumber(object value){return NativeEngine.Number(value);}
  void GuardMethodChain(string module,int first){
   var seen=new HashSet<int>();int rva=first;
   while(true){
    NativeMemory.Require(seen.Add(rva),"Requested native method has a jump cycle.");var guard=CodeGuard(module,rva);
    NativeAbiTargetProfiles.CheckFields(guard,"requested method body",Relative,"rva","bytes","reloc_offsets");
    byte[] bytes=HexBytes(Convert.ToString(guard["bytes"]));IntPtr image=Module(module);
    NativeCodeRelocation.RebaseDeltaInPlace(bytes,(IEnumerable)guard["reloc_offsets"],unchecked(NativeMemory.U(image)-preferred[module]));
    NativeAbiTargetProfiles.RequireArtifact(rva>=0&&(long)rva+bytes.Length<=sizes[module],"Requested method guard exceeds its bound module.",Relative,module+":"+rva);
    NativeAbiTargetProfiles.RequireIdentity(BitConverter.ToString(bytes)==BitConverter.ToString(NativeMemory.Bytes(NativeMemory.Add(image,rva),bytes.Length)),"Current bound method bytes changed.",Relative,module+":"+rva);
    if(bytes.Length>=5&&bytes[0]==0xE9){rva=checked(rva+5+BitConverter.ToInt32(bytes,1));continue;}
    if(bytes.Length>=6&&bytes[0]==0xFF&&bytes[1]==0x25){
     IntPtr slot=new IntPtr(unchecked((int)BitConverter.ToUInt32(bytes,2)));object imports;
     if(profile.TryGetValue("mfc_imports",out imports)||profile.TryGetValue("imports",out imports)){
      bool matched=false;foreach(var row in ProfileRows(imports,"imports",false)){
       object raw;if(!row.TryGetValue("iat_rva",out raw)||NativeMemory.Add(Engine.ImageBase,EngineNumber(raw))!=slot)continue;
       var fields=new List<string>{"iat_rva","target_rva"};if(row.ContainsKey("ordinal"))fields.Add("ordinal");NativeAbiTargetProfiles.CheckFields(row,"requested method import",Relative,fields.ToArray());
       IntPtr owner=Module("mfc110u.dll"),target=NativeMemory.Add(owner,EngineNumber(row["target_rva"]));
       NativeAbiTargetProfiles.RequireIdentity(NativeMemory.Ptr(slot,0)==target,"Requested native method IAT differs.",Relative,module+":"+rva);
       if(row.TryGetValue("ordinal",out raw))NativeAbiTargetProfiles.RequireIdentity(GetProcAddressOrdinal(owner,new IntPtr(EngineNumber(raw)))==target,"Requested native method ordinal differs.",Relative,module+":"+rva);matched=true;
      }
      if(!matched)throw new NativeAbiUnavailableException("Requested native method import lacks a matching profile role.",Relative,module+":"+rva);
     }else throw new NativeAbiUnavailableException("Requested method is an import thunk without an import role contract.",Relative,module+":"+rva);
    }
    return;
   }
  }
  internal IntPtr Address(string name){
   NativeAbiTargetProfiles.RequireIdentity(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Native function access requires the captured x86 host UI thread.",Relative,name);
   Load();Dictionary<string,object> row;
   if(ambiguousFunctions.Contains(name))throw new NativeAbiUnavailableException("Native profile has multiple callable rows with this name; a profile-specific role is required: "+name,Relative,name);
   if(!functions.TryGetValue(name,out row))throw new NativeAbiUnavailableException("Native profile has no requested function: "+name,Relative,name);
   string bytesKey=format=="strategy"?"expected_first_32_bytes":format=="duplicate"?"first32":format=="save"?"expected_first32":format=="control"?"first32":"bytes";
   string relocKey=format=="strategy"?"relocatable_dword_offsets_in_first32":format=="duplicate"||format=="save"?"relocation_offsets":format=="control"?"relocations":"reloc_offsets";
   var fields=new List<string>{"rva"};if(row.ContainsKey("module"))fields.Add("module");if(row.ContainsKey(bytesKey)){fields.Add(bytesKey);fields.Add(relocKey);}if(row.ContainsKey("ordinal"))fields.Add("ordinal");if(row.ContainsKey("export_name"))fields.Add("export_name");
   NativeAbiTargetProfiles.CheckFields(row,"function",Relative,fields.ToArray());
   object value;string module=row.TryGetValue("module",out value)?Convert.ToString(value):"McgsSetPro.exe";
   IntPtr image=Module(module);int rva=NativeEngine.Number(row["rva"]);
   if(!row.ContainsKey(bytesKey)){GuardMethodChain(module,rva);return NativeMemory.Add(image,rva);}
   byte[] expected=HexBytes(Convert.ToString(row[bytesKey]));
   NativeAbiTargetProfiles.RequireArtifact(expected.Length>0&&rva>=0&&(long)rva+expected.Length<=sizes[module],"Native function guard exceeds its module: "+Relative+"/"+name,Relative,name);
   NativeCodeRelocation.RebaseDeltaInPlace(expected,(IEnumerable)row[relocKey],unchecked((uint)(NativeMemory.U(image)-preferred[module])));
   IntPtr address=NativeMemory.Add(image,rva);
   NativeAbiTargetProfiles.RequireIdentity(BitConverter.ToString(NativeMemory.Bytes(address,expected.Length))==BitConverter.ToString(expected),"Current bound function bytes changed: "+Relative+"/"+name,Relative,name);
   if(row.ContainsKey("ordinal"))NativeAbiTargetProfiles.RequireIdentity(GetProcAddressOrdinal(image,new IntPtr(NativeEngine.Number(row["ordinal"])))==address,"Native ordinal export differs: "+name,Relative,name);
   if(row.ContainsKey("export_name"))NativeAbiTargetProfiles.RequireIdentity(GetProcAddress(image,Convert.ToString(row["export_name"]))==address,"Native named export differs: "+name,Relative,name);
   return address;
  }
  internal T Bind<T>(string name)where T:class{return Marshal.GetDelegateForFunctionPointer(Address(name),typeof(T))as T;}
  static byte[] HexBytes(string value){NativeMemory.Require(!String.IsNullOrEmpty(value)&&value.Length%2==0,"Malformed native function byte guard.");var bytes=new byte[value.Length/2];for(int i=0;i<bytes.Length;i++)bytes[i]=Byte.Parse(value.Substring(i*2,2),NumberStyles.HexNumber,CultureInfo.InvariantCulture);return bytes;}
 }

 internal static class NativeProjectIdentity {
  const int RootDocVtableRva=0xD57684;
  static readonly ConditionalWeakTable<NativeEngine,NativeLazyFunctionProfile> profiles=new ConditionalWeakTable<NativeEngine,NativeLazyFunctionProfile>();
  internal static NativeLazyFunctionProfile Functions(NativeEngine engine){return profiles.GetValue(engine,delegate(NativeEngine value){return new NativeLazyFunctionProfile(value,"strategy-properties/strategy-write-guard-profile.json","cbf353eac5361873ff47179bf2ddd8e6a0b383864d91c109a98135880d804eea","strategy");});}
  internal static IntPtr RootDocument(NativeEngine engine){return RootDocument(engine,Functions(engine));}
  internal static IntPtr RootDocument(NativeEngine engine,NativeLazyFunctionProfile functions){
   NativeMemory.Require(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Project identity requires the captured x86 host UI thread.");
   IntPtr app=functions.Bind<NativeEngine.CdeclPointer>("GetAfxApp")();NativeMemory.Require(app!=IntPtr.Zero,"No current MFC application.");
   // These are the explicit evidenced x86 object fields, not offsets inferred from a software version.
   IntPtr doc=NativeMemory.Ptr(app,0x520),table=engine.Address(RootDocVtableRva);
   NativeMemory.Require(doc!=IntPtr.Zero&&NativeMemory.Ptr(doc,0)==table,"Current root document type differs.");
   IntPtr col=NativeMemory.Ptr(table,-4);engine.Rva(col);NativeMemory.Require(NativeMemory.I32(col,0)==0&&NativeMemory.I32(col,4)==0,"Current root document primary RTTI layout differs.");
   IntPtr type=NativeMemory.Ptr(col,12);engine.Rva(type);NativeMemory.Require(NativeMemory.Ascii(NativeMemory.Add(type,8),256)==".?AVC0DocManage@@","Current root document RTTI differs.");
   NativeMemory.Readable(NativeMemory.Add(doc,0x24),4);return doc;
  }
  internal static string CurrentProjectPath(NativeEngine engine){
   IntPtr doc=RootDocument(engine);string value=NativeUsableEditPermit.ReadCurrentCString(NativeMemory.Add(doc,0x24),Int32.MaxValue/2-1);NativeMemory.Require(value.Length>0,"Current native document has no project path.");return Path.GetFullPath(value);
  }
 }
}
