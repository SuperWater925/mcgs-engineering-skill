// Exact original CRecipe STORE projection. No native call and no raw project write.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Runtime.InteropServices;

namespace McgsInternalBridge {
 internal static class NativeRecipeStoreProjection {
  internal const uint FormatMarker = 1134562542U; // original DWORD at preferred VA12058A0, ee0ca043
  const string BinarySha = "bf0b6a0933d9147013638996083509d3b4711805ff3eb88963a0c35b3a660084";
  const string StorePrefix = "558bec83ec18894dfc8b45fcf30f1005a0582001f30f114034";

  internal static void RequireBeforeSave(NativeDataEngineering.Api api) {
   api.Current();
   NativeMemory.Require(NativeBinaryIdentity.Observe(BinarySha,api.Engine.ImageSha256,"NativeRecipeStoreProjection:16:editor"), "Recipe STORE projection requires its exact original binary.");
   api.Check("RecipeSave"); api.Check("RecipeSaveWorker");
   byte[] expected = new byte[StorePrefix.Length / 2];
   for (int i = 0; i < expected.Length; i++) expected[i] = Byte.Parse(StorePrefix.Substring(i * 2, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
   // The one HIGHLOW operand is a runtime address; its full four bytes remain exact.
   Array.Copy(BitConverter.GetBytes(NativeMemory.U(api.Engine.Address(0xE058A0))), 0, expected, 16, 4);
   NativeMemory.Require(BitConverter.ToString(expected) == BitConverter.ToString(NativeMemory.Bytes(api.Engine.Address(0x900320), expected.Length)), "Original CRecipe STORE marker projection code differs.");
   NativeMemory.Require(unchecked((uint)NativeMemory.I32(api.Engine.Address(0xE058A0), 0)) == FormatMarker, "Original CRecipe STORE marker constant differs.");
   NativeMemory.Require(Marshal.ReadByte(api.RecipeManager, 0x38) == 1 && NativeMemory.Ptr(api.Root, 0x520) != IntPtr.Zero, "Recipe native save requires the already loaded manager and original storage owner.");
  }

  // Called only after an actual normally returned, validated module4 Save. Keep every
  // field and list position, including object/name/type/byte38/columns/rows and unknown keys.
  internal static List<Dictionary<string,object>> ExpectedCatalogAfterSave(object before) {
   NativeMemory.Require(before is IEnumerable && !(before is string) && !(before is IDictionary), "Recipe STORE catalog is not an ordered record sequence.");
   var result = new List<Dictionary<string,object>>();
   foreach (object item in (IEnumerable)before) {
    var record = NativePageControlPreparation.Map(item);
    foreach (string key in new[]{"object", "name", "format_bits", "raw_byte38", "columns", "rows"}) NativeMemory.Require(record.ContainsKey(key), "Recipe STORE record lacks its complete known field: " + key);
    Convert.ToUInt32(record["format_bits"], CultureInfo.InvariantCulture); // preserve all before DWORDs; no whitelist/mask
    var projected = new Dictionary<string,object>(record);
    projected["format_bits"] = FormatMarker;
    result.Add(projected);
   }
   return result;
  }

  internal static Dictionary<string,object> ValidateAfterSave(NativeDataEngineering.Api api, object before, object after, bool nativeReturned) {
   NativeMemory.Require(nativeReturned, "Recipe STORE projection cannot follow a failed/unknown native return.");
   RequireBeforeSave(api);
   NativeMemory.Require(Marshal.ReadByte(api.RecipeManager, 0x38) == 1 && Marshal.ReadByte(api.RecipeManager, 0x39) == 0, "Returned recipe save did not leave exact loaded1/dirty0 flags.");
   var expected = ExpectedCatalogAfterSave(before);
   NativePageControlPreparation.Same(expected, after, "Original RecipeSave changed a recipe outside its exact format_bits STORE projection.");
   var changes = new List<object>(); int index = 0;
   foreach (object item in (IEnumerable)before) {
    var record = NativePageControlPreparation.Map(item); uint old = Convert.ToUInt32(record["format_bits"], CultureInfo.InvariantCulture);
    if (old != FormatMarker) changes.Add(new Dictionary<string,object>{{"index",index},{"object",record["object"]},{"name",record["name"]},{"field","format_bits"},{"before_uint32",old},{"after_uint32",FormatMarker}});
    index++;
   }
   return new Dictionary<string,object>{{"original_store_projection_verified",true},{"normal_native_save_return",true},{"format_marker_uint32",FormatMarker},{"only_projected_field","format_bits"},{"changed_records",changes},{"loaded_after",1},{"dirty_after",0},{"all_other_known_fields_exact",true},{"database_blob_acceptance_verified",false}};
  }

  // Read an in-process result produced by the embedded persistence participant. This
  // is not request input and must not infer STORE merely from a related module ID.
  internal static bool RelatedSaveWasVerified(Dictionary<string,object> result) {
   object value;
   if (!result.TryGetValue("related_module_persistence", out value)) return false;
   var persistence = NativePageControlPreparation.Map(value);
   NativeMemory.Require(Object.Equals(persistence["ok"], true), "Related module persistence did not complete.");
   bool found = false;
   foreach (object item in (IEnumerable)persistence["module_saves"]) {
    var row = NativePageControlPreparation.Map(item);
    if (Convert.ToInt32(row["module_id"], CultureInfo.InvariantCulture) != 4) continue;
    NativeMemory.Require(!found && Object.Equals(row["native_save_called"],true) && Object.Equals(row["native_return"],true), "Related recipe save lacks one normally returned actual call.");
    var projection = NativePageControlPreparation.Map(row["recipe_store_projection"]);
    NativeMemory.Require(Object.Equals(projection["original_store_projection_verified"],true) && Object.Equals(projection["normal_native_save_return"],true) && Convert.ToUInt32(projection["format_marker_uint32"],CultureInfo.InvariantCulture)==FormatMarker && Convert.ToInt32(projection["loaded_after"],CultureInfo.InvariantCulture)==1 && Convert.ToInt32(projection["dirty_after"],CultureInfo.InvariantCulture)==0 && Object.Equals(projection["all_other_known_fields_exact"],true), "Related recipe save projection was not validated by its actual participant.");
    found = true;
   }
   return found;
  }
 }
}
