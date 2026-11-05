// RootAdd ends with original IObject21 generation. This is not a copy/LOAD codec rule.
// Native raw before/after records remain intact; this predicts only the proved empty Prog result.
using System;using System.Collections;using System.Collections.Generic;using System.IO;
using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeStrategyWorkingModelEditing {
  internal const string RootAddGenerationAbiSha="f40e60924c1a020e180f9eb5a467d144121867262ff5b4e8739087d2d4f0dba4";
  const string EmptyCompiledSha="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
  const string GeneratedEmptyProgSha="9ce6c494fe82468ce25c30c30ad97a6db11e5d22bcac40b97df0a7237f7c6eac";
  internal static void RequireRootAddGenerationContract(Api api){
   string file=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"strategy-prep","node-edit-prep","lifecycle-prep","strategy-rootadd-generation-abi-profile.json");
   NativeMemory.Require(NativeMemory.Hash(file)==RootAddGenerationAbiSha,"RootAdd original Prog generation contract differs.");var profile=new JavaScriptSerializer{MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));
   NativeMemory.Require(NativeBinaryIdentity.Observe(Convert.ToString(profile["binary_sha256"]),api.Engine.ImageSha256,"NativeStrategyRootAddGeneration:13:editor")&&Convert.ToString(profile["base_lifecycle_abi_sha256"])==LifecycleAbiProfileSha&&NativeMemory.Hash(Convert.ToString(profile["proof_file"]))==Convert.ToString(profile["proof_sha256"]),"RootAdd original native generation binary/proof differs.");api.Current();
   foreach(object value in(IEnumerable)profile["guards"]){var row=M(value);byte[] bytes=B(Convert.ToString(row["bytes"]));NativeCodeRelocation.RebaseDeltaInPlace(bytes,(IEnumerable)row["reloc_offsets"],unchecked((uint)(NativeMemory.U(api.Engine.ImageBase)-0x400000U)));NativeMemory.Require(H(bytes)==H(NativeMemory.Bytes(api.Engine.Address(N(row["rva"])),bytes.Length)),"Original RootAdd/compiler instruction guard differs: "+Convert.ToString(row["name"]));}
  }
  internal static List<object> OriginalRootAddGeneratedRows(Api api,object input){
   RequireRootAddGenerationContract(api);var result=new List<object>();foreach(object copied in(IEnumerable)new JavaScriptSerializer{MaxJsonLength=64*1024*1024}.DeserializeObject(Json(input)))result.Add(copied);
   foreach(object value in result){var row=M(value);var node=M(row["action"]);object className;if(!node.TryGetValue("class_name",out className)||Convert.ToString(className)!="CStgyFuncProg")continue;var fields=M(node["serialized_fields"]);var source=M(fields["strings@0x20"]);var compiled=M(fields["byte_arrays@0xC"]);
    if(Convert.ToString(source["text"])!=""||Convert.ToString(source["utf16le_hex"])!=""||N(compiled["bytes"])!=0)continue;
    NativeMemory.Require(Convert.ToString(compiled["sha256"])==EmptyCompiledSha&&Object.Equals(compiled["complete_payload_sha256"],true),"Empty Prog input did not carry the complete exact empty compiled payload.");
    compiled["bytes"]=13;compiled["sha256"]=GeneratedEmptyProgSha;
   }return result;
  }
 }
}
