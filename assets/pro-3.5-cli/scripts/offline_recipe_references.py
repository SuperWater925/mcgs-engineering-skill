"""Exact variable declarations for the recipe rename reference check.

The projected fields are never written to the database. Other parts of these
archives still go through the ordinary reference check.
"""
import re
import struct

import native_format as fmt
from mcs_window_archive import Reader, write_cstring
from offline_picture_library import mentions
from offline_structure import _data_group_members, _group_member_span


# Whole-group and whole-record calls observed in Pro release bytecode. The
# three numbers are the original function, result type, and argument count.
_RECIPE_REORDER_CALLS = {
    'RecipeLoad': (1, 2, 1), 'RecipeLoadByDialog': (2, 2, 2),
    'RecipeGetCurrentPosition': (3, 2, 1), 'RecipeGetName': (4, 4, 1),
    'RecipeGetCurrentValue': (5, 2, 1),
}
_RECIPE_REORDER_OUTPUTS = {'RecipeGetCurrentPosition': (2, b'\x47\x3e'), 'RecipeGetName': (3, b'\x3f')}
# Exact no-argument DrawRecipe Refresh method call from the original release
# cache. Only use it when the source names a verified same-page table.
_RECIPE_REFRESH = bytes.fromhex('050500000003fefffffffeffffff000000000000000000000000')


def recipe_reorder_release_cache(source, group, refresh_targets, variables):
    """Match a complete known release program without a column-position operand."""
    from mcs_plugin_controls import utf8_write

    body = bytearray(12)
    recipe_calls = 0
    for line in source.splitlines():
        line = line.strip()
        if not line:
            continue
        method = re.fullmatch(r'(.+\.Refresh)\s*\(\s*\)', line)
        if method and method[1] in refresh_targets:
            body.extend(_RECIPE_REFRESH)
            continue
        call = re.fullmatch(r'(?:(?P<output>[^\W\d]\w*)\s*=\s*)?!(?P<function>[A-Za-z]+)\s*\((?P<args>[^()]*)\)', line)
        args = re.fullmatch(r'\s*"([^"\r\n]*)"\s*(?:,\s*"([^"\r\n]*)"\s*)?', call['args']) if call else None
        function = _RECIPE_REORDER_CALLS.get(call['function']) if call else None
        if (not args or not function or args[1] != group or ('\0' in line)
                or (args[2] is not None) != (function[2] == 2)):
            raise ValueError('Unsupported recipe release call for column reorder')
        output = _RECIPE_REORDER_OUTPUTS.get(call['function'])
        target = variables.get(call['output']) if output and call['output'] else None
        if output:
            if not target or target['kind'] != output[0]:
                raise ValueError('Recipe release output does not resolve to the expected native scalar')
            statement = output[1] + struct.pack('<I', target['id'])
        else:
            if call['output']:
                raise ValueError('Unsupported recipe release output for column reorder')
            statement = b'\0'
        for literal in args.groups():
            if literal is not None:
                body.extend(b'\x13' + utf8_write(literal))
        body.extend(b'\x07' + struct.pack('<3I', *function) + statement)
        recipe_calls += 1
    if not recipe_calls:
        raise ValueError('Expected an existing whole-recipe release call')
    return bytes(body) + b'\1'


def require_recipe_reorder_safe_button(control, group, refresh_targets, variables):
    from mcs_button_control import ButtonArchive
    from 原生界面样式 import CommonEnvelope

    common = CommonEnvelope.parse(control)
    projected = common.project_without_animations()
    button = ButtonArchive.parse(projected)
    if common.to_record().payload != control.payload or button.to_bytes() != projected.payload:
        raise ValueError('Recipe button does not round-trip')
    expected = recipe_reorder_release_cache(button.release_script.value, group, refresh_targets, variables)
    if not button.release_compiled.value or button.release_compiled.value != expected:
        raise ValueError('Original recipe release compilation does not match its supported source')
    # Prove every other owner byte remains independently visible to the
    # reference guard. This projection is never written to the database.
    button.release_script.value = ''
    button.release_compiled.value = b''
    projected.payload = button.to_bytes()
    if mentions(common.restore_projected(projected).payload, group):
        raise ValueError('Another field of the recipe button also references the group')


def objdata_names(raw, records):
    if fmt.pack_variables(records) != raw:
        raise ValueError("ObjData fails byte roundtrip")
    offset = 12
    for record in records:
        source = record["_text_source"]
        end = offset + len(source["name"][1])
        yield record["name"], offset, end
        offset = end + len(source["note"][1]) + len(source["unit"][1])
        offset += len(record["prefix"]) + len(record["extension"])
    if offset != len(raw):
        raise ValueError("ObjData variable records do not fill the archive")


