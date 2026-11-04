using System;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal static object CollectionKnownValues(NativeEngine e,NativeContext c,string project,IntPtr full,string className){
   if(className!="CDrawHisPic"&&className!="CDrawSaveData")return null;
   var a=new CollectionApi(e,c,project);NativeMemory.Require(a.Drawing.Type(full).Name==className,"Collection snapshot concrete type differs.");
   var spec=a.Spec(className);return a.Records(NativeMemory.Add(full,Num(spec["array_offset"])),spec);
  }
 }
}
