// Request-scoped project identity for the new engineering entry only.
using System;using System.Collections.Generic;using System.IO;
namespace McgsInternalBridge {
 internal static class NativeEngineeringProjectScope {
  [ThreadStatic]static string expected;
  internal static string ExpectedProjectPath {get{return expected??Path.GetFullPath(NativeOperations.TaskRoot+@"\fixtures\initial.MCP");}}
  internal static void Enter(Dictionary<string,object> request) {
   NativeMemory.Require(expected==null,"Engineering project scope is already active.");object op;
   if(request==null||!request.TryGetValue("op",out op))return;string name=Convert.ToString(op);
   if(name!="engineering-edit-inspect"&&name!="engineering-edit-batch"&&name!="engineering-project-lifecycle-read"&&name!="engineering-project-close-reopen-original")return;
   object raw;NativeMemory.Require(request.TryGetValue("expected_project",out raw)&&raw is string,"Engineering request needs its exact expected project path.");
   string path=Path.GetFullPath((string)raw),root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";
   NativeMemory.Require(String.Equals(Path.GetExtension(path),".MCP",StringComparison.OrdinalIgnoreCase)&&File.Exists(path),"Engineering project must be an existing Pro MCP file.");
   NativeMemory.Require((File.GetAttributes(path)&FileAttributes.Directory)==0,"Engineering project must be a regular owned file.");
   expected=path;NativeEngineeringFileHashes.Enter();
  }
  internal static void BindNativeIdentity(string actual){if(expected==null)return;string native=Path.GetFullPath(actual);NativeMemory.Require(native.Equals(expected,StringComparison.OrdinalIgnoreCase),"Native engineering scope differs from the validated requested project.");expected=native;}
  internal static void Exit(){try{NativeEngineeringFileHashes.Exit();}finally{expected=null;}}
 }
}
