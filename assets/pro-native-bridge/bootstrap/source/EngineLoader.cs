using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace McgsInternalBridge {
    internal static class EngineLoader {
        sealed class LoadedEngine {internal string Sha;internal MethodInfo Dispatch,Prepare,Finalize;}
        internal sealed class PreparedCall {
            internal Dictionary<string,object> Request;
            internal string Path,Sha;
            internal int PrepareThreadId;
            internal object Engine;
        }
        static readonly Dictionary<string,LoadedEngine> Cache=new Dictionary<string,LoadedEngine>(StringComparer.OrdinalIgnoreCase);
        static string EngineRoot{get{return BootstrapLayout.EngineRoot;}}
        static MethodInfo Optional(Type type,string name,Type[] parameters) {
            MethodInfo method=type.GetMethod(name,BindingFlags.Public|BindingFlags.Static,null,parameters,null);
            if(method!=null&&method.ReturnType!=typeof(Dictionary<string,object>))throw new InvalidOperationException("EngineEntry."+name+" has an unexpected public signature.");
            if(method==null&&type.GetMember(name,BindingFlags.Public|BindingFlags.Static).Length!=0)throw new InvalidOperationException("EngineEntry."+name+" has an unexpected public signature.");
            return method;
        }
        static Dictionary<string,object> Invoke(MethodInfo method,object[] args) {
            Dictionary<string,object> result;
            try{result=(Dictionary<string,object>)method.Invoke(null,args);}catch(TargetInvocationException error){throw error.InnerException??error;}
            if(result==null)throw new InvalidOperationException("Engine returned no dictionary from "+method.Name+".");
            return result;
        }
        // Background only: select and pin the engine for this entire request.
        // Optional engine hooks must be managed/file-only, with no UI/native state.
        internal static PreparedCall Prepare(Dictionary<string,object> request) {
            BootstrapLayout.CheckHost();
            string manifest=BootstrapLayout.Regular(Path.Combine(BootstrapRuntime.RuntimeRoot,"active-engine.json"));
            if(new FileInfo(manifest).Length>8192)throw new InvalidOperationException("Engine manifest exceeds 8 KiB.");
            var data=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(manifest,Encoding.UTF8));
            if(data==null||!data.ContainsKey("assembly")||!data.ContainsKey("sha256"))throw new InvalidOperationException("Engine manifest requires assembly and sha256.");
            string path=BootstrapLayout.Regular(Convert.ToString(data["assembly"])),expected=Convert.ToString(data["sha256"]);
            object scope;if(!data.TryGetValue("bootstrap_scope_sha256",out scope)||Convert.ToString(scope)!=BootstrapLayout.ConfigurationSha256)throw new InvalidOperationException("Active engine belongs to another bootstrap configuration.");
            if(!String.Equals(Path.GetDirectoryName(path),EngineRoot,StringComparison.OrdinalIgnoreCase)||!Regex.IsMatch(Path.GetFileName(path),@"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.dll\z"))throw new InvalidOperationException("Engine path must be a single DLL basename inside the configured engine directory.");
            if(!Regex.IsMatch(expected??"",@"\A[0-9a-fA-F]{64}\z"))throw new InvalidOperationException("Expected an engine SHA256.");
            string actual;using(var algorithm=SHA256.Create())using(var stream=File.OpenRead(path))actual=BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
            if(!String.Equals(actual,expected,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Engine SHA256 differs from manifest.");
            LoadedEngine loaded;
            lock(Cache){
                if(Cache.TryGetValue(path,out loaded)){
                    if(!String.Equals(loaded.Sha,actual,StringComparison.Ordinal))throw new InvalidOperationException("A loaded engine version was modified; use a new filename.");
                }else{
                    Assembly assembly=Assembly.LoadFile(path);Type type=assembly.GetType("McgsInternalBridge.EngineEntry",true,false);
                    MethodInfo method=type.GetMethod("Dispatch",BindingFlags.Public|BindingFlags.Static,null,new[]{typeof(Dictionary<string,object>),typeof(object),typeof(int)},null);
                    if(method==null||method.ReturnType!=typeof(Dictionary<string,object>))throw new InvalidOperationException("EngineEntry.Dispatch has an unexpected public signature.");
                    loaded=new LoadedEngine{Sha=actual,Dispatch=method,Prepare=Optional(type,"PrepareRequest",new[]{typeof(Dictionary<string,object>)}),Finalize=Optional(type,"FinalizeResponse",new[]{typeof(Dictionary<string,object>),typeof(Dictionary<string,object>)})};Cache.Add(path,loaded);
                }
            }
            var prepared=loaded.Prepare==null?request:Invoke(loaded.Prepare,new object[]{request});
            return new PreparedCall{Request=prepared,Path=path,Sha=actual,Engine=loaded,PrepareThreadId=BootstrapRuntime.GetCurrentThreadId()};
        }
        internal static Dictionary<string,object> Dispatch(PreparedCall call,object datObj,int uiThread) {
            if(BootstrapRuntime.GetCurrentThreadId()!=uiThread||uiThread!=BootstrapRuntime.UiThreadId)throw new InvalidOperationException("Engine dispatch requires the captured native UI thread.");
            return Invoke(((LoadedEngine)call.Engine).Dispatch,new object[]{call.Request,datObj,uiThread});
        }
        internal static Dictionary<string,object> Finalize(PreparedCall call,Dictionary<string,object> response) {
            var loaded=(LoadedEngine)call.Engine;
            var result=loaded.Finalize==null?response:Invoke(loaded.Finalize,new object[]{call.Request,response});
            result["bridge_bootstrap_scope_sha256"]=BootstrapLayout.ConfigurationSha256;result["engine_assembly"]=Path.GetFileName(call.Path);result["engine_sha256"]=call.Sha;
            return result;
        }
        // Retained source compatibility for callers of the former synchronous API.
        internal static Dictionary<string,object> Dispatch(Dictionary<string,object> request,object datObj,int uiThread){var call=Prepare(request);return Finalize(call,Dispatch(call,datObj,uiThread));}
    }
}
