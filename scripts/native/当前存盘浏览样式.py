"""原生 0x5033 存盘浏览字段和样式适配。只处理控件归档字节。

原有352.1 codec只覆盖member1b8列表为空的10B前缀。当前记录的同一
前缀为6B原样头、DWORD数量、逐项CString+DWORD；已证列及样式字段的
偏移按列表实际长度平移，列表和其他未编辑字节原样保留。
"""
import copy
import re
import struct

from mcs_window_archive import write_cstring
from 原生界面样式 import Reader, CommonEnvelope, edit_font, fonts
from 旧下拉框与历史表样式 import NativeStyle, SAVE_COLUMN_TEXT_FIELDS, SAVE_ROLES, parse_save_data

SAVED_DATA_TYPE = 0x5033
SAVED_DATA_STYLE_FIELDS = frozenset({'row_height', 'saved_data_colors', 'saved_data_columns',
                                    'saved_data_fonts', 'saved_data_time_parts', 'saved_data_time_filter',
                                    'saved_data_source'})
FONT_ROLES = {role: key for key, role in SAVE_ROLES.items() if key.endswith('_font')}
COLOR_ROLES = {role: key for key, role in SAVE_ROLES.items()
               if role not in FONT_ROLES and role not in {'row_height', 'inner_rect'}}
COLUMN_ALIGNMENTS = ('left', 'center', 'right')
# Display dialog 0x6c8, checkboxes 0x405..0x40b. Both designers serialize
# these seven values in this order even though their object members differ.
TIME_PART_MEMBERS = dict(zip(
    ('year', 'month', 'day', 'hour', 'minute', 'second', 'millisecond'),
    ('17c', '180', '184', '188', '18c', '190', '194'),
))
# Time Condition dialog 0x6c9. The names on the right label common wire
# positions using the Stu serializer's member names.
TIME_FILTER_MEMBERS = {
    'order': '1d0', 'mode': '1d8', 'recent_minutes': '1dc',
    'fixed_period': '1e0', 'fixed_split_point': '1e4',
}
TIME_FILTER_BINDINGS = {'start_variable': '1b4', 'end_variable': '19c'}
TIME_FILTER_ORDERS = ('ascending', 'descending')
TIME_FILTER_MODES = ('all', 'recent', 'fixed', 'variables')
TIME_FILTER_PERIODS = ('today', 'this_month', 'this_week', 'previous_day', 'previous_month', 'previous_week')
TIME_FILTER_SPLIT_RANGES = ((0, 23), (1, 31), (1, 7), (0, 23), (1, 31), (1, 7))
MAX_RECENT_MINUTES = 0x2222222
DATA_SOURCE_KINDS = ('group', 'alarm_history', 'operation_log')
GROUP_BUILT_IN_FIELDS = {'MCGS序号': 1, 'MCGS_Time': 10}
SYSTEM_INDEX_FIELDS = ('MCGS序号', 'MCGSIndexID')
# Both native Source dialogs build the same ordered CString/DWORD vectors.
# The sequence row comes from the same localized resource in every mode.
SYSTEM_SAVED_DATA_SOURCES = {
    'alarm_history': ('MCGS_ALARM', 'TIMES', (
        ('VALNAME', 3), ('TIMES', 10), ('TIMEE', 10), ('TIMEA', 10),
        ('ALARMTYPE', 1), ('VALUE', 2), ('STANDVALUE', 2), ('INFO', 3),
    )),
    'operation_log': ('MCGS_OPERATION_LOG', 'MCGS_Time', (
        ('MCGS_TIME', 10), ('MCGS_TIMEMS', 1), ('MCGS_LOG_USER_NAME', 3),
        ('MCGS_LOG_WND_NAME', 3), ('MCGS_LOG_OBJ_NAME', 3),
        ('MCGS_LOG_ACTION', 3), ('MCGS_LOG_INFO', 3),
    )),
}
SYSTEM_TIME_KEY_MEMBERS = ('1cc', '1d4')

