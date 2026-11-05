"""Read own x86 managed DLL metadata without CLR loading or native calls.

Only bounded PE/ECMA metadata needed by deployment is interpreted. This checks
the compiled configuration constant and entry type; it does not attest business
ABI behavior or invoke an assembly, constructor, reflection or vendor module.
"""
import struct


class ManagedImage:
    def __init__(self, raw):
        self.raw = bytes(raw)
        self._need(len(raw) >= 64 and raw[:2] == b'MZ', 'Missing DOS header')
        pe = self._unpack('<I', 60)
        self._need(self._read(pe, 4) == b'PE\0\0', 'Missing PE signature')
        machine, count, _, _, _, size, flags = self._unpack('<HHIIIHH', pe + 4)
        self._need(machine == 0x14c and flags & 0x2000 and flags & 2, 'Expected own I386 DLL')
        optional = pe + 24
        self._need(size >= 216 and self._unpack('<H', optional) == 0x10b, 'Expected PE32 managed DLL')
        self._read(optional, size)
        self.headers = self._unpack('<I', optional + 60)
        self._need(self._unpack('<I', optional + 92) >= 15, 'Missing CLI data directory')
        self.sections = []
        for index in range(count):
            at = optional + size + index * 40
            self._read(at, 40)
            virtual, rva, length, offset = self._unpack('<IIII', at + 8)
            self._read(offset, length)
            self.sections.append((rva, max(virtual, length), offset, length))
        cli, cli_size = self._unpack('<II', optional + 96 + 14 * 8)
        self._need(cli and cli_size >= 72, 'Missing CLI header')
        at = self._offset(cli, 72)
        self._need(self._unpack('<I', at) >= 72, 'Truncated CLI header')
        metadata, length, corflags = self._unpack('<III', at + 8)
        self._need(corflags & 1 and corflags & 2 and not corflags & 0x10, 'Expected x86 IL-only managed DLL')
        self.meta = self._read(self._offset(metadata, length), length)
        self._need(self.meta[:4] == b'BSJB', 'Missing CLR metadata signature')
        version_size = self._mu('<I', 12)
        position = (16 + version_size + 3) & ~3
        _, streams = self._mu('<HH', position)
        position += 4
        self.streams = {}
        for _ in range(streams):
            offset, size = self._mu('<II', position)
            position += 8
            end = self.meta.find(b'\0', position, min(position + 32, len(self.meta)))
            self._need(end >= position, 'Unterminated metadata stream name')
            name = self.meta[position:end].decode('ascii')
            self._need(name not in self.streams and offset + size <= len(self.meta), 'Invalid metadata stream extent')
            self.streams[name] = self.meta[offset:offset + size]
            position = (end + 4) & ~3
        self.strings = self.streams['#Strings']
        self.blobs = self.streams['#Blob']
        self.tables = self.streams.get('#~')
        self._need(self.tables is not None and len(self.tables) >= 24, 'Missing metadata tables')
        heap_sizes = self.tables[6]
        self.string_size, self.guid_size, self.blob_size = [4 if heap_sizes & bit else 2 for bit in (1, 2, 4)]
        valid = struct.unpack_from('<Q', self.tables, 8)[0]
        self.rows = {}
        position = 24
        for table in range(64):
            if valid & (1 << table):
                self._need(position + 4 <= len(self.tables), 'Truncated table row counts')
                self.rows[table] = struct.unpack_from('<I', self.tables, position)[0]
                position += 4
        self._need(not self.rows.get(3) and not self.rows.get(5), 'Pointer metadata tables are outside the own compiler contract')
        self.offsets = {}
        s, g, b = self.string_size, self.guid_size, self.blob_size
        sizes = {
            0: 2+s+3*g, 1: self._coded(2, (0, 26, 35, 1))+2*s,
            2: 4+2*s+self._coded(2, (2, 1, 27))+self._index(4)+self._index(6),
            3: self._index(4), 4: 2+s+b, 5: self._index(6),
            6: 8+s+b+self._index(8), 7: self._index(8), 8: 4+s,
            9: self._index(2)+self._coded(2, (2, 1, 27)),
            10: self._coded(3, (2, 1, 26, 6, 27))+s+b,
            11: 2+self._coded(2, (4, 8, 23))+b,
        }
        self.sizes = sizes
        for table in range(12):
            self.offsets[table] = position
            position += self.rows.get(table, 0) * sizes[table]
        self._need(position <= len(self.tables), 'Truncated metadata tables through Constant')

    @staticmethod
    def _need(value, message):
        if not value:
            raise ValueError(message)

    def _read(self, offset, size):
        self._need(offset >= 0 and size >= 0 and offset + size <= len(self.raw), 'PE extent exceeds file')
        return self.raw[offset:offset + size]

    def _unpack(self, fmt, offset):
        value = struct.unpack(fmt, self._read(offset, struct.calcsize(fmt)))
        return value[0] if len(value) == 1 else value

    def _mu(self, fmt, offset):
        self._need(offset >= 0 and offset + struct.calcsize(fmt) <= len(self.meta), 'Metadata extent exceeds stream')
        value = struct.unpack_from(fmt, self.meta, offset)
        return value[0] if len(value) == 1 else value

    def _offset(self, rva, size):
        if rva < self.headers and rva + size <= self.headers:
            self._read(rva, size)
            return rva
        matches = [(off+rva-start) for start, _, off, length in self.sections if start <= rva and rva+size <= start+length]
        self._need(len(matches) == 1, 'RVA is not uniquely backed by file bytes')
        return matches[0]

    def _index(self, table):
        return 4 if self.rows.get(table, 0) >= 65536 else 2

    def _coded(self, bits, tables):
        return 4 if max((self.rows.get(table, 0) for table in tables), default=0) >= 1 << (16-bits) else 2

    def _uint(self, offset, size):
        return int.from_bytes(self.tables[offset:offset+size], 'little')

    def _string(self, index):
        self._need(0 <= index < len(self.strings), 'String heap index exceeds stream')
        end = self.strings.find(b'\0', index)
        self._need(end >= 0, 'Unterminated metadata string')
        return self.strings[index:end].decode('utf-8')

    def _blob(self, index):
        self._need(0 <= index < len(self.blobs), 'Blob index exceeds heap')
        first = self.blobs[index]
        if first < 0x80:
            length, size = first, 1
        elif first < 0xc0:
            self._need(index+2 <= len(self.blobs), 'Truncated compressed blob length')
            length, size = ((first & 0x3f) << 8) | self.blobs[index+1], 2
        else:
            self._need(first < 0xe0 and index+4 <= len(self.blobs), 'Invalid compressed blob length')
            length, size = int.from_bytes(self.blobs[index:index+4], 'big') & 0x1fffffff, 4
        self._need(index+size+length <= len(self.blobs), 'Blob exceeds heap')
        return self.blobs[index+size:index+size+length]

    def type_fields(self, full_name):
        result = []
        for row in range(self.rows.get(2, 0)):
            at = self.offsets[2] + row*self.sizes[2] + 4
            name = self._string(self._uint(at, self.string_size)); at += self.string_size
            namespace = self._string(self._uint(at, self.string_size)); at += self.string_size
            if (namespace+'.' if namespace else '')+name != full_name:
                continue
            at += self._coded(2, (2, 1, 27))
            start = self._uint(at, self._index(4))
            if row+1 < self.rows[2]:
                next_at = self.offsets[2]+(row+1)*self.sizes[2]+4+2*self.string_size+self._coded(2, (2, 1, 27))
                end = self._uint(next_at, self._index(4))
            else:
                end = self.rows.get(4, 0)+1
            self._need(1 <= start <= end <= self.rows.get(4, 0)+1, 'Invalid TypeDef field range')
            result.extend(range(start, end))
        return result

    def string_constant(self, full_name, field_name):
        wanted = []
        for field in self.type_fields(full_name):
            at = self.offsets[4]+(field-1)*self.sizes[4]
            if self._string(self._uint(at+2, self.string_size)) == field_name:
                wanted.append(field)
        self._need(len(wanted) == 1, 'Expected one compiled binding field: '+full_name+'.'+field_name)
        values = []
        for row in range(self.rows.get(11, 0)):
            at = self.offsets[11]+row*self.sizes[11]
            parent = self._uint(at+2, self._coded(2, (4, 8, 23)))
            if parent == wanted[0] << 2:
                self._need(self._uint(at, 2) == 0x0e, 'Compiled binding field is not a string constant')
                blob = self._uint(at+2+self._coded(2, (4, 8, 23)), self.blob_size)
                values.append(self._blob(blob).decode('utf-16le'))
        self._need(len(values) == 1, 'Expected one compiled binding constant')
        return values[0]


def verify_scope_binding(raw, scope_sha256, *, bootstrap=False):
    image = ManagedImage(raw)
    name = 'McgsInternalBridge.BootstrapLayout' if bootstrap else 'McgsInternalBridge.NativeEngineeringDeliveryLayout'
    actual = image.string_constant(name, 'ExpectedConfigurationSha256')
    if actual != scope_sha256:
        raise ValueError('Compiled own DLL configuration SHA differs from the selected scope')
    return {'machine': 'I386', 'format': 'PE32', 'managed': True, 'compiled_scope_sha256': actual}
