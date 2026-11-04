// Vendor whole-file hashes are observations, never release/build admission gates.
// Structural ABI, owner, request and immutable own-payload checks remain separate.
using System;using System.Collections.Generic;using System.Threading;
namespace McgsInternalBridge {
 internal static class NativeBinaryIdentity {
  const int MaximumDifferences=256;
  sealed class RequestState {
   internal string Id;internal long Sequence,Observations,Mismatches;
   internal readonly List<Dictionary<string,object>> Differences=new List<Dictionary<string,object>>();
   internal readonly HashSet<string> Seen=new HashSet<string>(StringComparer.Ordinal);
  }
  static long nextSequence;
  [ThreadStatic]static RequestState current;
  internal static void Begin(Dictionary<string,object> request){
   if(current!=null)throw new InvalidOperationException("Nested binary-observation request scope is not supported.");
   object value;string id=null;if(request!=null&&(request.TryGetValue("request_id",out value)||request.TryGetValue("id",out value)))id=Convert.ToString(value);
   current=new RequestState{Id=id,Sequence=Interlocked.Increment(ref nextSequence)};
  }
  internal static bool Observe(string expected,string actual,string role){
   RequestState state=current;if(state==null)return true;
   state.Observations++;
   if(String.Equals(expected,actual,StringComparison.OrdinalIgnoreCase))return true;
   state.Mismatches++;
   // Cap both retained rows and dedup keys. Total mismatch count remains truthful.
   if(state.Differences.Count<MaximumDifferences){
    string key=(role??"")+"\0"+(expected??"")+"\0"+(actual??"");
    if(state.Seen.Add(key))state.Differences.Add(new Dictionary<string,object>{{"role",role},{"expected_sha256",expected},{"actual_sha256",actual},{"match",false}});
   }
   return true;
  }
  internal static Dictionary<string,object> Snapshot(){
   RequestState state=current;var rows=new List<object>();
   if(state!=null)foreach(var difference in state.Differences)rows.Add(new Dictionary<string,object>(difference));
   return new Dictionary<string,object>{{"whole_file_sha_admission",false},{"observation_only",true},{"request_active",state!=null},
    {"request_id",state==null?null:state.Id},{"request_sequence",state==null?0:state.Sequence},{"managed_thread_id",Thread.CurrentThread.ManagedThreadId},
    {"observations",state==null?0:state.Observations},{"mismatch_observations",state==null?0:state.Mismatches},
    {"difference_limit",MaximumDifferences},{"retained_differences",rows.Count},{"retention_limit_reached",rows.Count==MaximumDifferences},{"differences",rows}};
  }
  internal static void End(){current=null;}
 }
}
