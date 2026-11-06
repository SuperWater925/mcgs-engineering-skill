// Own setup UI and narrowly scoped vendor-installer window helper.
// No vendor files, global SendKeys, foreground forcing, remote memory or killing.
using System;
using System.Collections;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class InstallerChoice {
 static readonly JavaScriptSerializer Json=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue,RecursionLimit=256};
 delegate bool EnumWindowProc(IntPtr window,IntPtr unused);
 [DllImport("user32.dll")]static extern bool EnumWindows(EnumWindowProc callback,IntPtr unused);
 [DllImport("user32.dll")]static extern bool EnumChildWindows(IntPtr parent,EnumWindowProc callback,IntPtr unused);
 [DllImport("user32.dll")]static extern uint GetWindowThreadProcessId(IntPtr window,out uint pid);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern int GetClassNameW(IntPtr window,StringBuilder name,int size);
 [DllImport("user32.dll",EntryPoint="GetWindowLongW")]static extern int GetWindowLong32(IntPtr window,int index);
 [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW")]static extern IntPtr GetWindowLong64(IntPtr window,int index);
 [DllImport("user32.dll")]static extern int GetDlgCtrlID(IntPtr window);
 [DllImport("user32.dll")]static extern bool IsWindowVisible(IntPtr window);
 [DllImport("user32.dll")]static extern bool IsWindowEnabled(IntPtr window);
 [DllImport("user32.dll")]static extern IntPtr GetParent(IntPtr window);
 [DllImport("user32.dll",SetLastError=true)]static extern bool PostMessageW(IntPtr window,uint message,IntPtr wparam,IntPtr lparam);
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true,EntryPoint="SendMessageTimeoutW")]
 static extern IntPtr SendText(IntPtr window,uint message,UIntPtr wparam,StringBuilder text,uint flags,uint milliseconds,out UIntPtr result);
 [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true,EntryPoint="SendMessageTimeoutW")]
 static extern IntPtr SetText(IntPtr window,uint message,UIntPtr wparam,string text,uint flags,uint milliseconds,out UIntPtr result);
 [DllImport("user32.dll",SetLastError=true,EntryPoint="SendMessageTimeoutW")]
 static extern IntPtr SendNumber(IntPtr window,uint message,UIntPtr wparam,IntPtr lparam,uint flags,uint milliseconds,out UIntPtr result);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr OpenJobObjectW(uint access,bool inherit,string name);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool QueryInformationJobObject(IntPtr job,int info,IntPtr data,uint size,out uint returned);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool QueryFullProcessImageNameW(IntPtr process,uint flags,StringBuilder file,ref int size);

 static void Need(bool condition,string message){if(!condition)throw new InvalidOperationException(message);}
 static string S(Dictionary<string,object> map,string key){object value;Need(map.TryGetValue(key,out value)&&value is string,"Expected text field: "+key);return(string)value;}
 static string Optional(Dictionary<string,object> map,string key,string fallback){object value;return map.TryGetValue(key,out value)&&value!=null?Convert.ToString(value,CultureInfo.InvariantCulture):fallback;}
 static Dictionary<string,object> Map(object value){var result=value as Dictionary<string,object>;Need(result!=null,"Expected JSON object.");return result;}
 static Dictionary<string,object> Read(string file){return Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.GetFullPath(file),Encoding.UTF8));}
 static string Hash(string file){using(var stream=File.OpenRead(file))using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();}
 static string Full(string value){Need(Path.IsPathRooted(value),"Use an absolute path.");string full=Path.GetFullPath(value),root=Path.GetPathRoot(full);return full.Length>root.Length?full.TrimEnd('\\','/'):root;}
 static bool Within(string path,string root){string a=Full(path),b=Full(root);return a.Equals(b,StringComparison.OrdinalIgnoreCase)||a.StartsWith(b+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);}
 static string Hex(IntPtr value){return "0x"+unchecked((ulong)value.ToInt64()).ToString("x",CultureInfo.InvariantCulture);}
 static IntPtr Handle(string value){long number=value.StartsWith("0x",StringComparison.OrdinalIgnoreCase)?Int64.Parse(value.Substring(2),NumberStyles.HexNumber,CultureInfo.InvariantCulture):Int64.Parse(value,CultureInfo.InvariantCulture);return new IntPtr(number);}
 static string Class(IntPtr window){var value=new StringBuilder(512);Need(GetClassNameW(window,value,value.Capacity)>0,"Window class could not be read.");return value.ToString();}
 static long Style(IntPtr window){return IntPtr.Size==8?GetWindowLong64(window,-16).ToInt64():GetWindowLong32(window,-16);}
 static UIntPtr Number(IntPtr window,uint message){UIntPtr result;Need(SendNumber(window,message,UIntPtr.Zero,IntPtr.Zero,2,2000,out result)!=IntPtr.Zero,"Window message did not return; inspect current state instead of retrying.");return result;}
 static string Text(IntPtr window){ulong count=Number(window,0x000e).ToUInt64();Need(count<Int32.MaxValue,"Window text exceeds the CLR string representation.");var text=new StringBuilder((int)count+1);UIntPtr result;Need(SendText(window,0x000d,new UIntPtr((uint)text.Capacity),text,2,2000,out result)!=IntPtr.Zero,"Window text read did not return.");return text.ToString();}
 static bool PathText(string value){return Regex.IsMatch(value??"",@"\A(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+)");}
 static string SafeText(IntPtr window,string cls){
  if((cls.Equals("Edit",StringComparison.OrdinalIgnoreCase)||cls.IndexOf("RichEdit",StringComparison.OrdinalIgnoreCase)>=0)&&(Style(window)&0x20)!=0)return "<password field omitted>";
  string value=Text(window);
  if((cls.Equals("Edit",StringComparison.OrdinalIgnoreCase)||cls.Equals("ComboBox",StringComparison.OrdinalIgnoreCase))&&!PathText(value))return "<edit value omitted>";
  return Regex.Replace(value,@"(?im)((?:密码|password|序列号|serial(?:\s+number)?|license\s+key|注册码|密钥)\s*[:：=]\s*)\S+","$1<value omitted>");
 }
 static string ProcessImage(Process process){var file=new StringBuilder(32768);int size=file.Capacity;Need(QueryFullProcessImageNameW(process.Handle,0,file,ref size),"Cannot read selected process image: "+Marshal.GetLastWin32Error());return Full(file.ToString());}
 static HashSet<int> JobPids(Dictionary<string,object> state){
  Need(Optional(state,"schema","")=="mcgs-installer-operation/v1"&&Object.Equals(state["vendor_started"],true),"No started installer operation was selected.");
  string name=S(state,"job_name");Need(name.StartsWith(@"Local\McgsTurnkeyInstall_",StringComparison.Ordinal),"Unexpected installer job name.");
  IntPtr job=OpenJobObjectW(4,false,name);Need(job!=IntPtr.Zero,"Installer job is no longer available; read operation status.");
  try{int count=8;while(true){int length=checked(8+count*IntPtr.Size);IntPtr data=Marshal.AllocHGlobal(length);try{uint returned;if(QueryInformationJobObject(job,3,data,(uint)length,out returned)){int actual=Marshal.ReadInt32(data,4);Need(actual>=0&&actual<=count,"Installer job process count changed.");var result=new HashSet<int>();for(int i=0;i<actual;i++)result.Add(checked((int)(IntPtr.Size==8?Marshal.ReadInt64(data,8+i*8):Marshal.ReadInt32(data,8+i*4))));return result;}int error=Marshal.GetLastWin32Error();Need(error==234,"Cannot query installer job: "+error);count=Math.Max(checked(count*2),Marshal.ReadInt32(data,0));}finally{Marshal.FreeHGlobal(data);}}}finally{CloseHandle(job);}
 }
 static Dictionary<string,object> CheckedState(Dictionary<string,object> request,out HashSet<int> pids){
  var state=Read(S(request,"state_file"));var plan=Read(S(state,"plan_file"));
  Need(Hash(S(state,"plan_file"))==S(state,"plan_sha256")&&S(plan,"plan_id")==S(state,"plan_id"),"Installer operation belongs to another or changed plan.");
  Need(Optional(plan,"schema","")=="mcgs-reinstall-plan/v1","Unexpected installation plan.");
  string choice=S(plan,"choice");Need(choice=="reinstall"||choice=="install","No user-selected installation operation.");
  pids=JobPids(state);return state;
 }
 static Process CheckProcess(int pid,string creation,HashSet<int> allowed){Need(allowed.Contains(pid),"Selected process is outside the installer job.");var process=Process.GetProcessById(pid);Need(!process.HasExited&&process.StartTime.ToFileTimeUtc().ToString(CultureInfo.InvariantCulture)==creation,"Selected installer process identity changed.");return process;}
 static IntPtr CheckWindow(Dictionary<string,object> request,HashSet<int> allowed){
  int pid=Convert.ToInt32(request["pid"],CultureInfo.InvariantCulture);using(var process=CheckProcess(pid,S(request,"creation_filetime"),allowed)){
   IntPtr window=Handle(S(request,"hwnd"));uint owner;Need(GetWindowThreadProcessId(window,out owner)>0&&owner==(uint)pid,"Window is not owned by the selected installer.");
   Need(Class(window)==S(request,"expected_class"),"Window class changed since inspection.");
   object id;if(request.TryGetValue("expected_control_id",out id))Need(GetDlgCtrlID(window)==Convert.ToInt32(id,CultureInfo.InvariantCulture),"Control identity changed.");
   object parent;if(request.TryGetValue("expected_parent_text",out parent))Need(Text(GetParent(window))==Convert.ToString(parent,CultureInfo.InvariantCulture),"Parent window text changed.");
   Need(IsWindowEnabled(window),"Selected control is disabled.");return window;
  }
 }
 static Dictionary<string,object> Describe(IntPtr window){uint pid;GetWindowThreadProcessId(window,out pid);string cls=Class(window);return new Dictionary<string,object>{{"hwnd",Hex(window)},{"pid",pid},{"class",cls},{"text",SafeText(window,cls)},{"control_id",GetDlgCtrlID(window)},{"parent",Hex(GetParent(window))},{"visible",IsWindowVisible(window)},{"enabled",IsWindowEnabled(window)}};}
 static Dictionary<string,object> Inspect(Dictionary<string,object> request){
  HashSet<int> pids;var state=CheckedState(request,out pids);var windows=new List<object>();var processRows=new List<object>();
  foreach(int pid in pids)try{using(var process=Process.GetProcessById(pid))processRows.Add(new Dictionary<string,object>{{"pid",pid},{"creation_filetime",process.StartTime.ToFileTimeUtc().ToString(CultureInfo.InvariantCulture)},{"executable",ProcessImage(process)}});}catch(ArgumentException){}
  EnumWindows(delegate(IntPtr window,IntPtr unused){uint pid;GetWindowThreadProcessId(window,out pid);if(!pids.Contains((int)pid))return true;var top=Describe(window);var children=new List<object>();EnumChildWindows(window,delegate(IntPtr child,IntPtr ignored){uint owner;GetWindowThreadProcessId(child,out owner);if(pids.Contains((int)owner))children.Add(Describe(child));return true;},IntPtr.Zero);top["children"]=children;windows.Add(top);return true;},IntPtr.Zero);
  return new Dictionary<string,object>{{"ok",true},{"operation","inspect"},{"job_name",state["job_name"]},{"processes",processRows},{"windows",windows},{"write_attempted",false},{"foreground_changed",false}};
 }
 static Dictionary<string,object> Click(Dictionary<string,object> request){
  HashSet<int> pids;CheckedState(request,out pids);IntPtr window=CheckWindow(request,pids);Need(Class(window)=="Button","Only a standard installer button can be clicked.");
  Need(Text(window)==S(request,"expected_text"),"Button text changed since inspection.");
  object desired;if(request.TryGetValue("desired_checked",out desired)){
   Need(desired is bool,"desired_checked must be Boolean.");bool current=Number(window,0x00f0).ToUInt64()==1;
   if(current==(bool)desired)return new Dictionary<string,object>{{"ok",true},{"operation","click"},{"already_in_desired_state",true},{"write_attempted",false}};
  }
  UIntPtr value;bool returned=SendNumber(window,0x00f5,UIntPtr.Zero,IntPtr.Zero,2,2000,out value)!=IntPtr.Zero;
  return new Dictionary<string,object>{{"ok",returned},{"operation","click"},{"write_attempted",true},{"delivery_returned",returned},{"outcome_unknown",!returned},{"automatic_retry",false},{"installer_completion_claimed",false},{"foreground_changed",false}};
 }
 static Dictionary<string,object> SetDirectory(Dictionary<string,object> request){
  HashSet<int> pids;var state=CheckedState(request,out pids);var plan=Read(S(state,"plan_file"));string target=Full(S(plan,"original_install_root"));
  IntPtr window=CheckWindow(request,pids);string cls=Class(window);Need(cls=="Edit"||cls=="ComboBox","Directory control must be an inspected standard edit or combo.");Need((Style(window)&0x20)==0,"Password fields cannot be changed by the directory helper.");
  string before=Text(window);Need(PathText(before),"Selected control does not currently contain an absolute directory.");
  if(Full(before).Equals(target,StringComparison.OrdinalIgnoreCase))return new Dictionary<string,object>{{"ok",true},{"operation","set-directory"},{"already_at_original_directory",true},{"write_attempted",false}};
  Need(before==S(request,"expected_text"),"Directory field changed since inspection.");
  UIntPtr result;bool returned=SetText(window,0x000c,UIntPtr.Zero,target,2,2000,out result)!=IntPtr.Zero;
  bool matches=returned&&Full(Text(window)).Equals(target,StringComparison.OrdinalIgnoreCase);
  return new Dictionary<string,object>{{"ok",matches},{"operation","set-directory"},{"write_attempted",true},{"directory",target},{"readback_matches",matches},{"outcome_unknown",!returned},{"automatic_retry",false},{"foreground_changed",false}};
 }
 static Dictionary<string,object> CloseEditor(Dictionary<string,object> request){
  var plan=Read(S(request,"plan_file"));Need(S(plan,"schema")=="mcgs-reinstall-plan/v1"&&S(plan,"choice")=="reinstall","Only the selected reinstall can request normal editor close.");
  string root=Full(S(plan,"original_install_root"));Need(!root.Equals(Path.GetPathRoot(root),StringComparison.OrdinalIgnoreCase),"A whole drive is not an editor root.");
  int pid=Convert.ToInt32(request["pid"],CultureInfo.InvariantCulture);using(var process=Process.GetProcessById(pid)){
   Need(process.StartTime.ToFileTimeUtc().ToString(CultureInfo.InvariantCulture)==S(request,"creation_filetime"),"Editor process identity changed.");Need(Within(ProcessImage(process),root),"Selected editor is outside the original installation.");
   IntPtr window=process.MainWindowHandle;Need(window!=IntPtr.Zero,"Selected process has no normal main window; use its original shutdown interface.");uint owner;Need(GetWindowThreadProcessId(window,out owner)>0&&owner==(uint)pid,"Main window ownership differs.");bool sent=PostMessageW(window,0x0010,IntPtr.Zero,IntPtr.Zero);
   return new Dictionary<string,object>{{"ok",sent},{"operation","close-editor"},{"normal_close_requested",sent},{"process_exit_verified",false},{"force_terminate",false},{"unsaved_prompt_handoff","AI must preserve unsaved work through the original prompt; do not assume the process exited."},{"write_attempted",sent},{"automatic_retry",false}};
  }
 }
 static Form BaseForm(string title,string message){
  var form=new Form{Text=title,StartPosition=FormStartPosition.CenterScreen,ClientSize=new Size(720,285),FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false,Font=new Font("Microsoft YaHei UI",10F)};
  form.Controls.Add(new Label{Text=message,AutoSize=false,Location=new Point(22,18),Size=new Size(676,175)});return form;
 }
 static Dictionary<string,object> Choose(Dictionary<string,object> request){
  bool fresh=Object.Equals(request.ContainsKey("not_installed")?request["not_installed"]:false,true);
  string family=Optional(request,"family","MCGS"),installed=Optional(request,"installed_version","未知"),bundled=Optional(request,"bundle_version","未知"),root=Optional(request,"install_root","");
  string text=fresh?family+" 尚未安装。\r\n随包版本："+bundled+"\r\n安装目录："+root:family+" 版本不一致。\r\n本机版本："+installed+"\r\n随包版本："+bundled+"\r\n当前目录："+root;
  text+="\r\n\r\n继续当前版本会自动分析本机程序。重装会先备份，再调用原厂卸载和安装向导，保留原目录。";
  string choice="cancel";using(var form=BaseForm("昆仑通态版本选择",text)){
   var current=new Button{Text="继续当前版本并自动适配",Location=new Point(22,215),Size=new Size(225,45),Enabled=!fresh};
   var reinstall=new Button{Text=fresh?"安装随包版本":"卸载后在原目录安装随包版本",Location=new Point(260,215),Size=new Size(275,45)};
   var cancel=new Button{Text="取消",Location=new Point(550,215),Size=new Size(145,45)};
   current.Click+=delegate{choice="current";form.Close();};reinstall.Click+=delegate{choice=fresh?"install":"reinstall";form.Close();};cancel.Click+=delegate{form.Close();};
   form.Controls.AddRange(new Control[]{current,reinstall,cancel});form.AcceptButton=fresh?cancel:current;form.CancelButton=cancel;form.ShowDialog();
  }
  return new Dictionary<string,object>{{"ok",true},{"choice",choice},{"family",family},{"installed_version",installed},{"bundle_version",bundled},{"install_root",root},{"software_changed",false}};
 }
 static Dictionary<string,object> SelectInstallation(Dictionary<string,object> request){
  object raw;Need(request.TryGetValue("installations",out raw),"No installations were supplied.");var list=new List<Dictionary<string,object>>();foreach(object item in(IEnumerable)raw)list.Add(Map(item));Need(list.Count>0,"No installation candidates.");string selected=null;
  using(var form=BaseForm("选择昆仑通态安装目录","发现多个安装位置，请选择本次要使用的这一套软件。其它安装不会被操作。")){
   var box=new ListBox{Location=new Point(22,70),Size=new Size(676,125)};foreach(var item in list)box.Items.Add(Optional(item,"family","MCGS")+"  "+Optional(item,"file_version","未知")+"  "+S(item,"install_root"));
   var use=new Button{Text="使用选中的安装",Location=new Point(295,215),Size=new Size(240,45),Enabled=false};var cancel=new Button{Text="取消",Location=new Point(550,215),Size=new Size(145,45)};
   box.SelectedIndexChanged+=delegate{use.Enabled=box.SelectedIndex>=0;};use.Click+=delegate{selected=S(list[box.SelectedIndex],"installation_id");form.Close();};cancel.Click+=delegate{form.Close();};
   form.Controls.AddRange(new Control[]{box,use,cancel});form.CancelButton=cancel;form.ShowDialog();
  }
  return new Dictionary<string,object>{{"ok",true},{"choice",selected==null?"cancel":"selected"},{"installation_id",selected},{"software_changed",false}};
 }
 static Dictionary<string,object> Run(string command,Dictionary<string,object> request){switch(command){case "choose":return Choose(request);case "select-installation":return SelectInstallation(request);case "inspect":return Inspect(request);case "click":return Click(request);case "set-directory":return SetDirectory(request);case "close-editor":return CloseEditor(request);default:throw new InvalidOperationException("Unknown installation helper command.");}}
 [STAThread]static int Main(string[] args){
  Console.OutputEncoding=new UTF8Encoding(false);
  string output=null,command=null,input=null;bool claimed=false;
  try{
   Need(args.Length>=3,"Use COMMAND --input REQUEST.json [--out NEW_RECEIPT.json].");command=args[0];for(int i=1;i<args.Length;i+=2){Need(i+1<args.Length,"Expected option value.");if(args[i]=="--input")input=args[i+1];else if(args[i]=="--out")output=args[i+1];else throw new InvalidOperationException("Unknown helper option.");}
   Need(input!=null,"An explicit request file is required.");bool writes=command=="click"||command=="set-directory"||command=="close-editor";
   if(writes){Need(output!=null,"A new receipt path is required for an at-most-once installer action.");output=Path.GetFullPath(output);Directory.CreateDirectory(Path.GetDirectoryName(output));
    if(File.Exists(output+".claim")){var previous=Read(output+".claim");Need(S(previous,"command")==command&&S(previous,"input_sha256")==Hash(input),"Existing action receipt belongs to another request; preserve it.");claimed=true;Need(File.Exists(output),"Previous action has an unknown result; inspect actual state instead of retrying.");var prior=Read(output);Console.WriteLine(Json.Serialize(prior));return Object.Equals(prior["ok"],true)?0:1;}
    Need(!File.Exists(output),"Receipt exists without its action claim; preserve it.");
    using(var file=new FileStream(output+".claim",FileMode.CreateNew,FileAccess.Write,FileShare.None)){byte[] bytes=Encoding.UTF8.GetBytes(Json.Serialize(new Dictionary<string,object>{{"command",command},{"input_sha256",Hash(input)},{"created_utc",DateTime.UtcNow.ToString("o",CultureInfo.InvariantCulture)}}));file.Write(bytes,0,bytes.Length);file.Flush(true);}claimed=true;
   }else if(output!=null)Need(!File.Exists(output),"Output already exists; preserve it.");
   Application.EnableVisualStyles();var result=Run(command,Read(input));result["automatic_retry"]=false;string json=Json.Serialize(result);if(output!=null)using(var file=new FileStream(output,FileMode.CreateNew,FileAccess.Write,FileShare.Read)){byte[] bytes=Encoding.UTF8.GetBytes(json);file.Write(bytes,0,bytes.Length);file.Flush(true);}Console.WriteLine(json);return Object.Equals(result["ok"],true)?0:1;
  }catch(Exception error){string json=Json.Serialize(new Dictionary<string,object>{{"ok",false},{"error",error.Message},{"operation",command},{"action_claimed",claimed},{"outcome_unknown",claimed},{"automatic_retry",false},{"installer_completion_claimed",false}});if(output!=null&&claimed&&!File.Exists(output))try{File.WriteAllText(output,json,new UTF8Encoding(false));}catch{}Console.WriteLine(json);return 1;}
 }
}
