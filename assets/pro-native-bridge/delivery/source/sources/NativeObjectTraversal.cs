// Shared production IObject description/iteration body. Callbacks use the caller's
// verified image/virtual ABI; isolated tests supply only their own allocated image.
using System;using System.Collections.Generic;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static class NativeObjectTraversal {
  internal static Dictionary<string,object> Describe(IntPtr instance,Func<IntPtr,int> rva,Func<IntPtr,int,int> callInt){
   IntPtr table=NativeMemory.Ptr(instance,0);rva(table);IntPtr col=NativeMemory.Ptr(table,-4);rva(col);
   int completeOffset=NativeMemory.I32(col,4);NativeMemory.Require(completeOffset>=0&&completeOffset<4096,"Invalid object RTTI offset.");
   IntPtr type=NativeMemory.Ptr(col,12);rva(type);string typeName=NativeMemory.Ascii(NativeMemory.Add(type,8),256);
   IntPtr hierarchy=NativeMemory.Ptr(col,16);rva(hierarchy);int count=NativeMemory.I32(hierarchy,8);NativeMemory.Require(count>0&&count<=128,"Invalid RTTI hierarchy.");
   IntPtr array=NativeMemory.Ptr(hierarchy,12);rva(array);bool isObject=false;
   for(int i=0;i<count;i++){IntPtr descriptor=NativeMemory.Ptr(array,4*i);rva(descriptor);IntPtr baseType=NativeMemory.Ptr(descriptor,0);rva(baseType);string name=NativeMemory.Ascii(NativeMemory.Add(baseType,8),256);if(name==".?AVIObject@@"&&NativeMemory.I32(descriptor,8)==completeOffset&&NativeMemory.I32(descriptor,12)==-1)isObject=true;}
   NativeMemory.Require(isObject,"Returned object is not the verified nonvirtual IObject base: "+typeName);
   int children=callInt(instance,19);NativeMemory.Require(children>=0,"Object child count is negative.");int module=callInt(instance,20);
   return new Dictionary<string,object>{{"address",NativeMemory.Hex(instance)},{"rtti",typeName},{"vtable_rva","0x"+rva(table).ToString("X")},{"complete_offset",completeOffset},{"module",module},{"child_count",children}};
  }
  internal static List<IntPtr> Children(IntPtr owner,Func<IntPtr,Dictionary<string,object>> describe,Action<IntPtr,IntPtr> construct,Func<IntPtr,IntPtr,bool> first,Func<IntPtr,IntPtr,bool> next,Action<IntPtr> destroy){
   describe(owner);IntPtr iter=Marshal.AllocHGlobal(16);bool constructed=false;var children=new List<IntPtr>();var seen=new HashSet<uint>();
   try{
    for(int i=0;i<16;i++)Marshal.WriteByte(iter,i,0);construct(iter,owner);constructed=true;NativeMemory.Require(NativeMemory.Ptr(iter,12)==owner,"Iterator owner differs.");
    bool has=first(owner,iter);
    // First can perform the original lazy page load. Count is authoritative only
    // after that transition, rather than treating a pre-load zero as a quota.
    int count=Convert.ToInt32(describe(owner)["child_count"]);
    while(has){NativeMemory.Require(NativeMemory.Ptr(iter,12)==owner,"Iterator owner changed.");NativeMemory.Require(children.Count<count,"Native child iterator yielded more than its actual owner count.");IntPtr child=NativeMemory.Ptr(iter,8);NativeMemory.Require(child!=IntPtr.Zero&&seen.Add(NativeMemory.U(child)),"Iterator returned an empty/repeated object or a cycle.");describe(child);children.Add(child);has=next(owner,iter);}
    NativeMemory.Require(NativeMemory.Ptr(iter,12)==owner&&children.Count==count&&Convert.ToInt32(describe(owner)["child_count"])==count,"Native child iterator end/count/owner changed.");
   }finally{try{if(constructed)destroy(iter);}finally{Marshal.FreeHGlobal(iter);}}
   return children;
  }
 }
}
