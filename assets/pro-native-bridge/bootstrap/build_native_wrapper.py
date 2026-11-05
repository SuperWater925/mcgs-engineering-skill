"""Build this experiment's native x86 self-registration adapter, without loading it.

The native Pro scanner deletes its scanned coclass registration, then calls the
scanned DLL's *native* DllRegisterServer export.  This adapter carries the exact
stable bridge type library and restores only the three transaction-owned private
HKLM/Registry32 roots.  It is not a COM server and does not invoke the bridge.

No registry API is invoked by this Python builder.  DllRegisterServer must be
separately reviewed and explicitly invoked by the parent experiment runner.
"""
from pathlib import Path
import hashlib
import json
import struct
import urllib.parse
import argparse
import re
import uuid


HERE = None
BOOT = None
CONTRACT = None
IMAGE_BASE = 0x68000000
ALIGN = 0x1000
FILE_ALIGN = 0x200
HKLM = 0x80000002
MARKER = 'CodexBridgeTransactionId'
ROOTS = None
WRAPPER_NAME = None
IMPORTS = ['RegOpenKeyExW', 'RegQueryValueExW', 'RegCreateKeyExW',
           'RegSetValueExW', 'RegCloseKey']


def p16(n): return struct.pack('<H', n)
def p32(n): return struct.pack('<I', n & 0xffffffff)
def align(n, a): return (n + a - 1) // a * a
def sha(b): return hashlib.sha256(b).hexdigest()
def wstr(s): return s.encode('utf-16le') + b'\0\0'


class Assembler:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}
        self.branches = []
        self.absolute = []

    def emit(self, b): self.code.extend(b)
    def label(self, name):
        if name in self.labels: raise ValueError('Duplicate label ' + name)
        self.labels[name] = len(self.code)
    def jump(self, name, condition=None):
        self.emit(b'\xe9' if condition is None else b'\x0f' + bytes([condition]))
        self.branches.append((len(self.code), name))
        self.emit(b'\0' * 4)
    def absolute32(self, target):
        self.absolute.append((len(self.code), target))
        self.emit(b'\0' * 4)
    def push(self, value): self.emit(b'\x68' + p32(value))
    def push_address(self, target):
        self.emit(b'\x68'); self.absolute32(target)
    def call_import(self, name):
        self.emit(b'\xff\x15'); self.absolute32(('iat', name))
    def lea_eax_local(self, disp): self.emit(b'\x8d\x85' + p32(disp))
    def push_local_address(self, disp):
        self.lea_eax_local(disp); self.emit(b'\x50')
    def push_handle(self): self.emit(b'\xff\x75\xf0')  # [ebp-16]
    def finish(self, addresses):
        for offset, name in self.branches:
            struct.pack_into('<i', self.code, offset, self.labels[name] - offset - 4)
        for offset, target in self.absolute:
            struct.pack_into('<I', self.code, offset, addresses[target])
        return bytes(self.code)


