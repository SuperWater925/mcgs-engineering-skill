// An own x86 STA message-loop host, not Pro and not a manufacturer ABI emulator.
using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;using System.Runtime.InteropServices;using System.Text;using System.Web.Script.Serialization;using System.Windows.Forms;
static class OwnMessageLoopHost {
 [DllImport("kernel32.dll")]static extern int GetCurrentThreadId();
 [STAThread]static int Main(string[] args){if(args.Length!=1)return 2;string root=Path.GetFullPath(args[0]);Directory.CreateDirectory(root);
  var timer=new Timer();timer.Interval=100;timer.Tick+=delegate{if(File.Exists(Path.Combine(root,"own-host.stop")))Application.ExitThread();};timer.Start();
  var row=new Dictionary<string,object>{{"own_test_host",true},{"is_pro",false},{"process_id",Process.GetCurrentProcess().Id},{"ui_thread_id",GetCurrentThreadId()},{"bits",IntPtr.Size*8},{"creation_filetime",Process.GetCurrentProcess().StartTime.ToFileTimeUtc()},{"native_business_called",false}};
  using(var f=new FileStream(Path.Combine(root,"own-host.ready.json"),FileMode.CreateNew,FileAccess.Write,FileShare.Read)){byte[] b=new UTF8Encoding(false).GetBytes(new JavaScriptSerializer().Serialize(row));f.Write(b,0,b.Length);f.Flush(true);}Application.Run();timer.Dispose();return 0;
 }
}