def parse_current_save_data(data):
    r=Reader(data)
    if r.take(6)!=bytes(6):raise ValueError('当前SaveData前6B头不匹配，禁止猜边界')
    n=r.u32()
    r.count_extent(n,5,'当前SaveData原生字段')
    fields=[]
    for _ in range(n):
        start=r.pos
        name=r.cstring()[0]
        word=r.u32()
        fields.append(dict(name=name,native_word=word,offset=start,end=r.pos))
    end=r.pos
    normalized=data[:6]+bytes(4)+data[end:]
    base=parse_save_data(normalized)
    shift=end-10
    result=NativeStyle(data)
    for key,(a,b,kind) in base.spans.items():
        assert a>=10
        result._add(key,a+shift,b-a,kind)
        assert result.values[key]==base.values[key]
    result.metadata=copy.deepcopy(base.metadata)
    result.metadata.update(native_field_list=fields,native_field_prefix_bytes=end,style_offset_shift=shift,
        original_front_six_bytes_hex=data[:6].hex(),native_word_meaning_not_inferred=True)
    result.metadata['post_font_offset']+=shift
    result.metadata['unmodified_m208_color_offset']+=shift
    result.metadata['column_spans'] = [
        {key: (start + shift, stop + shift) for key, (start, stop) in spans.items()}
        for spans in base.metadata['column_spans']]
    result.metadata['column_end_offset'] += shift
    # Member names identify positions from the Stu serializer. The two
    # families share the timestamp wire order, not the same member offsets.
    q=Reader(data,result.metadata['column_end_offset'])
    assert q.u32()==0
    q.cstring()
    config={}
    def word(name):
        offset=q.pos
        value=q.u32()
        config[name]=dict(offset=offset,kind='DWORD',value=value,raw_hex=data[offset:q.pos].hex())
    def string(name):
        offset=q.pos
        value=q.cstring()[0]
        config[name]=dict(offset=offset,kind='CString',value=value,raw_hex=data[offset:q.pos].hex())
    for name in ('100','104','108','10c','110','114','118','198','120','reserved1','reserved2','140'):word(name)
    for name in ('144','148','14c','150','154','158','15c','160','164'):string(name)
    for name in ('17c','180','184','188','18c','190','194'):word(name)
    for name in ('19c','1b4','1cc'):string(name)
    word('1d0')
    string('1d4')
    for name in ('1d8','1dc','1e0','1e4','1fc','200','20c'):word(name)
    result.metadata['native_config_member_map']=config
    for part, member in TIME_PART_MEMBERS.items():
        result._add(f'time_{part}', config[member]['offset'], 4, 'checkbox')
    for setting, member in TIME_FILTER_MEMBERS.items():
        result._add(f'filter_{setting}', config[member]['offset'], 4, 'dword')
    if result.to_bytes()!=data:raise ValueError('当前SaveData原文回环不匹配')
    return result

def _record_layout(record):
    if record.type_id != SAVED_DATA_TYPE:
        raise ValueError('Saved-data styling requires a native saved-data browser')
    common = CommonEnvelope.parse(record)
    return common, parse_current_save_data(common.content)


def parse_record(record):
    return _record_layout(record)[1]


def filter_value(layout, name, choices):
    raw = layout.values[f'filter_{name}']
    return choices[raw] if raw < len(choices) else None


def saved_data_time_filter(layout):
    config = layout.metadata['native_config_member_map']
    return {
        'order': filter_value(layout, 'order', TIME_FILTER_ORDERS),
        'mode': filter_value(layout, 'mode', TIME_FILTER_MODES),
        'recent_minutes': layout.values['filter_recent_minutes'],
        'fixed_period': filter_value(layout, 'fixed_period', TIME_FILTER_PERIODS),
        'fixed_split_point': layout.values['filter_fixed_split_point'],
        'start_variable': config['1b4']['value'],
        'end_variable': config['19c']['value'],
    }


def data_source(layout):
    config = layout.metadata['native_config_member_map']
    code = config['140']['value']
    return {'kind': DATA_SOURCE_KINDS[code] if code < len(DATA_SOURCE_KINDS) else None,
            'group': config['144']['value']}


def source_fields(layout):
    return [(row['name'], row['native_word']) for row in layout.metadata['native_field_list']]


def source_string_patch(layout, member, value):
    record = layout.metadata['native_config_member_map'][member]
    old, start = record['value'], record['offset']
    return (start, start+len(old.wire), write_cstring(value, wide=old.wide))


