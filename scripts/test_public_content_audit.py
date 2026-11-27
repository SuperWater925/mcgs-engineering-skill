"""Exercise release scan rules with isolated, synthetic contents."""

import gzip
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from audit_public_content import Audit, CATALOG_SCHEMA, TRANSFER_KEYS, catalog_name


def json_bytes(document):
    return json.dumps(document).encode('utf-8')


def archive_bytes(members):
    raw = io.BytesIO()
    with ZipFile(raw, 'w') as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return io.BytesIO(raw.getvalue())


class PublicContentTests(unittest.TestCase):
    def setUp(self):
        self.token = {'mnemonic': 'example', 'operands': [['symbol', 'placeholder', 8]]}
        self.transfer = dict.fromkeys(TRANSFER_KEYS, 0) | {'mnemonic': 'example'}

    def test_only_known_catalog_shapes_are_exempt(self):
        context = {'tokens': [self.token], 'transfers': [self.transfer]}
        transfer_with_context = self.transfer | {
            'target_context_status': 'available', 'target_signature_chain': [context],
        }
        signature = {'tokens': [self.token], 'transfers': [transfer_with_context]}
        catalog = {'schema': CATALOG_SCHEMA, 'signatures': [signature]}
        name = catalog_name('skill')
        audit = Audit('skill')
        audit.scan_zip(archive_bytes({name: gzip.compress(json_bytes(catalog))}))
        self.assertEqual(audit.report()['catalog_exceptions'], {
            'normalized_signature_tokens': 2, 'transfer_mnemonics': 2,
        })
        self.assertTrue(audit.report()['passed'])

        catalog['appendix'] = {'instructions': [self.token]}
        audit = Audit('skill')
        audit.scan_member(name, gzip.compress(json_bytes(catalog)))
        self.assertEqual(audit.violations[name], {'instruction-record': 1})

    def test_moved_or_expanded_catalog_tokens_fail(self):
        catalog = {'schema': CATALOG_SCHEMA, 'signatures': [{'tokens': [self.token]}]}
        audit = Audit('source')
        audit.scan_member('elsewhere.json.gz', gzip.compress(json_bytes(catalog)))
        self.assertEqual(audit.violations['elsewhere.json.gz'], {'instruction-record': 1})

        catalog['signatures'][0]['tokens'][0] = self.token | {'raw_text': 'example listing'}
        audit.scan_member(catalog_name('source'), gzip.compress(json_bytes(catalog)))
        self.assertEqual(audit.violations[catalog_name('source')], {'instruction-record': 1})

    def test_schema_names_and_ordinary_references_pass(self):
        audit = Audit('source')
        audit.scan_member('references/schema.json', json_bytes({
            'properties': {
                'mnemonic': {'type': 'string'}, 'instructions': {'type': 'array'},
                'complete_disassembly': {'type': 'boolean'}, 'basic_blocks': {'type': 'object'},
                'jump_chain': {'type': 'array'},
            },
        }))
        audit.scan_member('README.md', b'Reference the `instructions` field when using other tools.')
        audit.scan_member('notes.json', json_bytes({'instructions': ['Read the setup guide'], 'code': 1}))
        self.assertTrue(audit.report()['passed'])

    def test_control_flow_and_fenced_raw_instructions_fail(self):
        audit = Audit('source')
        audit.scan_member('evidence.json', json_bytes({
            'complete_disassembly': True, 'jump_chain': ['synthetic'], 'basic_blocks': {'block': []},
        }))
        audit.scan_member('README.md', b'```json\n' + json_bytes({'instructions': [self.token]}) + b'\n```\n')
        self.assertEqual(audit.violations['evidence.json'], {
            'complete-disassembly': 1, 'disassembly-control-flow': 2,
        })
        self.assertEqual(audit.violations['README.md'], {'instruction-record': 1})

    def test_nested_archive_checks_gzip_contents(self):
        nested = archive_bytes({'evidence.json.gz': gzip.compress(json_bytes({'code': [self.token]}))})
        audit = Audit('skill')
        audit.scan_zip(archive_bytes({'nested.zip': nested.getvalue()}))
        self.assertEqual(audit.gzip_members, 1)
        self.assertEqual(audit.violations['nested.zip!evidence.json.gz'], {'instruction-record': 1})

    def test_gzip_under_alternate_extension_is_still_scanned(self):
        audit = Audit('skill')
        audit.scan_member('package.dat', gzip.compress(json_bytes({'code': [self.token]})))
        self.assertEqual(audit.violations['package.dat'], {'instruction-record': 1})

    def test_only_update_mode_allows_first_party_executables(self):
        audit = Audit('update')
        shipped = 'payload/tools/McgsStart.exe'
        audit.scan_member(shipped, b'MZ')
        audit.scan_member('payload/vendor/program.dll', b'MZ')
        self.assertNotIn(shipped, audit.violations)
        self.assertEqual(audit.violations['payload/vendor/program.dll'], {'unexpected-executable-or-debug-file': 1})
        audit = Audit('skill')
        audit.scan_member(shipped, b'MZ')
        self.assertEqual(audit.violations[shipped], {'unexpected-executable-or-debug-file': 1})

    def test_scan_root_checks_untracked_public_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'SKILL.md').write_text('# Skill', encoding='utf-8')
            (root / 'evidence.json').write_bytes(json_bytes({'instructions': [self.token]}))
            ignored = root / 'local-artifacts'
            ignored.mkdir()
            (ignored / 'private.json').write_bytes(json_bytes(self.token))
            audit = Audit('source')
            audit.scan_source(root)
            self.assertEqual(audit.violations, {'evidence.json': {'instruction-record': 1}})


if __name__ == '__main__':
    unittest.main()
