"""Check release source and ZIPs for retained disassembly evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import BadZipFile, ZipFile
import zlib

from check_repository import MANIFEST, package_files


CATALOG = 'assets/pro-native-bridge/abi-adapter/catalogs/reference.json.gz'
CATALOG_SCHEMA = 'mcgs-native-reference-catalog/v1'
SIGNATURE_ITEM = ('signatures', '[]')
TRANSFER_ITEM = SIGNATURE_ITEM + ('transfers', '[]')
TARGET_SIGNATURE_ITEM = TRANSFER_ITEM + ('target_signature_chain', '[]')
TOKEN_POSITIONS = {SIGNATURE_ITEM + ('tokens', '[]'), TARGET_SIGNATURE_ITEM + ('tokens', '[]')}
TRANSFER_POSITIONS = {TRANSFER_ITEM, TARGET_SIGNATURE_ITEM + ('transfers', '[]')}
TRANSFER_KEYS = {
    'mnemonic', 'kind', 'immediate_offset', 'immediate_size', 'inside_signature_offset',
    'instruction_index', 'instruction_offset', 'reference_target_rva',
}
TRANSFER_CONTEXT_KEYS = TRANSFER_KEYS | {'target_context_status', 'target_signature_chain'}
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_DEPTH = 4
EXECUTABLE_SUFFIXES = {'.exe', '.dll', '.pdb', '.sys', '.ocx', '.msi'}
UNSUPPORTED_ARCHIVE_SUFFIXES = {'.7z', '.rar', '.tar', '.tgz', '.bz2', '.xz'}
UPDATE_TOOLS = {
    'payload/McgsStart.exe', 'payload/tools/McgsStart.exe', 'payload/tools/InstallerChoice.exe',
    'payload/engine/business/McgsEngineering.Portable.dll',
    'payload/engine/business/stu/McgsStuBusinessEngine.dll',
}
UPDATE_BRIDGE_TOOL = re.compile(
    r'payload/engine/bridge/McgsPortable(?:Attach_v\d+\.exe|(?:Bridge|Hook)_v\d+\.dll)\Z'
)
NORMALIZED_MNEMONIC = re.compile(r'[a-z][a-z0-9_]*(?: [a-z][a-z0-9_]*)*\Z')
NORMALIZED_OPERAND_PART = re.compile(r'[a-zA-Z0-9_]+\Z')
INSTRUCTION_LINE = re.compile(
    r'^\s*(?:0x)?[\da-fA-F]{4,16}:?\s+(?:[\da-fA-F]{2}\s+){1,16}'
    r'[a-zA-Z][a-zA-Z0-9_.]*(?:\s+.*)?$'
)
JSON_FENCE = re.compile(r'^\s*```json\s*\n(.*?)^\s*```\s*$', re.I | re.M | re.S)


def catalog_name(kind: str) -> str:
    return {'source': '', 'skill': 'mcgs-engineering/', 'update': 'payload/skill/'}[kind] + CATALOG


def normalized_operand(operand) -> bool:
    return isinstance(operand, list) and len(operand) in {3, 7} and all(
        part is None or type(part) is int or isinstance(part, str)
        and len(part) <= 24 and NORMALIZED_OPERAND_PART.fullmatch(part)
        for part in operand
    )


def allowed_catalog_record(position: tuple[str, ...], record: dict) -> str | None:
    mnemonic = record.get('mnemonic')
    if not isinstance(mnemonic, str) or len(mnemonic) > 24 or not NORMALIZED_MNEMONIC.fullmatch(mnemonic):
        return None
    if position in TOKEN_POSITIONS and record.keys() == {'mnemonic', 'operands'}:
        operands = record['operands']
        if isinstance(operands, list) and all(normalized_operand(operand) for operand in operands):
            return 'normalized_signature_tokens'
    if position in TRANSFER_POSITIONS and record.keys() in (TRANSFER_KEYS, TRANSFER_CONTEXT_KEYS):
        return 'transfer_mnemonics'
    return None


def walk_records(document):
    stack = [((), document)]
    while stack:
        position, obj = stack.pop()
        if isinstance(obj, dict):
            yield position, obj
            stack.extend((position + (key,), value) for key, value in obj.items())
        elif isinstance(obj, list):
            stack.extend((position + ('[]',), item) for item in obj)


def instruction_dump(text: str, minimum=2) -> bool:
    consecutive = 0
    for line in text.splitlines():
        if INSTRUCTION_LINE.fullmatch(line):
            consecutive += 1
            if consecutive >= minimum:
                return True
        else:
            consecutive = 0
    return False


class Audit:
    def __init__(self, kind: str):
        self.kind = kind
        self.files_scanned = 0
        self.gzip_members = 0
        self.catalog_exceptions = Counter()
        self.violations = {}

    def flag(self, name: str, violation: str):
        self.violations.setdefault(name, Counter())[violation] += 1

    def scan_document(self, name: str, document, *, catalog=False):
        for position, record in walk_records(document):
            if isinstance(record.get('mnemonic'), str) and record['mnemonic'].strip():
                exception = allowed_catalog_record(position, record) if catalog else None
                if exception:
                    self.catalog_exceptions[exception] += 1
                else:
                    self.flag(name, 'instruction-record')
            if isinstance(record.get('complete_disassembly'), bool):
                self.flag(name, 'complete-disassembly')
            for field in ('jump_chain', 'basic_blocks'):
                value = record.get(field)
                schema_definition = isinstance(value, dict) and position[-1:] == ('properties',)
                if isinstance(value, (dict, list)) and not schema_definition:
                    self.flag(name, 'disassembly-control-flow')
            for field in ('code', 'instructions', 'disassembly'):
                value = record.get(field)
                if isinstance(value, str) and instruction_dump(value, minimum=1):
                    self.flag(name, 'instruction-listing')
                elif isinstance(value, list) and value and all(isinstance(row, str) for row in value):
                    if instruction_dump('\n'.join(value), minimum=1):
                        self.flag(name, 'instruction-listing')

    def scan_member(self, name: str, data: bytes, depth=0):
        self.files_scanned += 1
        if depth > MAX_ARCHIVE_DEPTH or len(data) > MAX_MEMBER_BYTES:
            self.flag(name, 'archive-scan-limit')
            return
        path = PurePosixPath(name.rsplit('!', 1)[-1])
        suffix = path.suffix.lower()
        if suffix in {'.zip', '.whl'} or data.startswith(b'PK\x03\x04'):
            self.scan_zip(io.BytesIO(data), name + '!', depth + 1)
            return
        if suffix in UNSUPPORTED_ARCHIVE_SUFFIXES:
            self.flag(name, 'unsupported-archive')
            return
        compressed = suffix == '.gz' or data.startswith(b'\x1f\x8b')
        if compressed:
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed_file:
                    data = compressed_file.read(MAX_MEMBER_BYTES + 1)
            except (EOFError, OSError, zlib.error):
                self.flag(name, 'invalid-gzip')
                return
            self.gzip_members += 1
            if len(data) > MAX_MEMBER_BYTES:
                self.flag(name, 'archive-scan-limit')
                return
            if suffix == '.gz':
                suffix = PurePosixPath(path.stem).suffix.lower()
            if data.startswith((b'\x1f\x8b', b'PK\x03\x04')):
                self.scan_member(name + '!' + path.stem, data, depth + 1)
                return
        if suffix in EXECUTABLE_SUFFIXES or data.startswith(b'MZ'):
            allowed_tool = self.kind == 'update' and (name in UPDATE_TOOLS or UPDATE_BRIDGE_TOOL.fullmatch(name))
            if not allowed_tool:
                self.flag(name, 'unexpected-executable-or-debug-file')
            return
        encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            self.flag(name, 'unsupported-encoding-or-binary')
            return
        if '\x00' in text:
            self.flag(name, 'unsupported-encoding-or-binary')
        elif suffix == '.json':
            self.scan_json(name, text, compressed)
        else:
            if instruction_dump(text):
                self.flag(name, 'instruction-listing')
            if text.lstrip().startswith(('{', '[')):
                try:
                    document = json.loads(text)
                except (ValueError, RecursionError):
                    pass
                else:
                    self.scan_document(name, document)
            if suffix == '.md':
                for block in JSON_FENCE.findall(text):
                    try:
                        document = json.loads(block)
                    except (ValueError, RecursionError):
                        continue
                    self.scan_document(name, document)

    def scan_json(self, name: str, text: str, compressed: bool):
        try:
            document = json.loads(text)
        except (ValueError, RecursionError):
            self.flag(name, 'invalid-json')
            return
        exact_catalog = compressed and name == catalog_name(self.kind)
        catalog = exact_catalog and isinstance(document, dict) and document.get('schema') == CATALOG_SCHEMA
        if exact_catalog and not catalog:
            self.flag(name, 'unexpected-catalog-schema')
        self.scan_document(name, document, catalog=catalog)

    def scan_zip(self, source, prefix='', depth=0):
        try:
            with ZipFile(source) as archive:
                seen = set()
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    name = prefix + info.filename
                    path = info.filename.split('/')
                    key = info.filename.casefold()
                    if any(part in {'', '.', '..'} for part in path) or '\\' in info.filename or ':' in info.filename:
                        self.flag(name, 'invalid-archive-path')
                    elif key in seen:
                        self.flag(name, 'duplicate-archive-path')
                    elif info.file_size > MAX_MEMBER_BYTES:
                        self.flag(name, 'archive-scan-limit')
                    else:
                        self.scan_member(name, archive.read(info), depth)
                    seen.add(key)
        except (OSError, BadZipFile, RuntimeError, zlib.error):
            self.flag(prefix or '<archive>', 'invalid-or-unsupported-zip')

    def scan_source(self, root: Path):
        try:
            files = package_files(root)
            if (root / MANIFEST).is_file():
                files.append(root / MANIFEST)
            for path in files:
                name = path.relative_to(root).as_posix()
                if path.stat().st_size > MAX_MEMBER_BYTES:
                    self.flag(name, 'archive-scan-limit')
                else:
                    self.scan_member(name, path.read_bytes())
        except (OSError, ValueError):
            self.flag('<source>', 'invalid-or-unreadable-source')

    def report(self):
        return {
            'passed': not self.violations,
            'files_scanned': self.files_scanned,
            'gzip_members_decoded': self.gzip_members,
            'catalog_exceptions': dict(self.catalog_exceptions),
            'violations': self.violations,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument('--root', type=Path, help='Source directory, defaults to this repository')
    paths.add_argument('--zip', type=Path, help='Packaged skill ZIP')
    paths.add_argument('--update-zip', type=Path, help='Packaged update ZIP with first-party tools')
    args = parser.parse_args()
    if args.update_zip:
        audit = Audit('update')
        audit.scan_zip(args.update_zip)
    elif args.zip:
        audit = Audit('skill')
        audit.scan_zip(args.zip)
    else:
        root = (args.root or Path(__file__).resolve().parents[1]).resolve()
        if not (root / 'SKILL.md').is_file():
            parser.error('Source root must contain SKILL.md')
        audit = Audit('source')
        audit.scan_source(root)
    if not audit.files_scanned:
        audit.flag('<source>' if audit.kind == 'source' else '<archive>', 'empty-input')
    print(json.dumps(audit.report(), ensure_ascii=False, indent=2))
    return 1 if audit.violations else 0


if __name__ == '__main__':
    raise SystemExit(main())
