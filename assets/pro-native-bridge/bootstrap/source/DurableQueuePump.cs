// Own queue transport only. Does not call vendor APIs, activate COM, or retry a dispatcher.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal sealed class DurableQueuePump {
        readonly string root,inbox,outbox,processed,claims,claimed,quarantine;
        readonly Func<Dictionary<string,object>,Action,Dictionary<string,object>> dispatch;
        readonly Func<Dictionary<string,object>> metadata;
        readonly Action<string,Exception> log;
        readonly JavaScriptSerializer json=new JavaScriptSerializer{MaxJsonLength=1024*1024,RecursionLimit=40};
        readonly int processId;readonly long processStartTicks;
        readonly Queue<string> recoveryWork=new Queue<string>(),pendingWork=new Queue<string>();
        readonly HashSet<string> observedClaims=new HashSet<string>(StringComparer.OrdinalIgnoreCase),pendingClaims=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        DateTime nextClaimEnumeration=DateTime.MinValue,nextPendingReview=DateTime.MinValue;
        IEnumerator<string> claimEnumeration;
        internal int ClaimReadCount,ClaimEnumerationCount;
        string lastInboxPath;
        int busy;
        internal DurableQueuePump(string directory,Func<Dictionary<string,object>,Dictionary<string,object>> handler,Func<Dictionary<string,object>> fields,Action<string,Exception> logger)
            :this(directory,delegate(Dictionary<string,object> request,Action enter){enter();return handler(request);},fields,logger){}
        internal DurableQueuePump(string directory,Func<Dictionary<string,object>,Action,Dictionary<string,object>> handler,Func<Dictionary<string,object>> fields,Action<string,Exception> logger) {
            root=Path.GetFullPath(directory);inbox=Path.Combine(root,"inbox");outbox=Path.Combine(root,"outbox");processed=Path.Combine(root,"processed");
            claims=Path.Combine(root,"claims");claimed=Path.Combine(root,"claimed");quarantine=Path.Combine(root,"quarantine");
            dispatch=handler;metadata=fields;log=logger;
            using(var process=Process.GetCurrentProcess()){processId=process.Id;processStartTicks=process.StartTime.ToUniversalTime().Ticks;}
        }
        internal bool PumpOne() {
            if(Interlocked.CompareExchange(ref busy,1,0)!=0)return false;
            try {
                EnsureDirectories();RecoverInterruptedClaims();
                string[] paths=Directory.GetFiles(inbox,"*.json");Array.Sort(paths,StringComparer.Ordinal);
                int start=0;if(lastInboxPath!=null){start=Array.BinarySearch(paths,lastInboxPath,StringComparer.Ordinal);start=start>=0?start+1:~start;if(start>=paths.Length)start=0;}
                for(int examined=0;examined<paths.Length&&examined<32;examined++){string path=paths[(start+examined)%paths.Length];lastInboxPath=path;if(ProcessRequest(path))return true;}
                return false;
            }finally{Interlocked.Exchange(ref busy,0);}
        }
        internal void Pause(){if(claimEnumeration!=null){claimEnumeration.Dispose();claimEnumeration=null;}nextClaimEnumeration=DateTime.MinValue;}
        void EnsureDirectories(){foreach(string path in new[]{root,inbox,outbox,processed,claims,claimed,quarantine}){Directory.CreateDirectory(path);if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw new IOException("Queue directory is a reparse point: "+path);}}
        static string Hash(byte[] value){using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(value)).Replace("-","").ToLowerInvariant();}
        static bool Occupied(string path){return File.Exists(path)||Directory.Exists(path);}
        static byte[] ReadLimited(string path) {
            // Delete sharing lets the winning process atomically take a request while
            // another process finishes its read. Write sharing is deliberately absent.
            using(var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read|FileShare.Delete)) {
                if(file.Length>65536)throw new InvalidDataException("Queue request exceeds64KiB.");
                byte[] data=new byte[(int)file.Length];int at=0;
                while(at<data.Length){int n=file.Read(data,at,data.Length-at);if(n==0)throw new EndOfStreamException("Queue request changed during read.");at+=n;}
                return data;
            }
        }
        static string Decode(byte[] raw){int at=raw.Length>=3&&raw[0]==0xEF&&raw[1]==0xBB&&raw[2]==0xBF?3:0;return new UTF8Encoding(false,true).GetString(raw,at,raw.Length-at);}
        Dictionary<string,object> ReadJson(string path){return json.Deserialize<Dictionary<string,object>>(Decode(ReadLimited(path)));}
        Dictionary<string,object> ReadClaim(string path){ClaimReadCount++;return ReadJson(path);}
        void WriteNew(string path,object value) {
            byte[] data=new UTF8Encoding(false).GetBytes(json.Serialize(value)+Environment.NewLine);
            using(var file=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None)){file.Write(data,0,data.Length);file.Flush(true);}
        }
        void StoreClaim(string path,Dictionary<string,object> state) {
            string temporary=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            WriteNew(temporary,state);File.Replace(temporary,path,null);
        }
        Dictionary<string,object> Response(string id,string outcome,string message,bool entered) {
            return new Dictionary<string,object>{{"ok",false},{"request_id",id},{"error",message},
                {"queue_execution_outcome",outcome},{"business_dispatch_entered",entered},
                {"write_attempted",entered?(object)null:(object)false},{"mutation_state",entered?"unknown":"not_entered"},
                {"automatic_retry",false},{"automatic_rollback",false}};
        }
        void Publish(string id,Dictionary<string,object> response) {
            string output=Path.Combine(outbox,id+".json");
            if(Occupied(output))throw new IOException("Response ID is already occupied; never replace it.");
            foreach(var field in metadata())response[field.Key]=field.Value;
            response["request_id"]=id;
            string temporary=output+"."+Guid.NewGuid().ToString("N")+".tmp";
            WriteNew(temporary,response);File.Move(temporary,output);
            // Optional wake-up only; the durable correlated file remains authoritative.
            try{object scope;if(response.TryGetValue("bridge_bootstrap_scope_sha256",out scope))using(var signal=EventWaitHandle.OpenExisting(@"Local\McgsInternalBridgeReply_"+Convert.ToString(scope)+"_"+id))signal.Set();}catch(WaitHandleCannotBeOpenedException){}catch(UnauthorizedAccessException){}catch(Exception error){log("queue_reply_notification_failed",error);}
        }
        void Quarantine(string path,string reason) {
            if(!Occupied(path))return;
            string target=Path.Combine(quarantine,DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffffff")+"_"+Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(target);
            // File.Move relocates a file symlink itself; it does not open its target.
            File.Move(path,Path.Combine(target,"request.json"));
            WriteNew(Path.Combine(target,"reason.json"),new Dictionary<string,object>{{"reason",reason},{"original_filename",Path.GetFileName(path)},{"utc",DateTime.UtcNow.ToString("o")},{"automatic_retry",false}});
        }
        void TryQuarantine(string path,string reason){try{Quarantine(path,reason);}catch(Exception error){log("queue_quarantine_failed",error);}}
        void Reject(string path,string id,string reason,Exception failure) {
            TryQuarantine(path,reason);
            if(id!=null && !Occupied(Path.Combine(outbox,id+".json"))) {
                try{Publish(id,Response(id,"rejected_before_dispatch",reason,false));}catch(Exception error){log("queue_rejection_receipt_failed",error);}
            }
            if(failure!=null)log("queue_request_rejected",failure);
        }
        static bool Pending(Dictionary<string,object> state){string value=Convert.ToString(state["status"]);return value=="claimed"||value=="dispatching";}
        static bool OwnerMayBeAlive(Dictionary<string,object> state) {
            try {
                int id=Convert.ToInt32(state["owner_process_id"]);long start=Convert.ToInt64(state["owner_process_start_ticks"]);
                using(var process=Process.GetProcessById(id))return !process.HasExited && process.StartTime.ToUniversalTime().Ticks==start;
            }catch(ArgumentException){return false;}catch(InvalidOperationException){return false;}
            catch{return true;} // Permission/metadata uncertainty never grants another execution.
        }
        void RecoverInterruptedClaims() {
            DateTime now=DateTime.UtcNow;
            if(claimEnumeration==null && now>=nextClaimEnumeration) {
                // Enumerate names occasionally; completed history is read at most once
                // per process. Bound initial reads so history cannot monopolize UI ticks.
                claimEnumeration=Directory.EnumerateFiles(claims,"*.json").GetEnumerator();
                ClaimEnumerationCount++;nextClaimEnumeration=now.AddSeconds(30);
            }
            int names=64;
            try{while(claimEnumeration!=null && names-->0){if(!claimEnumeration.MoveNext()){claimEnumeration.Dispose();claimEnumeration=null;break;}string path=claimEnumeration.Current;if(observedClaims.Add(path))recoveryWork.Enqueue(path);}}
            catch{if(claimEnumeration!=null){claimEnumeration.Dispose();claimEnumeration=null;}throw;}
            int budget=32;
            while(budget-->0 && recoveryWork.Count>0){string path=recoveryWork.Dequeue();if(RecoverOneClaim(path)&&pendingClaims.Add(path))pendingWork.Enqueue(path);}
            if(now>=nextPendingReview) {
                int count=Math.Min(16,pendingWork.Count);
                while(count-->0){string path=pendingWork.Dequeue();if(RecoverOneClaim(path))pendingWork.Enqueue(path);else pendingClaims.Remove(path);}
                nextPendingReview=now.AddSeconds(1);
            }
        }
        bool RecoverOneClaim(string path) {
            try {
                    if(Occupied(path+".failed-before-dispatch"))return false;
                    if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0){log("queue_claim_reparse_blocked",new IOException("Claim is a reparse point."));return false;}
                    var state=ReadClaim(path);if(state==null||!Pending(state))return false;if(OwnerMayBeAlive(state))return true;
                    string id=Path.GetFileNameWithoutExtension(path);
                    if(!Regex.IsMatch(id,@"\A[A-Za-z0-9_-]{1,80}\z")){log("queue_invalid_claim_blocked",new InvalidDataException("Invalid durable claim filename."));return false;}
                    state["status"]="ambiguous";state["error"]="Claim owner exited before durable completion; do not replay.";state["automatic_retry"]=false;state["automatic_rollback"]=false;
                    StoreClaim(path,state);
                    TryQuarantine(Path.Combine(claimed,id+".json"),"interrupted_claim_ambiguous");
                    TryQuarantine(Path.Combine(inbox,id+".json"),"interrupted_claim_ambiguous");
                    if(!Occupied(Path.Combine(outbox,id+".json")))try{var recoveryResponse=Response(id,"ambiguous",Convert.ToString(state["error"]),true);object captured;if(state.TryGetValue("request_sha256",out captured))recoveryResponse["queue_request_sha256"]=captured;if(state.TryGetValue("claim_token",out captured))recoveryResponse["queue_claim_token"]=captured;recoveryResponse["queue_automatic_retry"]=false;Publish(id,recoveryResponse);state["response_published"]=true;StoreClaim(path,state);}catch(Exception error){log("queue_ambiguous_receipt_failed",error);}
                    return false;
            }catch(Exception error){log("queue_claim_recovery_blocked",error);return true;}
        }
        bool ProcessRequest(string path) {
            string id=Path.GetFileNameWithoutExtension(path);
            if(!Regex.IsMatch(id,@"\A[A-Za-z0-9_-]{1,80}\z")){Reject(path,null,"invalid_request_filename",new InvalidDataException("Invalid queue file ID."));return false;}
            string output=Path.Combine(outbox,id+".json"),history=Path.Combine(processed,id+".json"),claimPath=Path.Combine(claims,id+".json"),owned=Path.Combine(claimed,id+".json");
            try {
                if(!File.Exists(path))return false;
                if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0){Reject(path,id,"input_reparse_point_rejected_before_read",null);return false;}
                if(Occupied(output)||Occupied(history)){TryQuarantine(path,"duplicate_completed_id_never_dispatch");return false;}
                if(Occupied(claimPath)) {
                    if(Occupied(claimPath+".failed-before-dispatch")){TryQuarantine(path,"failed_claim_reserved_no_dispatch");return false;}
                    // A concurrent winner may not have moved the original inbox file yet.
                    // Never steal that file while its durable owner may still be alive.
                    try{var existing=ReadClaim(claimPath);if(existing!=null&&!Pending(existing))TryQuarantine(path,"duplicate_reserved_id_never_dispatch");else if(existing!=null&&!OwnerMayBeAlive(existing))RecoverOneClaim(claimPath);}
                    catch(Exception error){log("queue_existing_claim_blocked",error);}
                    return false;
                }
                byte[] raw=ReadLimited(path);Dictionary<string,object> request;
                try{
                    request=json.Deserialize<Dictionary<string,object>>(Decode(raw));if(request==null)throw new InvalidDataException("Expected a request object.");
                    object value;if(!request.TryGetValue("op",out value)||!(value is string)||!Regex.IsMatch((string)value,@"\A[a-z][a-z0-9_-]{0,79}\z"))throw new InvalidDataException("Expected a nonempty lowercase transport operation of at most80 characters.");
                    if(request.TryGetValue("request_id",out value)&&(!(value is string)||(string)value!=id))throw new InvalidDataException("Payload request_id differs from its queue filename.");
                    if(request.TryGetValue("schema",out value)&&(!(value is int)||(int)value!=1))throw new InvalidDataException("Unknown transport schema; only schema1 or legacy absent schema is accepted.");
                }
                catch(Exception error){Reject(path,id,"malformed_request",error);return false;}
                string token=Guid.NewGuid().ToString("N"),requestSha=Hash(raw);
                var state=new Dictionary<string,object>{{"schema",1},{"request_id",id},{"request_sha256",requestSha},{"claim_token",token},
                    {"status","claimed"},{"owner_process_id",processId},{"owner_process_start_ticks",processStartTicks},{"claimed_utc",DateTime.UtcNow.ToString("o")},
                    {"automatic_retry",false},{"automatic_rollback",false}};
                bool claimAcquired=false;
                try {
                    byte[] claimBytes=new UTF8Encoding(false).GetBytes(json.Serialize(state)+Environment.NewLine);
                    using(var file=new FileStream(claimPath,FileMode.CreateNew,FileAccess.Write,FileShare.None)){claimAcquired=true;file.Write(claimBytes,0,claimBytes.Length);file.Flush(true);}
                    observedClaims.Add(claimPath);
                }catch(Exception error) {
                    int code=error.HResult&0xffff;
                    if(!claimAcquired && error is IOException && (code==80||code==183) && Occupied(claimPath)){log("queue_claim_not_acquired",error);return false;}
                    if(claimAcquired) {
                        // Preserve even a zero-byte/partly written reservation forever.
                        // The failed claim is not a normal competing-owner condition.
                        var failure=new Dictionary<string,object>{{"status","failed_claim_before_dispatch"},{"claim_acquired",true},{"claim_durability","unknown_or_incomplete"},{"business_dispatch_entered",false},{"request_sha256",requestSha},{"error_type",error.GetType().Name},{"error",error.Message},{"automatic_retry",false},{"automatic_rollback",false}};
                        try{WriteNew(claimPath+".failed-before-dispatch",failure);}catch(Exception marker){log("queue_failed_claim_marker_not_durable",marker);}
                        Reject(path,id,"claim_write_or_flush_failed_before_dispatch",error);log("queue_failed_claim_before_dispatch",error);return false;
                    }
                    if(Occupied(claimPath)){log("queue_claim_create_uncertain_no_dispatch",error);return false;}
                    throw;
                }
                bool entered=false,published=false;
                try {
                    File.Move(path,owned);
                    if((File.GetAttributes(owned)&FileAttributes.ReparsePoint)!=0 || Hash(ReadLimited(owned))!=requestSha)throw new IOException("Claimed payload differs from the captured request.");
                    // Preparation is file/managed-only. Persist dispatching on this
                    // worker immediately before scheduling the one UI dispatch.
                    var dispatchClock=Stopwatch.StartNew();
                    Dictionary<string,object> response=dispatch(request,delegate{
                        if(entered)throw new InvalidOperationException("Dispatcher entry cannot repeat.");
                        state["status"]="dispatching";StoreClaim(claimPath,state);entered=true;
                    });
                    if(response==null)throw new InvalidOperationException("Dispatcher returned no response.");
                    response["queue_dispatch_elapsed_ms"]=dispatchClock.Elapsed.TotalMilliseconds;
                    response["queue_claim_token"]=token;response["queue_request_sha256"]=requestSha;response["queue_automatic_retry"]=false;
                    Publish(id,response);published=true;
                    File.Move(owned,history);
                    state["status"]="completed";state["response_published"]=true;state["completed_utc"]=DateTime.UtcNow.ToString("o");StoreClaim(claimPath,state);
                    return true;
                }catch(Exception error) {
                    state["status"]=entered?"ambiguous":"rejected_before_dispatch";state["business_dispatch_entered"]=entered;state["response_published"]=published;
                    state["error_type"]=error.GetType().Name;state["error"]=error.Message;state["automatic_retry"]=false;state["automatic_rollback"]=false;
                    try{StoreClaim(claimPath,state);}catch(Exception persist){log("queue_durable_state_update_failed",persist);}
                    TryQuarantine(owned,entered?"dispatch_or_publish_or_cleanup_ambiguous":"claimed_pre_dispatch_failure");
                    TryQuarantine(path,entered?"dispatch_or_publish_or_cleanup_ambiguous":"claimed_pre_dispatch_failure");
                    if(!Occupied(output))try{var failureResponse=Response(id,entered?"ambiguous":"rejected_before_dispatch",error.Message,entered);failureResponse["queue_claim_token"]=token;failureResponse["queue_request_sha256"]=requestSha;failureResponse["queue_automatic_retry"]=false;Publish(id,failureResponse);published=true;state["response_published"]=true;StoreClaim(claimPath,state);}catch(Exception receipt){log("queue_failure_receipt_failed",receipt);}
                    log(entered?"queue_ambiguous_dispatch":"queue_claim_pre_dispatch_rejected",error);return entered;
                }
            }catch(Exception error){Reject(path,id,"request_pre_dispatch_io_rejected",error);return false;}
        }
    }
}