def load_contract():
    global ROOTS, WRAPPER_NAME
    tx_path = CONTRACT
    plan_path = BOOT / 'hklm-registration-plan.json'
    tx_raw, plan_raw = tx_path.read_bytes(), plan_path.read_bytes()
    tx, plan = json.loads(tx_raw), json.loads(plan_raw)
    if tx['state'] != 'prepared_not_registered' or tx['hive'] != 'HKLM' or tx['view'] != 'Registry32':
        raise ValueError('Unexpected transaction hive/view')
    config_raw = (BOOT / 'McgsInternalBridge.bridge.json').read_bytes()
    config = json.loads(config_raw)
    if tx['bootstrap_scope_sha256'] != sha(config_raw) or plan['bootstrap_scope_sha256'] != sha(config_raw) or Path(config['bootstrap_root']).resolve() != BOOT:
        raise ValueError('Registration contract/config binding differs')
    identity = config.get('cold_com_identity')
    if identity is None:
        ROOTS = [r'Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}',
                 r'Software\Classes\McgsInternalBridge.AddInObj',
                 r'Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}']
        WRAPPER_NAME = 'McgsInternalLoader.dll'
    else:
        cls, lib, interface = [str(uuid.UUID(identity[key])).upper() for key in ('class_guid', 'type_library_guid', 'interface_guid')]
        progid, WRAPPER_NAME = identity['progid'], identity['native_wrapper_file_name']
        if not re.fullmatch(r'McgsInternalBridge\.AddInObj_[a-f0-9]{10}', progid) or not re.fullmatch(r'McgsInternalLoader_[a-f0-9]{10}\.dll', WRAPPER_NAME):
            raise ValueError('Invalid deployment-scoped cold COM identity')
        if progid != 'McgsInternalBridge.' + identity['coclass_name']:
            raise ValueError('Cold coclass and ProgID disagree')
        ROOTS = ['Software\\Classes\\CLSID\\{'+cls+'}', 'Software\\Classes\\'+progid,
                 'Software\\Classes\\TypeLib\\{'+lib+'}']
    if tx['roots'] != ROOTS or plan['requires_absent_roots'] != ROOTS:
        raise ValueError('Private root allowlist changed')
    token = tx['transaction_id']
    if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Unexpected transaction marker')
    entries = tx['expected_entries']
    stable = BOOT / 'McgsInternalBridge.dll'
    codebase = 'file:///' + str(stable).replace('\\', '/')
    if urllib.parse.unquote(codebase) != codebase:
        raise ValueError('CodeBase must use the tested unescaped native URI')
    seen = set()
    for entry in entries:
        key = entry['key']
        if not any(key == r or key.startswith(r + '\\') for r in ROOTS):
            raise ValueError('Registry key outside allowlist: ' + key)
        if key in seen: raise ValueError('Duplicate registry key')
        seen.add(key)
        for name, value in entry['values'].items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise ValueError('Only REG_SZ values are supported')
            if '\0' in name + value: raise ValueError('Embedded NUL')
            if len(wstr(value)) > 2048: raise ValueError('Registry value too large')
            if name == 'CodeBase' and value != codebase:
                raise ValueError('Transaction CodeBase is not current unescaped URI')
    for root in ROOTS:
        entry = next(e for e in entries if e['key'] == root)
        if entry['values'].get(MARKER) != token:
            raise ValueError('Missing matching ownership marker on root')
    plan_values = {e['key']: e['values'] for e in plan['registration']}
    for key, values in plan_values.items():
        actual = next(e['values'] for e in entries if e['key'] == key)
        if any(actual.get(name) != value for name, value in values.items()):
            raise ValueError('Plan and transaction disagree at ' + key)
    # Root ownership markers must be the first registration writes.
    entries = sorted(entries, key=lambda e: (0 if e['key'] in ROOTS else 1,
                                             ROOTS.index(e['key']) if e['key'] in ROOTS else 0))
    return entries, token, {'transaction': str(tx_path), 'transaction_sha256': sha(tx_raw),
                            'plan': str(plan_path), 'plan_sha256': sha(plan_raw),
                            'stable_path': str(stable), 'stable_sha256': sha(stable.read_bytes()),
                            'transaction_id': token, 'codebase': codebase,
                            'bootstrap_scope_sha256': sha(config_raw), 'cold_com_identity': identity}


