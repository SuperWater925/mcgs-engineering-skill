// One release DLL, with an explicit sibling configuration per connection.
// All initialization below is managed file/JSON/PE metadata work, never vendor calls.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeEngineeringDeliveryLayout {
  internal const string PortableEngineContract="mcgs-portable-engine/v1";
  internal const string ExpectedConfigurationSha256="runtime:mcgs-portable-engine/v1";
  internal const string ExpectedTransportClientSha256="298e62cf5798acc03d82af5dd5b5751703a1e65348e12a485780239c01fe3417";
  sealed class Layout {internal string File,Sha,Task,Engineering,Runtime,Install,Editor,Transport,TransportSha,Binding,BindingSha;}
  static readonly object sync=new object();static Layout loaded;
  static Layout Current{get{lock(sync){if(loaded==null){Layout value=Load();Require(Path.GetDirectoryName(value.Transport).Equals(value.Runtime,StringComparison.OrdinalIgnoreCase),"Portable queue transport must be directly inside RuntimeRoot.");loaded=value;}return loaded;}}}
  internal static string ConfigurationSha256{get{return Current.Sha;}}
  internal static string TaskRoot{get{return Current.Task;}}
  internal static string EngineeringRoot{get{return Current.Engineering;}}
  internal static string EvidenceRoot{get{return Path.Combine(EngineeringRoot,"task-evidence");}}
  internal static string RuntimeRoot{get{return Current.Runtime;}}
  internal static string WorkingRoot{get{return Path.Combine(RuntimeRoot,"engineering");}}
  internal static string InstallRoot{get{return Current.Install;}}
  internal static string EditorExecutable{get{return Current.Editor;}}
  internal static string ProgramRoot{get{return Path.GetDirectoryName(EditorExecutable);}}
  internal static string TransportClientFile{get{return Current.Transport;}}
  internal static string TransportClientSha256{get{return Current.TransportSha;}}
  internal static string PortableBindingFile{get{return Current.Binding;}}
  internal static string PortableBindingSha256{get{return Current.BindingSha;}}
  static void Require(bool value,string message){if(!value)throw new InvalidOperationException(message);}
  internal static string HashBytes(byte[] bytes){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
  internal static byte[] ReadRegular(string file){Require(File.Exists(file)&&(File.GetAttributes(file)&FileAttributes.Directory)==0,"Portable delivery needs an existing regular file: "+file);using(var stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read)){Require(stream.Length>0&&stream.Length<=int.MaxValue,"Portable delivery file exceeds managed bounds.");var data=new byte[(int)stream.Length];int at=0;while(at<data.Length){int n=stream.Read(data,at,data.Length-at);if(n==0)throw new EndOfStreamException();at+=n;}return data;}}
  internal static string Text(Dictionary<string,object> map,string key){object value;Require(map.TryGetValue(key,out value)&&value is string&&!String.IsNullOrEmpty((string)value)&&((string)value).IndexOf('\0')<0,"Portable delivery needs text: "+key);return(string)value;}
  internal static string Absolute(string text){Require(!String.IsNullOrEmpty(text)&&text.IndexOf('\0')<0&&Regex.IsMatch(text,@"\A(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|\z))"),"Portable path must be fully absolute.");string path=Path.GetFullPath(text),root=Path.GetPathRoot(path);return path.Equals(root,StringComparison.OrdinalIgnoreCase)?root:path.TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar);}
  internal static bool Within(string path,string root){return path.Equals(root,StringComparison.OrdinalIgnoreCase)||path.StartsWith(root.TrimEnd('\\','/')+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);}
  static string DirectoryPath(string text){string path=Absolute(text);Require(Directory.Exists(path),"Portable delivery directory is absent: "+path);return path;}
  static string EditorImage(string text){string file=Absolute(text);using(var stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read))using(var reader=new BinaryReader(stream)){Require(stream.Length>=64&&reader.ReadUInt16()==0x5a4d,"Selected editor DOS header differs.");stream.Position=60;uint pe=reader.ReadUInt32();Require(pe>=64&&(long)pe+26<=stream.Length,"Selected editor PE header is truncated.");stream.Position=pe;Require(reader.ReadUInt32()==0x00004550&&reader.ReadUInt16()==0x14c,"Selected editor must be an x86 PE image.");ushort count=reader.ReadUInt16();stream.Position+=12;ushort optional=reader.ReadUInt16(),flags=reader.ReadUInt16();Require(optional>=96&&(long)pe+24+optional<=stream.Length&&reader.ReadUInt16()==0x10b&&(flags&2)!=0&&(flags&0x2000)==0,"Selected editor must be a PE32 executable.");long table=(long)pe+24+optional;Require(count>=1&&count<=96&&table+count*40<=stream.Length,"Selected editor section table is truncated.");for(int i=0;i<count;i++){stream.Position=table+i*40+16;uint size=reader.ReadUInt32(),offset=reader.ReadUInt32();Require(size==0||(offset!=0&&(long)offset+size<=stream.Length),"Selected editor section bytes are truncated.");}}return file;}
  static Layout Load(){
   string assembly=typeof(NativeEngineeringDeliveryLayout).Assembly.Location;Require(!String.IsNullOrEmpty(assembly),"Portable engine has no local assembly file.");string file=Path.ChangeExtension(Path.GetFullPath(assembly),".scope.json");byte[] bytes=ReadRegular(file);
   var map=new JavaScriptSerializer{MaxJsonLength=int.MaxValue}.Deserialize<Dictionary<string,object>>(new UTF8Encoding(false,true).GetString(bytes).TrimStart('\uFEFF'));
   Require(map!=null&&map.Count==(map.ContainsKey("editor_executable")?11:10)&&map.ContainsKey("schema")&&map["schema"] is int&&(int)map["schema"]==1,"Portable delivery scope schema differs.");foreach(string key in map.Keys)Require(Array.IndexOf(new[]{"schema","task_root","engineering_root","runtime_root","install_root","transport_client_file","transport_client_sha256","editor_executable","portable_engine_contract","portable_binding_file","portable_binding_sha256"},key)>=0,"Unknown portable scope field.");Require(Text(map,"portable_engine_contract")==PortableEngineContract,"Portable engine contract differs.");
   var result=new Layout{File=file,Sha=HashBytes(bytes),Task=DirectoryPath(Text(map,"task_root")),Engineering=DirectoryPath(Text(map,"engineering_root")),Runtime=DirectoryPath(Text(map,"runtime_root")),Install=DirectoryPath(Text(map,"install_root")),Transport=Absolute(Text(map,"transport_client_file")),TransportSha=Text(map,"transport_client_sha256"),Binding=Absolute(Text(map,"portable_binding_file")),BindingSha=Text(map,"portable_binding_sha256")};
   Require(!result.Task.TrimEnd('\\','/').Equals(Path.GetPathRoot(result.Task).TrimEnd('\\','/'),StringComparison.OrdinalIgnoreCase)&&Within(result.Runtime,result.Task)&&!result.Runtime.Equals(result.Task,StringComparison.OrdinalIgnoreCase),"Portable runtime must be an explicit task child.");Require(!Within(result.Engineering,result.Runtime)&&!Within(result.Runtime,result.Engineering),"Portable runtime and engineering payload overlap.");Require(Within(result.Transport,result.Task)||Within(result.Transport,result.Engineering),"Transport source escapes task and payload.");Require(result.TransportSha==ExpectedTransportClientSha256&&HashBytes(ReadRegular(result.Transport))==result.TransportSha,"Transport source SHA differs.");Require(Within(result.Binding,result.Engineering)&&Regex.IsMatch(result.BindingSha,@"\A[a-f0-9]{64}\z")&&HashBytes(ReadRegular(result.Binding))==result.BindingSha,"Portable binding SHA/path differs.");result.Editor=EditorImage(map.ContainsKey("editor_executable")?Text(map,"editor_executable"):Path.Combine(result.Install,"Program","McgsSetPro.exe"));Require(Within(result.Editor,result.Install),"Selected editor escapes installation.");return result;
  }
  internal static void Check(){Layout value=Current;Require(HashBytes(ReadRegular(value.File))==value.Sha,"Portable scope changed after load.");Require(HashBytes(ReadRegular(value.Binding))==value.BindingSha,"Portable binding changed after load.");Require(HashBytes(ReadRegular(value.Transport))==value.TransportSha,"Portable transport changed after load.");DirectoryPath(value.Task);DirectoryPath(EvidenceRoot);DirectoryPath(value.Runtime);DirectoryPath(value.Install);}
 }
}
