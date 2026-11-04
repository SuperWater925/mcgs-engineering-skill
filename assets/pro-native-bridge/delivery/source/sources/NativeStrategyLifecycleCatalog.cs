// Complete raw/persistent strategy bridge for lifecycle and legacy capture consumers.
// This reader never calls Serialize, a provider initializer, save, or reference mutator.
using System;using System.Collections;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeStrategyWorkingModelEditing {
  internal static TypedContract PersistentContract(NativeEngine e,NativeContext c,string project){return new TypedContract(new Api(e,c,project));}
  internal static List<object> PersistentConditionsForLegacy(TypedContract contract,IntPtr row){
   var api=contract.Native;NativeMemory.Require(api.Class(row).Name=="CStrategyRow","Native persistent bridge row type differs.");IntPtr cell=NativeMemory.Ptr(row,4);var result=new List<object>();
   if(cell==IntPtr.Zero){result.Add(new Dictionary<string,object>{{"cell_exists",false}});return result;}
   NativeMemory.Require(api.Class(cell).Name=="CStrategyCell","Native persistent bridge cell type differs.");foreach(IntPtr node in api.Conditions(cell))result.Add(PersistentNode(contract,node));return result;
  }
  internal static Dictionary<string,object> PersistentOtherFunctionForLegacy(TypedContract contract,IntPtr row,int nativeIndex){
   var api=contract.Native;NativeMemory.Require(api.Class(row).Name=="CStrategyRow","Native persistent action bridge row type differs.");IntPtr node=NativeMemory.Ptr(row,8);
   return new Dictionary<string,object>{{"native_row_index",nativeIndex},{"persistent_action",PersistentNode(contract,node)},{"full_native_serialized_members_projected",true},{"unknown_nonserialized_provider_state_complete",false}};
  }
  internal static List<object> PersistentRows(TypedContract contract,IntPtr block){var api=contract.Native;var result=new List<object>();var rows=api.Rows(block);
   for(int i=0;i<rows.Count;i++)result.Add(new Dictionary<string,object>{{"native_row_index",i},{"cell_exists",NativeMemory.Ptr(rows[i],4)!=IntPtr.Zero},{"conditions",PersistentConditionsForLegacy(contract,rows[i])},{"action",PersistentNode(contract,NativeMemory.Ptr(rows[i],8))}});
   return result;
  }
  internal static Dictionary<string,object> KnownBlockMetadata(TypedContract contract,IntPtr block){
   var api=contract.Native;api.Base.Read.Table(block,"BlockComplete");api.Base.Read.Table(NativeMemory.Add(block,4),"BlockIObject");
   var numbers=new Dictionary<string,object>();foreach(int offset in new[]{0x1C,0x34,0x38,0x3C,0x40,0x44,0x58,0x5C})numbers["0x"+offset.ToString("X")]=unchecked((uint)NativeMemory.I32(block,offset));
   string password=api.CString(NativeMemory.Add(block,0x60));
   return new Dictionary<string,object>{{"name",api.CString(NativeMemory.Add(block,0x18))},{"comment",api.CString(NativeMemory.Add(block,0x14))},{"original_serialized_and_store_projection_words",numbers},{"password_utf16_units",password.Length},{"password_utf16le_sha256",Hash(RawText(password))},{"unknown_nonserialized_block_members_complete",false}};
  }
  internal static Dictionary<string,object> FullBlockRecord(TypedContract contract,NativeStrategyTriggerContextEditing.Api contexts,int id,IntPtr io){
   var api=contract.Native;api.Base.Read.Table(io,"BlockIObject");IntPtr full=NativeMemory.Add(io,-4),context=NativeMemory.Ptr(full,0x10);
   NativeMemory.Require(LTrace("block-"+id+"-read-id",()=>NativeStrategyProfile.ReadId(api.Base.Read.Existing,io))==id&&NativeMemory.I32(context,8)==id,"Persistent strategy block/context ID linkage differs.");
   var conditions=new List<object>();var others=new List<object>();var programs=new List<object>();var rows=LTrace("block-"+id+"-rows",()=>api.Rows(full));
   for(int i=0;i<rows.Count;i++){conditions.Add(LTrace("block-"+id+"-row-"+i+"-conditions",()=>PersistentConditionsForLegacy(contract,rows[i])));IntPtr function=NativeMemory.Ptr(rows[i],8);
    if(function!=IntPtr.Zero&&api.Class(function).Name=="CStgyFuncProg"){string body=LTrace("block-"+id+"-row-"+i+"-body",()=>api.CString(NativeMemory.Add(function,0x20)));programs.Add(new Dictionary<string,object>{{"native_row_index",i},{"row",NativeMemory.Hex(rows[i])},{"program",NativeMemory.Hex(function)},{"source_utf16le_hex",H(RawText(body))},{"source_utf16le_sha256",Hash(RawText(body))},{"source_utf16_code_units",body.Length}});}
    else others.Add(LTrace("block-"+id+"-row-"+i+"-other",()=>PersistentOtherFunctionForLegacy(contract,rows[i],i)));
   }
   return new Dictionary<string,object>{{"block_id",id},{"block_name",LTrace("block-"+id+"-read-name",()=>NativeStrategyProfile.ReadName(api.Base.Read.Existing,io))},{"block_iobject",NativeMemory.Hex(io)},{"context",NativeMemory.Hex(context)},{"conditions_json",Json(conditions)},{"other_functions_json",Json(others)},{"programs",programs},{"persistent_rows",LTrace("block-"+id+"-persistent-rows",()=>PersistentRows(contract,full))},{"known_block_metadata",LTrace("block-"+id+"-metadata",()=>KnownBlockMetadata(contract,full))},{"trigger_fields",LTrace("block-"+id+"-context-fields",()=>contexts.Fields(context))},{"trigger_complete_raw_hex",H(NativeMemory.Bytes(context,N(contexts.Type(context)["size"])))},{"block_complete_raw_hex",H(NativeMemory.Bytes(full,0x68))},{"block_dirty_raw",(int)System.Runtime.InteropServices.Marshal.ReadByte(full,0x64)},{"claim_preimage_uses_serialize",false}};
  }
  internal static Dictionary<string,object> InspectPersistentCanonical(NativeEngine e,NativeContext c,string project){
   var contract=LTrace("catalog-contract",()=>PersistentContract(e,c,project));var api=contract.Native;var contexts=LTrace("catalog-context-api",()=>new NativeStrategyTriggerContextEditing.Api(e,c,project));var rows=new List<object>();
   var raw=new List<object>();foreach(var entry in LTrace("catalog-blocks",()=>api.Base.Blocks())){var item=LTrace("catalog-block-"+entry.Key,()=>FullBlockRecord(contract,contexts,entry.Key,entry.Value));raw.Add(item);var semantic=new Dictionary<string,object>(item);semantic.Remove("block_complete_raw_hex");semantic.Remove("trigger_complete_raw_hex");semantic.Remove("block_dirty_raw");rows.Add(semantic);}
   return new Dictionary<string,object>{{"ok",true},{"abi_profile_sha256",TypedAbiProfileSha},{"blocks",rows},{"raw_blocks_full",raw},{"next_strategy_id",LTrace("catalog-next-id",()=>api.Base.Bind<I0>("NextStrategyId")(api.Base.Root))},{"contexts",LTrace("catalog-contexts",()=>contexts.Catalog())},{"provider_registry_raw",LTrace("catalog-provider-registry",()=>ProviderRegistryRaw(contract))},{"full_original_action_condition_serialized_members_projected",true},{"unknown_nonserialized_provider_state_complete",false},{"claim_preimage_uses_serialize",false},{"write_attempted",false},{"native_acceptance_pending",true}};
  }
 }
}

