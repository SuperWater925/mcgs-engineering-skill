"""Instruction-aware x86 signatures. Never masks ordinary object displacements.

Only PE HIGHLOW locations and decoded direct branch immediates are normalized.
A JMP thunk is identified through its terminal body/import, not an E9 wildcard.
No native code is loaded or called.
"""
from __future__ import annotations
import struct
import bisect
from collections import defaultdict
from pe32 import import_identity

try:
    import capstone
    from capstone import x86_const as x86
except ImportError as exc:
    raise ImportError('The ABI preparer needs capstone 5.x in this same Python; install requirements.txt. No separate environment is required.') from exc

DECODER_VERSION = capstone.__version__


def relocation_range(pe, start, end, *, intersecting=False):
    ordered = getattr(pe, '_abi_ordered_relocations', None)
    if ordered is None:
        ordered = sorted(pe.relocations)
        pe._abi_ordered_relocations = ordered
    # Instruction models require whole operands. A byte guard instead needs
    # every HIGHLOW word touching its window, including a truncated tail.
    first, last = (start - 3, end - 1) if intersecting else (start, end - 4)
    return ordered[bisect.bisect_left(ordered, first):bisect.bisect_right(ordered, last)]


def import_symbol_match(reference, actual, pe=None):
    """Compare symbol identity; a named import's lookup hint is not identity.

    Ordinal changes and renamed DLLs need a selected logical dependency plus
    a named export or a uniquely proven current export body. Exact unresolved
    ordinal imports retain their ordinal and DLL checks.
    """
    if not isinstance(reference, dict) or not isinstance(actual, dict):
        return None
    same_dll = reference.get('dll', '').casefold() == actual.get('dll', '').casefold()
    named = reference.get('name') is not None
    if named and import_identity(reference) == import_identity(actual):
        return 'named-import-symbol'
    role = reference.get('export_role')
    if role:
        if pe is None:
            return None
        dependencies = getattr(pe, '_abi_import_dependencies', {})
        imported = dependencies.get(actual.get('dll', '').casefold())
        if imported and imported[0] == role['module']:
            alias, target = imported
            current = (target.exports.get(actual.get('name')) if actual.get('name') is not None else
                       target.exports_by_ordinal.get(actual.get('ordinal')))
            if current and not current.get('forwarder') and current.get('rva'):
                names = role.get('names', [])
                if any(target.exports.get(name, {}).get('rva') == current['rva'] and
                       not target.exports[name].get('forwarder') for name in names):
                    return 'selected-dependency-named-export-role'
                proven = getattr(pe, '_abi_import_role_targets', {}).get((alias, role['reference_rva']), set())
                if len(proven) == 1 and current['rva'] in proven:
                    return 'selected-dependency-proven-export-body'
        # A cataloged ordinal role cannot fall back to the old ordinal number
        # after the dependency changed; the export target must be proved.
        return None
    if same_dll and not named and reference.get('ordinal') is not None and import_identity(reference) == import_identity(actual):
        return 'exact-ordinal-import-symbol'
    return None


def decoder():
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    return md


def available(pe, rva, wanted):
    section = pe.section_for_rva(rva)
    if section is None:
        return b''
    count = min(wanted, section.raw_size - (rva - section.rva))
    return pe.read(rva, count) if count > 0 else b''


def type_anchor(pe, rva):
    cache = getattr(pe, '_abi_type_reference_cache', None)
    if cache is None:
        cache = {};pe._abi_type_reference_cache = cache
    if rva not in cache:
        try:
            import rtti
            model = rtti.describe_vtable(pe, rva)
            cache[rva] = {'decorated_name': model['decorated_name'], 'col_offset': model['col_offset'],
                'bases': [[b['decorated_name'], b['contained'], b['pmd'], b['attributes']] for b in model['hierarchy']['bases']]}
        except (ValueError, struct.error):
            cache[rva] = None
    return cache[rva]


def string_anchor(pe, rva):
    """Only a complete readable string is an anchor, never a pointer guess."""
    section = pe.section_for_rva(rva)
    if section is None or section.executable:
        return None
    raw = available(pe, rva, 512)
    nul = raw.find(b'\0')
    if 4 <= nul < len(raw) and all(32 <= c < 127 for c in raw[:nul]):
        return {'encoding': 'ascii', 'bytes_hex': raw[:nul + 1].hex()}
    for end in range(8, len(raw) - 1, 2):
        if raw[end:end + 2] == b'\0\0':
            try:
                value = raw[:end].decode('utf-16le')
            except UnicodeError:
                break
            if value and all(c.isprintable() for c in value):
                return {'encoding': 'utf-16le', 'bytes_hex': raw[:end + 2].hex()}
            break
    return None


