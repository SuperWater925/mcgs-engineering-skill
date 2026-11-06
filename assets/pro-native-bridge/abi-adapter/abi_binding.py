"""Resolve one selected program's native profiles before delivery SHA repinning.

Only classified PE addresses change. Object offsets, IDs and calling contracts
remain the existing contracts. No editor process is loaded or invoked here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re

from abi_locator import DEFAULT_CATALOG, load_catalog, resolve_catalog, write_resolved_profiles
from inventory import arguments, mask_csharp
from pe32 import PE32


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _need(value, message):
    if not value:
        raise ValueError(message)


def actual_module_files(catalog, layout):
    """Compatibility wrapper; select current program dependencies, not reference copies."""
    from module_selection import select_module_files
    return select_module_files(catalog, layout)['files']


class TargetBinding:
    def __init__(self, stage, manifest, layout, output, catalog_file=None, module_overrides=None, progress_callback=None):
        self.stage = Path(stage)
        self.output = Path(output)
        self.catalog_file = Path(catalog_file or DEFAULT_CATALOG).resolve()
        self.catalog = load_catalog(self.catalog_file)
        _need(self.catalog.get('schema') == 'mcgs-native-reference-catalog/v1', 'Native reference catalog schema differs')
        source_file = Path(__file__).resolve().parent / 'catalogs' / 'source-addresses.json'
        self.source_catalog = json.loads(source_file.read_text(encoding='utf-8-sig'))
        _need(self.source_catalog.get('schema') == 'mcgs-native-source-address-catalog/v1', 'Source address catalog schema differs')
        self.source_entries = {}
        self.source_guards = {}
        self.source_ordinals = {}
        source_rows = {row['name']: row for row in manifest['sources']}
        for entry in self.source_catalog['entries']:
            if entry.get('status') != 'confirmed':
                continue
            name = PureWindowsPath(entry['source']).name
            _need(name in source_rows and source_rows[name]['sha256'] == entry['source_sha256'],
                  'Classified source span is not from the selected source manifest: ' + name)
            self.source_entries.setdefault(name, []).append(entry)
        for guard in self.source_catalog.get('source_guards', []):
            name = PureWindowsPath(guard['source']).name
            _need(name in source_rows and source_rows[name]['sha256'] == guard['source_sha256'],
                  'Source guard is not from the selected source manifest: ' + name)
            self.source_guards.setdefault(name, []).append(guard)
        for ordinal in self.source_catalog.get('source_ordinals',[]):
            name=PureWindowsPath(ordinal['source']).name
            _need(name in source_rows and source_rows[name]['sha256']==ordinal['source_sha256'],
                  'Source ordinal is not from the selected source manifest: '+name)
            self.source_ordinals.setdefault(name,[]).append(ordinal)
        from module_selection import select_module_files
        selection = select_module_files(self.catalog, layout, module_overrides, progress_callback=progress_callback)
        modules = selection['files']
        self.module_selection_report = selection['report']
        self.actual_module_paths = modules
        self.module_names = {row.get('basename','').casefold(): alias
                             for alias,row in self.catalog['reference_modules'].items() if row.get('basename')}
        self.result = resolve_catalog(self.catalog, modules, progress_callback=progress_callback)
        self.attestation = write_resolved_profiles(self.catalog, self.result, self.output / 'profiles',
                                                  profile_root=self.stage / 'artifacts')
        self.profile_rows = {row['relative_path']: row for row in self.attestation['reference_profiles']}
        self.overrides = {}
        known = {row['task_relative_file']: row for row in manifest['owned_artifacts']}
        for relative, row in self.profile_rows.items():
            _need(relative in known and row['reference_sha256'] == known[relative]['sha256'],
                  'Resolved profile is not from this selected manifest: ' + relative)
            file = (self.output / 'profiles' / row['resolved_relative_path']).resolve()
            _need(file.is_relative_to((self.output / 'profiles').resolve()), 'Resolved profile path escapes its output')
            raw = file.read_bytes()
            _need(digest(raw) == row['resolved_sha256'], 'Resolved profile SHA differs')
            self.overrides[relative] = raw
        self.source_changes = []
        self.guard_changes = []
        self.ordinal_changes = []
        self.ordinal_images = {}
        (self.output / 'adaptation.json').write_bytes(json_bytes(self.result))
        (self.output / 'module-selection.json').write_bytes(json_bytes(self.module_selection_report))

    def module_file_value(self, value, key=None):
        if not isinstance(value,str):
            return value
        windows = PureWindowsPath(value)
        alias = self.module_names.get(windows.name.casefold())
        if alias not in self.actual_module_paths:
            return value
        if windows.is_absolute() or Path(value).is_absolute():
            return str(self.actual_module_paths[alias])
        if key == 'relative_file':
            # This field denotes a PE provider, not a business path. Consumers
            # must use the selected file even if its directory/name changed.
            return str(self.actual_module_paths[alias])
        if key in ('file_name','filename','base_name','basename') and value.casefold() in self.module_names:
            return self.actual_module_paths[alias].name
        return value

    def source_module_paths(self, text, original_install):
        pairs = {}
        for basename,alias in self.module_names.items():
            if alias not in self.actual_module_paths:
                continue
            old_files=[PureWindowsPath(original_install)/'Program'/basename,PureWindowsPath(original_install)/basename]
            declared=self.catalog['reference_modules'][alias].get('install_relative_path')
            relative=PureWindowsPath(declared) if isinstance(declared,str) else None
            if relative and not relative.is_absolute() and '..' not in relative.parts:
                old_files.append(PureWindowsPath(original_install)/relative)
            for old_file in old_files:
                old = str(old_file);new = str(self.actual_module_paths[alias])
                for first,last in ((old,new),(old.replace('\\','\\\\'),new.replace('\\','\\\\')),(old.replace('\\','/'),new.replace('\\','/'))):
                    pairs[first.casefold()]=last
        if not pairs:
            return text
        pattern = re.compile('|'.join(re.escape(old)+r'''(?=(?:\\)?['"]|$)''' for old in sorted(pairs,key=len,reverse=True)),re.I)
        return pattern.sub(lambda match:pairs[match.group().casefold()],text)

    def patch_addresses(self, name, text):
        """Apply spans against exact original text, before all other rewriting."""
        entries = self.source_entries.get(name, [])
        if not entries and name not in self.source_guards and name not in self.source_ordinals:
            return text
        masked, unused = mask_csharp(text)
        replacements = {}
        for entry in entries:
            start, end = entry['start'], entry['end']
            _need(text[start:end] == entry['original_literal'], 'Native source address span changed: ' + name)
            old = entry['reference_rva']; alias = entry['module']
            mapped = self.result['rva_maps'].get(alias, {}).get(hex(old))
            if mapped is not None:
                actual = mapped['actual_rva']
                if entry['address_kind'] == 'preferred_PE_VA_literal':
                    actual += self.result['modules'][alias]['actual']['image_base']
                elif entry['address_kind'] == 'reference_base_encoded_RVA':
                    actual += entry['output_preferred_base']
                suffix = re.search(r'[uUlL]+$', entry['original_literal'])
                replacement = hex(actual) + (suffix.group() if suffix else '')
                replacements[(start, end)] = replacement
                status = 'resolved'
            else:
                reason = json.dumps(alias + ':' + hex(old) + ':' + name)
                replacement = 'NativeAbiTargetProfiles.UnresolvedRva(' + reason + ')'
                suffix=re.search(r'[uUlL]+$',entry['original_literal'])
                value_type=entry.get('value_type','int')
                if value_type=='uint' or suffix and suffix.group().lower()=='u':replacement='unchecked((uint)'+replacement+')'
                elif value_type=='ulong' or suffix and 'u' in suffix.group().lower():replacement='unchecked((ulong)'+replacement+')'
                elif value_type=='long':replacement='((long)'+replacement+')'
                if entry['address_kind'] == 'PE_RVA_constant':
                    # Keep a compile-time const; only its proven pointer-producing
                    # uses become a lazy unavailable call, not a type initializer.
                    symbol = re.search(r'(\w+)\s*=\s*$', masked[:start])
                    _need(symbol is not None, 'Classified const declaration has no symbol')
                    found = 0
                    for consumer in entry['consumers']:
                        opening = masked.find('(', consumer['offset'])
                        unused_end, spans = arguments(masked, opening)
                        _need(spans, 'Classified const consumer is not a complete call')
                        for a, b in spans:
                            for match in re.finditer(r'\b' + re.escape(symbol.group(1)) + r'\b', masked[a:b]):
                                replacements[(a + match.start(), a + match.end())] = replacement
                                found += 1
                    _need(found, 'Unresolved address const has no lazy consumer boundary')
                else:
                    replacements[(start, end)] = replacement
                actual = None; status = 'unresolved'
            self.source_changes.append({'source': name, 'module': alias, 'reference_rva': old,
                                        'actual_rva': mapped['actual_rva'] if mapped else None,
                                        'emitted_numeric_value':actual,'address_kind':entry['address_kind'],
                                        'status': status, 'span': [start, end]})
        for guard in self.source_guards.get(name, []):
            start, end = guard['start'], guard['end']
            _need(text[start:end] == guard['original_literal'], 'Native source byte-guard span changed: ' + name)
            match = next((item for item in self.result['functions']
                          if item['module'] == guard['module'] and item['reference_rva'] == guard['reference_rva']
                          and item['status'] == 'resolved'
                          and len(item.get('guard_bytes_at_reference_preferred_base', '')) == 2 * guard['length']), None)
            mapped = self.result['rva_maps'].get(guard['module'], {}).get(hex(guard['reference_rva']))
            state = {'id':guard['id'], 'module':guard['module'], 'reference_rva':guard['reference_rva'],
                     'actual_rva':mapped['actual_rva'] if mapped else None, 'length':guard['length'],
                     'status':'verified' if match else 'unresolved',
                     'reference_preferred_base':self.catalog['reference_modules'][guard['module']]['image_base'],
                     'details':'Resolved current full source guard' if match else 'Full source guard was not uniquely located'}
            if match:
                state.update(actual_rva=match['actual_rva'],
                             bytes_at_reference_preferred_base=match['guard_bytes_at_reference_preferred_base'],
                             highlow_offsets=match['actual_relocation_offsets'], proof_id=match['proof_id'])
                replacements[(start,end)] = json.dumps(match['guard_bytes_at_reference_preferred_base'])
            self.guard_changes.append(state)
        for ordinal in self.source_ordinals.get(name,[]):
            start,end=ordinal['start'],ordinal['end'];alias=ordinal['module'];old=ordinal['reference_ordinal'];rva=ordinal['reference_rva']
            _need(text[start:end]==ordinal['original_literal'],'Native source ordinal span changed: '+name)
            mapped=self.result['rva_maps'].get(alias,{}).get(hex(rva));actual=None;proof=None
            if mapped and alias in self.actual_module_paths:
                if alias not in self.ordinal_images:self.ordinal_images[alias]=PE32(self.actual_module_paths[alias])
                pe=self.ordinal_images[alias];target=mapped['actual_rva'];same=pe.exports_by_ordinal.get(old)
                if same and same['rva']==target and not same.get('forwarder'):
                    actual=old;proof='Current original ordinal exports the uniquely located target'
                else:
                    names={export for row in self.catalog['signatures'] if row['module']==alias and row['reference_rva']==rva for export in row.get('exports',[])}
                    named={pe.exports[export]['ordinal'] for export in names if export in pe.exports and pe.exports[export]['rva']==target and not pe.exports[export].get('forwarder')}
                    candidates={number for number,row in pe.exports_by_ordinal.items() if row['rva']==target and not row.get('forwarder')}
                    if len(named)==1:actual=next(iter(named));proof='Unique matching named export for the located target'
                    elif len(candidates)==1:actual=next(iter(candidates));proof='Unique actual ordinal for the located target'
            if actual is not None:
                suffix=re.search(r'[uUlL]+$',ordinal['original_literal']);literal=ordinal['original_literal'].lower()
                replacements[(start,end)]=(hex(actual) if literal.startswith('0x') else str(actual))+(suffix.group() if suffix else '')
            else:
                replacements[(start,end)]='NativeAbiTargetProfiles.UnresolvedRva('+json.dumps(alias+':ordinal:'+str(old)+':'+name)+')'
            self.ordinal_changes.append({'source':name,'span':[start,end],'module':alias,'reference_ordinal':old,
                'reference_rva':rva,'actual_ordinal':actual,'actual_rva':mapped['actual_rva'] if mapped else None,
                'status':'verified' if actual is not None else 'unresolved','proof':proof})
        ordered = sorted(replacements.items(), reverse=True)
        next_start = len(text)
        for (start, end), replacement in ordered:
            _need(end <= next_start, 'Classified native source address spans overlap')
            text = text[:start] + replacement + text[end:]
            next_start = start
        return text

    def index(self, resolved, layout, copied):
        rows = []
        helper = Path(__file__).with_name('NativeAbiTargetProfiles.cs').read_text(encoding='utf-8-sig')
        declaration = re.search(r'LazyProfiles\s*=\s*new\s+HashSet<string>\s*\([^)]*\)\s*\{(.*?)\};', helper, re.S)
        contract = re.search(r'const\s+string\s+LazyEntryContract\s*=\s*"([^"\r\n]+)"', helper)
        _need(declaration is not None and contract is not None, 'Owned lazy profile reader contract is absent')
        lazy_profiles = set(re.findall(r'"([^"\\]+)"', declaration.group(1)))
        _need(lazy_profiles and all(path and '..' not in path.split('/') for path in lazy_profiles),
              'Owned lazy profile declarations differ')
        by_relative = {}
        for item in copied:
            by_relative.setdefault(item['original_relative_file'], []).append(item)
        for relative, record in self.profile_rows.items():
            normalized = relative.replace('\\', '/')
            root_entries = normalized == 'static/read-tree-guard-profile.json'
            # An explicit ReadLazyAllText consumer validates consumed entries.
            # Generic CheckProfile still refuses partial files, including those
            # not yet converted to an operation-level reader.
            explicit_lazy_reader = bool(record.get('entry_resolutions'))
            partial_allowed = root_entries or explicit_lazy_reader
            status = 'verified' if record['status'] == 'resolved' else 'partial' if partial_allowed else 'unresolved'
            entries = [{key: entry[key] for key in ('name', 'json_pointer', 'status', 'direct_status',
                                                   'no_native_address_fields', 'failure_category',
                                                   'feature_scope', 'adaptation_attempts') if key in entry}
                       for entry in record.get('entry_resolutions', [])]
            for item in by_relative.get(relative, []):
                rows.append({'file': item['planned_file'], 'profile': relative, 'status': status,
                             'sha256': digest(resolved[relative]), 'allow_partial_entries': partial_allowed,
                             'entry_validation_contract': contract.group(1) if explicit_lazy_reader else None,
                             'availability_scope': 'checked_entry_or_fields' if partial_allowed else 'complete_profile_required',
                             'entry_statuses': entries,
                             'details': json.dumps(record['unresolved_fields'], ensure_ascii=True, separators=(',', ':'))})
        # Static contracts have no native addresses to locate, but consumers
        # still need the exact promoted bytes in the bound integrity index.
        # Omitting them breaks explicit lazy readers before their referenced
        # live profile can be checked. This does not admit unresolved ABI rows.
        for relative, items in by_relative.items():
            if relative in self.profile_rows:
                continue
            _need(relative in resolved, 'Copied static contract has no frozen bytes: ' + relative)
            for item in items:
                rows.append({'file': item['planned_file'], 'profile': relative,
                             'status': 'unchanged', 'sha256': digest(resolved[relative]),
                             'allow_partial_entries': False, 'entry_validation_contract': None,
                             'integrity_only': True, 'details': 'Frozen non-native contract; no address proof implied'})
        modules = []
        for alias, item in self.result['modules'].items():
            modules.append({'logical_name': alias, 'reference_basename': (item.get('reference') or {}).get('basename') or alias,
                            'actual_basename': item['actual']['basename'], 'actual_sha256': item['actual']['sha256'],
                            'actual_file': str(self.actual_module_paths[alias]),
                            'is_editor': alias == 'editor'})
        return {'schema': 'mcgs-native-bound-profile-index/v1', 'catalog_sha256': self.result['catalog_sha256'],
                'files': rows, 'modules': modules, 'source_guards':self.guard_changes,'source_ordinals':self.ordinal_changes,
                'object_layout_offsets_changed': False, 'vendor_whole_file_sha_admission': False,
                'feature_scoped_failure': True, 'adaptive_locator': True}

    def summary(self):
        return {'catalog_sha256': self.result['catalog_sha256'],
                'module_selection': self.module_selection_report,
                'profiles': {state: sum(row['status'] == state for row in self.profile_rows.values())
                             for state in ('resolved', 'partial', 'unresolved')},
                'source_addresses': {state: sum(row['status'] == state for row in self.source_changes)
                                     for state in ('resolved', 'unresolved')},
                'source_changes': self.source_changes,
                'source_guards':[{key:value for key,value in row.items() if key!='bytes_at_reference_preferred_base'} for row in self.guard_changes],
                'source_ordinals':self.ordinal_changes,
                'gaps': self.result['gaps'], 'not_a_runtime_semantics_or_layout_validation': True}


def patch_runtime_source(name, text):
    """Bound-only lazy ABI checks and lexical IO/module call indirection."""
    def once(old, new):
        nonlocal text
        _need(text.count(old) == 1, 'Native ABI lazy-check contract differs: ' + name + ': ' + old[:70])
        text = text.replace(old, new)
    if name == 'NativeOperations.functional.cs':
        # A SHA computation does not consume an address. Keep Hash pure so a
        # partial profile cannot reject a later explicit per-entry reader here.
        # Actual reads below still enforce the bound profile/index integrity.
        once('{"error_type",e.GetType().Name}',
             '{"error_type",e.GetType().Name},{"native_abi",NativeAbiTargetProfiles.Metadata(e)},{"native_function_binding",NativeAbiTargetProfiles.BindingMetadata()}')
        once('var result=NativeOperations.Dispatch(request,datObj);',
             'var result=NativeOperations.Dispatch(request,datObj);result["native_function_binding"]=NativeAbiTargetProfiles.BindingMetadata();')
        # Core functions and table slots are lazy in the reusable source itself.
        # Binding only changes classified addresses/guards and owned file IO;
        # it must not inject an eager whole-table gate back into the constructor.
    elif name == 'NativeControlPropertyBatch.cs':
        once('NativeMemory.Require(BitConverter.ToString(expected)==BitConverter.ToString(NativeMemory.Bytes(api.Engine.Address(rva),expected.Length))',
             'NativeAbiTargetProfiles.RelocateSourceGuard(rva,expected);NativeMemory.Require(BitConverter.ToString(expected)==BitConverter.ToString(NativeMemory.Bytes(api.Engine.Address(rva),expected.Length))')
    elif name == 'NativeRecipeStoreProjection.cs':
        once('Array.Copy(BitConverter.GetBytes(NativeMemory.U(api.Engine.Address(',
             'NativeAbiTargetProfiles.RelocateSourceGuard("NativeRecipeStoreProjection.cs:StorePrefix",expected);Array.Copy(BitConverter.GetBytes(NativeMemory.U(api.Engine.Address(')
    elif name == 'NativeStrategyLifecycleProfile.reusable.v3.cs':
        once('CheckCurrentApplicationPrefix();Root=Read.Existing.RootDoc();',
             'NativeAbiTargetProfiles.RelocateSourceGuard("NativeStrategyLifecycleProfile.reusable.v3.cs:applicationPrefix",currentApplicationPrefix);CheckCurrentApplicationPrefix();Root=Read.Existing.RootDoc();')
    if name in ('NativeLabelScalarReadonlyProfile.cs','NativeLabelScalarCachedReadonlyProfile.cs'):
        once('name=="MfcOrdinal"+ordinal',
             'NativeAbiTargetProfiles.MatchesLogicalOrdinalName("mfc",name,ordinal)')
    masked, unused = mask_csharp(text)
    replacements = []
    for match in re.finditer(r'\bFile\.(ReadAllText|ReadAllBytes)\s*(?=\()', masked):
        replacements.append((match.start(), match.end(), 'NativeAbiTargetProfiles.' + match.group(1)))
    for match in re.finditer(r'\bGetModuleHandleW\s*(?=\()', masked):
        # P/Invoke declarations keep their native entry point and signature.
        prefix = masked[max(masked.rfind(';', 0, match.start()), masked.rfind('{', 0, match.start()),
                            masked.rfind('}', 0, match.start())) + 1:match.start()]
        if re.search(r'\bextern\s+\w+\s*$', prefix):
            continue
        replacements.append((match.start(), match.end(), 'NativeAbiTargetProfiles.ModuleHandle'))
    for start, end, replacement in sorted(replacements, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text
