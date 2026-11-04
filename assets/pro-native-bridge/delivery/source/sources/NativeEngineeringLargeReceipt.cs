// Complete engineering results travel as a bounded, hashed local artifact.
// The stable at-most-once queue retains its existing 1 MiB envelope limit.
using System;using System.Collections.Generic;using System.IO;using System.Text;
using System.Security.Cryptography;using System.Text.RegularExpressions;using System.Web.Script.Serialization;
namespace McgsInternalBridge {
 internal static class NativeEngineeringLargeReceipt {
  const int Maximum=16*1024*1024;
  static string Hash(byte[] bytes){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
  static void Ancestors(string path){string root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\');for(var d=new DirectoryInfo(path);d!=null;d=d.Parent){NativeMemory.Require(d.FullName.Equals(root,StringComparison.OrdinalIgnoreCase)||d.FullName.StartsWith(root+"\\",StringComparison.OrdinalIgnoreCase),"Engineering reply ancestor escaped its task root.");if(d.Exists)NativeMemory.Require((d.Attributes&FileAttributes.ReparsePoint)==0,"Engineering reply ancestor is a reparse point.");if(d.FullName.Equals(root,StringComparison.OrdinalIgnoreCase))return;}throw new InvalidOperationException("Engineering reply task root was not reached.");}
  internal static Dictionary<string,object> Pack(Dictionary<string,object> request,Dictionary<string,object> result){
   string op=Convert.ToString(request["op"]);if(op!="engineering-edit-inspect"&&op!="engineering-edit-batch")return result;
   string id=Convert.ToString(request["request_id"]);NativeMemory.Require(Regex.IsMatch(id??"",@"\A[A-Za-z0-9_-]{1,80}\z"),"Engineering reply needs its exact queue request ID.");
   string claimed=Path.Combine(NativeOperations.TaskRoot,"runtime","claimed",id+".json");Ancestors(Path.GetDirectoryName(claimed));
   NativeMemory.Require((File.GetAttributes(claimed)&(FileAttributes.Directory|FileAttributes.ReparsePoint))==0,"Engineering reply claimed request is not a regular file.");
   byte[] submitted;using(var stream=new FileStream(claimed,FileMode.Open,FileAccess.Read,FileShare.Read|FileShare.Delete)){
    NativeMemory.Require(stream.Length>0&&stream.Length<=65536,"Engineering reply request exceeds its queue bound.");submitted=new byte[(int)stream.Length];int at=0;while(at<submitted.Length){int n=stream.Read(submitted,at,submitted.Length-at);if(n==0)throw new EndOfStreamException();at+=n;}
   }
   var json=new JavaScriptSerializer{MaxJsonLength=Maximum,RecursionLimit=128};
   var original=json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(submitted));
   NativeMemory.Require(Convert.ToString(original["request_id"])==id&&Convert.ToString(original["op"])==op&&Convert.ToString(original["expected_project"])==Convert.ToString(request["expected_project"]),"Engineering reply request identity differs.");
   string requestSha=Hash(submitted);result["request_id"]=id;result["queue_request_sha256"]=requestSha;
   byte[] payload=new UTF8Encoding(false,true).GetBytes(json.Serialize(result)+Environment.NewLine);NativeMemory.Require(payload.Length<=Maximum,"Complete engineering reply exceeds16MiB; narrow the logical selectors.");
   string directory=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"reply-payloads");Ancestors(directory);Directory.CreateDirectory(directory);Ancestors(directory);
   string output=Path.Combine(directory,id+".json"),temporary=output+"."+Guid.NewGuid().ToString("N")+".staging";
   NativeMemory.Require(!File.Exists(output)&&!Directory.Exists(output),"Engineering reply ID already has an artifact; never replace or replay it.");
   using(var stream=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None)){stream.Write(payload,0,payload.Length);stream.Flush(true);}File.Move(temporary,output);
   return new Dictionary<string,object>{{"ok",result["ok"]},{"op",op},{"write_attempted",result["write_attempted"]},{"operation_phase",result["operation_phase"]},
    {"engineering_payload",new Dictionary<string,object>{{"schema",1},{"file",output},{"byte_length",payload.Length},{"sha256",Hash(payload)},{"request_id",id},{"queue_request_sha256",requestSha}}}};
  }
 }
}