def decode_signature(pe, rva, guard_length=32):
    if not pe.is_executable(rva):
        raise ValueError('Signature address is not in an executable PE section')
    guard = pe.read(rva, guard_length)
    data = available(pe, rva, guard_length + 15)
    instructions = []
    match_end = 0
    # End at RET/JMP/INT3: bytes from an adjacent function are not identity.
    for ins in decoder().disasm(data, rva):
        offset = ins.address - rva
        if offset >= guard_length:
            break
        if offset != match_end:
            raise ValueError('x86 decoding did not preserve instruction boundaries')
        if ins.id == x86.X86_INS_INT3:
            break
        instructions.append(ins)
        match_end = offset + ins.size
        if ins.group(capstone.CS_GRP_RET) or ins.id == x86.X86_INS_JMP:
            break
    if not instructions or match_end < 1:
        raise ValueError('Insufficient complete x86 instructions for identity')
    mask = bytearray(b'\xff' * match_end)
    raw = pe.read(rva, match_end)
    tokens, relocations, transfers = [], [], []
    for index, ins in enumerate(instructions):
        off = ins.address - rva
        local_relocs = [site - ins.address for site in relocation_range(pe, ins.address, ins.address + ins.size)]
        for loc in local_relocs:
            mask[off + loc:off + loc + 4] = bytes(4)
            va = struct.unpack_from('<I', raw, off + loc)[0]
            try:
                target = pe.va_to_rva(va)
            except ValueError:
                target = None
            imports = pe.imports_by_iat.get(target) if target is not None else None
            if imports:
                imports = {**imports, 'dll': imports['dll'].lower()}
            relocations.append({'instruction_index': index, 'instruction_offset': off,
                'byte_offset_in_instruction': loc, 'reference_site_rva': ins.address + loc,
                'reference_target_rva': target, 'reference_value': va,
                'reference_target_executable': pe.is_executable(target) if target is not None else None,
                'RTTI_vtable_anchor': type_anchor(pe, target) if target is not None and not pe.is_executable(target) else None,
                'import': imports, 'string_anchor': string_anchor(pe, target) if target is not None else None})
        direct = (ins.group(capstone.CS_GRP_JUMP) or ins.group(capstone.CS_GRP_CALL)) and any(
            op.type == x86.X86_OP_IMM for op in ins.operands)
        if direct:
            start, size = ins.imm_offset, ins.imm_size
            if not size or start + size > ins.size:
                raise ValueError('Decoded branch has no complete immediate encoding')
            mask[off + start:off + start + size] = bytes(size)
            target = next(op.imm & 0xffffffff for op in ins.operands if op.type == x86.X86_OP_IMM)
            transfers.append({'instruction_index': index, 'instruction_offset': off,
                'immediate_offset': start, 'immediate_size': size, 'reference_target_rva': target,
                'mnemonic': ins.mnemonic, 'kind': 'jump' if ins.group(capstone.CS_GRP_JUMP) else 'call',
                'inside_signature_offset': target - rva if rva <= target < rva + match_end else None})
        operands = []
        for op in ins.operands:
            if op.type == x86.X86_OP_REG:
                operands.append(['reg', ins.reg_name(op.reg), op.size])
            elif op.type == x86.X86_OP_IMM:
                operands.append(['branch' if direct else 'absolute' if ins.imm_offset in local_relocs else 'imm',
                                 None if direct or ins.imm_offset in local_relocs else op.imm, op.size])
            elif op.type == x86.X86_OP_MEM:
                mem = op.mem
                is_absolute = ins.disp_offset in local_relocs
                # ecx/esi + field offsets remain exact numeric values.
                operands.append(['mem', ins.reg_name(mem.segment), ins.reg_name(mem.base), ins.reg_name(mem.index),
                                 mem.scale, None if is_absolute else mem.disp, op.size])
            else:
                operands.append(['other', op.type, op.size])
        tokens.append({'mnemonic': ins.mnemonic, 'operands': operands})
    return {'reference_rva': rva, 'guard_length': guard_length, 'match_length': match_end,
            'bytes_hex': raw.hex(), 'mask_hex': bytes(mask).hex(), 'tokens': tokens,
            'instruction_offsets': [ins.address - rva for ins in instructions],
            'relocations': relocations, 'transfers': transfers,
            'first_is_direct_thunk': bool(instructions[0].id == x86.X86_INS_JMP and transfers and transfers[0]['instruction_index'] == 0)}


