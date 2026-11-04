using System;using System.Collections;using System.Collections.Generic;using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativePictureResources {
  internal static NativeReferenceModulePersistence.IParticipant PrepareReferencePersistence(NativeEngine e,NativeContext c,string p){return new ReferenceParticipant(new EditApi(e,c,p));}
  sealed class ReferenceParticipant:NativeReferenceModulePersistence.IParticipant {
   readonly EditApi api;readonly PV0 dirty;readonly PB0 save;
   internal ReferenceParticipant(EditApi a){api=a;dirty=api.Bind<PV0>("PictureMarkDirty");save=api.Bind<PB0>("PictureSave");}
   public int ModuleId{get{return 11;}}
   public Dictionary<string,object> Capture(){return ReadRaw(api.Raw.Engine,api.Raw.Context,api.Raw.Project);}
   object Semantics(Dictionary<string,object> raw){return new Dictionary<string,object>{{"ordered_names",raw["ordered_names"]},{"records",Logical(raw["records"])}};}
   object Logical(object value){var map=value as Dictionary<string,object>;if(map!=null){var output=new Dictionary<string,object>();foreach(var pair in map)if(pair.Key!="raw_native_object_hex"&&pair.Key!="image_raw_native_hex"&&pair.Key!="raw_name_catalog_complete"&&pair.Key!="name_index_node")output.Add(pair.Key,Logical(pair.Value));return output;}if(value is IEnumerable&&!(value is string)){var rows=new List<object>();foreach(object item in(IEnumerable)value)rows.Add(Logical(item));return rows;}return value;}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease,Dictionary<string,object> action){var before=Capture();NativeOperationTrace.BeforeMutation("reference-picture-original-dirty");dirty(api.Raw.Preload);NativeOperationTrace.BeforeMutation("reference-picture-original-save");bool returned=save(api.Raw.Preload);NativeMemory.Require(returned&&Marshal.ReadByte(api.Raw.Manager,0x39)==0,"Related original Picture save failed/left dirty.");var after=Capture();NativePageControlPreparation.Same(Semantics(before),Semantics(after),"Related Picture save changed known names/content/frame/vector values.");return new Dictionary<string,object>{{"module_id",11},{"native_save_called",true},{"native_return",returned},{"known_resource_semantics_equal",true},{"full_unknown_image_payload_claimed",false},{"file_acceptance_verified",false}};}
   public void Dispose(){}
  }
 }
}
