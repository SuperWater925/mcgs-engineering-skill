// Bound alongside one engine after resolving the selected program's native API.
// No reference vendor build whitelist. Existing field and native guards remain.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
 internal sealed class NativeAbiUnavailableException : InvalidOperationException {
  internal readonly string Status,Profile,Entry;
  internal NativeAbiUnavailableException(string message,string profile,string entry) : base(message) {Status="unresolved";Profile=profile;Entry=entry;}
 }
 internal static class NativeAbiTargetProfiles {
  internal const string ExpectedIndexSha256="__BOUND_ABI_PROFILE_INDEX_SHA256__";
  const string IndexName="abi-target-profile-index.json";
  static readonly object Sync=new object();
  static Dictionary<string,Dictionary<string,object>> files;
  static List<Dictionary<string,object>> modules;
  static Dictionary<string,Dictionary<string,object>> sourceGuards;
  static List<Dictionary<string,object>> sourceOrdinals;
  static readonly HashSet<string> verifiedModules=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
  static string indexPath;
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,EntryPoint="GetModuleHandleW")]static extern IntPtr GetModuleHandle(string name);
  static string HashFile(string path) {
   using(var sha=SHA256.Create())
   using(var input=File.Open(path,FileMode.Open,FileAccess.Read,FileShare.Read))
    return BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();
  }
  static string Text(Dictionary<string,object> row,string key) {
   object value;
   if(!row.TryGetValue(key,out value)||!(value is string))throw new InvalidDataException("Current native API index has no text field: "+key);
   return (string)value;
  }
  static void Load() {
   lock(Sync) {
    if(files!=null)return;
    indexPath=Path.Combine(NativeEngineeringDeliveryLayout.EvidenceRoot,IndexName);
    if(ExpectedIndexSha256.Length!=64||HashFile(indexPath)!=ExpectedIndexSha256)
     throw new InvalidDataException("Current native API index differs from this engine. Bind the engine and index together from the current program.");
    var map=new JavaScriptSerializer{MaxJsonLength=int.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(File.ReadAllText(indexPath,new UTF8Encoding(false,true)));
    if(Text(map,"schema")!="mcgs-native-bound-profile-index/v1")throw new InvalidDataException("Current native API index schema differs.");
    var found=new Dictionary<string,Dictionary<string,object>>(StringComparer.OrdinalIgnoreCase);
    foreach(object item in (IEnumerable)map["files"]) {
     var row=(Dictionary<string,object>)item;
     string path=Path.GetFullPath(Text(row,"file"));
     if(found.ContainsKey(path))throw new InvalidDataException("Current native API profile path is duplicated.");
     found.Add(path,row);
    }
    var moduleRows=new List<Dictionary<string,object>>();
    foreach(object item in (IEnumerable)map["modules"])moduleRows.Add((Dictionary<string,object>)item);
    var guardRows=new Dictionary<string,Dictionary<string,object>>(StringComparer.Ordinal);
    foreach(object item in (IEnumerable)map["source_guards"]){var row=(Dictionary<string,object>)item;guardRows.Add(Text(row,"id"),row);}
    var ordinalRows=new List<Dictionary<string,object>>();
    foreach(object item in (IEnumerable)map["source_ordinals"])ordinalRows.Add((Dictionary<string,object>)item);
    sourceOrdinals=ordinalRows;sourceGuards=guardRows;modules=moduleRows;files=found;
   }
  }
  internal static void CheckProfile(string path,bool verifyBytes) {
   Load();
   Dictionary<string,object> row;
   if(!files.TryGetValue(Path.GetFullPath(path),out row))return;
   string status=Text(row,"status");
   object allow;
   bool partial=status=="partial"&&Text(row,"profile")=="static/read-tree-guard-profile.json"&&row.TryGetValue("allow_partial_entries",out allow)&&allow is bool&&(bool)allow;
   if(status!="verified"&&status!="unchanged"&&!partial) {
    object details;
    string explanation=row.TryGetValue("details",out details)?Convert.ToString(details,CultureInfo.InvariantCulture):"Unresolved native method or table";
    throw new NativeAbiUnavailableException("Current program API is unresolved for this feature: "+Text(row,"profile")+"; "+explanation+". No particular Pro release is required; inspect or extend this method's locator.",Text(row,"profile"),"");
   }
   if(verifyBytes&&HashFile(path)!=Text(row,"sha256"))
    throw new InvalidDataException("Resolved native API profile changed after binding: "+Text(row,"profile"));
  }
  // Historic explicit readers; other consumers may opt in only by calling
  // ReadLazyAllText and checking every consumed function/table before access.
  // Generic File IO remains strict: an unreadable unused entry is not silently
  // admitted to a consumer which has not implemented operation-level checks.
  internal const string LazyEntryContract="mcgs-native-lazy-entry/v1";
  static readonly HashSet<string> LazyProfiles=new HashSet<string>(StringComparer.Ordinal) {
   "coverage-20261101/usable-edit-0001/data-recipe-device-prep/data-recipe-native-abi-profile.json",
   "strategy-properties/strategy-write-guard-profile.json",
   "static/native-page-duplicate-abi-profile.json","static/document-dirty-save-abi-profile.json",
   "extensions/page/page-extension-abi-profile.json","extensions/page/page-size-abi-profile.json","extensions/page/page-delete-abi-profile.json",
   "extensions/control/control-abi-guard-v2.json","extensions/control/standard-controls-abi-guard-v3.json",
   "extensions/strategy/strategy-extension-read-guard.json","extensions/strategy/strategy-extension-write-guard.json",
   "extensions/strategy/registration/registration-abi-guard.json","extensions/strategy/delete/strategy-delete-abi-profile.json",
   "coverage-20261101/usable-edit-0001/page-control-prep/current-template-control-abi-profile.v2.json",
   "coverage-20261101/references-view/live-label-abi-profile.json",
   "coverage-20261101/usable-edit-0001/page-control-prep/native-control-placement-factory-abi-profile.v3.json",
   "coverage-20261101/usable-edit-0001/page-control-prep/page-name-cache-abi-profile.v3.json"
  };
  internal static string ReadLazyAllText(string path,string expectedSha) {
   Load();Dictionary<string,object> row;
   if(!files.TryGetValue(Path.GetFullPath(path),out row))throw new InvalidDataException("Lazy native profile has no bound integrity index entry.");
   string relative=Text(row,"profile").Replace('\\','/'),status=Text(row,"status");
   if(status=="partial"){
    object allow,contract;
    if(!row.TryGetValue("allow_partial_entries",out allow)||!(allow is bool)||!(bool)allow||!row.TryGetValue("entry_validation_contract",out contract)||!(contract is string)||(string)contract!=LazyEntryContract)
     throw new NativeAbiUnavailableException("Native partial profile lacks its explicit per-entry validation contract.",relative,"");
   }else if(status!="verified"&&status!="unchanged")throw new NativeAbiUnavailableException("Current program API is unresolved for this feature.",relative,"");
   byte[] bytes=File.ReadAllBytes(path);string actual;using(var sha=SHA256.Create())actual=BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
   if(actual!=Text(row,"sha256")||actual!=expectedSha)throw new InvalidDataException("Resolved lazy native profile changed after binding: "+relative);
   return new UTF8Encoding(false,true).GetString(bytes).TrimStart('\ufeff');
  }
  internal static void VerifyTemplateInventory(string path,string expectedSha) {
   Load();Dictionary<string,object> row;
   const string relative="coverage-20261101/controls/installed-control-abi-inventory.json";
   // This file contributes provenance/integrity only. Every used native class/table is guarded from the template profile.
   if(!files.TryGetValue(Path.GetFullPath(path),out row)||Text(row,"profile")!=relative||HashFile(path)!=Text(row,"sha256")||Text(row,"sha256")!=expectedSha)
    throw new InvalidDataException("Installed CDraw class inventory changed.");
  }

  internal static void CheckEntry(Dictionary<string,object> item,string kind) {CheckEntry(item,kind,"static/read-tree-guard-profile.json");}
  internal static void CheckEntry(Dictionary<string,object> item,string kind,string profile) {
   object raw;string name=item.ContainsKey("name")?Convert.ToString(item["name"],CultureInfo.InvariantCulture):kind;
   var state=item.TryGetValue("_abi_resolution",out raw)?raw as Dictionary<string,object>:null;
   if(state!=null&&state.TryGetValue("entry",out raw)&&raw is string)name=(string)raw;
   bool matchingProfile=state!=null&&state.TryGetValue("profile",out raw)&&raw is string&&(string)raw==profile;
   // Legacy root rows predate profile labels; their existing exact index and per-row status still apply.
   if(profile=="static/read-tree-guard-profile.json"&&state!=null&&!state.ContainsKey("profile"))matchingProfile=true;
   if(!matchingProfile||!state.ContainsKey("status")||(Convert.ToString(state["status"],CultureInfo.InvariantCulture)!="resolved"&&Convert.ToString(state["status"],CultureInfo.InvariantCulture)!="verified"))
    throw new NativeAbiUnavailableException("Current program native "+kind+" was not uniquely located: "+name+". No particular Pro release is imposed by this tool; locate or adapt this entry.",profile,name);
  }
  internal static bool IsEntryResolved(Dictionary<string,object> item,string profile) {
   object raw;var state=item.TryGetValue("_abi_resolution",out raw)?raw as Dictionary<string,object>:null;
   return state!=null&&state.TryGetValue("profile",out raw)&&Object.Equals(raw,profile)&&state.TryGetValue("status",out raw)&&(Object.Equals(raw,"resolved")||Object.Equals(raw,"verified"));
  }
  internal static void CheckDirectEntry(Dictionary<string,object> item,string kind,string profile) {
   object raw;var state=item.TryGetValue("_abi_resolution",out raw)?raw as Dictionary<string,object>:null;
   string name=item.ContainsKey("class_name")?Convert.ToString(item["class_name"],CultureInfo.InvariantCulture):kind;
   if(state==null||!state.TryGetValue("profile",out raw)||!Object.Equals(raw,profile)||!state.TryGetValue("direct_status",out raw)||(!Object.Equals(raw,"resolved")&&!Object.Equals(raw,"verified")))
    throw new NativeAbiUnavailableException("Current program native "+kind+" direct address fields were not uniquely located: "+name,profile,name);
  }
  internal static void CheckFields(Dictionary<string,object> item,string kind,string profile,params string[] fields) {
   var paths=new string[fields.Length];for(int i=0;i<fields.Length;i++){if(String.IsNullOrEmpty(fields[i])||!item.ContainsKey(fields[i]))throw new InvalidDataException("Native field reader requested an absent field: "+fields[i]);paths[i]="/"+fields[i].Replace("~","~0").Replace("/","~1");}
   CheckPaths(item,kind,profile,paths);
  }
  internal static void CheckPaths(Dictionary<string,object> item,string kind,string profile,params string[] paths) {
   object raw;var state=item.TryGetValue("_abi_resolution",out raw)?raw as Dictionary<string,object>:null;
   string name=item.ContainsKey("name")?Convert.ToString(item["name"],CultureInfo.InvariantCulture):kind;
   if(state==null||!state.TryGetValue("profile",out raw)||!Object.Equals(raw,profile)||!state.TryGetValue("json_pointer",out raw)||!(raw is string))
    throw new NativeAbiUnavailableException("Native field reader lacks its bound entry identity: "+name,profile,name);
   string prefix=(string)raw;
   foreach(string pathPart in paths){
    if(String.IsNullOrEmpty(pathPart)||pathPart[0]!='/')throw new InvalidDataException("Native entry path must be an explicit relative JSON pointer.");
    string pointer=prefix+pathPart;
    object selected=item;foreach(string encoded in pathPart.Substring(1).Split('/')){string key=encoded.Replace("~1","/").Replace("~0","~");var map=selected as Dictionary<string,object>;if(map!=null){if(!map.TryGetValue(key,out selected))throw new InvalidDataException("Native entry path is absent: "+pathPart);}else{var list=selected as IList;int index;if(list==null||!Int32.TryParse(key,NumberStyles.None,CultureInfo.InvariantCulture,out index)||index<0||index>=list.Count)throw new InvalidDataException("Native entry array index is absent: "+pathPart);selected=list[index];}}
    object details;if(!state.TryGetValue("details",out details)||!(details is IEnumerable))throw new InvalidDataException("Native field reader has no resolution details.");
    foreach(object value in(IEnumerable)details){var detail=value as Dictionary<string,object>;if(detail==null)throw new InvalidDataException("Native field resolution detail is not an object.");
     object path;if(!detail.TryGetValue("json_pointer",out path)||!(path is string))throw new InvalidDataException("Native field resolution detail has no path.");
     if((string)path==pointer||((string)path).StartsWith(pointer+"/",StringComparison.Ordinal)||pointer.StartsWith((string)path+"/",StringComparison.Ordinal))throw new NativeAbiUnavailableException("Native "+kind+" field was not uniquely located: "+name+pathPart,profile,name+pathPart);
    }
   }
  }
  internal static int UnresolvedRva(string entry) {
   throw new NativeAbiUnavailableException("Current program native address was not uniquely located: "+entry+". No particular Pro release is imposed by this tool; locate or adapt this entry.","classified C# PE address",entry);
  }
  internal static Dictionary<string,object> Metadata(Exception error) {
   while(error!=null) {
    var problem=error as NativeAbiUnavailableException;
    if(problem!=null)return new Dictionary<string,object>{{"native_abi_status",problem.Status},{"affected_profile",problem.Profile},{"affected_entry",problem.Entry},{"upgrade_required",false},{"software_version_gate",false}};
    error=error.InnerException;
   }
   return new Dictionary<string,object>();
  }
  internal static Dictionary<string,object> BindingMetadata() {
   return new Dictionary<string,object>{{"mode","current_program_resolved"},{"cross_build_contract","mcgs-native-cross-build/v4"},{"entry_validation_contract",LazyEntryContract},{"profile_index_sha256",ExpectedIndexSha256},{"reference_RVAs_used_directly",false},{"operation_entry_validation",true},{"selected_module_equivalent_copy",true},{"field_resolution_validation",true}};
  }
  internal static bool MatchesLogicalOrdinalName(string module,string name,int actualOrdinal) {
   Load();
   foreach(var row in sourceOrdinals) {
    object raw;
    if(Text(row,"module")==module&&Text(row,"status")=="verified"&&row.TryGetValue("actual_ordinal",out raw)&&raw!=null&&Convert.ToInt32(raw,CultureInfo.InvariantCulture)==actualOrdinal&&name=="MfcOrdinal"+Convert.ToString(row["reference_ordinal"],CultureInfo.InvariantCulture))return true;
   }
   return false;
  }
  internal static void RelocateSourceGuard(int actualRva,byte[] expected) {
   Load();string id=null;
   foreach(var row in sourceGuards.Values) {
    object raw;
    if(row.TryGetValue("actual_rva",out raw)&&raw!=null&&Convert.ToInt32(raw,CultureInfo.InvariantCulture)==actualRva&&Convert.ToInt32(row["length"],CultureInfo.InvariantCulture)==expected.Length&&Text(row,"module")=="editor") {
     if(id!=null)throw new InvalidDataException("Current source guard address/length is ambiguous.");
     id=Text(row,"id");
    }
   }
   if(id==null)throw new NativeAbiUnavailableException("Current source byte guard has no resolved native entry.","classified C# byte guard",actualRva.ToString("x",CultureInfo.InvariantCulture));
   RelocateSourceGuard(id,expected);
  }
  internal static void RelocateSourceGuard(string id,byte[] expected) {
   Load();Dictionary<string,object> row;
   if(!sourceGuards.TryGetValue(id,out row)||Text(row,"status")!="verified")
    throw new NativeAbiUnavailableException("Current source byte guard was not uniquely located: "+id+". No particular Pro release is imposed by this tool; locate or adapt this entry.","classified C# byte guard",id);
   string canonical=BitConverter.ToString(expected).Replace("-","").ToLowerInvariant();
   if(canonical!=Text(row,"bytes_at_reference_preferred_base"))throw new InvalidDataException("Bound source guard differs from its current target index: "+id);
   IntPtr module=ModuleHandle(Text(row,"module"));
   if(module==IntPtr.Zero)throw new InvalidDataException("Current source guard module is not loaded.");
   NativeCodeRelocation.RebaseInPlace(expected,(IEnumerable)row["highlow_offsets"],unchecked((uint)module.ToInt32()),Convert.ToUInt32(row["reference_preferred_base"],CultureInfo.InvariantCulture));
  }
  static Dictionary<string,object> ModuleRow(string logicalName) {
   Load();string basename=String.IsNullOrEmpty(logicalName)?"":Path.GetFileName(logicalName);bool rooted=!String.IsNullOrEmpty(logicalName)&&Path.IsPathRooted(logicalName);Dictionary<string,object> found=null;
   // Logical roles take precedence over another role's coincident basename.
   // This also permits explicitly mapped roles to share one merged module.
   if(!rooted)foreach(var row in modules)if(basename.Equals(Text(row,"logical_name"),StringComparison.OrdinalIgnoreCase))return row;
   foreach(var row in modules) {
    object raw;bool matches;
    if(rooted&&row.TryGetValue("actual_file",out raw)&&raw is string)matches=Path.GetFullPath(logicalName).Equals(Path.GetFullPath((string)raw),StringComparison.OrdinalIgnoreCase);
    else matches=basename.Equals(Text(row,"logical_name"),StringComparison.OrdinalIgnoreCase)||basename.Equals(Text(row,"reference_basename"),StringComparison.OrdinalIgnoreCase)||basename.Equals(Text(row,"actual_basename"),StringComparison.OrdinalIgnoreCase);
    if(!matches)continue;
    if(found!=null&&!Object.ReferenceEquals(found,row)){
     object a,b;bool same=found.TryGetValue("actual_file",out a)&&row.TryGetValue("actual_file",out b)&&a is string&&b is string&&Path.GetFullPath((string)a).Equals(Path.GetFullPath((string)b),StringComparison.OrdinalIgnoreCase)&&Text(found,"actual_sha256")==Text(row,"actual_sha256");
     if(!same)throw new InvalidDataException("Native logical module selection is ambiguous: "+logicalName);
    }
    found=row;
   }
   return found;
  }
  internal static string ModuleFile(string logicalName) {
   var row=ModuleRow(logicalName);if(row==null)throw new NativeAbiUnavailableException("Native module has no current bound file: "+logicalName,"selected modules",logicalName);
   object raw;string path=null;
   if(row.TryGetValue("actual_file",out raw)&&raw is string)path=Path.GetFullPath((string)raw);
   else foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(Path.GetFileName(loaded.FileName).Equals(Text(row,"actual_basename"),StringComparison.OrdinalIgnoreCase)){
    if(path!=null&&!path.Equals(Path.GetFullPath(loaded.FileName),StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Legacy native module path is ambiguous: "+logicalName);
    path=Path.GetFullPath(loaded.FileName);
   }
   if(path==null||!File.Exists(path))throw new InvalidDataException("Native module file is unavailable for this target's API binding: "+logicalName);
   lock(Sync){string key=Text(row,"logical_name");if(!verifiedModules.Contains(key)){if(HashFile(path)!=Text(row,"actual_sha256"))throw new InvalidDataException("Native module file changed since this target's API binding: "+logicalName);verifiedModules.Add(key);}}
   return path;
  }
  internal static IntPtr ModuleHandle(string logicalName) {
   var row=ModuleRow(logicalName);if(row==null)return GetModuleHandle(logicalName);
   string file=ModuleFile(logicalName);IntPtr handle=IntPtr.Zero;
   foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules){if(Path.GetFullPath(loaded.FileName).Equals(file,StringComparison.OrdinalIgnoreCase)){
     if(handle!=IntPtr.Zero&&handle!=loaded.BaseAddress)throw new InvalidDataException("Selected native module is loaded more than once: "+logicalName);
     handle=loaded.BaseAddress;
    }
   }
   // Activation contexts and directory aliases may load an equivalent copy.
   // Accept it only when exactly one live module has the selected full content;
   // a basename alone, or two equal copies with distinct bases, is not proof.
   if(handle==IntPtr.Zero){
    foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules){string actual;try{actual=HashFile(loaded.FileName);}catch(IOException){continue;}catch(UnauthorizedAccessException){continue;}
     if(actual!=Text(row,"actual_sha256"))continue;
     if(handle!=IntPtr.Zero&&handle!=loaded.BaseAddress)throw new InvalidDataException("Equivalent native module content has multiple loaded owners: "+logicalName);
     handle=loaded.BaseAddress;
    }
   }
   if(Convert.ToBoolean(row["is_editor"],CultureInfo.InvariantCulture)&&handle!=Process.GetCurrentProcess().MainModule.BaseAddress)throw new InvalidDataException("Selected native editor differs from the attached host.");
   return handle;
  }
  internal static string ReadAllText(string path) {CheckProfile(path,true);return File.ReadAllText(path);}
  internal static string ReadAllText(string path,Encoding encoding) {CheckProfile(path,true);return File.ReadAllText(path,encoding);}
  internal static byte[] ReadAllBytes(string path) {CheckProfile(path,true);return File.ReadAllBytes(path);}
 }
}
