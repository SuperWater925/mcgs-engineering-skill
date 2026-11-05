// Owned IPropertyCollector copies values while each original getter is active.
// This does not instantiate PropertyManager/QVariant or use its dispatcher as a getter.
using System;using System.Collections.Generic;using System.Runtime.InteropServices;using System.Text;
namespace McgsInternalBridge {
 internal sealed class NativeTypedPropertyCollector : IDisposable {
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void Getter(IntPtr target,IntPtr collector);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)]delegate void Scalar(IntPtr self,IntPtr owner,IntPtr key,IntPtr value);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)]delegate void Enumeration(IntPtr self,IntPtr owner,IntPtr key,IntPtr value,IntPtr options);
  [UnmanagedFunctionPointer(CallingConvention.StdCall)]delegate void Pair(IntPtr self,IntPtr owner,IntPtr key,IntPtr value,IntPtr number,IntPtr options);
  [DllImport("kernel32.dll",SetLastError=true)]static extern IntPtr VirtualAlloc(IntPtr address,UIntPtr size,uint type,uint protection);
  [DllImport("kernel32.dll",SetLastError=true)]static extern bool VirtualProtect(IntPtr address,UIntPtr size,uint protection,out uint previous);
  [DllImport("kernel32.dll",SetLastError=true)]static extern bool VirtualFree(IntPtr address,UIntPtr size,uint type);
  [DllImport("kernel32.dll")]static extern IntPtr GetCurrentProcess();
  [DllImport("kernel32.dll",SetLastError=true)]static extern bool FlushInstructionCache(IntPtr process,IntPtr address,UIntPtr size);
  readonly NativeEngine engine;readonly List<Delegate> callbacks=new List<Delegate>();
  readonly List<Dictionary<string,object>> rows=new List<Dictionary<string,object>>();
  readonly List<string> errors=new List<string>();readonly HashSet<uint> activeTargets=new HashSet<uint>();
  IntPtr instance,vtable,code;bool active,entered,disposed;int depth;
  internal NativeTypedPropertyCollector(NativeEngine native) {
   engine=native;RequireThread();
   try {
    instance=Marshal.AllocHGlobal(8);vtable=Marshal.AllocHGlobal(14*4);
    Marshal.WriteInt32(instance,0,vtable.ToInt32());Marshal.WriteInt32(instance,4,0x434F4C31);
    var bytes=new List<byte>();var offsets=new int[14];
    for(int slot=0;slot<14;slot++) {
     offsets[slot]=bytes.Count;
     if(slot==0){bytes.AddRange(new byte[]{0x33,0xC0,0xC2,4,0});continue;}
     int captured=slot;Delegate callback;
     if(slot==7)callback=new Enumeration(delegate(IntPtr self,IntPtr owner,IntPtr key,IntPtr value,IntPtr options){Copy(captured,self,owner,key,value,IntPtr.Zero);});
     else if(slot==9||slot==11)callback=new Pair(delegate(IntPtr self,IntPtr owner,IntPtr key,IntPtr value,IntPtr number,IntPtr options){Copy(captured,self,owner,key,value,number);});
     else callback=new Scalar(delegate(IntPtr self,IntPtr owner,IntPtr key,IntPtr value){Copy(captured,self,owner,key,value,IntPtr.Zero);});
     callbacks.Add(callback);IntPtr address=Marshal.GetFunctionPointerForDelegate(callback);
     bytes.AddRange(new byte[]{0x58,0x51,0x50,0xB8});bytes.AddRange(BitConverter.GetBytes(address.ToInt32()));bytes.AddRange(new byte[]{0xFF,0xE0});
    }
    NativeMemory.Require(bytes.Count<=4096,"Owned collector code bound differs.");
    code=VirtualAlloc(IntPtr.Zero,new UIntPtr(4096),0x3000,0x04);NativeMemory.Require(code!=IntPtr.Zero,"Cannot allocate owned collector thunks.");
    Marshal.Copy(bytes.ToArray(),0,code,bytes.Count);uint previous;
    NativeMemory.Require(VirtualProtect(code,new UIntPtr(4096),0x20,out previous)&&FlushInstructionCache(GetCurrentProcess(),code,new UIntPtr((uint)bytes.Count)),"Cannot publish owned collector RX thunks.");
    for(int slot=0;slot<14;slot++)Marshal.WriteInt32(vtable,slot*4,NativeMemory.Add(code,offsets[slot]).ToInt32());
   }catch{Dispose();throw;}
  }
  static void RequireThread(){NativeMemory.Require(IntPtr.Size==4&&EngineEntry.ExpectedUiThreadId>0&&NativeMemory.GetCurrentThreadId()==EngineEntry.ExpectedUiThreadId,"Owned property collector requires captured x86 UI thread.");}
  static string CString(IntPtr storage,int maximum) {
   NativeMemory.Readable(storage,4);IntPtr text=NativeMemory.Ptr(storage,0);NativeMemory.Require(text!=IntPtr.Zero,"Collector CString is NULL.");
   int length=NativeMemory.I32(text,-12),capacity=NativeMemory.I32(text,-8);
   NativeMemory.Require(length>=0&&capacity>=length,"Collector CString length/capacity differs.");
   byte[] raw=NativeMemory.Bytes(text,checked(length*2+2));NativeMemory.Require(raw[raw.Length-1]==0&&raw[raw.Length-2]==0,"Collector CString terminator differs.");
   return new UnicodeEncoding(false,false,true).GetString(raw,0,length*2);
  }
  void ReadTarget(IntPtr target) {
   RequireThread();NativeMemory.Require(!disposed&&active&&depth<16&&activeTargets.Add(NativeMemory.U(target)),"Property component depth/cycle/lifetime differs.");
   depth++;
   try{NativePropertyTarget.Describe(engine,target);Getter getter=engine.Bind<Getter>(engine.Virtual(target,6));getter(target,instance);}
   finally{depth--;activeTargets.Remove(NativeMemory.U(target));GC.KeepAlive(callbacks);}
  }
  void Copy(int slot,IntPtr self,IntPtr owner,IntPtr key,IntPtr value,IntPtr number) {
   try {
    RequireThread();NativeMemory.Require(!disposed&&active&&self==instance&&NativeMemory.I32(self,4)==0x434F4C31,"Owned property callback context/bound differs.");
    NativeMemory.Require(owner!=IntPtr.Zero&&activeTargets.Contains(NativeMemory.U(owner)),"Getter returned an unentered property owner.");
    string name=CString(key,256);var row=new Dictionary<string,object>{{"native_owner",NativeMemory.Hex(owner)},{"native_key",name},{"collector_slot",slot},{"component_depth",depth-1}};
    switch(slot) {
     case 1:
      row["native_type_tag"]=9;row["component_iobject"]=NativeMemory.Hex(value);row["value"]=null;rows.Add(row);
      if(value!=IntPtr.Zero){var info=NativePropertyTarget.Describe(engine,value);row["component_rtti"]=info["rtti"];row["component_property_interface"]=info["property_interface"];ReadTarget(value);}return;
     case 2:row["native_type_tag"]=0;row["value"]=NativeMemory.U(value);break;
     case 3:row["native_type_tag"]=1;row["value"]=NativeOriginalFontValue.Snapshot(value);break;
     case 4:row["native_type_tag"]=2;row["value"]=value.ToInt32();break;
     case 5:row["native_type_tag"]=3;row["value"]=CString(value,131072);break;
     case 6:case 12:
      row["native_type_tag"]=slot==6?4:11;uint flag=NativeMemory.U(value)&255U;NativeMemory.Require(flag<=1,"Native Boolean collector value differs.");row["value"]=flag!=0;break;
     case 7:row["native_type_tag"]=5;row["value"]=CString(value,131072);break;
     case 8:row["native_type_tag"]=10;row["value"]=CString(value,131072);break;
     case 9:case 11:
      row["native_type_tag"]=slot==9?6:7;row["value"]=new Dictionary<string,object>{{"text",CString(value,131072)},{"number",number.ToInt32()}};break;
     case 10:row["native_type_tag"]=8;row["value"]=CString(value,131072);break;
     case 13:row["native_type_tag"]=12;row["value"]=CString(value,131072);break;
     default:throw new InvalidOperationException("Unknown owned collector slot.");
    }
    rows.Add(row);
   }catch(Exception error){errors.Add(error.GetType().Name+": "+error.Message);}
  }
  internal List<Dictionary<string,object>> Read(IntPtr logicalTarget) {
   RequireThread();NativeMemory.Require(!disposed&&!entered&&!active,"Owned collector is single-use.");entered=true;active=true;
   try{ReadTarget(logicalTarget);}finally{active=false;GC.KeepAlive(callbacks);}
   NativeMemory.Require(errors.Count==0,"Owned collector callback failed: "+String.Join("; ",errors.ToArray()));
   return rows;
  }
  public void Dispose(){if(disposed)return;NativeMemory.Require(!active,"Cannot release collector during native getter.");disposed=true;GC.KeepAlive(callbacks);if(code!=IntPtr.Zero){VirtualFree(code,UIntPtr.Zero,0x8000);code=IntPtr.Zero;}if(vtable!=IntPtr.Zero){Marshal.FreeHGlobal(vtable);vtable=IntPtr.Zero;}if(instance!=IntPtr.Zero){Marshal.FreeHGlobal(instance);instance=IntPtr.Zero;}callbacks.Clear();}
 }
}
