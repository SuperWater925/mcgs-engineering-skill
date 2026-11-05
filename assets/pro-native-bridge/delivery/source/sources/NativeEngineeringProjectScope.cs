// Request-scoped project identity for the new engineering entry only.
using System;using System.Collections.Generic;using System.IO;using System.Runtime.InteropServices;using Microsoft.Win32.SafeHandles;
namespace McgsInternalBridge {
 internal static class NativeEngineeringProjectScope {
  [ThreadStatic]static string expected;
  internal static string ExpectedProjectPath {get{return expected??Path.GetFullPath(NativeOperations.TaskRoot+@"\fixtures\initial.MCP");}}
  internal static void Enter(Dictionary<string,object> request) {
   NativeMemory.Require(expected==null,"Engineering project scope is already active.");NativeLazyFunctionProfile.BeginRequest();object op;
   if(request==null||!request.TryGetValue("op",out op))return;string name=Convert.ToString(op);
   if(name!="engineering-edit-inspect"&&name!="engineering-edit-batch"&&name!="engineering-project-lifecycle-read"&&name!="engineering-project-close-reopen-original")return;
   object raw;NativeMemory.Require(request.TryGetValue("expected_project",out raw)&&raw is string,"Engineering request needs its exact expected project path.");
   string path=Path.GetFullPath((string)raw),root=Path.GetFullPath(NativeOperations.TaskRoot).TrimEnd('\\')+"\\";
   NativeMemory.Require(String.Equals(Path.GetExtension(path),".MCP",StringComparison.OrdinalIgnoreCase)&&File.Exists(path),"Engineering project must be an existing Pro MCP file.");
   NativeMemory.Require((File.GetAttributes(path)&FileAttributes.Directory)==0,"Engineering project must be a regular owned file.");
   expected=path;NativeEngineeringFileHashes.Enter();
  }
  internal static void BindNativeIdentity(string actual){if(expected==null)return;string native=Path.GetFullPath(actual);NativeMemory.Require(SameFile(native,expected),"Native engineering scope differs from the validated requested project.");expected=native;}
  [StructLayout(LayoutKind.Sequential)]struct FileInformation {internal uint Attributes,CreationLow,CreationHigh,AccessLow,AccessHigh,WriteLow,WriteHigh,VolumeSerial,SizeHigh,SizeLow,Links,IndexHigh,IndexLow;}
  [DllImport("kernel32.dll",SetLastError=true)][return:MarshalAs(UnmanagedType.Bool)]static extern bool GetFileInformationByHandle(SafeFileHandle handle,out FileInformation info);
  internal static bool SameFile(string first,string second){
   string a=Path.GetFullPath(first),b=Path.GetFullPath(second);if(String.Equals(a,b,StringComparison.OrdinalIgnoreCase))return true;
   if(!File.Exists(a)||!File.Exists(b))return false;
   using(var left=new FileStream(a,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))using(var right=new FileStream(b,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)){
    FileInformation x,y;if(!GetFileInformationByHandle(left.SafeFileHandle,out x)||!GetFileInformationByHandle(right.SafeFileHandle,out y))throw new IOException("Cannot prove actual engineering file identity.",Marshal.GetExceptionForHR(Marshal.GetHRForLastWin32Error()));
    return x.VolumeSerial==y.VolumeSerial&&x.IndexHigh==y.IndexHigh&&x.IndexLow==y.IndexLow;
   }
  }
  internal static void Exit(){try{NativeEngineeringFileHashes.Exit();}finally{expected=null;NativeLazyFunctionProfile.EndRequest();}}
 }
}
