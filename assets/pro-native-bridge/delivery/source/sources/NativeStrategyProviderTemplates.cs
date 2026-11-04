// Raw native provider projection and legal current-project configuration templates.
// Never cold-initialize service registries or invoke provider UI during inspection/Claim.
using System;using System.Collections;using System.Collections.Generic;
namespace McgsInternalBridge {
 internal static partial class NativeStrategyWorkingModelEditing {
  static bool ProviderClass(string name){return name=="CStgyFuncSvr"||name=="CStgyFuncAddin";}
  internal static Dictionary<string,object> PersistentNode(TypedContract contract,IntPtr node){
   if(node==IntPtr.Zero)return new Dictionary<string,object>{{"exists",false}};
   var api=contract.Native;var type=api.Class(node);
   if(contract.Classes.ContainsKey(type.Name))return contract.Persistent(node);
   NativeMemory.Require(type.Name=="CStrategyConn"||type.Name=="CStrategyFunc","Unknown native node persistent fields are not silently skipped.");
   int number=type.Name=="CStrategyConn"?8:4,text=type.Name=="CStrategyConn"?0x14:8;
   string value=api.CString(NativeMemory.Add(node,text));
   return new Dictionary<string,object>{{"class_name",type.Name},{"serialized_fields",new Dictionary<string,object>{{"dwords@0x"+number.ToString("X"),unchecked((uint)NativeMemory.I32(node,number))},{"strings@0x"+text.ToString("X"),new Dictionary<string,object>{{"text",value},{"utf16le_hex",H(RawText(value))}}}}},{"all_original_native_serialized_fields_projected",true},{"nonserialized_private_layout_complete",false}};
  }
  internal static List<object> TypedTree(TypedContract contract,IntPtr block){
   var api=contract.Native;var tree=api.Tree(block);var rows=api.Rows(block);
   for(int i=0;i<rows.Count;i++){var row=M(tree[i]);var conditions=new List<object>();IntPtr cell=NativeMemory.Ptr(rows[i],4);
    if(cell!=IntPtr.Zero)foreach(IntPtr node in api.Conditions(cell))conditions.Add(PersistentNode(contract,node));
    row["serialized_conditions"]=conditions;row["serialized_action"]=PersistentNode(contract,NativeMemory.Ptr(rows[i],8));
    row["all_node_serialized_member_projections_covered"]=true;row["unknown_nonserialized_private_payload_complete"]=false;
   }return tree;
  }
  static Dictionary<string,object> RegistryValue(Api api,IntPtr at,int stride){
   var value=new Dictionary<string,object>{{"first_text",api.CString(at)},{"second_text",api.CString(NativeMemory.Add(at,4))},{"i4_8",NativeMemory.I32(at,8)}};
   if(stride==16)value["i4_C"]=NativeMemory.I32(at,12);return value;
  }
  static Dictionary<string,object> RegistryArray(Api api,int rva,int vtable,int stride){
   IntPtr at=api.Engine.Address(rva);NativeMemory.Require(NativeMemory.Ptr(at,0)==api.Engine.Address(vtable),"Actual native provider registry CArray vtable differs.");
   IntPtr data=NativeMemory.Ptr(at,4);int count=NativeMemory.I32(at,8),capacity=NativeMemory.I32(at,12),growth=NativeMemory.I32(at,16);
   NativeMemory.Require(count>=0&&count<=4096&&capacity>=count&&(count==0||data!=IntPtr.Zero),"Actual loaded provider registry shape differs.");
   if(count>0)NativeMemory.Readable(data,checked(count*stride));var items=new List<object>();
   for(int i=0;i<count;i++)items.Add(new Dictionary<string,object>{{"native_index",i},{"value",RegistryValue(api,NativeMemory.Add(data,i*stride),stride)}});
   return new Dictionary<string,object>{{"pointer",NativeMemory.Hex(at)},{"data",NativeMemory.Hex(data)},{"count",count},{"capacity",capacity},{"growth_raw",growth},{"element_stride",stride},{"items",items}};
  }
  internal static Dictionary<string,object> ProviderArchiveGlobals(Api api){
   var values=new Dictionary<string,object>{{"global_string_13C08BC",api.CString(api.Engine.Address(0xFC08BC))}};
   foreach(int va in new[]{0x13C08C0,0x13C08C4,0x13C08C8,0x13C08CC})values["global_i4_"+va.ToString("X")]=unchecked((uint)NativeMemory.I32(api.Engine.Address(va-0x400000),0));
   return values;
  }
  internal static Dictionary<string,object> ProviderRegistryRaw(TypedContract contract){
   var api=contract.Native;api.Current();var text=new Dictionary<string,object>();foreach(int va in new[]{0x13C08BC,0x13C08E0,0x13C08FC})text["0x"+va.ToString("X")]=api.CString(api.Engine.Address(va-0x400000));
   var integers=new Dictionary<string,object>();foreach(int va in new[]{0x13C08C0,0x13C08C4,0x13C08C8,0x13C08CC})integers["0x"+va.ToString("X")]=NativeMemory.I32(api.Engine.Address(va-0x400000),0);
   return new Dictionary<string,object>{{"registry16",RegistryArray(api,0xFC0898,0xE37F98,16)},{"registry12",RegistryArray(api,0xFC08E4,0xE37FB4,12)},{"native_global_strings",text},{"native_global_i4",integers},{"raw_read_only",true},{"cold_loader_invoked",false},{"empty_registry_is_not_a_readiness_proof",true},{"private_config_payload_semantics_complete",false}};
  }
  internal static IntPtr ResolveProviderTemplate(TypedContract contract,Dictionary<string,object> input,string expectedClass){
   foreach(string key in input.Keys)NativeMemory.Require(key=="block_id"||key=="block_name"||key=="native_row_index"||key=="model","Unknown provider configuration template selector is not ignored: "+key);
   NativeMemory.Require(ProviderClass(expectedClass),"Configuration templates are restricted to the actual native provider classes.");
   var target=new Dictionary<string,object>(input);target.Add("node_kind","action");var resolved=ResolveTyped(contract.Native,target);
   NativeMemory.Require(!resolved.Condition&&contract.Native.Class(resolved.Node).Name==expectedClass,"Current native configuration template concrete provider class differs.");
   // Read all persistent members now; ownership and private payload copy are performed only
   // inside Apply through the original factory/Serialize2 clone and original row adoption.
   contract.Persistent(resolved.Node);return resolved.Node;
  }
  internal static Dictionary<string,object> ProviderCatalog(NativeEngine engine,NativeContext context,string project){
   var contract=new TypedContract(new Api(engine,context,project));var api=contract.Native;var result=new List<object>();
   foreach(var entry in api.Base.Blocks())AppendProviders(contract,result,entry.Key,NativeStrategyProfile.ReadName(api.Base.Read.Existing,entry.Value),false,NativeMemory.Add(entry.Value,-4));
   foreach(var view in api.Views().Values)AppendProviders(contract,result,view.Id,NativeStrategyProfile.ReadName(api.Base.Read.Existing,api.Base.Blocks()[view.Id]),true,view.Block);
   return new Dictionary<string,object>{{"abi_profile_sha256",TypedAbiProfileSha},{"providers",result},{"loaded_service_registry",ProviderRegistryRaw(contract)},{"claim_preimage_uses_serialize",false},{"arbitrary_provider_config_pending",true},{"native_acceptance_pending",true}};
  }
  static void AppendProviders(TypedContract contract,List<object> result,int id,string name,bool working,IntPtr block){
   var api=contract.Native;var rows=api.Rows(block);for(int i=0;i<rows.Count;i++){IntPtr action=NativeMemory.Ptr(rows[i],8);if(action==IntPtr.Zero)continue;var type=api.Class(action);if(!ProviderClass(type.Name))continue;
    result.Add(new Dictionary<string,object>{{"block_id",id},{"block_name",name},{"model",working?"working":"canonical"},{"native_row_index",i},{"node",api.Node(action)},{"parameters",contract.Parameters(action)},{"persistent",contract.Persistent(action)},{"nonserialized_provider_pointer_or_external_state_complete",false},{"current_native_template_candidate",true},{"original_compile_required",true}});
   }
  }
 }
}