def edit_group_source(layout, changes, variables, current):
    if changes.keys() != {'kind', 'group'} or not isinstance(changes['group'], str):
        raise ValueError('Saved-data group source selection requires a named group')
    if current == changes:
        return changes, None, {}, []
    if current['kind'] != 'group':
        raise ValueError('Saved-data source selection currently preserves the original group field layout')
    group_name = changes['group']
    group = variables.get(group_name) if variables is not None else None
    if group is None or group['kind'] != 0xffffffff:
        raise ValueError('Saved-data source requires an existing native data group')

    reader = Reader(group['extension'])
    count = reader.u32()
    reader.count_extent(count, 1, 'Saved-data source group members')
    fields = dict(GROUP_BUILT_IN_FIELDS)
    for _ in range(count):
        member = reader.cstring()[0]
        record = variables.get(member)
        if record is None or record['kind'] not in (1, 2, 3) or member in fields:
            raise ValueError('Saved-data source group must have distinct scalar members')
        fields[member] = record['kind']
    cached = source_fields(layout)
    if len(cached) != len(fields) or dict(cached) != fields:
        raise ValueError('Saved-data source must have the same native column fields and types')
    return changes, None, {}, [source_string_patch(layout, '144', group_name)]


def edit_data_source(layout, changes, variables):
    if not isinstance(changes, dict) or not isinstance(changes.get('kind'), str):
        raise ValueError('Saved-data source selection requires a known kind')
    kind = changes['kind']
    current = data_source(layout)
    if kind == 'group':
        return edit_group_source(layout, changes, variables, current)
    if kind not in SYSTEM_SAVED_DATA_SOURCES or changes.keys() - {'kind', 'group', 'index_field'}:
        raise ValueError('Saved-data system source must select alarm_history or operation_log')
    system_name, time_key, fixed_fields = SYSTEM_SAVED_DATA_SOURCES[kind]
    if 'group' in changes and changes['group'] != system_name:
        raise ValueError(f'Saved-data {kind} uses the original source name {system_name}')
    if current['kind'] not in DATA_SOURCE_KINDS:
        raise ValueError('Current saved-data source kind cannot be identified')
    native = source_fields(layout)
    original_index = native[0][0] if native and native[0][0] in SYSTEM_INDEX_FIELDS and native[0][1] == 1 else None
    if current['kind'] in SYSTEM_SAVED_DATA_SOURCES:
        stored_name, _, stored_fields = SYSTEM_SAVED_DATA_SOURCES[current['kind']]
        if current['group'] != stored_name or original_index is None or native != [(original_index, 1), *stored_fields]:
            raise ValueError('Current saved-data system source fields do not match its original layout')
    if (layout.metadata.get('trailing_binding_present') and
            (layout.metadata.get('trailing_object_id') != 0xffffffff or layout.metadata.get('trailing_object_name'))):
        raise ValueError('Saved-data source retains a separate native object binding')
    if native and original_index is None and 'index_field' not in changes:
        raise ValueError('Saved-data source index field is unrecognized; select its exact native language name')
    index = changes.get('index_field', original_index or SYSTEM_INDEX_FIELDS[0])
    if index not in SYSTEM_INDEX_FIELDS:
        raise ValueError('Saved-data source index_field must be MCGS序号 or MCGSIndexID')
    fields = [(index, 1), *fixed_fields]
    expected = {'kind': kind, 'group': system_name}
    if current == expected and native == fields:
        return expected, None, {}, []

    config = layout.metadata['native_config_member_map']
    changes_to_archive = []
    time_fields = {name.casefold() for name, word in fields if word == 10}
    expected_time = {}
    for member in SYSTEM_TIME_KEY_MEMBERS:
        old = config[member]['value']
        if old in ('', 'MCGS_Time', 'TIMES'):
            value = time_key
        elif old.casefold() in time_fields:
            value = old
        else:
            raise ValueError(f'Saved-data time field {old!r} is not a timestamp in {kind}')
        expected_time[member] = value
        if value != old:
            changes_to_archive.append(source_string_patch(layout, member, value))
    if current != expected:
        offset = config['140']['offset']
        changes_to_archive.extend([
            (offset, offset+4, struct.pack('<I', DATA_SOURCE_KINDS.index(kind))),
            source_string_patch(layout, '144', system_name),
        ])
    if native != fields:
        wide = native[0][0].wide if native else config['144']['value'].wide
        prefix = struct.pack('<I', len(fields)) + b''.join(
            write_cstring(name, wide=wide) + struct.pack('<I', word) for name, word in fields
        )
        changes_to_archive.append((6, layout.metadata['native_field_prefix_bytes'], prefix))
    return expected, fields, expected_time, changes_to_archive

