using System;using System.Collections;using System.Collections.Generic;using System.IO;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static partial class NativeUsableDeviceBatch {
  internal static NativeReferenceModulePersistence.IParticipant PrepareReferencePersistence(NativeEngine e,NativeContext c,string p){NativeMemory.Require(Path.GetFullPath(p).Equals(NativeUsableEditPermit.Fixture,StringComparison.OrdinalIgnoreCase),"Related Device project differs.");return new ReferenceParticipant(new Api(e,c));}
  sealed class ReferenceParticipant:NativeReferenceModulePersistence.IParticipant {
   readonly Api api;internal ReferenceParticipant(Api a){api=a;}
   public int ModuleId{get{return 1;}}
   public Dictionary<string,object> Capture(){api.Current();var configured=DriverProperties.CaptureConfigured(api.Engine,api.Context,NativeUsableEditPermit.Fixture);var rows=new List<object>();foreach(object entry in (IEnumerable)configured["known_device_records"])rows.Add(entry);var semantics=new Dictionary<string,object>();var cacheRows=new JavaScriptSerializer{MaxJsonLength=64*1024*1024}.Deserialize<List<Dictionary<string,object>>>(Convert.ToString(configured["native_driver_cache_catalog"]));foreach(var row in cacheRows){var cache=Map(row["cache"]);object business;semantics.Add(Convert.ToString(row["name"]),cache.TryGetValue("semantic_used_cache",out business)?business:null);}return new Dictionary<string,object>{{"module_id",1},{"manager",NativeMemory.Hex(api.Manager)},{"document",NativeMemory.Hex(api.Document)},{"raw_known_records",rows},{"configured_raw",configured},{"driver_cache_semantics",semantics},{"dirty",NativeMemory.I32(api.Document,0x48)},{"full_unknown_serialization_claimed",false}};}
   public Dictionary<string,object> Flush(NativeUsableEditPermit.Lease lease,Dictionary<string,object> action){api.Current();var current=DriverProperties.PrepareConfiguredPersistence(api.Engine,api.Context,NativeUsableEditPermit.Fixture);var result=current.FlushRelated(lease,action);result["module_id"]=1;result["file_acceptance_verified"]=false;return result;}
   public void Dispose(){}
  }
 }
}
