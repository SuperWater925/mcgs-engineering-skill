"""McgsPro native fields, selected by structure with original headers kept."""
import base64
import math
import re
import struct
from pathlib import Path
import sys
from functools import lru_cache

_native = Path(__file__).resolve().parents[3] / 'scripts/native'
if str(_native) not in sys.path:
    sys.path.insert(0, str(_native))
from mcs_window_archive import ControlRecord, Reader, WindowSettings, write_count, write_cstring
from mcgs_text import narrow_encoding
from 原生界面样式 import CommonEnvelope
from mcs_input_text import InputRecord
import mcgs_native_zip as native_zip


def binary(value):
    return base64.b64decode(value['binary'], validate=True)


def language_text_id(value):
    token = re.fullmatch(r'\x07(0|[1-9][0-9]{0,9})', value)
    ident = int(token[1]) if token else None
    return ident if ident is not None and ident <= 0xffffffff else None


def _read_language_texts(raw, offset):
    reader = Reader(raw, offset)
    count = reader.u32()
    reader.count_extent(count, 4, 'Selected languages')
    selected = [reader.u32() for _ in range(count)]
    count = reader.u32()
    reader.count_extent(count, 23, 'Language definitions')
    definitions = set()
    for _ in range(count):
        language_id = reader.u32()
        if language_id in definitions:
            raise ValueError('Repeated language definition')
        definitions.add(language_id)
        reader.cstring()
        for _ in range(2):
            reader.cstring()
            reader.take(8)
    if not definitions or len(set(selected)) != len(selected) or not set(selected) <= definitions:
        raise ValueError('Unrecognized language selection and definition extent')

    count = reader.u32()
    reader.count_extent(count, 8, 'Language text IDs')
    rows = {}
    for _ in range(count):
        text_id = reader.u32()
        if text_id in rows:
            raise ValueError('Repeated language text ID')
        translations = {}
        entries = reader.u32()
        reader.count_extent(entries, 5, 'Language translations')
        for _ in range(entries):
            language_id = reader.u32()
            if language_id in translations:
                raise ValueError('Repeated translation language in text ID')
            translations[language_id] = reader.cstring()[0]
        rows[text_id] = translations
    reader.take(4)
    if reader.pos != len(raw):
        raise ValueError('Unrecognized language text archive suffix')
    return rows


def language_texts(data):
    rows = [row for row in data['System']['rows'] if row['strName'] == 'MCGSLINGUIST']
    if len(rows) != 1:
        raise ValueError('Expected one current MCGSLINGUIST archive')
    blob = rows[0].get('lbContext')
    if not isinstance(blob, dict) or not isinstance(blob.get('binary'), str):
        raise ValueError('Current MCGSLINGUIST archive has no binary content')
    raw = archive(blob)
    matches = []
    for offset in (12, 16):
        try:
            entries = _read_language_texts(raw, offset)
        except (ValueError, struct.error):
            continue
        if entries not in matches:
            matches.append(entries)
    if len(matches) != 1:
        raise ValueError('MCGSLINGUIST text dictionary cannot be parsed unambiguously')
    return matches[0]


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


def edit_control(kind, b, edits, variables=None, *, picture_references=None):
    # Reuse the same original Pro class codecs for creation and existing edits.
    from control_factory import edit_control as edit_native_control
    return edit_native_control(kind, b, edits, variables, picture_references=picture_references)


def page_properties(trailer, *, ident=None, name=None, width=None, height=None, background=None, description=None, identity=None):
    settings=WindowSettings.parse(trailer, identity=identity)
    if settings.to_bytes()!=trailer:
        raise ValueError('Unsupported page properties')
    values={'id':ident,'name':name,'width':width,'height':height,'background':background,'description':description}
    targets={key:settings.field(key) for key,value in values.items() if value is not None}
    for key, target in targets.items():
        val=values[key]
        if key in ('width','height') and (type(val)is not int or not 1<=val<=0x7fffffff):raise ValueError('Invalid native Int32 page size')
        if key=='description' and (not isinstance(val,str) or '\0' in val):raise ValueError('Page description requires text without NUL')
        target.value=val
    return settings.to_bytes()


