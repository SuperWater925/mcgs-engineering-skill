"""Publisher-only deterministic x86 thread hook. No target/config is compiled in.

IPC layout MPT6/v1: magic/version/pid/tid/creation at 0/4/8/12/16;
state 28 (0 ready, 1 entered, 2 returned), HRESULT/type/value at 32/36/40;
UTF16 config at 256 (32768 chars), SHA256 at 65792 (65 chars).
The mapping and completion event are named by current PID + creation FILETIME.
"""
from pathlib import Path
import hashlib,importlib.util,json,struct,uuid
BASE=0x68000000;ALIGN=0x1000;FA=0x200
p16=lambda x:struct.pack('<H',x)
p32=lambda x:struct.pack('<I',x&0xffffffff)
align=lambda n,a:(n+a-1)//a*a
def build(output,assembler_source):
 spec=importlib.util.spec_from_file_location('portable_assembler',assembler_source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);a=m.Assembler()
 data=bytearray();labels={}
 def blob(n,b):labels[n]=len(data);data.extend(b)
 def wide(n,s):blob(n,s.encode('utf-16le')+b'\0\0')
 blob('clsid',uuid.UUID('C81CD5F3-FD35-46C3-911F-304F48417645').bytes_le)
 blob('idispatch',uuid.UUID('00020400-0000-0000-C000-000000000046').bytes_le);blob('nullguid',bytes(16))
 wide('map_fmt',r'Local\McgsPortableAttach_v6_%u_%08X%08X')
 wide('event_fmt',r'Local\McgsPortableAttach_v6_%u_%08X%08X_done')
 def local(d):a.emit(b'\x8d\x85'+p32(d))
 def pushlocal(d):local(d);a.emit(b'\x50')
 def immediate(d,v):a.emit(b'\xc7\x85'+p32(d)+p32(v))
 def mapimm(d,v):a.emit(b'\xc7\x86'+p32(d)+p32(v))
 def mapstore(d):a.emit(b'\x89\x86'+p32(d))
 def format_name(label):
  a.emit(b'\xff\x75\xd0\xff\x75\xd4');a.call_import('GetCurrentProcessId');a.emit(b'\x50');a.push_address(('data',label));pushlocal(-1024);a.call_import('wsprintfW');a.emit(b'\x83\xc4\x14')
 a.label('DllMain');a.emit(b'\xb8\x01\0\0\0\xc2\x0c\0'+b'\x90'*8)
 a.label('GetMsgProc');a.emit(b'\x55\x8b\xec\x53\x56\x57\x81\xec'+p32(0x500))
 a.emit(b'\x83\x7d\x08\0');a.jump('chain',0x8c)
 a.emit(b'\x31\xc0\x89\x45\xec\x31\xf6') # map handle=-20, view=esi
 for d in (-16,-24,-112,-108,-104,-100,-144,-140,-136,-132,-176,-172,-168,-164,-160,-156,-152,-148):immediate(d,0)
 pushlocal(-72);pushlocal(-64);pushlocal(-56);pushlocal(-48);a.call_import('GetCurrentProcess');a.emit(b'\x50');a.call_import('GetProcessTimes');a.emit(b'\x85\xc0');a.jump('chain',0x84)
 format_name('map_fmt');pushlocal(-1024);a.push(0);a.push(0xF001F);a.call_import('OpenFileMappingW');a.emit(b'\x85\xc0');a.jump('chain',0x84);a.emit(b'\x89\x45\xec')
 a.push(131072);a.push(0);a.push(0);a.push(0xF001F);a.emit(b'\xff\x75\xec');a.call_import('MapViewOfFile');a.emit(b'\x85\xc0');a.jump('cleanup',0x84);a.emit(b'\x8b\xf0')
 a.emit(b'\x81\x3eMPT6');a.jump('cleanup',0x85)
 a.emit(b'\x83\x7e\x04\x01');a.jump('cleanup',0x85)
 a.call_import('GetCurrentProcessId');a.emit(b'\x39\x46\x08');a.jump('cleanup',0x85)
 a.call_import('GetCurrentThreadId');a.emit(b'\x39\x46\x0c');a.jump('cleanup',0x85)
 a.emit(b'\x8b\x45\xd0\x39\x46\x10');a.jump('cleanup',0x85)
 a.emit(b'\x8b\x45\xd4\x39\x46\x14');a.jump('cleanup',0x85)
 # One callback owns this mapping; CLR activation can re-enter the message pump.
 a.emit(b'\x31\xc0\xb9\x01\0\0\0\xf0\x0f\xb1\x4e\x1c');a.jump('cleanup',0x85)
 mapimm(32,0x8000FFFF);mapimm(36,0);mapimm(40,1)
 # Client always writes terminators; validate them before constructing BSTRs.
 a.emit(b'\x66\x83\xbe'+p32(256+65534)+b'\0');a.jump('signal',0x85)
 a.emit(b'\x66\x83\xbe'+p32(65792+128)+b'\0');a.jump('signal',0x85)
 pushlocal(-16);a.push_address(('data','idispatch'));a.push(1);a.push(0);a.push_address(('data','clsid'));a.call_import('CoCreateInstance');mapstore(32);a.emit(b'\x85\xc0');a.jump('signal',0x88)
 # rgvarg[0]=sha, rgvarg[1]=config: IDispatch arguments are reversed.
 a.emit(b'\x8d\x86'+p32(65792)+b'\x50');a.call_import('SysAllocString');a.emit(b'\x89\x85'+p32(-168));immediate(-176,8)
 a.emit(b'\x85\xc0');a.jump('oom',0x84)
 a.emit(b'\x8d\x86'+p32(256)+b'\x50');a.call_import('SysAllocString');a.emit(b'\x89\x85'+p32(-152));immediate(-160,8)
 a.emit(b'\x85\xc0');a.jump('oom',0x84)
 local(-176);a.emit(b'\x89\x85'+p32(-112));immediate(-104,2)
 a.push(0);a.push(0);pushlocal(-144);pushlocal(-112);a.push(1);a.push(0);a.push_address(('data','nullguid'));a.push(1);a.emit(b'\xff\x75\xf0\x8b\x45\xf0\x8b\x00\xff\x50\x18');mapstore(32)
 a.emit(b'\x0f\xb7\x85'+p32(-144));mapstore(36);a.emit(b'\x8b\x85'+p32(-136));mapstore(40);a.jump('release')
 a.label('oom');mapimm(32,0x8007000E)
 a.label('release')
 for d in (-176,-160,-144):pushlocal(d);a.call_import('VariantClear')
 a.emit(b'\xff\x75\xf0\x8b\x45\xf0\x8b\x00\xff\x50\x08')
 a.label('signal');mapimm(28,2)
 format_name('event_fmt');pushlocal(-1024);a.push(0);a.push(2);a.call_import('OpenEventW');a.emit(b'\x85\xc0');a.jump('cleanup',0x84)
 a.emit(b'\x89\x45\xe8\x50');a.call_import('SetEvent');a.emit(b'\xff\x75\xe8');a.call_import('CloseHandle')
 a.label('cleanup');a.emit(b'\x85\xf6');a.jump('close',0x84);a.emit(b'\x56');a.call_import('UnmapViewOfFile')
 a.label('close');a.emit(b'\x83\x7d\xec\0');a.jump('chain',0x84);a.emit(b'\xff\x75\xec');a.call_import('CloseHandle')
 a.label('chain');a.emit(b'\xff\x75\x10\xff\x75\x0c\xff\x75\x08');a.push(0);a.call_import('CallNextHookEx');a.emit(b'\x8d\x65\xf4\x5f\x5e\x5b\x5d\xc2\x0c\0')
 text_rva=0x1000;data_rva=align(text_rva+len(a.code),ALIGN);rdata_rva=align(data_rva+len(data),ALIGN)
 name=b'McgsPortableHook_v6.dll\0';func=b'GetMsgProc\0';rdata=bytearray(50+len(name)+len(func))
 struct.pack_into('<IIHH7I',rdata,0,0,0,0,0,rdata_rva+50,1,1,1,rdata_rva+40,rdata_rva+44,rdata_rva+48)
 struct.pack_into('<IIH',rdata,40,text_rva+a.labels['GetMsgProc'],rdata_rva+50+len(name),0);rdata[50:50+len(name)]=name;rdata[50+len(name):]=func
 groups={'kernel32.dll':['GetCurrentProcess','GetProcessTimes','GetCurrentProcessId','GetCurrentThreadId','OpenFileMappingW','MapViewOfFile','UnmapViewOfFile','CloseHandle','OpenEventW','SetEvent'],'user32.dll':['wsprintfW','CallNextHookEx'],'ole32.dll':['CoCreateInstance'],'oleaut32.dll':['SysAllocString','VariantClear']}
 idata_rva=align(rdata_rva+len(rdata),ALIGN);idata=bytearray(20*(len(groups)+1));addresses={('data',k):BASE+data_rva+v for k,v in labels.items()}
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
 return {'sha256':hashlib.sha256(image).hexdigest(),'bytes':len(image),'entry':'inert TRUE only','export':'GetMsgProc','ipc':'MPT6/v1;PID+creation-named shared mapping','target_hook':'thread-specific WH_GETMESSAGE','imports':groups,'target_paths_compiled':False,'vendor_methods':False,'remote_memory_writes':False,'remote_thread':False}
