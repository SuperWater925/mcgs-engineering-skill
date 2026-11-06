"""Unified non-vendor verification entry; never opens Pro or an MCP/MCS project.

Publisher fixture setup builds an own native cold-CLR STA message loop and an own
ping-only engine. The actual receiver materialization path does not compile.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,struct,subprocess,time,uuid
HERE=Path(__file__).resolve().parent
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def wait_file(path,seconds=15):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if Path(path).is_file():return Path(path).read_bytes()
  time.sleep(.05)
 raise TimeoutError('Fixture output missing: '+str(path))
def invoke(client,operation,config):
 result=subprocess.run([str(client),operation,str(config)],capture_output=True,text=True,encoding='utf-8',timeout=40)
 try:value=json.loads(result.stdout)
 except Exception:raise RuntimeError('Own client did not emit JSON: '+result.stdout+' '+result.stderr)
 return {'exit_code':result.returncode,'result':value}
def run(artifacts,output,csc=None):
 artifacts=Path(artifacts).resolve();output=Path(output).resolve()
 if output.exists()and any(output.iterdir()):raise ValueError('Use a fresh external fixture root')
 output.mkdir(parents=True,exist_ok=True)
 runtime=output/'connection/queue';runtime.mkdir(parents=True);install=output/'own install 中文';(install/'Program').mkdir(parents=True)
 host=install/'Program/OwnMessageLoopHost.exe';native=module('portable_fixture_native_loop',HERE.parent/'hot-attach/build_native_loop.py')
 native_info=native.build(runtime,host,HERE.parent/'bootstrap/build_native_wrapper.py')
 compiler=Path(csc or Path(os.environ.get('WINDIR',r'C:\Windows'))/'Microsoft.NET/Framework/v4.0.30319/csc.exe')
 ping=output/'OwnPingEngine.dll'
 subprocess.run([str(compiler),'/nologo','/target:library','/platform:x86','/codepage:65001','/out:'+str(ping),str(HERE.parent/'hot-attach/source/OwnPingEngine.cs')],check=True)
 materialize=module('portable_fixture_materialize',HERE/'materialize.py')
 result={'schema':1,'test_kind':'own-native-cold-CLR-STA-only','real_pro_started':False,'manufacturer_business_abi_tested':False,'vendor_project_opened':False,'native_host':native_info,'checks':{}}
 process=subprocess.Popen([str(host)],cwd=str(host.parent),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 config=None;client=None
 try:
  ready=wait_file(runtime/'own-native-host.ready.bin');assert len(ready)==40 and ready[:4]==b'NLP1'
  pid,tid=struct.unpack_from('<II',ready,8);creation=struct.unpack_from('<Q',ready,16)[0];assert process.pid==pid
  prepared=materialize.materialize(artifacts=artifacts,task_root=output/'connection',runtime_root=runtime,bootstrap_root=output/'connection/bootstrap',install_root=install,editor=host,pid=pid,ui_thread=tid,creation_filetime=creation,host_kind='own-test-native-message-loop')
  result['materialization']=prepared;config=Path(prepared['config']);client=Path(prepared['client']);boot=config.parent
  engine=boot/'engines/OwnPingEngine.dll';shutil.copyfile(ping,engine)
  write(runtime/'active-engine.json',{'assembly':str(engine),'sha256':sha(engine),'bootstrap_scope_sha256':prepared['bootstrap_scope_sha256']})
  result['checks']['plan']=invoke(client,'--plan',config);assert result['checks']['plan']['exit_code']==0
  result['checks']['connect']=invoke(client,'--connect',config);assert result['checks']['connect']['result']['host_attached']is True
  result['checks']['reuse']=invoke(client,'--connect',config);assert result['checks']['reuse']['result']['connection_reused']is True
  request_id='fixture_'+uuid.uuid4().hex
  inbox=runtime/'inbox';inbox.mkdir(exist_ok=True);write(inbox/(request_id+'.json'),{'op':'ping','request_id':request_id})
  response=json.loads(wait_file(runtime/'outbox'/(request_id+'.json')).decode('utf-8-sig'));result['checks']['ping']=response
  assert response['ok']is True and response['process_id']==pid and response['ui_thread_id']==tid
  assert response['queue_dispatch_thread_id']==tid and response['queue_prepare_thread_id']!=tid and response['queue_finalize_thread_id']!=tid
  result['checks']['status']=invoke(client,'--status',config);assert result['checks']['status']['result']['host_attached']is True
  result['checks']['same_publisher_bytes']=all(sha(boot/p['file'])==p['sha256']for p in json.loads((artifacts/'portable-bridge-manifest.json').read_text(encoding='utf-8'))['artifacts'])
  assert result['checks']['same_publisher_bytes']
  result['ok']=True
 finally:
  if config is not None and process.poll()is None:result['unregister']=invoke(client,'--unregister',config)
  (runtime/'bridge.stop').write_text('own fixture complete',encoding='utf-8');(runtime/'own-native-host.stop').write_text('own fixture complete',encoding='utf-8')
  try:result['host_exit_code']=process.wait(timeout=10)
  except subprocess.TimeoutExpired:result['host_exit_code']=None;result['host_normal_stop_pending']=True
  write(output/'fixture-result.json',result)
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--artifacts',required=True);p.add_argument('--output',required=True);p.add_argument('--csc');a=p.parse_args();print(json.dumps(run(a.artifacts,a.output,a.csc),ensure_ascii=False,indent=2))
