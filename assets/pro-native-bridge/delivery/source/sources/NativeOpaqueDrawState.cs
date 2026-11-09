// Read-only preservation of non-target CDraw objects. No unknown virtual method
// or private derived field is called/read; lifecycle operations still require a
// fully supported target class and subtree.
using System;using System.Collections.Generic;using System.Diagnostics;
namespace McgsInternalBridge {
 internal static class NativeOpaqueDrawState {
  // Only keep these image bounds for one read-only capture. In particular,
  // never reuse them across a native call that can open or mutate a document.
  internal sealed class LoadedImageRanges {
   struct Range {internal ulong First,Last;}
   readonly List<Range> ranges=new List<Range>();
   internal LoadedImageRanges(){
    using(var process=Process.GetCurrentProcess())foreach(ProcessModule module in process.Modules){
     ulong first=NativeMemory.U(module.BaseAddress);
     ranges.Add(new Range{First=first,Last=first+(uint)module.ModuleMemorySize});
    }
   }
   internal void Check(IntPtr pointer,int bytes){
    NativeMemory.Require(bytes>=0,"Negative RTTI range.");
    ulong start=NativeMemory.U(pointer),end=start+(uint)bytes;
    NativeMemory.Require(end<=0x100000000UL,"RTTI range overflows x86.");
    foreach(Range range in ranges)if(start>=range.First&&end<=range.Last){NativeMemory.Readable(pointer,bytes);return;}
    throw new InvalidOperationException("Opaque CDraw metadata is outside loaded images.");
   }
  }
  sealed class Rtti {internal string Name;internal IntPtr Table,Col,Type,Hierarchy;internal readonly List<Dictionary<string,object>> Bases=new List<Dictionary<string,object>>();internal bool Draw,Object,Unit;}
  static Rtti ReadRtti(LoadedImageRanges ranges,IntPtr instance,int expectedOffset,IntPtr drawType,IntPtr objectType,IntPtr unitType){
   IntPtr table=NativeMemory.Ptr(instance,0);ranges.Check(NativeMemory.Add(table,-4),8);IntPtr col=NativeMemory.Ptr(table,-4);ranges.Check(col,20);NativeMemory.Require(NativeMemory.I32(col,0)==0&&NativeMemory.I32(col,4)==expectedOffset&&NativeMemory.I32(col,8)==0,"Opaque CDraw primary/base RTTI layout differs.");
   IntPtr type=NativeMemory.Ptr(col,12),hierarchy=NativeMemory.Ptr(col,16);ranges.Check(type,9);ranges.Check(hierarchy,16);string name=NativeMemory.Ascii(NativeMemory.Add(type,8),256);int count=NativeMemory.I32(hierarchy,8);NativeMemory.Require(count>0,"Opaque CDraw RTTI hierarchy is empty.");IntPtr array=NativeMemory.Ptr(hierarchy,12);ranges.Check(array,checked(count*4));var result=new Rtti{Name=name,Table=table,Col=col,Type=type,Hierarchy=hierarchy};
   for(int i=0;i<count;i++){IntPtr descriptor=NativeMemory.Ptr(array,checked(i*4));ranges.Check(descriptor,24);IntPtr baseType=NativeMemory.Ptr(descriptor,0);ranges.Check(baseType,9);string baseName=NativeMemory.Ascii(NativeMemory.Add(baseType,8),256);int m=NativeMemory.I32(descriptor,8),p=NativeMemory.I32(descriptor,12),v=NativeMemory.I32(descriptor,16);if(p==-1&&m==0&&baseType==drawType&&baseName==".?AVCDrawObj@@")result.Draw=true;if(p==-1&&m==4&&baseType==objectType&&baseName==".?AVIObject@@")result.Object=true;if(unitType!=IntPtr.Zero&&p==-1&&m==0&&baseType==unitType&&baseName==".?AVCDrawUnit@@")result.Unit=true;result.Bases.Add(new Dictionary<string,object>{{"rtti",baseName},{"descriptor",NativeMemory.Hex(descriptor)},{"type",NativeMemory.Hex(baseType)},{"contained",NativeMemory.I32(descriptor,4)},{"mdisp",m},{"pdisp",p},{"vdisp",v},{"attributes",NativeMemory.I32(descriptor,20)}});}
   NativeMemory.Require(result.Draw&&result.Object,"Opaque non-target object lacks the proven CDrawObj/IObject common bases.");return result;
  }
  internal static Dictionary<string,object> Capture(IntPtr full,IntPtr document,IntPtr drawType,IntPtr objectType,IntPtr unitType,out bool unit){
   var ranges=new LoadedImageRanges();var primary=ReadRtti(ranges,full,0,drawType,objectType,unitType);var secondary=ReadRtti(ranges,NativeMemory.Add(full,4),4,drawType,objectType,unitType);NativeMemory.Require(primary.Type==secondary.Type&&primary.Hierarchy==secondary.Hierarchy&&primary.Name==secondary.Name,"Opaque CDraw primary/IObject identity differs.");NativeMemory.Readable(full,0xE4);NativeMemory.Require(NativeMemory.Ptr(full,0x64)==document,"Opaque CDraw document owner differs.");unit=primary.Unit;
   return new Dictionary<string,object>{{"opaque",true},{"rtti",primary.Name},{"class",primary.Name},{"type_id",NativeMemory.I32(full,0xC)},{"complete",NativeMemory.Hex(full)},{"owner_document",NativeMemory.Hex(document)},{"primary_vtable",NativeMemory.Hex(primary.Table)},{"iobject_vtable",NativeMemory.Hex(secondary.Table)},{"rtti_col",NativeMemory.Hex(primary.Col)},{"rtti_type",NativeMemory.Hex(primary.Type)},{"rtti_hierarchy",NativeMemory.Hex(primary.Hierarchy)},{"rtti_bases",primary.Bases},{"rectangle",NativePageControlAbi.Rectangle(full)},{"raw_DWORD60",unchecked((uint)NativeMemory.I32(full,0x60))},{"raw_DWORDB0",unchecked((uint)NativeMemory.I32(full,0xB0))},{"preservation_scope","proven_common_identity_geometry_state; derived_private_payload_not_interpreted"},{"unknown_virtual_called",false},{"known_unit_base",unit}};
  }
 }
}
