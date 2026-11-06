// Own, precompiled x86 transport. No manufacturer APIs, focus changes or compiler.
using System;using System.Collections.Generic;using System.Diagnostics;using System.Globalization;using System.IO;using System.IO.MemoryMappedFiles;using System.Reflection;using System.Runtime.InteropServices;using System.Security.Cryptography;using System.Text;using System.Threading;using System.Web.Script.Serialization;using Microsoft.Win32;
static class PortableClient {
 const string Release="mcgs-portable-bridge/v6",ClassId="C81CD5F3-FD35-46C3-911F-304F48417645",TypeName="McgsInternalBridge.PortableAttachObject";
 static readonly JavaScriptSerializer Json=new JavaScriptSerializer{MaxJsonLength=int.MaxValue,RecursionLimit=256};
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr LoadLibraryW(string name);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi,SetLastError=true)]static extern IntPtr GetProcAddress(IntPtr module,string name);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool FreeLibrary(IntPtr module);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool IsWow64Process(IntPtr process,out bool wow64);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 [DllImport("user32.dll",SetLastError=true)]static extern IntPtr SetWindowsHookExW(int hook,IntPtr callback,IntPtr module,uint thread);
 [DllImport("user32.dll",SetLastError=true)]static extern bool UnhookWindowsHookEx(IntPtr hook);
 [DllImport("user32.dll",SetLastError=true)]static extern bool PostThreadMessageW(uint thread,uint message,IntPtr w,IntPtr l);
 [DllImport("user32.dll",SetLastError=true)]static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool GetTokenInformation(IntPtr token,int kind,IntPtr data,uint size,out uint needed);
 [DllImport("advapi32.dll")]static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
 [DllImport("advapi32.dll")]static extern IntPtr GetSidSubAuthority(IntPtr sid,uint index);
 static void Need(bool okay,string message){if(!okay)throw new InvalidOperationException(message);}
 static string Text(Dictionary<string,object> value,string key){return Convert.ToString(value[key],CultureInfo.InvariantCulture);}
 static string Hash(string file){using(var sha=SHA256.Create())using(var input=File.OpenRead(file))return BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();}
 static string Regular(string file){file=Path.GetFullPath(file);Need(File.Exists(file),"Input file missing: "+file);return file;}
 static Dictionary<string,object> Read(string file){return Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));}
 static void WriteNew(string file,Dictionary<string,object> data){Directory.CreateDirectory(Path.GetDirectoryName(file));byte[] bytes=Encoding.UTF8.GetBytes(Json.Serialize(data)+Environment.NewLine);using(var stream=new FileStream(file,FileMode.CreateNew,FileAccess.Write,FileShare.Read)){stream.Write(bytes,0,bytes.Length);stream.Flush(true);}}
 static RegistryHive Hive(Process process){IntPtr token;Need(OpenProcessToken(process.Handle,8,out token),"Cannot read target integrity token.");try{uint bytes;GetTokenInformation(token,25,IntPtr.Zero,0,out bytes);Need(bytes>0&&bytes<=int.MaxValue,"Invalid integrity token length.");IntPtr memory=Marshal.AllocHGlobal((int)bytes);try{Need(GetTokenInformation(token,25,memory,bytes,out bytes),"Cannot read target integrity.");IntPtr sid=Marshal.ReadIntPtr(memory);byte count=Marshal.ReadByte(GetSidSubAuthorityCount(sid));Need(count>0,"Empty integrity SID.");return Marshal.ReadInt32(GetSidSubAuthority(sid,(uint)count-1))>0x2000?RegistryHive.LocalMachine:RegistryHive.CurrentUser;}finally{Marshal.FreeHGlobal(memory);}}finally{CloseHandle(token);}}
 static string Key {get{return @"Software\Classes\CLSID\{"+ClassId+"}";}}
 static Dictionary<string,string> RegistrationValues(Dictionary<string,object> c){return new Dictionary<string,string>{{"","mscoree.dll"},{"ThreadingModel","Both"},{"Class",TypeName},{"Assembly",Text(c,"bootstrap_assembly_full_name")},{"RuntimeVersion","v4.0.30319"},{"CodeBase",AssemblyName.GetAssemblyName(Text(c,"bootstrap_dll")).CodeBase}};}
 static void VerifyOwned(RegistryKey root,Dictionary<string,object> c,bool exactCodeBase){
  Need(root!=null&&Convert.ToString(root.GetValue("PortableBridgeRelease"))==Release&&Convert.ToString(root.GetValue("PortableBridgeDllSha256"))==Text(c,"bootstrap_dll_sha256")&&Convert.ToString(root.GetValue(""))==TypeName,"Private portable CLSID is owned by different content.");
  Need(root.GetValueNames().Length==3&&root.GetSubKeyNames().Length==1&&root.GetSubKeyNames()[0]=="InprocServer32","Private portable CLSID structure changed.");
  var expected=RegistrationValues(c);using(var server=root.OpenSubKey("InprocServer32")){
   Need(server!=null&&server.GetValueNames().Length==6&&server.GetSubKeyNames().Length==1&&server.GetSubKeyNames()[0]=="1.0.0.0","Private portable server structure changed.");
   foreach(var item in expected)if(item.Key!="CodeBase"||exactCodeBase)Need(server.GetValueKind(item.Key)==RegistryValueKind.String&&Convert.ToString(server.GetValue(item.Key))==item.Value,"Private portable server value changed: "+item.Key);
   using(var version=server.OpenSubKey("1.0.0.0")){Need(version!=null&&version.GetSubKeyNames().Length==0&&version.GetValueNames().Length==4,"Private version structure changed.");foreach(string name in new[]{"Class","Assembly","RuntimeVersion","CodeBase"})if(name!="CodeBase"||exactCodeBase)Need(version.GetValueKind(name)==RegistryValueKind.String&&Convert.ToString(version.GetValue(name))==expected[name],"Private portable version value changed: "+name);}
  }
 }
 static void Register(Dictionary<string,object> c,RegistryHive hive,bool remove){using(var registry=RegistryKey.OpenBaseKey(hive,RegistryView.Registry32)){
  using(var existing=registry.OpenSubKey(Key)){if(existing!=null)VerifyOwned(existing,c,remove);else if(remove)return;}
  if(remove){registry.DeleteSubKeyTree(Key);return;}
  using(var root=registry.CreateSubKey(Key)){
   root.SetValue("",TypeName,RegistryValueKind.String);root.SetValue("PortableBridgeRelease",Release,RegistryValueKind.String);root.SetValue("PortableBridgeDllSha256",Text(c,"bootstrap_dll_sha256"),RegistryValueKind.String);
   var values=RegistrationValues(c);using(var server=root.CreateSubKey("InprocServer32")){foreach(var item in values)server.SetValue(item.Key,item.Value,RegistryValueKind.String);using(var version=server.CreateSubKey("1.0.0.0"))foreach(string name in new[]{"Class","Assembly","RuntimeVersion","CodeBase"})version.SetValue(name,values[name],RegistryValueKind.String);}root.Flush();VerifyOwned(root,c,true);
  }
 }}
 static string Token(int pid,long creation){return pid+"_"+creation.ToString("X16",CultureInfo.InvariantCulture);}
 static Dictionary<string,object> Discovery(int pid,long creation){
  try{using(var map=MemoryMappedFile.OpenExisting(@"Local\McgsPortableBridge_v6_"+Token(pid,creation),MemoryMappedFileRights.Read))using(var view=map.CreateViewAccessor(0,0,MemoryMappedFileAccess.Read)){int length=view.ReadInt32(0);Need(length>0&&length<=262140,"Live portable discovery has invalid length.");byte[] bytes=new byte[length];view.ReadArray(4,bytes,0,length);var d=Json.Deserialize<Dictionary<string,object>>(new UTF8Encoding(false,true).GetString(bytes));Need(Text(d,"release")==Release&&Convert.ToInt32(d["process_id"])==pid&&Convert.ToInt64(d["creation_filetime"])==creation,"Live portable discovery identity differs.");return d;}}
  catch(FileNotFoundException){return null;}
 }
 static Dictionary<string,object> Run(string[] args){
  Need(IntPtr.Size==4,"Use the shipped x86 client.");Need(args.Length>=2,"Use --discover PID CREATION_FILETIME, or --plan|--connect|--status|--unregister CONFIG [PID UI_THREAD CREATION_FILETIME].");
  if(args[0]=="--discover"){
   Need(args.Length==3,"Discovery requires an explicit PID and creation FILETIME.");int selected=Int32.Parse(args[1],CultureInfo.InvariantCulture);long started=Int64.Parse(args[2],CultureInfo.InvariantCulture);
   using(var target=Process.GetProcessById(selected))Need(target.StartTime.ToFileTimeUtc()==started,"Discovery target PID was reused or restarted.");
   var live=Discovery(selected,started);return new Dictionary<string,object>{{"ok",true},{"operation","--discover"},{"host_attached",live!=null},{"existing_bridge",live},{"process_id",selected},{"creation_filetime",started},{"vendor_business_called",false},{"automatic_retry",false}};
  }
  string operation=args[0]=="status"?"--status":args[0];Need(operation=="--plan"||operation=="--connect"||operation=="--status"||operation=="--unregister","Unknown portable bridge operation.");
  string configFile=Regular(args[1]);var c=Read(configFile);Need(Convert.ToInt32(c["schema"])==1&&Text(c,"portable_bridge_contract")==Release&&Text(c,"class_guid")==ClassId,"Portable client configuration contract differs.");
  foreach(var pair in new[]{new[]{"bootstrap_dll","bootstrap_dll_sha256"},new[]{"hook_dll","hook_dll_sha256"},new[]{"editor_executable","editor_sha256"},new[]{"bootstrap_config","bootstrap_scope_sha256"}})Need(Hash(Regular(Text(c,pair[0])))==Text(c,pair[1]),"Current preparation input changed: "+pair[0]);
  int pid=args.Length>=3?Int32.Parse(args[2],CultureInfo.InvariantCulture):Convert.ToInt32(c["target_process_id"]),tid=args.Length>=4?Int32.Parse(args[3],CultureInfo.InvariantCulture):Convert.ToInt32(c["target_ui_thread_id"]);long creation=args.Length>=5?Int64.Parse(args[4],CultureInfo.InvariantCulture):Convert.ToInt64(c["target_creation_filetime"]);
  Need(pid>0&&tid>0&&pid!=Process.GetCurrentProcess().Id&&pid==Convert.ToInt32(c["target_process_id"])&&tid==Convert.ToInt32(c["target_ui_thread_id"])&&creation==Convert.ToInt64(c["target_creation_filetime"]),"Explicit target identity differs from this preparation.");
  using(var process=Process.GetProcessById(pid)){
   process.Refresh();Need(process.StartTime.ToFileTimeUtc()==creation,"Target PID was reused or restarted.");string executable=Regular(process.MainModule.FileName);Need(String.Equals(executable,Path.GetFullPath(Text(c,"editor_executable")),StringComparison.OrdinalIgnoreCase)&&Hash(executable)==Text(c,"editor_sha256"),"Target differs from the current explicit executable; this is not a release whitelist.");
   bool owned=false;foreach(ProcessThread thread in process.Threads)if(thread.Id==tid)owned=true;Need(owned,"Selected thread does not belong to this process.");
   if(Text(c,"host_kind")=="pro"){uint owner;IntPtr window=process.MainWindowHandle;Need(window!=IntPtr.Zero&&GetWindowThreadProcessId(window,out owner)==(uint)tid&&owner==(uint)pid,"Selected UI thread must own the Pro main window.");}
   bool wow;Need(IsWow64Process(process.Handle,out wow)&&(!Environment.Is64BitOperatingSystem||wow),"Target must be PE32/I386 for this release's x86 hook.");
   RegistryHive hive=Hive(process);var result=new Dictionary<string,object>{{"ok",true},{"operation",operation},{"portable_bridge_contract",Release},{"process_id",pid},{"ui_thread_id",tid},{"creation_filetime",creation},{"registry_hive",hive.ToString()+"/Registry32"},{"host_attached",false},{"thread_specific_hook",true},{"global_hook",false},{"remote_thread",false},{"remote_memory_written",false},{"windows_focus_changed",false},{"vendor_business_called",false},{"automatic_retry",false}};
   var discovered=Discovery(pid,creation);if(discovered!=null){result["existing_bridge"]=discovered;result["host_attached"]=true;result["connection_reused"]=true;if(operation!="--unregister")return result;}
   string root=Path.GetFullPath(Text(c,"runtime_root")),attempt=Path.Combine(root,"hot-attach","attempt-"+Token(pid,creation)+".json"),outcome=Path.Combine(root,"hot-attach","outcome-"+Token(pid,creation)+".json");
   result["attempt_file"]=attempt;result["outcome_file"]=outcome;
   if(operation=="--plan"||operation=="--status"){result["prior_attempt"]=File.Exists(attempt);result["prior_outcome"]=File.Exists(outcome)?(object)Read(outcome):null;result["requires_outcome_review"]=File.Exists(attempt)&&!File.Exists(outcome);return result;}
   using(var gate=new Mutex(false,@"Local\McgsPortableRegistration_v6")){
    bool acquired=false;try{try{acquired=gate.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}Need(acquired,"Another portable registration/connect is in progress; inspect its outcome before retry.");
     if(operation=="--unregister"){Register(c,hive,true);result["registration_removed"]=true;return result;}
     discovered=Discovery(pid,creation);if(discovered!=null){result["existing_bridge"]=discovered;result["host_attached"]=true;result["connection_reused"]=true;return result;}
     Need(!File.Exists(attempt)&&!File.Exists(outcome),"This exact target has an attach receipt. Inspect status; do not automatically replay failure or unknown outcome.");
     Register(c,hive,false);
     string name=@"Local\McgsPortableAttach_v6_"+Token(pid,creation);bool fresh;
     using(var completed=new EventWaitHandle(false,EventResetMode.ManualReset,name+"_done",out fresh)){
      Need(fresh,"An attach completion event already exists for this target.");
      using(var map=MemoryMappedFile.CreateNew(name,131072,MemoryMappedFileAccess.ReadWrite))using(var view=map.CreateViewAccessor()){
       byte[] path=Encoding.Unicode.GetBytes(Path.GetFullPath(Text(c,"bootstrap_config"))+"\0"),sha=Encoding.Unicode.GetBytes(Text(c,"bootstrap_scope_sha256")+"\0");Need(path.Length<=65536&&sha.Length==130,"Configuration path exceeds the Windows UTF16 path representation.");
       view.WriteArray(0,Encoding.ASCII.GetBytes("MPT6"),0,4);view.Write(4,1);view.Write(8,pid);view.Write(12,tid);view.Write(16,creation);view.Write(28,0);view.WriteArray(256,path,0,path.Length);view.WriteArray(65792,sha,0,sha.Length);view.Flush();
       WriteNew(attempt,new Dictionary<string,object>{{"schema",1},{"state","prepared_before_hook"},{"config_file",configFile},{"config_sha256",Hash(configFile)},{"process_id",pid},{"ui_thread_id",tid},{"creation_filetime",creation},{"utc",DateTime.UtcNow.ToString("o")},{"automatic_retry",false}});
       IntPtr module=IntPtr.Zero,hook=IntPtr.Zero;try{
        module=LoadLibraryW(Text(c,"hook_dll"));Need(module!=IntPtr.Zero,"Cannot load inert own hook: "+Marshal.GetLastWin32Error());IntPtr callback=GetProcAddress(module,"GetMsgProc");Need(callback!=IntPtr.Zero,"Own hook export missing.");process.Refresh();Need(!process.HasExited&&process.StartTime.ToFileTimeUtc()==creation,"Target identity changed before hook attachment.");
        hook=SetWindowsHookExW(3,callback,module,(uint)tid);Need(hook!=IntPtr.Zero,"Thread hook failed: "+Marshal.GetLastWin32Error());Need(PostThreadMessageW((uint)tid,0,IntPtr.Zero,IntPtr.Zero),"Could not post WM_NULL: "+Marshal.GetLastWin32Error());
        bool signaled=completed.WaitOne(30000);int state=view.ReadInt32(28);result["native_mapping_state"]=state;result["completion_signaled"]=signaled;
        if(state==2){int hr=view.ReadInt32(32),type=view.ReadInt32(36),value=view.ReadInt32(40);result["native_hresult"]="0x"+unchecked((uint)hr).ToString("X8");result["com_result_variant_type"]=type;result["managed_attach_return"]=value;result["ok"]=hr>=0&&type==3&&value==0;result["host_attached"]=result["ok"];result["state"]=Convert.ToBoolean(result["ok"])?"attached":"returned_failure";}
        else{result["ok"]=false;result["state"]="unknown";result["error"]="Attach has no final native return; no automatic retry.";}
        discovered=Discovery(pid,creation);if(discovered!=null)result["existing_bridge"]=discovered;
       }catch(Exception error){result["ok"]=false;result["state"]=hook==IntPtr.Zero?"failed_before_hook":"unknown";result["error"]=error.Message;}
       finally{if(hook!=IntPtr.Zero){bool removed=UnhookWindowsHookEx(hook);result["thread_hook_removed"]=removed;if(!removed)result["hook_cleanup_win32_error"]=Marshal.GetLastWin32Error();}if(module!=IntPtr.Zero)FreeLibrary(module);}
       WriteNew(outcome,result);return result;
      }
     }
    }finally{if(acquired)gate.ReleaseMutex();}
   }
  }
 }
 static int Main(string[] args){Console.OutputEncoding=new UTF8Encoding(false);try{var result=Run(args);Console.WriteLine(Json.Serialize(result));return Convert.ToBoolean(result["ok"])?0:1;}catch(Exception error){Console.WriteLine(Json.Serialize(new Dictionary<string,object>{{"ok",false},{"error",error.Message},{"automatic_retry",false},{"vendor_business_called",false}}));return 1;}}
}
