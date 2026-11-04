// Minimal shared property interface. A component may be IPropertyLinker without
// the IObject child/module methods at19/20; never enumerate those extra slots.
using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static class NativePropertyTarget {
  internal static Dictionary<string,object> Describe(NativeEngine engine,IntPtr pointer) {
   IntPtr table=NativeMemory.Ptr(pointer,0);engine.Rva(table);IntPtr col=NativeMemory.Ptr(table,-4);engine.Rva(col);
   int offset=NativeMemory.I32(col,4);NativeMemory.Require(NativeMemory.I32(col,0)==0&&offset>=0&&offset<=4096,"Property target complete-object locator differs.");
   IntPtr type=NativeMemory.Ptr(col,12),hierarchy=NativeMemory.Ptr(col,16);engine.Rva(type);engine.Rva(hierarchy);
   string name=NativeMemory.Ascii(NativeMemory.Add(type,8),256);int count=NativeMemory.I32(hierarchy,8);NativeMemory.Require(count>0&&count<=128,"Property target RTTI hierarchy exceeds bound.");
   IntPtr array=NativeMemory.Ptr(hierarchy,12);engine.Rva(array);bool directObject=false,directLinker=false;
   for(int i=0;i<count;i++) {
    IntPtr descriptor=NativeMemory.Ptr(array,4*i),baseType=NativeMemory.Ptr(descriptor,0);engine.Rva(descriptor);engine.Rva(baseType);
    string baseName=NativeMemory.Ascii(NativeMemory.Add(baseType,8),256);
    if(NativeMemory.I32(descriptor,8)!=offset||NativeMemory.I32(descriptor,12)!=-1)continue;
    if(baseName==".?AVIObject@@")directObject=true;
    if(baseName==".?AVIPropertyLinker@ObjectTree@@")directLinker=true;
   }
   NativeMemory.Require(directObject||directLinker,"Native component does not expose a supported direct property interface at this exact pointer.");
   // Only these two slots are part of the required property contract.
   IntPtr setter=NativeMemory.Ptr(table,5*4),getter=NativeMemory.Ptr(table,6*4);engine.Rva(setter);engine.Rva(getter);NativeMemory.Readable(setter,1);NativeMemory.Readable(getter,1);
   return new Dictionary<string,object>{{"address",NativeMemory.Hex(pointer)},{"rtti",name},{"complete_offset",offset},{"property_interface",directObject?"IObject":"ObjectTree::IPropertyLinker"},
    {"vtable_rva","0x"+engine.Rva(table).ToString("X")},{"setter",NativeMemory.Hex(setter)},{"getter",NativeMemory.Hex(getter)},{"IObject_children_or_module_methods_called",false}};
  }
 }
}
