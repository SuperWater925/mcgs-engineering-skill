"""Strict, file-only PE32/I386 reader for the ABI preparation tools.

No code is loaded, registered or executed.  File SHA values returned by
``identity`` are observations, never software/build admission rules.  RVA reads
are deliberately limited to file-backed bytes; virtual zero-filled tails are
not invented as disassembly or RTTI evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import struct
from typing import Iterator


class PEFormatError(ValueError):
    """The supplied bytes do not provide an unambiguous PE32 file mapping."""


@dataclass(frozen=True)
class Section:
    name: str
    rva: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int

    @property
    def executable(self) -> bool:
        return bool(self.characteristics & 0x20000000)

    @property
    def readable(self) -> bool:
        return bool(self.characteristics & 0x40000000)

    @property
    def writable(self) -> bool:
        return bool(self.characteristics & 0x80000000)

    @property
    def mapped_size(self) -> int:
        return max(self.virtual_size, self.raw_size)


class PE32:
    """Read PE sections, HIGHLOW sites, exports and imports from actual bytes.

    ``source`` is a filesystem path or a bytes-like object.  DLL images are
    supported as well as EXE images.  No fixed section count, image digest,
    product name or software release is required.
    """

    def __init__(self, source: str | os.PathLike[str] | bytes | bytearray | memoryview):
        if isinstance(source, (bytes, bytearray, memoryview)):
            self.path: Path | None = None
            self.data = bytes(source)
        else:
            self.path = Path(source).resolve()
            self.data = self.path.read_bytes()
        self.sections: list[Section] = []
        self.directories: list[tuple[int, int]] = []
        self.relocations: set[int] = set()
        self.other_relocations: dict[int, list[int]] = {}
        self.exports: dict[str, dict] = {}
        self.exports_by_ordinal: dict[int, dict] = {}
        self.imports_by_iat: dict[int, dict] = {}
        self.import_modules: list[str] = []
        self._parse_headers()
        self._parse_relocations()
        self._parse_exports()
        self._parse_imports()

    def _fail(self, message: str):
        raise PEFormatError(message)

    def _file(self, offset: int, size: int) -> bytes:
        if type(offset) is not int or type(size) is not int or offset < 0 or size < 0 or offset + size > len(self.data):
            self._fail(f"File extent outside image: offset={offset!r}, size={size!r}")
        return self.data[offset:offset + size]

    def _unpack(self, fmt: str, offset: int):
        values = struct.unpack(fmt, self._file(offset, struct.calcsize(fmt)))
        return values[0] if len(values) == 1 else values

    def _parse_headers(self):
        if len(self.data) < 64 or self.data[:2] != b"MZ":
            self._fail("Missing or truncated DOS MZ header")
        self.pe_offset = self._unpack("<I", 0x3c)
        if self.pe_offset < 64 or self._file(self.pe_offset, 4) != b"PE\0\0":
            self._fail("Missing PE signature at the declared DOS e_lfanew")
        machine, count, timestamp, _, _, optional_size, flags = self._unpack("<HHIIIHH", self.pe_offset + 4)
        if machine != 0x14c:
            self._fail(f"PE machine 0x{machine:04x} is not I386")
        self.machine = machine
        self.timestamp = timestamp
        self.characteristics = flags
        self.is_dll = bool(flags & 0x2000)
        if not flags & 0x0002:
            self._fail("COFF image is not marked executable")
        optional = self.pe_offset + 24
        if optional_size < 96:
            self._fail("Truncated PE32 optional header")
        self._file(optional, optional_size)
        if self._unpack("<H", optional) != 0x10b:
            self._fail("Optional header is not PE32 (0x010b)")
        self.entry_rva = self._unpack("<I", optional + 16)
        self.image_base = self._unpack("<I", optional + 28)
        self.section_alignment = self._unpack("<I", optional + 32)
        self.file_alignment = self._unpack("<I", optional + 36)
        self.image_size = self._unpack("<I", optional + 56)
        self.headers_size = self._unpack("<I", optional + 60)
        self.subsystem = self._unpack("<H", optional + 68)
        self.dll_characteristics = self._unpack("<H", optional + 70)
        if not self.section_alignment or not self.file_alignment or not self.image_size:
            self._fail("Zero PE image size/alignment")
        if self.image_base + self.image_size > 0x100000000:
            self._fail("Preferred PE32 image VA extent exceeds 32-bit address space")
        if not 0 < self.headers_size <= min(self.image_size, len(self.data)):
            self._fail("SizeOfHeaders exceeds backed file/image extent")
        if self.entry_rva >= self.image_size and self.entry_rva != 0:
            self._fail("Entry point RVA exceeds SizeOfImage")
        directories = self._unpack("<I", optional + 92)
        if directories > (optional_size - 96) // 8:
            self._fail("Declared data directories exceed optional header")
        self.directories = [self._unpack("<II", optional + 96 + index * 8) for index in range(directories)]
        table = optional + optional_size
        if count == 0 or count > (len(self.data) - table) // 40:
            self._fail("Section table is absent or exceeds the file")
        self._file(table, count * 40)
        if table + count * 40 > self.headers_size:
            self._fail("Section table exceeds SizeOfHeaders")
        for index in range(count):
            at = table + index * 40
            name = self._file(at, 8).split(b"\0", 1)[0].decode("ascii", errors="replace")
            virtual_size, rva, raw_size, raw_offset = self._unpack("<IIII", at + 8)
            characteristics = self._unpack("<I", at + 36)
            if raw_size:
                if raw_offset < self.headers_size:
                    self._fail(f"Section {name!r} raw bytes overlap headers")
                self._file(raw_offset, raw_size)
            mapped = max(virtual_size, raw_size)
            if rva + mapped > self.image_size or rva + mapped > 0x100000000:
                self._fail(f"Section {name!r} RVA extent exceeds SizeOfImage")
            self.sections.append(Section(name, rva, virtual_size, raw_offset, raw_size, characteristics))
        intervals = sorted((s.rva, s.rva + s.mapped_size, s.name) for s in self.sections if s.mapped_size)
        for before, after in zip(intervals, intervals[1:]):
            if after[0] < before[1]:
                self._fail(f"Overlapping virtual section mapping: {before[2]!r}/{after[2]!r}")
        raw = sorted((s.raw_offset, s.raw_offset + s.raw_size, s.name) for s in self.sections if s.raw_size)
        for before, after in zip(raw, raw[1:]):
            if after[0] < before[1]:
                self._fail(f"Overlapping raw section mapping: {before[2]!r}/{after[2]!r}")

    def section_for_rva(self, rva: int) -> Section | None:
        if type(rva) is not int or rva < 0 or rva >= self.image_size:
            return None
        return next((s for s in self.sections if s.rva <= rva < s.rva + s.mapped_size), None)

    def rva_to_offset(self, rva: int, size: int = 1) -> int:
        if type(rva) is not int or type(size) is not int or rva < 0 or size < 0 or rva + size > self.image_size:
            self._fail(f"RVA extent outside image: rva={rva!r}, size={size!r}")
        if rva < self.headers_size and rva + size <= self.headers_size:
            self._file(rva, size)
            return rva
        section = self.section_for_rva(rva)
        if section is None or rva - section.rva + size > section.raw_size:
            self._fail(f"RVA is not completely file-backed: rva=0x{rva:x}, size={size}")
        offset = section.raw_offset + rva - section.rva
        self._file(offset, size)
        return offset

    def read(self, rva: int, size: int) -> bytes:
        offset = self.rva_to_offset(rva, size)
        return self._file(offset, size)

    def u32(self, rva: int) -> int:
        return struct.unpack("<I", self.read(rva, 4))[0]

    def va_to_rva(self, va: int) -> int:
        if type(va) is not int or not self.image_base <= va < self.image_base + self.image_size:
            self._fail(f"VA {va!r} is outside preferred-base image")
        return va - self.image_base

    def is_executable(self, rva: int) -> bool:
        section = self.section_for_rva(rva)
        return section is not None and section.executable

    def _backed_available(self, rva: int) -> int:
        if 0 <= rva < self.headers_size:
            return self.headers_size - rva
        section = self.section_for_rva(rva)
        if section is None or rva - section.rva >= section.raw_size:
            self._fail(f"RVA 0x{rva:x} has no backed byte range")
        return section.raw_size - (rva - section.rva)

    def cstring(self, rva: int, maxbytes: int = 4096) -> str:
        if type(maxbytes) is not int or maxbytes <= 0:
            self._fail("CString bound must be a positive byte count")
        data = self.read(rva, min(maxbytes, self._backed_available(rva)))
        end = data.find(b"\0")
        if end < 0:
            self._fail(f"CString at RVA 0x{rva:x} has no NUL within its backed/caller bound")
        try:
            return data[:end].decode("ascii")
        except UnicodeDecodeError as exc:
            raise PEFormatError(f"Non-ASCII PE/RTTI string at RVA 0x{rva:x}") from exc

    def iter_regions(self, executable: bool | None = None) -> Iterator[tuple[Section, bytes]]:
        for section in self.sections:
            if section.raw_size and (executable is None or section.executable == executable):
                yield section, self._file(section.raw_offset, section.raw_size)

    def find_bytes(self, pattern: bytes, executable: bool | None = None) -> list[int]:
        if not isinstance(pattern, bytes) or not pattern:
            self._fail("Byte search pattern must be nonempty bytes")
        result = []
        for section, data in self.iter_regions(executable):
            start = 0
            while True:
                index = data.find(pattern, start)
                if index < 0:
                    break
                result.append(section.rva + index)
                start = index + 1
        return result

    def _directory(self, index: int) -> tuple[int, int]:
        if index >= len(self.directories):
            return 0, 0
        rva, size = self.directories[index]
        if not rva and not size:
            return 0, 0
        if not rva or not size:
            self._fail(f"Data directory {index} has only one nonzero extent field")
        # Security directory (index4) is file-offset based, but is not consumed
        # by this RVA reader. All requested directories are genuine RVAs.
        if rva + size > self.image_size:
            self._fail(f"Data directory {index} exceeds SizeOfImage")
        self.read(rva, size)
        return rva, size

    def _parse_relocations(self):
        rva, size = self._directory(5)
        if not size:
            return
        data = self.read(rva, size)
        position = 0
        while position < size:
            if size - position < 8:
                self._fail("Truncated base-relocation block header")
            page, block_size = struct.unpack_from("<II", data, position)
            if block_size < 8 or block_size % 2 or block_size > size - position:
                self._fail("Invalid base-relocation block extent")
            if page & 0xfff:
                self._fail("Base-relocation block page is not 4KiB aligned")
            at = position + 8
            while at < position + block_size:
                encoded = struct.unpack_from("<H", data, at)[0]
                at += 2
                kind, offset = encoded >> 12, encoded & 0xfff
                if kind == 0:
                    continue
                site = page + offset
                if kind == 3:
                    self.read(site, 4)
                    self.relocations.add(site)
                else:
                    if site >= self.image_size:
                        self._fail("Base-relocation site exceeds SizeOfImage")
                    self.other_relocations.setdefault(kind, []).append(site)
                    if kind == 4:  # HIGHADJ consumes a signed addend word.
                        if at + 2 > position + block_size:
                            self._fail("HIGHADJ relocation lacks its addend word")
                        at += 2
            position += block_size

    def _parse_exports(self):
        rva, size = self._directory(0)
        if not size:
            return
        if size < 40:
            self._fail("Truncated export-directory header")
        _, _, _, _, dll_name, ordinal_base, count, named_count, funcs, names, ordinals = struct.unpack("<IIHHIIIIIII", self.read(rva, 40))
        self.export_module_name = self.cstring(dll_name) if dll_name else None
        function_data = self.read(funcs, count * 4) if count else b""
        name_data = self.read(names, named_count * 4) if named_count else b""
        ordinal_data = self.read(ordinals, named_count * 2) if named_count else b""
        for index in range(count):
            target = struct.unpack_from("<I", function_data, index * 4)[0]
            if target >= self.image_size and target != 0:
                self._fail("Export target RVA exceeds SizeOfImage")
            forwarder = self.cstring(target, rva + size - target) if rva <= target < rva + size else None
            ordinal = ordinal_base + index
            self.exports_by_ordinal[ordinal] = {"rva": target, "ordinal": ordinal, "forwarder": forwarder}
        named_ordinals = set()
        for index in range(named_count):
            name_rva = struct.unpack_from("<I", name_data, index * 4)[0]
            slot = struct.unpack_from("<H", ordinal_data, index * 2)[0]
            if slot >= count:
                self._fail("Named export ordinal index exceeds function table")
            name = self.cstring(name_rva)
            if not name or name in self.exports:
                self._fail("Empty or duplicate exported name")
            ordinal = ordinal_base + slot
            self.exports[name] = dict(self.exports_by_ordinal[ordinal], name=name)
            named_ordinals.add(ordinal)
        for ordinal, row in self.exports_by_ordinal.items():
            if ordinal not in named_ordinals:
                self.exports[f"#{ordinal}"] = dict(row, name=None)

    def _parse_imports(self):
        rva, size = self._directory(1)
        if not size:
            return
        if size < 20:
            self._fail("Truncated import-directory descriptor")
        terminated = False
        for offset in range(0, size - 19, 20):
            original, timestamp, forward, name_rva, iat = struct.unpack("<IIIII", self.read(rva + offset, 20))
            if not any((original, timestamp, forward, name_rva, iat)):
                terminated = True
                break
            if not name_rva or not iat:
                self._fail("Import descriptor lacks module name or IAT")
            dll = self.cstring(name_rva)
            self.import_modules.append(dll)
            thunk = original or iat
            available = min(self._backed_available(thunk), self._backed_available(iat)) // 4
            thunk_terminated = False
            for index in range(available):
                value = self.u32(thunk + 4 * index)
                if value == 0:
                    thunk_terminated = True
                    break
                entry = {"dll": dll, "name": None, "ordinal": None}
                if value & 0x80000000:
                    if value & 0x7fff0000:
                        if original:
                            self._fail("Ordinal import contains nonzero reserved bits")
                        entry["bound_address"] = value
                        entry["unresolved_reason"] = "bound IAT without an original hint/name thunk"
                    else:
                        entry["ordinal"] = value & 0xffff
                else:
                    try:
                        entry["hint"] = struct.unpack("<H", self.read(value, 2))[0]
                        entry["name"] = self.cstring(value + 2)
                    except PEFormatError:
                        if original:
                            raise
                        # An image with an already bound IAT may omit OFT.
                        # Preserve that uncertainty instead of inventing a name.
                        entry["bound_address"] = value
                        entry["unresolved_reason"] = "bound IAT without an original hint/name thunk"
                site = iat + 4 * index
                if site in self.imports_by_iat:
                    self._fail("Import descriptors overlap an IAT slot")
                self.imports_by_iat[site] = entry
            if not thunk_terminated:
                self._fail("Import thunk array has no file-backed terminator")
        if not terminated:
            self._fail("Import descriptors have no terminator within directory extent")

    def identity(self) -> dict:
        """Return neutral file observations, excluding any local source path."""
        return {"sha256": hashlib.sha256(self.data).hexdigest(), "file_size": len(self.data),
                "machine": "I386", "machine_code": self.machine, "format": "PE32", "is_dll": self.is_dll,
                "image_base": self.image_base, "image_size": self.image_size, "entry_rva": self.entry_rva,
                "section_count": len(self.sections), "HIGHLOW_relocation_count": len(self.relocations),
                "other_relocation_types": {str(k): len(v) for k, v in self.other_relocations.items()},
                "export_count": len(self.exports), "import_slot_count": len(self.imports_by_iat),
                "whole_file_sha_admission": False}