def edit_time_filter(layout, changes, variables):
    allowed = TIME_FILTER_MEMBERS.keys() | TIME_FILTER_BINDINGS.keys()
    if not isinstance(changes, dict) or not changes or changes.keys() - allowed:
        raise ValueError('Saved-data time filter requires known editable time condition fields')
    old_mode = filter_value(layout, 'mode', TIME_FILTER_MODES)
    mode = changes.get('mode', old_mode)
    codes = {}
    for key, choices in (('order', TIME_FILTER_ORDERS), ('mode', TIME_FILTER_MODES),
                         ('fixed_period', TIME_FILTER_PERIODS)):
        if key in changes:
            if changes[key] not in choices:
                raise ValueError(f'Saved-data time filter {key} requires one of {", ".join(choices)}')
            codes[f'filter_{key}'] = choices.index(changes[key])
    if 'recent_minutes' in changes or ('mode' in changes and mode == 'recent'):
        minutes = changes.get('recent_minutes', layout.values['filter_recent_minutes'])
        if type(minutes) is not int or not 0 <= minutes <= MAX_RECENT_MINUTES:
            raise ValueError(f'Saved-data recent time requires 0..{MAX_RECENT_MINUTES} minutes')
        if 'recent_minutes' in changes:
            codes['filter_recent_minutes'] = minutes
    if changes.keys() & {'fixed_period', 'fixed_split_point'} or ('mode' in changes and mode == 'fixed'):
        period = codes.get('filter_fixed_period', layout.values['filter_fixed_period'])
        if not 0 <= period < len(TIME_FILTER_SPLIT_RANGES):
            raise ValueError('Saved-data fixed time requires a known fixed period')
        minimum, maximum = TIME_FILTER_SPLIT_RANGES[period]
        split = changes.get('fixed_split_point', layout.values['filter_fixed_split_point'])
        if type(split) is not int or not minimum <= split <= maximum:
            raise ValueError(f'Saved-data fixed split point for {TIME_FILTER_PERIODS[period]} requires {minimum}..{maximum}')
        if 'fixed_split_point' in changes:
            codes['filter_fixed_split_point'] = split
    config = layout.metadata['native_config_member_map']
    selected = changes.keys() & TIME_FILTER_BINDINGS.keys()
    if mode == 'variables' and old_mode != 'variables':
        selected = TIME_FILTER_BINDINGS.keys()
    replacements = []
    expected = {}
    for name in selected:
        member = config[TIME_FILTER_BINDINGS[name]]
        old = member['value']
        value = changes.get(name, old)
        if value != '' or mode == 'variables':
            match = variables.get(value) if isinstance(value, str) and value.isidentifier() and variables is not None else None
            if match is None or match['kind'] != 3:
                raise ValueError(f'Saved-data {name} requires an existing string variable in this project')
        if value != old:
            start = member['offset']
            replacements.append((start, start+len(old.wire), write_cstring(value, wide=old.wide)))
        expected[name] = value
    return codes, replacements, expected


def saved_data_style(record):
    layout = parse_record(record)
    time_parts = {}
    for part in TIME_PART_MEMBERS:
        value = layout.values[f'time_{part}']
        time_parts[part] = bool(value) if value in (0, 1) else None
    return {"row_height": layout.values["m204"],
            "saved_data_colors": {role: layout.values[key] & 0xffffff for role, key in COLOR_ROLES.items()},
            "saved_data_fonts": {role: fonts(layout.values[key]) for role, key in FONT_ROLES.items()},
            "saved_data_time_parts": time_parts,
            "saved_data_time_filter": saved_data_time_filter(layout),
            "saved_data_source": data_source(layout),
            "saved_data_fields": [dict(name=name, native_type=word) for name, word in source_fields(layout)],
            "saved_data_columns": [
                {"index": index, "width": column["width"], "title": column["texts"][1],
                 "alignment": COLUMN_ALIGNMENTS[column['alignment']] if column['alignment'] < len(COLUMN_ALIGNMENTS) else None,
                 "title_editable": not column["texts"][1].startswith("\x07"),
                 "unit": column["texts"][2], "unit_editable": not column["texts"][2].startswith("\x07"),
                 "display_format": column["texts"][3], "data_name": column["texts"][0],
                 "output_variable": column["texts"][4]}
                for index, column in enumerate(layout.metadata["columns"])]}


