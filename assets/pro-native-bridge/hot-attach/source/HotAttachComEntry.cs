using System;using System.Collections.Generic;using System.Diagnostics;using System.Runtime.InteropServices;using System.Threading;
namespace McgsInternalBridge {
 [ComVisible(true),Guid("__HOT_INTERFACE_GUID__"),InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
 public interface IHotAttach { [DispId(1)] int Attach(); }
 [ComVisible(true),Guid("__HOT_CLASS_GUID__"),ClassInterface(ClassInterfaceType.None),ComDefaultInterface(typeof(IHotAttach))]
 public sealed class HotAttachObject:IHotAttach {
  [DllImport("ole32.dll")]static extern int CoGetApartmentType(out int type,out int qualifier);
  public int Attach(){try{BootstrapLayout.CheckHost();int type,qualifier;int hr=CoGetApartmentType(out type,out qualifier);
    if(hr<0||(type!=0&&type!=3))throw new InvalidOperationException("Hot attachment requires the existing UI STA; COM apartment is not changed.");
    BootstrapRuntime.EnsureUiPump("ThreadSpecificHotAttach",0,null);
    BootstrapRuntime.RecordEvent("hot_attach_completed",new Dictionary<string,object>{{"process_id",Process.GetCurrentProcess().Id},{"native_thread_id",BootstrapRuntime.GetCurrentThreadId()},{"existing_com_apartment",type},{"datobj_is_null",true},{"vendor_business_called",false}});return 0;
   }catch(Exception e){BootstrapRuntime.RecordError("hot_attach",e);return 1;}}
 }
}
