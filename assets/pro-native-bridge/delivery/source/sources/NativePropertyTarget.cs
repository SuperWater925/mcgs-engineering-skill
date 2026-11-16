// Minimal shared property interface. A component may be IPropertyLinker without
// the IObject child/module methods at19/20; never enumerate those extra slots.
using System;using System.Collections.Generic;using System.Runtime.InteropServices;using System.Runtime.CompilerServices;
namespace McgsInternalBridge {
 internal static class NativePropertyTarget {
  sealed class Cache {internal readonly NativeOpaqueDrawState.LoadedImageRanges Images=new NativeOpaqueDrawState.LoadedImageRanges();internal readonly Dictionary<uint,Dictionary<string,object>> Tables=new Dictionary<uint,Dictionary<string,object>>();}
  static readonly ConditionalWeakTable<NativeEngine,Cache> caches=new ConditionalWeakTable<NativeEngine,Cache>();
  internal static Dictionary<string,object> Describe(NativeEngine engine,IntPtr pointer) {
   Cache cache=caches.GetValue(engine,delegate(NativeEngine ignored){return new Cache();});var ranges=cache.Images;IntPtr table=NativeMemory.Ptr(pointer,0);Dictionary<string,object> known;if(cache.Tables.TryGetValue(NativeMemory.U(table),out known)){var current=new Dictionary<string,object>(known);current["address"]=NativeMemory.Hex(pointer);return current;}ranges.Check(NativeMemory.Add(table,-4),32);IntPtr col=NativeMemory.Ptr(table,-4);ranges.Check(col,20);
   int offset=NativeMemory.I32(col,4);NativeAbiTargetProfiles.RequireLayout(NativeMemory.I32(col,0)==0&&offset>=0,"Property target complete-object locator differs.","property RTTI","COL");NativeMemory.Readable(NativeMemory.Add(pointer,-offset),checked(offset+4));
   IntPtr type=NativeMemory.Ptr(col,12),hierarchy=NativeMemory.Ptr(col,16);ranges.Check(type,9);ranges.Check(hierarchy,16);
   string name=NativeMemory.Ascii(NativeMemory.Add(type,8),Int32.MaxValue);int count=NativeMemory.I32(hierarchy,8);NativeMemory.Require(count>0,"Property target RTTI hierarchy is empty.");
   IntPtr array=NativeMemory.Ptr(hierarchy,12);ranges.Check(array,checked(count*4));bool directObject=false,directLinker=false;
   for(int i=0;i<count;i++) {
    IntPtr descriptor=NativeMemory.Ptr(array,checked(4*i));ranges.Check(descriptor,24);IntPtr baseType=NativeMemory.Ptr(descriptor,0);ranges.Check(baseType,9);
    string baseName=NativeMemory.Ascii(NativeMemory.Add(baseType,8),Int32.MaxValue);
    if(NativeMemory.I32(descriptor,8)!=offset||NativeMemory.I32(descriptor,12)!=-1)continue;
    if(baseName==".?AVIObject@@")directObject=true;
    if(baseName==".?AVIPropertyLinker@ObjectTree@@")directLinker=true;
   }
   if(!directObject&&!directLinker)throw NativeAbiTargetProfiles.Problem("unsupported_feature","Native component does not expose a direct property interface at this pointer.","property RTTI",name);
   var result=new Dictionary<string,object>{{"address",NativeMemory.Hex(pointer)},{"rtti",name},{"complete_offset",offset},{"property_interface",directObject?"IObject":"ObjectTree::IPropertyLinker"},
    {"vtable",NativeMemory.Hex(table)},{"IObject_children_or_module_methods_called",false}};
   cache.Tables.Add(NativeMemory.U(table),result);return new Dictionary<string,object>(result);
  }
  internal static T Bind<T>(NativeEngine engine,IntPtr target,bool setter)where T:class{
   Describe(engine,target);IntPtr table=NativeMemory.Ptr(target,0);
   IntPtr method=NativeAbiTargetProfiles.ProvenVirtualSlot(table,setter?5:6,setter?"native property setter":"native property getter");
   return Marshal.GetDelegateForFunctionPointer(method,typeof(T))as T;
  }
 }
}
