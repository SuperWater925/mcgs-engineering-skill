// Per-request binary SHA reuse backed by open Windows deny-write/delete handles.
// Project files, permits and JSON contracts always retain their fresh hash path.
using System;using System.Collections.Generic;using System.IO;using System.Security.Cryptography;
namespace McgsInternalBridge {
 internal static class NativeEngineeringFileHashes {
  sealed class Held:IDisposable {
   internal FileStream Stream;internal string Sha;
   public void Dispose(){if(Stream!=null){FileStream s=Stream;Stream=null;s.Dispose();}}
  }
  sealed class Scope:IDisposable {
   internal readonly Dictionary<string,Held> Files=new Dictionary<string,Held>(StringComparer.OrdinalIgnoreCase);
   internal int Hits;
   public void Dispose(){Exception first=null;foreach(Held file in Files.Values)try{file.Dispose();}catch(Exception e){if(first==null)first=e;}Files.Clear();if(first!=null)throw first;}
  }
  [ThreadStatic]static Scope current;
  internal static void Enter(){NativeMemory.Require(current==null,"Binary hash request scope is already active.");current=new Scope();}
  internal static void Exit(){Scope scope=current;current=null;if(scope!=null)scope.Dispose();}
  internal static bool TryHash(string path,out string hash){
   hash=null;Scope scope=current;if(scope==null)return false;
   string extension=Path.GetExtension(path);if(!extension.Equals(".dll",StringComparison.OrdinalIgnoreCase)&&!extension.Equals(".exe",StringComparison.OrdinalIgnoreCase))return false;
   string file=Path.GetFullPath(path);Held held;
   if(scope.Files.TryGetValue(file,out held)){NativeMemory.Require(held.Stream!=null,"Cached binary handle has been released prematurely.");scope.Hits++;hash=held.Sha;return true;}
   held=new Held();try{
    // Sharing read alone denies writes/rename/delete for the entire cache lifetime.
    // A conflicting already-open writer fails preparation instead of weakening it.
    held.Stream=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.Read,65536,FileOptions.SequentialScan);
    using(var sha=SHA256.Create())held.Sha=BitConverter.ToString(sha.ComputeHash(held.Stream)).Replace("-","").ToLowerInvariant();
    scope.Files.Add(file,held);hash=held.Sha;return true;
   }catch{held.Dispose();throw;}
  }
  internal static Dictionary<string,object> Status(){return new Dictionary<string,object>{{"scope","current engineering UI request only"},{"unique_binary_files_hashed",current==null?0:current.Files.Count},{"binary_hash_reuses",current==null?0:current.Hits},{"write_delete_denied_while_reused",true},{"release_at_request_end",true},{"project_permit_JSON_hashes_cached",false},{"engineering_performance_measurement_pending",true}};}
 }
}
