// Explicit direct Bitmap carrier replacement inside an already loaded vector.
// Original CPicture STORE persists independent pixels, not a permanent name link.
using System;using System.Collections;using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace McgsInternalBridge {
 internal static partial class NativePictureResources {
  sealed class EmbeddedRasterCarrier {
   internal ContainedLink Member;internal Dictionary<string,object> Cached;
   internal Dictionary<string,object> Row(){var row=Member.Row();row["image_reference_mode"]=0;row["cached_bytes"]=Cached;row["persistence_form"]="independent-embedded-raster";row["permanent_name_dependency"]=false;return row;}
  }
  static EmbeddedRasterCarrier SelectEmbedded(ContainedInventory inventory,string resource,object path){
   EmbeddedRasterCarrier found=null;string wanted=ContainedPathObject(path);
   foreach(var item in inventory.Embedded)if(item.Member.Resource==resource&&ContainedPathObject(item.Member.ImagePath)==wanted){NativeMemory.Require(found==null,"Explicit embedded carrier path repeats.");found=item;}
   NativeMemory.Require(found!=null,"Explicit carrier path is not a loaded direct Bitmap private raster with a nonempty cache and no frames.");return found;
  }
  static string ContainedPathObject(object value){return NativeUsableEditPermit.Json(value);}
  static Dictionary<string,object> ContainedActionCapture(ContainedApi api,Dictionary<string,object> action,ContainedInventory inventory=null){
   var current=inventory??ContainedScan(api.Pictures);var result=ContainedCapture(api,current);var target=Map(action["target"]);
   if(target.ContainsKey("carrier_image_path")){NativeMemory.Require(Number(target["module_id"])==11,"Private carrier action must target module11.");var selected=SelectEmbedded(current,Convert.ToString(target["name"]),target["carrier_image_path"]);result["selected_embedded_raster_carrier"]=selected.Row();}
   return result;
  }
  sealed class PreparedPrivateRasterContained:INativePreparedPageControlEdit,INativePreparedRelatedPersistence {
   readonly ContainedApi api;readonly Dictionary<string,object> action,before,replacementPicture;readonly EmbeddedRasterCarrier selected;
   readonly string resource,newName;readonly NativeStrategyProfile.CString replacement,resourceName;
   Dictionary<string,object> actualAfter,normalization;bool entered,applied,failed,disposed;
   internal PreparedPrivateRasterContained(ContainedApi value,Dictionary<string,object> request){
    api=value;action=request;NativeMemory.Require(NativePageControlPreparation.Kind(action)==ContainedReferenceKind&&Convert.ToString(action["abi_profile_sha256"])==ContainedReferenceProfileSha,"Private raster action kind/ABI differs.");
    var target=Map(action["target"]);NativeMemory.Require(target.Count==3&&target.ContainsKey("module_id")&&target.ContainsKey("name")&&target.ContainsKey("carrier_image_path")&&Number(target["module_id"])==11,"Private raster target requires module_id, resource name and exact carrier_image_path only.");
    resource=Convert.ToString(target["name"]);NativePageControlPreparation.Name(resource);var desired=Map(action["after"]);
    NativeMemory.Require(desired.Count==5&&desired.ContainsKey("to_picture")&&desired.ContainsKey("expected_reference_count")&&Number(desired["expected_reference_count"])==1,"Private raster replacement requires one exact carrier and target picture.");
    foreach(string key in new[]{"allow_original_content_hash_recompute","allow_original_private_raster_replacement","accept_original_standalone_embedded_persistence"})NativeMemory.Require(desired.ContainsKey(key)&&Object.Equals(desired[key],true),"Private raster replacement needs explicit original effect permission: "+key);
    newName=Convert.ToString(desired["to_picture"]);NativePageControlPreparation.Name(newName);NativeMemory.Require(!newName.Equals(resource,StringComparison.OrdinalIgnoreCase),"Private raster replacement cannot reference its own vector resource.");
    api.Pictures.Picture(resource);var inventory=ContainedScan(api.Pictures);selected=SelectEmbedded(inventory,resource,target["carrier_image_path"]);
    var member=selected.Member;NativeMemory.Require(member.Carrier=="CDrawBitmap.embedded_image"&&member.State==IntPtr.Zero&&member.Frame==IntPtr.Zero&&NativeMemory.I32(member.Bitmap,0xC)==0x5009&&member.Image==NativeMemory.Add(member.Bitmap,0xE4),"Private replacement only accepts the exact direct CDrawBitmap+E4 owning image.");
    NativeMemory.Require(Marshal.ReadByte(member.Image,8)==0&&NativeMemory.I32(member.Image,0x14)==0&&Number(selected.Cached["length"])>0,"Selected current image is not a nonempty private raster.");
    // Resetting an owning CByteArray must never release another captured image's
    // buffer. Selection is the explicit path; payload hashes are preimages only.
    IntPtr ownedBuffer=NativeMemory.Ptr(member.Image,0x30);NativeMemory.Require(ownedBuffer!=IntPtr.Zero,"Private raster has no actual owned cache buffer.");
    foreach(uint address in inventory.Images)if(address!=NativeMemory.U(member.Image))NativeMemory.Require(NativeMemory.Ptr(new IntPtr(unchecked((int)address)),0x30)!=ownedBuffer,"Private raster cache aliases another captured image; no reset is permitted.");
    before=ContainedActionCapture(api,action,inventory);NativePageControlPreparation.Before(action,before);
    replacementPicture=Record(api.Pictures.Raw,api.Pictures.Picture(newName));IntPtr targetImage=NativeMemory.Add(api.Pictures.Picture(newName),0x18);
    NativeMemory.Require(Marshal.ReadByte(targetImage,8)==0&&NativeMemory.I32(targetImage,0x14)==0&&((IList)Map(replacementPicture["frames"])["rows"]).Count==0&&Number(Map(replacementPicture["cached_bytes"])["length"])>0,"Replacement must be an existing embedded raster picture with its actual nonempty payload.");
    int cacheStoreKind=NativeMemory.I32(targetImage,0x24);NativeMemory.Require(cacheStoreKind==1||cacheStoreKind==2||cacheStoreKind==3||cacheStoreKind==5,"Replacement does not use the original exact cached-byte STORE branch; do not infer persisted bytes from another representation.");
    NativeMemory.Require(NativeMemory.I32(api.Pictures.Raw.Engine.Address(0xFBFF30),0)==0,"Private replacement requires original registration mode0; it never changes the global mode.");
    try{replacement=new NativeStrategyProfile.CString(api.Pictures.Raw.Common.Shared,newName);resourceName=new NativeStrategyProfile.CString(api.Pictures.Raw.Common.Shared,resource);ValidateBefore();}catch{Dispose();throw;}
   }
   public void ValidatePersistence(NativeUsableEditPermit.Plan plan){if(plan.Commit)plan.RequireModulePersistence(action,11);}
   public void ValidateBefore(){NativeMemory.Require(!disposed&&!entered,"Private raster replacement is disposed/already entered.");api.Check();NativeMemory.Require(NativeMemory.I32(api.Pictures.Raw.Engine.Address(0xFBFF30),0)==0,"Native image registration mode changed before private replacement.");NativePageControlPreparation.Same(before,ContainedActionCapture(api,action),"Private carrier/resource/payload preimage changed before claim.");}
   void InitializedNamed(){
    IntPtr image=selected.Member.Image;api.Pictures.Raw.Table(image,"PictureImage");api.Pictures.Raw.Table(NativeMemory.Add(image,4),"PictureImageSecondary");
    NativeMemory.Require(Marshal.ReadByte(image,8)==1&&NativeMemory.I32(image,0x10)==0&&NativeMemory.I32(image,0x14)==0&&NativeMemory.I32(image,0x18)==0&&NativeMemory.I32(image,0x1C)==0xC0C0C0&&NativeMemory.I32(image,0x20)==0&&NativeMemory.I32(image,0x24)==0&&NativeMemory.I32(image,0x28)==0&&NativeMemory.I32(image,0x78)==0&&NativeMemory.I32(image,0x7C)==0,"Original named initializer did not return its exact declared image state.");
    NativeMemory.Require(Number(api.Pictures.Raw.ByteArray(NativeMemory.Add(image,0x2C))["length"])==0&&((IList)api.Pictures.Raw.FrameList(NativeMemory.Add(image,0x88))["rows"]).Count==0,"Original named initializer retained private pixels or owning frames.");
    NativeMemory.Require(NativeMemory.I32(api.Pictures.Raw.Engine.Address(0xFBFF30),0)==0,"Original image initializer changed global registration mode.");
   }
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);entered=true;try{
    NativeOperationTrace.BeforeMutation("picture-private-carrier-mark-root");api.RootDirty(api.Pictures.Raw.Common.Shared.RootDoc(),1);Marshal.WriteInt32(api.Pictures.Raw.Common.Shared.RootDoc(),0x114,0);
    lease.RequireApplying(action);api.Check();NativeOperationTrace.BeforeMutation("picture-private-carrier-original-named-initializer21");api.InitializeNamedReference(selected.Member.Image);InitializedNamed();
    lease.RequireApplying(action);api.Check();NativeOperationTrace.BeforeMutation("picture-private-carrier-original-name-setter17");api.SetName(selected.Member.Image,replacement.Storage);InitializedNamed();NativeMemory.Require(CString(NativeMemory.Add(selected.Member.Image,0xC),4096)==newName,"Original image setter did not retain the selected replacement name.");
    lease.RequireApplying(action);api.Check();NativeOperationTrace.BeforeMutation("picture-private-carrier-original-content-hash-refresh");api.Refresh(api.Pictures.Raw.Preload,resourceName.Storage,1);NativeOperationTrace.BeforeMutation("picture-private-carrier-original-module-dirty");api.MarkDirty(api.Pictures.Raw.Preload);
    actualAfter=ContainedCapture(api);VerifyAfter(actualAfter);normalization=new Dictionary<string,object>{{"persistence_form","original-CPicture-independent-embedded-raster"},{"permanent_name_link",false},{"carrier_image_path",selected.Member.ImagePath},{"source_picture",newName},{"before_payload",Map(before["selected_embedded_raster_carrier"])["cached_bytes"]},{"expected_persisted_payload",replacementPicture["cached_bytes"]},{"target_mode_after_apply",1},{"original_standalone_store_expands_name_to_pixels",true},{"stored_wire_and_reopen_acceptance_pending",true}};
    applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",ContainedReferenceKind},{"replacement_branch","explicit-private-raster-carrier"},{"changed_reference_count",1},{"before",before},{"after",actualAfter},{"normalized_persistence",normalization},{"canonical_source_picture_modified",false},{"raw_target_image_flag_or_CString_write",false},{"original_initializer21_called",true},{"original_name_setter17_called",true},{"pending_module11_flush",true}};
   }catch{failed=true;throw;}}
   static Dictionary<string,Dictionary<string,object>> ByLocator(object rows){var result=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);foreach(object value in(IEnumerable)rows){var row=Map(value);result.Add(Convert.ToString(row["locator"]),row);}return result;}
   void VerifyAfter(Dictionary<string,object> current){
    InitializedNamed();NativeMemory.Require(CString(NativeMemory.Add(selected.Member.Image,0xC),4096)==newName,"Selected carrier's exact new name changed.");
    NativePageControlPreparation.Same(before["reference_graph"],current["reference_graph"],"Private carrier replacement changed the registered object graph.");
    var oldCatalog=Map(before["resource_catalog"]);var nowCatalog=Map(current["resource_catalog"]);NativePageControlPreparation.Same(oldCatalog["ordered_names"],nowCatalog["ordered_names"],"Private carrier replacement changed picture names/order.");
    var old=RecordMap(oldCatalog);var now=RecordMap(nowCatalog);NativeMemory.Require(old.Count==now.Count&&now.ContainsKey(resource),"Private carrier replacement changed picture count/name.");
    string imageRaw=Hex(NativeMemory.Bytes(selected.Member.Image,0xA4));int touched=0;
    foreach(var pair in old){NativeMemory.Require(now.ContainsKey(pair.Key),"Private carrier replacement removed a picture.");if(pair.Key!=resource){NativePageControlPreparation.Same(pair.Value,now[pair.Key],"Private carrier replacement changed another original picture's full known raw fields or payload.");continue;}var expected=DeepContainedCopy(pair.Value);var actual=now[pair.Key];string hash=Convert.ToString(actual["content_hash"]);NativeMemory.Require(hash.Length==32&&IsLowerHex(hash),"Original replacement resource hash is malformed.");expected["content_hash"]=hash;expected["raw_native_object_hex"]=NativePointerResult(Convert.ToString(expected["raw_native_object_hex"]),Convert.ToString(actual["raw_native_object_hex"]),0x14);PatchSelectedBitmap(expected,actual,imageRaw,ref touched);NativePageControlPreparation.Same(expected,actual,"Private carrier replacement changed data outside its exact owning image and original content hash.");}
    NativeMemory.Require(touched==1,"Explicit private carrier is not one unique Bitmap in the protected draw tree.");
    var beforeRefs=Map(before["contained_references"]);var afterRefs=Map(current["contained_references"]);var oldNamed=ByLocator(beforeRefs["links"]);var newNamed=ByLocator(afterRefs["links"]);
    NativeMemory.Require(newNamed.Count==oldNamed.Count+1&&newNamed.ContainsKey(selected.Member.Locator)&&!oldNamed.ContainsKey(selected.Member.Locator),"Private carrier did not become exactly its requested transient named member.");foreach(var pair in oldNamed)NativePageControlPreparation.Same(pair.Value,newNamed[pair.Key],"Another contained named image changed.");
    var expectedNamed=DeepContainedCopy(Map(before["selected_embedded_raster_carrier"]));expectedNamed.Remove("cached_bytes");expectedNamed.Remove("persistence_form");expectedNamed.Remove("permanent_name_dependency");expectedNamed["image_reference_mode"]=1;expectedNamed["name"]=newName;expectedNamed["image_raw_hex"]=imageRaw;NativePageControlPreparation.Same(expectedNamed,newNamed[selected.Member.Locator],"Private carrier locator/identity changed beyond its declared original image reset and name.");
    var oldEmbedded=ByLocator(beforeRefs["embedded_raster_carriers"]);var newEmbedded=ByLocator(afterRefs["embedded_raster_carriers"]);NativeMemory.Require(oldEmbedded.Count==newEmbedded.Count+1&&oldEmbedded.ContainsKey(selected.Member.Locator)&&!newEmbedded.ContainsKey(selected.Member.Locator),"Embedded raster carrier membership changed outside the one selected path.");foreach(var pair in oldEmbedded)if(pair.Key!=selected.Member.Locator){NativeMemory.Require(newEmbedded.ContainsKey(pair.Key),"Another embedded carrier disappeared.");NativePageControlPreparation.Same(pair.Value,newEmbedded[pair.Key],"Another embedded carrier's raw image or actual payload changed.");}
    foreach(string key in new[]{"root_frames","coverage","registered_graph_is_complete_for_resource_content","other_animation_and_dynamic_component_image_fields_covered"})NativePageControlPreparation.Same(beforeRefs[key],afterRefs[key],"Contained inventory topology/coverage changed unexpectedly.");
   }
   void PatchSelectedBitmap(object expected,object actual,string imageRaw,ref int touched){
    var left=expected as Dictionary<string,object>;var right=actual as Dictionary<string,object>;
    if(left!=null){object complete;if(left.TryGetValue("complete",out complete)&&Convert.ToString(complete)==NativeMemory.Hex(selected.Member.Bitmap)){
      NativeMemory.Require(right!=null&&Convert.ToString(right["complete"])==Convert.ToString(complete)&&Convert.ToString(left["class"])=="CDrawBitmap"&&Number(left["size"])==0x188,"Explicit carrier's concrete Bitmap identity/size changed.");
      string old=Convert.ToString(left["raw_native_object_hex"]),now=Convert.ToString(right["raw_native_object_hex"]);NativeMemory.Require(old.Length==0x188*2&&now.Length==old.Length&&imageRaw.Length==0xA4*2,"Explicit Bitmap/image raw bounds differ.");left["raw_native_object_hex"]=old.Substring(0,0xE4*2)+imageRaw;touched++;
     }foreach(string key in new List<string>(left.Keys))if(right!=null&&right.ContainsKey(key))PatchSelectedBitmap(left[key],right[key],imageRaw,ref touched);return;}
    var a=expected as IList;var b=actual as IList;if(a!=null&&b!=null){NativeMemory.Require(a.Count==b.Count,"Protected picture draw tree shape changed.");for(int i=0;i<a.Count;i++)PatchSelectedBitmap(a[i],b[i],imageRaw,ref touched);}
   }
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(applied&&!failed&&!disposed,"Only a verified private carrier replacement may flush.");lease.BeginFlush(action);lease.RequireModulePersistence(action,11);try{NativePageControlPreparation.Same(actualAfter,ContainedCapture(api),"Private replacement/catalog changed before original save.");NativeOperationTrace.BeforeMutation("picture-private-carrier-original-module11-save");NativeMemory.Require(api.Save(api.Pictures.Raw.Preload)&&Marshal.ReadByte(api.Pictures.Raw.Manager,0x39)==0,"Original private replacement save did not normally return/clear dirty.");var after=ContainedCapture(api);VerifyAfter(after);lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"module_id",11},{"native_save_called",true},{"after",after},{"normalized_persistence",normalization},{"permanent_name_link",false},{"stored_wire_and_reopen_acceptance_pending",true}};}catch{failed=true;throw;}}
   public void Dispose(){if(disposed)return;disposed=true;try{if(replacement!=null)replacement.Dispose();}finally{if(resourceName!=null)resourceName.Dispose();}}
  }
 }
}