def attach_reference_contexts(pe, signature):
    """Keep only sparse branch/body signatures, so no reference PE is deployed."""
    for transfer in signature['transfers']:
        if transfer['inside_signature_offset'] is not None:
            continue
        target, seen, chain = transfer['reference_target_rva'], set(), []
        try:
            while True:
                if target in seen:
                    raise ValueError('Reference thunk chain loops')
                seen.add(target)
                part = decode_signature(pe, target, 24)
                chain.append(part)
                if not part['first_is_direct_thunk']:
                    break
                target = part['transfers'][0]['reference_target_rva']
            transfer['target_signature_chain'] = chain
            transfer['target_context_status'] = 'complete'
        except (ValueError, struct.error) as exc:
            transfer['target_signature_chain'] = chain
            transfer['target_context_status'] = 'unresolved'
            transfer['target_context_reason'] = str(exc)
    return signature


def longest_literal(signature):
    raw, mask = bytes.fromhex(signature['bytes_hex']), bytes.fromhex(signature['mask_hex'])
    best, current = (0, b''), 0
    for i in range(len(mask) + 1):
        if i < len(mask) and mask[i] == 255:
            continue
        if i - current > len(best[1]):
            best = (current, raw[current:i])
        current = i + 1
    return best


def candidates(pe, signature, anchors=(), *, prefix_fallback=False):
    if anchors:
        return sorted({int(rva) for rva in anchors if pe.is_executable(int(rva))})
    offset, literal = longest_literal(signature)
    if prefix_fallback:
        raw, mask = bytes.fromhex(signature['bytes_hex']), bytes.fromhex(signature['mask_hex'])
        first_mask = next((i for i, b in enumerate(mask) if b != 255), len(mask))
        offset, literal = 0, raw[:first_mask]
    if not literal:
        return []
    result = set()
    for section, data in pe.iter_regions(executable=True):
        pos = data.find(literal)
        while pos >= 0:
            start = section.rva + pos - offset
            if section.rva <= start and start + signature['match_length'] <= section.rva + section.raw_size:
                result.add(start)
            pos = data.find(literal, pos + 1)
    return sorted(result)


def actual_instructions(pe, rva, count):
    # A decoded instruction is at most15 bytes. Count derives from the supplied
    # signature, not an arbitrary old sample limit.
    return list(decoder().disasm(available(pe, rva, max(15, count * 15)), rva, count=count))


def local_match(reference, actual_pe, rva):
    """Match exact nonaddress operands, including every ordinary field offset."""
    try:
        actual = decode_signature(actual_pe, rva, max(reference['guard_length'], reference['match_length']) + 15)
    except (ValueError, struct.error):
        return None
    wanted = reference['tokens']
    if len(actual['tokens']) < len(wanted) or actual['tokens'][:len(wanted)] != wanted:
        # A longer first RET path can end later; compare exactly the same number
        # of instructions with the same instruction-aware token rules.
        return None
    return actual