class VariableRecords(list):
    """Retain the source document header while parsing its actual record layout."""
    def __init__(self, values=(), document_header=struct.pack('<f', 12.0), alarm_spans=None,
                 group_member_spans=None, empty_group_spans=None, group_id_member_spans=None):
        super().__init__(values)
        self.document_header = document_header
        self.alarm_spans = alarm_spans
        self.group_member_spans = group_member_spans if group_member_spans is not None else {}
        self.empty_group_spans = empty_group_spans if empty_group_spans is not None else {}
        self.group_id_member_spans = group_id_member_spans if group_id_member_spans is not None else {}


def _variables(blob,group_strings=False,alarm_bytes=40,alarm_tail=0,record_tail=0):
    if len(blob)<12 or u32(blob,4) != len(blob)-8:
        raise ValueError('Unsupported variable document')
    count=u32(blob,8); pos=12; rows=[]; alarm_spans={}; group_member_spans={}; empty_group_spans={}
    group_id_member_spans={}
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
            if group_index==0 and kind==0xffffffff and n==0:
                empty_group_spans[native_id]=(pos,pos)
            if group_index==0 and kind==0xffffffff:
                member_start=pos
                if group_strings:
                    for _ in range(n):_,pos=string(blob,pos)
                    group_member_spans[native_id]=(member_start,pos)
                else:
                    pos+=4*n
                    group_id_member_spans[native_id]=(member_start,pos)
            else:pos+=4*n
            if pos>len(blob):raise ValueError('Variable group vector exceeds record extent')
            if group_index==0:
                enabled=u32(blob,pos);pos+=4
                if enabled not in (0,1):raise ValueError('Invalid alarm flag')
                if enabled:
                    alarms=u32(blob,pos);pos+=4
                    if alarms>len(blob)//(alarm_bytes+4):raise ValueError('Invalid alarm count')
                    spans=[]
                    for _ in range(alarms):
                        item_start=pos-extension_start
                        _,pos=string(blob,pos+alarm_bytes);pos+=alarm_tail
                        spans.append((item_start,pos-extension_start,alarm_bytes))
                    if spans:alarm_spans[native_id]=tuple(spans)
        _,pos=string(blob,pos)
        pos+=record_tail
        if pos>len(blob):raise ValueError('Variable record tail exceeds document extent')
        rows.append({'id':native_id,'name':name,'note':note,'unit':unit,'kind':kind,
                     'initial':initial,'prefix':prefix,'extension':blob[extension_start:pos],
                     '_text_source':{'name':(name,name_raw),'note':(note,note_raw),'unit':(unit,unit_raw)}})
    if pos!=len(blob) or len({r['name'] for r in rows})!=count:
        raise ValueError('Variable extent or duplicate name')
    if len({r['id'] for r in rows})!=count:raise ValueError('Duplicate native variable ID')
    return VariableRecords(rows, blob[:4], alarm_spans, group_member_spans, empty_group_spans, group_id_member_spans)


