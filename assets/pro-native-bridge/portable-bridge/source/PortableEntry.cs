using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;using System.IO.MemoryMappedFiles;using System.Runtime.InteropServices;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 [ComVisible(true),Guid("D0A82013-C890-46F2-93B3-C9C3CDA53685"),InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
 public interface IPortableAttach { [DispId(1)] int Attach([MarshalAs(UnmanagedType.BStr)]string config,[MarshalAs(UnmanagedType.BStr)]string sha256); }
 [ComVisible(true),Guid("C81CD5F3-FD35-46C3-911F-304F48417645"),ClassInterface(ClassInterfaceType.None),ComDefaultInterface(typeof(IPortableAttach))]
 public sealed class PortableAttachObject:IPortableAttach {
  static MemoryMappedFile discovery;
  [DllImport("ole32.dll")]static extern int CoGetApartmentType(out int apartment,out int qualifier);
  public int Attach(string config,string sha256){
   try {
    BootstrapLayout.Initialize(config,sha256);BootstrapLayout.CheckHost();
    int apartment,qualifier;int hr=CoGetApartmentType(out apartment,out qualifier);
    if(hr<0||(apartment!=0&&apartment!=3))throw new InvalidOperationException("Portable attach must enter the selected UI STA.");
    BootstrapLayout.CheckAttachThread();
    BootstrapRuntime.EnsureUiPump("PortableThreadSpecificAttach",0,null);
    using(var process=Process.GetCurrentProcess()){
     if(discovery==null){
      string name=@"Local\McgsPortableBridge_v6_"+process.Id+"_"+process.StartTime.ToFileTimeUtc().ToString("X16");
      discovery=MemoryMappedFile.CreateNew(name,262144,MemoryMappedFileAccess.ReadWrite);
      var fields=new Dictionary<string,object>{{"schema",1},{"release","mcgs-portable-bridge/v6"},{"process_id",process.Id},{"creation_filetime",process.StartTime.ToFileTimeUtc()},{"ui_thread_id",BootstrapRuntime.UiThreadId},{"bootstrap_config",BootstrapLayout.ConfigurationFile},{"bootstrap_scope_sha256",BootstrapLayout.ConfigurationSha256},{"runtime_root",BootstrapLayout.RuntimeRoot},{"bootstrap_root",BootstrapLayout.BootstrapRoot}};
      byte[] bytes=Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(fields));
      using(var view=discovery.CreateViewAccessor()){view.WriteArray(4,bytes,0,bytes.Length);view.Write(0,bytes.Length);view.Flush();}
     }
    }
    BootstrapRuntime.RecordEvent("portable_attach_completed",new Dictionary<string,object>{{"release","mcgs-portable-bridge/v6"},{"native_thread_id",BootstrapRuntime.UiThreadId}});return 0;
   }catch(Exception error){
    try{BootstrapRuntime.RecordError("portable_attach",error);}catch{}
    // Initialization failures can precede the runtime log. Preserve this exact
    // attempt's diagnostic beside its explicit configuration without replay.
    try{byte[] bytes=Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(new Dictionary<string,object>{{"schema",1},{"error",error.Message},{"error_type",error.GetType().FullName},{"stack",error.StackTrace},{"inner_error",error.InnerException==null?null:error.InnerException.Message},{"automatic_retry",false}}));using(var file=new FileStream(config+".attach-error.json",FileMode.CreateNew,FileAccess.Write,FileShare.Read)){file.Write(bytes,0,bytes.Length);file.Flush(true);}}catch{}
    return 1;
   }
  }
 }
}