def verify_context(reference_pe, actual_pe, reference, actual, reference_rva, actual_rva, *, verify_targets=True):
    """Prove branch/thunk and absolute reference roles in the matched instructions.

    Nested target body anchors are compared once; this is an identity proof,
    not inferred object layout or an asserted calling convention.
    """
    evidence, refs = [], []
    actual_reloc = {(r['instruction_index'], r['byte_offset_in_instruction']): r for r in actual['relocations']}
    for ref in reference['relocations']:
        key = (ref['instruction_index'], ref['byte_offset_in_instruction'])
        got = actual_reloc.get(key)
        if got is None or got['reference_target_rva'] is None or ref['reference_target_rva'] is None:
            return None
        old, new = ref['reference_target_rva'], got['reference_target_rva']
        if ref.get('import'):
            role = import_symbol_match(ref['import'], got.get('import'), actual_pe)
            if role is None:
                return None
        elif ref.get('RTTI_vtable_anchor'):
            if ref['RTTI_vtable_anchor'] != got.get('RTTI_vtable_anchor'):
                return None
            role = 'exact-RTTI-vtable-operand'
        elif ref.get('string_anchor'):
            if ref['string_anchor'] != got.get('string_anchor'):
                return None
            role = 'exact-string-reference'
        else:
            # Both targets must have the same code/data section role. Ordinary
            # object displacements were already compared in the instruction.
            if ref['reference_target_executable'] != actual_pe.is_executable(new):
                return None
            role = 'same-decoded-HIGHLOW-operand'
        refs.append({'reference_rva': old, 'actual_rva': new, 'kind': 'operand-reference',
                     'operand_role': role, 'instruction_index': ref['instruction_index'],
                     'reference_site_rva': ref['reference_site_rva'], 'actual_site_rva': got['reference_site_rva']})
        evidence.append({'kind': role, 'instruction_index': ref['instruction_index']})
    actual_transfers = {row['instruction_index']: row for row in actual['transfers']}
    for ref in reference['transfers']:
        got = actual_transfers.get(ref['instruction_index'])
        if got is None or got['mnemonic'] != ref['mnemonic'] or got['kind'] != ref['kind']:
            return None
        old, new = ref['reference_target_rva'], got['reference_target_rva']
        if ref['inside_signature_offset'] is not None:
            # Instruction lengths can differ for short/near branches, so use
            # the target instruction index rather than a byte displacement.
            new_instructions = actual_instructions(actual_pe, actual_rva, len(reference['tokens']))
            old_index = next((i for i, offset in enumerate(reference['instruction_offsets']) if reference_rva + offset == old), None)
            if old_index is None or old_index >= len(new_instructions) or new_instructions[old_index].address != new:
                return None
            role = 'same-local-basic-block'
        else:
            if not verify_targets:
                continue
            if not actual_pe.is_executable(new):
                return None
            chain = ref.get('target_signature_chain')
            if not chain and reference_pe is not None:
                attach_reference_contexts(reference_pe, reference)
                chain = ref.get('target_signature_chain')
            if ref.get('target_context_status') != 'complete' or not chain:
                return None
            visited_new = set()
            for part_index, target_signature in enumerate(chain):
                if new in visited_new:
                    return None
                visited_new.add(new)
                try:
                    target = local_match(target_signature, actual_pe, new)
                except (ValueError, struct.error):
                    return None
                if target is None:
                    return None
                nested = verify_context(None, actual_pe, target_signature, target,
                    target_signature['reference_rva'], new, verify_targets=False)
                if nested is None:
                    return None
                refs.extend(nested['referents'])
                if part_index + 1 < len(chain):
                    if not target['first_is_direct_thunk']:
                        return None
                    new = target['transfers'][0]['reference_target_rva']
            if chain[-1]['first_is_direct_thunk']:
                return None
            role = 'branch-target-body-signature'
            refs.append({'reference_rva': ref['reference_target_rva'], 'actual_rva': got['reference_target_rva'],
                         'kind': 'code-reference', 'operand_role': role, 'instruction_index': ref['instruction_index']})
        evidence.append({'kind': role, 'instruction_index': ref['instruction_index'],
                         'reference_target_rva': ref['reference_target_rva'], 'actual_target_rva': got['reference_target_rva']})
    return {'normalization_proofs': evidence, 'referents': refs}


def normalized_guard_bytes(pe, rva, length, reference_preferred_base):
    """Preserve existing C# HIGHLOW delta semantics without double rebasing."""
    data = bytearray(pe.read(rva, length))
    positions = []
    for site in relocation_range(pe, rva, rva + length, intersecting=True):
        off = site - rva
        # Read the complete source word, rebase once, then restore only bytes
        # present in the guard. Packing into the short guard loses trailing
        # HIGHLOWs or extends its length, both of which change the contract.
        value = struct.unpack('<I', pe.read(site, 4))[0]
        canonical = struct.pack('<I', (value - pe.image_base + reference_preferred_base) & 0xffffffff)
        first, last = max(0, off), min(length, off + 4)
        data[first:last] = canonical[first - off:last - off]
        positions.append(off)
    return bytes(data), positions