def _variables_preserving_alarm_layout(blob, group_strings=False, record_tail=0):
    """Locate opaque alarm extensions through whole-document record framing.

    No alarm internals are edited or synthesized. Every candidate must resolve
    the exact remaining record count, unique IDs/names, and final EOF. Ambiguous
    framing is reported for variable editing only, never for unrelated pages.
    """
    if len(blob)<12 or u32(blob,4)!=len(blob)-8:raise ValueError('Invalid variable document')
    count=u32(blob,8)
    if count>len(blob)//100:raise ValueError('Invalid variable count')
    @lru_cache(maxsize=None)
    def parse_from(pos,remaining):
        if not remaining:return [()] if pos==len(blob) else []
        if len(blob)-pos<100*remaining:return []
        try:
            row={};sources={}
            for key in ('name','note','unit'):
                start=pos;value,pos=string(blob,pos);row[key]=value;sources[key]=(value,blob[start:pos])
            if not row['name'] or '\0' in row['name']:return []
            start=pos;kind=u32(blob,pos)
            if kind not in (1,2,3,0xffffffff):return []
            _,middle=string(blob,pos+36);initial,end=string(blob,middle+28)
            if end+24>len(blob):return []
            row.update(id=u32(blob,end+12),kind=kind,initial=initial,prefix=blob[start:end+24],_text_source=sources)
            extension_start=pos=end+24
            members=u32(blob,pos);pos+=4
            if members>count:return []
            if kind==0xffffffff and group_strings:
                for _ in range(members):_,pos=string(blob,pos)
            else:pos+=4*members
            enabled=u32(blob,pos);pos+=4
            if enabled not in (0,1):return []
            if enabled:
                alarms=u32(blob,pos);pos+=4
                if alarms>(len(blob)-pos)//5:return []
                # Each alarm has at least one numeric field plus a CString.
                # Retain the complete segment without assigning its fields.
                candidates=range(pos+5*alarms,len(blob)-4) if alarms else (pos,)
            else:candidates=(pos,)
            answers=[]
            for group_start in candidates:
                try:
                    groups=u32(blob,group_start)
                    if groups>count:continue
                    text_pos=group_start+4+groups*4
                    _,next_pos=string(blob,text_pos);next_pos+=record_tail
                    if next_pos>len(blob):continue
                    if remaining==1 and next_pos!=len(blob):continue
                    continuations=parse_from(next_pos,remaining-1)
                    if not continuations:continue
                    current=dict(row,extension=blob[extension_start:next_pos])
                    for following in continuations:
                        records=(current,)+following
                        if len({r['id'] for r in records})!=len(records) or len({r['name'] for r in records})!=len(records):continue
                        if not any(records==old for old in answers):answers.append(records)
                        if len(answers)>1:return answers
                except (ValueError,UnicodeError,struct.error,IndexError):continue
            return answers
        except (ValueError,UnicodeError,struct.error,IndexError):return []
    matches=parse_from(12,count)
    if len(matches)!=1:raise ValueError('Alarm extension has no unique complete variable framing')
    return VariableRecords(matches[0],blob[:4])


def variables(blob):
    # A document can use ID vectors or native CString group members, and the
    # measured alarm bodies have 40 or 52 bytes plus a four-byte suffix.
    # Pick a complete, unique parse of all records; do not infer from a
    # software release number or rewrite any alarm/member bytes.
    candidates=[];errors=[]
    for strings in (False,True):
        for record_tail in (0,12):
            for alarm_bytes,alarm_tail in ((40,0),(52,4)):
                try:
                    rows=_variables(blob,strings,alarm_bytes,alarm_tail,record_tail)
                    equivalent=next((other for other in candidates if rows==other),None)
                    if equivalent is None:candidates.append(rows)
                    else:
                        if rows.alarm_spans!=equivalent.alarm_spans:equivalent.alarm_spans=None
                        for field in ('group_member_spans','empty_group_spans','group_id_member_spans'):
                            matched = getattr(rows,field)
                            setattr(equivalent,field,{
                                ident: span for ident, span in getattr(equivalent,field).items()
                                if matched.get(ident) == span
                            })
                except (ValueError,UnicodeError,struct.error,IndexError) as exc:errors.append(str(exc))
    if not candidates:
        for strings in (False,True):
            for record_tail in (0,12):
                try:
                    rows=_variables_preserving_alarm_layout(blob,strings,record_tail)
                    if not any(rows==other for other in candidates):candidates.append(rows)
                except (ValueError,UnicodeError,struct.error,IndexError) as exc:errors.append(str(exc))
    if len(candidates)!=1:
        raise ValueError('Ambiguous variable record layout' if candidates else 'Unsupported variable record layout: '+'; '.join(dict.fromkeys(errors)))
    return candidates[0]


def pack_variables(rows):
    body=bytearray()
    for i,row in enumerate(rows):
        prefix=row['prefix'];_,middle=string(prefix,36);old_initial,end=string(prefix,middle+28)
        prefix=bytearray(prefix if old_initial==row['initial'] else prefix[:middle+28]+text(row['initial'])+prefix[end:])
        native_id=row.get('id',i)
        if type(native_id)is not int or not 0<=native_id<=0xffffffff:raise ValueError('Invalid native variable ID')
        _,new_end=string(prefix,middle+28);struct.pack_into('<I',prefix,new_end+12,native_id)
        def source_text(key):
            source=row.get('_text_source',{}).get(key)
            return source[1] if source is not None and source[0]==row[key] else text(row[key])
        body.extend(source_text('name')+source_text('note')+source_text('unit')+bytes(prefix)+row['extension'])
    result=getattr(rows,'document_header',struct.pack('<f',12.))+struct.pack('<II',len(body)+4,len(rows))+body
    variables(result)
    return result
