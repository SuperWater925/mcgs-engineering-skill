"""McgsPro native fields, selected by structure with original headers kept."""
import base64
import math
import struct
from pathlib import Path
import sys

_native = Path(__file__).resolve().parents[3] / 'scripts/native'
if str(_native) not in sys.path:
    sys.path.insert(0, str(_native))
from mcs_window_archive import ControlRecord, WindowSettings, write_count, write_cstring
from mcgs_text import narrow_encoding
from 原生界面样式 import CommonEnvelope
from mcs_input_text import InputRecord
import mcgs_native_zip as native_zip


def binary(value):
    return base64.b64decode(value['binary'], validate=True)


def wrap(value):
    return {'binary': base64.b64encode(value).decode('ascii')}


def archive(value):
    """Decode a database BLOB and its actual optional native archive envelope."""
    raw = binary(value)
    return native_zip.unpack_if_wrapped(raw)


def wrap_like(original, plain):
    """Preserve the source envelope, including exact compressed bytes on no-op."""
    raw = binary(original)
    return wrap(native_zip.pack_like(raw, plain))


def u32(b, p):
    if p < 0 or p + 4 > len(b):
        raise ValueError('Truncated integer')
    return struct.unpack_from('<I', b, p)[0]


def string(b, p):
    def take(n):
        nonlocal p
        if n < 0 or p < 0 or p+n > len(b):
            raise ValueError('Truncated text')
        v = b[p:p+n]; p += n
        return v
    width = 1
    n = int.from_bytes(take(1), 'little')
    if n == 255:
        n = int.from_bytes(take(2), 'little')
        if n == 65534:
            width = 2; n = int.from_bytes(take(1), 'little')
            if n == 255:
                n = int.from_bytes(take(2), 'little')
        if n == 65535:
            n = int.from_bytes(take(4), 'little')
    return take(n*width).decode('utf-16le' if width == 2 else narrow_encoding()), p


def text(value):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('Text must be a string without NUL')
    return write_cstring(value)


class WindowRecords(list):
    """Keep each source frame header, including valid non-minimal lengths."""
    def __init__(self):
        super().__init__();self.frame_headers=[]


def window(b, *, validate_settings=True):
    title, pos = string(b, 12)
    if title != 'MCGS-SET DOCUMENT;VERSION 01.00':
        raise ValueError('Unsupported native document')
    count_pos = pos; count = u32(b, pos); pos += 4
    if count > (len(b)-pos)//6:
        raise ValueError('Invalid record count')
    records = WindowRecords()
    for _ in range(count):
        frame_start=pos
        kind, size = struct.unpack_from('<IH', b, pos); pos += 6
        if size == 65535:
            size = u32(b, pos); pos += 4
        if pos+size > len(b):
            raise ValueError('Invalid control frame')
        records.frame_headers.append((kind,size,b[frame_start:pos]))
        records.append((kind, b[pos:pos+size])); pos += size
    if validate_settings:
        settings = WindowSettings.parse(b[pos:])
        if settings.to_bytes() != b[pos:]:
            raise ValueError('Invalid page property roundtrip')
    return b[:count_pos], records, b[pos:]


def pack_window(header, records, trailer, *, validate_settings=True):
    result = header + struct.pack('<I', len(records))
    headers=getattr(records,'frame_headers',())
    for index,(kind, payload) in enumerate(records):
        original=headers[index] if index<len(headers) else None
        frame=(original[2] if original is not None and original[:2]==(kind,len(payload))
               else struct.pack('<IH', kind, len(payload)) if len(payload)<65535
               else struct.pack('<IHI', kind,65535,len(payload)))
        result += frame + payload
    result += trailer
    window(result, validate_settings=validate_settings)
    return result


def bounds(value):
    if not isinstance(value, list) or len(value) != 4 or any(type(x) is not int or not -0x80000000<=x<=0x7fffffff for x in value):
        raise ValueError('Bounds require four native Int32 values')
    if value[0] >= value[2] or value[1] >= value[3]:
        raise ValueError('Positive control dimensions required')
    return struct.pack('<4i', *value)


def common(b):
    if len(b) < 70:
        raise ValueError('Unsupported common control')
    parsed = CommonEnvelope.parse(ControlRecord(0, b, write_count(len(b)), 0))
    name_pos = len(parsed.prefix)
    name = parsed.name.value
    end = name_pos + len(parsed.name.to_bytes())
    if not name:
        raise ValueError('Unsupported control name')
    return {'bounds': list(parsed.rect), 'bounds_pos': parsed.rect_offset,
            'name': name, 'name_pos': name_pos, 'name_end': end}


def edit_control(kind, b, edits, variables=None):
    # Reuse the same original Pro class codecs for creation and existing edits.
    from control_factory import edit_control as edit_native_control
    return edit_native_control(kind, b, edits, variables)


