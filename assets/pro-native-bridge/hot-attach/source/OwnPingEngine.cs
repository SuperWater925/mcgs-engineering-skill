// Transport-only own host engine. It has no project or vendor business methods.
using System;using System.Collections.Generic;using System.Diagnostics;using System.Runtime.InteropServices;
namespace McgsInternalBridge { public static class EngineEntry {
 [DllImport("kernel32.dll")]static extern int GetCurrentThreadId();
 public static Dictionary<string,object> Dispatch(Dictionary<string,object> request,object datObj,int uiThread){
  if(uiThread!=GetCurrentThreadId()||Convert.ToString(request["op"])!="ping")throw new InvalidOperationException("Own transport proof accepts UI-thread ping only.");
  return new Dictionary<string,object>{{"ok",true},{"op","ping"},{"own_test_host",Process.GetCurrentProcess().ProcessName=="OwnMessageLoopHost"},{"transport_probe_engine",true},{"host_process_image",Process.GetCurrentProcess().MainModule.FileName},{"manufacturer_business_abi_tested",false},{"process_id",Process.GetCurrentProcess().Id},{"ui_thread_id",uiThread},{"datobj_is_null",datObj==null},{"write_attempted",false}};
 }
}}
