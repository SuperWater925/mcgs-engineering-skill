"""Copy one already built, scope-bound OWN engine into the prepared bridge.

No Pro or transport call. Existing engine names and active manifests are never overwritten.
"""
import argparse, hashlib, json, os, re
from pathlib import Path


def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def regular(p):
    if not p.is_file(): raise ValueError('Missing regular file: ' + str(p))
    for x in [p, *p.parents]:
        if x.exists() and x.stat(follow_symlinks=False).st_file_attributes & 0x400:
            raise ValueError('Reparse path: ' + str(x))


def write_new(p, b):
    with p.open('xb') as f:
        f.write(b); f.flush(); os.fsync(f.fileno())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bootstrap-root',required=True)
    p.add_argument('--engine-file',required=True)
    p.add_argument('--engine-scope-file',required=True)
    a=p.parse_args();boot=Path(os.path.abspath(a.bootstrap_root))
    config=boot/'McgsInternalBridge.bridge.json';regular(config)
    cfg=json.loads(config.read_text(encoding='utf-8-sig'))
    built=json.loads((boot/'build-manifest.json').read_text(encoding='utf-8-sig'))
    if built['bootstrap_scope_sha256']!=digest(config):raise ValueError('Prepared build/config binding differs')
    if Path(cfg['bootstrap_root']).resolve()!=boot: raise ValueError('Bootstrap root differs')
    engine=Path(os.path.abspath(a.engine_file));scope=Path(os.path.abspath(a.engine_scope_file))
    for f in [engine,scope]:regular(f)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.dll',engine.name):raise ValueError('Use a single fresh DLL basename matching the binding filename')
    if scope.name!=engine.stem+'.scope.json':raise ValueError('Scope must have the exact engine sibling filename')
    sc=json.loads(scope.read_text(encoding='utf-8-sig'))
    for key in ['task_root','runtime_root','install_root']:
        if os.path.normcase(os.path.abspath(sc[key]))!=os.path.normcase(os.path.abspath(cfg[key])):
            raise ValueError('Engine and bootstrap disagree on '+key)
    selected_editor=Path(sc.get('editor_executable',str(Path(sc['install_root'])/'Program'/'McgsSetPro.exe')))
    if os.path.normcase(os.path.abspath(selected_editor))!=os.path.normcase(os.path.abspath(cfg['editor_executable'])):
        raise ValueError('Engine and bootstrap disagree on the selected editor executable')
    target=boot/'engines'/engine.name;target_scope=target.with_suffix('.scope.json')
    if target.exists() or target_scope.exists():raise ValueError('Do not overwrite any engine/scope version')
    write_new(target,engine.read_bytes());write_new(target_scope,scope.read_bytes())
    runtime=Path(cfg['runtime_root']);runtime.mkdir(parents=True,exist_ok=True)
    for d in [runtime,*runtime.parents]:
        if d.stat(follow_symlinks=False).st_file_attributes & 0x400:raise ValueError('Runtime reparse ancestor')
    manifest=runtime/'active-engine.json'
    value={'assembly':str(target),'sha256':digest(target),'bootstrap_scope_sha256':digest(config)}
    # First deployment only. Later hot-engine selection remains a separate,
    # reviewed file-only action; it must retain this bootstrap scope digest.
    write_new(manifest,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'schema':1,'status':'own_engine_staged_not_host_called','manifest':str(manifest),
                      'engine_sha256':digest(target),'engine_scope_sha256':digest(target_scope),
                      'bootstrap_scope_sha256':digest(config),'host_started':False},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
