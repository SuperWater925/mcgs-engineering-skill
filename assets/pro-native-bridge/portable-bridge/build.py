"""Publisher-only build. Receiver preparation never calls this module or Csc."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,re,subprocess
HERE=Path(__file__).resolve().parent
TEMPLATES=HERE.parent/'bootstrap'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def build(output,csc=None):
 output=Path(output).resolve()
 if output.exists() and any(output.iterdir()):raise ValueError('Use an empty publisher output; do not replace loaded own artifacts')
 output.mkdir(parents=True,exist_ok=True);src=output/'source';src.mkdir()
 contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
 compiler=Path(csc or Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework/v4.0.30319/csc.exe')
 if not compiler.is_file():raise ValueError('Publisher C# compiler missing: '+str(compiler))
 for name in ('Bootstrap.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs'):
  text=(TEMPLATES/'source'/name).read_text(encoding='utf-8-sig')
  if name=='Bootstrap.cs':
   start=text.index('    [ComVisible(true)]',text.index('namespace McgsInternalBridge'))
   end=text.index('    internal static class BootstrapRuntime')
   text=text[:start]+text[end:]
   text=text.replace('4D2519E0-CC21-4F82-A19C-1AF9801C64E1',contract['assembly_guid'])
   # beforefieldinit may run when COM JITs Attach, before its first Initialize
   # call. Do not resolve connection paths in static field initializers.
   text=text.replace('internal static readonly string Inbox=Path.Combine(RuntimeRoot,"inbox");','internal static string Inbox{get{return Path.Combine(RuntimeRoot,"inbox");}}')
   text=text.replace('internal static readonly string Outbox=Path.Combine(RuntimeRoot,"outbox");','internal static string Outbox{get{return Path.Combine(RuntimeRoot,"outbox");}}')
  (src/name).write_text(text,encoding='utf-8')
 layout=(TEMPLATES/'source/BootstrapLayout.cs').read_text(encoding='utf-8-sig')
 layout=layout.replace('internal const string ExpectedConfigurationSha256="__BOUND_CONFIGURATION_SHA256__";',
 '''internal const string PortableBridgeContract="mcgs-portable-bridge/v6";
  internal static string ExpectedConfigurationSha256;internal static string ConfigurationFile;
  internal static void Initialize(string file,string expected){lock(Gate){
   file=Regular(file);Need(Regex.IsMatch(expected??"",@"\\A[0-9a-f]{64}\\z"),"Expected this preparation's configuration SHA.");
   if(ConfigurationFile!=null){Need(SamePath(file,ConfigurationFile)&&expected==ExpectedConfigurationSha256,"This process already owns another portable bridge context; reuse its discovery record.");return;}
   ConfigurationFile=file;ExpectedConfigurationSha256=expected;
   try{Load();}catch{ConfigurationFile=null;ExpectedConfigurationSha256=null;throw;}
  }}
  internal static void CheckAttachThread(){Load();using(var p=Process.GetCurrentProcess()){
   Need(Convert.ToInt32(data["target_process_id"])==p.Id&&Convert.ToInt64(data["target_creation_filetime"])==p.StartTime.ToFileTimeUtc(),"Portable target PID/creation changed.");
   Need(Convert.ToInt32(data["target_ui_thread_id"])==BootstrapRuntime.GetCurrentThreadId(),"Portable callback is outside the selected UI thread.");
  }}''')
 layout=layout.replace('Need(ExpectedConfigurationSha256.Length==64,"Prepare and bind the bootstrap configuration before compiling.");','Need(ExpectedConfigurationSha256!=null&&ExpectedConfigurationSha256.Length==64,"Initialize the portable bridge with the current configuration.");')
 layout=layout.replace('file=Regular(Path.Combine(own,"McgsInternalBridge.bridge.json"))','file=Regular(ConfigurationFile)')
 layout=layout.replace('"Bootstrap configuration SHA differs from this compiled binding."','"Bootstrap configuration SHA differs from this connection preparation."')
 # A generic release has no compiled target or task path. Initialization pins the
 # current file bytes; all other path, capability and host checks are retained.
 (src/'BootstrapLayout.cs').write_text(layout,encoding='utf-8')
 (src/'PortableEntry.cs').write_bytes((HERE/'source/PortableEntry.cs').read_bytes())
 dll=output/contract['bridge_file'];client=output/contract['client_file'];hook=output/contract['hook_file']
 common=[str(compiler),'/nologo','/platform:x86','/codepage:65001','/optimize+','/reference:System.Web.Extensions.dll']
 subprocess.run(common+['/target:library','/reference:System.Windows.Forms.dll','/out:'+str(dll)]+[str(p)for p in sorted(src.glob('*.cs'))],check=True)
 subprocess.run(common+['/target:exe','/out:'+str(client),str(HERE/'source/PortableClient.cs')],check=True)
 spec=importlib.util.spec_from_file_location('portable_hook_builder',HERE/'build_hook.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 hook_info=mod.build(hook,TEMPLATES/'build_native_wrapper.py')
 manifest={'schema':1,'contract':contract['release'],'state':'publisher_compiled_not_attached','identity':contract,'artifacts':[{'file':p.name,'sha256':sha(p),'bytes':p.stat().st_size}for p in (dll,client,hook)],'native_hook':hook_info,'receiver_compilation_required':False,'vendor_files_included':False,'sources':[{'file':str(p.relative_to(output)),'sha256':sha(p)}for p in sorted(src.glob('*.cs'))]}
 write(output/'portable-bridge-manifest.json',manifest);return manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--csc');z=p.parse_args();print(json.dumps(build(z.output,z.csc),ensure_ascii=False,indent=2))
