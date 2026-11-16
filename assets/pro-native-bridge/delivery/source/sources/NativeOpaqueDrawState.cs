// Read-only preservation of non-target CDraw objects. No unknown virtual method
// or private derived field is called/read; lifecycle operations still require a
// fully supported target class and subtree.
using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;
namespace McgsInternalBridge {
 internal static class NativeOpaqueDrawState {
  [ThreadStatic]static LoadedImageRanges requestImages;
  internal static LoadedImageRanges RequestImages {get{return requestImages??(requestImages=new LoadedImageRanges());}}
  internal static void ResetRequestImages(){requestImages=null;}
  // One operation may reuse image bounds. A newly loaded module refreshes on
  // demand; VirtualQuery still validates every accessed native memory range.
  internal sealed class LoadedImageRanges {
   struct Range {internal ulong First,Last;internal string File;}
   readonly List<Range> ranges=new List<Range>();
   internal readonly Dictionary<Tuple<IntPtr,IntPtr>,Rtti> Tables=new Dictionary<Tuple<IntPtr,IntPtr>,Rtti>();
   internal LoadedImageRanges(){Refresh();}
   void Refresh(){ranges.Clear();
    using(var process=Process.GetCurrentProcess())foreach(ProcessModule module in process.Modules){
     ulong first=NativeMemory.U(module.BaseAddress);
     ranges.Add(new Range{First=first,Last=first+(uint)module.ModuleMemorySize,File=Path.GetFullPath(module.FileName)});
    }
   }
   internal void Check(IntPtr pointer,int bytes){
    NativeMemory.Require(bytes>=0,"Negative RTTI range.");
    ulong start=NativeMemory.U(pointer),end=start+(uint)bytes;
    NativeMemory.Require(end<=0x100000000UL,"RTTI range overflows x86.");
    foreach(Range range in ranges)if(start>=range.First&&end<=range.Last){NativeMemory.Readable(pointer,bytes);return;}
    Refresh();foreach(Range range in ranges)if(start>=range.First&&end<=range.Last){NativeMemory.Readable(pointer,bytes);return;}
    throw NativeAbiTargetProfiles.Problem("abi_layout_mismatch","Native RTTI or table entry is outside loaded images.","loaded RTTI images",NativeMemory.Hex(pointer));
   }
   internal IntPtr Owner(IntPtr pointer,out string file){
    Check(pointer,1);ulong value=NativeMemory.U(pointer);
    foreach(Range range in ranges)if(value>=range.First&&value<range.Last){file=range.File;return new IntPtr(unchecked((int)range.First));}
    throw NativeAbiTargetProfiles.Problem("abi_layout_mismatch","Native address has no loaded module.","loaded RTTI images",NativeMemory.Hex(pointer));
   }
   internal int Relative(IntPtr pointer){Check(pointer,1);ulong value=NativeMemory.U(pointer);foreach(Range range in ranges)if(value>=range.First&&value<range.Last)return checked((int)(value-range.First));throw new InvalidOperationException("Native address has no loaded module.");}
  }
  internal sealed class Rtti {
   internal string Name;internal IntPtr Table,Col,Type,Hierarchy;
   internal readonly List<Dictionary<string,object>> Bases=new List<Dictionary<string,object>>();
   internal int Offset,ObjectOffset=-1;internal bool Draw,Unit;
  }
  static Rtti ReadRtti(LoadedImageRanges ranges,IntPtr instance,int expectedOffset){
   IntPtr table=NativeMemory.Ptr(instance,0),col=NativeMemory.Ptr(table,-4);
   var key=Tuple.Create(table,col);Rtti cached;
   if(ranges.Tables.TryGetValue(key,out cached)){
    NativeAbiTargetProfiles.RequireLayout(cached.Offset==expectedOffset,"Live control base offset differs.","drawing RTTI",cached.Name);
    return cached;
   }
   ranges.Check(NativeMemory.Add(table,-4),8);ranges.Check(col,20);
   NativeAbiTargetProfiles.RequireLayout(NativeMemory.I32(col,0)==0&&NativeMemory.I32(col,4)==expectedOffset&&NativeMemory.I32(col,8)==0,"Control primary/base RTTI layout differs.","drawing RTTI","COL");
   IntPtr type=NativeMemory.Ptr(col,12),hierarchy=NativeMemory.Ptr(col,16);ranges.Check(type,9);ranges.Check(hierarchy,16);
   string name=NativeMemory.Ascii(NativeMemory.Add(type,8),Int32.MaxValue);int count=NativeMemory.I32(hierarchy,8);
   NativeAbiTargetProfiles.RequireLayout(count>0,"Control RTTI hierarchy is empty.","drawing RTTI",name);
   IntPtr array=NativeMemory.Ptr(hierarchy,12);ranges.Check(array,checked(count*4));
   var result=new Rtti{Name=name,Table=table,Col=col,Type=type,Hierarchy=hierarchy,Offset=expectedOffset};
   for(int i=0;i<count;i++){
    IntPtr descriptor=NativeMemory.Ptr(array,checked(i*4));ranges.Check(descriptor,24);IntPtr baseType=NativeMemory.Ptr(descriptor,0);ranges.Check(baseType,9);
    string baseName=NativeMemory.Ascii(NativeMemory.Add(baseType,8),Int32.MaxValue);
    int m=NativeMemory.I32(descriptor,8),p=NativeMemory.I32(descriptor,12),v=NativeMemory.I32(descriptor,16);
    if(p==-1&&m==0&&baseName==".?AVCDrawObj@@")result.Draw=true;
    if(p==-1&&m>0&&baseName==".?AVIObject@@"){
     NativeAbiTargetProfiles.RequireLayout(result.ObjectOffset<0||result.ObjectOffset==m,"Control has ambiguous direct IObject bases.","drawing RTTI",name);
     result.ObjectOffset=m;
    }
    if(p==-1&&m==0&&baseName==".?AVCDrawUnit@@")result.Unit=true;
    result.Bases.Add(new Dictionary<string,object>{{"rtti",baseName},{"descriptor",NativeMemory.Hex(descriptor)},{"type",NativeMemory.Hex(baseType)},{"contained",NativeMemory.I32(descriptor,4)},{"mdisp",m},{"pdisp",p},{"vdisp",v},{"attributes",NativeMemory.I32(descriptor,20)}});
   }
   ranges.Tables.Add(key,result);return result;
  }
  static IntPtr ObjectBase(IntPtr full,LoadedImageRanges ranges,Rtti primary,out Rtti secondary){
   if(!primary.Draw||primary.ObjectOffset<=0)throw NativeAbiTargetProfiles.Problem("unsupported_feature","Control has no proven direct CDrawObj/IObject bases.","drawing RTTI",primary.Name);
   IntPtr instance=NativeMemory.Add(full,primary.ObjectOffset);
   secondary=ReadRtti(ranges,instance,primary.ObjectOffset);
   NativeAbiTargetProfiles.RequireLayout(primary.Type==secondary.Type&&primary.Hierarchy==secondary.Hierarchy&&primary.Name==secondary.Name,"Control primary and IObject RTTI identities differ.","drawing RTTI",primary.Name);
   return instance;
  }
  internal static IntPtr ControlObject(IntPtr full) {
   var ranges=RequestImages;Rtti secondary;return ObjectBase(full,ranges,ReadRtti(ranges,full,0),out secondary);
  }
  internal static bool TryControlObject(IntPtr full,out IntPtr instance,out string rtti) {
   var ranges=RequestImages;try{
    Rtti secondary;var primary=ReadRtti(ranges,full,0);rtti=primary.Name;
    if(!primary.Draw||primary.ObjectOffset<=0){instance=IntPtr.Zero;return false;}
    instance=ObjectBase(full,ranges,primary,out secondary);return true;
   }catch(NativeCompatibilityException error){
    if(!NativeAbiTargetProfiles.IsUnavailableFeature(error))throw;
    instance=IntPtr.Zero;rtti=null;return false;
   }
  }
  internal static Dictionary<string,object> Capture(IntPtr full,IntPtr document,bool unitLayoutAvailable,out bool unit,LoadedImageRanges ranges=null){
   if(ranges==null)ranges=RequestImages;var primary=ReadRtti(ranges,full,0);Rtti secondary;
   ObjectBase(full,ranges,primary,out secondary);
   NativeMemory.Require(NativeMemory.Ptr(full,NativeLayout.Offset("control.owner_document"))==document,"Opaque CDraw document owner differs.");
   unit=unitLayoutAvailable&&primary.Unit;
   return new Dictionary<string,object>{{"opaque",true},{"rtti",primary.Name},{"class",primary.Name},{"type_id",NativeMemory.I32(full,NativeLayout.Offset("control.type_id"))},{"complete",NativeMemory.Hex(full)},{"owner_document",NativeMemory.Hex(document)},{"primary_vtable",NativeMemory.Hex(primary.Table)},{"iobject_vtable",NativeMemory.Hex(secondary.Table)},{"rtti_col",NativeMemory.Hex(primary.Col)},{"rtti_type",NativeMemory.Hex(primary.Type)},{"rtti_hierarchy",NativeMemory.Hex(primary.Hierarchy)},{"rtti_bases",primary.Bases},{"rectangle",NativePageControlAbi.Rectangle(full)},{"raw_DWORD60",unchecked((uint)NativeMemory.I32(full,NativeLayout.Offset("control.raw_state")))},{"raw_DWORDB0",unchecked((uint)NativeMemory.I32(full,0xB0))},{"preservation_scope","proven_common_identity_geometry_state; derived_private_payload_not_interpreted"},{"unknown_virtual_called",false},{"known_unit_base",unit}};
  }
 }
}
