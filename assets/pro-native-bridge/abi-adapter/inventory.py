"""Inventory reference ABI inputs without loading an editor or changing profiles.

This is a lexical inventory, not a C# compiler or an ABI compatibility proof.
Every finding retains its source location and an explicit interpretation kind.
Object-layout and ambiguous numeric findings must not be treated as PE RVAs.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import subprocess


SCHEMA = 'mcgs-native-abi-inventory/v1'
SOURCE = 'assets/pro-native-bridge/delivery/source'
SHA = re.compile(r'^[a-fA-F0-9]{64}$')
HEX = re.compile(r'^[a-fA-F0-9]+$')
INT = re.compile(r'(?<![\w.])(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:[uUlL]{0,2})(?![\w.])')
HEXLITERAL = re.compile(r'(?<![\w.])0[xX][0-9a-fA-F]+(?:[uUlL]{0,2})(?![\w.])')
CALL = re.compile(r'\b(?:(?:[A-Za-z_]\w*\.)*Address|IntPtr\.Add|new\s+IntPtr|'
                  r'NativeMemory\.(?:Add|Ptr|I32|U32|U16|I16|U8|Bytes|Readable)|'
                  r'Marshal\.(?:ReadInt32|ReadInt64|ReadIntPtr|ReadInt16|ReadByte|'
                  r'WriteInt32|WriteInt64|WriteIntPtr|WriteInt16|WriteByte)|'
                  r'Path\.Combine)\s*\(')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def text_line(starts, offset):
    return bisect_right(starts, offset)


def snippet(value, limit=240):
    value = re.sub(r'\s+', ' ', value).strip()
    return value if len(value) <= limit else value[:limit] + '...'


def literal_value(raw):
    if raw.startswith('@"'):
        return raw[2:-1].replace('""', '"')
    body = raw[1:-1]
    escapes = {'0': '\0', 'a': '\a', 'b': '\b', 'f': '\f', 'n': '\n',
               'r': '\r', 't': '\t', 'v': '\v', '\\': '\\', '"': '"', "'": "'"}
    def replace(match):
        value = match.group(1)
        if value[0] in ('u', 'U', 'x'):
            return chr(int(value[1:], 16))
        return escapes.get(value, '\\' + value)
    return re.sub(r'\\(u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|x[0-9a-fA-F]{1,4}|.)', replace, body)


def mask_csharp(text):
    """Keep all offsets/line breaks while masking comments, strings and chars."""
    output = list(text); strings = []; at = 0
    def blank(begin, end):
        for index in range(begin, end):
            if text[index] not in '\r\n': output[index] = ' '
    while at < len(text):
        begin = at
        if text.startswith('//', at):
            end = text.find('\n', at); at = len(text) if end < 0 else end
        elif text.startswith('/*', at):
            end = text.find('*/', at + 2); at = len(text) if end < 0 else end + 2
        elif text.startswith('@"', at):
            at += 2
            while at < len(text):
                if text.startswith('""', at): at += 2
                elif text[at] == '"': at += 1; break
                else: at += 1
            strings.append((begin, at, literal_value(text[begin:at])))
        elif text[at] in ('"', "'"):
            quote = text[at]; at += 1
            while at < len(text):
                if text[at] == '\\': at += 2
                elif text[at] == quote: at += 1; break
                else: at += 1
            if quote == '"': strings.append((begin, at, literal_value(text[begin:at])))
        else:
            at += 1; continue
        blank(begin, min(at, len(text)))
    return ''.join(output), strings


def arguments(masked, opening):
    depth = 0; start = opening + 1; parts = []
    for at in range(opening, len(masked)):
        char = masked[at]
        if char in '([{': depth += 1
        elif char in ')]}':
            depth -= 1
            if depth == 0:
                parts.append((start, at)); return at + 1, parts
        elif char == ',' and depth == 1:
            parts.append((start, at)); start = at + 1
    return None, []


def numeric(value):
    value = re.sub(r'[uUlL]+$', '', value.strip())
    try: return int(value, 16 if value.lower().startswith('0x') else 10)
    except ValueError: return None


def csharp_inventory(name, raw):
    text = raw.decode('utf-8-sig'); masked, strings = mask_csharp(text)
    starts = [0] + [match.end() for match in re.finditer('\n', text)]
    findings = []; capabilities = []; profile_literals = []
    for match in CALL.finditer(masked):
        opening = masked.find('(', match.start()); end, ranges = arguments(masked, opening)
        if end is None: continue
        call = re.sub(r'\s+', ' ', masked[match.start():opening].strip())
        args = [text[a:b].strip() for a, b in ranges]
        base = args[0] if args else ''
        if call.endswith('.Address') or call == 'Address':
            kind = 'pe_rva_entry'; policy = 'module-aware reference-to-actual RVA map'
        elif call in ('IntPtr.Add', 'NativeMemory.Add'):
            module = bool(re.search(r'ImageBase|ModuleBase|module|preferredBase|\.Address\(', base, re.I))
            kind = 'module_add_candidate' if module else 'object_or_owned_buffer_offset'
            policy = 'resolve module RVA only after base ownership proof' if module else 'requires separate object-layout or owned-buffer classification'
        elif call == 'new IntPtr':
            kind = 'pointer_or_ordinal_constructor'; policy = 'do not remap ordinals, handles, sentinels or actual pointers'
        elif call == 'Path.Combine':
            if '.json' not in text[match.start():end]: continue
            kind = 'profile_path_expression'; policy = 'resolve profile by task-relative key and attested content digest'
        else:
            kind = 'native_field_or_buffer_access'; policy = 'field/layout proof required; not a PE RVA'
        literals = []
        for index, (a, b) in enumerate(ranges):
            for token in INT.finditer(masked[a:b]):
                literals.append({'argument': index, 'literal': token.group(), 'integer': numeric(token.group()), 'start': a + token.start(), 'end': a + token.end()})
        findings.append({'kind': kind, 'line': text_line(starts, match.start()), 'offset': match.start(),
                         'call': call, 'arguments': [snippet(arg) for arg in args], 'argument_spans': [{'start': a, 'end': b} for a, b in ranges],
                         'numeric_literals': literals, 'rewrite_policy': policy,
                         'source': snippet(text[match.start():end])})
    for begin, end, value in strings:
        preceding = masked[max(0, begin - 180):begin]
        declaration = re.search(r'\b([A-Za-z_]\w*)\s*=\s*$', preceding)
        symbol = declaration.group(1) if declaration else None
        row = {'line': text_line(starts, begin), 'offset': begin, 'symbol': symbol}
        if SHA.fullmatch(value):
            findings.append(dict(row, kind='sha256_literal_candidate', value=value,
                                 rewrite_policy='link digest to its actual profile/module; never forge observed hashes'))
        elif value.startswith('.?AV') or value.startswith('.?AU'):
            findings.append(dict(row, kind='native_RTTI_name', value=value,
                                 rewrite_policy='match actual RTTI and validate associated COL/vtable/layout'))
        if value.lower().endswith('.json'):
            profile_literals.append(dict(row, value=value.replace('\\', '/')))
        if symbol in ('Kind', 'ReadOp', 'ExecuteOp') or symbol and symbol.endswith('Kind'):
            capabilities.append(dict(row, value=value))
    for match in HEXLITERAL.finditer(masked):
        value = numeric(match.group()); before = masked[max(0, match.start() - 100):match.start()]
        declaration = re.search(r'\b([A-Za-z_]\w*)\s*=\s*$', before)
        kind = 'unclassified_hex_constant'
        if value in (0xff, 0xffff, 0xffffffff, 0x7fffffff): kind = 'mask_or_sentinel_candidate'
        elif value == 0x400000: kind = 'preferred_PE_base_candidate'
        elif value is not None and value >= 0x10000: kind = 'RVA_VA_capacity_or_ID_candidate'
        findings.append({'kind': kind, 'line': text_line(starts, match.start()), 'offset': match.start(),
                         'literal': match.group(), 'integer': value,
                         'symbol': declaration.group(1) if declaration else None,
                         'context': snippet(text[max(0, match.start() - 65):match.end() + 65]),
                         'rewrite_policy': 'lexical candidate only; never apply a numeric-wide substitution'})
    counts = Counter(row['kind'] for row in findings)
    return {'file': name, 'sha256': digest(raw), 'line_count': len(starts), 'finding_counts': dict(counts),
            'entrypoint_exposure': 'not proven by this lexical inventory', 'capability_literals': capabilities,
            'profile_filename_literals': profile_literals,
            'findings': sorted(findings, key=lambda row: (row['offset'], row['kind']))}


def pointer(parts):
    return '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts)


def profile_kind(parts, value):
    key = str(parts[-1]).lower() if parts else ''; joined = '/'.join(map(str, parts)).lower()
    if 'sha' in key or 'digest' in key:
        vendor = bool(re.search(r'binary|editor|executable|mfc|driver|common|loaded_module', joined))
        return 'vendor_identity_hash' if vendor else 'owned_profile_or_other_digest'
    if 'rtti' in key or key == 'class_name' and isinstance(value, str) and value.startswith('.?'):
        return 'RTTI_bytes_or_name'
    if any(token in key for token in ('reloc', 'highlow')): return 'PE_relocation_description'
    if 'image_base' in key or 'preferred_base' in key: return 'preferred_PE_image_base'
    if 'rva' in key: return 'PE_RVA'
    if key in ('va', 'va_at_preferred_base', 'address', 'start_va', 'end_va'):
        return 'VA_or_address_candidate'
    if any(token in key for token in ('expected_first', 'bytes', 'prefix_hex', 'signature_hex')):
        return 'native_code_or_serialized_bytes'
    if 'offset' in key or 'offsets/' in joined: return 'object_code_or_serialization_offset_candidate'
    if '/slots/' in joined: return 'vtable_slot_value_candidate'
    if key in ('vtable', 'col', 'type_descriptor', 'methods', 'functions'):
        return 'native_table_or_method_description'
    if key in ('calling_convention', 'args', 'return', 'abi') or '/abi/' in joined:
        return 'native_call_signature'
    if key in ('size', 'sizeof', 'stride', 'object_size', 'image_size') or 'size_of' in key:
        return 'object_buffer_or_PE_size_candidate'
    return None


def value_summary(value):
    if isinstance(value, str) and HEX.fullmatch(value) and len(value) > 128:
        return {'hex_byte_count': len(value) // 2, 'encoded_text_sha256': digest(value.encode('ascii'))}
    if isinstance(value, str) and len(value) > 400:
        return {'character_count': len(value), 'utf8_sha256': digest(value.encode('utf-8'))}
    return value


def artifact_inventory(relative, raw):
    row = {'file': relative, 'sha256': digest(raw), 'format': Path(relative).suffix,
           'capability_resolution': 'not performed; this is reference inventory only'}
    if row['format'] != '.json':
        row['role'] = 'owned source/evidence, not a JSON profile'; return row
    data = json.loads(raw.decode('utf-8-sig')); shapes = defaultdict(set); fields = []; modules = set(); export_ordinals = []
    stack = [((), (), data)]
    while stack:
        parts, shape_parts, value = stack.pop(); kind = type(value).__name__
        shapes[pointer(shape_parts)].add(kind)
        semantic = profile_kind(parts, value)
        if semantic and not isinstance(value, (dict, list)):
            fields.append({'pointer': pointer(parts), 'shape_pointer': pointer(shape_parts),
                           'kind': semantic, 'value': value_summary(value)})
        if isinstance(value, str) and re.search(r'\.(?:dll|exe)$', value, re.I):
            modules.add(PureWindowsPath(value.replace('/', '\\')).name)
        if isinstance(value, dict):
            if type(value.get('ordinal')) is int and 'rva' in value:
                module=value.get('module')
                if module is None and 'mfc' in (str(p).lower() for p in parts): module='mfc110u.dll'
                address=value['rva'] if type(value['rva']) is int else numeric(value['rva']) if isinstance(value['rva'],str) else None
                if isinstance(module,str) and address is not None:
                    export_ordinals.append({'module':module,'ordinal':value['ordinal'],'rva':address,'pointer':pointer(parts)})
            for key, child in reversed(list(value.items())):
                stack.append((parts + (key,), shape_parts + (key,), child))
        elif isinstance(value, list):
            for index in reversed(range(len(value))):
                stack.append((parts + (index,), shape_parts + ('*',), value[index]))
    schema = {key: sorted(types) for key, types in sorted(shapes.items())}
    row.update({'declared_schema': data.get('schema') if isinstance(data, dict) else None,
                'schema_shape_sha256': digest(json.dumps(schema, sort_keys=True).encode()),
                'schema_shape': schema, 'module_basename_hints': sorted(modules),
                'field_kind_counts': dict(Counter(field['kind'] for field in fields)),
                'semantic_fields': fields, 'declared_export_ordinals':export_ordinals})
    return row


def source_address_catalog(sources, artifacts, source_texts):
    """Exact rewrite spans with conservative PE-address syntax evidence."""
    editor_rvas = set()
    for artifact in artifacts:
        for field in artifact.get('semantic_fields', []):
            if field['kind'] != 'PE_RVA' or '/mfc/' in field['pointer'].lower(): continue
            value = field['value']; number = value if type(value) is int else numeric(value) if isinstance(value, str) else None
            if number is not None: editor_rvas.add(number)
    def module_alias(name):
        name = PureWindowsPath(name).name.lower()
        return 'editor' if name == 'mcgssetpro.exe' else 'mfc' if re.fullmatch(r'mfc\d+u?\.dll', name) else 'common' if name == 'common.dll' else name
    body_regions=defaultdict(list)
    def module_base(expression, text, position=None):
        if re.fullmatch(r'(?:\w+\.)*(?:ImageBase|imageBase)', expression): return 'editor'
        handle = re.fullmatch(r'GetModuleHandle(?:W|A)?\("([^"]+)"\)', expression)
        if handle: return module_alias(handle.group(1))
        if re.fullmatch(r'\w+',expression) and position is not None:
            # A locally assigned handle before the exact use, with no later
            # assignment in this lexical block. This covers generic "module"
            # variables without assuming all variables named module are MFC.
            regions=[(a,b) for a,b in body_regions[id(text)] if a<=position<b]
            start=max((a for a,b in regions),default=text.rfind('{',0,position)+1)
            prefix=text[start:position]
            writes=list(re.finditer(r'\b'+re.escape(expression)+r'\s*=\s*(?!=)',prefix))
            if writes:
                assigned=re.match(r'GetModuleHandle(?:W|A)?\("([^"]+)"\)',prefix[writes[-1].end():])
                if assigned:return module_alias(assigned.group(1))
                indexed_assignment=re.match(r'(?:modules|handles|bases)\["([^"]+)"\]',prefix[writes[-1].end():])
                if indexed_assignment and ('GetModuleHandleW(' in text or 'Process.GetCurrentProcess().Modules' in text):return module_alias(indexed_assignment.group(1))
        indexed = re.fullmatch(r'(?:modules|handles|bases)\["([^"]+)"\]', expression)
        if indexed and ('GetModuleHandleW(' in text or 'Process.GetCurrentProcess().Modules' in text): return module_alias(indexed.group(1))
        if re.fullmatch(r'(?:\w+\.)*(?:Mfc|mfc)', expression):
            # Explicit local field/module assignment, or the same partial Api's
            # Mfc field whose constructor assigns modules["mfc110u.dll"].
            local = re.search(r'\b(?:Mfc|mfc)\s*=\s*(?:\w+\.BaseAddress|GetModuleHandleW\(|modules\["mfc\d+u?\.dll"\])', text)
            origin = re.search(r'\[\s*"mfc"\s*\]|mfc\d+u?\.dll', text)
            partial = 'partial class NativeUsableDeviceBatch' in text and any('Mfc=modules["mfc110u.dll"]' in other for other in source_texts.values())
            if (local and origin) or partial: return 'mfc'
        return None
    # Discover int-RVA wrappers from their bodies, then map only names/arity
    # whose definitions agree. For example Slot(obj,slot,rva) passes the third
    # argument to Engine.Address; the adjacent slot and object offsets do not.
    definitions = defaultdict(list); local_definitions=defaultdict(list); method_models=defaultdict(list)
    for filename, text in source_texts.items():
        masked, unused = mask_csharp(text)
        for method in re.finditer(r'\b([A-Za-z_]\w*)(?:<[^(){};]+>)?\s*\(', masked):
            opening = masked.find('(', method.start()); end, spans = arguments(masked, opening)
            if end is None: continue
            tail = re.match(r'\s*(?:where\s+[^{};]+)?\s*\{', masked[end:])
            if not tail: continue
            params = []
            for a, b in spans:
                param = re.fullmatch(r'\s*(?:(?:ref|out|params)\s+)?([\w.<>\[\],]+)\s+(\w+)\s*', masked[a:b])
                if not param: break
                params.append(param.groups())
            else:
                at = end + tail.end() - 1; depth = 1; stop = at + 1
                while stop < len(masked) and depth:
                    if masked[stop] == '{': depth += 1
                    elif masked[stop] == '}': depth -= 1
                    stop += 1
                if depth: continue
                body = text[at + 1:stop - 1]; body_mask = masked[at + 1:stop - 1]; bindings = {}
                body_regions[id(text)].append((at+1,stop-1))
                method_models[filename].append({'name':method.group(1),'params':params,'start':at+1,'end':stop-1,'body':body,'masked':body_mask})
                for index, (kind, symbol) in enumerate(params):
                    if kind not in ('int', 'uint'): continue
                    if re.search(r'(?:\bAddress|\b(?:\w+\.)*(?:Engine|engine|e)\.Address)\(\s*' + re.escape(symbol) + r'\s*\)', body_mask):
                        bindings[index] = ('editor', kind)
                    for call in re.finditer(r'\b(?:NativeMemory\.Add|IntPtr\.Add)\s*\(', body_mask):
                        op = body_mask.find('(', call.start()); unused_end, args = arguments(body_mask, op)
                        if len(args) == 2 and body_mask[args[1][0]:args[1][1]].strip() == symbol:
                            alias = module_base(body[args[0][0]:args[0][1]].strip(), text)
                            if alias: bindings[index] = (alias, kind)
                definitions[(method.group(1), len(params))].append(bindings)
                local_definitions[(filename,method.group(1),len(params))].append(bindings)
    wrappers = {}
    for key, candidates in definitions.items():
        common = {index: binding for index, binding in candidates[0].items()
                  if all(other.get(index) == binding for other in candidates)}
        if common and key[0] != 'Address': wrappers[key] = common
    local_wrappers={}
    for key,candidates in local_definitions.items():
        common={index:binding for index,binding in candidates[0].items() if all(other.get(index)==binding for other in candidates)}
        if common and key[1]!='Address':local_wrappers[key]=common
    # This comparator's four editor cursor RVAs are checked against guards by
    # name before Bind<T>; its body does not repeat the pointer arithmetic.
    trigger_extra = source_texts.get('assets/pro-native-bridge/delivery/source/sources/NativeStrategyTriggerContextEditing.cs', '') or source_texts.get('NativeStrategyTriggerContextEditing.cs', '')
    if 'T Extra<T>(string name,int rva)' in trigger_extra and 'N(guards[name],"rva")==rva' in trigger_extra:
        wrappers[('Extra', 2)] = {1: ('editor', 'int')}
    entries = {}; unresolved = []; ordinals = {}
    ordinal_targets=defaultdict(set)
    for artifact in artifacts:
        for row in artifact.get('declared_export_ordinals',[]):
            ordinal_targets[module_alias(row['module']),row['ordinal']].add(row['rva'])
    for source in sources:
        text = source_texts[source['file']]; masked, unused = mask_csharp(text); constants = defaultdict(list)
        for statement in re.finditer(r'\bconst\s+(?:int|uint|long|ulong)\s+([^;]+);', masked):
            for match in re.finditer(r'\b(\w+)\s*=\s*(0[xX][0-9a-fA-F]+|[0-9]+)([uUlL]{0,2})\b', statement.group(1)):
                start = statement.start(1) + match.start(2); end = statement.start(1) + match.end(2) + len(match.group(3))
                constants[match.group(1)].append((start, end, numeric(match.group(2))))
        def add(start, end, reference, module, kind, proof, call, value_type='int'):
            if reference is None or reference < 0x1000: return
            key = (source['file'], start, end)
            row = entries.setdefault(key, {'source': source['file'], 'source_sha256': source['sha256'],
                'start': start, 'end': end, 'original_literal': text[start:end], 'module': module,
                'address_kind': kind, 'reference_rva': reference, 'status': 'confirmed', 'proof': [], 'consumers': []})
            row['value_type'] = value_type
            if row['module'] != module or row['reference_rva'] != reference:
                row['status'] = 'ambiguous'; row['proof'].append('The same span has conflicting address interpretations')
            if proof not in row['proof']: row['proof'].append(proof)
            consumer = {'line': call['line'], 'call': call['call'], 'offset': call['offset']}
            if consumer not in row['consumers']: row['consumers'].append(consumer)
        variable_uses=[];field_uses=defaultdict(set)
        for call in source['findings']:
            if 'call' not in call: continue
            name = call['call']; args = call['arguments']; argument = None; module = None; proof = None
            if call['kind'] == 'pe_rva_entry' and (name == 'Address' or re.search(r'(?:^|\.)(?:Engine|engine|e)\.Address$', name)):
                argument = 0; module = 'editor'; proof = 'Literal/constant consumed by the known NativeEngine.Address RVA boundary'
            elif name in ('NativeMemory.Add', 'IntPtr.Add', 'NativeMemory.Ptr', 'NativeMemory.I32', 'NativeMemory.U32', 'NativeMemory.U16', 'NativeMemory.I16', 'NativeMemory.U8', 'Marshal.ReadInt32', 'Marshal.ReadIntPtr', 'Marshal.ReadInt16', 'Marshal.ReadByte') and len(args) > 1:
                module = module_base(args[0], text, call['offset'])
                if module:
                    argument = 1; proof = 'RVA consumed against a module base with explicit local module/partial-field ownership'
            if argument is not None and len(call['argument_spans']) > argument:
                span = call['argument_spans'][argument]; expression = text[span['start']:span['end']]
                if re.fullmatch(r'\s*[A-Za-z_]\w*\s*',expression):variable_uses.append((expression.strip(),module,call))
                member=re.fullmatch(r'\s*\w+\.(\w+)\s*',expression)
                if member:field_uses[member.group(1)].add(module)
                tokens = [token for token in call['numeric_literals'] if token['argument'] == argument]
                for token in tokens:
                    storage_access=name.startswith(('NativeMemory.Ptr','NativeMemory.I','NativeMemory.U','Marshal.Read'))
                    add(token['start'], token['end'], token['integer'], module, 'PE_data_RVA_literal' if storage_access else 'PE_RVA_literal', proof, call)
                for identifier in re.findall(r'\b[A-Za-z_]\w*\b', expression):
                    matches = constants.get(identifier, [])
                    if len(matches) == 1:
                        start, end, value = matches[0]
                        add(start, end, value, module, 'PE_RVA_constant', proof + '; unique const declaration in this source', call)
                    elif len(matches) > 1:
                        unresolved.append({'source': source['file'], 'line': call['line'], 'call': name,
                                           'reason': 'Multiple const declarations need a C# scope proof', 'symbol': identifier})
            elif name == 'new IntPtr':
                for token in call['numeric_literals']:
                    value = token['integer']
                    if value is not None and value >= 0x400000 and value - 0x400000 in editor_rvas:
                        add(token['start'], token['end'], value - 0x400000, 'editor', 'preferred_PE_VA_literal',
                            'Absolute pointer equals the reference preferred editor base plus a documented profile RVA', call)
            if call['kind'] == 'module_add_candidate' and argument is None:
                unresolved.append({'source': source['file'], 'line': call['line'], 'call': name,
                                   'base': args[0] if args else '', 'reason': 'Variable/parameter module ownership not proven by local syntax'})
        for call in re.finditer(r'\b((?:[A-Za-z_]\w*\.)*)([A-Za-z_]\w*)(?:<[^(){};]+>)?\s*\(', masked):
            opening = masked.find('(', call.start()); unused_end, spans = arguments(masked, opening)
            bindings = local_wrappers.get((source['file'],call.group(2),len(spans))) or wrappers.get((call.group(2), len(spans)))
            if not bindings: continue
            for index, (module, value_type) in bindings.items():
                a, b = spans[index]
                synthetic = {'line': text_line([0] + [m.end() for m in re.finditer('\n', text)], call.start()),
                             'call': call.group(1) + call.group(2), 'offset': call.start()}
                expression=masked[a:b].strip();member=re.fullmatch(r'\w+\.(\w+)',expression)
                if member:field_uses[member.group(1)].add(module)
                for token in INT.finditer(masked[a:b]):
                    add(a + token.start(), a + token.end(), numeric(token.group()), module, 'PE_RVA_literal',
                        'Integer argument of a native RVA wrapper whose same-name/arity definitions agree on the module boundary', synthetic, value_type)
                for identifier in re.findall(r'\b[A-Za-z_]\w*\b',masked[a:b]):
                    matches=constants.get(identifier,[])
                    if len(matches)==1:
                        first,last,value=matches[0]
                        add(first,last,value,module,'PE_RVA_constant',
                            'Unique integer const passed to a proven native RVA wrapper argument',synthetic,value_type)
                    elif len(matches)>1:
                        unresolved.append({'source':source['file'],'line':synthetic['line'],'call':synthetic['call'],
                                           'reason':'Wrapper const requires a C# scope proof','symbol':identifier})
        # Follow only local integer assignments whose value reaches a proven
        # module-relative boundary in the same method. Branches/switches are
        # included; ordinary object fields and arbitrary Number() results are
        # never reclassified.
        for symbol,module,consumer in variable_uses:
            owners=[m for m in method_models[source['file']] if m['start']<=consumer['offset']<m['end']]
            if not owners:continue
            method=max(owners,key=lambda m:m['start'])
            for assignment in re.finditer(r'\b'+re.escape(symbol)+r'\s*=\s*(0[xX][0-9a-fA-F]+|[0-9]+)([uUlL]{0,2})\s*;',method['masked']):
                start=method['start']+assignment.start(1);end=method['start']+assignment.end(1)+len(assignment.group(2))
                add(start,end,numeric(assignment.group(1)),module,'PE_RVA_literal','Local branch/switch integer assignment reaches a proven module RVA boundary in the same method',consumer)
        # A constructor can store address arguments in fields before the
        # fields reach Address()/a proven wrapper. Only the parameter->field
        # pairs with that exact consumer evidence are considered.
        for method in method_models[source['file']]:
            bindings={}
            for index,(kind,param) in enumerate(method['params']):
                if kind not in ('int','uint'):continue
                for assigned in re.finditer(r'\b(\w+)\s*=\s*'+re.escape(param)+r'\s*;',method['masked']):
                    aliases=field_uses.get(assigned.group(1),set())
                    if len(aliases)==1:bindings[index]=next(iter(aliases))
            if not bindings:continue
            for constructed in re.finditer(r'\bnew\s+'+re.escape(method['name'])+r'\s*\(',masked):
                unused_end,spans=arguments(masked,masked.find('(',constructed.start()))
                if len(spans)!=len(method['params']):continue
                consumer={'line':text.count('\n',0,constructed.start())+1,'call':'new '+method['name'],'offset':constructed.start()}
                for index,module in bindings.items():
                    aa,bb=spans[index]
                    for token in INT.finditer(masked[aa:bb]):
                        add(aa+token.start(),aa+token.end(),numeric(token.group()),module,'PE_RVA_literal','Constructor parameter stored in a field consumed by a proven module RVA boundary',consumer)
        # Preferred-VA array values are addresses only when the foreach value
        # reaches Address(value-referencePreferredBase) in that same statement.
        for loop in re.finditer(r'\bforeach\s*\(\s*int\s+(\w+)\s+in\s+new\s*\[\s*\]\s*\{([^{}]+)\}\s*\)',masked):
            symbol=loop.group(1);statement_end=masked.find(';',loop.end())
            if statement_end<0:continue
            tail=masked[loop.end():statement_end]
            if not re.search(r'\b(?:\w+\.)*Address\(\s*'+re.escape(symbol)+r'\s*-\s*0[xX]400000\s*\)',tail):continue
            consumer={'line':text.count('\n',0,loop.start())+1,'call':'foreach preferred editor VA -> Address','offset':loop.start()}
            for token in INT.finditer(loop.group(2)):
                value=numeric(token.group())
                if value is not None and value>=0x400000:
                    first,last=loop.start(2)+token.start(),loop.start(2)+token.end()
                    add(first,last,value-0x400000,'editor','reference_base_encoded_RVA','Foreach encoded RVA reaches editor Address(value-referencePreferredBase); keep its subtraction base unchanged',consumer)
                    entries[source['file'],first,last]['output_preferred_base']=0x400000
        # Export ordinal literals are a different address domain. Keep them in
        # a separate catalog so no binder can accidentally write an RVA here.
        def ordinal_span(start,end,value,module,consumer,assigned_rva=None):
            targets=set(ordinal_targets.get((module,value),set()))
            if not targets and assigned_rva is not None:targets.add(assigned_rva)
            if len(targets)!=1:
                unresolved.append({'source':source['file'],'line':consumer['line'],'call':consumer['call'],'reason':'Export ordinal has no unique declared module/target RVA proof','module':module,'ordinal':value});return
            row={'source':source['file'],'source_sha256':source['sha256'],'start':start,'end':end,'original_literal':text[start:end],
                 'module':module,'reference_ordinal':value,'reference_rva':next(iter(targets)),'status':'confirmed',
                 'proof':'Exact module export ordinal and unique profile target or same-branch native RVA assignment; not an RVA literal','consumers':[consumer]}
            ordinals[source['file'],start,end]=row
        for call in re.finditer(r'\b(?:GetProcAddressOrdinal|ExportOrdinal|Export)\s*\(',masked):
            unused_end,spans=arguments(masked,masked.find('(',call.start()))
            if len(spans)!=2:continue
            module=module_base(text[spans[0][0]:spans[0][1]].strip(),text,call.start())
            if not module:continue
            expression=masked[spans[1][0]:spans[1][1]];literal=re.fullmatch(r'\s*new\s+IntPtr\(\s*(\d+)\s*\)\s*',expression)
            consumer={'line':text.count('\n',0,call.start())+1,'call':masked[call.start():masked.find('(',call.start())],'offset':call.start()}
            if literal:
                ordinal_span(spans[1][0]+literal.start(1),spans[1][0]+literal.end(1),int(literal.group(1)),module,consumer)
            variable=re.fullmatch(r'\s*new\s+IntPtr\(\s*(\w+)\s*\)\s*',expression)
            if variable and not literal:
                owners=[m for m in method_models[source['file']] if m['start']<=call.start()<m['end']]
                if owners:
                    method=max(owners,key=lambda m:m['start'])
                    for assigned in re.finditer(r'\b'+re.escape(variable.group(1))+r'\s*=\s*(\d+)\s*;',method['masked']):
                        paired=re.search(r'\brva\s*=\s*(0[xX][0-9a-fA-F]+|[0-9]+)\s*;\s*$',method['masked'][:assigned.start()])
                        ordinal_span(method['start']+assigned.start(1),method['start']+assigned.end(1),int(assigned.group(1)),module,consumer,numeric(paired.group(1)) if paired else None)
        # These dictionaries and role comparisons are explicitly keyed by
        # ordinals read from guarded MFC export rows. They are not ordinary
        # application IDs; preserve the logical names separately in binding.
        if re.search(r'\bmfcMethods\.Add\(\s*ordinal\s*,\s*address\s*\)',masked):
            for use in re.finditer(r'\bmfcMethods\[\s*(\d+)\s*\]',masked):
                ordinal_span(use.start(1),use.end(1),int(use.group(1)),'mfc',
                    {'line':text.count('\n',0,use.start())+1,'call':'MFC export-ordinal dictionary key','offset':use.start()})
            for method in method_models[source['file']]:
                ordinal_parameters=[i for i,(kind,param) in enumerate(method['params']) if kind=='int' and re.search(r'\bmfcMethods\[\s*'+re.escape(param)+r'\s*\]',method['masked'])]
                for use in re.finditer(r'\b'+re.escape(method['name'])+r'\s*\(',masked):
                    unused_end,spans=arguments(masked,masked.find('(',use.start()))
                    if len(spans)!=len(method['params']):continue
                    for i in ordinal_parameters:
                        aa,bb=spans[i];literal=re.fullmatch(r'\s*(\d+)\s*',masked[aa:bb])
                        if literal:ordinal_span(aa+literal.start(1),aa+literal.end(1),int(literal.group(1)),'mfc',
                            {'line':text.count('\n',0,use.start())+1,'call':'MFC export-ordinal dictionary wrapper '+method['name'],'offset':use.start()})
        if 'name=="MfcOrdinal"+ordinal' in text and 'Num(guards[name]["ordinal"])' in text:
            for use in re.finditer(r'\bordinal\s*==\s*(\d+)',masked):
                ordinal_span(use.start(1),use.end(1),int(use.group(1)),'mfc',
                    {'line':text.count('\n',0,use.start())+1,'call':'MFC guarded export role allowlist','offset':use.start()})
    guards = []
    for source in sources:
        text=source_texts[source['file']]; masked, strings=mask_csharp(text)
        def guard(start,end,value,rva,role):
            identifier=PureWindowsPath(source['file']).name+':'+role
            guards.append({'id':identifier,'source':source['file'],'source_sha256':source['sha256'],
                'start':start,'end':end,'original_literal':text[start:end],'reference_rva':rva,'module':'editor',
                'length':len(value)//2,'status':'confirmed','proof':'Exact source byte guard linked to its checked native function '+role})
            for address in entries.values():
                if address['source']==source['file'] and address['module']=='editor' and address['reference_rva']==rva:
                    address['length']=max(address.get('length',0),len(value)//2)
        if PureWindowsPath(source['file']).name=='NativeControlPropertyBatch.cs':
            for call in re.finditer(r'\bPairedExactCode\s*\(',masked):
                opening=masked.find('(',call.start());unused_end,spans=arguments(masked,opening)
                if len(spans)!=3:continue
                rva=numeric(text[spans[1][0]:spans[1][1]])
                literal=next(((a,b,value) for a,b,value in strings if spans[2][0]<=a<b<=spans[2][1]),None)
                if rva is not None and literal and re.fullmatch('[a-fA-F0-9]+',literal[2]):
                    guard(*literal,rva,'PairedExactCode-'+hex(rva))
        for a,b,value in strings:
            if PureWindowsPath(source['file']).name=='NativeRecipeStoreProjection.cs' and re.search(r'const\s+string\s+StorePrefix\s*=\s*$',masked[:a]):
                guard(a,b,value,0x900320,'StorePrefix')
            if PureWindowsPath(source['file']).name=='NativeStrategyLifecycleProfile.reusable.v3.cs' and re.search(r'const\s+string\s+applicationPrefix\s*=\s*$',masked[:a]):
                guard(a,b,value,0x6C060,'applicationPrefix')
    items = sorted(entries.values(), key=lambda row: (row['source'], row['start']))
    return {'schema': 'mcgs-native-source-address-catalog/v1',
            'span_unit': 'Python Unicode indices in the exact utf-8-sig-decoded reference C# text, including CRLF',
            'rewrite_order': 'Apply nonoverlapping confirmed spans in descending offset order before other source patches; verify source SHA and original literal',
            'generic_numeric_parser_rewritten': False, 'object_layout_offsets_rewritten': False,
            'counts': {'entries': len(items), 'confirmed': sum(row['status'] == 'confirmed' for row in items),
                       'source_ordinals':len(ordinals),'address_kinds':dict(Counter(row['address_kind'] for row in items)),
                       'module_ownership_or_const_scope_gaps': len(unresolved)},
            'entries': items, 'source_guards':guards, 'source_ordinals':sorted(ordinals.values(),key=lambda r:(r['source'],r['start'])), 'unresolved_source_candidates': unresolved}


def build(repo, git_ref=None):
    repo = Path(repo).resolve(); objects = {}
    if git_ref:
        tree = subprocess.run(['git', '-C', str(repo), 'ls-tree', '-r', '-z', '--full-tree', git_ref], capture_output=True, check=True).stdout
        for entry in tree.split(b'\0'):
            if not entry: continue
            head, relative = entry.split(b'\t', 1); objects[relative.decode('utf-8')] = head.split()[2].decode('ascii')
    def load(relative):
        if git_ref:
            if relative not in objects: raise ValueError('Missing git reference file: ' + relative)
            result = subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', objects[relative]], capture_output=True, check=True)
            return result.stdout
        return (repo / relative).read_bytes()
    manifest_raw = load(SOURCE + '/source-and-dependency-manifest.json')
    manifest = json.loads(manifest_raw.decode('utf-8-sig')); sources = []; artifacts = []; pin_differences = []; source_texts = {}
    for entry in manifest['sources']:
        relative = SOURCE + '/sources/' + entry['name']; raw = load(relative)
        item = csharp_inventory(relative, raw); item['manifest_sha256'] = entry['sha256']; sources.append(item); source_texts[relative] = raw.decode('utf-8-sig')
        if item['sha256'] != entry['sha256']: pin_differences.append(relative)
    for entry in manifest['owned_artifacts']:
        relative = SOURCE + '/artifacts/' + entry['task_relative_file']; raw = load(relative)
        item = artifact_inventory(entry['task_relative_file'], raw); item['manifest_sha256'] = entry['sha256']; artifacts.append(item)
        if item['sha256'] != entry['sha256']: pin_differences.append(relative)
    by_hash = defaultdict(list); by_name = defaultdict(list)
    for item in artifacts:
        by_hash[item['sha256']].append(item['file']); by_name[Path(item['file']).name.lower()].append(item['file'])
    consumers = defaultdict(list)
    for source in sources:
        for field in source['findings']:
            if field['kind'] == 'sha256_literal_candidate':
                matches = by_hash.get(field['value'].lower(), [])
                if matches:
                    field['matches_owned_artifact'] = matches
                    field['rewrite_policy'] = 'verify attested resolved profile digest for the same reference key; preserve actual hash observations'
                    for name in matches: consumers[name].append({'source': source['file'], 'line': field['line'], 'evidence': 'exact profile digest literal'})
        for literal in source['profile_filename_literals']:
            for name in by_name.get(Path(literal['value']).name.lower(), []):
                consumers[name].append({'source': source['file'], 'line': literal['line'], 'evidence': 'filename literal; path/exposure may remain dynamic'})
    for item in artifacts:
        item['source_consumer_candidates'] = consumers[item['file']]
    finding_counts = Counter(); field_counts = Counter()
    for source in sources: finding_counts.update(source['finding_counts'])
    for item in artifacts: field_counts.update(item.get('field_kind_counts', {}))
    return {'schema': SCHEMA, 'input_mode': 'git-object' if git_ref else 'working-tree', 'git_reference': git_ref,
            'reference_manifest_sha256': digest(manifest_raw), 'counts': {'CSharp_sources': len(sources),
             'owned_artifacts': len(artifacts), 'JSON_artifacts': sum(item['format'] == '.json' for item in artifacts),
             'source_findings': dict(finding_counts), 'profile_semantic_fields': dict(field_counts)},
            'manifest_pin_differences': pin_differences,
            'inventory_limits': ['Lexical source findings are candidates, not C# semantic binding or proof of production exposure.',
             'An address match does not prove object offsets, calling convention or native capabilities unchanged.',
             'Number is a general parser; never remap its numeric result globally.',
             'Some paths are assembled dynamically; absence of a filename consumer is not proof that a profile is unused.'],
            'attestation_contract_suggestion': {'target_modules': 'actual module identities and PE evidence',
             'address_map': 'module + reference RVA -> actual RVA, with match evidence and capability status',
             'profiles': 'reference relative key + reference SHA -> resolved relative key + actual resolved SHA + field evidence',
             'layouts': 'explicit field/call ABI evidence or unsupported; never inferred from a single RVA delta',
             'runtime_hash_guard': 'verify current resolved bytes against the attested resolved SHA; do not return historical expected SHA as actual'},
            'sources': sources, 'artifacts': artifacts, 'source_address_catalog': source_address_catalog(sources, artifacts, source_texts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--git-ref', help='Optional immutable reference, avoiding concurrent working-tree edits')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--address-output', type=Path)
    args = parser.parse_args(); result = build(args.repo, args.git_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.address_output:
        args.address_output.parent.mkdir(parents=True, exist_ok=True)
        args.address_output.write_text(json.dumps(result['source_address_catalog'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'schema': SCHEMA, 'counts': result['counts'], 'manifest_pin_differences': result['manifest_pin_differences']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
