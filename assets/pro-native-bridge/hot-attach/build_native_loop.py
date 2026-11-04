"""Own pure-native PE32 STA message loop. No CLR directory or vendor dependency.
The only window is HWND_MESSAGE; it exits normally when its own stop file appears.
"""
from pathlib import Path
import struct,importlib.util,hashlib
BASE=0x400000;ALIGN=4096;FA=512
p16=lambda v:struct.pack('<H',v);p32=lambda v:struct.pack('<I',v&0xffffffff)
al=lambda n,a:(n+a-1)//a*a
def build(runtime,output,assembler_source):
 mod=importlib.util.spec_from_file_location('native_loop_assembler',assembler_source);m=importlib.util.module_from_spec(mod);mod.loader.exec_module(m);a=m.Assembler()
 d=bytearray();labels={}
 def data(n,b):labels[n]=len(d);d.extend(b)
 def ws(n,s):data(n,str(s).encode('utf-16le')+b'\0\0')
 data('class',bytes(40));data('hwnd',bytes(4));data('ready',b'NLP1'+p32(1)+bytes(32));ws('classname','OwnColdClrMessageLoop');ws('title','Own transport-only message loop');ws('readyfile',Path(runtime)/'own-native-host.ready.bin');ws('stopfile',Path(runtime)/'own-native-host.stop')
 def abs(n,off=0):a.absolute32(('data',n,off))
 def push(n,off=0):a.emit(b'\x68');abs(n,off)
 def store(n,off=0):a.emit(b'\xa3');abs(n,off)
 def loc(off):a.emit(b'\x8d\x85'+p32(off))
 def ploc(off):loc(off);a.emit(b'\x50')
 def exitcode(c):a.push(c);a.call_import('ExitProcess')
 a.label('Entry');a.emit(b'\x55\x8b\xec\x53\x56\x57\x81\xec'+p32(0x100))
 a.push(0);a.call_import('OleInitialize');a.emit(b'\x85\xc0');a.jump('badcom',0x88)
 a.push(0);a.call_import('GetModuleHandleW');store('class',16);push('class');a.call_import('RegisterClassW');a.emit(b'\x85\xc0');a.jump('badwindow',0x84)
 a.push(0);a.emit(b'\xa1');abs('class',16);a.emit(b'\x50');a.push(0);a.push(-3)
 for _ in range(4):a.push(0)
 a.push(0);push('title');push('classname');a.push(0);a.call_import('CreateWindowExW');a.emit(b'\x85\xc0');a.jump('badwindow',0x84);store('hwnd');store('ready',24)
 a.push(0);a.push(100);a.push(1);a.emit(b'\x50');a.call_import('SetTimer');a.emit(b'\x85\xc0');a.jump('badwindow',0x84)
 a.call_import('GetCurrentProcessId');store('ready',8);a.call_import('GetCurrentThreadId');store('ready',12)
 ploc(-72);ploc(-80);ploc(-88);ploc(-96);a.call_import('GetCurrentProcess');a.emit(b'\x50');a.call_import('GetProcessTimes');a.emit(b'\x85\xc0');a.jump('badwindow',0x84)
 a.emit(b'\x8b\x45\xa0');store('ready',16);a.emit(b'\x8b\x45\xa4');store('ready',20)
 a.push(0);a.push(0x80);a.push(1);a.push(0);a.push(1);a.push(0x40000000);push('readyfile');a.call_import('CreateFileW');a.emit(b'\x83\xf8\xff');a.jump('badwindow',0x84);a.emit(b'\x89\x45\x9c')
 a.push(0);ploc(-104);a.push(40);push('ready');a.emit(b'\xff\x75\x9c');a.call_import('WriteFile');a.emit(b'\xff\x75\x9c');a.call_import('FlushFileBuffers');a.emit(b'\xff\x75\x9c');a.call_import('CloseHandle')
 a.label('loop');a.push(0);a.push(0);a.push(0);ploc(-64);a.call_import('GetMessageW');a.emit(b'\x85\xc0');a.jump('quit',0x8e);ploc(-64);a.call_import('TranslateMessage');ploc(-64);a.call_import('DispatchMessageW');a.jump('loop')
 a.label('quit');a.call_import('OleUninitialize');exitcode(0)
 a.label('badcom');exitcode(101)
 a.label('badwindow');exitcode(102)
 a.label('WndProc');a.emit(b'\x55\x8b\xec\x81\x7d\x0c\x13\x01\0\0');a.jump('not_timer',0x85);push('stopfile');a.call_import('GetFileAttributesW');a.emit(b'\x83\xf8\xff');a.jump('default',0x84);a.emit(b'\xff\x75\x08');a.call_import('DestroyWindow');a.jump('zero')
 a.label('not_timer');a.emit(b'\x83\x7d\x0c\x02');a.jump('default',0x85);a.push(0);a.call_import('PostQuitMessage');a.jump('zero')
 a.label('default');a.emit(b'\xff\x75\x14\xff\x75\x10\xff\x75\x0c\xff\x75\x08');a.call_import('DefWindowProcW');a.emit(b'\x5d\xc2\x10\0')
 a.label('zero');a.emit(b'\x33\xc0\x5d\xc2\x10\0')
 tr=0x1000;dr=al(tr+len(a.code),ALIGN);ir=al(dr+len(d),ALIGN)
 struct.pack_into('<I',d,labels['class']+4,BASE+tr+a.labels['WndProc']);struct.pack_into('<I',d,labels['class']+36,BASE+dr+labels['classname'])
 groups={'kernel32.dll':['GetModuleHandleW','GetCurrentProcessId','GetCurrentThreadId','GetCurrentProcess','GetProcessTimes','CreateFileW','WriteFile','FlushFileBuffers','CloseHandle','GetFileAttributesW','ExitProcess'],
 'user32.dll':['RegisterClassW','CreateWindowExW','SetTimer','GetMessageW','TranslateMessage','DispatchMessageW','DestroyWindow','PostQuitMessage','DefWindowProcW'],'ole32.dll':['OleInitialize','OleUninitialize']}
 imports=bytearray(20*(len(groups)+1));addresses={}
 for off,key in a.absolute:
  if key[0]=='data':addresses[key]=BASE+dr+labels[key[1]]+key[2]
 for idx,(dll,names) in enumerate(groups.items()):
  ds=len(imports);imports.extend(dll.encode()+b'\0');h=[]
  for n in names:
   if len(imports)%2:imports.append(0)
   h.append(ir+len(imports));imports.extend(b'\0\0'+n.encode()+b'\0')
  while len(imports)%4:imports.append(0)
  it=len(imports);imports.extend(b''.join(p32(v)for v in h+[0]));iat=len(imports);imports.extend(b''.join(p32(v)for v in h+[0]));struct.pack_into('<5I',imports,20*idx,ir+it,0,0,ir+ds,ir+iat)
  for j,n in enumerate(names):addresses['iat',n]=BASE+ir+iat+j*4
 code=a.finish(addresses);rr=al(ir+len(imports),ALIGN);blocks={}
 for site in [tr+off for off,_ in a.absolute]+[dr+labels['class']+4,dr+labels['class']+36]:blocks.setdefault(site&~4095,[]).append(0x3000|(site&4095))
 reloc=bytearray()
 for page,entries in sorted(blocks.items()):
  if len(entries)%2:entries.append(0)
  reloc.extend(struct.pack('<II',page,8+2*len(entries))+b''.join(p16(v)for v in entries))
 sec=[('.text',tr,code,0x60000020),('.data',dr,bytes(d),0xc0000040),('.idata',ir,bytes(imports),0xc0000040),('.reloc',rr,bytes(reloc),0x42000040)]
 hs=al(0x80+4+20+224+40*len(sec),FA);dos=bytearray(128);dos[:2]=b'MZ';struct.pack_into('<I',dos,60,128);opt=bytearray(224)
 struct.pack_into('<HBB9I',opt,0,0x10b,0,0,al(len(code),FA),sum(al(len(c),FA)for _,_,c,_ in sec[1:]),0,tr+a.labels['Entry'],tr,dr,BASE,ALIGN,FA);struct.pack_into('<6H',opt,40,6,0,0,0,6,0);struct.pack_into('<4I',opt,52,0,al(rr+len(reloc),ALIGN),hs,0);struct.pack_into('<HH',opt,68,2,0x140);struct.pack_into('<6I',opt,72,0x100000,0x1000,0x100000,0x1000,0,16)
 for i,r,n in [(1,ir,20*(len(groups)+1)),(5,rr,len(reloc))]:struct.pack_into('<II',opt,96+i*8,r,n)
 headers=bytes(dos)+b'PE\0\0'+struct.pack('<HHIIIHH',0x14c,len(sec),0,0,0,224,0x102)+bytes(opt);payload=bytearray();offset=hs
 for n,r,c,f in sec:
  rs=al(len(c),FA);headers+=struct.pack('<8s6I2HI',n.encode(),len(c),r,rs,offset,0,0,0,0,f);payload.extend(c.ljust(rs,b'\0'));offset+=rs
 image=headers.ljust(hs,b'\0')+payload
 with Path(output).open('xb')as f:f.write(image)
 return {'file':str(output),'sha256':hashlib.sha256(image).hexdigest(),'bits':32,'clr_directory':False,'own_test_host':True,'vendor_dependency':False,'imports':groups,'normal_stop':'own-native-host.stop -> DestroyWindow -> WM_DESTROY -> PostQuitMessage -> OleUninitialize/ExitProcess0'}
