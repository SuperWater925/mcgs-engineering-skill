using System;using System.Collections.Generic;using System.Diagnostics;using System.Globalization;using System.IO;using System.Reflection;using System.Runtime.InteropServices;using System.Security.Cryptography;using System.Text;using System.Threading;using System.Web.Script.Serialization;using Microsoft.Win32;
static class HotAttachClient {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr LoadLibraryW(string path);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi,SetLastError=true)]static extern IntPtr GetProcAddress(IntPtr module,string name);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool FreeLibrary(IntPtr module);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool IsWow64Process(IntPtr process,out bool wow64);
 [DllImport("user32.dll",SetLastError=true)]static extern IntPtr SetWindowsHookExW(int kind,IntPtr function,IntPtr module,uint thread);
 [DllImport("user32.dll",SetLastError=true)]static extern bool UnhookWindowsHookEx(IntPtr hook);
 [DllImport("user32.dll",SetLastError=true)]static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
 [DllImport("user32.dll",SetLastError=true)]static extern bool PostThreadMessageW(uint thread,uint message,IntPtr w,IntPtr l);
 static JavaScriptSerializer J=new JavaScriptSerializer{MaxJsonLength=int.MaxValue,RecursionLimit=256};
 static void Need(bool b,string s){if(!b)throw new InvalidOperationException(s);}
 static string Hash(string f){using(var a=SHA256.Create())using(var s=File.OpenRead(f))return BitConverter.ToString(a.ComputeHash(s)).Replace("-","").ToLowerInvariant();}
 static string S(Dictionary<string,object>d,string k){return Convert.ToString(d[k]);}
 static string Regular(string p){string f=Path.GetFullPath(p);Need(File.Exists(f),"Missing regular input: "+f);return f;}
 static string Key(Dictionary<string,object> c){return @"Software\Classes\CLSID\{"+S(c,"class_guid")+"}";}
 // Run has already verified this own DLL's configured SHA. Use the CLR's COM
 // registration representation, matching RegAsm even for non-ASCII paths.
 static Dictionary<string,string> Values(Dictionary<string,object>c){return new Dictionary<string,string>{{"","mscoree.dll"},{"ThreadingModel","Both"},{"Class","McgsInternalBridge.HotAttachObject"},{"Assembly",S(c,"bootstrap_assembly_full_name")},{"RuntimeVersion","v4.0.30319"},{"CodeBase",AssemblyName.GetAssemblyName(S(c,"bootstrap_dll")).CodeBase}};}
 static string LegacyCodeBase(Dictionary<string,object>c){return new Uri(S(c,"bootstrap_dll")).AbsoluteUri;}
 static bool RegistrationValueMatches(object value,RegistryValueKind kind,string expected,string legacy,bool allowLegacy){return kind==RegistryValueKind.String&&value is string&&((string)value==expected||(allowLegacy&&legacy!=null&&(string)value==legacy));}
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
 [DllImport("advapi32.dll",SetLastError=true)]static extern bool GetTokenInformation(IntPtr token,int kind,IntPtr data,uint size,out uint needed);
 [DllImport("advapi32.dll")]static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
 [DllImport("advapi32.dll")]static extern IntPtr GetSidSubAuthority(IntPtr sid,uint index);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr h);
 static RegistryHive AutoHive(Process p){IntPtr token;Need(OpenProcessToken(p.Handle,8,out token),"Cannot read selected host token.");try{uint needed;GetTokenInformation(token,25,IntPtr.Zero,0,out needed);Need(needed>0&&needed<=int.MaxValue,"Integrity token size exceeds the CLR allocation representation.");IntPtr data=Marshal.AllocHGlobal((int)needed);try{Need(GetTokenInformation(token,25,data,needed,out needed),"Cannot read selected host integrity.");IntPtr sid=Marshal.ReadIntPtr(data);byte n=Marshal.ReadByte(GetSidSubAuthorityCount(sid));Need(n>0,"Integrity SID is empty.");int rid=Marshal.ReadInt32(GetSidSubAuthority(sid,(uint)n-1));return rid>0x2000?RegistryHive.LocalMachine:RegistryHive.CurrentUser;}finally{Marshal.FreeHGlobal(data);}}finally{CloseHandle(token);}}
 static void VerifyRegistration(RegistryKey r,Dictionary<string,object> c){VerifyRegistration(r,c,false);}
 static bool VerifyRegistration(RegistryKey r,Dictionary<string,object> c,bool allowLegacy){
  Need(r!=null,"Private CLSID ownership differs.");
  Need(r.GetSubKeyNames().Length==1&&r.GetSubKeyNames()[0]=="InprocServer32"&&r.GetValueNames().Length==2,"Private CLSID has unplanned values/subkeys.");
  Need(RegistrationValueMatches(r.GetValue("HotAttachScopeSha256"),r.GetValueKind("HotAttachScopeSha256"),S(c,"bootstrap_scope_sha256"),null,false)&&RegistrationValueMatches(r.GetValue(""),r.GetValueKind(""),"McgsInternalBridge.HotAttachObject",null,false),"Private CLSID ownership differs.");
  var values=Values(c);string legacy=allowLegacy?LegacyCodeBase(c):null;bool migration=false;
  using(var server=r.OpenSubKey("InprocServer32")){
   Need(server!=null&&server.GetSubKeyNames().Length==1&&server.GetSubKeyNames()[0]=="1.0.0.0"&&server.GetValueNames().Length==values.Count,"Private server has unplanned content.");
   foreach(var pair in values){object value=server.GetValue(pair.Key);Need(RegistrationValueMatches(value,server.GetValueKind(pair.Key),pair.Value,pair.Key=="CodeBase"?legacy:null,allowLegacy),"Private COM registration changed.");if(pair.Key=="CodeBase"&&(string)value!=pair.Value)migration=true;}
   using(var version=server.OpenSubKey("1.0.0.0")){
    Need(version!=null&&version.GetSubKeyNames().Length==0&&version.GetValueNames().Length==4,"Private version registration changed.");
    foreach(string key in new[]{"Class","Assembly","RuntimeVersion","CodeBase"}){object value=version.GetValue(key);Need(RegistrationValueMatches(value,version.GetValueKind(key),values[key],key=="CodeBase"?legacy:null,allowLegacy),"Private version value changed.");if(key=="CodeBase"&&(string)value!=values[key])migration=true;}
   }
  }
  return migration;
 }
 static void Registration(Dictionary<string,object>c,bool remove,RegistryHive hive){
  using(var u=RegistryKey.OpenBaseKey(hive,RegistryView.Registry32)){
   string root=Key(c);bool exists,migration=false;
   using(var current=u.OpenSubKey(root,false)){exists=current!=null;if(exists)migration=VerifyRegistration(current,c,true);else Need(!remove,"Private registration is absent.");}
   if(remove){u.DeleteSubKeyTree(root);return;}
   if(exists){
    if(!migration)return;
    // Only the exact same-owner registration, with all other contents unchanged,
    // may migrate the two historical percent-encoded CodeBase values.
    using(var r=u.OpenSubKey(root,true)){
     VerifyRegistration(r,c,true);string codebase=Values(c)["CodeBase"];
     using(var server=r.OpenSubKey("InprocServer32",true))using(var version=server.OpenSubKey("1.0.0.0",true)){server.SetValue("CodeBase",codebase,RegistryValueKind.String);version.SetValue("CodeBase",codebase,RegistryValueKind.String);version.Flush();server.Flush();}r.Flush();
    }
   }else using(var r=u.CreateSubKey(root)){
    var values=Values(c);r.SetValue("HotAttachScopeSha256",S(c,"bootstrap_scope_sha256"),RegistryValueKind.String);r.SetValue("","McgsInternalBridge.HotAttachObject",RegistryValueKind.String);
    using(var server=r.CreateSubKey("InprocServer32")){foreach(var pair in values)server.SetValue(pair.Key,pair.Value,RegistryValueKind.String);using(var version=server.CreateSubKey("1.0.0.0"))foreach(string key in new[]{"Class","Assembly","RuntimeVersion","CodeBase"})version.SetValue(key,values[key],RegistryValueKind.String);}r.Flush();
   }
   using(var verify=u.OpenSubKey(root))VerifyRegistration(verify,c);
  }
 }
 static Dictionary<string,object> Run(string[] a){Need(a.Length>=2,"Use --plan|--register|--unregister|--attach|--connect CONFIG [PID UI_THREAD CREATION_FILETIME [EXCLUDED_PID...]].");Need(IntPtr.Size==4,"Use the own x86 client for the x86 hook/host.");string cf=Regular(a[1]);var c=J.Deserialize<Dictionary<string,object>>(File.ReadAllText(cf,Encoding.UTF8));Need(Convert.ToInt32(c["schema"])==1,"Hot attach schema differs.");foreach(var pair in new[]{new[]{"bootstrap_dll","bootstrap_dll_sha256"},new[]{"hook_dll","hook_dll_sha256"},new[]{"editor_executable","editor_sha256"}})Need(Hash(Regular(S(c,pair[0])))==S(c,pair[1]),"Configured own module/editor hash changed: "+pair[0]);Need(Hash(Regular(S(c,"bootstrap_config")))==S(c,"bootstrap_scope_sha256"),"Compiled bootstrap scope changed.");
  if(a[0]=="--register"||a[0]=="--unregister"){RegistryHive hive;using(var selected=a.Length>=3?Process.GetProcessById(Int32.Parse(a[2])):Process.GetCurrentProcess())hive=AutoHive(selected);Registration(c,a[0]=="--unregister",hive);return new Dictionary<string,object>{{"ok",true},{"operation",a[0]},{"registry_hive",hive.ToString()+"/Registry32"},{"own_clsid",S(c,"class_guid")},{"target_process_called",false}};}
  Need(a[0]=="--plan"||a[0]=="--attach"||a[0]=="--connect","Unknown operation.");Need(a.Length>=4,"A specific PID and UI thread are required; global hooks are not supported.");int pid=Int32.Parse(a[2]),tid=Int32.Parse(a[3]);Need(pid>0&&tid>0&&pid!=Process.GetCurrentProcess().Id,"Bad target process/thread.");for(int i=5;i<a.Length;i++)Need(pid!=Int32.Parse(a[i]),"Target PID is explicitly protected/excluded.");
  using(var p=Process.GetProcessById(pid)){p.Refresh();string executable=Regular(p.MainModule.FileName);Need(executable.Equals(Path.GetFullPath(S(c,"editor_executable")),StringComparison.OrdinalIgnoreCase)&&Hash(executable)==S(c,"editor_sha256"),"Target is not the exact explicitly configured host image.");bool found=false;foreach(ProcessThread t in p.Threads)if(t.Id==tid)found=true;Need(found,"Requested UI thread is not owned by the target process.");if(S(c,"host_kind")=="pro"){uint owner;IntPtr main=p.MainWindowHandle;Need(main!=IntPtr.Zero&&GetWindowThreadProcessId(main,out owner)==(uint)tid&&owner==(uint)pid,"Selected Pro thread must own its actual main window; no guessed or worker thread.");}bool wow;Need(IsWow64Process(p.Handle,out wow),"Cannot query target bitness.");Need(!Environment.Is64BitOperatingSystem||wow,"Target is not x86.");RegistryHive selectedHive=AutoHive(p);long creation=p.StartTime.ToFileTimeUtc();var result=new Dictionary<string,object>{{"ok",true},{"operation",a[0]},{"process_id",pid},{"ui_thread_id",tid},{"creation_filetime",creation},{"host_kind",S(c,"host_kind")},{"registry_scope_auto",selectedHive.ToString()+"/Registry32"},{"thread_specific_hook",true},{"global_hook",false},{"remote_thread",false},{"remote_memory_written",false},{"vendor_business_called",false},{"host_attached",false}};if(a[0]=="--plan")return result;
   Need(a.Length>=5&&Int64.Parse(a[4],CultureInfo.InvariantCulture)==creation,"Creation FILETIME is required from the selected target, preventing PID reuse.");string runtime=Path.GetFullPath(S(c,"runtime_root"));string native=Path.Combine(runtime,"hot-attach","native-"+pid+".bin");Directory.CreateDirectory(Path.GetDirectoryName(native));Need(!File.Exists(native),"This target already has a native attach outcome; inspect it and do not replay.");
   if(a[0]=="--connect")Registration(c,false,selectedHive);using(var u=RegistryKey.OpenBaseKey(selectedHive,RegistryView.Registry32))using(var r=u.OpenSubKey(Key(c)))VerifyRegistration(r,c);
   bool fresh;using(var ready=new EventWaitHandle(false,EventResetMode.ManualReset,S(c,"event_prefix")+pid,out fresh)){Need(fresh,"Another attach attempt already owns this exact completion event.");IntPtr module=IntPtr.Zero,hook=IntPtr.Zero;try{module=LoadLibraryW(S(c,"hook_dll"));Need(module!=IntPtr.Zero,"Cannot load own inert hook DLL: "+Marshal.GetLastWin32Error());IntPtr function=GetProcAddress(module,"GetMsgProc");Need(function!=IntPtr.Zero,"Own GetMsgProc export missing.");p.Refresh();Need(!p.HasExited&&p.StartTime.ToFileTimeUtc()==creation,"Target identity changed before attaching the hook.");hook=SetWindowsHookExW(3,function,module,(uint)tid);Need(hook!=IntPtr.Zero,"Thread-specific hook installation failed: "+Marshal.GetLastWin32Error());Need(PostThreadMessageW((uint)tid,0,IntPtr.Zero,IntPtr.Zero),"Cannot wake the existing queue with WM_NULL: "+Marshal.GetLastWin32Error());Need(ready.WaitOne(30000),"Attach outcome pending/unknown after30s; no retry.");Need(File.Exists(native),"Native completion has no persisted result; outcome unknown.");byte[] b=File.ReadAllBytes(native);Need(b.Length==40&&Encoding.ASCII.GetString(b,0,4)=="HAT1"&&BitConverter.ToInt32(b,8)==pid&&BitConverter.ToInt32(b,12)==tid,"Native attach result identity/size differs.");int hr=BitConverter.ToInt32(b,16),type=BitConverter.ToInt32(b,20),value=BitConverter.ToInt32(b,24);result["native_hresult"]="0x"+unchecked((uint)hr).ToString("X8");result["com_result_variant_type"]=type;result["managed_attach_return"]=value;result["native_result_file"]=native;result["ok"]=hr>=0&&type==3&&value==0;result["host_attached"]=result["ok"];return result;
    }finally{if(hook!=IntPtr.Zero){bool removed=UnhookWindowsHookEx(hook);result["thread_hook_removed"]=removed;if(!removed)result["hook_cleanup_win32_error"]=Marshal.GetLastWin32Error();}if(module!=IntPtr.Zero)FreeLibrary(module);}}
  }
 }
 static int Main(string[] args){try{var r=Run(args);Console.WriteLine(J.Serialize(r));return Convert.ToBoolean(r["ok"])?0:1;}catch(Exception e){Console.WriteLine(J.Serialize(new Dictionary<string,object>{{"ok",false},{"error",e.Message},{"automatic_retry",false},{"vendor_business_called",false}}));return 1;}}
}
