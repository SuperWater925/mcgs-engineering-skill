// Managed data only. No native project/control pointer is read on these workers.
using System;using System.Collections;using System.Collections.Generic;using System.Collections.Concurrent;
using System.Diagnostics;using System.IO;using System.Runtime.CompilerServices;using System.Runtime.InteropServices;
using System.Security.Cryptography;using System.Text;using System.Threading;using System.Threading.Tasks;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeRequestPipeline {
  sealed class Ticket {
   internal Dictionary<string,object> Specification,Inspection;internal int PreparationThread,NativeThread;
   internal double PreparationMs,NativeMs;internal Stopwatch NativeClock;internal TraceWriter Trace;
   internal readonly List<Action> FileWork=new List<Action>();
  }
  static readonly ConditionalWeakTable<Dictionary<string,object>,Ticket> tickets=new ConditionalWeakTable<Dictionary<string,object>,Ticket>();
  [ThreadStatic]static Dictionary<string,object> currentNativeRequest;
  [DllImport("kernel32.dll")]static extern int GetCurrentThreadId();
  static string Hash(byte[] value){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(value)).Replace("-","").ToLowerInvariant();}
  static Dictionary<string,object> Clone(Dictionary<string,object> value){var json=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue,RecursionLimit=256};return json.Deserialize<Dictionary<string,object>>(json.Serialize(value));}
  static Dictionary<string,object> ReadDocument(Dictionary<string,object> request,string fileKey,string hashKey,bool requiredHash){
   string path=Path.GetFullPath(Convert.ToString(request[fileKey]));byte[] bytes;
   using(var input=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)){
    if(input.Length>16*1024*1024)throw new InvalidDataException("Specification exceeds16MiB.");bytes=new byte[(int)input.Length];int at=0;while(at<bytes.Length){int count=input.Read(bytes,at,bytes.Length-at);if(count==0)throw new EndOfStreamException();at+=count;}
   }
   object expected;bool hasHash=request.TryGetValue(hashKey,out expected);if(requiredHash&&!hasHash)throw new InvalidDataException("Inspection selectors need their submitted SHA.");if(hasHash&&Hash(bytes)!=Convert.ToString(expected))throw new InvalidDataException("Submitted input file changed.");
   string text;using(var reader=new StreamReader(new MemoryStream(bytes),Encoding.UTF8,true))text=reader.ReadToEnd();
   var document=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue,RecursionLimit=256}.Deserialize<Dictionary<string,object>>(text);if(document==null)throw new InvalidDataException("Input specification must be an object.");return document;
  }
  internal static Dictionary<string,object> Prepare(Dictionary<string,object> submitted){
   if(submitted==null)throw new ArgumentNullException("submitted");var clock=Stopwatch.StartNew();var request=Clone(submitted);var ticket=new Ticket{PreparationThread=GetCurrentThreadId()};
   string operation=request.ContainsKey("op")?Convert.ToString(request["op"]):"";object raw;
   if(operation=="engineering-edit-batch"&&!request.ContainsKey("permit_file")){
    if(request.TryGetValue("specification",out raw)){ticket.Specification=raw as Dictionary<string,object>;if(ticket.Specification==null)throw new InvalidDataException("Specification must be an object.");}
    else if(request.ContainsKey("specification_file"))ticket.Specification=ReadDocument(request,"specification_file","specification_sha256",false);
   }
   if(operation=="engineering-edit-inspect"&&request.ContainsKey("inspection_file"))ticket.Inspection=ReadDocument(request,"inspection_file","inspection_sha256",true);
   ticket.PreparationMs=clock.Elapsed.TotalMilliseconds;tickets.Add(request,ticket);return request;
  }
  internal static bool IsPrepared(Dictionary<string,object> request){Ticket value;return request!=null&&tickets.TryGetValue(request,out value);}
  internal static bool TrySpecification(Dictionary<string,object> request,out Dictionary<string,object> specification){Ticket value;specification=null;if(request==null||!tickets.TryGetValue(request,out value)||value.Specification==null)return false;specification=value.Specification;return true;}
  internal static bool TryInspection(Dictionary<string,object> request,out Dictionary<string,object> specification){Ticket value;specification=null;if(request==null||!tickets.TryGetValue(request,out value)||value.Inspection==null)return false;specification=value.Inspection;return true;}
  internal static void NativeStarted(Dictionary<string,object> request){currentNativeRequest=request;Ticket value;if(request!=null&&tickets.TryGetValue(request,out value)){value.NativeThread=GetCurrentThreadId();value.NativeClock=Stopwatch.StartNew();}}
  internal static void NativeFinished(Dictionary<string,object> request,TraceWriter trace){currentNativeRequest=null;Ticket value;if(request!=null&&tickets.TryGetValue(request,out value)){if(value.NativeClock!=null)value.NativeMs=value.NativeClock.Elapsed.TotalMilliseconds;value.Trace=trace;}if(trace!=null)trace.Complete();}
  internal static bool DeferFileWork(Action work){Ticket value;if(currentNativeRequest==null||!tickets.TryGetValue(currentNativeRequest,out value))return false;value.FileWork.Add(work);return true;}
  internal static Dictionary<string,object> Finish(Dictionary<string,object> request,Dictionary<string,object> result){
   Ticket value;if(!tickets.TryGetValue(request,out value))return NativeEngineeringLargeReceipt.Pack(request,result);var clock=Stopwatch.StartNew();
   try{
    var metrics=new Dictionary<string,object>{{"prepared_thread_id",value.PreparationThread},{"native_thread_id",value.NativeThread},{"response_thread_id",GetCurrentThreadId()},{"preparation_ms",value.PreparationMs},{"native_dispatch_ms",value.NativeMs},{"prepared_specification_reused",value.Specification!=null}};
    var fileClock=Stopwatch.StartNew();foreach(Action work in value.FileWork)work();metrics["deferred_file_jobs"]=value.FileWork.Count;metrics["deferred_file_ms"]=fileClock.Elapsed.TotalMilliseconds;
    if(value.Trace!=null){var traceClock=Stopwatch.StartNew();metrics["trace"]=value.Trace.Drain();metrics["trace_drain_ms"]=traceClock.Elapsed.TotalMilliseconds;}
    result["runtime_pipeline"]=metrics;var packed=NativeEngineeringLargeReceipt.Pack(request,result);packed["response_finalize_elapsed_ms"]=clock.Elapsed.TotalMilliseconds;return packed;
   }finally{tickets.Remove(request);}
  }
  internal sealed class TraceWriter {
   readonly BlockingCollection<Dictionary<string,object>> rows=new BlockingCollection<Dictionary<string,object>>();readonly Task writer;readonly string file;
   int count,batches,writerThread;string error;bool completed;
   internal TraceWriter(string destination){file=destination;writer=Task.Factory.StartNew(Write,CancellationToken.None,TaskCreationOptions.None,TaskScheduler.Default);}
   internal void Add(Dictionary<string,object> row){if(!completed)rows.Add(row);}
   internal void Complete(){if(completed)return;completed=true;rows.CompleteAdding();}
   void Write(){
    writerThread=GetCurrentThreadId();try{
     Directory.CreateDirectory(Path.GetDirectoryName(file));using(var output=new FileStream(file,FileMode.Append,FileAccess.Write,FileShare.ReadWrite)){
      var json=new JavaScriptSerializer{MaxJsonLength=Int32.MaxValue};
      while(!rows.IsCompleted){Dictionary<string,object> row;if(!rows.TryTake(out row,20))continue;var text=new StringBuilder();int n=0;
       do{text.Append(json.Serialize(row));text.Append(Environment.NewLine);n++;}while(n<256&&rows.TryTake(out row));
       byte[] bytes=new UTF8Encoding(false).GetBytes(text.ToString());output.Write(bytes,0,bytes.Length);output.Flush();count+=n;batches++;
      }
      output.Flush(true);
     }
    }catch(Exception failure){error=failure.GetType().Name+": "+failure.Message;while(!rows.IsCompleted){Dictionary<string,object> ignored;rows.TryTake(out ignored,20);}}
   }
   internal Dictionary<string,object> Drain(){Complete();writer.Wait();rows.Dispose();return new Dictionary<string,object>{{"complete",error==null},{"error",error},{"rows_written",count},{"write_batches",batches},{"writer_thread_id",writerThread},{"flush_to_disk_at_request_end",true}};}
  }
 }
}
