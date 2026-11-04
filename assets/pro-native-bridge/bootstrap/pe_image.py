"""Read a supplied image's PE32/I386 identity without a release or hash whitelist."""
import hashlib
from pathlib import Path
import struct


def pe32_identity(editor):
    data = Path(editor).read_bytes()

    def invalid(reason):
        raise ValueError('Online bridge requires a PE32/I386 executable: ' + reason)

    if len(data) < 64 or data[:2] != b'MZ':
        invalid('missing or truncated DOS header')
    pe = struct.unpack_from('<I', data, 60)[0]
    if pe < 64 or pe + 24 > len(data) or data[pe:pe + 4] != b'PE\0\0':
        invalid('missing or truncated PE signature/COFF header')
    machine, sections, _, _, _, optional_size, flags = struct.unpack_from('<HHIIIHH', data, pe + 4)
    if machine != 0x14c:
        invalid('machine 0x%04x; I386 (0x014c) is required, not x64/ARM' % machine)
    optional = pe + 24
    if optional_size < 96 or optional + optional_size > len(data):
        invalid('truncated PE32 optional header')
    magic = struct.unpack_from('<H', data, optional)[0]
    if magic != 0x10b:
        invalid('optional-header magic 0x%04x; PE32 (0x010b) is required' % magic)
    if not flags & 0x2 or flags & 0x2000:
        invalid('an executable image is required, not a DLL')
    table = optional + optional_size
    if not 1 <= sections <= 96 or table + sections * 40 > len(data):
        invalid('missing or truncated section table')
    for i in range(sections):
        raw_size, raw_offset = struct.unpack_from('<II', data, table + i * 40 + 16)
        if raw_size and (raw_offset == 0 or raw_offset + raw_size > len(data)):
            invalid('section %d raw data exceeds the image' % i)
    return {'binary_sha256': hashlib.sha256(data).hexdigest(), 'machine': 'I386',
            'pe_format': 'PE32', 'machine_code': machine, 'optional_header_magic': magic}
