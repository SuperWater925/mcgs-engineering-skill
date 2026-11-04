"""Only existing safe exports: exact MainCtrl strings and two proved NUL-tail bytes."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
import os

sys.dont_write_bytecode = True
_skill_roots = ([Path(os.environ['MCGS_SKILL_ROOT'])] if os.environ.get('MCGS_SKILL_ROOT') else []) + list(Path(__file__).resolve().parents)
_scripts = next((root / 'scripts' for root in _skill_roots if (root / 'scripts/native_tool.py').is_file()), None)
if _scripts is None:
    raise RuntimeError('Set MCGS_SKILL_ROOT to the installed skill folder for this historical fixture audit.')
sys.path.insert(0, str(_scripts))
import native_tool as nt
from mcs_window_archive import Reader, write_cstring

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[1]
OLD = '首页'
TEMP = 'BRIDGE_REF_首页改名验证'
EVIDENCE = TASK / 'verification/final-readback-0001/window-settings-semantics-evidence.json'


def sha(value):
    return hashlib.sha256(value).hexdigest()


def mainctrl(raw):
    # This is a fixture-specific suffix parser, not a generic WndControl codec.
    # Native C0DocCtrl Serialize orders the four arrays here. Prefix is immutable.
    r = Reader(raw)
    r.pos = 796
    arrays = []
    spans = []
    for kind in ('start_names', 'start_ids', 'mem_names', 'mem_ids'):
        count = r.count()
        if count > 32:
            raise ValueError('MainCtrl suffix array outside the narrow fixture')
        values = []
        for index in range(count):
            if kind.endswith('names'):
                at = r.pos
                text, encoded, wide = r.cstring()
                values.append(text)
                spans.append({'kind': kind, 'index': index, 'start': at, 'end': r.pos,
                              'value': text, 'wide': wide})
            else:
                values.append(r.u32())
        arrays.append((kind, values))
    return dict(arrays), spans, raw[:796], raw[r.pos:]


def audit(before_dir, after_dir):
    before, after = nt.Export(before_dir), nt.Export(after_dir)
    for export in (before, after):
        if export.index.get('project_family') != 'Pro' or not export.index.get('source_unchanged'):
            raise ValueError('Expected immutable Pro safe exports')
    a, b = before.blob('WndControl', '1', 'lbObjects'), after.blob('WndControl', '1', 'lbObjects')
    left, left_spans, prefix, tail = mainctrl(a)
    right, right_spans, prefix_after, tail_after = mainctrl(b)
    if left != {'start_names': ['首页'], 'start_ids': [2],
                'mem_names': ['首页', '状态监控'], 'mem_ids': [2, 4]}:
        raise ValueError('Unexpected exact MainCtrl original preimage')
    expected_temp = copy.deepcopy(left)
    expected_temp['start_names'][0] = TEMP
    expected_temp['mem_names'][0] = TEMP
    if right not in (left, expected_temp):
        raise ValueError('MainCtrl change is not either exact restored or exact two temporary names')
    if prefix != prefix_after or tail != tail_after:
        raise ValueError('MainCtrl prefix or remaining settings differs')
    reconstructed = b
    replacements = []
    for span in reversed(right_spans):
        if span['value'] != TEMP:
            continue
        encoded = write_cstring(OLD, span['wide'])
        reconstructed = reconstructed[:span['start']] + encoded + reconstructed[span['end']:]
        replacements.append(span)
    if reconstructed != a:
        raise ValueError('Replacing only precise two temporary CStrings does not rebuild all original bytes')
    pages = []
    for key, absolute, transition in (('2', 4147, (b'\x00\xec', b'\x00\xeb')),
                                      ('3', 1968, (b'\x00\xcf', b'\x00\xea'))):
        original = before.blob('WndUser', key, 'lbObjects')
        actual = after.blob('WndUser', key, 'lbObjects')
        wa, wb = nt.WindowArchive.parse(original), nt.WindowArchive.parse(actual)
        if wa.to_bytes() != original or wb.to_bytes() != actual:
            raise ValueError('Page archive does not round-trip')
        sa, sb = wa.settings(), wb.settings()
        differences = [i for i, (x, y) in enumerate(zip(original, actual)) if x != y]
        if len(original) != len(actual) or differences not in ([], [absolute]):
            raise ValueError('Page differs outside exact one-byte transition')
        if differences and (sa.password_data, sb.password_data) != transition:
            raise ValueError('Unexpected exact short-block byte transition')
        if len(sa.password_data) != 2 or len(sb.password_data) != 2 or sa.password_data[:1] != b'\0' or sb.password_data[:1] != b'\0':
            raise ValueError('Outside already-proved two-byte NUL-first block')
        repaired_settings = copy.deepcopy(sb)
        repaired_settings.password_data = sa.password_data
        repaired_page = copy.deepcopy(wb)
        repaired_page.trailer = repaired_settings.to_bytes()
        if repaired_page.to_bytes() != original:
            raise ValueError('Other page prefix/control/settings/event bytes differ')
        pages.append({'page_id': int(key), 'bytes': len(original), 'absolute_changed_offsets': differences,
                      'field': 'WindowSettings.password_data', 'field_bytes': 2,
                      'changed_field_offset': 1 if differences else None,
                      'before_block_sha256': sha(sa.password_data), 'after_block_sha256': sha(sb.password_data),
                      'first_ansi_nul_offset': 0, 'plaintext_not_output': True,
                      'controls_prefix_all21_properties_events_exact': True,
                      'full_original_archive_rebuilt_by_only_restoring_ignored_byte': True,
                      'temporary_name_residual': TEMP.encode('utf-16le') in actual or TEMP.encode() in actual})
    remaining = bool(replacements)
    return {'schema': 1, 'ok': not remaining, 'status': 'failed_mainctrl_temporary_names_persisted' if remaining else 'strict_restoration_passed',
            'read_only_existing_exports_only': True, 'database_or_vendor_or_gui_access': False,
            'mainctrl': {'before_bytes': len(a), 'after_bytes': len(b), 'before_sha256': sha(a), 'after_sha256': sha(b),
                         'before_arrays': left, 'after_arrays': right, 'temporary_name_residual_count': len(replacements),
                         'temporary_name_cstring_spans': list(reversed(replacements)),
                         'prefix_first796_and_remaining_tail_exact': True,
                         'all_other_bytes_exact_after_only_two_cstring_reconstruction': True,
                         'storage_name_id_divergence_unresolved': remaining, 'name_ids_unchanged': True},
            'pages': pages,
            'existing_password_semantics_proof': {'file': str(EVIDENCE), 'sha256': sha(EVIDENCE.read_bytes()),
                'scope': 'Only these two specified pages and observed one-byte changes; length2/ANSI NUL at0, native crypto skips<8 and FromAnsi cb=-1 ignores byte1. No field-wide exemption.'},
            'before': {'export': str(Path(before_dir).resolve()), 'project_sha256': before.index['sha256']},
            'after': {'export': str(Path(after_dir).resolve()), 'project_sha256': after.index['sha256']},
            'whole_project_or_other_fields_acceptance_claimed': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.before, args.after)
    with Path(args.output).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'ok': result['ok'], 'status': result['status'],
                      'temporary_names': result['mainctrl']['temporary_name_residual_count']}))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
