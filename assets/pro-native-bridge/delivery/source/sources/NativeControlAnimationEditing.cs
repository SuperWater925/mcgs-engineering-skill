// Original CAni factory/Serialize ownership and whole-list commit, under the unified Lease.
using System;using System.Collections;using System.Collections.Generic;using System.Globalization;using System.Runtime.InteropServices;
using A=McgsInternalBridge.NativeAnimationListEditing;
namespace McgsInternalBridge {
 internal static partial class NativeCurrentTemplateControlOperations {
  internal const string AnimationKind="control-animation-list";
  [UnmanagedFunctionPointer(CallingConvention.ThisCall)]delegate void AnimationPropertySetter(IntPtr self,IntPtr sink);
  sealed class AnimationApi {
   internal readonly Api Drawing;internal readonly A.OwnedApi Owned;internal readonly string Project;
   internal AnimationApi(NativeEngine e,NativeContext c,string p){Drawing=new Api(e,c,p);Owned=new A.OwnedApi(e,Drawing.Shared.Shared);Project=p;}
  }
  static Dictionary<string,object> AnimationCapture(AnimationApi api,Dictionary<string,object> action){
   IntPtr page,doc;Node target=api.Drawing.Locate(Map(action["target"]),out page,out doc);var sourceRows=new List<object>();object after;if(action.TryGetValue("after",out after)&&Map(after).ContainsKey("items"))foreach(object value in(IEnumerable)Map(after)["items"]){var item=Map(value);if(!item.ContainsKey("source"))continue;var src=Map(item["source"]);IntPtr sp,sd;Node sn=api.Drawing.Locate(Map(src["control"]),out sp,out sd);var values=api.Owned.Raw.Items(sn.Full);int index=Num(src["index"]);NativeMemory.Require(index>=0&&index<values.Count,"Animation source index absent.");sourceRows.Add(new Dictionary<string,object>{{"source",src},{"source_control",Snapshot(api.Drawing,sn)},{"source_page",api.Drawing.Shared.PageSnapshot(sp)},{"source_list_raw",api.Owned.Raw.Records(sn.Full)},{"source_list_values",api.Owned.Records(sn.Full)}});}
   var forest=api.Drawing.Forest(doc);var pageAnimations=new List<object>();foreach(Node node in Flatten(forest)){if(node.Class==null)pageAnimations.Add(new Dictionary<string,object>{{"control",NativeMemory.Hex(node.Full)},{"path",node.Path},{"opaque_control",Snapshot(api.Drawing,node)}});else pageAnimations.Add(new Dictionary<string,object>{{"control",NativeMemory.Hex(node.Full)},{"path",node.Path},{"raw",api.Owned.Raw.Records(node.Full)},{"values",api.Owned.Records(node.Full)}});}
   return new Dictionary<string,object>{{"abi_profile_sha256",A.OwnedProfileSha},{"raw_abi_profile_sha256",A.ProfileSha},{"target_control",Snapshot(api.Drawing,target)},{"page",api.Drawing.Shared.PageSnapshot(page)},{"page_control_forest",AnimationSnapshotForest(api.Drawing,forest)},{"history_store_projection",NativeHistoryStoreProjection.Prepare(api.Drawing.Engine,doc).Before},{"page_animation_lists",pageAnimations},{"items",api.Owned.Records(target.Full)},{"items_raw",api.Owned.Raw.Records(target.Full)},{"source_items",sourceRows},{"full_serialization_preimage",false}};
  }
  // The forest is local to this capture/Verify boundary; no node is reused across mutation.
  static List<object> AnimationSnapshotForest(Api api,List<Node> forest){var result=new List<object>();foreach(Node node in forest)result.Add(Snapshot(api,node));return result;}
  internal static Dictionary<string,object> ReadAnimations(NativeEngine e,NativeContext c,string p,Dictionary<string,object> a){return AnimationCapture(new AnimationApi(e,c,p),a);}
  internal static INativePreparedPageControlEdit PrepareAnimations(NativeEngine e,NativeContext c,string p,Dictionary<string,object> a){return new PreparedAnimations(new AnimationApi(e,c,p),a);}
  sealed class PreparedAnimations:INativePreparedPageControlEdit {
   sealed class Item:IDisposable {
    internal IntPtr Source,Private;internal Dictionary<string,object> Type,SourceValues,SerializedCloneBaseline,Expected,Updates,SizeDimensionRestoration,VMoveDimensionRestoration,InputBindingPreimage;internal NativeTypedPropertyDispatcher Properties;
    internal A.Factory Factory;internal A.Serial Serialize;internal A.Owner SetOwner;internal A.Delete Delete;internal AnimationPropertySetter SetProperties;
    internal bool Retained;internal bool ConstructorReturned,AdoptionEntered,VerifyCloneAfterOwner;public void Dispose(){if(Properties!=null){Properties.Dispose();Properties=null;}}
   }
   readonly NativeHistoryStoreProjection historyState;readonly AnimationApi api;readonly Dictionary<string,object> action,before;readonly Node target;readonly IntPtr page,doc,view,array;readonly List<Item> items=new List<Item>();readonly Dictionary<uint,A.Delete> oldDestructors=new Dictionary<uint,A.Delete>();readonly HashSet<IntPtr> retained=new HashSet<IntPtr>();readonly BeforeModify modify;readonly VI rootDirty,docDirty,invalidate;readonly V0 update;readonly SaveData save;readonly NativeEngine.ThisInt isModified;
   bool nativeUnknown,failed,applied,disposed;IntPtr file,store,load;bool fileLive,storeLive,loadLive;
   NativeDataEngineering.Api inputData;
   internal PreparedAnimations(AnimationApi a,Dictionary<string,object> request){
    api=a;action=request;NativeMemory.Require(NativePageControlPreparation.Kind(action)==AnimationKind&&Convert.ToString(action["abi_profile_sha256"])==A.OwnedProfileSha,"Animation kind/ABI differs.");target=api.Drawing.Locate(Map(action["target"]),out page,out doc);historyState=NativeHistoryStoreProjection.Prepare(api.Drawing.Engine,doc);view=api.Drawing.View(doc);array=NativeMemory.Add(target.Full,0x9C);var after=Map(action["after"]);NativeMemory.Require(Object.Equals(after["allow_original_owned_list_rebuild"],true)&&Object.Equals(after["defer_native_final_compile_and_reference_rebuild"],true),"Animation list needs explicit original whole-list rebuild and deferred final compile.");foreach(string key in after.Keys)NativeMemory.Require(key=="items"||key=="expected_existing_items"||key=="allow_original_owned_list_rebuild"||key=="defer_native_final_compile_and_reference_rebuild"||key=="history_property13_projection","Unknown animation after field.");
    uint history=unchecked((uint)NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated")));if(after.ContainsKey("history_property13_projection")){var h=Map(after["history_property13_projection"]);NativeMemory.Require(h.Count==2&&Convert.ToUInt32(h["before_raw_uint32"],CultureInfo.InvariantCulture)==history&&Convert.ToUInt32(h["after_raw_uint32"],CultureInfo.InvariantCulture)==0,"Animation history raw13 projection differs.");}else NativeMemory.Require(history==0,"Nonzero raw13 needs its explicit original history projection.");
    modify=api.Drawing.ViewBind<BeforeModify>("DocBeforeModify");rootDirty=api.Drawing.Shared.Shared.Bind<VI>("RootSetModified");docDirty=api.Drawing.Shared.Bind<VI>("standard","DocSetModified");invalidate=api.Drawing.ViewBind<VI>("InvalidateView");update=api.Drawing.ViewBind<V0>("UpdateView");save=api.Drawing.Shared.Bind<SaveData>("standard","WindowSaveData");isModified=api.Drawing.Shared.Shared.Bind<NativeEngine.ThisInt>("RootIsModified");api.Drawing.Shared.Slot(doc,96,0x3CBE6);api.Drawing.Shared.Slot(doc,27,0x3A3C8);api.Drawing.Shared.Slot(api.Drawing.Context.WindowService,12,0x21733);
    try{before=AnimationCapture(api,action);if(after.ContainsKey("expected_existing_items"))NativePageControlPreparation.Same(after["expected_existing_items"],before["items"],"Animation records changed since the edit plan was prepared.");NativePageControlPreparation.Before(action,before);foreach(object value in(IEnumerable)after["items"]){NativeMemory.Require(items.Count<=Int32.MaxValue/4,"Animation list exceeds its bound.");var row=Map(value);NativeMemory.Require(row.ContainsKey("source")!=row.ContainsKey("new_class"),"Animation item needs one real source or original new_class factory.");foreach(string key in row.Keys)NativeMemory.Require(key=="source"||key=="clone_source"||key=="new_class"||key=="expected_record"||key=="properties"||key=="native_member_updates"||key=="restore_observed_output_clone"||key=="restore_observed_size_clone"||key=="restore_observed_vmove_clone"||key=="restore_observed_palette_clone"||key=="restore_observed_blink_clone"||key=="input_binding_preimage","Unknown animation item field.");if(row.ContainsKey("clone_source"))NativeMemory.Require(row.ContainsKey("source")&&Object.Equals(row["clone_source"],true),"clone_source requires a source and an explicit true value.");var item=new Item{Expected=Map(row["expected_record"])};items.Add(item);string name;bool sameSourceSlot=false;if(row.ContainsKey("source")){var src=Map(row["source"]);IntPtr sp,sd;Node sn=api.Drawing.Locate(Map(src["control"]),out sp,out sd);var sources=api.Owned.Raw.Items(sn.Full);int index=Num(src["index"]);NativeMemory.Require(index>=0&&index<sources.Count,"Animation source index differs.");item.Source=sources[index];item.Type=api.Owned.Raw.Type(item.Source);item.SourceValues=api.Owned.Values(item.Source);
      sameSourceSlot=sp==page&&sd==doc&&sn.Full==target.Full&&index==items.Count-1;
      // One unchanged occurrence may keep the original object and its compiled caches.
      // Further occurrences are independent clones and must pass archive round-trip checks.
      if(sn.Full==target.Full&&!row.ContainsKey("clone_source")&&!row.ContainsKey("native_member_updates")&&!row.ContainsKey("properties")&&retained.Add(item.Source)){
       NativePageControlPreparation.Same(item.Expected,item.SourceValues,"Retained animation differs from its exact expected record.");
       item.Retained=true;
      }
      name=Convert.ToString(item.Type["name"]);}else{name=Convert.ToString(row["new_class"]);item.Type=api.Owned.Class(name);}
      NativeMemory.Require(name!="CAniObj"&&Convert.ToString(item.Expected["class"])==name,"Animation class must be one real standard concrete class and match expected_record.");
      PrepareInputBinding(item,name,row);
      if(row.ContainsKey("restore_observed_output_clone")){
       NativeMemory.Require(Object.Equals(row["restore_observed_output_clone"],true)&&item.Source!=IntPtr.Zero&&!item.Retained&&name=="CAniOutput"&&row.ContainsKey("native_member_updates")&&!row.ContainsKey("properties"),"Output clone restoration needs the observed CAniOutput shape and explicit private member updates.");
       item.SerializedCloneBaseline=ObservedOutputClone(item.SourceValues);
       ValidateOutputRestoration(item,Map(row["native_member_updates"]));
      }
      if(row.ContainsKey("restore_observed_size_clone")){
       NativeMemory.Require(Object.Equals(row["restore_observed_size_clone"],true)&&sameSourceSlot&&!item.Retained&&name=="CAniSize"&&row.ContainsKey("native_member_updates")&&!row.ContainsKey("properties")&&!row.ContainsKey("clone_source"),"Size clone restoration requires updating the original CAniSize slot on the same control.");
       item.SerializedCloneBaseline=PrepareObservedSizeClone(item,Map(row["native_member_updates"]));
      }
      if(row.ContainsKey("restore_observed_vmove_clone")){
       NativeMemory.Require(Object.Equals(row["restore_observed_vmove_clone"],true)&&sameSourceSlot&&!item.Retained
         &&name=="CAniVMove"&&row.ContainsKey("native_member_updates")&&!row.ContainsKey("properties")&&!row.ContainsKey("clone_source"),
         "Vertical movement clone restoration requires updating the original CAniVMove slot on the same control.");
       PrepareObservedVMoveClone(item,Map(row["native_member_updates"]));
      }
      if(row.ContainsKey("restore_observed_palette_clone")){
       NativeMemory.Require(Object.Equals(row["restore_observed_palette_clone"],true)&&sameSourceSlot&&!item.Retained
         &&(name=="CAniBrush"||name=="CAniTextColor")&&row.ContainsKey("native_member_updates")
         &&!row.ContainsKey("properties")&&!row.ContainsKey("clone_source"),
         "Palette clone restoration requires updating the original brush or text-color slot on the same control.");
       item.SerializedCloneBaseline=PrepareObservedPaletteClone(item,Map(row["native_member_updates"]));
      }
      if(row.ContainsKey("restore_observed_blink_clone")){
       NativeMemory.Require(Object.Equals(row["restore_observed_blink_clone"],true)&&sameSourceSlot&&!item.Retained
         &&name=="CAniBlink"&&row.ContainsKey("native_member_updates")&&!row.ContainsKey("properties")
         &&!row.ContainsKey("clone_source"),
         "Blink clone restoration requires updating the original CAniBlink slot on the same control.");
       item.SerializedCloneBaseline=PrepareObservedBlinkClone(item,Map(row["native_member_updates"]));
       item.VerifyCloneAfterOwner=true;
      }
      if(item.Retained)continue;item.Factory=api.Owned.FactoryFor(item.Type);item.Serialize=api.Owned.Slot<A.Serial>(item.Type,false,2);item.SetOwner=api.Owned.Slot<A.Owner>(item.Type,false,18);item.Delete=api.Owned.Slot<A.Delete>(item.Type,false,1);item.SetProperties=api.Owned.Slot<AnimationPropertySetter>(item.Type,true,5);
      if(row.ContainsKey("native_member_updates")){
       var updates=Map(row["native_member_updates"]);
       ValidateAnimationUpdates(api.Owned,name,updates);
       item.Updates=item.SizeDimensionRestoration==null?updates:new Dictionary<string,object>{{"strings",updates["strings"]}};
      }
      if(row.ContainsKey("properties")){var properties=new List<Dictionary<string,object>>();foreach(object p in(IEnumerable)row["properties"])properties.Add(Map(p));item.Properties=new NativeTypedPropertyDispatcher(api.Drawing.Shared.Shared,properties);}}foreach(IntPtr old in api.Owned.Raw.Items(target.Full))oldDestructors.Add(NativeMemory.U(old),api.Owned.Slot<A.Delete>(api.Owned.Raw.Type(old),false,1));foreach(Item item in items)if(!item.Retained&&item.Source!=IntPtr.Zero){file=Marshal.AllocHGlobal(44);store=Marshal.AllocHGlobal(72);load=Marshal.AllocHGlobal(72);break;}ValidateBefore();}catch{Dispose();throw;}
   }
   static readonly string[] OutputCloneWords={"5c","60","68","6c"};
   static Dictionary<string,object> ObservedOutputClone(Dictionary<string,object> source){
    var words=new Dictionary<string,object>(Map(source["words_uint32"]));
    var bytes=new Dictionary<string,object>(Map(source["byte_arrays_hex"]));
    NativeMemory.Require(words.Count==14&&words.ContainsKey("c")&&Num(words["c"])==0&&
      bytes.Count==1&&bytes.ContainsKey("14")&&Convert.ToString(bytes["14"]).Length==64,
      "The output animation does not have the observed compiled source layout.");
    for(int index=0;index<OutputCloneWords.Length;index++){
     var key=OutputCloneWords[index];int original=index==0?0:1;
     NativeMemory.Require(words.ContainsKey(key)&&Num(words[key])==original,"Output animation source flags differ from the observed serializer contract.");
     words[key]=1-original;
    }
    bytes["14"]="";
    var result=new Dictionary<string,object>(source);result["words_uint32"]=words;result["byte_arrays_hex"]=bytes;return result;
   }
   static void ValidateOutputRestoration(Item item,Dictionary<string,object> updates){
    NativeMemory.Require(updates.ContainsKey("words_uint32"),"The private output clone must restore its observed flag fields.");
    var source=Map(item.SourceValues["words_uint32"]);
    var restored=Map(updates["words_uint32"]);
    foreach(string key in OutputCloneWords)
     NativeMemory.Require(restored.ContainsKey(key)&&Num(restored[key])==Num(source[key]),"An original output animation flag would not be restored.");
    NativePageControlPreparation.Same(Map(item.SerializedCloneBaseline["byte_arrays_hex"]),item.Expected["byte_arrays_hex"],"Only the original output compile cache may be regenerated.");
   }
   static readonly string[] SizeWordKeys={"8","c","30","34","38","3c","40","44","48","4c"};
   static Dictionary<string,object> PrepareObservedSizeClone(Item item,Dictionary<string,object> updates){
    var source=item.SourceValues;
    var words=Map(source["words_uint32"]);
    var strings=Map(source["strings"]);
    var bytes=Map(source["byte_arrays_hex"]);
    NativeMemory.Require(words.Count==SizeWordKeys.Length&&Array.TrueForAll(SizeWordKeys,words.ContainsKey)
      &&strings.Count==1&&strings.ContainsKey("2c")&&Map(source["arrays"]).Count==0
      &&bytes.Count==1&&bytes.ContainsKey("14")&&bytes["14"] is string,
      "The size animation does not have the observed original serialization layout.");
    NativeMemory.Require(updates.Count==2&&updates.ContainsKey("strings")&&updates.ContainsKey("words_uint32"),
      "A size clone requires exactly an expression update and restoration of both original dimension words.");
    var changedStrings=Map(updates["strings"]);
    object expression;
    NativeMemory.Require(changedStrings.Count==1&&changedStrings.TryGetValue("2c",out expression)
      &&expression is string&&!String.IsNullOrWhiteSpace((string)expression)&&!Object.Equals(expression,strings["2c"]),
      "Size clone restoration requires a different nonempty expression.");
    var dimensions=new Dictionary<string,object>{{"48",words["48"]},{"4c",words["4c"]}};
    NativePageControlPreparation.Same(dimensions,Map(updates["words_uint32"]),
      "The size clone must restore both original dimension words without changing other scalars.");

    // Original Serialize omits these dimensions and the expression cache.
    // Restore the dimensions before reading the private clone's full record.
    item.SizeDimensionRestoration=new Dictionary<string,object>{{"words_uint32",dimensions}};
    var baseline=new Dictionary<string,object>(source);
    baseline["byte_arrays_hex"]=new Dictionary<string,object>{{"14",""}};
    var expected=new Dictionary<string,object>(baseline);
    expected["strings"]=changedStrings;
    NativePageControlPreparation.Same(expected,item.Expected,
      "Only the size expression and its derived compile cache may differ in the prepared item.");
    return baseline;
   }
   static readonly string[] VMoveWordKeys={"8","c","30","34","38","3c","40"};
   static void PrepareObservedVMoveClone(Item item,Dictionary<string,object> updates){
    var source=item.SourceValues;
    var words=Map(source["words_uint32"]);
    var strings=Map(source["strings"]);
    var bytes=Map(source["byte_arrays_hex"]);
    NativeMemory.Require(words.Count==VMoveWordKeys.Length&&Array.TrueForAll(VMoveWordKeys,words.ContainsKey)
      &&strings.Count==1&&strings.ContainsKey("2c")&&Map(source["arrays"]).Count==0
      &&bytes.Count==1&&bytes.ContainsKey("14")&&Object.Equals(bytes["14"],""),
      "The vertical movement animation does not have the observed original serialization layout.");
    NativeMemory.Require(updates.Count==1&&updates.ContainsKey("strings"),
      "A vertical movement clone accepts only an expression update.");
    var changedStrings=Map(updates["strings"]);
    object expression;
    NativeMemory.Require(changedStrings.Count==1&&changedStrings.TryGetValue("2c",out expression)
      &&expression is string&&!String.IsNullOrWhiteSpace((string)expression)&&!Object.Equals(expression,strings["2c"]),
      "Vertical movement clone restoration requires a different nonempty expression.");
    var expected=new Dictionary<string,object>(source);
    expected["strings"]=changedStrings;
    NativePageControlPreparation.Same(expected,item.Expected,
      "Only the vertical movement expression may differ in the prepared item.");
    NativeMemory.Require(Convert.ToUInt32(words["40"],CultureInfo.InvariantCulture)!=0,
      "The original vertical movement dimension does not require restoration.");
    // The original archive does not store this owner-derived dimension.
    // The private object's initial value is immaterial once the live value is
    // restored and the complete resulting private record matches the source.
    item.VMoveDimensionRestoration=new Dictionary<string,object>{{"words_uint32",new Dictionary<string,object>{{"40",words["40"]}}}};
   }
   static Dictionary<string,object> PrepareObservedPaletteClone(Item item,Dictionary<string,object> updates){
    var source=item.SourceValues;
    var words=Map(source["words_uint32"]);
    var strings=Map(source["strings"]);
    var arrays=Map(source["arrays"]);
    var bytes=Map(source["byte_arrays_hex"]);
    NativeMemory.Require(words.Count==2&&words.ContainsKey("8")&&words.ContainsKey("c")
      &&strings.Count==1&&strings.ContainsKey("2c")&&arrays.Count==2&&arrays.ContainsKey("30")&&arrays.ContainsKey("44")
      &&bytes.Count==1&&bytes.ContainsKey("14")&&bytes["14"] is string,
      "The palette animation does not have the observed original serialization layout.");
    var thresholds=arrays["30"] as IList;
    var colors=arrays["44"] as IList;
    NativeMemory.Require(thresholds!=null&&colors!=null&&thresholds.Count==colors.Count,
      "The original palette threshold and color counts differ.");
    NativeMemory.Require(updates.Count==1&&updates.ContainsKey("arrays"),
      "Palette clone restoration permits only threshold and color array updates.");
    var changedArrays=Map(updates["arrays"]);
    NativeMemory.Require(changedArrays.Count>0,"A palette clone needs at least one changed array.");
    var expectedArrays=new Dictionary<string,object>(arrays);
    foreach(var entry in changedArrays){
     NativeMemory.Require(entry.Key=="30"||entry.Key=="44","Unknown original palette array.");
     var updated=entry.Value as IList;
     NativeMemory.Require(updated!=null&&updated.Count==thresholds.Count,"A palette update cannot change its native element count.");
     if(entry.Key=="44")
      for(int i=0;i<colors.Count;i++)
       NativeMemory.Require((Convert.ToUInt32(updated[i],CultureInfo.InvariantCulture)&0xff000000U)==
         (Convert.ToUInt32(colors[i],CultureInfo.InvariantCulture)&0xff000000U),
         "A palette color update cannot change its native high byte.");
     expectedArrays[entry.Key]=updated;
    }
    NativeMemory.Require(NativePageControlPreparation.Json(expectedArrays)!=NativePageControlPreparation.Json(arrays),
      "Keep an unchanged palette instead of replacing its original item.");

    // Both native serializers retain all business members and omit only the
    // derived expression cache, which the deferred original check can rebuild.
    var baseline=new Dictionary<string,object>(source);
    baseline["byte_arrays_hex"]=new Dictionary<string,object>{{"14",""}};
    var expected=new Dictionary<string,object>(baseline);
    expected["arrays"]=expectedArrays;
    NativePageControlPreparation.Same(expected,item.Expected,
      "Only the captured palette arrays and the derived compile cache may differ in the prepared item.");
    return baseline;
   }
   static readonly string[] BlinkWordKeys={"8","c","30","34","38","3c","40","44","48","4c","50"};
   static Dictionary<string,object> PrepareObservedBlinkClone(Item item,Dictionary<string,object> updates){
    var source=item.SourceValues;
    var words=Map(source["words_uint32"]);
    var strings=Map(source["strings"]);
    var cache=Map(source["byte_arrays_hex"]);
    NativeMemory.Require(words.Count==BlinkWordKeys.Length&&Array.TrueForAll(BlinkWordKeys,words.ContainsKey)
      &&Num(words["8"])==0x3001&&Num(words["c"])==0x3f800000&&Num(words["30"])==0&&Num(words["3c"])==0
      &&Num(source["enabled_raw_byte"])==10&&strings.Count==1&&strings.ContainsKey("2c")
      &&Map(source["arrays"]).Count==0&&cache.Count==1&&cache.ContainsKey("14")&&cache["14"] is string,
      "The Blink animation does not have the observed original serialization layout.");
    foreach(string key in updates.Keys)
     NativeMemory.Require(key=="strings"||key=="words_uint32","Blink clone updates only the expression or declared style words.");
    var expectedWords=new Dictionary<string,object>(words);
    var expectedStrings=new Dictionary<string,object>(strings);
    object requested;
    if(updates.TryGetValue("strings",out requested)){
     var changed=Map(requested);object expression;
     NativeMemory.Require(changed.Count==1&&changed.TryGetValue("2c",out expression)&&expression is string
       &&!String.IsNullOrWhiteSpace((string)expression),"Blink update requires a nonempty expression.");
     AnimationText(changed["2c"]);
     expectedStrings["2c"]=changed["2c"];
    }
    if(updates.TryGetValue("words_uint32",out requested)){
     foreach(var pair in Map(requested)){
      string key=pair.Key;
      bool color=key=="48"||key=="4c"||key=="50";
      NativeMemory.Require((key=="40"||key=="44"||color)&&(pair.Value is int||pair.Value is uint||pair.Value is long),
        "Unknown Blink style word or invalid unsigned value.");
      uint value=Convert.ToUInt32(pair.Value,CultureInfo.InvariantCulture);
      uint old=Convert.ToUInt32(words[key],CultureInfo.InvariantCulture);
      NativeMemory.Require((key!="40"||value<=2)&&(key!="44"||value<=1)&&(!color||((value^old)&0xff000000U)==0),
        "Blink speed, mode or packed color high byte differs.");
      expectedWords[key]=value;
     }
    }
    NativeMemory.Require(NativePageControlPreparation.Json(expectedWords)!=NativePageControlPreparation.Json(words)
      ||NativePageControlPreparation.Json(expectedStrings)!=NativePageControlPreparation.Json(strings),
      "Keep an unchanged Blink animation instead of replacing it.");

    // Serialize leaves owner-derived words for SetOwner to initialize.
    // At that point the full original record differs only in its derived cache.
    var baseline=new Dictionary<string,object>(source);
    baseline["byte_arrays_hex"]=new Dictionary<string,object>{{"14",""}};
    var expected=new Dictionary<string,object>(baseline);
    expected["words_uint32"]=expectedWords;
    expected["strings"]=expectedStrings;
    NativePageControlPreparation.Same(expected,item.Expected,
      "The Blink edit must preserve all other captured members and defer only the expression cache.");
    return baseline;
   }
   static uint InputBindingId(Dictionary<string,object> record){
    return Convert.ToUInt32(Map(record["words_uint32"])["88"],CultureInfo.InvariantCulture);
   }
   static void ValidateInputBindingUpdates(Dictionary<string,object> row,string name,uint id){
    object raw;
    if(!row.TryGetValue("native_member_updates",out raw))return;
    var updates=Map(raw);
    if(updates.TryGetValue("strings",out raw))
     foreach(var value in Map(raw))
      if(Int32.Parse(value.Key,NumberStyles.HexNumber,CultureInfo.InvariantCulture)==0x2C)
       NativeMemory.Require(Object.Equals(value.Value,name),"The input name update differs from the full expected binding.");
    if(updates.TryGetValue("words_uint32",out raw))
     foreach(var value in Map(raw))
      if(Int32.Parse(value.Key,NumberStyles.HexNumber,CultureInfo.InvariantCulture)==0x88)
       NativeMemory.Require(Convert.ToUInt32(value.Value,CultureInfo.InvariantCulture)==id,"The input ID update differs from the full expected binding.");
   }
   static int InputBindingKind(Dictionary<string,object> binding,string name,uint id){
    NativeMemory.Require(binding.Count==3&&binding.ContainsKey("native_type"),"Input binding requires exactly a variable name, ID and scalar type.");
    int kind=Num(binding["native_type"]);
    NativeMemory.Require(kind==1||kind==2||kind==3,"Input binding must identify a native scalar variable.");
    NativePageControlPreparation.Same(new Dictionary<string,object>{{"name",name},{"native_id",id},{"native_type",kind}},
      binding,"Input binding variable identity differs from the full animation record.");
    return kind;
   }
   void PrepareInputBinding(Item item,string className,Dictionary<string,object> row){
    bool hasPreimage=row.ContainsKey("input_binding_preimage");
    if(className!="CAniInput"||item.SourceValues==null){
     NativeMemory.Require(!hasPreimage,"Input binding preimage requires an existing CAniInput animation.");
     return;
    }
    string oldName=NativePageControlPreparation.Text(Map(item.SourceValues["strings"]),"2c");
    string newName=NativePageControlPreparation.Text(Map(item.Expected["strings"]),"2c");
    uint oldId=InputBindingId(item.SourceValues),newId=InputBindingId(item.Expected);
    ValidateInputBindingUpdates(row,newName,newId);
    bool changed=oldName!=newName||oldId!=newId;
    NativeMemory.Require(changed==hasPreimage,"An input binding preimage is required exactly when the variable name or ID changes.");
    if(!changed)return;
    NativeMemory.Require(oldName!=newName&&oldId!=newId&&oldId<=Int32.MaxValue&&newId<=Int32.MaxValue,
      "Input rebinding requires two distinct native variable names and IDs.");
    var binding=Map(row["input_binding_preimage"]);
    NativeMemory.Require(binding.Count==2&&binding.ContainsKey("source")&&binding.ContainsKey("target"),
      "Input binding preimage requires source and target variable identities.");
    int oldKind=InputBindingKind(Map(binding["source"]),oldName,oldId);
    int newKind=InputBindingKind(Map(binding["target"]),newName,newId);
    NativeMemory.Require(oldKind==newKind,"Replacement input binding must have the same native scalar type.");
    item.InputBindingPreimage=binding;
    if(inputData==null)inputData=new NativeDataEngineering.Api(api.Drawing.Engine,api.Drawing.Context,api.Project);
   }
   void ValidateInputBindingVariable(Dictionary<string,object> identity){
    var actual=NativeDataLogicalCatalog.DataRecord(inputData,inputData.Data(identity));
    NativePageControlPreparation.Same(identity,
      new Dictionary<string,object>{{"name",actual["name"]},{"native_id",actual["native_id"]},{"native_type",actual["native_type"]}},
      "A current input binding variable name, ID or scalar type differs.");
   }
   void ValidateInputBindings(){
    if(inputData==null)return;
    foreach(Item item in items){
     if(item.InputBindingPreimage==null)continue;
     ValidateInputBindingVariable(Map(item.InputBindingPreimage["source"]));
     ValidateInputBindingVariable(Map(item.InputBindingPreimage["target"]));
    }
   }
   static void ValidateAnimationUpdates(A.OwnedApi api,string name,Dictionary<string,object> updates){var layout=api.Layout(name);foreach(string key in updates.Keys)NativeMemory.Require(key=="words_uint32"||key=="strings"||key=="arrays"||key=="enabled_raw_byte","Unknown private native animation member update.");object value;if(updates.TryGetValue("words_uint32",out value)){var allowed=new HashSet<int>();foreach(object x in(IEnumerable)layout["editable_word_offsets"])allowed.Add(Num(x));foreach(var pair in Map(value)){int off=Int32.Parse(pair.Key,NumberStyles.HexNumber,CultureInfo.InvariantCulture);NativeMemory.Require(allowed.Contains(off),"Animation word offset is outside the native scalar layout.");A.OwnedApi.RequirePackedBoolWord(name,off,Convert.ToUInt32(pair.Value,CultureInfo.InvariantCulture));}}if(updates.TryGetValue("enabled_raw_byte",out value))NativeMemory.Require(Num(value)==0||Num(value)==1,"Animation Boolean update differs.");if(updates.TryGetValue("strings",out value)){var allowed=new HashSet<int>();foreach(object x in(IEnumerable)layout["string_offsets"])allowed.Add(Num(x));foreach(var pair in Map(value)){NativeMemory.Require(allowed.Contains(Int32.Parse(pair.Key,NumberStyles.HexNumber,CultureInfo.InvariantCulture)),"Animation CString offset is outside its real owned layout.");AnimationText(pair.Value);}}if(updates.TryGetValue("arrays",out value))foreach(var pair in Map(value)){int offset=Int32.Parse(pair.Key,NumberStyles.HexNumber,CultureInfo.InvariantCulture);Dictionary<string,object> member=null;foreach(object x in(IEnumerable)layout["array_members"]){var row=Map(x);if(Num(row["offset"])==offset)member=row;}NativeMemory.Require(member!=null,"Animation array offset is outside its real owned layout.");int n=0;foreach(object x in(IEnumerable)pair.Value){n=checked(n+1);if(Convert.ToString(member["kind"])=="cstring")AnimationText(x);else Convert.ToUInt32(x,CultureInfo.InvariantCulture);}}}
   static void AnimationText(object value){NativeMemory.Require(value is string,"Animation text must be an explicit string.");string text=(string)value;NativeMemory.Require(text.Length<=Int32.MaxValue/2-1&&text.IndexOf('\0')<0,"Animation text length/NUL differs.");new System.Text.UnicodeEncoding(false,false,true).GetBytes(text);}
   public void ValidateBefore(){NativeMemory.Require(!disposed&&!failed&&!applied,"Animation action is disposed/failed/applied.");NativePageControlPreparation.Same(before,AnimationCapture(api,action),"Animation/page/template preimage changed before Apply.");ValidateInputBindings();}
   void Call(Action actionBody){nativeUnknown=true;actionBody();nativeUnknown=false;}
   void CloseStreams(bool release){if(loadLive){loadLive=false;Call(()=>api.Owned.DestroyArchive(load));}if(storeLive){storeLive=false;Call(()=>api.Owned.DestroyArchive(store));}if(fileLive){fileLive=false;Call(()=>api.Owned.DestroyMemory(file));}if(release){if(load!=IntPtr.Zero){Marshal.FreeHGlobal(load);load=IntPtr.Zero;}if(store!=IntPtr.Zero){Marshal.FreeHGlobal(store);store=IntPtr.Zero;}if(file!=IntPtr.Zero){Marshal.FreeHGlobal(file);file=IntPtr.Zero;}}}
   void CloneSource(Item item){
    NativeMemory.Require(file!=IntPtr.Zero&&store!=IntPtr.Zero&&load!=IntPtr.Zero&&!fileLive&&!storeLive&&!loadLive,"Owned animation streams are not freshly available.");
    NativeOperationTrace.BeforeMutation("animation-private-original-memory-file-ctor");
    Call(()=>{NativeMemory.Require(api.Owned.ConstructMemory(file,1024)==file,"Animation CMemFile constructor returned another object.");fileLive=true;});
    NativeOperationTrace.BeforeMutation("animation-private-original-store-archive-ctor");
    Call(()=>{NativeMemory.Require(api.Owned.ConstructArchive(store,file,0,0x400000,IntPtr.Zero)==store,"Animation CArchive store constructor differs.");storeLive=true;});
    Marshal.WriteIntPtr(store,0,doc);
    NativeOperationTrace.BeforeMutation("animation-original-source-serialize-to-owned-memory");
    Call(()=>item.Serialize(item.Source,store));
    Call(()=>api.Owned.CloseArchive(store));
    Call(()=>api.Owned.SeekBegin(file));
    NativeOperationTrace.BeforeMutation("animation-private-original-load-archive-ctor");
    Call(()=>{NativeMemory.Require(api.Owned.ConstructArchive(load,file,1,0x400000,IntPtr.Zero)==load,"Animation CArchive load constructor differs.");loadLive=true;});
    Marshal.WriteIntPtr(load,0,doc);
    NativeOperationTrace.BeforeMutation("animation-original-private-deserialize-from-owned-memory");
    Call(()=>item.Serialize(item.Private,load));
    Call(()=>api.Owned.CloseArchive(load));
    CloseStreams(false);
    if(item.SizeDimensionRestoration!=null){
     NativeOperationTrace.BeforeMutation("animation-private-size-dimensions-restore");
     Call(()=>api.Owned.PrivateUpdates(item.Private,item.SizeDimensionRestoration));
    }
    if(item.VMoveDimensionRestoration!=null){
     NativeOperationTrace.BeforeMutation("animation-private-vmove-dimension-restore");
     Call(()=>api.Owned.PrivateUpdates(item.Private,item.VMoveDimensionRestoration));
    }
    if(!item.VerifyCloneAfterOwner)VerifySerializedClone(item);
   }
   void VerifySerializedClone(Item item){
    NativePageControlPreparation.Same(item.SerializedCloneBaseline??item.SourceValues,
      api.Owned.Values(item.Private),"Original animation archive clone differs from its exact supported source layout.");
   }
   void SetPrivateOwner(Item item){
    NativeOperationTrace.BeforeMutation("animation-original-private-owner-setter");
    Call(()=>item.SetOwner(item.Private,target.Full));
    NativeMemory.Require(NativeMemory.Ptr(item.Private,0x28)==target.Full,
      "Original animation owner setter did not establish target control.");
    if(item.VerifyCloneAfterOwner)VerifySerializedClone(item);
   }
   void Verify(){NativeMemory.Require(api.Drawing.Type(target.Full).Name==target.Class.Name&&NativeMemory.Ptr(target.Full,NativeLayout.Offset("control.owner_document"))==doc,"Animation target concrete identity/owner differs.");NativePageControlPreparation.Same(historyState.AfterStoreSnapshot(before["target_control"]),Snapshot(api.Drawing,target),"Animation list changed target name/geometry/raw control state.");var expected=new List<object>();foreach(Item item in items)expected.Add(item.Expected);NativePageControlPreparation.Same(expected,api.Owned.Records(target.Full),"Original animation list differs from exact expected records.");var committed=api.Owned.Raw.Items(target.Full);
    for(int i=0;i<items.Count;i++)if(items[i].Retained)NativeMemory.Require(committed[i]==items[i].Source,"Retained animation identity changed.");
    var forest=api.Drawing.Forest(doc);var owners=new NativeAnimationOwnerIndex<Node>(Flatten(forest),node=>NativeMemory.Hex(node.Full));NativePageControlPreparation.Same(historyState.AfterStoreSnapshot(before["page_control_forest"]),AnimationSnapshotForest(api.Drawing,forest),"Animation list changed other control identity/geometry/raw state.");owners.VerifyUnchanged((IEnumerable)before["page_animation_lists"],value=>Convert.ToString(Map(value)["control"]),NativeMemory.Hex(target.Full),(value,found)=>{var row=Map(value);if(row.ContainsKey("opaque_control")){NativeMemory.Require(found.Class==null,"Opaque animation owner changed type state.");NativePageControlPreparation.Same(historyState.AfterStoreSnapshot(row["opaque_control"]),Snapshot(api.Drawing,found),"Opaque non-target control changed during animation editing.");return;}NativeMemory.Require(found.Class!=null,"Known animation owner became opaque.");NativePageControlPreparation.Same(row["raw"],api.Owned.Raw.Records(found.Full),"Another native animation list/raw state changed.");NativePageControlPreparation.Same(row["values"],api.Owned.Records(found.Full),"Another animation's owned values changed.");});foreach(object value in(IEnumerable)before["source_items"]){var saved=Map(value);IntPtr sp,sd;Node sn=api.Drawing.Locate(Map(Map(saved["source"])["control"]),out sp,out sd);if(sn.Full==target.Full)continue;NativePageControlPreparation.Same(historyState.AfterStoreSnapshot(saved["source_control"]),Snapshot(api.Drawing,sn),"Foreign animation template control changed.");NativePageControlPreparation.Same(saved["source_list_raw"],api.Owned.Raw.Records(sn.Full),"Foreign animation template raw list changed.");NativePageControlPreparation.Same(saved["source_list_values"],api.Owned.Records(sn.Full),"Foreign animation template owned values changed.");if(sd!=doc)NativePageControlPreparation.Same(saved["source_page"],api.Drawing.Shared.PageSnapshot(sp),"Foreign animation template page changed.");}var original=Map(before["page"]);var now=api.Drawing.Shared.PageSnapshot(page);var attrs=new List<object>();int k=0;foreach(object v in(IEnumerable)original["attributes"])attrs.Add(k++==9?0:v);NativePageControlPreparation.Same(attrs,now["attributes"],"Animation list changed an unplanned page attribute.");NativePageControlPreparation.Same(original["pages"],now["pages"],"Animation list changed page identities/order.");}
   public Dictionary<string,object> Apply(NativeUsableEditPermit.Lease lease){ValidateBefore();lease.BeginApply(action);try{var privatePointers=new HashSet<uint>();foreach(Item item in items){if(item.Retained)continue;lease.RequireApplying(action);NativeOperationTrace.BeforeMutation("animation-original-runtime-class-factory");Call(()=>{item.Private=item.Factory();NativeMemory.Require(item.Private!=IntPtr.Zero&&privatePointers.Add(NativeMemory.U(item.Private)),"Animation native factory returned null/aliased object.");item.ConstructorReturned=true;api.Owned.Raw.Type(item.Private);});if(item.Source!=IntPtr.Zero)CloneSource(item);SetPrivateOwner(item);if(item.Updates!=null){NativeOperationTrace.BeforeMutation("animation-owned-private-native-member-preparation");Call(()=>api.Owned.PrivateUpdates(item.Private,item.Updates));}if(item.Properties!=null){NativeOperationTrace.BeforeMutation("animation-owned-private-original-property-setter");Call(()=>item.Properties.Invoke(sink=>item.SetProperties(NativeMemory.Add(item.Private,4),sink)));}NativePageControlPreparation.Same(item.Expected,api.Owned.Values(item.Private),"Prepared animation differs from exact expected_record before project mutation.");}
    NativePageControlPreparation.Same(before,AnimationCapture(api,action),"Private animation construction/clone changed project/template state.");
    ValidateInputBindings();
    lease.RequireApplying(action);NativeOperationTrace.BeforeMutation("animation-original-page-before-modify");historyState.ValidateBefore();Call(()=>modify(doc,view,1,1));historyState.OriginalStoreReturned();NativeMemory.Require(NativeMemory.I32(doc,NativeLayout.Offset("document.history_generated"))==0,"Original animation history raw13 differs.");NativePageControlPreparation.Same(before["items_raw"],api.Owned.Raw.Records(target.Full),"Original history notification changed the animation owner list before commit.");
    var old=api.Owned.Raw.Items(target.Full);IntPtr data=NativeMemory.Ptr(array,4);int count=NativeMemory.I32(array,8);for(int i=0;i<old.Count;i++){IntPtr p=old[i];if(retained.Contains(p))continue;api.Owned.Raw.Type(p);NativeMemory.Require(oldDestructors.ContainsKey(NativeMemory.U(p)),"An old animation destructor was not resolved before Claim.");A.Delete destroy=oldDestructors[NativeMemory.U(p)];NativeMemory.Require(NativeMemory.Ptr(array,4)==data&&NativeMemory.I32(array,8)==count&&NativeMemory.Ptr(data,4*i)==p,"Animation owning slot changed before its unique destructor.");NativeOperationTrace.BeforeMutation("animation-original-release-old-owned-item");Call(()=>destroy(p,1));NativeMemory.Require(NativeMemory.Ptr(array,4)==data&&NativeMemory.I32(array,8)==count,"Animation destructor altered its owner container unexpectedly.");Marshal.WriteIntPtr(data,4*i,IntPtr.Zero);old[i]=IntPtr.Zero;}NativeOperationTrace.BeforeMutation("animation-original-empty-pointer-array");Call(()=>api.Owned.PointerSize(array,0,-1));for(int i=0;i<items.Count;i++){Item item=items[i];IntPtr p=item.Retained?item.Source:item.Private;NativeOperationTrace.BeforeMutation("animation-original-adopt-private-item");item.AdoptionEntered=true;int at=-1;Call(()=>at=api.Owned.PointerAdd(array,p));NativeMemory.Require(at==i&&NativeMemory.I32(array,8)==i+1&&NativeMemory.Ptr(NativeMemory.Ptr(array,4),4*i)==p,"Original animation Add did not adopt the exact private pointer once.");item.Private=IntPtr.Zero;}NativeOperationTrace.BeforeMutation("animation-mark-root-and-page-dirty");Call(()=>rootDirty(api.Drawing.Shared.Shared.RootDoc(),1));Marshal.WriteInt32(api.Drawing.Shared.Shared.RootDoc(),NativeLayout.Offset("document.compile_valid"),0);Call(()=>docDirty(doc,1));Verify();if(view!=IntPtr.Zero){NativeMemory.Require(api.Drawing.View(doc)==view,"Animation drawing view changed.");NativeOperationTrace.BeforeMutation("animation-original-view-refresh");Call(()=>invalidate(view,1));Call(()=>update(view));Verify();}applied=true;lease.CompleteApply(action);return new Dictionary<string,object>{{"ok",true},{"kind",AnimationKind},{"items",api.Owned.Records(target.Full)},{"original_owned_list_rebuilt",true},{"retained_original_count",retained.Count},{"constructed_item_count",items.Count-retained.Count},{"removed_original_count",old.Count-retained.Count},{"native_final_compile_and_reference_rebuild_pending",true},{"pending_explicit_page_flush",true}};}catch{failed=true;throw;}}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease){NativeMemory.Require(applied&&!failed&&!disposed,"Only a verified animation Apply may flush.");lease.BeginFlush(action);try{Verify();int dirty=isModified(doc);NativeMemory.Require(dirty==0||dirty==1,"Animation page dirty representation differs.");if(dirty==1){NativeOperationTrace.BeforeMutation("animation-original-page-save-data");bool ok=false;Call(()=>ok=save(api.Drawing.Context.WindowService,page));NativeMemory.Require(ok&&isModified(doc)==0,"Animation original page SaveData did not reach clean state.");}Verify();lease.CompleteFlush(action);return new Dictionary<string,object>{{"ok",true},{"page_save_data_called",dirty==1},{"full_persistence_acceptance_pending",true}};}catch{failed=true;throw;}}
   public void Dispose(){if(disposed)return;disposed=true;try{if(!failed&&!nativeUnknown){CloseStreams(true);foreach(Item item in items)if(item.Private!=IntPtr.Zero&&item.ConstructorReturned&&!item.AdoptionEntered){IntPtr p=item.Private;item.Private=IntPtr.Zero;Call(()=>item.Delete(p,1));}}}finally{foreach(Item item in items)item.Dispose();}}
  }
 }
}