def build():
    entries, token, sources = load_contract()
    strings = bytearray()
    str_offsets = {}
    def intern(value):
        key = ('str', value)
        if key not in str_offsets:
            str_offsets[key] = len(strings)
            strings.extend(wstr(value))
        return key
    for e in entries:
        intern(e['key'])
        for name, value in e['values'].items(): intern(name); intern(value)
    intern(MARKER); intern(token)

    a = Assembler()
    a.label('DllMain')
    a.emit(b'\xb8\x01\0\0\0\xc2\x0c\0')  # TRUE; stdcall 3 args
    a.emit(b'\x90' * (align(len(a.code), 16) - len(a.code)))
    a.label('DllRegisterServer')
    # EBP establishes locals.  Saved EBX/ESI/EDI occupy -4/-8/-12.
    # hKey=-16, cbData=-20, type=-24, originalError=-28,
    # disposition=-32, buffer=-2080 (ends at -33).
    a.emit(b'\x55\x8b\xec\x53\x56\x57\x81\xec' + p32(0x820))
    a.emit(b'\xc7\x45\xf0\0\0\0\0')

    def open_key(key, missing_label):
        a.push_local_address(-16)
        a.push(0x201)  # KEY_QUERY_VALUE | KEY_WOW64_32KEY
        a.push(0); a.push_address(intern(key)); a.push(HKLM)
        a.call_import('RegOpenKeyExW')
        a.emit(b'\x85\xc0'); a.jump('open_ok_' + missing_label, 0x84)
        a.emit(b'\x83\xf8\x02'); a.jump(missing_label, 0x84)
        a.emit(b'\x83\xf8\x03'); a.jump(missing_label, 0x84)
        a.jump('error_no_close')
        a.label('open_ok_' + missing_label)

    query_counter = 0
    def query_value(name, expected, missing_ok):
        nonlocal query_counter
        n = str(query_counter); query_counter += 1
        done = 'query_done_' + n
        present = 'query_present_' + n
        a.emit(b'\xc7\x45\xec' + p32(2048))
        a.emit(b'\xc7\x45\xe8' + p32(0))
        a.push_local_address(-20); a.push_local_address(-2080)
        a.push_local_address(-24); a.push(0)
        a.push_address(intern(name)); a.push_handle()
        a.call_import('RegQueryValueExW')
        a.emit(b'\x85\xc0'); a.jump(present, 0x84)
        a.emit(b'\x83\xf8\x02')
        a.jump(done if missing_ok else 'ownership_denied_close', 0x84)
        a.jump('error_close')
        a.label(present)
        a.emit(b'\x83\x7d\xe8\x01'); a.jump('invalid_data_close', 0x85)
        a.emit(b'\x81\x7d\xec' + p32(len(wstr(expected))))
        a.jump('invalid_data_close', 0x85)
        a.emit(b'\x8d\xb5' + p32(-2080))
        a.emit(b'\xbf'); a.absolute32(intern(expected))
        a.emit(b'\xb9' + p32(len(wstr(expected))) + b'\xfc\xf3\xa6')
        a.jump('invalid_data_close', 0x85)
        a.label(done)

    def close_ok():
        a.push_handle(); a.call_import('RegCloseKey')
        a.emit(b'\x85\xc0'); a.jump('error_no_close', 0x85)
        a.emit(b'\xc7\x45\xf0\0\0\0\0')

    # Read-only full preflight, before any key/value mutation.
    for idx, root in enumerate(ROOTS):
        skip = 'root_absent_' + str(idx)
        open_key(root, skip); query_value(MARKER, token, False); close_ok(); a.label(skip)
    for idx, e in enumerate(entries):
        skip = 'entry_absent_' + str(idx)
        open_key(e['key'], skip)
        for name, value in e['values'].items(): query_value(name, value, True)
        close_ok(); a.label(skip)
    a.label('preflight_complete')

    writes = []
    for idx, e in enumerate(entries):
        a.push_local_address(-32)
        a.push_local_address(-16)
        a.push(0); a.push(0x203)  # security=null; QUERY|SET|WOW64_32KEY
        a.push(0); a.push(0); a.push(0)
        a.push_address(intern(e['key'])); a.push(HKLM)
        a.call_import('RegCreateKeyExW')
        a.emit(b'\x85\xc0'); a.jump('error_no_close', 0x85)
        if e['key'] in ROOTS:
            # A root which appeared since preflight must also carry our marker.
            created = 'root_newly_created_' + str(idx)
            a.emit(b'\x83\x7d\xe0\x01'); a.jump(created, 0x84)
            a.emit(b'\x83\x7d\xe0\x02'); a.jump('invalid_data_close', 0x85)
            query_value(MARKER, token, False)
            a.label(created)
        # Repeat each value check just before setting; existing mismatches are
        # never overwritten.  Unknown values are neither read nor overwritten.
        items = list(e['values'].items())
        if e['key'] in ROOTS:
            items.sort(key=lambda item: 0 if item[0] == MARKER else 1)
        for name, value in items:
            query_value(name, value, True)
            offset = len(a.code)
            a.push(len(wstr(value))); a.push_address(intern(value)); a.push(1)
            a.push(0); a.push_address(intern(name)); a.push_handle()
            a.call_import('RegSetValueExW')
            a.emit(b'\x85\xc0'); a.jump('error_close', 0x85)
            writes.append({'key': e['key'], 'name': name, 'value': value,
                           'type': 'REG_SZ', 'cbData': len(wstr(value)),
                           'code_offset': offset})
        close_ok()
    a.emit(b'\x31\xc0'); a.jump('epilog')
    a.label('ownership_denied_close'); a.emit(b'\xb8' + p32(5)); a.jump('error_close')
    a.label('invalid_data_close'); a.emit(b'\xb8' + p32(13)); a.jump('error_close')
    a.label('error_close')
    a.emit(b'\x89\x45\xe4')
    a.push_handle(); a.call_import('RegCloseKey')
    a.emit(b'\x8b\x45\xe4')
    a.label('error_no_close')
    # HRESULT_FROM_WIN32 preserves <=0; otherwise FACILITY_WIN32 | low16.
    a.emit(b'\x85\xc0'); a.jump('epilog', 0x8e)
    a.emit(b'\x25\xff\xff\0\0\x0d\0\0\x07\x80')
    a.label('epilog')
    a.emit(b'\x81\xc4' + p32(0x820) + b'\x5f\x5e\x5b\x5d\xc3')

    text_rva = 0x1000
    rdata_rva = align(text_rva + len(a.code), ALIGN)
    # Export table precedes aligned UTF16 strings.
    export_name = WRAPPER_NAME.encode('ascii') + b'\0'
    export_func = b'DllRegisterServer\0'
    export_size = 50 + len(export_name) + len(export_func)
    strings_offset = align(export_size, 4)
    rdata = bytearray(strings_offset) + strings
    struct.pack_into('<IIHHIIIIIII', rdata, 0, 0, 0, 0, 0,
                     rdata_rva + 50, 1, 1, 1, rdata_rva + 40,
                     rdata_rva + 44, rdata_rva + 48)
    struct.pack_into('<IIH', rdata, 40,
                     text_rva + a.labels['DllRegisterServer'],
                     rdata_rva + 50 + len(export_name), 0)
    rdata[50:50+len(export_name)] = export_name
    rdata[50+len(export_name):export_size] = export_func

    idata_rva = align(rdata_rva + len(rdata), ALIGN)
    idata = bytearray(40)
    dll_offset = len(idata); idata.extend(b'advapi32.dll\0')
    if len(idata) & 1: idata.append(0)
    hints = []
    for name in IMPORTS:
        hints.append(idata_rva + len(idata))
        idata.extend(b'\0\0' + name.encode('ascii') + b'\0')
        if len(idata) & 1: idata.append(0)
    while len(idata) & 3: idata.append(0)
    int_offset = len(idata)
    for value in hints + [0]: idata.extend(p32(value))
    iat_offset = len(idata)
    for value in hints + [0]: idata.extend(p32(value))
    struct.pack_into('<5I', idata, 0, idata_rva + int_offset, 0, 0,
                     idata_rva + dll_offset, idata_rva + iat_offset)
    addresses = {key: IMAGE_BASE + rdata_rva + strings_offset + value
                 for key, value in str_offsets.items()}
    addresses.update({('iat', name): IMAGE_BASE + idata_rva + iat_offset + idx*4
                      for idx, name in enumerate(IMPORTS)})
    code = a.finish(addresses)

    rsrc_rva = align(idata_rva + len(idata), ALIGN)
    tlb = (BOOT / 'McgsInternalBridge.tlb').read_bytes()
    if not 256 <= len(tlb) <= 65536 or tlb[:4] != b'MSFT':
        raise ValueError('Expected bounded own MSFT type library')
    stable = (BOOT / 'McgsInternalBridge.dll').read_bytes()
    if stable.count(tlb) != 1:
        raise ValueError('Own DLL must contain the exact current type-library bytes once')
    identity = sources['cold_com_identity']
    if identity is not None:
        metadata = json.loads((BOOT / 'bootstrap-embedded-typelib.json').read_text(encoding='utf-8-sig'))
        coclasses = [row for row in metadata['types'] if row['kind'] == 'TKIND_COCLASS']
        interfaces = [row for row in metadata['types'] if row['name'] == 'IAddInObj']
        if (str(uuid.UUID(metadata['guid'])).upper() != identity['type_library_guid'] or
                len(coclasses) != 1 or coclasses[0]['name'] != identity['coclass_name'] or
                str(uuid.UUID(coclasses[0]['guid'])).upper() != identity['class_guid'] or
                len(interfaces) != 1 or str(uuid.UUID(interfaces[0]['guid'])).upper() != identity['interface_guid']):
            raise ValueError('Compiled TYPELIB identity differs from this deployment')
        for key in ('type_library_guid', 'class_guid', 'interface_guid'):
            if uuid.UUID(identity[key]).bytes_le not in tlb:
                raise ValueError('Current TYPELIB omits its deployment GUID: ' + key)
    # Root named type TYPELIB -> numeric name 1 -> language 0 -> data.
    rsrc = bytearray(104)
    struct.pack_into('<IIHHHH', rsrc, 0, 0, 0, 0, 0, 1, 0)
    struct.pack_into('<II', rsrc, 16, 0x80000000 | 88, 0x80000000 | 24)
    struct.pack_into('<IIHHHH', rsrc, 24, 0, 0, 0, 0, 0, 1)
    struct.pack_into('<II', rsrc, 40, 1, 0x80000000 | 48)
    struct.pack_into('<IIHHHH', rsrc, 48, 0, 0, 0, 0, 0, 1)
    struct.pack_into('<II', rsrc, 64, 0, 72)
    struct.pack_into('<4I', rsrc, 72, rsrc_rva + 104, len(tlb), 0, 0)
    rsrc[88:104] = p16(7) + 'TYPELIB'.encode('utf-16le')
    rsrc.extend(tlb)

    reloc_rva = align(rsrc_rva + len(rsrc), ALIGN)
    blocks = {}
    for offset, target in a.absolute:
        site = text_rva + offset
        blocks.setdefault(site & ~0xfff, []).append(0x3000 | (site & 0xfff))
    reloc = bytearray()
    for page, offsets in sorted(blocks.items()):
        if len(offsets) & 1: offsets.append(0)
        reloc.extend(struct.pack('<II', page, 8 + len(offsets)*2))
        for offset in offsets: reloc.extend(p16(offset))

    sections = [('.text', text_rva, code, 0x60000020),
                ('.rdata', rdata_rva, bytes(rdata), 0x40000040),
                ('.idata', idata_rva, bytes(idata), 0xc0000040),
                ('.rsrc', rsrc_rva, bytes(rsrc), 0x40000040),
                ('.reloc', reloc_rva, bytes(reloc), 0x42000040)]
    header_size = align(0x80 + 4 + 20 + 224 + len(sections)*40, FILE_ALIGN)
    dos = bytearray(0x80); dos[:2] = b'MZ'; struct.pack_into('<I', dos, 0x3c, 0x80)
    coff = struct.pack('<HHIIIHH', 0x14c, len(sections), 0, 0, 0, 224, 0x2102)
    opt = bytearray(224)
    struct.pack_into('<HBB9I', opt, 0, 0x10b, 0, 0,
                     align(len(code), FILE_ALIGN),
                     sum(align(len(s[2]), FILE_ALIGN) for s in sections[1:]), 0,
                     text_rva + a.labels['DllMain'], text_rva, rdata_rva,
                     IMAGE_BASE, ALIGN, FILE_ALIGN)
    struct.pack_into('<6H', opt, 40, 6, 0, 0, 0, 6, 0)
    struct.pack_into('<4I', opt, 52, 0, align(reloc_rva + len(reloc), ALIGN), header_size, 0)
    struct.pack_into('<HH', opt, 68, 2, 0x140)  # GUI subsystem; ASLR + NX
    struct.pack_into('<6I', opt, 72, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    for directory, rva, size in [(0, rdata_rva, export_size), (1, idata_rva, 40),
                                  (2, rsrc_rva, len(rsrc)), (5, reloc_rva, len(reloc)),
                                  (12, idata_rva + iat_offset, (len(IMPORTS)+1)*4)]:
        struct.pack_into('<II', opt, 96 + directory*8, rva, size)
    headers = bytes(dos) + b'PE\0\0' + coff + bytes(opt)
    offset = header_size
    payload = bytearray()
    for name, rva, content, flags in sections:
        raw_size = align(len(content), FILE_ALIGN)
        headers += struct.pack('<8s6I2HI', name.encode('ascii'), len(content), rva,
                               raw_size, offset, 0, 0, 0, 0, flags)
        payload.extend(content.ljust(raw_size, b'\0')); offset += raw_size
    image = headers.ljust(header_size, b'\0') + payload
    output = HERE / WRAPPER_NAME
    output.write_bytes(image)
    report = {
        'schema': 1, 'status': 'built_not_loaded_or_registered', 'path': str(output),
        'sha256': sha(image), 'size': len(image), 'machine': 'I386/native PE32 DLL',
        'image_base': hex(IMAGE_BASE), 'aslr': True, 'nx': True, 'clr_header': False,
        'entry_rva': hex(text_rva + a.labels['DllMain']),
        'DllMain': {'return': 'TRUE', 'cleanup': 'ret 12', 'registry_work': False},
        'exports': {'DllRegisterServer': hex(text_rva + a.labels['DllRegisterServer'])},
        'registration_abi': 'x86 stdcall, no parameters, HRESULT in EAX, ret',
        'callee_saved': ['EBX', 'ESI', 'EDI', 'EBP'],
        'imports': ['advapi32.' + name for name in IMPORTS],
        'relocation_type': 'IMAGE_REL_BASED_HIGHLOW',
        'absolute_fixup_count': len(a.absolute),
        'relocation_sites': [hex(text_rva + o) for o, _ in a.absolute],
        'ownership_marker': MARKER, 'transaction_id': token,
        'registry_hive': 'HKLM', 'registry_view_flag': 'KEY_WOW64_32KEY (0x200)',
        'write_roots': ROOTS, 'expected_entries': entries, 'writes': writes,
        'protection': {
            'full_read_only_preflight_before_first_mutation': True,
            'existing_root_requires_exact_transaction_marker': True,
            'existing_planned_values_require_exact_type_length_and_bytes': True,
            'missing_roots_keys_values_may_be_created': True,
            'each_value_rechecked_before_write': True,
            'unplanned_values_or_keys_untouched': True,
            'failure_rollback': False,
            'partial_failure_note': 'Failure after writes may leave partial own registration; no existing mismatching value is overwritten. Parent must verify after smoke.',
            'concurrency_note': 'No global registry transaction; host experiment must prevent concurrent registration writers.'},
        'error_contract': {'Win32_failure': 'HRESULT_FROM_WIN32(original LSTATUS)',
                           'unowned_root': '0x80070005',
                           'mismatching_existing_value': '0x8007000D',
                           'close_on_error': 'preserve original status while closing current open hKey'},
        'typelib': {'type': 'TYPELIB', 'name': 1, 'language': 0,
                    'size': len(tlb), 'sha256': sha(tlb)},
        'sources': sources, 'labels_rva': {k: hex(text_rva+v) for k,v in a.labels.items()},
        'code_sha256': sha(code), 'registry_api_executed_by_builder': False,
        'bridge_or_vendor_callback_invoked': False, 'deployed': False,
    }
    (HERE / 'build-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['path','sha256','size','absolute_fixup_count','status']}, ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap-root', required=True)
    parser.add_argument('--registration-contract', required=True)
    args=parser.parse_args()
    BOOT=Path(args.bootstrap_root).resolve()
    HERE=BOOT/'native-wrapper'
    CONTRACT=Path(args.registration_contract).resolve()
    if not BOOT.is_dir() or not CONTRACT.is_file():raise ValueError('Prepare explicit bootstrap and registration contract first')
    HERE.mkdir(exist_ok=False)
    build()
