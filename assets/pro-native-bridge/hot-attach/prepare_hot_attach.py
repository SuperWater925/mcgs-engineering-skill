"""Explicit own bridge/hook configuration and compilation. No registration/attach/start.
The --host-kind own-test-message-loop branch builds an own transport-only host.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,uuid,importlib.util,os,re
HERE=Path(__file__).resolve().parent
DEFAULT_BOOT=HERE.parent/'bootstrap'
sys.path.insert(0,str(DEFAULT_BOOT))
from pe_image import pe32_identity
CSC=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework/v4.0.30319/csc.exe'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 with Path(p).open('xb')as f:f.write((json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
def run(a):subprocess.run([str(x) for x in a],check=True)
def absolute(s):
 if not Path(s).is_absolute():raise ValueError('Use an explicit absolute path')
 p=Path(s).resolve();assert p.drive and str(p)!=p.anchor
 return p

def empty_output(path,label):
 if path.exists() and (not path.is_dir() or any(path.iterdir())):
  raise ValueError(label+' is not empty; preserve existing files/claims and reuse the existing bridge or select a fresh preparation subdirectory')
def hot_capability(editor,host_kind):
 return {'schema':1,**pe32_identity(editor),'entry_mode':'thread_specific_hot_attach',
         'hot_attach_mechanism_supported':True,'mechanism_preflight_only':True,
         'mechanism':{'hook':'WH_GETMESSAGE','activation':'COM','callback_thread':'target_UI_STA'},
         'static_loader_contract_supported':False,'native_cold_scan_used':False,
         'own_message_loop_host':host_kind.startswith('own-test'),'host_kind':host_kind,
         'manufacturer_loader_or_business_abi_claimed':False,'actual_attach_verified':False,
         'scope':'Current explicit PE32/I386 image identity and standard WH_GETMESSAGE/COM UI-STA mechanism only. No manufacturer cold-loader or native business ABI compatibility is claimed.'}

def template_sources(templates):
 required=['Bootstrap.cs','BootstrapLayout.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs']
 sources={}
 for name in required:
  file=templates/'source'/name
  if not file.is_file():raise ValueError('Bootstrap template input is missing: '+str(file))
  sources[name]=file.read_text(encoding='utf-8-sig')
 layout=sources['BootstrapLayout.cs']
 if layout.count('__BOUND_CONFIGURATION_SHA256__')!=1 or any(token not in layout for token in ['thread_specific_hot_attach','hot_attach_mechanism_supported','native_cold_scan_used']):
  raise ValueError('Bootstrap template contract mismatch: BootstrapLayout must support this hot-attach mechanism capability. Do not mix old cold-only layout sources with the current hot preparer; this is an own-tool source mismatch, not a Pro version restriction.')
 runtime=sources['Bootstrap.cs']
 for pattern in [r'\bnamespace\s+McgsInternalBridge\s*\{',r'(?m)^[ \t]*(?:internal|public)\s+static\s+class\s+BootstrapRuntime\s*\{',r'\bstatic\s+void\s+EnsureUiPump\s*\(\s*string\s+\w+\s*,\s*int\s+\w+\s*,\s*object\s+\w+\s*\)',r'\bstatic\s+void\s+RecordEvent\s*\(',r'\bstatic\s+void\s+RecordError\s*\(',r'\bstatic\s+extern\s+int\s+GetCurrentThreadId\s*\(']:
  if not re.search(pattern,runtime):raise ValueError('Bootstrap template contract mismatch: required UI-STA runtime interface is absent; use one compatible own-source template set.')
 assembler=templates/'build_native_wrapper.py'
 if not assembler.is_file() or 'class Assembler' not in assembler.read_text(encoding='utf-8-sig'):
  raise ValueError('Bootstrap template contract mismatch: own PE Assembler interface is absent.')
 return sources

def main():
 global CSC
 ap=argparse.ArgumentParser();ap.add_argument('--task-root',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--bootstrap-root',required=True);ap.add_argument('--install-root',required=True);ap.add_argument('--editor');ap.add_argument('--host-kind',choices=['pro','own-test-message-loop','own-test-native-message-loop'],default='pro');ap.add_argument('--bootstrap-template',default=str(DEFAULT_BOOT));ap.add_argument('--ping-only',action='store_true');ap.add_argument('--csc',type=Path,default=CSC,help='Explicit x86 .NET Framework-compatible C# compiler');z=ap.parse_args()
 CSC=z.csc.resolve()
 task,runtime,boot,install=[absolute(v) for v in [z.task_root,z.runtime_root,z.bootstrap_root,z.install_root]]
 assert runtime.is_relative_to(task) and boot.is_relative_to(task) and runtime!=task and boot!=task
 assert not runtime.is_relative_to(boot) and not boot.is_relative_to(runtime)
 templates=absolute(z.bootstrap_template);editor=absolute(z.editor) if z.editor else install/'Program/OwnMessageLoopHost.exe'
 if not CSC.is_file():raise ValueError('The x86 .NET Framework C# compiler is unavailable: '+str(CSC))
 prepared_sources=template_sources(templates)
 if z.host_kind.startswith('own-test'):
  if z.editor:raise ValueError('Own test executable is built here, not an external image')
  cap=None
 else:
  if not z.editor or not editor.is_file():raise ValueError('Use --editor with the explicit actual Pro executable')
  if not install.is_dir() or not editor.is_relative_to(install):raise ValueError('The explicit executable must be inside the existing installation root')
  cap=hot_capability(editor,z.host_kind)
 empty_output(boot,'BootstrapRoot')
 if runtime.exists() and not runtime.is_dir():raise ValueError('RuntimeRoot must be a directory, not an existing file')
 boot.mkdir(parents=True,exist_ok=True);runtime.mkdir(parents=True,exist_ok=True)
 empty_output(boot,'BootstrapRoot')
 (runtime/'hot-attach').mkdir(exist_ok=True);src=boot/'bound-source';src.mkdir()
 if z.host_kind.startswith('own-test'):
  editor.parent.mkdir(parents=True,exist_ok=True)
  if z.host_kind=='own-test-native-message-loop':
   mod=importlib.util.spec_from_file_location('own_native_loop',HERE/'build_native_loop.py');gen=importlib.util.module_from_spec(mod);mod.loader.exec_module(gen);gen.build(runtime,editor,templates/'build_native_wrapper.py')
  else:run([CSC,'/nologo','/target:winexe','/platform:x86','/codepage:65001','/reference:System.Web.Extensions.dll','/reference:System.Windows.Forms.dll','/out:'+str(editor),HERE/'source/OwnMessageLoopHost.cs'])
  cap=hot_capability(editor,z.host_kind)
 class_guid=str(uuid.uuid4()).upper();interface_guid=str(uuid.uuid4()).upper();assembly_guid=str(uuid.uuid4()).upper();assembly_name='McgsHotBridge_'+uuid.UUID(class_guid).hex[:12]
 write(boot/'loader-capability.json',cap)
 config={'schema':1,'task_root':str(task),'runtime_root':str(runtime),'install_root':str(install),'bootstrap_root':str(boot),'editor_executable':str(editor),'editor_sha256':cap['binary_sha256'],'loader_contract_file':str(boot/'loader-capability.json'),'loader_contract_sha256':sha(boot/'loader-capability.json'),'addins_directory':str(editor.parent/'Addins'),'addins_ini_file':str(editor.parent/'Addins/Addins.ini'),'startup_registry_path':r'Software\McgsHotAttachOwn\Startup','entry_mode':'thread_specific_hot_attach','host_kind':z.host_kind,'hot_assembly_name':assembly_name,'ping_only':bool(z.ping_only or z.host_kind.startswith('own-test'))}
 write(boot/'McgsInternalBridge.bridge.json',config);scope_sha=sha(boot/'McgsInternalBridge.bridge.json')
 for n in ['Bootstrap.cs','BootstrapLayout.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs']:
  s=prepared_sources[n]
  if n=='BootstrapLayout.cs':s=s.replace('__BOUND_CONFIGURATION_SHA256__',scope_sha)
  if n=='Bootstrap.cs':
   body=re.search(r'(?m)^[ \t]*(?:internal|public)\s+static\s+class\s+BootstrapRuntime\s*\{',s).start();shell=s.find('    [ComVisible(true)]',re.search(r'\bnamespace\s+McgsInternalBridge\s*\{',s).start())
   if shell>=0 and shell<body:s=s[:shell]+s[body:]
   s=s.replace('4D2519E0-CC21-4F82-A19C-1AF9801C64E1',assembly_guid)
   old='''            if(!String.Equals(Path.GetFileName(Process.GetCurrentProcess().MainModule.FileName),"McgsSetPro.exe",StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Bridge callback is outside McgsSetPro.exe.");'''
   # CheckHost above already enforces exact bound full path/SHA/x86. It permits
   # the expressly bound own message-loop host without pretending it is Pro.
   if s.count(old)>1:raise ValueError("Bootstrap template repeats its old basename-only callback guard")
   s=s.replace(old,'            // Exact host path/SHA is enforced by BootstrapLayout.CheckHost above; no basename-only substitute.')
  (src/n).write_text(s,encoding='utf-8')
 entry=(HERE/'source/HotAttachComEntry.cs').read_text(encoding='utf-8').replace('__HOT_CLASS_GUID__',class_guid).replace('__HOT_INTERFACE_GUID__',interface_guid)
 (src/'HotAttachComEntry.cs').write_text(entry,encoding='utf-8')
 dll=boot/(assembly_name+'.dll')
 run([CSC,'/nologo','/target:library','/platform:x86','/codepage:65001','/optimize+','/reference:System.Web.Extensions.dll','/reference:System.Windows.Forms.dll','/out:'+str(dll),*[src/n for n in ['Bootstrap.cs','BootstrapLayout.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs','HotAttachComEntry.cs']]])
 client=boot/'McgsHotAttach.exe';run([CSC,'/nologo','/target:exe','/platform:x86','/codepage:65001','/reference:System.Web.Extensions.dll','/out:'+str(client),HERE/'source/HotAttachClient.cs'])
 plan={'schema':1,'host_kind':z.host_kind,'class_guid':class_guid,'interface_guid':interface_guid,'runtime_root':str(runtime),'bootstrap_dll':str(dll),'bootstrap_dll_sha256':sha(dll),'bootstrap_assembly_full_name':assembly_name+', Version=1.0.0.0, Culture=neutral, PublicKeyToken=null','bootstrap_config':str(boot/'McgsInternalBridge.bridge.json'),'bootstrap_scope_sha256':scope_sha,'editor_executable':str(editor),'editor_sha256':cap['binary_sha256'],'event_prefix':r'Local\McgsHotAttach_'+scope_sha+'_','hook_dll':str(boot/'McgsHotAttachHook.dll')}
 write(boot/'hook-build-config.json',plan)
 m=importlib.util.spec_from_file_location('hook_build',HERE/'build_hook_pe.py');b=importlib.util.module_from_spec(m);m.loader.exec_module(b);native=b.build(boot/'hook-build-config.json',plan['hook_dll'],templates/'build_native_wrapper.py');plan['hook_dll_sha256']=sha(plan['hook_dll']);write(boot/'hot-attach.json',plan)
 engines=boot/'engines';engines.mkdir()
 if z.host_kind.startswith('own-test') or z.ping_only:
  e=engines/('McgsInternalEngine_'+str(900000000000000000+uuid.uuid4().int%99999999999999999)+'.dll');run([CSC,'/nologo','/target:library','/platform:x86','/codepage:65001','/out:'+str(e),HERE/'source/OwnPingEngine.cs']);write(runtime/'active-engine.json',{'assembly':str(e),'sha256':sha(e),'bootstrap_scope_sha256':scope_sha})
 manifest={'schema':1,'state':'compiled_own_source_only_not_registered_or_attached','host_kind':z.host_kind,'bootstrap_scope_sha256':scope_sha,'bootstrap_assembly_name':assembly_name,'cold_addin_shell_removed':True,'config_file':str(boot/'hot-attach.json'),'config_sha256':sha(boot/'hot-attach.json'),'client':str(client),'client_sha256':sha(client),'native_hook':native,'sources':[{'file':str(f.relative_to(boot)),'sha256':sha(f)}for f in src.glob('*.cs')],'no_vendor_files_copied':True,'process_started':False,'registry_written':False,'host_attached':False}
 write(boot/'build-manifest.json',manifest);print(json.dumps({'manifest':str(boot/'build-manifest.json'),'manifest_sha256':sha(boot/'build-manifest.json'),'config':str(boot/'hot-attach.json'),'client':str(client),'registry_written':False,'attached':False},ensure_ascii=False))
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
if __name__=='__main__':main()
