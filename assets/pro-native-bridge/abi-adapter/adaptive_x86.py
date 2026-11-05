"""Anchored x86 adaptation after the exact portable signature did not match.

This is not a fuzzy whole-image search.  A named export, proved RTTI slot, or
surviving caller role must first identify the candidate.  It preserves ordinary
member displacements, widths, stack operations and ABI-visible registers.  It
never manufactures mappings for changed diagnostic strings or an unproved
callee merely because its caller was identified.
"""
from __future__ import annotations

import copy
import struct


_SAVED = frozenset(('ebx', 'esi', 'edi'))
_FULL_GPR = frozenset(('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'esp', 'ebp'))
_SAVED_PARTS = {'bx': 'ebx', 'bl': 'ebx', 'bh': 'ebx', 'si': 'esi', 'di': 'edi'}
_IDENTITIES = frozenset(('named-export', 'rtti-slot', 'proven-caller-role'))
_WRITE_ONLY = frozenset(('mov', 'movzx', 'movsx', 'movsxd', 'lea'))


def _identity(proof, rva):
    return (isinstance(proof, dict) and proof.get('kind') in _IDENTITIES
            and proof.get('independent') is True and proof.get('actual_rva') == rva
            and isinstance(proof.get('proof_id'), str) and bool(proof['proof_id']))


def _normalized_token(token):
    mnemonic, operands = token['mnemonic'], copy.deepcopy(token['operands'])
    if mnemonic in ('nop', 'endbr32'):
        return None, 'padding-or-entry-marker'
    if mnemonic in ('mov', 'xchg') and len(operands) == 2:
        if operands[0] == operands[1] and operands[0][0] == 'reg' and operands[0][1] in _FULL_GPR and operands[0][2] == 4:
            return None, 'GPR-self-move-or-exchange'
    if mnemonic == 'lea' and len(operands) == 2:
        dest, address = operands
        if (dest[0] == 'reg' and dest[2] == 4 and address[0] == 'mem'
                and address[1] is None and address[2] in _FULL_GPR
                and address[3] is None and address[4] == 1 and address[5] == 0):
            return {'mnemonic': 'mov', 'operands': [dest, ['reg', address[2], 4]]}, 'LEA-zero-offset-register-copy'
    return {'mnemonic': mnemonic, 'operands': operands}, None


def _canonical(signature):
    tokens, source_indexes, by_source, changes = [], [], {}, []
    for index, source in enumerate(signature['tokens']):
        token, reason = _normalized_token(source)
        if reason:
            changes.append({'instruction_index': index, 'kind': reason})
        if token is None:
            by_source[index] = None
            continue
        if _import_transfer(signature, index) is not None:
            token = {'mnemonic': token['mnemonic'], 'operands': [['import-transfer', None, 4]]}
            changes.append({'instruction_index': index, 'kind': 'import-backed-transfer-form'})
        by_source[index] = len(tokens)
        tokens.append(token)
        source_indexes.append(index)
    return {'tokens': tokens, 'source_indexes': source_indexes, 'by_source': by_source, 'changes': changes}


def _indirect_import(signature, index):
    token = signature['tokens'][index]
    if token['mnemonic'] not in ('call', 'jmp') or len(token['operands']) != 1:
        return None
    operand = token['operands'][0]
    if operand[0] != 'mem' or operand[1] is not None or operand[2] is not None or operand[3] is not None or operand[5] is not None or operand[6] != 4:
        return None
    rows = [row for row in signature['relocations'] if row['instruction_index'] == index]
    return rows[0]['import'] if len(rows) == 1 and rows[0].get('import') else None


def _import_transfer(signature, index):
    direct = _indirect_import(signature, index)
    if direct:
        return direct
    transfer = next((row for row in signature['transfers'] if row['instruction_index'] == index), None)
    if transfer is None or transfer.get('target_context_status') != 'complete':
        return None
    chain = transfer.get('target_signature_chain')
    if not chain or any(not row['first_is_direct_thunk'] for row in chain[:-1]):
        return None
    last = chain[-1]
    substantial = [position for position, token in enumerate(last['tokens']) if _normalized_token(token)[0] is not None]
    if len(substantial) != 1 or last['tokens'][substantial[0]]['mnemonic'] != 'jmp':
        return None
    return _indirect_import(last, substantial[0])


def _terminal(signature):
    if not signature['tokens']:
        return False
    return signature['tokens'][-1]['mnemonic'] in ('ret', 'retf', 'iret', 'iretd', 'jmp')


def _decode(actual_pe, rva, wanted):
    import x86_signature as xs
    section = actual_pe.section_for_rva(rva)
    if section is None or not section.executable:
        return None
    remaining = section.raw_size - (rva - section.rva)
    if remaining <= 0:
        return None
    # Grow only while real decoded padding consumes the inspected span.  The
    # section extent, not a sample-specific number of padding bytes, bounds IO.
    span = min(remaining, max(15, wanted * 15))
    while True:
        try:
            current = xs.decode_signature(actual_pe, rva, span)
            xs.attach_reference_contexts(actual_pe, current)
        except (ValueError, struct.error):
            return None
        normalized = _canonical(current)
        if len(normalized['tokens']) >= wanted or _terminal(current) or span == remaining:
            return current
        # INT3/undecodable bytes are executable behavior, never discarded as
        # padding.  decode_signature stopped before them and cannot grow past.
        if current['match_length'] < span:
            return current
        span = min(remaining, span * 2)


def _effective_thunk(signature):
    normalized = _canonical(signature)
    if len(normalized['tokens']) != 1 or normalized['tokens'][0]['mnemonic'] != 'jmp':
        return None
    index = normalized['source_indexes'][0]
    return next((item for item in signature['transfers']
                 if item['instruction_index'] == index and item['kind'] == 'jump'), None)


def _actual_body(actual_pe, rva, wanted):
    current, visited, chain = rva, set(), []
    while current not in visited:
        visited.add(current)
        model = _decode(actual_pe, current, wanted)
        if model is None:
            return None
        transfer = _effective_thunk(model)
        if transfer is None:
            return model, current, chain
        target = transfer['reference_target_rva']
        if not actual_pe.is_executable(target):
            return None
        chain.append({'entry_rva': current, 'target_rva': target})
        current = target
    return None


def _register_pair(reference, actual, forward, reverse):
    if reference in _SAVED and actual in _SAVED:
        if reference in forward and forward[reference] != actual:
            return False
        if actual in reverse and reverse[actual] != reference:
            return False
        forward[reference], reverse[actual] = actual, reference
        return True
    if reference in _SAVED_PARTS or actual in _SAVED_PARTS:
        if reference != actual:
            return False
        # A fixed partial alias also fixes its entire containing register.
        return _register_pair(_SAVED_PARTS[reference], _SAVED_PARTS[actual], forward, reverse)
    # EAX return, ECX this, EDX fastcall arguments, ESP/EBP, segments and all
    # partial/SIMD/FPU registers keep their explicit observed roles.
    return reference == actual


def _operand_pair(reference, actual, forward, reverse):
    if not isinstance(reference, list) or not isinstance(actual, list) or len(reference) != len(actual) or reference[0] != actual[0]:
        return False
    kind = reference[0]
    if kind == 'reg':
        return reference[2:] == actual[2:] and _register_pair(reference[1], actual[1], forward, reverse)
    if kind == 'mem':
        # segment, scale, displacement and access width must stay exact.  Only
        # the already-constrained general register names can be substituted.
        return (reference[1] == actual[1] and reference[4:] == actual[4:]
                and _register_pair(reference[2], actual[2], forward, reverse)
                and _register_pair(reference[3], actual[3], forward, reverse))
    return reference == actual


def _reads_and_writes(token):
    mnemonic, operands = token['mnemonic'], token['operands']
    reads, writes = set(), set()
    zero = (mnemonic in ('xor', 'sub') and len(operands) == 2
            and operands[0] == operands[1] and operands[0][0] == 'reg'
            and operands[0][2] == 4)
    for index, operand in enumerate(operands):
        if operand[0] == 'mem':
            reads.update(reg for reg in operand[2:4] if reg in _SAVED)
        elif operand[0] == 'reg' and operand[1] in _SAVED:
            register = operand[1]
            if zero or index == 0 and (mnemonic in _WRITE_ONLY or mnemonic == 'pop'):
                writes.add(register)
            else:
                reads.add(register)
                if index == 0 and mnemonic not in ('push', 'cmp', 'test', 'call', 'jmp'):
                    writes.add(register)
    return reads, writes


def _register_lifetimes(signature, canonical, mapping, used):
    """Must-defined on every reachable prefix path, including loop backedges.

    Renaming is unavailable when a jump leaves this supplied CFG: an unseen
    block might restore an entry value and re-enter a known read.  Calls keep
    normal callee-saved register semantics, and no whole-function proof is
    inferred from this prefix analysis.
    """
    renamed = {name for name, other in mapping.items() if name != other}
    if not renamed:
        return True
    tokens = canonical['tokens'][:used]
    jumps = _by_canonical([row for row in signature['transfers'] if row['kind'] == 'jump'], canonical, used)
    successors = [set() for _ in tokens]
    reads_by_node, writes_by_node, restored_by_node = [], [], []
    for index, token in enumerate(tokens):
        reads, writes = _reads_and_writes(token)
        # Saving an arbitrary entry value is legitimate.  Using that value as
        # a custom hidden argument is not proved by a register permutation.
        saving = token['mnemonic'] == 'push' and len(token['operands']) == 1 and token['operands'][0][0] == 'reg'
        reads_by_node.append(set() if saving else reads & renamed)
        restored_by_node.append(writes & renamed if token['mnemonic'] == 'pop' else set())
        writes_by_node.append(set() if token['mnemonic'] == 'pop' else writes & renamed)
        transfers = jumps.get(index, [])
        if transfers:
            for transfer in transfers:
                target = _target_index(signature, canonical, transfer['reference_target_rva'], used)
                if target is None:
                    return False
                successors[index].add(target)
            if token['mnemonic'] not in ('jmp', 'ljmp') and index + 1 < used:
                successors[index].add(index + 1)
        elif token['mnemonic'] in ('jmp', 'ljmp'):
            # Indirect jump destinations cannot be invented from a prefix.
            return False
        elif token['mnemonic'] not in ('ret', 'retf', 'iret', 'iretd') and index + 1 < used:
            successors[index].add(index + 1)
    reachable, pending = set(), [0]
    while pending:
        node = pending.pop()
        if node in reachable:
            continue
        reachable.add(node)
        pending.extend(successors[node] - reachable)
    predecessors = [set() for _ in tokens]
    for node in reachable:
        for target in successors[node]:
            predecessors[target].add(node)
    # A must analysis starts at top for non-entry nodes.  It only removes
    # facts to a fixed point; loop definitions cannot create an entry fact.
    incoming = [set(renamed) for _ in tokens]
    outgoing = [set(renamed) for _ in tokens]
    incoming[0] = set()
    changed = True
    while changed:
        changed = False
        for node in sorted(reachable):
            if node == 0:
                before = set()
            elif predecessors[node]:
                before = set.intersection(*(outgoing[parent] for parent in predecessors[node]))
            else:
                before = set()
            after = (before - restored_by_node[node]) | writes_by_node[node]
            if before != incoming[node] or after != outgoing[node]:
                incoming[node], outgoing[node], changed = before, after, True
    for node in reachable:
        if reads_by_node[node] - incoming[node]:
            return False
    return True


def _pair_tokens(reference, actual):
    left, right = _canonical(reference), _canonical(actual)
    wanted = len(left['tokens'])
    if not wanted or len(right['tokens']) < wanted:
        return None
    forward, reverse = {}, {}
    for source, target in zip(left['tokens'], right['tokens']):
        if source['mnemonic'] != target['mnemonic'] or len(source['operands']) != len(target['operands']):
            return None
        if not all(_operand_pair(a, b, forward, reverse) for a, b in zip(source['operands'], target['operands'])):
            return None
    if not _register_lifetimes(reference, left, forward, wanted):
        return None
    if not _register_lifetimes(actual, right, reverse, wanted):
        return None
    changed = {key for key, value in forward.items() if key != value}
    if changed:
        old_implicit = _implicit_saved(reference, set(left['source_indexes']))
        new_implicit = _implicit_saved(actual, set(right['source_indexes'][:wanted]))
        if old_implicit is None or new_implicit is None:
            return None
        if old_implicit & changed or new_implicit & {forward[key] for key in changed}:
            return None
    return left, right, forward


def _implicit_saved(signature, selected):
    import x86_signature as xs
    try:
        instructions = list(xs.decoder().disasm(bytes.fromhex(signature['bytes_hex']), signature['reference_rva']))
    except (ValueError, struct.error):
        return None
    if len(instructions) != len(signature['tokens']):
        return None
    return {ins.reg_name(register) for index, ins in enumerate(instructions) if index in selected
            for register in tuple(ins.regs_read) + tuple(ins.regs_write)
            if ins.reg_name(register) in _SAVED}


def _target_index(signature, canonical, target, used):
    try:
        raw_index = signature['instruction_offsets'].index(target - signature['reference_rva'])
    except ValueError:
        return None
    # A branch landing on a removed NOP runs the next substantive instruction.
    while raw_index < len(signature['tokens']):
        current = canonical['by_source'][raw_index]
        if current is not None:
            return current if current < used else None
        raw_index += 1
    return None


def _by_canonical(rows, canonical, used):
    result = {}
    for row in rows:
        index = canonical['by_source'].get(row['instruction_index'])
        if index is not None and index < used:
            result.setdefault(index, []).append(row)
    for entries in result.values():
        entries.sort(key=lambda item: item.get('byte_offset_in_instruction', 0))
    return result


def _rtti_match(reference, actual):
    if not isinstance(reference, dict) or not isinstance(actual, dict):
        return None
    # A missing ctor displacement is a missing layout fact, not zero.  Catalog
    # regeneration or an explicit complete type proof supplies that fact.
    if 'constructor_displacement_offset' not in reference or 'constructor_displacement_offset' not in actual:
        return None
    if reference == actual:
        return {'kind': 'exact-RTTI-vtable-operand'}
    import rtti
    proof = rtti.anchor_role_proof(reference, actual)
    return {'kind': 'proved-RTTI-object-interface-role', 'role': proof} if proof else None


def _strict_chain(actual_pe, reference, target):
    import x86_signature as xs
    chain = reference.get('target_signature_chain')
    if reference.get('target_context_status') != 'complete' or not chain:
        return None
    current, seen, referents, evidence = target, set(), [], []
    for index, part in enumerate(chain):
        if current in seen:
            return None
        seen.add(current)
        matched = xs.local_match(part, actual_pe, current)
        context = xs.verify_context(None, actual_pe, part, matched, part['reference_rva'], current, verify_targets=False) if matched else None
        if context is None:
            return None
        referents.extend(context['referents'])
        evidence.extend(context['normalization_proofs'])
        if index + 1 < len(chain):
            if not matched['first_is_direct_thunk']:
                return None
            current = matched['transfers'][0]['reference_target_rva']
    if chain[-1]['first_is_direct_thunk']:
        return None
    return {'referents': referents, 'normalization_proofs': evidence}


def _anchored_chain(actual_pe, reference, target, *, external_identity):
    """Check a changed branch prefix as part of an already anchored caller.

    This contributes control-path evidence, not a standalone function/address
    mapping.  The locator must validate any emitted candidate against that
    function's own complete supplied signature before publishing an address.
    """
    chain = reference.get('target_signature_chain')
    if reference.get('target_context_status') != 'complete' or not chain:
        return None
    current, seen, evidence = target, set(), []
    for index, part in enumerate(chain):
        if current in seen:
            return None
        seen.add(current)
        wanted = len(_canonical(part)['tokens'])
        source_thunk = _effective_thunk(part)
        if source_thunk is not None:
            actual = _decode(actual_pe, current, wanted)
            body_rva, wrappers = current, []
        else:
            found = _actual_body(actual_pe, current, wanted)
            if found is None:
                return None
            actual, body_rva, wrappers = found
        if actual is None:
            return None
        paired = _pair_tokens(part, actual)
        context = _context(part, actual_pe, actual, paired, external_identity=external_identity, verify_targets=False) if paired else None
        if context is None:
            return None
        evidence.extend(context['normalization_proofs'])
        if wrappers:
            evidence.append({'kind': 'anchored-branch-entry-thunks', 'actual_thunks': wrappers, 'actual_body_rva': body_rva})
        if index + 1 < len(chain):
            actual_thunk = _effective_thunk(actual)
            if source_thunk is None or actual_thunk is None:
                return None
            current = actual_thunk['reference_target_rva']
    if _effective_thunk(chain[-1]) is not None:
        return None
    return {'normalization_proofs': evidence, 'standalone_address_mapping_proved': False}


def _observed_string(pe, rva, encoding):
    section = pe.section_for_rva(rva)
    if section is None or section.executable:
        return None
    remaining = section.raw_size - (rva - section.rva)
    if remaining <= 0:
        return None
    raw = pe.read(rva, remaining)
    if encoding == 'ascii':
        end = raw.find(b'\0')
        if end < 0 or any(not (32 <= value < 127 or value in (9, 10, 13)) for value in raw[:end]):
            return None
        return {'encoding': encoding, 'bytes_hex': raw[:end + 1].hex()}
    if encoding == 'utf-16le':
        end = next((index for index in range(0, len(raw) - 1, 2) if raw[index:index + 2] == b'\0\0'), None)
        if end is None:
            return None
        try:
            value = raw[:end].decode(encoding)
        except UnicodeError:
            return None
        if any(not (char.isprintable() or char in '\t\r\n') for char in value):
            return None
        return {'encoding': encoding, 'bytes_hex': raw[:end + 2].hex()}
    return None


def _context(reference, actual_pe, actual, paired, *, external_identity, verify_targets=True):
    import x86_signature as xs
    left, right, register_map = paired
    used = len(left['tokens'])
    old_relocs = _by_canonical(reference['relocations'], left, used)
    new_relocs = _by_canonical(actual['relocations'], right, used)
    referents, candidates, evidence, observations = [], [], [], []
    import_indexes = set()
    for index in range(used):
        source_import = _import_transfer(reference, left['source_indexes'][index])
        actual_import = _import_transfer(actual, right['source_indexes'][index])
        if source_import is None and actual_import is None:
            continue
        role = xs.import_symbol_match(source_import, actual_import, actual_pe)
        if role is None:
            return None
        import_indexes.add(index)
        evidence.append({'kind': 'same-import-transfer-role-across-encoding', 'instruction_index': index,
            'identity_proof': role, 'cross-module_wrapper_address_mapping_emitted': False})
    old_relocs = {key: value for key, value in old_relocs.items() if key not in import_indexes}
    new_relocs = {key: value for key, value in new_relocs.items() if key not in import_indexes}
    if set(old_relocs) != set(new_relocs):
        return None
    for index, refs in old_relocs.items():
        found = new_relocs[index]
        if len(refs) != len(found):
            return None
        for source, target in zip(refs, found):
            old, new = source['reference_target_rva'], target['reference_target_rva']
            if old is None or new is None:
                return None
            if source.get('import'):
                role = xs.import_symbol_match(source['import'], target.get('import'), actual_pe)
                if role is None:
                    return None
                detail = {'kind': role}
            elif source.get('RTTI_vtable_anchor'):
                detail = _rtti_match(source['RTTI_vtable_anchor'], target.get('RTTI_vtable_anchor'))
                if detail is None:
                    return None
                role = detail['kind']
            elif source.get('string_anchor'):
                expected_encoding = source['string_anchor']['encoding']
                string = target.get('string_anchor') or _observed_string(actual_pe, new, expected_encoding)
                if not string or source['string_anchor']['encoding'] != string['encoding']:
                    return None
                if source['string_anchor'] != string:
                    if not external_identity:
                        return None
                    observations.append({'kind': 'changed-string-content-under-independent-function-role',
                        'instruction_index': index, 'string_address_mapping_emitted': False})
                    # Localized text can change without changing the entry ABI.
                    # Its address is not a correspondence for another reader.
                    continue
                role, detail = 'exact-string-reference', {'kind': 'exact-string-reference'}
            else:
                if target.get('import') or target.get('RTTI_vtable_anchor') or target.get('string_anchor'):
                    return None
                if source['reference_target_executable'] != actual_pe.is_executable(new):
                    return None
                if source['reference_target_executable']:
                    candidates.append({'reference_rva': old, 'actual_rva': new, 'kind': 'code-reference',
                        'operand_role': 'aligned-unverified-code-pointer-candidate',
                        'instruction_index': source['instruction_index'],
                        'reference_site_rva': source['reference_site_rva'], 'actual_site_rva': target['reference_site_rva']})
                    continue
                role, detail = 'same-decoded-HIGHLOW-operand', {'kind': 'same-decoded-HIGHLOW-operand'}
            referents.append({'reference_rva': old, 'actual_rva': new, 'kind': 'operand-reference',
                'operand_role': role, 'instruction_index': source['instruction_index'],
                'reference_site_rva': source['reference_site_rva'], 'actual_site_rva': target['reference_site_rva']})
            evidence.append({**detail, 'instruction_index': index})
    old_transfers = _by_canonical(reference['transfers'], left, used)
    new_transfers = _by_canonical(actual['transfers'], right, used)
    old_transfers = {key: value for key, value in old_transfers.items() if key not in import_indexes}
    new_transfers = {key: value for key, value in new_transfers.items() if key not in import_indexes}
    if set(old_transfers) != set(new_transfers):
        return None
    for index, refs in old_transfers.items():
        found = new_transfers[index]
        if len(refs) != len(found):
            return None
        for source, target in zip(refs, found):
            if source['mnemonic'] != target['mnemonic'] or source['kind'] != target['kind']:
                return None
            old, new = source['reference_target_rva'], target['reference_target_rva']
            local = _target_index(reference, left, old, used)
            if source['inside_signature_offset'] is not None:
                if local is None or _target_index(actual, right, new, used) != local:
                    return None
                evidence.append({'kind': 'same-canonical-local-basic-block', 'instruction_index': index,
                    'reference_target_rva': old, 'actual_target_rva': new})
                continue
            if not actual_pe.is_executable(new):
                return None
            if not verify_targets:
                observations.append({'kind': 'nested-branch-prefix-only', 'instruction_index': index,
                    'standalone_address_mapping_emitted': False})
                continue
            body = _strict_chain(actual_pe, source, new)
            if body is None:
                branch = _anchored_chain(actual_pe, source, new, external_identity=external_identity) if external_identity else None
                if branch is not None:
                    evidence.extend(branch['normalization_proofs'])
                    evidence.append({'kind': 'anchored-canonical-branch-context', 'instruction_index': index,
                        'standalone_address_mapping_emitted': False})
                    candidates.append({'reference_rva': old, 'actual_rva': new, 'kind': 'code-reference',
                        'operand_role': 'aligned-unverified-transfer-candidate',
                        'instruction_index': source['instruction_index'],
                        'reference_site_rva': reference['reference_rva'] + source['instruction_offset'],
                        'actual_site_rva': actual['reference_rva'] + target['instruction_offset']})
                    continue
                if source['kind'] != 'call' or not external_identity:
                    # Tail/conditional branch behavior is part of this entry's
                    # control path.  It does not receive the callee exception.
                    return None
                observations.append({'kind': 'callee-body-context-differs-under-independent-caller-role',
                    'instruction_index': index, 'callee_address_mapping_emitted': False})
                candidates.append({'reference_rva': old, 'actual_rva': new, 'kind': 'code-reference',
                    'operand_role': 'aligned-unverified-transfer-candidate',
                    'instruction_index': source['instruction_index'],
                    'reference_site_rva': reference['reference_rva'] + source['instruction_offset'],
                    'actual_site_rva': actual['reference_rva'] + target['instruction_offset']})
                continue
            referents.extend(body['referents'])
            evidence.extend(body['normalization_proofs'])
            referents.append({'reference_rva': old, 'actual_rva': new, 'kind': 'code-reference',
                'operand_role': 'branch-target-body-signature', 'instruction_index': source['instruction_index']})
            evidence.append({'kind': 'branch-target-body-signature', 'instruction_index': index,
                'reference_target_rva': old, 'actual_target_rva': new})
    changes = [{'side': 'reference', **item} for item in left['changes']]
    changes += [{'side': 'actual', **item} for item in right['changes']
                if right['by_source'].get(item['instruction_index']) is None
                or right['by_source'].get(item['instruction_index'], used) < used]
    changed_regs = {key: value for key, value in register_map.items() if key != value}
    if changed_regs:
        changes.append({'kind': 'defined-callee-saved-register-permutation', 'mapping': changed_regs,
            'entry_values_not_used_as_hidden_arguments': True, 'ABI_visible_registers_preserved': True,
            'definition_analysis': 'reachable-CFG-must-defined-predecessor-intersection'})
    evidence.extend(changes)
    evidence.extend(observations)
    return {'normalization_proofs': evidence, 'referents': referents, 'candidate_referents': candidates,
            'observations': observations, 'register_mapping': changed_regs}


def match(reference, actual_pe, rva, *, identity_proof):
    """Return matched current bytes/context, or None; never choose a candidate.

    The caller validates identity uniqueness and surviving proof dependencies.
    Actual code guards must still be emitted from the selected current PE.
    A prefix correspondence does not assert whole-function call semantics.
    """
    if not _identity(identity_proof, rva) or not actual_pe.is_executable(rva):
        return None
    source, reference_thunks = reference, []
    transfer = _effective_thunk(reference)
    if transfer is not None:
        chain = transfer.get('target_signature_chain')
        if transfer.get('target_context_status') != 'complete' or not chain or chain[-1]['first_is_direct_thunk']:
            return None
        source = chain[-1]
        reference_thunks = [reference['reference_rva']] + [part['reference_rva'] for part in chain[:-1]]
    wanted = len(_canonical(source)['tokens'])
    decoded = _actual_body(actual_pe, rva, wanted)
    if decoded is None:
        return None
    actual, body_rva, actual_thunks = decoded
    paired = _pair_tokens(source, actual)
    if paired is None:
        return None
    allow_context_changes = identity_proof['kind'] in ('named-export', 'proven-caller-role')
    context = _context(source, actual_pe, actual, paired, external_identity=allow_context_changes)
    if context is None:
        return None
    if reference_thunks or actual_thunks:
        context['normalization_proofs'].append({'kind': 'independently-anchored-entry-thunk-chain',
            'reference_entry_rva': reference['reference_rva'], 'reference_body_rva': source['reference_rva'],
            'actual_entry_rva': rva, 'actual_body_rva': body_rva,
            'reference_thunk_entries': reference_thunks, 'actual_thunks': actual_thunks})
        if source['reference_rva'] != reference['reference_rva']:
            context['candidate_referents'].append({'reference_rva': source['reference_rva'],
                'actual_rva': body_rva, 'kind': 'code-reference',
                'operand_role': 'aligned-unverified-entry-body-candidate', 'instruction_index': 0})
    evidence = {'kind': 'anchored-x86-structural-adaptation',
        'identity': copy.deepcopy(identity_proof), 'reference_rva': reference['reference_rva'],
        'actual_rva': rva, 'reference_body_rva': source['reference_rva'], 'actual_body_rva': body_rva,
        'ordinary_member_offsets_and_widths_preserved': True,
        'stack_and_visible_return_instructions_preserved': True,
        'ABI_entry_and_return_registers_preserved': True,
        'callee_saved_entry_values_not_remapped_as_arguments': True,
        'register_definition_analysis': 'reachable-CFG-must-defined-predecessor-intersection',
        'context_changes_require_named_export_or_proved_caller': True,
        'context_relaxation_identity': identity_proof['kind'] if allow_context_changes else None,
        'whole_function_call_semantics_proved': False,
        'reference_semantic_instruction_count': len(paired[0]['tokens']),
        'actual_inspected_bytes': actual['match_length'],
        'unproved_string_or_callee_address_mappings_emitted': False}
    return {'actual': actual, 'context': context, 'evidence': evidence}