def edit_columns(layout, changes, styled, variables=None):
    if not isinstance(changes, list) or not changes:
        raise ValueError("Saved-data columns require a nonempty array of column edits")
    columns = layout.metadata["columns"]
    spans = layout.metadata["column_spans"]
    desired = {}
    replacements = []
    source_names = {row['name'] for row in layout.metadata['native_field_list']}
    allowed = {'width', 'alignment'} | SAVE_COLUMN_TEXT_FIELDS.keys()
    for edit in changes:
        if (not isinstance(edit, dict) or edit.keys() - allowed - {'index'}
                or 'index' not in edit or not edit.keys() & allowed):
            raise ValueError('Each saved-data column edit needs index and a display setting')
        index = edit["index"]
        if type(index) is not int or not 0 <= index < len(columns) or index in desired:
            raise ValueError("Saved-data column index must identify one existing, unique slot")
        expected = dict(columns[index], texts=columns[index]["texts"][:], words=columns[index]["words"][:])
        desired[index] = expected
        if "width" in edit:
            width = edit["width"]
            if type(width) is not int or not 1 <= width <= 0x7fffffff:
                raise ValueError("Saved-data column width must fit a positive signed LONG")
            replacements.append((*spans[index]["width"], struct.pack("<I", width)))
            expected["width"] = width
        if 'alignment' in edit:
            alignment = edit['alignment']
            if alignment not in COLUMN_ALIGNMENTS:
                raise ValueError('Saved-data column alignment requires left, center or right')
            native_alignment = COLUMN_ALIGNMENTS.index(alignment)
            replacements.append((*spans[index]['alignment'], struct.pack('<I', native_alignment)))
            expected['alignment'] = native_alignment
        for field, text_index in SAVE_COLUMN_TEXT_FIELDS.items():
            if field not in edit:
                continue
            old, value = expected['texts'][text_index], edit[field]
            if old.startswith('\x07'):
                raise ValueError(f'Saved-data column {field} refers to a language entry; edit the language entry separately')
            if not isinstance(value, str) or '\0' in value or value.startswith('\x07'):
                raise ValueError(f'Saved-data column {field} must be literal text without NUL')
            if field == 'data_name' and value != old and value not in source_names:
                raise ValueError('Saved-data column must use a field declared by the current native data source')
            if field == 'output_variable' and value != old:
                if value:
                    match = variables.get(value) if variables is not None and value.isidentifier() else None
                    if match is None or match['kind'] not in (1, 2, 3):
                        raise ValueError('Saved-data column output requires an existing scalar project variable')
                # Drop only this column's old derived binding so the original
                # compiler resolves the newly selected output name.
                expected['words'] = [0, 0xffffffff]
                replacements.append((*spans[index]['compiled_output'], struct.pack('<2I', *expected['words'])))
            if field == 'display_format' and value and value != old:
                parts = value.split('|')
                if len(parts) != 2:
                    raise ValueError('Saved-data display format requires two values separated by |')
                if all(re.fullmatch(r'[+-]?[0-9]+', part.strip()) for part in parts):
                    places, spaces = map(int, parts)
                    if not -1 <= places <= 15 or not 0 <= spaces <= 1024:
                        raise ValueError('Saved-data display format requires -1..15 decimal places and 0..1024 trailing spaces')
            if value != old:
                replacements.append((*spans[index][field], write_cstring(value, wide=old.wide)))
            expected['texts'][text_index] = value

    cursor = 0
    chunks = []
    for start, stop, wire in sorted(replacements):
        chunks.extend((styled[cursor:start], wire))
        cursor = stop
    return b"".join((*chunks, styled[cursor:])), desired


