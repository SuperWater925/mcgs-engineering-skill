"""Compare extracted native UI evidence without a process, database or project writer.

python -B native_ui_rules.py --input evidence.json --out NEW-report.json
Input schema/examples: ../references/pro-native-ui-rules.json. Input references
only already-extracted files. Native profile declarations must come from an
independently verified ABI capture; this helper does not attest their provenance.
Exit 0=PASS, 2=DIFFERENCE, 3=REVIEW, 1=invalid input/I/O. No raw inputs/password
bytes are echoed, and report files are created exclusively.
"""
from __future__ import annotations
import argparse,hashlib,json,re,struct,sys,zlib
from pathlib import Path

class Invalid(ValueError):pass

def require(test,message):
    if not test:raise Invalid(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def digest(value):return isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value) is not None
def keys(value,allowed,required=()):
    require(isinstance(value,dict) and set(value)<=set(allowed) and set(required)<=set(value),'Object fields do not match the documented schema')
def text(value):
    require(isinstance(value,str) and value and len(value)<=4096 and '\0' not in value,'Expected bounded nonempty text');return value
def integer(value):return type(value)is int

def evaluate(data,base,rules):
    """Return a JSON-safe scoped comparison. Does not write or mutate inputs."""
    keys(data,{'schema','native_profile','pictures','passwords','cells'},{'schema'})
    require(data['schema']==1 and any(k in data for k in ('pictures','passwords','cells')),'Missing rule sections or unsupported schema')
    base=Path(base);results=[]
    def read_ref(ref):
        keys(ref,{'file','sha256','records_pointer'},{'file','sha256'})
        require(digest(ref['sha256']),'File reference requires lowercase SHA256')
        path=Path(ref['file']);path=path if path.is_absolute() else base/path
        require(path.suffix.lower() not in {'.mcp','.mcs','.mdb','.accdb'},'Only extracted evidence is accepted; project/database files are not read')
        require(path.stat().st_size<=64*1024*1024,'Evidence file exceeds64MiB')
        raw=path.read_bytes();require(sha(raw)==ref['sha256'],'Referenced evidence SHA256 differs');return raw
    def blob(value):
        require(isinstance(value,dict),'Blob must be an object')
        if 'hex' in value:
            keys(value,{'hex','sha256'},{'hex'});require(isinstance(value['hex'],str) and len(value['hex'])<=128*1024*1024,'Invalid bounded hex blob')
            try:raw=bytes.fromhex(value['hex'])
            except ValueError:raise Invalid('Invalid hex blob') from None
            if 'sha256' in value:require(digest(value['sha256']) and sha(raw)==value['sha256'],'Hex blob SHA256 differs')
            return raw
        keys(value,{'file','sha256'},{'file','sha256'});return read_ref(value)
    def record(ident,status,reason,**values):
        results.append(dict(id=ident,status=status,reason=reason,**values))
    def profile(contract):
        actual=data.get('native_profile',{});expected=rules['native_profile_contract']
        if not isinstance(actual,dict) or actual.get('binary_sha256')!=expected['binary_sha256']:return False
        if contract=='empty_ANSI_password' and actual.get('mfc110u_sha256')!=expected['mfc110u_sha256']:return False
        guards=actual.get('code_guards',{})
        return isinstance(guards,dict) and all(guards.get(k)==expected['code_guards'][k] for k in rules['contracts'][contract]['required_profile_guards'])
    if 'pictures' in data:
        pic=data['pictures'];keys(pic,{'before','after','before_names','after_names','approved_additions','native_save_receipt'},{'before','after','before_names','after_names','approved_additions'})
        def rows(values):
            require(isinstance(values,list),'Picture records must be an array');out={}
            for row in values:
                keys(row,{'name','content_hash','native_image_wire','name_wire'},{'name','content_hash','native_image_wire'})
                name=text(row['name']);require(name not in out,'Duplicate picture name');require(isinstance(row['content_hash'],str) and re.fullmatch('[0-9a-f]{32}',row['content_hash']),'Invalid picture content_hash')
                wire=blob(row['native_image_wire']);require(len(wire)>=4,'Native image stream has no mode DWORD')
                out[name]=(row,wire)
            return out
        before,after=rows(pic['before']),rows(pic['after']);approved=pic['approved_additions'];require(isinstance(approved,list),'Approved additions must be an array')
        additions={}
        for item in approved:
            keys(item,{'name','source','dimensions'},{'name','source','dimensions'});name=text(item['name']);require(name not in additions and name not in before,'Added picture names must be new and unique');additions[name]=item
        names_before,names_after=pic['before_names'],pic['after_names']
        list_ok=(isinstance(names_before,list) and isinstance(names_after,list) and len(names_before)==len(set(names_before)) and set(names_before)==set(before) and names_after==names_before+list(additions) and set(after)==set(before)|set(additions))
        record('picture-list','PASS' if list_ok else 'DIFFERENCE','Only declared names may be appended in declared order',old_count=len(before),new_count=len(after))
        save_hashes=None
        if 'native_save_receipt' in pic:
            ref=pic['native_save_receipt'];receipt=json.loads(read_ref(ref).decode('utf-8-sig'));require(receipt.get('ok') is True,'Native-save receipt did not report success')
            pointer=ref.get('records_pointer','/actions/0/apply/resource_catalog_after/records');require(isinstance(pointer,str) and pointer.startswith('/'),'Receipt records_pointer must be a JSON pointer')
            records=receipt
            try:
                for token in pointer[1:].split('/'):
                    token=token.replace('~1','/').replace('~0','~');records=records[int(token)] if isinstance(records,list) else records[token]
            except (KeyError,IndexError,ValueError,TypeError):raise Invalid('Native-save records pointer is absent') from None
            require(isinstance(records,list),'Native-save records must be an array');save_hashes={}
            for row in records:
                name=text(row['name']);value=row['content_hash'];require(name not in save_hashes and isinstance(value,str) and re.fullmatch('[0-9a-f]{32}',value),'Ambiguous/invalid native-save hash record');save_hashes[name]=value
        for name,(old,wire) in before.items():
            if name not in after:record('picture:'+name,'DIFFERENCE','Original picture removed');continue
            new,new_wire=after[name];same=wire==new_wire
            name_same=('name_wire' not in old and 'name_wire' not in new) or ('name_wire' in old and 'name_wire' in new and blob(old['name_wire'])==blob(new['name_wire']))
            if not same or not name_same:record('picture:'+name,'DIFFERENCE','Original image/name serialization changed',content_preserved=False);continue
            changed=old['content_hash']!=new['content_hash'];mode=struct.unpack_from('<I',wire)[0]
            if not changed:status,reason,algorithm='PASS','Complete original image and content_hash exact',False
            elif mode==2:
                algorithm=new['content_hash']==hashlib.md5(new_wire).hexdigest();status='PASS' if algorithm else 'DIFFERENCE';reason='Mode2 metadata must equal MD5 of the entire unchanged image stream'
            elif save_hashes is None:status,reason,algorithm='REVIEW','Changed non-mode2 metadata requires an explicit SHA-bound native-save receipt',False
            else:
                matched=save_hashes.get(name)==new['content_hash'];status='PASS' if matched else 'DIFFERENCE';reason='Non-mode2 metadata compared to exact original native-save postimage; algorithm not reproduced';algorithm=False
            record('picture:'+name,status,reason,content_preserved=True,native_image_wire_sha256=sha(new_wire),mode=mode,content_hash_metadata_changed=changed,hash_algorithm_independently_reproduced=algorithm)
        for name,item in additions.items():
            if name not in after:record('new-picture:'+name,'DIFFERENCE','Approved picture missing');continue
            row,wire=after[name];dims=item['dimensions'];require(isinstance(dims,list) and len(dims)==2 and all(integer(n) and 0<n<=32768 for n in dims),'Invalid declared PNG dimensions')
            require(digest(item['source'].get('sha256')),'New PNG source requires an explicit SHA256');png=blob(item['source'])
            ok=len(wire)>=16 and struct.unpack_from('<4I',wire)==(2,dims[0],dims[1],len(png)) and wire[16:]==png and png.startswith(b'\x89PNG\r\n\x1a\n') and len(png)>=24 and struct.unpack_from('>II',png,16)==tuple(dims)
            pos=8;ended=False
            while ok and pos<len(png):
                if pos+12>len(png):ok=False;break
                length=struct.unpack_from('>I',png,pos)[0];end=pos+8+length
                if end+4>len(png) or (zlib.crc32(png[pos+4:end])&0xffffffff)!=struct.unpack_from('>I',png,end)[0]:ok=False;break
                kind=png[pos+4:pos+8];pos=end+4
                if kind==b'IEND':ended=True;break
            ok=ok and ended and pos==len(png) and row['content_hash']==hashlib.md5(wire).hexdigest()
            record('new-picture:'+name,'PASS' if ok else 'DIFFERENCE','Exact approved PNG bytes,dimensions,full chunk CRCs and mode2 hash',source_sha256=sha(png))
    if 'passwords' in data:
        require(isinstance(data['passwords'],list),'passwords must be an array')
        expected=rules['contracts']['empty_ANSI_password']['required_metadata']
        for row in data['passwords']:
            keys(row,{'id','before_wire','after_wire','before_native','after_native'},{'id','before_wire','after_wire','before_native','after_native'})
            ident='password:'+text(row['id']);before,after=blob(row['before_wire']),blob(row['after_wire'])
            def empty(meta):
                return isinstance(meta,dict) and all(type(meta.get(k)) is type(v) and meta[k]==v for k,v in expected.items())
            matched=profile('empty_ANSI_password')
            # Require empty native state even for an equal opaque block; never infer it.
            ok=matched and empty(row['before_native']) and empty(row['after_native']) and row['before_native']==row['after_native'] and len(before)==len(after)==2 and before[0]==after[0]==0
            record(ident,'PASS' if ok else 'DIFFERENCE','Only source-profile-matched empty ANSI two-byte tail transitions are accepted',native_profile_matched=matched,before_wire_length=len(before),after_wire_length=len(after),before_wire_sha256=sha(before),after_wire_sha256=sha(after),wire_exact=before==after,tail_projection_used=ok and before!=after,password_content_disclosed=False)
    if 'cells' in data:
        require(isinstance(data['cells'],list),'cells must be an array')
        for row in data['cells']:
            keys(row,{'id','actual_class','actual_type_id','children','approved_child_fills','actual_parent_fill'},{'id','actual_class','actual_type_id','children','approved_child_fills','actual_parent_fill'})
            ident='cell:'+text(row['id']);contract=rules['contracts']['Cell_uniform_fill'];matched=profile('Cell_uniform_fill')
            require(isinstance(row['children'],list) and isinstance(row['approved_child_fills'],list),'Cell child inputs must be arrays')
            def child_map(values,field):
                out={}
                for child in values:
                    keys(child,{'id',field},{'id',field});key=text(child['id']);value=child[field];require(key not in out and integer(value) and 0<=value<=0xffffffff,'Invalid/duplicate child fill input');out[key]=value
                return out
            children=child_map(row['children'],'actual_fill');approved=child_map(row['approved_child_fills'],'value');parent=row['actual_parent_fill'];require(integer(parent) and 0<=parent<=0xffffffff,'Invalid parent fill')
            if not matched or row['actual_class']!=contract['actual_class'] or row['actual_type_id']!=contract['actual_type_id']:record(ident,'DIFFERENCE','Cell getter ABI/class/type does not match the proved contract');continue
            if not approved or set(children)!=set(approved):record(ident,'DIFFERENCE','Actual child identity set differs from the explicitly approved set');continue
            if len(set(approved.values()))!=1:record(ident,'REVIEW','Nonuniform approved fills have no derived-value rule');continue
            expected_fill=next(iter(approved.values()))
            ok=children==approved and parent==expected_fill
            record(ident,'PASS' if ok else 'DIFFERENCE','Compare one explicit parent getter expectation derived solely from approved uniform child values',expected_parent_fill=expected_fill,all_children_match_approved=children==approved,property_key=contract['native_key'],native_type_tag=0,masked_keys=[])
    require(results,'No checks supplied')
    status='DIFFERENCE' if any(r['status']=='DIFFERENCE' for r in results) else 'REVIEW' if any(r['status']=='REVIEW' for r in results) else 'PASS'
    return {'schema':1,'status':status,'counts':{k:sum(r['status']==k for r in results) for k in ('PASS','REVIEW','DIFFERENCE')},'checks':results,'native_process_or_database_accessed':False,'project_written':False,'input_provenance_independently_attested':False,'runtime_or_reopen_acceptance_claimed':False}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);p.add_argument('--input',required=True,type=Path);p.add_argument('--out',type=Path);p.add_argument('--rules',type=Path,default=Path(__file__).resolve().parents[1]/'references/pro-native-ui-rules.json');a=p.parse_args()
    data=json.loads(a.input.read_text(encoding='utf-8-sig'));rules=json.loads(a.rules.read_text(encoding='utf-8-sig'));require(rules.get('schema')==1,'Unsupported rule contract schema')
    result=evaluate(data,a.input.resolve().parent,rules);result['rules_sha256']=sha(a.rules.read_bytes())
    raw=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.out:
        with a.out.open('x',encoding='utf-8',newline='\n') as stream:stream.write(raw)
        print(json.dumps({'status':result['status'],'counts':result['counts'],'report_sha256':sha(raw.encode('utf-8'))}))
    else:print(raw,end='')
    return {'PASS':0,'DIFFERENCE':2,'REVIEW':3}[result['status']]
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'INVALID_INPUT','exception_type':type(error).__name__,'input_values_withheld':True}),file=sys.stderr);raise SystemExit(1)
