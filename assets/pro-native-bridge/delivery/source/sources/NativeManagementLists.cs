// Select an actual management UI list by its proven type, independently of the
// number/order of installed product modules.
using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static class NativeManagementLists {
  internal static IntPtr FindUnique(IntPtr array,Func<IntPtr,bool> matches,Action<IntPtr> verify,string description){
   string before=BitConverter.ToString(NativeMemory.Bytes(array,16));var items=NativeDynamicCollections.ReadUniquePointerArray(array);IntPtr found=IntPtr.Zero;
   foreach(IntPtr item in items)if(matches(item)){NativeMemory.Require(found==IntPtr.Zero,"More than one native "+description+" matches the current type.");verify(item);found=item;}
   NativeMemory.Require(before==BitConverter.ToString(NativeMemory.Bytes(array,16)),"Native management-list array changed during discovery.");NativeMemory.Require(found!=IntPtr.Zero,"Native "+description+" is absent.");return found;
  }
 }
}
