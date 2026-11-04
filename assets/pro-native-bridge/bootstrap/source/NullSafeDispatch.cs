// Own x86 IDispatch adapter. No registration, host loading, or vendor calls.
// Only malformed NULL VT_BYREF|VT_DISPATCH storage is normalised per Invoke.
using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace McgsInternalBridge {
    internal sealed class NullSafeDispatch {
        internal static readonly Guid DispatchIid=new Guid("00020400-0000-0000-C000-000000000046");
        static readonly Guid UnknownIid=new Guid("00000000-0000-0000-C000-000000000046");
        const int E_POINTER=unchecked((int)0x80004003),E_UNEXPECTED=unchecked((int)0x8000FFFF);
        const int DISP_E_BADPARAMCOUNT=unchecked((int)0x8002000E);
        static int liveCount,createdCount;
        static long normalisedCount,temporaryOutputReleaseCount;
        internal static int LiveProxyCount{get{return Interlocked.CompareExchange(ref liveCount,0,0);}}
        internal static int CreatedProxyCount{get{return Interlocked.CompareExchange(ref createdCount,0,0);}}
        internal static long NormalisedNullDispatchArguments{get{return Interlocked.Read(ref normalisedCount);}}
        internal static long ReleasedTemporaryDispatchOutputs{get{return Interlocked.Read(ref temporaryOutputReleaseCount);}}

        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int QI(IntPtr self,IntPtr iid,IntPtr output);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate uint Ref(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int TypeCount(IntPtr self,IntPtr output);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int TypeInfo(IntPtr self,uint index,uint lcid,IntPtr output);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Names(IntPtr self,IntPtr iid,IntPtr names,uint count,uint lcid,IntPtr output);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int InvokeMethod(IntPtr self,int member,IntPtr iid,uint lcid,ushort flags,
            IntPtr parameters,IntPtr result,IntPtr exception,IntPtr argumentError);

        // One immutable28-byte vtable and seven static thunks live for the process.
        // They cannot disappear while a last Release callback is returning.
        static class SharedVtable {
            internal static readonly Delegate[] Callbacks={new QI(QueryCallback),new Ref(AddRefCallback),new Ref(ReleaseCallback),
                new TypeCount(TypeCountCallback),new TypeInfo(TypeInfoCallback),new Names(NamesCallback),new InvokeMethod(InvokeCallback)};
            static readonly GCHandle CallbackRoot=GCHandle.Alloc(Callbacks);
            internal static readonly IntPtr Pointer=Build();
            static IntPtr Build() {
                if(IntPtr.Size!=4)throw new PlatformNotSupportedException("NullSafeDispatch requires x86.");
                IntPtr table=Marshal.AllocHGlobal(7*4);
                try{for(int i=0;i<7;i++)Marshal.WriteIntPtr(table,i*4,Marshal.GetFunctionPointerForDelegate(Callbacks[i]));return table;}
                catch{Marshal.FreeHGlobal(table);throw;}
            }
        }

        internal sealed class Cache {
            readonly object gate=new object();WeakReference current;
            internal IntPtr Acquire(object target,Type dispinterface) {
                if(IntPtr.Size!=4)throw new PlatformNotSupportedException("NullSafeDispatch requires x86.");
                lock(gate) {
                    NullSafeDispatch existing=current==null?null:current.Target as NullSafeDispatch;
                    if(existing!=null && existing.TryAddRef())return existing.instance;
                    var proxy=new NullSafeDispatch(target,dispinterface,this);
                    current=new WeakReference(proxy);return proxy.instance; // constructor owns the returned reference
                }
            }
            internal void Clear(NullSafeDispatch value) {
                lock(gate){if(current!=null && Object.ReferenceEquals(current.Target,value))current=null;}
            }
        }

        IntPtr instance,inner;GCHandle root;readonly WeakReference cache;
        int references=1,disposed;bool counted;
        readonly QI innerQI;readonly TypeCount innerCount;readonly TypeInfo innerInfo;
        readonly Names innerNames;readonly InvokeMethod innerInvoke;
        NullSafeDispatch(object target,Type dispinterface,Cache owner) {
            cache=new WeakReference(owner);
            try {
                inner=Marshal.GetComInterfaceForObject(target,dispinterface,CustomQueryInterfaceMode.Ignore);
                if(inner==IntPtr.Zero)throw new InvalidOperationException("An inner dispinterface is required.");
                IntPtr table=Marshal.ReadIntPtr(inner);
                innerQI=Bind<QI>(table,0);innerCount=Bind<TypeCount>(table,3);innerInfo=Bind<TypeInfo>(table,4);
                innerNames=Bind<Names>(table,5);innerInvoke=Bind<InvokeMethod>(table,6);
                instance=Marshal.AllocHGlobal(8);
                root=GCHandle.Alloc(this);
                Marshal.WriteIntPtr(instance,SharedVtable.Pointer);
                Marshal.WriteIntPtr(instance,4,GCHandle.ToIntPtr(root));
                Interlocked.Increment(ref liveCount);Interlocked.Increment(ref createdCount);counted=true;
            }catch{DisposeCore();throw;}
            GC.KeepAlive(target);
        }
        static T Bind<T>(IntPtr table,int slot)where T:class {
            return Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(table,slot*4),typeof(T)) as T;
        }
        static NullSafeDispatch Lookup(IntPtr self) {
            if(self==IntPtr.Zero)return null;
            IntPtr handle=Marshal.ReadIntPtr(self,4);
            return handle==IntPtr.Zero?null:GCHandle.FromIntPtr(handle).Target as NullSafeDispatch;
        }
        bool TryAddRef() {
            for(;;){int value=Interlocked.CompareExchange(ref references,0,0);
                if(value<=0 || value==Int32.MaxValue)return false;
                if(Interlocked.CompareExchange(ref references,value+1,value)==value)return true;}
        }
        uint ReleaseCore() {
            for(;;){int value=Interlocked.CompareExchange(ref references,0,0);if(value<=0)return 0;
                if(Interlocked.CompareExchange(ref references,value-1,value)!=value)continue;
                if(value==1)DisposeCore();return unchecked((uint)(value-1));}
        }
        void DisposeCore() {
            if(Interlocked.Exchange(ref disposed,1)!=0)return;
            // A WeakReference cache never creates target -> proxy -> CCW -> target ownership cycles.
            Cache owner=cache==null?null:cache.Target as Cache;if(owner!=null)owner.Clear(this);
            IntPtr native=Interlocked.Exchange(ref instance,IntPtr.Zero);
            IntPtr ccw=Interlocked.Exchange(ref inner,IntPtr.Zero);
            try{if(ccw!=IntPtr.Zero)Marshal.Release(ccw);}
            finally {
                if(native!=IntPtr.Zero){Marshal.WriteIntPtr(native,4,IntPtr.Zero);Marshal.FreeHGlobal(native);}
                if(root.IsAllocated)root.Free();
                if(counted){counted=false;Interlocked.Decrement(ref liveCount);}
                GC.KeepAlive(this);
            }
        }
        static int Error(Exception error){return Marshal.GetHRForException(error);}

        static int QueryCallback(IntPtr self,IntPtr iid,IntPtr output) {
            NullSafeDispatch proxy=null;bool held=false;
            try {
                if(output==IntPtr.Zero)return E_POINTER;Marshal.WriteIntPtr(output,IntPtr.Zero);
                if(iid==IntPtr.Zero)return E_POINTER;
                proxy=Lookup(self);if(proxy==null || !(held=proxy.TryAddRef()))return E_POINTER;
                Guid value=(Guid)Marshal.PtrToStructure(iid,typeof(Guid));
                if(value==DispatchIid) {
                    if(!proxy.TryAddRef())return E_UNEXPECTED;
                    Marshal.WriteIntPtr(output,proxy.instance);return 0;
                }
                // IID_IUnknown is deliberately the real CCW identity, as are all other QIs.
                return proxy.innerQI(proxy.inner,iid,output);
            }catch(Exception error){return Error(error);}
            finally{if(held)proxy.ReleaseCore();GC.KeepAlive(proxy);}
        }
        static uint AddRefCallback(IntPtr self) {
            NullSafeDispatch proxy=null;
            try{proxy=Lookup(self);return proxy!=null && proxy.TryAddRef()?unchecked((uint)Interlocked.CompareExchange(ref proxy.references,0,0)):0;}
            catch{return 0;}finally{GC.KeepAlive(proxy);}
        }
        static uint ReleaseCallback(IntPtr self) {
            NullSafeDispatch proxy=null;
            try{proxy=Lookup(self);return proxy==null?0:proxy.ReleaseCore();}
            catch{return 0;}finally{GC.KeepAlive(proxy);}
        }
        static int TypeCountCallback(IntPtr self,IntPtr output) {
            NullSafeDispatch proxy=null;bool held=false;
            try{if(output==IntPtr.Zero)return E_POINTER;proxy=Lookup(self);if(proxy==null || !(held=proxy.TryAddRef()))return E_POINTER;
                return proxy.innerCount(proxy.inner,output);}
            catch(Exception error){return Error(error);}finally{if(held)proxy.ReleaseCore();GC.KeepAlive(proxy);}
        }
        static int TypeInfoCallback(IntPtr self,uint index,uint lcid,IntPtr output) {
            NullSafeDispatch proxy=null;bool held=false;
            try{if(output==IntPtr.Zero)return E_POINTER;proxy=Lookup(self);if(proxy==null || !(held=proxy.TryAddRef()))return E_POINTER;
                return proxy.innerInfo(proxy.inner,index,lcid,output);}
            catch(Exception error){return Error(error);}finally{if(held)proxy.ReleaseCore();GC.KeepAlive(proxy);}
        }
        static int NamesCallback(IntPtr self,IntPtr iid,IntPtr names,uint count,uint lcid,IntPtr output) {
            NullSafeDispatch proxy=null;bool held=false;
            try{if(iid==IntPtr.Zero || (count>0 && (names==IntPtr.Zero || output==IntPtr.Zero)))return E_POINTER;
                proxy=Lookup(self);if(proxy==null || !(held=proxy.TryAddRef()))return E_POINTER;
                return proxy.innerNames(proxy.inner,iid,names,count,lcid,output);}
            catch(Exception error){return Error(error);}finally{if(held)proxy.ReleaseCore();GC.KeepAlive(proxy);}
        }
        static int InvokeCallback(IntPtr self,int member,IntPtr iid,uint lcid,ushort flags,
            IntPtr parameters,IntPtr result,IntPtr exception,IntPtr argumentError) {
            NullSafeDispatch proxy=null;bool held=false;
            try{if(parameters==IntPtr.Zero || iid==IntPtr.Zero)return E_POINTER;
                proxy=Lookup(self);if(proxy==null || !(held=proxy.TryAddRef()))return E_POINTER;
                return proxy.Invoke(member,iid,lcid,flags,parameters,result,exception,argumentError);}
            catch(Exception error){return Error(error);}finally{if(held)proxy.ReleaseCore();GC.KeepAlive(proxy);}
        }
        int Invoke(int member,IntPtr iid,uint lcid,ushort flags,IntPtr parameters,IntPtr result,IntPtr exception,IntPtr argumentError) {
            uint count=unchecked((uint)Marshal.ReadInt32(parameters,8)),named=unchecked((uint)Marshal.ReadInt32(parameters,12));
            if(count>16 || named>count)return DISP_E_BADPARAMCOUNT;
            IntPtr original=Marshal.ReadIntPtr(parameters),names=Marshal.ReadIntPtr(parameters,4);
            if((count>0 && original==IntPtr.Zero) || (named>0 && names==IntPtr.Zero))return E_POINTER;
            int total=unchecked((int)count),normalised=0;bool[] temporary=new bool[total];
            for(int i=0;i<total;i++) {
                IntPtr at=IntPtr.Add(original,i*16);ushort type=unchecked((ushort)Marshal.ReadInt16(at));
                if(Marshal.ReadIntPtr(at,8)!=IntPtr.Zero)continue;
                if(type==0x4009){temporary[i]=true;++normalised;}
                else if(type==0x4008 || type==0x4003){if(argumentError!=IntPtr.Zero)Marshal.WriteInt32(argumentError,i);return E_POINTER;}
            }
            IntPtr copied=IntPtr.Zero,copyParameters=IntPtr.Zero,scratch=IntPtr.Zero;
            try {
                copyParameters=Marshal.AllocHGlobal(16);byte[] data=new byte[16];Marshal.Copy(parameters,data,0,16);Marshal.Copy(data,0,copyParameters,16);
                if(total>0) {
                    copied=Marshal.AllocHGlobal(total*16);byte[] arguments=new byte[total*16];Marshal.Copy(original,arguments,0,arguments.Length);
                    Marshal.Copy(arguments,0,copied,arguments.Length);Marshal.WriteIntPtr(copyParameters,copied);
                    if(normalised>0) {
                        scratch=Marshal.AllocHGlobal(total*4);for(int i=0;i<total;i++)Marshal.WriteIntPtr(scratch,i*4,IntPtr.Zero);
                        for(int i=0;i<total;i++)if(temporary[i])Marshal.WriteIntPtr(copied,i*16+8,IntPtr.Add(scratch,i*4));
                        Interlocked.Add(ref normalisedCount,normalised);
                    }
                }
                return innerInvoke(inner,member,iid,lcid,flags,copyParameters,result,exception,argumentError);
            }finally {
                try {
                    if(scratch!=IntPtr.Zero)for(int i=0;i<total;i++)if(temporary[i]) {
                        IntPtr output=Marshal.ReadIntPtr(scratch,i*4);
                        if(output!=IntPtr.Zero){Marshal.Release(output);Interlocked.Increment(ref temporaryOutputReleaseCount);}
                    }
                }finally {
                    // The copied variants borrow all original BSTR/interface references: never VariantClear them.
                    if(scratch!=IntPtr.Zero)Marshal.FreeHGlobal(scratch);
                    if(copied!=IntPtr.Zero)Marshal.FreeHGlobal(copied);
                    if(copyParameters!=IntPtr.Zero)Marshal.FreeHGlobal(copyParameters);
                }
            }
        }
    }
}
