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
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
 internal sealed class NativeLazyFunctionProfile {
  internal readonly NativeEngine Engine;internal readonly string Relative;
  readonly string expectedSha,format;
  Dictionary<string,object> profile;
  readonly Dictionary<string,Dictionary<string,object>> functions=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);
  readonly Dictionary<string,Dictionary<string,object>> moduleRows=new Dictionary<string,Dictionary<string,object>>(StringComparer.OrdinalIgnoreCase);
  readonly Dictionary<string,IntPtr> handles=new Dictionary<string,IntPtr>(StringComparer.OrdinalIgnoreCase);
  readonly Dictionary<string,uint> preferred=new Dictionary<string,uint>(StringComparer.OrdinalIgnoreCase);
  readonly Dictionary<string,int> sizes=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase);
  [DllImport("kernel32.dll",CharSet=CharSet.Ansi,ExactSpelling=true)]static extern IntPtr GetProcAddress(IntPtr module,string name);
  [DllImport("kernel32.dll",EntryPoint="GetProcAddress",ExactSpelling=true)]static extern IntPtr GetProcAddressOrdinal(IntPtr module,IntPtr ordinal);
  internal NativeLazyFunctionProfile(NativeEngine engine,string relative,string sha,string rowFormat){Engine=engine;Relative=relative;expectedSha=sha;format=rowFormat;}
  internal Dictionary<string,object> Profile {get{Load();return profile;}}
  void Load(){
   if(profile!=null)return;
   string file=Path.Combine(NativeOperations.TaskRoot,Relative.Replace('/',Path.DirectorySeparatorChar));
   var parsed=new JavaScriptSerializer{MaxJsonLength=32*1024*1024,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(NativeAbiTargetProfiles.ReadLazyAllText(file,expectedSha));
   object raw;
   if(parsed.TryGetValue("modules",out raw))foreach(object value in (IEnumerable)raw){var row=(Dictionary<string,object>)value;moduleRows.Add(Convert.ToString(row["name"]),row);}
   if(parsed.TryGetValue("binary_sha256",out raw))NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(raw),Engine.ImageSha256,"NativeLazyFunctionProfile:"+Relative+":editor"),"Native profile belongs to another editor image: "+Relative);
   if(parsed.TryGetValue("functions",out raw))foreach(object value in (IEnumerable)raw){var row=(Dictionary<string,object>)value;functions.Add(Convert.ToString(row["name"]),row);}
   profile=parsed;
  }
  internal bool Has(string name){Load();return functions.ContainsKey(name);}
  IntPtr Module(string name){
   IntPtr handle;if(handles.TryGetValue(name,out handle))return handle;
   handle=NativeAbiTargetProfiles.ModuleHandle(name);NativeMemory.Require(handle!=IntPtr.Zero,"Required native module is not already loaded: "+name);
   ProcessModule found=null;foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==handle){found=loaded;break;}
   NativeMemory.Require(found!=null,"Required native module has no loaded image: "+name);
   Dictionary<string,object> row;
   uint imageBase;
   if(moduleRows.TryGetValue(name,out row)){
    NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(row["sha256"]),NativeMemory.Hash(found.FileName),"NativeLazyFunctionProfile:"+Relative+":"+name),"Native module observation failed: "+name);
    imageBase=unchecked((uint)NativeEngine.Number(row["preferred_base"]));
   }else{
    NativeMemory.Require(handle==Engine.ImageBase,"Profile has no explicit ABI module declaration: "+name);
    object value;imageBase=profile.TryGetValue("preferred_base",out value)?unchecked((uint)NativeEngine.Number(value)):0x400000U;
   }
   if(name.Equals("McgsSetPro.exe",StringComparison.OrdinalIgnoreCase))NativeMemory.Require(handle==Engine.ImageBase,"Native profile and attached editor disagree.");
   handles.Add(name,handle);preferred.Add(name,imageBase);sizes.Add(name,found.ModuleMemorySize);return handle;
  }
  internal IntPtr Address(string name){
   NativeMemory.Require(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Native function access requires the captured x86 host UI thread.");
   Load();Dictionary<string,object> row;
   if(!functions.TryGetValue(name,out row))throw new NativeAbiUnavailableException("Native profile has no requested function: "+name,Relative,name);
   NativeAbiTargetProfiles.CheckEntry(row,"function",Relative);
   object value;string module=row.TryGetValue("module",out value)?Convert.ToString(value):"McgsSetPro.exe";
   IntPtr image=Module(module);int rva=NativeEngine.Number(row["rva"]);
   string bytesKey=format=="strategy"?"expected_first_32_bytes":format=="duplicate"?"first32":format=="save"?"expected_first32":format=="control"?"first32":"bytes";
   string relocKey=format=="strategy"?"relocatable_dword_offsets_in_first32":format=="duplicate"||format=="save"?"relocation_offsets":format=="control"?"relocations":"reloc_offsets";
   byte[] expected=HexBytes(Convert.ToString(row[bytesKey]));
   NativeMemory.Require(expected.Length>0&&rva>=0&&(long)rva+expected.Length<=sizes[module],"Native function guard exceeds its module: "+Relative+"/"+name);
   foreach(object offset in (IEnumerable)row[relocKey]){
    int at=NativeEngine.Number(offset);NativeMemory.Require(at>=0&&at<expected.Length,"Invalid native function relocation start.");
    int count=Math.Min(4,expected.Length-at);byte[] word=new byte[4];Array.Copy(expected,at,word,0,count);
    uint relocated=unchecked(BitConverter.ToUInt32(word,0)+NativeMemory.U(image)-preferred[module]);Array.Copy(BitConverter.GetBytes(relocated),0,expected,at,count);
   }
   IntPtr address=NativeMemory.Add(image,rva);
   NativeMemory.Require(BitConverter.ToString(NativeMemory.Bytes(address,expected.Length))==BitConverter.ToString(expected),"Native function bytes differ: "+Relative+"/"+name);
   if(row.ContainsKey("ordinal"))NativeMemory.Require(GetProcAddressOrdinal(image,new IntPtr(NativeEngine.Number(row["ordinal"])))==address,"Native ordinal export differs: "+name);
   if(row.ContainsKey("export_name"))NativeMemory.Require(GetProcAddress(image,Convert.ToString(row["export_name"]))==address,"Native named export differs: "+name);
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
   IntPtr doc=RootDocument(engine);IntPtr text=NativeMemory.Ptr(doc,0x24);NativeMemory.Require(text!=IntPtr.Zero,"Current native document has no project path.");
   var result=new StringBuilder();for(int i=0;i<2048;i++){IntPtr at=NativeMemory.Add(text,2*i);NativeMemory.Readable(at,2);char c=(char)(ushort)Marshal.ReadInt16(at);if(c==0){NativeMemory.Require(result.Length>0,"Current native document has no project path.");return Path.GetFullPath(result.ToString());}result.Append(c);}
   throw new InvalidOperationException("Current native project path exceeds its bounded CString length.");
  }
 }
}
