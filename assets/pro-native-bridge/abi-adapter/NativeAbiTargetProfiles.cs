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
    var map=new JavaScriptSerializer{MaxJsonLength=16*1024*1024,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(File.ReadAllText(indexPath,new UTF8Encoding(false,true)));
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
   bool partial=status=="partial"&&row.TryGetValue("allow_partial_entries",out allow)&&allow is bool&&(bool)allow;
   if(status!="verified"&&status!="unchanged"&&!partial) {
    object details;
    string explanation=row.TryGetValue("details",out details)?Convert.ToString(details,CultureInfo.InvariantCulture):"Unresolved native method or table";
    throw new NativeAbiUnavailableException("Current program API is unresolved for this feature: "+Text(row,"profile")+"; "+explanation+". No particular Pro release is required; inspect or extend this method's locator.",Text(row,"profile"),"");
   }
   if(verifyBytes&&HashFile(path)!=Text(row,"sha256"))
    throw new InvalidDataException("Resolved native API profile changed after binding: "+Text(row,"profile"));
  }
  internal static void CheckEntry(Dictionary<string,object> item,string kind) {
   object raw;string name=item.ContainsKey("name")?Convert.ToString(item["name"],CultureInfo.InvariantCulture):kind;
   var state=item.TryGetValue("_abi_resolution",out raw)?raw as Dictionary<string,object>:null;
   if(state==null||!state.ContainsKey("status")||(Convert.ToString(state["status"],CultureInfo.InvariantCulture)!="resolved"&&Convert.ToString(state["status"],CultureInfo.InvariantCulture)!="verified"))
    throw new NativeAbiUnavailableException("Current program native "+kind+" was not uniquely located: "+name+". No particular Pro release is imposed by this tool; locate or adapt this entry.","static/read-tree-guard-profile.json",name);
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
   return new Dictionary<string,object>{{"mode","current_program_resolved"},{"profile_index_sha256",ExpectedIndexSha256},{"reference_RVAs_used_directly",false}};
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
   uint delta=unchecked((uint)module.ToInt32()-Convert.ToUInt32(row["reference_preferred_base"],CultureInfo.InvariantCulture));
   foreach(object value in (IEnumerable)row["highlow_offsets"]) {
    int offset=Convert.ToInt32(value,CultureInfo.InvariantCulture);
    if(offset<0||offset>expected.Length-4)throw new InvalidDataException("Current source guard relocation exceeds its byte range.");
    Array.Copy(BitConverter.GetBytes(unchecked(BitConverter.ToUInt32(expected,offset)+delta)),0,expected,offset,4);
   }
  }
  internal static IntPtr ModuleHandle(string logicalName) {
   Load();string basename=String.IsNullOrEmpty(logicalName)?"":Path.GetFileName(logicalName);
   foreach(var row in modules) {
    if(!basename.Equals(Text(row,"logical_name"),StringComparison.OrdinalIgnoreCase)&&!basename.Equals(Text(row,"reference_basename"),StringComparison.OrdinalIgnoreCase)&&!basename.Equals(Text(row,"actual_basename"),StringComparison.OrdinalIgnoreCase))continue;
    bool editor=Convert.ToBoolean(row["is_editor"],CultureInfo.InvariantCulture);
    IntPtr handle=editor?Process.GetCurrentProcess().MainModule.BaseAddress:GetModuleHandle(Text(row,"actual_basename"));
    if(handle==IntPtr.Zero)return handle;
    string expected=Text(row,"actual_sha256"),key=Text(row,"logical_name");
    lock(Sync) {
     if(!verifiedModules.Contains(key)) {
      string file=null;
      foreach(ProcessModule loaded in Process.GetCurrentProcess().Modules)if(loaded.BaseAddress==handle){file=loaded.FileName;break;}
      if(file==null||HashFile(file)!=expected)throw new InvalidDataException("Loaded native module changed since this target's API binding: "+key);
      verifiedModules.Add(key);
     }
    }
    return handle;
   }
   return GetModuleHandle(logicalName);
  }
  internal static string ReadAllText(string path) {CheckProfile(path,true);return File.ReadAllText(path);}
  internal static string ReadAllText(string path,Encoding encoding) {CheckProfile(path,true);return File.ReadAllText(path,encoding);}
  internal static byte[] ReadAllBytes(string path) {CheckProfile(path,true);return File.ReadAllBytes(path);}
 }
}
