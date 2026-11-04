"""Explicit own bridge/hook configuration and compilation. No registration/attach/start.
The --host-kind own-test-message-loop branch builds an own transport-only host.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,uuid,importlib.util,os
HERE=Path(__file__).resolve().parent
DEFAULT_BOOT=HERE.parent/'bootstrap'
CSC=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework/v4.0.30319/csc.exe'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 with Path(p).open('xb')as f:f.write((json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
def run(a):subprocess.run([str(x) for x in a],check=True)
def absolute(s):
 p=Path(s).resolve();assert p.drive and str(p)!=p.anchor
 for x in [p,*p.parents]:
  if x.exists():assert not (x.stat(follow_symlinks=False).st_file_attributes&0x400),'Reparse path'
 return p
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--task-root',required=True);ap.add_argument('--runtime-root',required=True);ap.add_argument('--bootstrap-root',required=True);ap.add_argument('--install-root',required=True);ap.add_argument('--editor');ap.add_argument('--host-kind',choices=['pro','own-test-message-loop','own-test-native-message-loop'],default='pro');ap.add_argument('--bootstrap-template',default=str(DEFAULT_BOOT));ap.add_argument('--ping-only',action='store_true');z=ap.parse_args()
 task,runtime,boot,install=[absolute(v) for v in [z.task_root,z.runtime_root,z.bootstrap_root,z.install_root]]
 assert len(str(runtime).encode('utf-16le'))//2<=220,'Native result path exceeds bounded path length'
 assert runtime.is_relative_to(task) and boot.is_relative_to(task) and runtime!=task and boot!=task
 assert not runtime.is_relative_to(boot) and not boot.is_relative_to(runtime)
 boot.mkdir(parents=True,exist_ok=False);runtime.mkdir(parents=True,exist_ok=True);(runtime/'hot-attach').mkdir(exist_ok=True);src=boot/'bound-source';src.mkdir()
 templates=absolute(z.bootstrap_template);editor=absolute(z.editor) if z.editor else install/'Program/OwnMessageLoopHost.exe'
 if z.host_kind.startswith('own-test'):
  assert not z.editor,'Own test executable is built here, not an external image'
  editor.parent.mkdir(parents=True,exist_ok=True)
  if z.host_kind=='own-test-native-message-loop':
   mod=importlib.util.spec_from_file_location('own_native_loop',HERE/'build_native_loop.py');gen=importlib.util.module_from_spec(mod);mod.loader.exec_module(gen);gen.build(runtime,editor,templates/'build_native_wrapper.py')
  else:run([CSC,'/nologo','/target:winexe','/platform:x86','/codepage:65001','/reference:System.Web.Extensions.dll','/reference:System.Windows.Forms.dll','/out:'+str(editor),HERE/'source/OwnMessageLoopHost.cs'])
 else:assert editor.is_file(),'Use the explicit actual Pro executable'
 class_guid=str(uuid.uuid4()).upper();interface_guid=str(uuid.uuid4()).upper();assembly_guid=str(uuid.uuid4()).upper();assembly_name='McgsHotBridge_'+uuid.UUID(class_guid).hex[:12]
 if z.host_kind=='pro':
  cap=load(templates/'loader-capability.current.json');assert cap['binary_sha256']==sha(editor),'Actual original loader/ABI contract is missing for this installed image'
 else:cap={'schema':1,'binary_sha256':sha(editor),'static_loader_contract_supported':True,'own_message_loop_host':True,'manufacturer_loader_or_business_abi_claimed':False,'native_cold_scan_used':False,'scope':'Only own x86 STA loop, standard COM activation and transport; no Pro functionality is claimed.'}
 write(boot/'loader-capability.json',cap)
 config={'schema':1,'task_root':str(task),'runtime_root':str(runtime),'install_root':str(install),'bootstrap_root':str(boot),'editor_executable':str(editor),'editor_sha256':sha(editor),'loader_contract_file':str(boot/'loader-capability.json'),'loader_contract_sha256':sha(boot/'loader-capability.json'),'addins_directory':str(install/'Program/Addins'),'addins_ini_file':str(install/'Program/Addins/Addins.ini'),'startup_registry_path':r'Software\McgsHotAttachOwn\Startup','entry_mode':'thread_specific_hot_attach','host_kind':z.host_kind,'hot_assembly_name':assembly_name,'ping_only':bool(z.ping_only or z.host_kind.startswith('own-test'))}
 write(boot/'McgsInternalBridge.bridge.json',config);scope_sha=sha(boot/'McgsInternalBridge.bridge.json')
 for n in ['Bootstrap.cs','BootstrapLayout.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs']:
  s=(templates/'source'/n).read_text(encoding='utf-8-sig')
  if n=='BootstrapLayout.cs':s=s.replace('__BOUND_CONFIGURATION_SHA256__',scope_sha)
  if n=='Bootstrap.cs':
   shell=s.index('    [ComVisible(true)]',s.index('namespace McgsInternalBridge {'));body=s.index('    internal static class BootstrapRuntime {',shell);s=s[:shell]+s[body:];s=s.replace('4D2519E0-CC21-4F82-A19C-1AF9801C64E1',assembly_guid)
   old='''            if(!String.Equals(Path.GetFileName(Process.GetCurrentProcess().MainModule.FileName),"McgsSetPro.exe",StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Bridge callback is outside McgsSetPro.exe.");'''
   # CheckHost above already enforces exact bound full path/SHA/x86. It permits
   # the expressly bound own message-loop host without pretending it is Pro.
   assert s.count(old)==1
   s=s.replace(old,'            // Exact host path/SHA is enforced by BootstrapLayout.CheckHost above; no basename-only substitute.')
  (src/n).write_text(s,encoding='utf-8')
 entry=(HERE/'source/HotAttachComEntry.cs').read_text(encoding='utf-8').replace('__HOT_CLASS_GUID__',class_guid).replace('__HOT_INTERFACE_GUID__',interface_guid)
 (src/'HotAttachComEntry.cs').write_text(entry,encoding='utf-8')
 dll=boot/(assembly_name+'.dll')
 run([CSC,'/nologo','/target:library','/platform:x86','/codepage:65001','/optimize+','/reference:System.Web.Extensions.dll','/reference:System.Windows.Forms.dll','/out:'+str(dll),*[src/n for n in ['Bootstrap.cs','BootstrapLayout.cs','EngineLoader.cs','DurableQueuePump.cs','NullSafeDispatch.cs','HotAttachComEntry.cs']]])
 client=boot/'McgsHotAttach.exe';run([CSC,'/nologo','/target:exe','/platform:x86','/codepage:65001','/reference:System.Web.Extensions.dll','/out:'+str(client),HERE/'source/HotAttachClient.cs'])
 plan={'schema':1,'host_kind':z.host_kind,'class_guid':class_guid,'interface_guid':interface_guid,'runtime_root':str(runtime),'bootstrap_dll':str(dll),'bootstrap_dll_sha256':sha(dll),'bootstrap_assembly_full_name':assembly_name+', Version=1.0.0.0, Culture=neutral, PublicKeyToken=null','bootstrap_config':str(boot/'McgsInternalBridge.bridge.json'),'bootstrap_scope_sha256':scope_sha,'editor_executable':str(editor),'editor_sha256':sha(editor),'event_prefix':r'Local\McgsHotAttach_'+scope_sha+'_','hook_dll':str(boot/'McgsHotAttachHook.dll')}
 write(boot/'hook-build-config.json',plan)
 m=importlib.util.spec_from_file_location('hook_build',HERE/'build_hook_pe.py');b=importlib.util.module_from_spec(m);m.loader.exec_module(b);native=b.build(boot/'hook-build-config.json',plan['hook_dll'],templates/'build_native_wrapper.py');plan['hook_dll_sha256']=sha(plan['hook_dll']);write(boot/'hot-attach.json',plan)
 engines=boot/'engines';engines.mkdir()
 if z.host_kind.startswith('own-test') or z.ping_only:
  e=engines/('McgsInternalEngine_'+str(900000000000000000+uuid.uuid4().int%99999999999999999)+'.dll');run([CSC,'/nologo','/target:library','/platform:x86','/codepage:65001','/out:'+str(e),HERE/'source/OwnPingEngine.cs']);write(runtime/'active-engine.json',{'assembly':str(e),'sha256':sha(e),'bootstrap_scope_sha256':scope_sha})
 manifest={'schema':1,'state':'compiled_own_source_only_not_registered_or_attached','host_kind':z.host_kind,'bootstrap_scope_sha256':scope_sha,'bootstrap_assembly_name':assembly_name,'cold_addin_shell_removed':True,'config_file':str(boot/'hot-attach.json'),'config_sha256':sha(boot/'hot-attach.json'),'client':str(client),'client_sha256':sha(client),'native_hook':native,'sources':[{'file':str(f.relative_to(boot)),'sha256':sha(f)}for f in src.glob('*.cs')],'no_vendor_files_copied':True,'process_started':False,'registry_written':False,'host_attached':False}
 write(boot/'build-manifest.json',manifest);print(json.dumps({'manifest':str(boot/'build-manifest.json'),'manifest_sha256':sha(boot/'build-manifest.json'),'config':str(boot/'hot-attach.json'),'client':str(client),'registry_written':False,'attached':False},ensure_ascii=False))
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
if __name__=='__main__':main()
