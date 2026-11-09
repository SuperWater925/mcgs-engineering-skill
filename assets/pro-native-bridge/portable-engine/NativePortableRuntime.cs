// Target tables contain current addresses and real artifact hashes; no native calls.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativePortableRuntime {
  internal const string SourceManifestSha256="__PORTABLE_SOURCE_MANIFEST_SHA256__";
  internal const string SourceCatalogSha256="__PORTABLE_SOURCE_CATALOG_SHA256__";
  internal const string EvidenceLayout="flat-v1";
  static readonly object sync=new object();static Dictionary<string,object> binding;
  static volatile Dictionary<string,string> artifactPaths;
  static Dictionary<string,object> Current{get{lock(sync){
   if(binding==null){
    byte[] raw=NativeEngineeringDeliveryLayout.ReadRegular(NativeEngineeringDeliveryLayout.PortableBindingFile);
    NativeAbiTargetProfiles.RequireArtifact(NativeEngineeringDeliveryLayout.HashBytes(raw)==NativeEngineeringDeliveryLayout.PortableBindingSha256,"Portable runtime binding changed.","portable-binding","");
    var value=new JavaScriptSerializer{MaxJsonLength=int.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(new UTF8Encoding(false,true).GetString(raw).TrimStart('\uFEFF'));
    NativeAbiTargetProfiles.RequireArtifact(NativeEngineeringDeliveryLayout.Text(value,"schema")=="mcgs-portable-engine-binding/v1"&&NativeEngineeringDeliveryLayout.Text(value,"engine_contract")==NativeEngineeringDeliveryLayout.PortableEngineContract,"Portable runtime binding schema differs.","portable-binding","schema");
    NativeAbiTargetProfiles.RequireArtifact(NativeEngineeringDeliveryLayout.Text(value,"source_manifest_sha256")==SourceManifestSha256&&NativeEngineeringDeliveryLayout.Text(value,"source_catalog_sha256")==SourceCatalogSha256,"Portable runtime data belongs to another OWN engine release.","portable-binding","source_manifest_sha256/source_catalog_sha256");
    string index=NativeEngineeringDeliveryLayout.Absolute(NativeEngineeringDeliveryLayout.Text(value,"profile_index_file"));
    NativeAbiTargetProfiles.RequireArtifact(NativeEngineeringDeliveryLayout.Within(index,NativeEngineeringDeliveryLayout.EvidenceRoot),"Portable index escapes evidence root.","portable-binding","profile_index_file");
    var paths=ReadArtifactPaths(value);
    binding=value;
    artifactPaths=paths;
   }return binding;
  }}}
  static string WindowsSeparators(string path){return path.Replace('/','\\');}
  static bool CanonicalChild(string path,string root){
   string prefix=root.TrimEnd('\\')+"\\";
   if(!path.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))return false;
   foreach(string part in path.Substring(prefix.Length).Split('\\')){
    if(part.Length==0||part.EndsWith(".",StringComparison.Ordinal)||part.EndsWith(" ",StringComparison.Ordinal))return false;
    foreach(char c in part)if(c<' '||"<>:\"|?*".IndexOf(c)>=0)return false;
   }
   return true;
  }
  static Dictionary<string,string> ReadArtifactPaths(Dictionary<string,object> value){
   var paths=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
   object raw;
   if(!value.TryGetValue("artifact_paths",out raw))return paths;
   var rows=raw as Dictionary<string,object>;
   NativeAbiTargetProfiles.RequireArtifact(rows!=null,"Portable evidence path map must be an object.","portable-binding","artifact_paths");
   string engineering=NativeEngineeringDeliveryLayout.EngineeringRoot,evidence=NativeEngineeringDeliveryLayout.EvidenceRoot;
   foreach(var row in rows){
    string logical=WindowsSeparators(row.Key),target=row.Value as string;
    NativeAbiTargetProfiles.RequireArtifact(CanonicalChild(logical,engineering)&&!paths.ContainsKey(logical),"Portable evidence logical path is invalid or repeated.","artifact_paths",row.Key);
    target=target==null?"":WindowsSeparators(target);
    NativeAbiTargetProfiles.RequireArtifact(CanonicalChild(target,evidence)&&target.Length<260&&target.LastIndexOf('\\')<248,"Portable evidence read path must be a compact child of the evidence root.","artifact_paths",row.Key);
    paths.Add(logical,NativeEngineeringDeliveryLayout.Absolute(target));
   }
   return paths;
  }
  static bool TryArtifactPath(string path,out string logical,out string physical){
   logical=physical=null;
   if(String.IsNullOrEmpty(path))return false;
   var paths=artifactPaths;
   if(paths!=null&&paths.Count==0)return false;
   logical=WindowsSeparators(path);
   if(paths==null){
    if(!NativeEngineeringDeliveryLayout.Within(logical,NativeEngineeringDeliveryLayout.EngineeringRoot))return false;
    var validated=Current;
    paths=artifactPaths;
   }
   return paths.TryGetValue(logical,out physical);
  }
  internal static string EvidenceReadPath(string path){
   string logical,physical;
   return TryArtifactPath(path,out logical,out physical)?physical:path;
  }
  // Keep logical ownership checks, relative profile keys and sibling paths
  // intact, even when the mapped name exceeds the legacy .NET path limit.
  internal static string LogicalFullPath(string path){
   string logical,physical;
   return TryArtifactPath(path,out logical,out physical)?logical:Path.GetFullPath(path);
  }
  internal static string LogicalDirectoryName(string path){
   string logical,physical;
   if(!TryArtifactPath(path,out logical,out physical))return Path.GetDirectoryName(path);
   int end=logical.LastIndexOf('\\');
   return logical.Substring(0,end==2&&logical[1]==':'?end+1:end);
  }
  static Dictionary<string,object> Table(string key){object value;NativeAbiTargetProfiles.RequireArtifact(Current.TryGetValue(key,out value)&&value is Dictionary<string,object>,"Portable runtime table is absent: "+key,"portable-binding",key);return(Dictionary<string,object>)value;}
  static Dictionary<string,object> Row(string table,string key){object value;NativeAbiTargetProfiles.RequireArtifact(Table(table).TryGetValue(key,out value)&&value is Dictionary<string,object>,"Portable runtime entry is absent: "+key,table,key);return(Dictionary<string,object>)value;}
  static int Number(Dictionary<string,object> row,string value,string table,string key){object raw,status;NativeAbiTargetProfiles.RequireArtifact(row.TryGetValue("status",out status),"Portable runtime entry has no status.",table,key);if(!row.TryGetValue(value,out raw)||raw==null||(Convert.ToString(status,CultureInfo.InvariantCulture)!="resolved"&&Convert.ToString(status,CultureInfo.InvariantCulture)!="verified"))throw new NativeAbiUnavailableException("Current program has no resolved native entry for this feature: "+key,table,key);return unchecked((int)Convert.ToInt64(raw,CultureInfo.InvariantCulture));}
  internal static int Address(string key){return Number(Row("source_addresses",key),"encoded_value","source_addresses",key);}
  internal static int Ordinal(string key){return Number(Row("source_ordinals",key),"actual_ordinal","source_ordinals",key);}
  internal static string GuardHex(string key){var row=Row("source_guards",key);if(NativeEngineeringDeliveryLayout.Text(row,"status")!="verified")throw new NativeAbiUnavailableException("Current program source byte guard is unresolved for this feature: "+key,"source_guards",key);return NativeEngineeringDeliveryLayout.Text(row,"bytes_at_reference_preferred_base");}
  internal static string ArtifactSha(string key){object value;NativeAbiTargetProfiles.RequireArtifact(Table("artifact_sha256").TryGetValue(key,out value)&&value is string&&((string)value).Length==64,"Portable artifact digest is absent: "+key,"artifact_sha256",key);return(string)value;}
  internal static string ModuleFile(string key){object value;NativeAbiTargetProfiles.RequireArtifact(Table("module_files").TryGetValue(key,out value)&&value is string,"Portable selected module is absent: "+key,"module_files",key);return NativeEngineeringDeliveryLayout.Absolute((string)value);}
  internal static string IndexFile{get{return NativeEngineeringDeliveryLayout.Text(Current,"profile_index_file");}}
  internal static string IndexSha256{get{return NativeEngineeringDeliveryLayout.Text(Current,"profile_index_sha256");}}
 }
}
