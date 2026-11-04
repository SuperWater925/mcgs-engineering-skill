// Owned x86 IPropertyDispatcher for the installed, derived ABI.
// This is a functional component, not a project writer or a queue entry point.
// The caller owns target selection, preimage permit, original dirty/history,
// getter readback and persistence. No project pointers are accepted from JSON.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
 internal sealed class NativeTypedPropertyDispatcher : IDisposable {
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)] delegate IntPtr AssignWide(IntPtr storage,IntPtr wide);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)] [return:MarshalAs(UnmanagedType.I1)]
  delegate bool ScalarCallback(IntPtr self,IntPtr key,IntPtr output);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)] [return:MarshalAs(UnmanagedType.I1)]
  delegate bool PairCallback(IntPtr self,IntPtr key,IntPtr output,IntPtr number);
  [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr VirtualAlloc(IntPtr address,UIntPtr size,uint type,uint protect);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualProtect(IntPtr address,UIntPtr size,uint protection,out uint previous);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool VirtualFree(IntPtr address,UIntPtr size,uint type);
  [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool FlushInstructionCache(IntPtr process,IntPtr address,UIntPtr size);
  sealed class Value {
   internal string Key;internal int Tag,Slot,Matches;internal uint Bits;
   internal IntPtr Wide;internal int Number;internal NativeOriginalFontValue Font;
  }
  readonly Dictionary<string,Value> values=new Dictionary<string,Value>(StringComparer.Ordinal);
  readonly List<Delegate> callbacks=new List<Delegate>();
  readonly List<string> errors=new List<string>();readonly AssignWide assign;
  IntPtr instance,vtable,code;bool disposed,active,entered;
  internal IntPtr Instance {get{RequireAlive();return instance;}}
  internal IList<string> Errors {get{return errors.AsReadOnly();}}
  internal NativeTypedPropertyDispatcher(NativeStrategyProfile.Api api,IEnumerable<Dictionary<string,object>> properties) {
   NativeMemory.Require(IntPtr.Size==4 && EngineEntry.ExpectedUiThreadId>0 && NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Typed dispatcher requires the captured x86 UI thread.");
   // Resolve the original CString assignment before any owned allocation/callback.
   assign=api.Bind<AssignWide>("CStringAssignWide");
   try {
    foreach(var row in properties) {
     NativeMemory.Require(values.Count<256 && row.ContainsKey("native_key") && row.ContainsKey("native_type_tag") && row.ContainsKey("value"),"Typed property needs native_key/native_type_tag/value, at most256 entries.");
     string key=Convert.ToString(row["native_key"],CultureInfo.InvariantCulture);
     NativeMemory.Require(!String.IsNullOrEmpty(key)&&key.Length<=256&&key.IndexOf('\0')<0&&!values.ContainsKey(key),"Typed property key is empty, repeated or unbounded.");
     var value=new Value{Key=key,Tag=Convert.ToInt32(row["native_type_tag"],CultureInfo.InvariantCulture)};
     values.Add(key,value); // Keep ownership even if later preparation fails.
     switch(value.Tag) {
      case 0: value.Slot=1;value.Bits=UInt32Value(row["value"]);break;
      case 1:
       var font=row["value"] as Dictionary<string,object>;NativeMemory.Require(font!=null,"Native font requires its typed FontValue object.");
       value.Slot=2;value.Font=new NativeOriginalFontValue(api.Engine,api,font);break;
      case 2: value.Slot=3;value.Bits=unchecked((uint)Int32Value(row["value"]));break;
      case 4: case 11:
       NativeMemory.Require(row["value"] is bool,"Native Boolean property requires JSON true/false.");
       value.Slot=value.Tag==4?5:11;value.Bits=(bool)row["value"]?1U:0U;break;
      case 3: case 5: case 8: case 10: case 12:
       value.Slot=value.Tag==3?4:value.Tag==5?6:value.Tag==8?9:value.Tag==10?7:12;
       value.Wide=Wide(row["value"]);break;
      case 6: case 7:
       var pair=row["value"] as Dictionary<string,object>;
       NativeMemory.Require(pair!=null&&pair.Count==2&&pair.ContainsKey("text")&&pair.ContainsKey("number"),"Native paired property requires exactly text/number.");
       value.Slot=value.Tag==6?8:10;value.Number=Int32Value(pair["number"]);value.Wide=Wide(pair["text"]);break;
      default: throw new InvalidOperationException("Native type tag "+value.Tag+" needs its own original component adapter; it cannot be treated as a scalar.");
     }
    }
    NativeMemory.Require(values.Count>0,"Typed dispatcher has no requested values.");
    instance=Marshal.AllocHGlobal(8);vtable=Marshal.AllocHGlobal(13*4);
    Marshal.WriteInt32(instance,0,vtable.ToInt32());Marshal.WriteInt32(instance,4,0x54595031);
    var bytes=new List<byte>();var offsets=new int[13];int[] cleanup={4,8,8,8,8,8,8,8,12,8,12,8,8};
    for(int slot=0;slot<13;slot++) {
     offsets[slot]=bytes.Count;
     if(slot==0) {bytes.AddRange(new byte[]{0x33,0xC0,0xC2,(byte)cleanup[slot],0});continue;}
     int captured=slot;Delegate callback;
     if(slot==8||slot==10) callback=new PairCallback(delegate(IntPtr self,IntPtr key,IntPtr output,IntPtr number){return Dispatch(captured,self,key,output,number);});
     else callback=new ScalarCallback(delegate(IntPtr self,IntPtr key,IntPtr output){return Dispatch(captured,self,key,output,IntPtr.Zero);});
     callbacks.Add(callback);IntPtr address=Marshal.GetFunctionPointerForDelegate(callback);
     // Convert thiscall ECX to first stdcall argument; original stack args stay in order.
     bytes.AddRange(new byte[]{0x58,0x51,0x50,0xB8});bytes.AddRange(BitConverter.GetBytes(address.ToInt32()));bytes.AddRange(new byte[]{0xFF,0xE0});
    }
    NativeMemory.Require(bytes.Count<=4096,"Typed dispatcher thunks exceeded owned allocation.");
    code=VirtualAlloc(IntPtr.Zero,new UIntPtr(4096),0x3000,0x04);NativeMemory.Require(code!=IntPtr.Zero,"Cannot allocate typed dispatcher thunks.");
    Marshal.Copy(bytes.ToArray(),0,code,bytes.Count);uint previous;
    NativeMemory.Require(VirtualProtect(code,new UIntPtr(4096),0x20,out previous)&&FlushInstructionCache(GetCurrentProcess(),code,new UIntPtr((uint)bytes.Count)),"Cannot publish typed dispatcher RX thunks.");
    for(int slot=0;slot<13;slot++)Marshal.WriteInt32(vtable,slot*4,NativeMemory.Add(code,offsets[slot]).ToInt32());
   } catch {Dispose();throw;}
  }
  static int Int32Value(object raw) {
   NativeMemory.Require(raw is int||raw is long||raw is uint||raw is short||raw is byte,"Native Int32 requires an integral JSON number.");
   long value=Convert.ToInt64(raw,CultureInfo.InvariantCulture);NativeMemory.Require(value>=Int32.MinValue&&value<=Int32.MaxValue,"Native Int32 is outside its range.");return (int)value;
  }
  static uint UInt32Value(object raw) {
   NativeMemory.Require(raw is int||raw is long||raw is uint||raw is short||raw is byte,"Native UInt32 requires an integral JSON number.");
   long value=Convert.ToInt64(raw,CultureInfo.InvariantCulture);NativeMemory.Require(value>=0&&value<=UInt32.MaxValue,"Native UInt32 is outside its range.");return (uint)value;
  }
  static IntPtr Wide(object raw) {
   NativeMemory.Require(raw is string,"Native text/enum property requires a JSON string, not an inferred conversion.");
   string text=(string)raw;NativeMemory.Require(text.Length<=131072&&text.IndexOf('\0')<0,"Native text property is unbounded or contains NUL.");
   // Reject unpaired surrogates before unmanaged allocation.
   new System.Text.UnicodeEncoding(false,false,true).GetBytes(text);
   return Marshal.StringToHGlobalUni(text);
  }
  void RequireAlive(){NativeMemory.Require(!disposed&&instance!=IntPtr.Zero&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Typed dispatcher lifetime/UI-thread differs.");}
  bool Dispatch(int slot,IntPtr self,IntPtr key,IntPtr output,IntPtr number) {
   try {
    RequireAlive();NativeMemory.Require(active&&self==instance&&NativeMemory.I32(self,4)==0x54595031,"Typed callback is outside its owned invocation.");
    string text=NativeStrategyProfile.ReadBorrowedCString(key,257);Value value;
    if(!values.TryGetValue(text,out value))return false;
    NativeMemory.Require(value.Slot==slot,"Native requested a different type for the declared property: "+text);
    NativeMemory.Require(value.Matches==0,"Native requested the same property more than once: "+text);
    if(value.Tag==1){NativeMemory.Require(value.Font!=null,"Owned FontValue is absent.");value.Font.AssignTo(output);}
    else if(value.Tag==4||value.Tag==11){NativeMemory.Readable(output,1);Marshal.WriteByte(output,(byte)value.Bits);}
    else if(value.Tag==0||value.Tag==2){NativeMemory.Readable(output,4);Marshal.WriteInt32(output,unchecked((int)value.Bits));}
    else {
     NativeMemory.Readable(output,4);NativeMemory.Require(value.Wide!=IntPtr.Zero,"Owned text value is absent.");assign(output,value.Wide);
     if(value.Tag==6||value.Tag==7){NativeMemory.Readable(number,4);Marshal.WriteInt32(number,value.Number);}
    }
    value.Matches++;return true;
   }catch(Exception error){errors.Add(error.GetType().Name+": "+error.Message);return false;}
  }
  internal void Invoke(Action<IntPtr> originalSetter) {
   RequireAlive();NativeMemory.Require(!entered&&!active&&originalSetter!=null,"Typed dispatcher is single-use; no automatic replay.");
   entered=true;active=true;
   try{originalSetter(instance);}finally{active=false;GC.KeepAlive(callbacks);}
   NativeMemory.Require(errors.Count==0,"Typed callback failed: "+String.Join("; ",errors.ToArray()));
   foreach(Value value in values.Values)NativeMemory.Require(value.Matches==1,"Native setter did not consume exactly one requested property: "+value.Key);
  }
  public void Dispose() {
   if(disposed)return;NativeMemory.Require(!active,"Cannot release a typed dispatcher during a native callback.");disposed=true;
   GC.KeepAlive(callbacks);
   if(code!=IntPtr.Zero){VirtualFree(code,UIntPtr.Zero,0x8000);code=IntPtr.Zero;}
   foreach(Value value in values.Values){try{if(value.Font!=null){value.Font.Dispose();value.Font=null;}}finally{if(value.Wide!=IntPtr.Zero){Marshal.FreeHGlobal(value.Wide);value.Wide=IntPtr.Zero;}}}
   if(vtable!=IntPtr.Zero){Marshal.FreeHGlobal(vtable);vtable=IntPtr.Zero;}
   if(instance!=IntPtr.Zero){Marshal.FreeHGlobal(instance);instance=IntPtr.Zero;}
   callbacks.Clear();
  }
 }
}
