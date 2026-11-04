"""Pro offline native primitives and bounded class-aware edits.

The packaged primitives originate in Pro archives. Existing clones preserve
their unrequested business fields; ordinary new controls use neutral primitives.
This module only transforms bytes. It never opens a database or runs Pro.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

NATIVE = Path(__file__).resolve().parents[3] / 'scripts' / 'native'
if str(NATIVE) not in sys.path:
    sys.path.insert(0, str(NATIVE))
from mcs_window_archive import ControlRecord, WindowSettings, write_count
from mcs_button_control import ButtonArchive
from mcs_input_text import InputRecord, InputMetadata, LabelRecord, unit_slot
from 原生界面样式 import CommonEnvelope, GroupArchive, set_font
from 可见动画归档 import 添加可见条件
from 窗口事件归档 import 窗口事件, 设置窗口事件

TYPES = {'label': 0x5008, 'line': 0x5002, 'rectangle': 0x5004,
         'button': 0x5027, 'numeric-input': 0x5025, 'character-input': 0x5025,
         'numeric-display': 0x5025, 'character-display': 0x5025}
INPUT_TYPES = {'numeric-input', 'character-input', 'numeric-display', 'character-display'}
FIELDS = {'name', 'bounds', 'text', 'caption', 'binding', 'binding_id', 'binding_type',
          'minimum', 'maximum', 'press_source', 'release_source', 'fill', 'border',
          'text_color', 'font', 'alignment', 'unit', 'decimals', 'visible_when'}


def text(value):
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('Expected text without NUL')
    return value


def rectangle(value, line=False):
    if (not isinstance(value, list) or len(value) != 4 or
            any(type(x) is not int or abs(x) > 32768 for x in value) or
            (value[0] == value[2] and value[1] == value[3] if line else value[0] >= value[2] or value[1] >= value[3])):
        raise ValueError('Bounds require four integers with positive dimensions')
    return value


def record(kind, payload):
    return ControlRecord(kind, payload, write_count(len(payload)), 0)


def _common(value):
    cm = CommonEnvelope.parse(value)
    if cm.to_record().payload != value.payload:
        raise ValueError('Native common envelope does not round-trip')
    return cm


def primitive_record(control_type, primitives=None):
    """Return a neutral Pro template, with no project binding or button source."""
    if control_type not in TYPES:
        raise ValueError('Unsupported control type: ' + str(control_type))
    if primitives is None:
        primitives = json.loads((Path(__file__).resolve().parent.parent /
                                 'assets/primitives.json').read_text(encoding='utf-8'))
    key = {'numeric-display': 'numeric-input', 'character-display': 'character-input'}.get(control_type, control_type)
    preset = primitives['controls'].get(key)
    if preset is None or preset['kind'] != TYPES[control_type]:
        raise ValueError('No matching neutral Pro primitive for ' + control_type)
    value = record(preset['kind'], bytes.fromhex(preset['payload']))
    cm = _common(value)
    if cm.animations:
        raise ValueError('Neutral primitive unexpectedly contains animation bindings')
    if control_type in INPUT_TYPES:
        q = InputRecord.parse(cm.project_without_animations())
        q.disable_images()
        q.variable = ''; q.properties[5] = 0xffffffff; q.expression_cache = b''
        if control_type.endswith('-display'):
            q.enabled_expression = '0'; q.disabled_when_nonzero = 0; q.disabled_style = 1
        value = cm.restore_projected(record(value.type_id, q.to_bytes()))
    return value


def resolve_clone(source_pages, descriptor, control_type):
    required = {'page_id', 'path', 'name', 'kind', 'sha256'}
    if not isinstance(descriptor, dict) or set(descriptor) != required:
        raise ValueError('clone_from requires page_id/path/name/kind/sha256')
    pages = [p for p in source_pages if p['id'] == descriptor['page_id']]
    if len(pages) != 1:
        raise ValueError('Clone page identity is absent or ambiguous')
    path = descriptor['path']
    if not isinstance(path, list) or not path or any(type(x) is not int or x < 0 for x in path):
        raise ValueError('Clone path requires nonnegative native control indexes')
    controls = pages[0]['controls']; value = None
    for depth, index in enumerate(path):
        if index >= len(controls):
            raise ValueError('Clone control path is absent')
        value = controls[index]
        if depth + 1 < len(path):
            controls = GroupArchive.parse(value).children
    kind = descriptor['kind']
    kind = int(kind, 0) if isinstance(kind, str) else kind
    if (kind != value.type_id or value.type_id != TYPES[control_type] or
            _common(value).name.value != descriptor['name'] or
            hashlib.sha256(value.payload).hexdigest() != descriptor['sha256']):
        raise ValueError('Clone name/type/path/preimage identity differs')
    if control_type in INPUT_TYPES:
        q = InputRecord.parse(_common(value).project_without_animations())
        if (q.variable_type == 3) != control_type.startswith('character-'):
            raise ValueError('Clone numeric/character class differs')
    return copy.deepcopy(value)


def _visible(value, expression):
    text(expression)
    if not expression.strip():
        raise ValueError('visible_when requires a nonempty native expression')
    from mcs_window_archive import Reader
    from 可见动画归档 import VisibleObject
    cm = _common(value); raw = value.payload
    if cm.animations:
        if len(cm.animations) != 1 or cm.animations[0]['class_name'] != 'CAniVisible':
            raise ValueError('Adding visibility to an existing animation graph is not implemented')
        reader = Reader(raw, cm.animation_start)
        if reader.count() != 1: raise ValueError('Native visible singleton count differs')
        visible = VisibleObject.parse(reader)
        if reader.pos != cm.animation_end: raise ValueError('Native visible singleton extent differs')
        visible.expression = expression
    else:
        visible = VisibleObject.new(expression)
    # Native common +0xb0 bit0 is serialized immediately after the array.
    base_word = struct.unpack_from('<H', raw, cm.animation_end)[0]
    result = copy.deepcopy(value)
    result.payload = (raw[:cm.animation_start] + write_count(1) + visible.to_bytes() +
                      struct.pack('<H', base_word | 1) + raw[cm.animation_end + 2:])
    _common(result)
    return result


def edit_control(kind, payload, edits, variables=None):
    """Edit supported original classes, restoring every unmodified animation."""
    if kind not in set(TYPES.values()) or not isinstance(edits, dict) or not edits or set(edits) - FIELDS:
        raise ValueError('Unknown, empty or unsupported native control edit')
    edits = dict(edits)
    if 'caption' in edits:
        if 'text' in edits and edits['text'] != edits['caption']:
            raise ValueError('caption and text disagree')
        edits['text'] = edits.pop('caption')
    value = record(kind, payload); cm = _common(value)
    if 'bounds' in edits:
        cm.set_rect(rectangle(edits['bounds'], kind == 0x5002))
    if 'name' in edits:
        name = text(edits['name'])
        if not name or len(name.encode('utf-16le')) // 2 > 32:
            raise ValueError('Control name requires 1..32 UTF-16 units')
        cm.name.value = name
    for key in ('fill', 'border', 'text_color'):
        if key in edits and (type(edits[key]) is not int or not 0 <= edits[key] <= 0xffffff):
            raise ValueError('Colors require integer COLORREF 0..0xffffff')
    cm.set_common_colors(**{k: edits[k] for k in ('fill', 'border') if k in edits})
    value = cm.to_record(); body = set(edits) - {'name', 'bounds', 'fill', 'border', 'visible_when'}
    if kind == 0x5027: body |= set(edits) & {'fill', 'border'}
    if kind == 0x5025: body |= set(edits) & {'fill'}
    if body:
        projected = cm.project_without_animations()
        parser = {0x5008: LabelRecord, 0x5025: InputRecord, 0x5027: ButtonArchive}.get(kind)
        if parser is None:
            raise ValueError('This shape has no supported class-specific text/input/button fields')
        q = parser.parse(projected)
        if q.to_bytes() != projected.payload:
            raise ValueError('Original class body does not round-trip')
        if 'text' in edits:
            if kind == 0x5008:
                q.caption = text(edits['text'])
            elif kind == 0x5027:
                q.caption.value = q.metadata.properties.caption.value = text(edits['text'])
            else:
                raise ValueError('Caption requires a label or button')
        if 'font' in edits:
            font = edits['font']
            if not isinstance(font, dict) or not font or set(font) - {'height', 'weight', 'family'}:
                raise ValueError('Unknown or empty font field')
            q.font = set_font(q.font, **font)
            if kind == 0x5027:
                q.metadata.properties.font = set_font(q.metadata.properties.font, **font)
        if 'alignment' in edits:
            align = {'left': 0, 'center': 1, 'right': 2}.get(edits['alignment'])
            if align is None or kind == 0x5027:
                raise ValueError('Alignment requires left/center/right on a label or input')
            if kind == 0x5008:
                q.style = q.appearance_prefix[1] = align
            else:
                q.properties[3] = align
        if 'text_color' in edits:
            color = edits['text_color']
            if kind == 0x5008:
                q.colour = color
            elif kind == 0x5025:
                q.properties[0] = color
            else:
                q.caption_words[1] = q.metadata.properties.words[5] = color
        if kind == 0x5025 and 'fill' in edits:
            q.properties[1] = edits['fill']
        if kind == 0x5027:
            for key, slots in [('fill', (1, 6)), ('border', (2, 7))]:
                if key in edits:
                    for slot in slots:
                        q.metadata.properties.words[slot] = edits[key]
        input_fields = {'binding', 'binding_id', 'binding_type', 'minimum', 'maximum', 'unit', 'decimals'}
        if set(edits) & input_fields:
            if kind != 0x5025:
                raise ValueError('Binding/range/unit/decimal fields require a native input/display')
            if 'binding' in edits:
                name = text(edits['binding']); target = (variables or {}).get(name)
                if target is None and {'binding_id', 'binding_type'} <= set(edits):
                    target = {'id': edits['binding_id'], 'kind': edits['binding_type']}
                if (target is None or type(target['id']) is not int or target['id'] < 0 or
                        target['kind'] not in (1, 2, 3) or
                        (q.variable_type == 3) != (target['kind'] == 3)):
                    raise ValueError('Binding must resolve to an existing matching numeric/character variable')
                if (q.variable, q.variable_id, q.variable_type) != (name, target['id'], target['kind']):
                    q.variable = name; q.properties[5] = target['id']; q.properties[6] = target['kind']; q.expression_cache = b''
            elif {'binding_id', 'binding_type'} & set(edits):
                raise ValueError('Binding identity fields require binding')
            if {'minimum', 'maximum'} & set(edits):
                if q.variable_type == 3:
                    raise ValueError('Character inputs do not accept numeric limits')
                low = edits.get('minimum', struct.unpack('<f', q.min_raw)[0]); high = edits.get('maximum', struct.unpack('<f', q.max_raw)[0])
                largest = struct.unpack('<f', bytes.fromhex('ffff7f7f'))[0]
                if not all(type(x) in (int, float) and math.isfinite(x) and abs(x) <= largest for x in (low, high)) or low > high:
                    raise ValueError('Expected an ordered finite float32 range')
                if 'minimum' in edits: q.min_raw = struct.pack('<f', low)
                if 'maximum' in edits: q.max_raw = struct.pack('<f', high)
            if 'unit' in edits: q.set_unit(text(edits['unit']))
            if 'decimals' in edits:
                places = edits['decimals']
                if q.variable_type == 3 or type(places) is not int or not 0 <= places <= 0xffffffff:
                    raise ValueError('Numeric decimal count must fit a native DWORD')
                metadata = InputMetadata.parse(q.common.metadata, q.appearance)
                a, b = bytearray(metadata.properties.value), bytearray(q.appearance)
                apos, bpos = unit_slot(a, 20)[1] + 12, unit_slot(b, 20)[1] + 12
                if struct.unpack_from('<I', a, apos)[0] != struct.unpack_from('<I', b, bpos)[0]:
                    raise ValueError('Input decimal mirrors differ')
                struct.pack_into('<I', a, apos, places); struct.pack_into('<I', b, bpos, places)
                metadata.properties.value = bytes(a); metadata.normalize_counts()
                q.common.metadata = metadata.to_bytes(); q.appearance = bytes(b)
        for key in ('press_source', 'release_source'):
            if key not in edits: continue
            if kind != 0x5027:
                raise ValueError('Native press/release source requires a standard button')
            owner = q.metadata.properties if key == 'press_source' else q
            source = 'press_script' if key == 'press_source' else 'release_script'
            cache = 'press_compiled' if key == 'press_source' else 'release_compiled'
            new = text(edits[key])
            if getattr(owner, source).value != new:
                getattr(owner, source).value = new; getattr(owner, cache).value = b''
        projected.payload = q.to_bytes()
        if parser.parse(projected).to_bytes() != projected.payload:
            raise ValueError('Changed native class body does not round-trip')
        value = cm.restore_projected(projected)
    if 'visible_when' in edits:
        value = _visible(value, edits['visible_when'])
    _common(value)
    return value.payload


def make_control(item, variables, primitives=None, source_pages=()):
    if not isinstance(item, dict) or set(item) - FIELDS - {'type', 'clone_from'}:
        raise ValueError('Unknown control property')
    control_type = item.get('type')
    if control_type not in TYPES or 'name' not in item or 'bounds' not in item:
        raise ValueError('New control requires supported type/name/bounds')
    value = resolve_clone(source_pages, item['clone_from'], control_type) if 'clone_from' in item else primitive_record(control_type, primitives)
    if control_type.endswith('-display') and 'clone_from' in item:
        cm = _common(value); projected = cm.project_without_animations(); q = InputRecord.parse(projected)
        q.enabled_expression = '0'; q.disabled_when_nonzero = 0; q.disabled_style = 1
        projected.payload = q.to_bytes(); value = cm.restore_projected(projected)
    if control_type in INPUT_TYPES and 'binding' not in item:
        raise ValueError('New numeric/character input or display requires explicit binding')
    edits = {k: v for k, v in item.items() if k not in ('type', 'clone_from')}
    value.payload = edit_control(value.type_id, value.payload, edits, variables)
    return value.type_id, value.payload


def page_events(trailer, changes, fresh=False):
    if not isinstance(changes, dict) or set(changes) - {'open', 'cycle', 'close', 'period_ms'}:
        raise ValueError('Page events accept open/cycle/close/period_ms')
    settings = WindowSettings.parse(trailer); before = 窗口事件.解析(settings.event_tail)
    defaults = ('', '', '') if fresh else (before.打开, before.循环, before.退出)
    if fresh:
        before.编译缓存 = [b'', b'', b'']
        settings.event_tail = before.序列化()
    settings.event_tail = 设置窗口事件(settings.event_tail,
        changes.get('open', defaults[0]), changes.get('cycle', defaults[1]),
        changes.get('close', defaults[2]), changes.get('period_ms', 100 if fresh else before.周期毫秒))
    return settings.to_bytes()
