"""Explain located and unresolved native entries without loading Pro.

This report describes static location evidence, not successful native execution.
One unresolved entry does not invalidate independently located entries.
"""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import sys


def read_document(path, schema):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or value.get('schema') != schema:
        raise ValueError('Unexpected evidence schema: ' + str(path))
    return value


def build_report(adaptation, attestation=None, *, profile=None, entry=None, include_located=False):
    if adaptation.get('schema') != 'mcgs-native-abi-adaptation/v1':
        raise ValueError('Expected current-program adaptation evidence')
    if attestation is not None and attestation.get('schema') != 'mcgs-native-resolved-profiles/v1':
        raise ValueError('Expected current-program resolved profiles evidence')
    profiles = []
    failures = []
    located = []
    metadata = []
    partial = []
    function_ids = set()
    addresses = set()
    for row in (attestation or {}).get('reference_profiles', []):
        name = row['relative_path']
        if profile is not None and name != profile:
            continue
        states = []
        for item in row.get('entry_resolutions', []):
            if entry is not None and item['name'] != entry:
                continue
            ready = item.get('status') in {'resolved', 'verified'}
            metadata_only = ready and item.get('no_native_address_fields', False)
            partly_located = not ready and (item.get('direct_status') in {'resolved', 'verified'} or bool(item.get('proof_ids')))
            function_ids.update(item.get('proof_ids', []))
            if 'reference_rva' in item:
                addresses.add((item.get('module'), item['reference_rva']))
            record = {'profile': name, 'entry': item['name'], 'json_pointer': item.get('json_pointer'),
                      'status': 'metadata_only' if metadata_only else 'located_runtime_unverified' if ready else
                                'partial_entry_runtime_fields_required' if partly_located else 'not_located',
                      'failure_category': None if ready else item.get('failure_category', 'locator_unresolved'),
                      'unresolved_fields': item.get('details', []),
                      'proof_ids': item.get('proof_ids', []),
                      'direct_fields_status': item.get('direct_status'),
                      'available_address_fields': [field['json_pointer'][len(item.get('json_pointer', '')):]
                          for field in row.get('resolved_fields', []) if
                          field['json_pointer'].startswith(item.get('json_pointer', '')+'/')],
                      'not_fully_located_is_not_a_feature_rejection': True,
                      'affects_other_entries': False, 'upgrade_required': False}
            states.append(record)
            (metadata if metadata_only else located if ready else partial if partly_located else failures).append(record)
        if entry is not None and not states:
            continue
        profiles.append({'profile': name, 'profile_evidence_status': row.get('status'),
                         'located_entries': sum(s['status'] == 'located_runtime_unverified' for s in states),
                         'not_located_entries': sum(s['status'] == 'not_located' for s in states),
                         'metadata_only_entries': sum(s['status'] == 'metadata_only' for s in states),
                         'partial_entries': sum(s['status'] == 'partial_entry_runtime_fields_required' for s in states),
                         'profile_status_is_not_a_global_feature_gate': True})
    functions = adaptation.get('functions', [])
    if profile is not None:
        functions = [row for row in functions if row.get('id') in function_ids or
                     (row.get('module'), row.get('reference_rva')) in addresses]
    if entry is not None:
        functions = [row for row in functions if entry in row.get('names', []) or row.get('id') == entry]
    methods = collections.Counter(row.get('resolution_method', 'not_located') for row in functions)
    unresolved_functions = []
    if profile is None:
        for row in functions:
            if row.get('status') != 'resolved':
                unresolved_functions.append({key: row[key] for key in (
                    'id', 'module', 'names', 'status', 'reason', 'failure_category',
                    'candidate_rvas', 'candidates_examined', 'adaptation_attempts') if key in row})
    if profile is not None and not profiles:
        raise ValueError('Requested profile is absent from the supplied attestation: ' + profile)
    if entry is not None and not located and not failures and not metadata and not partial and not functions:
        raise ValueError('Requested entry is absent from the supplied evidence: ' + entry)
    result = {'schema': 'mcgs-native-adaptation-report/v1',
              'scope': 'provided static location evidence; runtime ABI/object/product contracts remain unverified',
              'software_version_gate': False, 'upgrade_required': False,
              'Pro_started_or_called': False, 'project_accessed_or_written': False,
              'unresolved_entries_disable_other_entries': False,
              'feature_availability_not_inferred_from_profile_status': True,
              'capabilities': adaptation.get('capabilities', {}),
              'summary': {'profiles': len(profiles), 'located_entries': len(located),
                          'not_located_entries': len(failures), 'metadata_only_entries': len(metadata),
                          'partial_entries': len(partial),
                          'functions_in_scope': len(functions),
                          'function_resolution_methods': dict(sorted(methods.items())),
                          'unresolved_functions_in_scope': sum(row.get('status') != 'resolved' for row in functions)},
              'profiles': profiles, 'not_located_entries': failures,
              'partial_entries': partial,
              'unresolved_functions': unresolved_functions,
              'runtime_failure_diagnostics': ['failure_category', 'affected_feature.kind', 'affected_feature.action_id',
                                              'affected_feature.stage', 'affected_profile', 'affected_entry', 'blocked_scope'],
              'remediation': 'Use independently located entries; adapt only the missing entry. Never call retained reference addresses.'}
    if include_located:
        result['located_entries'] = located
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adaptation', type=Path, required=True)
    parser.add_argument('--attestation', type=Path, help='Defaults to sibling profiles/attestation.json when present')
    parser.add_argument('--profile', help='Exact relative profile name')
    parser.add_argument('--entry', help='Exact entry name or function identity')
    parser.add_argument('--include-located', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    if args.out and args.out.exists():
        raise ValueError('Output must be a new file')
    path = args.attestation or args.adaptation.parent/'profiles/attestation.json'
    attestation = read_document(path, 'mcgs-native-resolved-profiles/v1') if path.is_file() else None
    if args.attestation is not None and attestation is None:
        raise ValueError('Selected attestation is absent')
    if args.profile is not None and attestation is None:
        raise ValueError('--profile needs the resolved profile attestation')
    adaptation = read_document(args.adaptation, 'mcgs-native-abi-adaptation/v1')
    if attestation is not None and attestation.get('catalog_sha256') != adaptation.get('catalog_sha256'):
        raise ValueError('Adaptation and attestation use different catalogs')
    if attestation is not None and attestation.get('modules') != adaptation.get('modules'):
        raise ValueError('Adaptation and attestation use different selected modules')
    report = build_report(adaptation, attestation, profile=args.profile, entry=args.entry,
                          include_located=args.include_located)
    raw = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(raw)
        print(json.dumps({'output': str(args.out), 'summary': report['summary'],
                          'Pro_started_or_called': False}, ensure_ascii=False))
    else:
        print(raw, end='')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'ok': False, 'failure_category': 'evidence_input_invalid',
                          'error': str(error), 'Pro_started_or_called': False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