def page_properties(trailer, *, ident=None, name=None, width=None, height=None):
    settings=WindowSettings.parse(trailer)
    if settings.to_bytes()!=trailer:
        raise ValueError('Unsupported page properties')
    for index,val,kind in ((0,ident,3),(1,name,8),(6,width,3),(7,height,3)):
        if val is None:continue
        if index>=len(settings.properties) or settings.properties[index].vt!=kind:
            raise ValueError('Requested page property position/type is not supported')
        if index in (6,7) and (type(val)is not int or not 1<=val<=0x7fffffff):raise ValueError('Invalid native Int32 page size')
        settings.properties[index].value=val
    return settings.to_bytes()


class VariableRecords(list):
    """Retain the source document header while parsing its actual record layout."""
    def __init__(self, values=(), document_header=struct.pack('<f', 12.0)):
        super().__init__(values)
        self.document_header = document_header


def _variables(blob,group_strings=False,alarm_bytes=40,alarm_tail=0):
    if len(blob)<12 or u32(blob,4) != len(blob)-8:
        raise ValueError('Unsupported variable document')
    count=u32(blob,8); pos=12; rows=[]
    if count > len(blob)//100:
        raise ValueError('Invalid variable count')
    for ident in range(count):
        name_start=pos;name,pos=string(blob,pos);name_raw=blob[name_start:pos]
        note_start=pos;note,pos=string(blob,pos);note_raw=blob[note_start:pos]
        unit_start=pos;unit,pos=string(blob,pos);unit_raw=blob[unit_start:pos]
        start=pos;kind=u32(blob,pos)
        if kind not in (1,2,3,0xffffffff):
            raise ValueError('Unsupported variable type')
        _, middle=string(blob,pos+36);initial,end=string(blob,middle+28)
        if end+24>len(blob):
            raise ValueError('Variable identity is truncated')
        native_id=u32(blob,end+12)
        prefix=blob[start:end+24]; pos=end+24; extension_start=pos
        for group_index in range(2):
            n=u32(blob,pos); pos+=4
            if n>count or pos>len(blob):
                raise ValueError('Invalid variable group vector')
            if group_index==0 and kind==0xffffffff and group_strings:
                for _ in range(n):_,pos=string(blob,pos)
            else:pos+=4*n
            if pos>len(blob):raise ValueError('Variable group vector exceeds record extent')
            if group_index==0:
                enabled=u32(blob,pos);pos+=4
                if enabled not in (0,1):raise ValueError('Invalid alarm flag')
                if enabled:
                    alarms=u32(blob,pos);pos+=4
                    if alarms>len(blob)//(alarm_bytes+4):raise ValueError('Invalid alarm count')
                    for _ in range(alarms):
                        _,pos=string(blob,pos+alarm_bytes);pos+=alarm_tail
        _,pos=string(blob,pos)
        rows.append({'id':native_id,'name':name,'note':note,'unit':unit,'kind':kind,
                     'initial':initial,'prefix':prefix,'extension':blob[extension_start:pos],
                     '_text_source':{'name':(name,name_raw),'note':(note,note_raw),'unit':(unit,unit_raw)}})
    if pos!=len(blob) or len({r['name'] for r in rows})!=count:
        raise ValueError('Variable extent or duplicate name')
    if len({r['id'] for r in rows})!=count:raise ValueError('Duplicate native variable ID')
    return VariableRecords(rows, blob[:4])


def variables(blob):
    # A document can use ID vectors or native CString group members, and the
    # measured alarm bodies have 40 or 52 bytes plus a four-byte suffix.
    # Pick a complete, unique parse of all records; do not infer from a
    # software release number or rewrite any alarm/member bytes.
    candidates=[];errors=[]
    for strings in (False,True):
        for alarm_bytes,alarm_tail in ((40,0),(52,4)):
            try:
                rows=_variables(blob,strings,alarm_bytes,alarm_tail)
                if not any(rows==other for other in candidates):candidates.append(rows)
            except (ValueError,UnicodeError,struct.error,IndexError) as exc:errors.append(str(exc))
    if len(candidates)!=1:
        raise ValueError('Ambiguous variable record layout' if candidates else 'Unsupported variable record layout: '+'; '.join(dict.fromkeys(errors)))
    return candidates[0]


def pack_variables(rows):
    body=b''
    for i,row in enumerate(rows):
        prefix=row['prefix'];_,middle=string(prefix,36);old_initial,end=string(prefix,middle+28)
        prefix=bytearray(prefix if old_initial==row['initial'] else prefix[:middle+28]+text(row['initial'])+prefix[end:])
        native_id=row.get('id',i)
        if type(native_id)is not int or not 0<=native_id<=0xffffffff:raise ValueError('Invalid native variable ID')
        _,new_end=string(prefix,middle+28);struct.pack_into('<I',prefix,new_end+12,native_id)
        def source_text(key):
            source=row.get('_text_source',{}).get(key)
            return source[1] if source is not None and source[0]==row[key] else text(row[key])
        body+=source_text('name')+source_text('note')+source_text('unit')+bytes(prefix)+row['extension']
    result=getattr(rows,'document_header',struct.pack('<f',12.))+struct.pack('<II',len(body)+4,len(rows))+body
    variables(result)
    return result
