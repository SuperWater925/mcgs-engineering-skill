using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

[assembly: ComVisible(false)]
[assembly: Guid("4D2519E0-CC21-4F82-A19C-1AF9801C64E1")]
[assembly: TypeLibVersion(1,0)]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace McgsInternalBridge {
    [ComVisible(true)]
    [Guid("D0455345-A83C-4B72-A864-EFCE902C3816")]
    [InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
    public interface IAddInObj {
        [DispId(1)] int SvrMenuCommand([In,Out,MarshalAs(UnmanagedType.BStr)]ref string name,[In,Out]ref int query,[In,Out,MarshalAs(UnmanagedType.IDispatch)]ref object data);
        [DispId(2)] int SvrStgySetOperator([In,Out,MarshalAs(UnmanagedType.BStr)]ref string name,[In,Out,MarshalAs(UnmanagedType.BStr)]ref string notes,[In,Out]ref int icon,[In,Out,MarshalAs(UnmanagedType.IDispatch)]ref object data,[In,Out,MarshalAs(UnmanagedType.IDispatch)]ref object saved,[In,Out]ref int query);
        [DispId(3)] int SvrStgyRunOperator([In,Out,MarshalAs(UnmanagedType.IDispatch)]ref object data,[In,Out,MarshalAs(UnmanagedType.IDispatch)]ref object saved);
        [DispId(4)] int SvrCheck([In,Out,MarshalAs(UnmanagedType.IDispatch)]ref object data,[In,Out]ref int flag);
    }

    [ComVisible(true)]
    [Guid("52119C44-5875-4DA6-9F72-E97D2E2182B4")]
    [ProgId("McgsInternalBridge.AddInObj")]
    [ClassInterface(ClassInterfaceType.None)]
    [ComDefaultInterface(typeof(IAddInObj))]
    public sealed class AddInObj : IAddInObj, ICustomQueryInterface {
        readonly NullSafeDispatch.Cache safeDispatch=new NullSafeDispatch.Cache();
        public CustomQueryInterfaceResult GetInterface(ref Guid iid,out IntPtr pointer) {
            pointer=IntPtr.Zero;
            if(iid!=NullSafeDispatch.DispatchIid)return CustomQueryInterfaceResult.NotHandled;
            try{pointer=safeDispatch.Acquire(this,typeof(IAddInObj));return CustomQueryInterfaceResult.Handled;}
            catch{return CustomQueryInterfaceResult.Failed;}
        }
        // Construction is deliberately inert. The native editor's callbacks
        // establish its UI thread and start the queue pump.
        public AddInObj() {}
        public int SvrMenuCommand(ref string name,ref int query,ref object data) {
            try {
                if(query==1)name="Codex Pro 实时工程桥";
                BootstrapRuntime.EnsureUiPump("SvrMenuCommand",query,data);
                return 0;
            }catch(Exception e){BootstrapRuntime.RecordError("SvrMenuCommand",e);return 1;}
        }
        public int SvrStgySetOperator(ref string name,ref string notes,ref int icon,ref object data,ref object saved,ref int query) {
            try {
                if(query==1){name="Codex Pro 内部工程桥";notes="隔离工程测试；内部接口由UI线程执行";icon=0;}
                BootstrapRuntime.EnsureUiPump("SvrStgySetOperator",query,data);
                return 0;
            }catch(Exception e){BootstrapRuntime.RecordError("SvrStgySetOperator",e);return 1;}
        }
        public int SvrStgyRunOperator(ref object data,ref object saved) {
            // This component does not perform runtime/device/strategy work.
            BootstrapRuntime.RecordEvent("runtime_callback_declined",new Dictionary<string,object>());
            return 1;
        }
        public int SvrCheck(ref object data,ref int flag) {return 0;}
    }

    internal static class BootstrapRuntime {
        internal static string RuntimeRoot{get{return BootstrapLayout.RuntimeRoot;}}
        internal static readonly string Inbox=Path.Combine(RuntimeRoot,"inbox");
        internal static readonly string Outbox=Path.Combine(RuntimeRoot,"outbox");
        internal static int UiThreadId;
        static SynchronizationContext uiContext;
        static Thread worker;
        static EventWaitHandle requestSignal;
        static object latestDatObj;
        static DurableQueuePump durablePump;
        static string dispatchWakeSource="start";
        static long eventPumpRuns,pollPumpRuns;
        static readonly object eventLogGate=new object();
        static Mutex runtimeGate;static bool ownsRuntimeGate;
        [DllImport("kernel32.dll")]internal static extern int GetCurrentThreadId();

        internal static void EnsureUiPump(string callback,int query,object datObj) {
            BootstrapLayout.CheckHost();
            if(IntPtr.Size!=4)throw new InvalidOperationException("Bridge requires the 32-bit native editor host.");
            if(!String.Equals(Path.GetFileName(Process.GetCurrentProcess().MainModule.FileName),"McgsSetPro.exe",StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Bridge callback is outside McgsSetPro.exe.");
            if(Thread.CurrentThread.GetApartmentState()!=ApartmentState.STA)throw new InvalidOperationException("Native callback is not STA.");
            int thread=GetCurrentThreadId();
            if(UiThreadId!=0&&UiThreadId!=thread)throw new InvalidOperationException("Callback changed native UI thread.");
            UiThreadId=thread;latestDatObj=datObj;AcquireRuntimeGate();
            RecordEvent("native_callback",new Dictionary<string,object>{{"callback",callback},{"query",query},{"native_thread_id",thread},{"process_id",Process.GetCurrentProcess().Id},{"client_bits",IntPtr.Size*8}});
            if(worker!=null)return;
            uiContext=SynchronizationContext.Current;
            if(uiContext==null||uiContext.GetType()==typeof(SynchronizationContext))uiContext=new System.Windows.Forms.WindowsFormsSynchronizationContext();
            var next=new Thread(WorkerLoop);next.IsBackground=true;next.Name="Mcgs own queue preparation/publication";
            next.SetApartmentState(ApartmentState.MTA);worker=next;
            try{next.Start();}catch{worker=null;ReleaseRuntimeGate();throw;}
            RecordEvent("ui_pump_started",new Dictionary<string,object>{{"native_thread_id",thread},{"pipeline","background-prepare/ui-dispatch/background-publish"}});
        }
        static void AcquireRuntimeGate(){if(ownsRuntimeGate)return;string key;using(var hash=System.Security.Cryptography.SHA256.Create())key=BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(RuntimeRoot.ToUpperInvariant()))).Replace("-","");runtimeGate=new Mutex(false,@"Local\McgsInternalBridgeQueue_"+key);try{ownsRuntimeGate=runtimeGate.WaitOne(0);}catch(AbandonedMutexException){ownsRuntimeGate=true;}if(!ownsRuntimeGate){runtimeGate.Dispose();runtimeGate=null;throw new InvalidOperationException("Another live bootstrap owns this exact queue root; do not start a competing host.");}}
        static void ReleaseRuntimeGate(){if(GetCurrentThreadId()!=UiThreadId)throw new InvalidOperationException("The UI-owned runtime mutex must be released on its UI thread.");if(ownsRuntimeGate){runtimeGate.ReleaseMutex();ownsRuntimeGate=false;}if(runtimeGate!=null){runtimeGate.Dispose();runtimeGate=null;}}

        // Only this worker reads the queue, claims requests, selects/loads engines,
        // and publishes replies. It never reads/releases the UI-owned datObj.
        static void WorkerLoop() {
            Thread owner=Thread.CurrentThread;
            try{
                requestSignal=new EventWaitHandle(false,EventResetMode.AutoReset,@"Local\McgsInternalBridgeWake_"+BootstrapLayout.ConfigurationSha256);
                RecordEvent("queue_notification_started",new Dictionary<string,object>{{"poll_fallback_ms",250},{"prepare_thread_id",GetCurrentThreadId()}});
                durablePump=new DurableQueuePump(RuntimeRoot,DispatchFromWorker,
                    delegate{return new Dictionary<string,object>{{"native_thread_id",UiThreadId},{"process_id",Process.GetCurrentProcess().Id},{"bridge_bootstrap_scope_sha256",BootstrapLayout.ConfigurationSha256},{"queue_prepare_thread_id",GetCurrentThreadId()},{"queue_publish_thread_id",GetCurrentThreadId()},{"queue_wake_source",dispatchWakeSource},{"queue_event_pump_runs",eventPumpRuns},{"queue_poll_pump_runs",pollPumpRuns},{"queue_pipeline","background-prepare/ui-dispatch/background-publish"}};},
                    delegate(string source,Exception error){RecordError(source,error);});
                while(true){
                    BootstrapLayout.Check();
                    if(File.Exists(Path.Combine(RuntimeRoot,"bridge.stop")))break;
                    bool handled=false;
                    try{handled=durablePump.PumpOne();}catch(Exception error){RecordError("queue_pump",error);}
                    if(handled)continue;
                    if(requestSignal.WaitOne(250)){dispatchWakeSource="event";eventPumpRuns++;}else{dispatchWakeSource="poll";pollPumpRuns++;}
                }
            }catch(Exception error){RecordError("queue_worker",error);}
            finally{
                try{if(durablePump!=null)durablePump.Pause();}catch(Exception error){RecordError("queue_pause",error);}finally{durablePump=null;}
                try{if(requestSignal!=null)requestSignal.Dispose();}catch(Exception error){RecordError("queue_signal_dispose",error);}finally{requestSignal=null;}
                // Do not wait on this worker from the UI: it may be waiting in Send.
                // All UI-owned gate/COM-reference cleanup is posted back to the UI.
                try{uiContext.Post(delegate(object unused){StopOnUi(owner);},null);}
                catch(Exception error){RecordError("queue_stop_ui_post",error);}
            }
        }
        static Dictionary<string,object> DispatchFromWorker(Dictionary<string,object> request,Action enterDispatch) {
            if(GetCurrentThreadId()==UiThreadId)throw new InvalidOperationException("Queue preparation must be outside the UI thread.");
            int prepareThread=GetCurrentThreadId(),dispatchThread=0;
            var clock=Stopwatch.StartNew();EngineLoader.PreparedCall prepared=EngineLoader.Prepare(request);double prepareMs=clock.Elapsed.TotalMilliseconds;
            if(File.Exists(Path.Combine(RuntimeRoot,"bridge.stop")))throw new OperationCanceledException("Bridge stop requested before UI dispatch; request remains reserved.");
            Dictionary<string,object> response=null;Exception failure=null;
            enterDispatch();clock.Restart();
            uiContext.Send(delegate(object unused){
                try{
                    if(GetCurrentThreadId()!=UiThreadId)throw new InvalidOperationException("SynchronizationContext.Send did not enter the captured UI thread.");
                    dispatchThread=GetCurrentThreadId();
                    // latestDatObj is accessed only here on its owning UI thread.
                    response=EngineLoader.Dispatch(prepared,latestDatObj,UiThreadId);
                }catch(Exception error){failure=error;}
            },null);
            double dispatchMs=clock.Elapsed.TotalMilliseconds;
            if(failure!=null)throw failure;
            clock.Restart();response=EngineLoader.Finalize(prepared,response);double finalizeMs=clock.Elapsed.TotalMilliseconds;
            response["queue_prepare_thread_id"]=prepareThread;response["queue_dispatch_thread_id"]=dispatchThread;response["queue_finalize_thread_id"]=GetCurrentThreadId();
            response["queue_prepare_elapsed_ms"]=prepareMs;response["queue_native_dispatch_elapsed_ms"]=dispatchMs;response["queue_finalize_elapsed_ms"]=finalizeMs;
            return response;
        }
        static void StopOnUi(Thread owner){
            if(GetCurrentThreadId()!=UiThreadId){RecordError("queue_stop_thread",new InvalidOperationException("Stop cleanup did not enter the original UI thread."));return;}
            if(worker!=owner)return;
            worker=null;latestDatObj=null;
            try{ReleaseRuntimeGate();RecordEvent("ui_pump_stopped",new Dictionary<string,object>{{"native_thread_id",UiThreadId},{"cleanup_thread_id",GetCurrentThreadId()}});}
            catch(Exception error){RecordError("queue_stop_cleanup",error);}
        }
        internal static void RecordEvent(string kind,Dictionary<string,object> fields) {
            try{
                lock(eventLogGate){BootstrapLayout.OwnedRuntime(Path.Combine(RuntimeRoot,"bootstrap-events.jsonl"));Directory.CreateDirectory(RuntimeRoot);fields["bridge_bootstrap_scope_sha256"]=BootstrapLayout.ConfigurationSha256;fields["event"]=kind;fields["utc"]=DateTime.UtcNow.ToString("o",CultureInfo.InvariantCulture);File.AppendAllText(Path.Combine(RuntimeRoot,"bootstrap-events.jsonl"),new JavaScriptSerializer().Serialize(fields)+Environment.NewLine,new UTF8Encoding(false));}
            }catch { /* Logging must never escape across a COM callback. */ }
        }
        internal static void RecordError(string source,Exception error){RecordEvent("error",new Dictionary<string,object>{{"source",source},{"error",error.Message},{"error_type",error.GetType().Name}});}
    }
}
