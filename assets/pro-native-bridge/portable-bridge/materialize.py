"""Copy publisher-built portable bridge bytes and write this target's JSON only.

No compiler, process start, COM activation, registry write or hook occurs here.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'bootstrap'))
from pe_image import pe32_identity
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,data):
 with Path(path).open('x',encoding='utf-8')as out:json.dump(data,out,ensure_ascii=False,indent=2);out.write('\n')
def absolute(value):
 path=Path(value)
 if not path.is_absolute():raise ValueError('Use an explicit absolute path: '+str(value))
 path=path.resolve()
 if str(path)==path.anchor:raise ValueError('A filesystem root is not a bridge task directory')
 return path
def materialize(*,artifacts,task_root,runtime_root,bootstrap_root,install_root,editor,pid,ui_thread,creation_filetime,host_kind='pro'):
 artifacts,task,runtime,boot,install,editor=map(absolute,(artifacts,task_root,runtime_root,bootstrap_root,install_root,editor))
 if not runtime.is_relative_to(task)or not boot.is_relative_to(task)or runtime==task or boot==task or runtime.is_relative_to(boot)or boot.is_relative_to(runtime):raise ValueError('Queue/bootstrap roots must be separate descendants of the connection root')
 if not editor.is_file()or not editor.is_relative_to(install):raise ValueError('The explicit current editor must be inside its actual installation root')
 if min(int(pid),int(ui_thread),int(creation_filetime))<=0:raise ValueError('Current PID/UI thread/creation FILETIME are required')
 manifest=load(artifacts/'portable-bridge-manifest.json');identity=load(HERE/'contract.json')
 if manifest.get('schema')!=1 or manifest.get('contract')!=identity['release']or manifest.get('identity')!=identity:raise ValueError('Publisher artifact manifest/portable contract differs')
 files={item['file']:item for item in manifest['artifacts']}
 for key in ('bridge_file','hook_file','client_file'):
  name=identity[key];file=artifacts/name
  if name not in files or not file.is_file()or file.stat().st_size!=files[name]['bytes']or sha(file)!=files[name]['sha256']:raise ValueError('Publisher artifact integrity differs: '+name)
 if boot.exists()and(not boot.is_dir()or any(boot.iterdir())):raise ValueError('Bridge output already has state; reuse/discover the existing connection instead of overwriting it')
 boot.mkdir(parents=True,exist_ok=True);runtime.mkdir(parents=True,exist_ok=True);(runtime/'hot-attach').mkdir(exist_ok=True);(boot/'engines').mkdir()
 for key in ('bridge_file','hook_file','client_file'):shutil.copyfile(artifacts/identity[key],boot/identity[key])
 shutil.copyfile(artifacts/'portable-bridge-manifest.json',boot/'portable-bridge-manifest.json')
 cap={'schema':1,**pe32_identity(editor),'entry_mode':'thread_specific_hot_attach','hot_attach_mechanism_supported':True,'mechanism_preflight_only':True,'mechanism':{'hook':'WH_GETMESSAGE','activation':'COM','callback_thread':'target_UI_STA'},'static_loader_contract_supported':False,'native_cold_scan_used':False,'own_message_loop_host':host_kind.startswith('own-test'),'host_kind':host_kind,'manufacturer_loader_or_business_abi_claimed':False,'actual_attach_verified':False}
 if cap.get('machine')!='I386'or cap.get('pe_format')!='PE32':raise ValueError('This portable hook release supports x86 PE32 hosts')
 write(boot/'loader-capability.json',cap)
 bridge={'schema':1,'portable_bridge_contract':identity['release'],'task_root':str(task),'runtime_root':str(runtime),'install_root':str(install),'bootstrap_root':str(boot),'editor_executable':str(editor),'editor_sha256':cap['binary_sha256'],'loader_contract_file':str(boot/'loader-capability.json'),'loader_contract_sha256':sha(boot/'loader-capability.json'),'addins_directory':str(editor.parent/'Addins'),'addins_ini_file':str(editor.parent/'Addins/Addins.ini'),'startup_registry_path':r'Software\McgsPortableBridge\UnusedHotStartup','entry_mode':'thread_specific_hot_attach','host_kind':host_kind,'hot_assembly_name':identity['assembly_name'],'ping_only':host_kind.startswith('own-test'),'target_process_id':int(pid),'target_ui_thread_id':int(ui_thread),'target_creation_filetime':int(creation_filetime)}
 config=boot/'McgsInternalBridge.bridge.json';write(config,bridge)
 client={'schema':1,'portable_bridge_contract':identity['release'],'class_guid':identity['class_guid'],'interface_guid':identity['interface_guid'],'host_kind':host_kind,'runtime_root':str(runtime),'bootstrap_dll':str(boot/identity['bridge_file']),'bootstrap_dll_sha256':sha(boot/identity['bridge_file']),'bootstrap_assembly_full_name':identity['assembly_name']+', Version=1.0.0.0, Culture=neutral, PublicKeyToken=null','bootstrap_config':str(config),'bootstrap_scope_sha256':sha(config),'editor_executable':str(editor),'editor_sha256':cap['binary_sha256'],'hook_dll':str(boot/identity['hook_file']),'hook_dll_sha256':sha(boot/identity['hook_file']),'client':str(boot/identity['client_file']),'client_sha256':sha(boot/identity['client_file']),'target_process_id':int(pid),'target_ui_thread_id':int(ui_thread),'target_creation_filetime':int(creation_filetime)}
 write(boot/'hot-attach.json',client)
 # Legacy stage/select consumers verify this current, data-only preparation
 # manifest separately from the immutable publisher artifact manifest.
 write(boot/'build-manifest.json',{'schema':1,'state':'materialized_precompiled_own_source_not_registered_or_attached','portable_bridge_contract':identity['release'],'bootstrap_scope_sha256':client['bootstrap_scope_sha256'],'bootstrap_assembly_name':identity['assembly_name'],'cold_addin_shell_removed':True,'config_file':str(boot/'hot-attach.json'),'config_sha256':sha(boot/'hot-attach.json'),'client':client['client'],'client_sha256':client['client_sha256'],'publisher_manifest_sha256':sha(artifacts/'portable-bridge-manifest.json'),'receiver_compilation_required':False,'no_vendor_files_copied':True,'process_started':False,'registry_written':False,'host_attached':False})
 result={'schema':1,'state':'materialized_not_registered_or_attached','portable_bridge_contract':identity['release'],'config':str(boot/'hot-attach.json'),'config_sha256':sha(boot/'hot-attach.json'),'client':client['client'],'client_sha256':client['client_sha256'],'bootstrap_root':str(boot),'runtime_root':str(runtime),'bootstrap_config':str(config),'bootstrap_scope_sha256':client['bootstrap_scope_sha256'],'publisher_manifest_sha256':sha(artifacts/'portable-bridge-manifest.json'),'receiver_compilation_required':False,'own_artifacts_byte_identical':all(sha(boot/identity[k])==files[identity[k]]['sha256']for k in ('bridge_file','hook_file','client_file')),'process_started':False,'registry_written':False,'host_attached':False}
 write(boot/'materialization.json',result);return result
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('artifacts','task-root','runtime-root','bootstrap-root','install-root','editor'):p.add_argument('--'+name,required=True)
 p.add_argument('--pid',required=True,type=int);p.add_argument('--ui-thread',required=True,type=int);p.add_argument('--creation-filetime',required=True,type=int);p.add_argument('--host-kind',choices=['pro','own-test-message-loop','own-test-native-message-loop'],default='pro')
 print(json.dumps(materialize(**vars(p.parse_args())),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
