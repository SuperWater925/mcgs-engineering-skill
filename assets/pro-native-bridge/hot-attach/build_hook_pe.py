"""Generate an own native x86 WH_GETMESSAGE hook; never load it here.
The hook uses ordinary COM to load the independently registered own bootstrap.
DllMain is inert. There are no remote-memory writes, remote threads or vendor APIs.
"""
from pathlib import Path
import argparse,hashlib,json,struct,uuid,importlib.util
BASE=0x68000000;ALIGN=0x1000;FA=0x200
p16=lambda x:struct.pack('<H',x);p32=lambda x:struct.pack('<I',x&0xffffffff)
align=lambda n,a:(n+a-1)//a*a
def build(config,output,assembler_source):
 q=json.loads(Path(config).read_text(encoding='utf-8-sig'))
 module=importlib.util.spec_from_file_location('own_wrapper_assembler',assembler_source);m=importlib.util.module_from_spec(module);module.loader.exec_module(m);a=m.Assembler()
 data=bytearray();labels={}
 def blob(name,value):labels[name]=len(data);data.extend(value);return name
 def wide(name,s):return blob(name,s.encode('utf-16le')+b'\0\0')
 blob('state',p32(0));blob('record',b'HAT1'+p32(1)+b'\0'*32)
 blob('clsid',uuid.UUID(q['class_guid']).bytes_le);blob('idispatch',uuid.UUID('00020400-0000-0000-C000-000000000046').bytes_le);blob('nullguid',bytes(16))
 wide('event_fmt',q['event_prefix']+'%u');wide('record_fmt',str(Path(q['runtime_root'])/'hot-attach'/'native-').replace('%','%%')+'%u.bin')
 def addr(x):a.absolute32(('data',x))
 def store(x,offset=0):a.emit(b'\xa3');a.absolute32(('dataoffset',x,offset))
 def mov_abs_imm(x,value):a.emit(b'\xc7\x05');addr(x);a.emit(p32(value))
 def lea(d):a.emit(b'\x8d\x85'+p32(d))
 def pushlocal(d):lea(d);a.emit(b'\x50')
 a.label('DllMain');a.emit(b'\xb8\x01\0\0\0\xc2\x0c\0');a.emit(b'\x90'*8)
 a.label('GetMsgProc');a.emit(b'\x55\x8b\xec\x53\x56\x57\x81\xec'+p32(0x500))
 a.emit(b'\x83\x7d\x08\0');a.jump('chain',0x8c)
 a.emit(b'\xa1');addr('state');a.emit(b'\x85\xc0');a.jump('chain',0x85);mov_abs_imm('state',1)
 # Own fixed locals: pDispatch -16, params -48, VARIANT -80, written -84, handles -88.
 a.emit(b'\x31\xc0\x89\x45\xf0');
 for off in [-48,-44,-40,-36,-80,-76,-72,-68]:a.emit(b'\x89\x85'+p32(off))
 a.call_import('GetCurrentProcessId');store('record',8);a.call_import('GetCurrentThreadId');store('record',12)
 pushlocal(-16);a.push_address(('data','idispatch'));a.push(1);a.push(0);a.push_address(('data','clsid'));a.call_import('CoCreateInstance');store('record',16)
 a.emit(b'\x85\xc0');a.jump('signal',0x88)
 # IDispatch::Invoke(1,IID_NULL,0,METHOD,&params,&result,NULL,NULL).
 a.push(0);a.push(0);pushlocal(-80);pushlocal(-48);a.push(1);a.push(0);a.push_address(('data','nullguid'));a.push(1);a.emit(b'\xff\x75\xf0\x8b\x45\xf0\x8b\x00\xff\x50\x18');store('record',16)
 a.emit(b'\x0f\xb7\x85'+p32(-80));store('record',20);a.emit(b'\x8b\x85'+p32(-72));store('record',24)
 pushlocal(-80);a.call_import('VariantClear');a.emit(b'\xff\x75\xf0\x8b\x45\xf0\x8b\x00\xff\x50\x08')
 a.label('signal')
 # Persist native HRESULT/type/value only, no UI text or application memory.
 a.call_import('GetCurrentProcessId');a.emit(b'\x50');a.push_address(('data','record_fmt'));pushlocal(-1024);a.call_import('wsprintfW');a.emit(b'\x83\xc4\x0c')
 a.push(0);a.push(0x80);a.push(1);a.push(0);a.push(1);a.push(0x40000000);pushlocal(-1024);a.call_import('CreateFileW');a.emit(b'\x83\xf8\xff');a.jump('event',0x84)
 a.emit(b'\x89\x45\xa8');a.push(0);pushlocal(-84);a.push(40);a.push_address(('data','record'));a.emit(b'\xff\x75\xa8');a.call_import('WriteFile');a.emit(b'\xff\x75\xa8');a.call_import('FlushFileBuffers');a.emit(b'\xff\x75\xa8');a.call_import('CloseHandle')
 a.label('event');a.call_import('GetCurrentProcessId');a.emit(b'\x50');a.push_address(('data','event_fmt'));pushlocal(-1024);a.call_import('wsprintfW');a.emit(b'\x83\xc4\x0c');pushlocal(-1024);a.push(0);a.push(2);a.call_import('OpenEventW');a.emit(b'\x85\xc0');a.jump('done',0x84)
 a.emit(b'\x89\x45\xa8\x50');a.call_import('SetEvent');a.emit(b'\xff\x75\xa8');a.call_import('CloseHandle')
 a.label('done');mov_abs_imm('state',2)
 a.label('chain');a.emit(b'\xff\x75\x10\xff\x75\x0c\xff\x75\x08');a.push(0);a.call_import('CallNextHookEx');a.emit(b'\x8d\x65\xf4\x5f\x5e\x5b\x5d\xc2\x0c\0')
 text_rva=0x1000;data_rva=align(text_rva+len(a.code),ALIGN);rdata_rva=align(data_rva+len(data),ALIGN)
 # One ordinary PE export.
 name=b'McgsHotAttachHook.dll\0';func=b'GetMsgProc\0';rdata=bytearray(50+len(name)+len(func))
 struct.pack_into('<IIHH7I',rdata,0,0,0,0,0,rdata_rva+50,1,1,1,rdata_rva+40,rdata_rva+44,rdata_rva+48)
 struct.pack_into('<IIH',rdata,40,text_rva+a.labels['GetMsgProc'],rdata_rva+50+len(name),0);rdata[50:50+len(name)]=name;rdata[50+len(name):]=func
 groups={'kernel32.dll':['GetCurrentProcessId','GetCurrentThreadId','CreateFileW','WriteFile','FlushFileBuffers','CloseHandle','OpenEventW','SetEvent'],
         'user32.dll':['wsprintfW','CallNextHookEx'],'ole32.dll':['CoCreateInstance'],'oleaut32.dll':['VariantClear']}
 idata_rva=align(rdata_rva+len(rdata),ALIGN);idata=bytearray(20*(len(groups)+1));addresses={('data',k):BASE+data_rva+v for k,v in labels.items()}
 for off,target in a.absolute:
  if target[0]=='dataoffset':addresses[target]=BASE+data_rva+labels[target[1]]+target[2]
 for idx,(dll,names) in enumerate(groups.items()):
  ds=len(idata);idata.extend(dll.encode()+b'\0');hints=[]
  for n in names:
   if len(idata)%2:idata.append(0)
   hints.append(idata_rva+len(idata));idata.extend(b'\0\0'+n.encode()+b'\0')
  while len(idata)%4:idata.append(0)
  it=len(idata);idata.extend(b''.join(p32(v)for v in hints+[0]));iat=len(idata);idata.extend(b''.join(p32(v)for v in hints+[0]))
  struct.pack_into('<5I',idata,20*idx,idata_rva+it,0,0,idata_rva+ds,idata_rva+iat)
  for j,n in enumerate(names):addresses['iat',n]=BASE+idata_rva+iat+j*4
 code=a.finish(addresses);reloc_rva=align(idata_rva+len(idata),ALIGN);blocks={}
 for off,_ in a.absolute:site=text_rva+off;blocks.setdefault(site&~0xfff,[]).append(0x3000|(site&0xfff))
 reloc=bytearray()
 for page,entries in sorted(blocks.items()):
  if len(entries)%2:entries.append(0)
  reloc.extend(struct.pack('<II',page,8+len(entries)*2)+b''.join(p16(v)for v in entries))
 sections=[('.text',text_rva,code,0x60000020),('.data',data_rva,bytes(data),0xc0000040),('.rdata',rdata_rva,bytes(rdata),0x40000040),('.idata',idata_rva,bytes(idata),0xc0000040),('.reloc',reloc_rva,bytes(reloc),0x42000040)]
 hs=align(0x80+4+20+224+len(sections)*40,FA);dos=bytearray(0x80);dos[:2]=b'MZ';struct.pack_into('<I',dos,0x3c,0x80)
 opt=bytearray(224);struct.pack_into('<HBB9I',opt,0,0x10b,0,0,align(len(code),FA),sum(align(len(s[2]),FA)for s in sections[1:]),0,text_rva+a.labels['DllMain'],text_rva,data_rva,BASE,ALIGN,FA)
 struct.pack_into('<6H',opt,40,6,0,0,0,6,0);struct.pack_into('<4I',opt,52,0,align(reloc_rva+len(reloc),ALIGN),hs,0);struct.pack_into('<HH',opt,68,2,0x140);struct.pack_into('<6I',opt,72,0x100000,0x1000,0x100000,0x1000,0,16)
 for n,r,size in [(0,rdata_rva,len(rdata)),(1,idata_rva,20*(len(groups)+1)),(5,reloc_rva,len(reloc))]:struct.pack_into('<II',opt,96+n*8,r,size)
 headers=bytes(dos)+b'PE\0\0'+struct.pack('<HHIIIHH',0x14c,len(sections),0,0,0,224,0x2102)+bytes(opt);payload=bytearray();offset=hs
 for n,r,c,f in sections:
  rs=align(len(c),FA);headers+=struct.pack('<8s6I2HI',n.encode(),len(c),r,rs,offset,0,0,0,0,f);payload.extend(c.ljust(rs,b'\0'));offset+=rs
 image=headers.ljust(hs,b'\0')+payload
 with Path(output).open('xb')as f:f.write(image)
 return {'file':str(output),'sha256':hashlib.sha256(image).hexdigest(),'bytes':len(image),'entry':'inert TRUE only','export':'GetMsgProc','target_hook':'thread-specific WH_GETMESSAGE only','relocations':len(a.absolute),'imports':groups,'vendor_methods':False,'remote_memory_writes':False,'remote_thread':False}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--output',required=True);ap.add_argument('--assembler-source',required=True);z=ap.parse_args();print(json.dumps(build(z.config,z.output,z.assembler_source),indent=2))
