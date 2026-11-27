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
from mcs_window_archive import ControlRecord, WindowSettings, Reader, write_count, write_cstring
from mcs_button_control import ButtonArchive
from mcs_input_text import InputRecord, InputMetadata, LabelRecord, unit_slot
from 原生界面样式 import CommonEnvelope, GenericMetadata, GroupArchive, set_font
from 可见动画归档 import 添加可见条件
from 窗口事件归档 import (WINDOW_DISPATCH_ACTIONS, WINDOW_MOUSE_DOWN_SOURCE, 初始化页面派发事件,
                   编辑页面派发, 窗口事件, 设置窗口事件)
from control_geometry import resize, GEOMETRY_TYPES
from 当前存盘浏览样式 import SAVED_DATA_STYLE_FIELDS, SAVED_DATA_TYPE
from 原生趋势样式 import HISTORY_CURVE_EDIT_FIELDS

TYPES = {'label': 0x5008, 'line': 0x5002, 'rectangle': 0x5004, 'ellipse': 0x5006, 'bitmap': 0x5009,
         'button': 0x5027, 'multi-state-button': 0x5028, 'multi-state-display': 0x502a,
         'numeric-input': 0x5025, 'character-input': 0x5025,
         'numeric-display': 0x5025, 'character-display': 0x5025}
PLUGIN_PATHS = {
    'recipe-table': r'@\ActiveX\外挂版本构件\配方构件\DrawRecipe.ui#配方[3.52]',
    'xy-curve': r'@\ActiveX\外挂版本构件\XY曲线\XYPicture.ui#XY曲线[3.52]',
    'alarm-table': r'@\ActiveX\外挂版本构件\报警浏览动画构件\AlarmTableView.ui#报警浏览[3.52]',
}
TYPES.update(dict.fromkeys(PLUGIN_PATHS, 0x503d))
DEFAULT_DISPLAY_TYPES = {'history-curve': 0x502e, 'saved-data-browser': 0x5033}
TYPES.update(DEFAULT_DISPLAY_TYPES)
MULTI_TYPES = {'multi-state-button', 'multi-state-display'}
INPUT_TYPES = {'numeric-input', 'character-input', 'numeric-display', 'character-display'}
FIELDS = {'name', 'bounds', 'text', 'caption', 'binding', 'binding_id', 'binding_type',
          'minimum', 'maximum', 'press_source', 'release_source', 'fill', 'border',
          'text_color', 'font', 'alignment', 'unit', 'decimals', 'visible_when',
          'write_binding', 'state_layout', 'state_edits', 'animations'}


def text(value):
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('Expected text without NUL')
    return value


