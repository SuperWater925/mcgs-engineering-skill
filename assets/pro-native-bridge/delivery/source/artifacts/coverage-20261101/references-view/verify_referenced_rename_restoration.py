"""Whole-field strict comparison after native MainCtrl restoration, from safe exports only."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.dont_write_bytecode = True
from audit_reference_rename_persistence import audit
import native_tool as nt


def fingerprint_differences(left, right):
    differences = []
    for table in sorted(set(left) | set(right)):
        a, b = left.get(table, {}), right.get(table, {})
        for key in sorted(set(a) | set(b)):
            aa, bb = a.get(key, {}), b.get(key, {})
            for field in sorted(set(aa) | set(bb)):
                if aa.get(field) != bb.get(field):
                    differences.append({'table': table, 'row_key': key, 'field': field,
                                        'before_fingerprint': aa.get(field),
                                        'after_fingerprint': bb.get(field)})
    return differences


def verify(before_directory, after_directory):
    before, after = nt.Export(before_directory), nt.Export(after_directory)
    errors = []
    for export in (before, after):
        for obj in (export.index, export.fp):
            if obj.get('project_family') != 'Pro' or obj.get('source_unchanged') is not True or obj.get('all_field_values_fingerprinted') is not True:
                errors.append('Incomplete immutable full-field Pro export')
        if export.index['tables'] != export.fp['tables']:
            errors.append('Export/fingerprint schemas disagree')
        for (table, key), row in export.rows.items():
            for field, info in row.items():
                if isinstance(info, dict) and {'file', 'bytes', 'sha256'} <= set(info):
                    data = export.blob(table, key, field)
                    wanted = f'binary:{len(data)}:{hashlib.sha256(data).hexdigest()}'
                    if export.fp['fingerprints'][table][key][field] != wanted:
                        errors.append(f'Exported BLOB/fingerprint disagreement: {table}/{key}/{field}')
    if before.index['tables'] != after.index['tables']:
        errors.append('Schema/table counts changed')
    left, right = before.fp['fingerprints'], after.fp['fingerprints']
    if set(left) != set(right) or any(set(left[t]) != set(right.get(t, {})) for t in left):
        errors.append('Typed table or row membership changed')
    differences = fingerprint_differences(left, right)
    classified = []
    narrow = None
    try:
        narrow = audit(before_directory, after_directory)
        if not narrow['ok'] or narrow['mainctrl']['temporary_name_residual_count'] != 0:
            errors.append('MainCtrl original full BLOB has not been exactly restored')
        for row in narrow['pages']:
            if row['absolute_changed_offsets']:
                classified.append(('WndUser', str(row['page_id']), 'lbObjects'))
    except Exception as error:
        errors.append('Narrow byte reconstruction failed: ' + str(error))
    allowed = set(classified)
    unknown = [d for d in differences if (d['table'], d['row_key'], d['field']) not in allowed]
    if unknown:
        errors.append('Unclassified complete typed field differences remain')
    if before.blob('WndControl', '1', 'lbObjects') != after.blob('WndControl', '1', 'lbObjects'):
        errors.append('WndControl1 BLOB must exactly equal the original pre-rename BLOB')
    nulls = {}
    for field in ('strNote', 'iDeleteFlag', 'iCompileFlag'):
        a = left['WndControl']['1'][field]
        b = right['WndControl']['1'][field]
        nulls[field] = {'before_fingerprint': a, 'after_fingerprint': b, 'equal': a == b}
        if a != b:
            errors.append('Native DAO changed WndControl1 typed field: ' + field)
    count_fields = sum(len(row) for rows in left.values() for row in rows.values())
    return {'schema': 1, 'ok': not errors, 'status': 'strict_pass' if not errors else 'failed',
            'read_only_existing_exports_only': True, 'MCP_database_vendor_GUI_queue_accessed': False,
            'source': {'before_export': str(Path(before_directory).resolve()),
                       'before_project_sha256': before.index['sha256'],
                       'after_export': str(Path(after_directory).resolve()),
                       'after_project_sha256': after.index['sha256']},
            'tables': len(before.index['tables']), 'rows': sum(t['rows'] for t in before.index['tables']),
            'typed_fields_compared': count_fields,
            'fingerprint_difference_count': len(differences), 'differences': differences,
            'precisely_classified_fields': [list(v) for v in classified],
            'unclassified_differences': unknown,
            'mainctrl_null_and_compile_fields': nulls,
            'mainctrl_full_original_blob_equal': before.blob('WndControl', '1', 'lbObjects') == after.blob('WndControl', '1', 'lbObjects'),
            'narrow_native_password_tail_byte_attribution': narrow,
            'errors': errors,
            'scope': 'MainCtrl exact original full BLOB required; only observed page2 offset4147 EC->EB and page3 offset1968 CF->EA in proved length2/NUL-first ignored tail byte may differ. All other typed fields/rows/unknown System/account fingerprints are strict.',
            'runtime_or_hardware_or_generic_rename_claimed': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = verify(args.before, args.after)
    with Path(args.output).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'ok': result['ok'], 'fields': result['typed_fields_compared'],
                      'classified': len(result['precisely_classified_fields']),
                      'unclassified': len(result['unclassified_differences'])}))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
