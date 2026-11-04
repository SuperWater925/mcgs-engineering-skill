"""Static PE/file evidence only. Never loads or calls the editor."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2]
sys.path.insert(0, str(TASK.parent / '20261101_Pro实时工程接口深查/static'))
from pe_reader import StaticPE


def main():
    pe = StaticPE(r'C:\unbound-install-root\Program\McgsSetPro.exe')
    relocs = [pe.base + x.rva for b in pe.pe.DIRECTORY_ENTRY_BASERELOC
              for x in b.entries if x.type == 3]
    def cfg(entry):
        body = pe.resolve(entry)[0]
        pending, seen, calls = [body], {}, []
        while pending:
            pc = pending.pop()
            if pc in seen:
                continue
            if not body <= pc < body + 0x4000 or len(seen) >= 5000:
                raise ValueError('Static CFG exceeded explicit bound ' + hex(body))
            i = next(pe.cs.disasm(pe.at(pc, 16), pc))
            seen[pc] = dict(va=hex(pc), bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str)
            if i.mnemonic.startswith('ret') or i.mnemonic in ('int3', 'ud2'):
                continue
            if i.mnemonic == 'call':
                c = dict(site=hex(pc), operand=i.op_str)
                if i.op_str.startswith('0x'):
                    c['resolved'] = hex(pe.resolve(int(i.op_str, 0))[0])
                calls.append(c)
            if i.mnemonic.startswith('j'):
                if not i.op_str.startswith('0x'):
                    raise ValueError('Unresolved local jump ' + hex(pc))
                dest = int(i.op_str, 0)
                if body <= dest < body + 0x4000:
                    pending.append(dest)
                else:
                    calls.append(dict(site=hex(pc), tail_target=hex(dest)))
                if i.mnemonic == 'jmp':
                    continue
            pending.append(pc + i.size)
        n = 32
        while any(body <= r < body + n and r + 4 > body + n for r in relocs):
            n = max(n, max(r + 4 - body for r in relocs if body <= r < body + n))
        return dict(entry_va=hex(entry), body_va=hex(body), body_rva=hex(body-pe.base),
                    normal_code=[seen[x] for x in sorted(seen)], calls=calls,
                    prefix_hex=pe.at(body,n).hex(),
                    prefix_relocations=[r-body for r in relocs if body <= r < body+n],
                    exception_unwind_not_part_of_normal_cfg=True)
    roots = {
        'PropertyManager_Ctor': 0xE43CA0, 'PropertyManager_Dtor': 0xE44430,
        'Aux_Ctor': 0xE43720, 'Aux_HashCtor': 0xE42210,
        'Aux_ListCtor': 0xE43410, 'Aux_ListCtorWrapper': 0xE424A0,
        'Aux_ListCtorInitialize': 0xE423E0, 'Aux_ListZero': 0xE42960,
        'Aux_SentinelAllocate': 0xE48400, 'Aux_Dtor': 0xE43E50,
        'Aux_GroupRecords': 0xE4F040, 'Aux_IndexByTag': 0xE459D0,
        'Aux_IndexByKey': 0xE458B0, 'Aux_AppendRecordPointer': 0xE36AB0,
        'Aux_Clear': 0xE4F300, 'Manager_Reset': 0xE4FCF0,
        'Manager_PruneThenClear': 0xE4E4A0, 'Manager_ApplyThenClear': 0xE4E770,
        'Color_Collector': 0xE54150, 'Int_Collector': 0xE54640,
        'Scalar_RecordStore': 0xE3D630, 'Scalar_TypeValidation': 0xE55680,
        'Scalar_OwnerKeyIndex': 0xE515B0, 'OwnerMappedValueCtor': 0xE43BB0,
    }
    functions = {name: cfg(va) for name, va in roots.items()}
    text = pe.pe.sections[0]
    text_va, raw = pe.base + text.VirtualAddress, text.get_data()
    def refs(targets, opcode):
        return [dict(site=hex(text_va+i), target=hex(text_va+i+5+struct.unpack_from('<i', raw, i+1)[0]))
                for i,b in enumerate(raw[:-4]) if b == opcode
                and text_va+i+5+struct.unpack_from('<i', raw, i+1)[0] in targets]
    thunks = refs({0xE4F040}, 0xE9)
    targets = {0xE4F040} | {int(x['site'],0) for x in thunks}
    direct_calls = refs(targets, 0xE8)
    absolute_refs = []
    for r in relocs:
        v = struct.unpack('<I', pe.at(r,4))[0]
        if v in targets:
            absolute_refs.append(dict(site=hex(r), value=hex(v)))
    assert thunks == [dict(site='0x42d254', target='0xe4f040')]
    assert direct_calls == [dict(site='0xe2c5bb', target='0x42d254')]
    assert not absolute_refs
    rows = list(pe.cs.disasm(pe.at(0xE40000, 0x16000), 0xE40000))
    hits = []
    for n,i in enumerate(rows):
        if ((i.mnemonic == 'add' and i.op_str.endswith(', 0x2c')) or
                (i.mnemonic == 'lea' and '+ 0x2c]' in i.op_str)):
            if 'ebp' in i.op_str or 'esp' in i.op_str:
                continue
            hits.append(dict(va=hex(i.address), instruction=i.mnemonic+' '+i.op_str,
                             context=[dict(va=hex(x.address), instruction=x.mnemonic+' '+x.op_str)
                                      for x in rows[max(0,n-7):n+7]]))
    assert [x['va'] for x in hits] == ['0xe43d10','0xe44460','0xe4e6b1','0xe4e892','0xe4f1c4','0xe4fd0c']
    closure_source = HERE.parent / 'generic-map-destruction-normal-cfg-0002.json'
    report = dict(
        purpose='Second PropertyManager container +0x2c: independent static closure after actual47 rejection',
        editor=dict(path=str(pe.path), preferred_base=hex(pe.base), sha256=hashlib.sha256(pe.raw).hexdigest()),
        source_file=str(Path(__file__).resolve()), source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        runtime_accessed=False, vendor_loaded=False, engineering_write=False, native_call_count=0,
        findings=dict(
            auxiliary_member_offset='0x2c', container_size='0x20',
            constructed_empty=dict(ctor='0xe43ca0 -> 0xe43720 -> 0xe42210 -> 0xe43410 -> 0xe424a0 -> 0xe423e0',
                                   zero_site='0xe42973', count_offset=4, sentinel_member_offset=0),
            observed_role='Explicit grouped index: native tag DWORD -> native converted key string -> vector of scalar-record pointers',
            grouping_call='0xe4f040, one direct text caller 0xe2c5bb through thunk 0x42d254',
            grouping_pointer_flow=dict(tag_address='inner pair +0x1c', key_address='inner pair',
                                       scalar_record_address='inner pair +0x18', vector_stride=4),
            scalar3_legal_expected_aux_count=0,
            reason='The selected inherited base getter invokes color/int collector -> record store -> type validation and main owner/key indexing. It does not invoke the explicit group-index builder.',
            main_inner_map_correction='Vendor independent formal-accessor proof places main owner inner map at owner node +0x10, not +0x0c; this report does not relax any count.',
            scope_limit='Six +0x2c address formations exhaust the explicitly scanned class-method interval [0xe40000,0xe56000). This is not a claim that all possible aliases or exception paths of the entire application were proved.'),
        scan_interval=[hex(0xE40000),hex(0xE56000)], auxiliary_address_formations=hits,
        grouping_references=dict(thunks=thunks,direct_calls=direct_calls,absolute_highlow_refs=absolute_refs),
        functions=functions,
        original_destructor_normal_cfg_reference=dict(file=str(closure_source),sha256=hashlib.sha256(closure_source.read_bytes()).hexdigest()),
        diagnostic_requirements=[
            'Capture raw primary/secondary table pointers and each map header address/head/count before checking its expected count.',
            'Report main owner mapped-value address, its raw first DWORD, and corrected inner-map address separately.',
            'If a header is readable, capture sentinel next/prev and validate symmetry only within explicit count bounds.',
            'Set a distinct own-record-header-copy phase before structural checks, retaining raw diagnostics through cleanup failures.',
            'Do not read freed old47 pointers or replay its consumed first-schema-miss claim; cached-schema scope requires a new independently pinned contract.'])
    out = HERE / 'pm-aux-map-static-closure-0001.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(file=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                          functions=len(functions),address_formations=len(hits),aux_expected_count=0),ensure_ascii=False))


if __name__ == '__main__':
    main()