def rectangle(value, line=False):
    if (not isinstance(value, list) or len(value) != 4 or
            any(type(x) is not int or not -0x80000000<=x<=0x7fffffff for x in value) or
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


def _local_primitive(control_type, source_pages, neutral):
    """Reuse a current class serialization while clearing new-object business.

    Unknown business-bearing extension layouts are not guessed; those local
    candidates remain untouched and another current neutral candidate is tried.
    Explicit clone_from never enters this neutralization path.
    """
    neutral_common=_common(neutral)
    neutral_input=InputRecord.parse(neutral_common.project_without_animations()) if control_type in INPUT_TYPES else None
    neutral_button=ButtonArchive.parse(neutral_common.project_without_animations()) if control_type=='button' else None
    def walk(controls):
        for candidate in controls:
            if candidate.type_id==0x503a:
                try:yield from walk(GroupArchive.parse(candidate).children)
                except (ValueError,UnicodeError):pass
            else:yield candidate
    for page in source_pages:
        for candidate in walk(page['controls']):
            if candidate.type_id!=TYPES[control_type]:continue
            try:
                cm=_common(copy.deepcopy(candidate))
                value=cm.project_without_animations()
                cm=_common(value)
                prefix=bytearray(cm.prefix)
                flags=struct.unpack_from('<H',prefix,cm.animation_end)[0]
                struct.pack_into('<H',prefix,cm.animation_end,flags&~1)
                cm.prefix=bytes(prefix)
                # A linked-object header is a dependency, even without animation.
                if struct.unpack_from('<I',cm.prefix,4)[0]&0x100:
                    reader=Reader(cm.prefix,20);reader.cstring()
                    cm.prefix=cm.prefix[:12]+bytes(8)+write_cstring('')+cm.prefix[reader.pos:]
                    cm=_common(cm.to_record())
                value=cm.to_record()
                if control_type in INPUT_TYPES:
                    q=InputRecord.parse(value)
                    if (q.variable_type==3)!=control_type.startswith('character-'):continue
                    meta=InputMetadata.parse(q.common.metadata,q.appearance)
                    neutral_meta=InputMetadata.parse(neutral_input.common.metadata,neutral_input.appearance)
                    # The Stu vendor template uses the same eight opaque metadata bytes
                    # for numeric, boolean and character inputs. Preserve that observed
                    # pair of fixed fields while clearing the separately framed events.
                    neutral_layout=(meta.words,meta.tail)==(neutral_meta.words,neutral_meta.tail)
                    stu_layout=(meta.words,meta.tail)==(bytes.fromhex('72005700fd070000'),struct.pack('<I',10000))
                    if meta.extension_extra or meta.extension_tail.value or not (neutral_layout or stu_layout):continue
                    meta.events=write_count(0);q.common.metadata=meta.to_bytes()
                    q.disable_images();q.variable='';q.properties[5]=0xffffffff;q.expression_cache=b''
                    q.properties[4]&=~6;q.min_raw=struct.pack('<f',0);q.max_raw=struct.pack('<f',100)
                    q.enabled_expression='0' if control_type.endswith('-display') else '1'
                    q.disabled_when_nonzero=0;q.disabled_style=1;q.keyboard_window=''
                    q.keyboard_fields=list(neutral_input.keyboard_fields)
                    value.payload=q.to_bytes()
                elif control_type=='button':
                    q=ButtonArchive.parse(value)
                    if (q.tail or q.metadata.extension_extra or q.metadata.extension_tail.value or q.metadata.properties.tail or
                            q.metadata.words!=neutral_button.metadata.words or q.metadata.tail not in (neutral_button.metadata.tail, neutral_button.metadata.tail+struct.pack('<I',10000))):continue
                    q.metadata.empty_events=write_count(0);q.metadata.properties.clear_actions()
                    q.enable_compiled.value=q.release_compiled.value=b''
                    q.action_texts.clear_values();q.action_ids.clear_values(0xffffffff);q.action_modes.clear_values(0)
                    q.action_words[:]=[0,0];q.release_script.value='';q.enabled_expression.value='1';q.enabled_invert=0
                    q.safety_mode=0;q.hold_time=0;q.confirmation_time=50;q.disabled_appearance=1
                    q.picture=struct.pack('<I',0x80)+write_cstring('')
                    q.metadata.properties.words[0]=0  # Legacy picture is always serialized.
                    q.metadata.properties.words[16]=0;q.metadata.properties.picture=b''
                    value.payload=q.to_bytes()
                else:
                    from 原生界面样式 import GenericMetadata
                    meta=GenericMetadata.parse(cm.metadata.value)
                    # Static primitives have just the common words/empty extension.
                    if len(meta.tail)!=10 and meta.tail!=bytes(10)+struct.pack('<I',10000):continue
                    cm.metadata.value=write_count(0)+meta.tail;value=cm.to_record()
                _common(value)
                return value
            except (ValueError,UnicodeError,struct.error):continue
    return None


def primitive_record(control_type, primitives=None, source_pages=()):
    """Return a native template with no project binding or button source."""
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
    if control_type in PLUGIN_PATHS:
        # Each designer supplies its own unbound external component defaults.
        family = primitives.get('family', 'Pro')
        if getattr(source_pages, 'family', family) != family:
            raise ValueError('No matching native ' + control_type + ' primitive for this project family')
        return value
    if control_type in DEFAULT_DISPLAY_TYPES:
        if getattr(source_pages, 'family', None) == 'Stu' and primitives.get('family') != 'Stu':
            raise ValueError('No neutral Stu primitive for ' + control_type)
        return value
    if control_type in MULTI_TYPES:
        if getattr(source_pages, 'family', None) == 'Stu' and primitives.get('family') != 'Stu':
            raise ValueError('No neutral Stu primitive for ' + control_type)
        from 原生界面样式 import MultiState
        state = MultiState.parse(value)
        if state.to_record().payload != value.payload:
            raise ValueError('Multi-state primitive roundtrip differs')
        return value
    local=_local_primitive(control_type,source_pages,value)
    if local is not None:return local
    if getattr(source_pages,'family',None)=='Stu' and primitives.get('family')!='Stu':
        raise ValueError('No neutral Stu primitive for '+control_type+'; specify clone_from for a current source record')
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
    elif control_type=='button':
        q=ButtonArchive.parse(cm.project_without_animations())
        q.metadata.properties.words[0]=0
        q.metadata.properties.words[16]=0
        q.metadata.properties.picture=b''
        value=cm.restore_projected(record(value.type_id,q.to_bytes()))
    return value


def resolve_clone(source_pages, descriptor, control_type):
    required = {'page_id', 'path', 'name', 'kind', 'sha256'}
    if not isinstance(descriptor, dict) or set(descriptor) != required:
        raise ValueError('clone_from requires page_id/path/name/kind/sha256')
    pages = ([source_pages.page(descriptor['page_id'])] if hasattr(source_pages, 'page')
             else [p for p in source_pages if p['id'] == descriptor['page_id']])
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


def _state_binding(value, edits, variables):
    from 原生界面样式 import MultiState, MultiButtonTail
    from mcs_button_control import CString
    q = MultiState.parse(value)
    for field in ("binding", "write_binding"):
        if field not in edits:
            continue
        name = text(edits[field])
        target = (variables or {}).get(name)
        if not name or not target or target["kind"] not in (1, 2) or type(target["id"]) is not int or not 0 <= target["id"] < 0xffffffff:
            raise ValueError("Multi-state binding requires an existing Boolean or numeric variable")
        if value.type_id == 0x5028:
            tail = MultiButtonTail.parse(q.tail)
            expression, words = ((tail.input_expression, tail.input_words) if field == "binding"
                                 else (tail.output_expression, tail.output_words))
            if words[1] != 0 or words[3] != 0:
                raise ValueError("Multi-state button binding uses an unsupported indirect reference")
            expression.value = name
            words[0], words[2] = target["id"], target["kind"]
            q.tail = tail.to_bytes()
        else:
            if field == "write_binding":
                raise ValueError("Only a multi-state button has a write binding")
            reader = Reader(q.tail)
            if reader.u32() not in (0, 1):
                raise ValueError("Unknown multi-state display comparison mode")
            expression = CString.parse(reader)
            end = reader.pos
            if reader.take(16) != bytes(16):
                raise ValueError("Multi-state display binding has unresolved extra fields")
            reader.cstring()
            reader.take(4)
            if reader.pos != len(q.tail):
                raise ValueError("Unknown multi-state display binding suffix")
            expression.value = name
            q.tail = q.tail[:4] + expression.to_bytes() + q.tail[end:]
    return q.to_record()


ALARM_COLOR_FIELDS = frozenset({
    'new_text', 'ended_unanswered_text', 'answered_active_text', 'complete_text', 'ended_text', 'prior_text',
    'title_background', 'title_text', 'odd_background', 'even_background', 'grid_color',
    'focus_background', 'focus_text', 'focus_border', 'category_new_background',
    'category_answered_background', 'category_ended_background', 'category_complete_background',
    'category_prior_background',
})


def edit_plugin(value, edits, expected=None):
    from mcs_plugin_controls import PluginControl, RecipeCore, XYCore
    from 报警表原生样式 import AlarmStyle
    cm = _common(value)
    source = cm.project_without_animations()
    plugin = PluginControl.parse(source)
    kind = next((key for key,path in PLUGIN_PATHS.items() if path == plugin.path), None)
    if kind is None or expected is not None and kind != expected:
        raise ValueError('External component identity differs from the selected class')
    if plugin.to_record().payload != source.payload:
        raise ValueError('External component envelope roundtrip differs')
    allowed = {'name','bounds'}
    if kind == 'recipe-table':
        core = RecipeCore.parse(plugin.core)
        allowed.update(('row_height','column_widths'))
    elif kind == 'xy-curve':
        core = XYCore.parse(plugin.core)
    else:
        if len(plugin.core) < 20 or struct.unpack_from('<I', plugin.core, 16)[0] not in (0x55b1b, 0x55b36):
            raise ValueError('Unrecognized alarm-table schema')
        core = AlarmStyle(plugin.core)
        allowed.update(('row_height','alarm_colors'))
    if core.to_bytes() != plugin.core or not edits or set(edits) - allowed:
        raise ValueError('Unrecognized component fields or component core')
    if 'row_height' in edits:
        height = edits['row_height']
        if type(height) is not int or not 1 <= height <= 0x7fffffff:
            raise ValueError('Row height must be a positive native integer')
        if kind == 'recipe-table':
            core.fields['m70'] = height
    if 'column_widths' in edits:
        widths = edits['column_widths']
        if not isinstance(widths, dict):
            raise ValueError('column_widths requires a mapping of native titles to widths')
        for name, width in widths.items():
            matches = [column for column in core.columns if column.title == name]
            if len(matches) != 1 or type(width) is not int or not 0 <= width <= 0x7fffffff:
                raise ValueError('Recipe column requires a unique current title and a valid width')
            matches[0].values[2] = width
    plugin.core = core.to_bytes()
    if kind == 'alarm-table':
        colors = edits.get('alarm_colors', {})
        if not isinstance(colors, dict) or set(colors) - ALARM_COLOR_FIELDS:
            raise ValueError('Unknown alarm table color role')
        if any(type(color) is not int or not 0 <= color <= 0xffffff for color in colors.values()):
            raise ValueError('Alarm table colors require a native COLORREF integer')
        fields = dict(colors)
        if 'row_height' in edits:
            fields['row_height'] = edits['row_height']
        raw = bytearray(plugin.core)
        for name, number in fields.items():
            offset, width = core.fields[name]
            if width != 4 or offset + width > core.opaque_tail:
                raise ValueError('Alarm style fields do not match the selected layout')
            struct.pack_into('<I', raw, offset, number)
        plugin.core = bytes(raw)
    edited = _common(cm.restore_projected(plugin.to_record()))
    if 'name' in edits:
        if not text(edits['name']).strip():
            raise ValueError('External component needs a name')
        edited.name.value = edits['name']
    if 'bounds' in edits:
        edited.set_rect(rectangle(edits['bounds']))
    return edited.to_record()


CONTROL_CLICK_TYPES = {0x5004: 275, 0x5008: 282, 0x5028: 262}


def control_click_event(value):
    native_type = CONTROL_CLICK_TYPES.get(value.type_id)
    if native_type is None:
        raise ValueError('Click script editing requires a verified native control class')
    common = _common(value)
    metadata = GenericMetadata.parse(common.metadata.value)
    if metadata.to_bytes() != common.metadata.value or len(metadata.events) != 1:
        raise ValueError('Expected one round-tripping native control event')
    event = metadata.events[0]
    if not event.is_unparameterized_click(native_type):
        raise ValueError('Expected the verified unparameterized native control Click event')
    return common, metadata, event


def edit_control_click(value, spec):
    common, metadata, event = control_click_event(value)
    event.set_click_source(spec)
    common.metadata.value = metadata.to_bytes()
    result = common.to_record()
    _, checked_metadata, checked = control_click_event(result)
    if checked_metadata.to_bytes() != metadata.to_bytes() or checked.source.value != spec['source']:
        raise ValueError('Native control Click edit did not round-trip')
    return result


def edit_control(kind, payload, edits, variables=None, *, picture_references=None):
    """Edit supported original classes, restoring every unmodified animation."""
    if isinstance(edits, dict) and 'click_event_source' in edits:
        if edits.keys() != {'click_event_source'}:
            raise ValueError('Native control Click script requires a dedicated edit')
        return edit_control_click(record(kind, payload), edits['click_event_source']).payload
    if kind == 0x5009 and isinstance(edits, dict) and 'bitmap_picture' in edits:
        from control_patch import edit
        return edit(record(kind, payload), edits, picture_references=picture_references).payload
    if kind in (0x5006, 0x5039, 0x503d) and isinstance(edits, dict) and edits.keys() == {'animations'}:
        from control_patch import edit
        return edit(record(kind, payload), edits).payload
    if isinstance(edits, dict) and (HISTORY_CURVE_EDIT_FIELDS & edits.keys() or
                                    (kind == SAVED_DATA_TYPE and SAVED_DATA_STYLE_FIELDS & edits.keys())):
        from control_patch import edit
        return edit(record(kind, payload), edits, variables=variables).payload
    if kind == 0x503d and isinstance(edits, dict):
        return edit_plugin(record(kind, payload), edits).payload
    if kind not in GEOMETRY_TYPES or not isinstance(edits, dict) or not edits or set(edits) - FIELDS:
        raise ValueError('Unknown, empty or unsupported native control edit')
    edits = dict(edits)
    if "write_binding" in edits and kind != 0x5028:
        raise ValueError("Only a multi-state button has a write binding")
    shared = {k: edits.pop(k) for k in ("state_layout", "state_edits", "animations") if k in edits}
    if shared and "visible_when" in edits and "animations" in shared:
        raise ValueError("Specify visibility in the final animations list")
    if kind in (0x5028, 0x502a):
        allowed = {"name", "bounds", "fill", "border", "binding", "write_binding"}
        if set(edits) - allowed:
            raise ValueError("Unsupported multi-state field")
        value = record(kind, payload)
        if "binding" in edits or "write_binding" in edits:
            value = _state_binding(value, edits, variables)
        if "name" in edits:
            cm = _common(value)
            cm.name.value = text(edits["name"])
            if not cm.name.value:
                raise ValueError("Control name must not be empty")
            value = cm.to_record()
        shared.update({k: edits[k] for k in ("bounds", "fill", "border") if k in edits})
        if shared:
            from control_patch import edit
            value = edit(value, shared, picture_references=picture_references)
        return value.payload
    if shared:
        from control_patch import edit
        value = edit(record(kind, payload), shared, picture_references=picture_references)
        if not edits:
            return value.payload
        payload = value.payload
    if 'caption' in edits:
        if 'text' in edits and edits['text'] != edits['caption']:
            raise ValueError('caption and text disagree')
        edits['text'] = edits.pop('caption')
    value = record(kind, payload); cm = _common(value)
    if 'bounds' in edits:
        value = resize(value, edits['bounds']); cm = _common(value)
    if 'name' in edits:
        name = text(edits['name'])
        if not name:
            raise ValueError('Control name must not be empty')
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
                if (target is None or type(target['id']) is not int or target['id'] < 0 or
                        target['kind'] not in (1, 2, 3) or
                        (q.variable_type == 3) != (target['kind'] == 3)):
                    raise ValueError('Binding must resolve to an existing matching numeric/character variable')
                for supplied, field in (('binding_id', 'id'), ('binding_type', 'kind')):
                    if supplied in edits and (type(edits[supplied]) is not int or edits[supplied] != target[field]):
                        raise ValueError(supplied + ' disagrees with the existing variable')
                if (q.variable, q.variable_id, q.variable_type) != (name, target['id'], target['kind']):
                    q.variable = name; q.properties[5] = target['id']; q.properties[6] = target['kind']; q.expression_cache = b''
            elif {'binding_id', 'binding_type'} & set(edits):
                raise ValueError('Binding identity fields require binding')
            if {'minimum', 'maximum'} & set(edits):
                q.set_limits(**{key: edits[key] for key in ('minimum', 'maximum') if key in edits})
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


# Pro CDrawUnit with its native empty event metadata. Original body SHA-256
# 7755dd9104a0f54835bd7d0ebbe26472e9ab6ed49cb563691b52704dcdecf563.
# Only identity, bounds and child array were neutralized.
GROUP_SHELL = bytes.fromhex(
    'cd8c9e4300000000000000000000000000000000640000006400000001000600'
    '0000010000000100000000000000010000000000c0c0c0000000000000000000'
    '0080fffeff05470072006f00750070000c0000000000000000000000000000000000')


# Stu G-series 800x480 sample page 2 control 1, body SHA-256
# 03a375e5969a26452fce60c359d2e70e0db7c773b49951bda09a73a2abfc5698.
# All 30 source groups use the same native trailer.
STU_GROUP_SHELL = bytes.fromhex(
    'cd8ca54300000000000000000000000000000000640000006400000001000600'
    '0000010000000100000000000000010000000000c0c0c0000000000000000000'
    '0080fffeff05470072006f007500700010000000000000000000000000001027'
    '00000000000000000000000000000000000000000000fffeff07440061007400'
    '61007b0052007d00010000000000000001000000000000000a00000000000000'
    'fffeff0750006f0069006e00740065007200fffeff0001000000000000000000'
    '00000100000001000000')
GROUP_SHELLS = {'Pro': GROUP_SHELL, 'Stu': STU_GROUP_SHELL}


def new_group(name, bounds, children, family):
    if not text(name).strip() or not children:
        raise ValueError('A group needs a name and at least one child')
    group = GroupArchive.parse(record(0x503a, GROUP_SHELLS[family]))
    group.common.name.value = name
    group.common.set_rect(rectangle(bounds))
    group.children = [record(kind, body) for kind, body in children]
    names = [_common(child).name.value.casefold() for child in group.children]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate group child name')
    return 0x503a, group.to_record().payload


def new_default_data_display(value, name, bounds):
    name = text(name)
    if not name.strip():
        raise ValueError('Control name must not be empty')
    bounds = rectangle(bounds)
    common = _common(value)
    if common.animations or struct.unpack_from('<I', common.prefix, 4)[0] & 0x100:
        raise ValueError('Default data display contains an animation or linked object')

    if value.type_id == DEFAULT_DISPLAY_TYPES['history-curve']:
        from 原生趋势样式 import HistoryCurveStyle
        layout = HistoryCurveStyle(common.content)
        original_name, = [span for span in layout.spans if span.name == '4c']
        stored, _, wide = Reader(original_name.raw).cstring()
        if stored != common.name.value:
            raise ValueError('Default history curve internal name differs')
        original_name.raw = write_cstring(name, wide)
        common.content = layout.to_bytes()
        if HistoryCurveStyle(common.content).fields()['4c'] != original_name.raw:
            raise ValueError('Default history curve name did not round-trip')
    else:
        from 当前存盘浏览样式 import parse_current_save_data
        layout = parse_current_save_data(common.content)
        inner = (bounds[0], bounds[1], bounds[2] - 28, bounds[3] - 28)
        if inner[2] <= inner[0] or inner[3] <= inner[1]:
            raise ValueError('Saved-data browser needs room for the original 28-pixel frame')
        stored = layout.metadata['native_name']
        end = layout.metadata['native_config_member_map']['100']['offset']
        start = end - len(stored.wire)
        if stored != common.name.value or start < 0 or common.content[start:end] != stored.wire:
            raise ValueError('Default saved-data browser internal name differs')
        laid_out = layout.set(m2a8=inner).to_bytes()
        common.content = laid_out[:start] + write_cstring(name, stored.wide) + laid_out[end:]
        check = parse_current_save_data(common.content)
        if check.metadata['native_name'] != name or check.values['m2a8'] != inner:
            raise ValueError('Default saved-data browser name or grid rectangle did not round-trip')
    common.name.value = name
    common.set_rect(bounds)
    result = common.to_record()
    _common(result)
    return result.type_id, result.payload


def make_control(item, variables, primitives=None, source_pages=()):
    if isinstance(item, dict) and item.get('type') == 'bitmap':
        base = {'type', 'name', 'bounds'}
        if item.keys() == base | {'clone_from'}:
            value = resolve_clone(source_pages, item['clone_from'], 'bitmap')
        elif (item.keys() == base | {'bitmap_picture'} and isinstance(item['bitmap_picture'], dict)
              and item['bitmap_picture'].keys() == {'embedded_hex'}):
            from control_patch import edit
            value = edit(primitive_record('bitmap', primitives), {'bitmap_picture': item['bitmap_picture']})
        else:
            raise ValueError('New bitmap requires type/name/bounds and embedded_hex or an explicit clone_from')
        return value.type_id, edit_control(value.type_id, value.payload,
                                          {'name': item['name'], 'bounds': item['bounds']})
    if isinstance(item, dict) and item.get('type') in PLUGIN_PATHS:
        kind = item['type']
        required = {'type', 'name', 'bounds'}
        if 'clone_from' in item:
            if not required <= item.keys():
                raise ValueError('External component requires type, name and bounds with clone_from')
            source = resolve_clone(source_pages, item['clone_from'], kind)
        elif item.keys() == required:
            source = primitive_record(kind, primitives, source_pages)
        else:
            raise ValueError('Default ' + kind + ' requires only type, name and bounds')
        edits = {field:value for field,value in item.items() if field not in ('type','clone_from')}
        return source.type_id, edit_plugin(source, edits, expected=kind).payload
    if isinstance(item, dict) and item.get('type') == 'group':
        if set(item) != {'type', 'name', 'bounds', 'children'} or not isinstance(item['children'], list):
            raise ValueError('Group requires name, bounds and children in native 0..10000 coordinates')
        family = (primitives or {}).get('family', getattr(source_pages, 'family', 'Pro'))
        return new_group(item['name'], item['bounds'], [
            make_control(child, variables, primitives, source_pages) for child in item['children']], family)
    if not isinstance(item, dict) or set(item) - FIELDS - {'type', 'clone_from'}:
        raise ValueError('Unknown control property')
    control_type = item.get('type')
    if control_type not in TYPES or 'name' not in item or 'bounds' not in item:
        raise ValueError('New control requires supported type/name/bounds')
    if control_type in DEFAULT_DISPLAY_TYPES:
        if set(item) != {'type', 'name', 'bounds'}:
            raise ValueError('Default history curve and saved-data browser accept type, name and bounds')
        value = primitive_record(control_type, primitives, source_pages)
        return new_default_data_display(value, item['name'], item['bounds'])
    value = resolve_clone(source_pages, item['clone_from'], control_type) if 'clone_from' in item else primitive_record(control_type, primitives, source_pages)
    if control_type in INPUT_TYPES and control_type.endswith('-display') and 'clone_from' in item:
        cm = _common(value); projected = cm.project_without_animations(); q = InputRecord.parse(projected)
        q.enabled_expression = '0'; q.disabled_when_nonzero = 0; q.disabled_style = 1
        projected.payload = q.to_bytes(); value = cm.restore_projected(projected)
    if control_type in INPUT_TYPES and 'binding' not in item:
        raise ValueError('New numeric/character input or display requires explicit binding')
    edits = {k: v for k, v in item.items() if k not in ('type', 'clone_from')}
    value.payload = edit_control(value.type_id, value.payload, edits, variables)
    return value.type_id, value.payload


def page_events(trailer, changes, fresh=False, *, family='Pro'):
    if not isinstance(changes, dict) or changes.keys() - {'open', 'cycle', 'close', 'period_ms'} - WINDOW_DISPATCH_ACTIONS:
        raise ValueError('Page events accept open/cycle/close/period_ms or one supported dispatch operation')
    dispatch = changes.keys() & WINDOW_DISPATCH_ACTIONS
    if len(dispatch) > 1 or (fresh and dispatch - {'add_click_event_source'}):
        raise ValueError('Specify one window dispatch operation; new pages only allow add_click_event_source')
    settings = WindowSettings.parse(trailer)
    editing_mouse_down = WINDOW_MOUSE_DOWN_SOURCE in dispatch
    protected = False
    if family == 'Stu':
        protected = bool(settings.password_data) or settings.to_bytes() != trailer
    elif editing_mouse_down:
        # Original unprotected Pro windows store an empty ANSI string and one opaque byte.
        native_empty = len(settings.password_data) == 2 and settings.password_data[:1] == b'\0'
        protected = not native_empty or settings.to_bytes() != trailer
    if dispatch and protected:
        raise ValueError('Window dispatch requires unprotected window settings that round-trip exactly')
    before = 窗口事件.解析(settings.event_tail)
    defaults = ('', '', '') if fresh else (before.打开, before.循环, before.退出)
    if fresh:
        before.编译缓存 = [b'', b'', b'']
        source_tail = before.序列化()
        settings.event_tail = 初始化页面派发事件(source_tail)
        if protected and settings.event_tail != source_tail:
            raise ValueError('Stu window Click requires unprotected window settings that round-trip exactly')
    settings.event_tail = 设置窗口事件(settings.event_tail,
        changes.get('open', defaults[0]), changes.get('cycle', defaults[1]),
        changes.get('close', defaults[2]), changes.get('period_ms', 100 if fresh else before.周期毫秒))
    for operation in dispatch:
        settings.event_tail = 编辑页面派发(settings.event_tail, operation, changes[operation], family=family)
    return settings.to_bytes()
