// Bound only by the file-only preparation command. No Pro discovery, COM
// activation, vendor DLL loading, registry write or process start occurs here.
using System;using System.Collections.Generic;using System.Diagnostics;
using System.Globalization;using System.IO;using System.Reflection;
using System.Security.Cryptography;using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static class BootstrapLayout {
  internal const string ExpectedConfigurationSha256="__BOUND_CONFIGURATION_SHA256__";
  static readonly object Gate=new object();static Dictionary<string,object> data;
  static FileStream heldConfiguration;
  internal static string ConfigurationSha256{get{Load();return ExpectedConfigurationSha256;}}
  internal static string TaskRoot{get{return Text("task_root");}}
  internal static string RuntimeRoot{get{return Text("runtime_root");}}
  internal static string InstallRoot{get{return Text("install_root");}}
  internal static string BootstrapRoot{get{return Text("bootstrap_root");}}
  internal static string EditorFile{get{return Text("editor_executable");}}
  internal static string EditorSha256{get{return Text("editor_sha256");}}
  internal static string StartupRegistryPath{get{return Text("startup_registry_path");}}
  internal static string ColdRegistryHive{get{Load();object value;string name=data.TryGetValue("cold_registry_hive",out value)?Convert.ToString(value):"HKLM";Need(name=="HKLM"||name=="HKCU","Unknown cold registry hive.");return name;}}
  static Dictionary<string,object> StartupProtocol{get{
   Load();object raw;if(!data.TryGetValue("cold_runtime",out raw))return new Dictionary<string,object>{{"value_name","Count"},{"accepted_values",new object[]{0,1}},{"scan_value",0}};
   var runtime=raw as Dictionary<string,object>;Need(runtime!=null,"Cold runtime protocol is not an object.");var startup=Field(runtime,"startup")as Dictionary<string,object>;Need(startup!=null,"Cold startup protocol is absent.");return startup;
  }}
  internal static string StartupValueName{get{string value=Convert.ToString(Field(StartupProtocol,"value_name"),CultureInfo.InvariantCulture);Need(!String.IsNullOrEmpty(value)&&value.IndexOf('\0')<0,"Configured startup value name is invalid.");return value;}}
  internal static int StartupScanValue{get{return Convert.ToInt32(Field(StartupProtocol,"scan_value"),CultureInfo.InvariantCulture);}}
  internal static bool AcceptsStartupValue(int value){var values=Field(StartupProtocol,"accepted_values")as System.Collections.IEnumerable;Need(values!=null,"Configured startup states are absent.");foreach(object item in values)if(Convert.ToInt32(item,CultureInfo.InvariantCulture)==value)return true;return false;}
  internal static string[] ColdRegistrationRoots{get{
   Load();object raw;if(!data.TryGetValue("cold_com_identity",out raw))return new[]{@"Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}",@"Software\Classes\McgsInternalBridge.AddInObj",@"Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}"};
   var identity=raw as Dictionary<string,object>;Need(identity!=null,"Cold COM identity must be an object.");
   string cls=Convert.ToString(Field(identity,"class_guid")),lib=Convert.ToString(Field(identity,"type_library_guid")),prog=Convert.ToString(Field(identity,"progid"));
   Guid parsed;Need(Guid.TryParseExact(cls,"D",out parsed)&&Guid.TryParseExact(lib,"D",out parsed)&&Regex.IsMatch(prog,@"\AMcgsInternalBridge\.AddInObj_[a-f0-9]{10}\z"),"Cold COM identity is not deployment scoped.");
   return new[]{@"Software\Classes\CLSID\{"+cls+"}",@"Software\Classes\"+prog,@"Software\Classes\TypeLib\{"+lib+"}"};
  }}
  internal static string EngineRoot{get{return Path.Combine(BootstrapRoot,"engines");}}
  static string Text(string key){Load();return (string)data[key];}
  internal static string Hash(string file){using(var h=SHA256.Create())using(var f=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read))return Hex(h.ComputeHash(f));}
  static string Hex(byte[] bytes){return BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant();}
  static void Need(bool value,string message){if(!value)throw new InvalidOperationException(message);}
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr CreateFile(string name,uint access,uint share,IntPtr security,uint creation,uint flags,IntPtr template);
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern uint GetFinalPathNameByHandle(IntPtr file,StringBuilder name,uint length,uint flags);
  [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
  static string CanonicalExisting(string path){IntPtr handle=CreateFile(path,0,7,IntPtr.Zero,3,0x02000000,IntPtr.Zero);if(handle==new IntPtr(-1))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());try{int capacity=512;while(true){var text=new StringBuilder(capacity);uint length=GetFinalPathNameByHandle(handle,text,(uint)capacity,0);if(length==0)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());if(length<capacity){string name=text.ToString();if(name.StartsWith(@"\\?\UNC\",StringComparison.OrdinalIgnoreCase))return @"\\"+name.Substring(8);if(name.StartsWith(@"\\?\",StringComparison.Ordinal))return name.Substring(4);return name;}capacity=checked((int)length+1);}}finally{CloseHandle(handle);}}
  internal static string LocalAbsolute(string path){Need(path!=null&&((path.Length>=3&&Char.IsLetter(path[0])&&path[1]==':'&&(path[2]=='\\'||path[2]=='/'))||path.StartsWith(@"\\",StringComparison.Ordinal)),"Use an explicit absolute path, not a drive-relative path.");string full=Path.GetFullPath(path),anchor=Path.GetPathRoot(full);Need(!String.Equals(full.TrimEnd('\\'),anchor.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase),"A filesystem root is not an owned workspace.");var suffix=new Stack<string>();string cursor=full;while(!File.Exists(cursor)&&!Directory.Exists(cursor)){string parent=Path.GetDirectoryName(cursor);Need(!String.IsNullOrEmpty(parent)&&parent!=cursor,"No existing ancestor proves the configured absolute path.");suffix.Push(Path.GetFileName(cursor));cursor=parent;}full=CanonicalExisting(cursor);while(suffix.Count>0)full=Path.Combine(full,suffix.Pop());return full.TrimEnd('\\');}
  internal static bool SamePath(string a,string b){return String.Equals(LocalAbsolute(a),LocalAbsolute(b),StringComparison.OrdinalIgnoreCase);}
  internal static void Ancestors(string directory){LocalAbsolute(directory);}
  internal static string Regular(string path){string full=LocalAbsolute(path);Need(File.Exists(full)&&(File.GetAttributes(full)&FileAttributes.Directory)==0,"Bootstrap input is not a regular file: "+full);return full;}
  internal static void OwnedRuntime(string path){string root=RuntimeRoot.TrimEnd('\\')+"\\",full=LocalAbsolute(path);Need(full.StartsWith(root,StringComparison.OrdinalIgnoreCase)||SamePath(full,RuntimeRoot),"Runtime output escapes the configured queue root.");Ancestors(Directory.Exists(full)?full:Path.GetDirectoryName(full));}
  static object Field(Dictionary<string,object> value,string key){object item;return value!=null&&value.TryGetValue(key,out item)?item:null;}
  static void CheckCapability(Dictionary<string,object> value,Dictionary<string,object> capability){
   Need(capability!=null&&Object.Equals(Field(capability,"schema"),1)&&Object.Equals(Field(capability,"binary_sha256"),Field(value,"editor_sha256")),"Capability identity does not match the currently bound executable.");
   if(Object.Equals(Field(value,"entry_mode"),"thread_specific_hot_attach")){
    var mechanism=Field(capability,"mechanism")as Dictionary<string,object>;
    Need(Object.Equals(Field(capability,"entry_mode"),"thread_specific_hot_attach")&&Object.Equals(Field(capability,"hot_attach_mechanism_supported"),true)&&Object.Equals(Field(capability,"mechanism_preflight_only"),true)&&Object.Equals(Field(capability,"machine"),"I386")&&Object.Equals(Field(capability,"pe_format"),"PE32"),"No PE32/I386 hot-attach mechanism preflight matches this executable.");
    Need(Object.Equals(Field(mechanism,"hook"),"WH_GETMESSAGE")&&Object.Equals(Field(mechanism,"activation"),"COM")&&Object.Equals(Field(mechanism,"callback_thread"),"target_UI_STA"),"Hot attach requires the WH_GETMESSAGE/COM target UI-STA mechanism.");
    Need(Object.Equals(Field(capability,"native_cold_scan_used"),false)&&Object.Equals(Field(capability,"static_loader_contract_supported"),false)&&Object.Equals(Field(capability,"manufacturer_loader_or_business_abi_claimed"),false),"A hot-attach preflight must not claim manufacturer cold-loader or business ABI compatibility.");
   }else Need(Object.Equals(Field(capability,"static_loader_contract_supported"),true)||Object.Equals(Field(capability,"configured_cold_addin_protocol"),true),"No configured native cold-Addin protocol matches this executable.");
  }
  static void Load(){lock(Gate){if(data!=null)return;Need(ExpectedConfigurationSha256.Length==64,"Prepare and bind the bootstrap configuration before compiling.");string own=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),file=Regular(Path.Combine(own,"McgsInternalBridge.bridge.json"));var stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read);try{Need(stream.Length<=int.MaxValue,"Bootstrap configuration exceeds the CLR byte-array representation.");byte[] bytes=new byte[checked((int)stream.Length)];int at=0;while(at<bytes.Length){int n=stream.Read(bytes,at,bytes.Length-at);if(n==0)throw new EndOfStreamException();at+=n;}using(var h=SHA256.Create())Need(Hex(h.ComputeHash(bytes))==ExpectedConfigurationSha256,"Bootstrap configuration SHA differs from this compiled binding.");var value=new JavaScriptSerializer{MaxJsonLength=int.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(new UTF8Encoding(false,true).GetString(bytes));Need(value!=null&&Convert.ToInt32(value["schema"],CultureInfo.InvariantCulture)==1,"Bootstrap configuration schema differs.");foreach(string key in new[]{"task_root","runtime_root","install_root","bootstrap_root","editor_executable","loader_contract_file","addins_directory","addins_ini_file"}){Need(value[key] is string,"Bootstrap path is not text: "+key);value[key]=LocalAbsolute((string)value[key]);}string task=(string)value["task_root"],runtime=(string)value["runtime_root"],boot=(string)value["bootstrap_root"],install=(string)value["install_root"];Need(runtime.StartsWith(task+"\\",StringComparison.OrdinalIgnoreCase)&&boot.StartsWith(task+"\\",StringComparison.OrdinalIgnoreCase)&&!SamePath(runtime,boot)&&!runtime.StartsWith(boot+"\\",StringComparison.OrdinalIgnoreCase)&&!boot.StartsWith(runtime+"\\",StringComparison.OrdinalIgnoreCase),"Bootstrap and queue roots must be separate explicit children of the owned task root.");Need(SamePath(boot,LocalAbsolute(own)),"Bootstrap assembly/launcher is outside its exact configured directory.");Need(((string)value["editor_executable"]).StartsWith(install+"\\",StringComparison.OrdinalIgnoreCase)&&((string)value["addins_directory"]).StartsWith(install+"\\",StringComparison.OrdinalIgnoreCase)&&SamePath(Path.GetDirectoryName((string)value["addins_ini_file"]),(string)value["addins_directory"]),"Configured editor/Addins locations escape the explicit installation root.");foreach(string key in new[]{"task_root","runtime_root","bootstrap_root","install_root","addins_directory"})Ancestors((string)value[key]);string contract=Regular((string)value["loader_contract_file"]);Need(Hash(contract)==(string)value["loader_contract_sha256"],"Native loader capability evidence changed.");var capability=new JavaScriptSerializer{MaxJsonLength=int.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(File.ReadAllText(contract,Encoding.UTF8));CheckCapability(value,capability);string editor=Regular((string)value["editor_executable"]);Need(Hash(editor)==(string)value["editor_sha256"],"Installed engineering executable changed from the explicit capability binding.");string startup=(string)value["startup_registry_path"];Need(startup.StartsWith("Software\\",StringComparison.OrdinalIgnoreCase)&&startup.IndexOf('\0')<0,"Use the explicitly observed existing per-user Software registry key.");heldConfiguration=stream;data=value;}catch{stream.Dispose();throw;}}}
  internal static void Check(){Load();Ancestors(RuntimeRoot);Need(heldConfiguration!=null,"Bootstrap binding was not retained.");}
  internal static void CheckHost(){Check();Need(IntPtr.Size==4,"The native engineering bootstrap requires x86.");using(var process=Process.GetCurrentProcess())Need(SamePath(process.MainModule.FileName,EditorFile),"Native callback is outside the configured engineering executable.");}
 }
}