def edit_saved_data_style(record, changes, variables=None):
    common, layout = _record_layout(record)
    if common.to_record().payload != record.payload:
        raise ValueError("Saved-data browser original does not round-trip")
    desired = {}
    if "row_height" in changes:
        desired["m204"] = changes["row_height"]
    if "saved_data_colors" in changes:
        colors = changes["saved_data_colors"]
        if not isinstance(colors, dict) or not colors or set(colors) - COLOR_ROLES.keys():
            raise ValueError("Saved-data browser colors require known color roles")
        for role, color in colors.items():
            if type(color) is not int or not 0 <= color <= 0xffffff:
                raise ValueError("Saved-data browser colors use COLORREF 0..0xffffff")
            key = COLOR_ROLES[role]
            desired[key] = (layout.values[key] & 0xff000000) | color
    if 'saved_data_fonts' in changes:
        styling = changes['saved_data_fonts']
        if not isinstance(styling, dict) or not styling or styling.keys() - FONT_ROLES.keys():
            raise ValueError('Saved-data browser fonts require header_font or body_font')
        for role, font_changes in styling.items():
            key = FONT_ROLES[role]
            raw = layout.values[key]
            if not fonts(raw):
                raise ValueError(f'Saved-data {role} has no native language font rows')
            desired[key] = edit_font(raw, font_changes)
    if 'saved_data_time_parts' in changes:
        parts = changes['saved_data_time_parts']
        if not isinstance(parts, dict) or not parts or parts.keys() - TIME_PART_MEMBERS.keys():
            raise ValueError('Saved-data time parts require known display checkboxes')
        for part, checked in parts.items():
            key = f'time_{part}'
            if type(checked) is not bool or layout.values[key] not in (0, 1):
                raise ValueError(f'Saved-data time part {part} requires a Boolean and a native checkbox state')
            desired[key] = int(checked)
    native_strings = []
    expected_time_bindings = {}
    expected_source = target_fields = None
    expected_source_time = {}
    if 'saved_data_time_filter' in changes:
        codes, time_bindings, expected_time_bindings = edit_time_filter(
            layout, changes['saved_data_time_filter'], variables)
        desired.update(codes)
        native_strings.extend(time_bindings)
    if 'saved_data_source' in changes:
        expected_source, target_fields, expected_source_time, source_patches = edit_data_source(
            layout, changes['saved_data_source'], variables)
        native_strings.extend(source_patches)
    common.content = layout.set(**desired).to_bytes()
    for start, stop, wire in sorted(native_strings, reverse=True):
        common.content = common.content[:start] + wire + common.content[stop:]
    expected_columns = {}
    if "saved_data_columns" in changes:
        # A new source can resize the leading field vector. Use its actual
        # column offsets and field names for the edits in the same transaction.
        column_layout = parse_current_save_data(common.content) if target_fields is not None else layout
        common.content, expected_columns = edit_columns(
            column_layout, changes["saved_data_columns"], common.content, variables)
    result = common.to_record()
    checked = parse_record(result)
    if any(checked.values[key] != value for key, value in desired.items()):
        raise ValueError("Saved-data browser style readback differs")
    actual_time_filter = saved_data_time_filter(checked)
    if any(actual_time_filter[name] != value for name, value in expected_time_bindings.items()):
        raise ValueError("Saved-data browser time variables did not round-trip")
    if expected_source is not None and data_source(checked) != expected_source:
        raise ValueError('Saved-data browser source did not round-trip')
    actual_source_config = checked.metadata['native_config_member_map']
    if any(actual_source_config[member]['value'] != value for member, value in expected_source_time.items()):
        raise ValueError('Saved-data browser source timestamp fields did not round-trip')
    if target_fields is not None:
        if source_fields(checked) != target_fields:
            raise ValueError('Saved-data browser original source field vector did not round-trip')
        original_types = dict(source_fields(layout))
        new_types = dict(target_fields)
        remapped = {edit['index'] for edit in changes.get('saved_data_columns', ()) if 'data_name' in edit}
        for index, column in enumerate(checked.metadata['columns']):
            name = column['texts'][SAVE_COLUMN_TEXT_FIELDS['data_name']]
            if name and (name not in new_types or
                         (index not in remapped and original_types.get(name) != new_types[name])):
                raise ValueError(f'Saved-data source requires an explicit target field for column {index}: {name}')
    if expected_columns:
        expected = layout.metadata["columns"][:]
        for index, column in expected_columns.items():
            expected[index] = column
        if checked.metadata["columns"] != expected:
            raise ValueError("Saved-data browser column readback differs")
    return result
