// Preserve a failed comparison at the instant it fails; never repeat native work to recover it.
using System;using System.Collections.Generic;using System.Diagnostics;using System.IO;
using System.Security.Cryptography;using System.Text;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeEngineeringComparisonEvidence {
  static string Hash(byte[] value){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(value)).Replace("-","").ToLowerInvariant();}
  internal static Exception Mismatch(string message,string expected,string actual){
   var failure=new InvalidOperationException(message);
   var metadata=new Dictionary<string,object>();failure.Data["managed_comparison_metadata"]=metadata;
   try{
   var data=new Dictionary<string,object>{{"schema",1},{"message",message},{"process_id",Process.GetCurrentProcess().Id},{"native_thread_id",NativeMemory.GetCurrentThreadId()},{"engine",typeof(NativeEngineeringComparisonEvidence).Assembly.ManifestModule.Name},{"operation_phase",NativeOperationTrace.Phase},{"native_write_attempted",NativeOperationTrace.MutationAttempted},{"expected_json",expected},{"actual_json",actual},{"comparison_rule_changed",false},{"native_calls_repeated",false}};
   if(!NativeRequestPipeline.DeferFileWork(delegate{WriteCaptured(data,metadata);}))WriteCaptured(data,metadata);
   }catch(Exception error){metadata["comparison_evidence_error"]=error.GetType().Name+": "+error.Message;}
   return failure;
  }
  static void WriteCaptured(Dictionary<string,object> data,Dictionary<string,object> metadata){
   try{
    string directory=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"comparison-failures");
    for(var parent=new DirectoryInfo(directory);parent!=null&&parent.FullName.StartsWith(NativeOperations.TaskRoot,StringComparison.OrdinalIgnoreCase);parent=parent.Parent)if(parent.Exists)NativeMemory.Require((parent.Attributes&FileAttributes.ReparsePoint)==0,"Comparison evidence ancestor is a reparse point.");
    Directory.CreateDirectory(directory);NativeMemory.Require((File.GetAttributes(directory)&FileAttributes.ReparsePoint)==0,"Comparison evidence directory is a reparse point.");
    byte[] bytes=new UTF8Encoding(false,true).GetBytes(new JavaScriptSerializer{MaxJsonLength=64*1024*1024,RecursionLimit=128}.Serialize(data)+Environment.NewLine);NativeMemory.Require(bytes.Length<=64*1024*1024,"Comparison evidence exceeds64MiB.");
    string path=Path.Combine(directory,DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffffff")+"-"+Guid.NewGuid().ToString("N")+".json");
    using(var stream=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None)){stream.Write(bytes,0,bytes.Length);stream.Flush(true);}
    metadata["comparison_evidence_file"]=path;metadata["comparison_evidence_sha256"]=Hash(bytes);metadata["comparison_evidence_bytes"]=bytes.Length;
   }catch(Exception error){metadata["comparison_evidence_error"]=error.GetType().Name+": "+error.Message;}
  }
  internal static Dictionary<string,object> Metadata(Exception error){if(error.Data.Contains("managed_comparison_metadata"))return(Dictionary<string,object>)error.Data["managed_comparison_metadata"];var result=new Dictionary<string,object>();foreach(string key in new[]{"comparison_evidence_file","comparison_evidence_sha256","comparison_evidence_bytes","comparison_evidence_error"})if(error.Data.Contains(key))result[key]=error.Data[key];return result;}
 }
}