def typeinfo_names(raw, records, by_name):
    # Data-object library, followed by the paired collection class tags.
    anchor = (write_cstring("数据对象") + write_cstring("数据对象集合")
              + struct.pack("<4I", 0x196f, 19, 19, len(records)))
    start = raw.find(anchor)
    if start < 0 or raw.find(anchor, start + 1) >= 0:
        raise ValueError("TYPEINFO variable collection is not unique")
    reader = Reader(raw, start + len(anchor))
    by_id = {record["id"]: record for record in records}
    kinds = {1: 22, 2: 23, 3: 24, 0xffffffff: 26}

    def declaration():
        begin = reader.pos
        symbol = reader.cstring()[0]
        end = reader.pos
        reader.cstring()  # Description remains visible to the reference guard.
        flags, kind, ident = (reader.u32() for _ in range(3))
        record = by_id.get(ident)
        if record is None or record["name"] != symbol or kinds.get(record["kind"]) != kind or flags not in (0, 5000):
            raise ValueError("TYPEINFO variable identity differs from ObjData")
        return record, (symbol, begin, end)

    seen = set()
    for _ in records:
        record, span = declaration()
        ident = record["id"]
        if ident in seen:
            raise ValueError("TYPEINFO duplicates an ObjData variable")
        seen.add(ident)
        yield span
        if record["kind"] == 0xffffffff:
            group_span, uses_ids = _group_member_span(records, ident)
            members, _, supported = _data_group_members(record, group_span, by_name, by_id if uses_ids else None)
            if not supported or reader.u32() != len(members):
                raise ValueError("TYPEINFO group member count differs from ObjData")
            for member in members:
                child, child_span = declaration()
                if child["id"] != member["id"] or reader.take(6) != bytes(6):
                    raise ValueError("TYPEINFO scalar member differs from ObjData")
                yield child_span
            if reader.u16() != 0:
                raise ValueError("Unknown TYPEINFO group trailer")
        elif reader.take(6) != bytes(6):
            raise ValueError("Unknown TYPEINFO scalar trailer")
    if reader.u16() != 0:
        raise ValueError("Unknown TYPEINFO variable collection trailer")


def browse_names(raw, by_name):
    reader = Reader(raw)
    if reader.u32() != 0x8000000a:
        raise ValueError("Unknown BROWSEOBJECT header")
    reader.u32()  # Original generation marker, independent of project data.
    if reader.u32() != 0:
        raise ValueError("Unknown BROWSEOBJECT flags")
    roots = reader.count_extent(reader.u32(), 24, "BROWSEOBJECT entry")

    def node():
        kind = reader.u32()
        if reader.u32() != kind or kind not in (1, 2, 3, 4, 5):
            raise ValueError("Unknown BROWSEOBJECT entry kind")
        begin = reader.pos
        symbol = reader.cstring()[0]
        end = reader.pos
        reader.u32()
        reader.cstring()
        reader.cstring()
        reader.u32()
        return kind, (symbol, begin, end)

    seen = set()
    for _ in range(roots):
        kind, span = node()
        if kind == 1:
            symbol, _, _ = span
            if symbol not in by_name or symbol in seen:
                raise ValueError("BROWSEOBJECT variable identity differs from ObjData")
            seen.add(symbol)
            yield span
        for _ in range(reader.count_extent(reader.u32(), 24, "BROWSEOBJECT child")):
            node()
    if reader.pos != len(raw):
        raise ValueError("BROWSEOBJECT entries do not fill the archive")


def variable_name_projections(system, recipe_names):
    selected = [row for row in system if row["strName"] in ("ObjData", "TYPEINFO", "BROWSEOBJECT")]
    rows = {row["strName"]: row for row in selected}
    if "ObjData" not in rows or len(rows) != len(selected):
        return {}
    blobs = {key: fmt.archive(row["lbContext"]) for key, row in rows.items()}
    affected = [key for key, raw in blobs.items() if any(mentions(raw, name) for name in recipe_names)]
    if not affected:
        return {}
    try:
        records = fmt.variables(blobs["ObjData"])
        sources = list(objdata_names(blobs["ObjData"], records))
    except ValueError:
        return {}  # The ordinary guard still scans every original field.
    by_name = {record["name"]: record for record in records}
    terms = {name.casefold() for name in recipe_names}
    safe_names = {name for name in by_name if name.casefold() not in terms
                  and any(term in name.casefold() for term in terms)}
    if not safe_names:
        return {}
    projected = {}
    for key in affected:
        raw = blobs[key]
        try:
            if key == "TYPEINFO":
                spans = list(typeinfo_names(raw, records, by_name))
            elif key == "BROWSEOBJECT":
                spans = list(browse_names(raw, by_name))
            else:
                spans = sources
        except ValueError:
            continue  # An unrecognized mirror is scanned without exclusions.
        masked = bytearray(raw)
        for name, start, end in spans:
            if name in safe_names:
                masked[start:end] = bytes(end - start)
        projected[id(rows[key]), "lbContext"] = bytes(masked)
    return projected
