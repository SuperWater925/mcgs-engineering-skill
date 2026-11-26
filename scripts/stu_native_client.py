"""Run the supported Stu engineering commands on an existing native connection."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

import stu_project_lifecycle as lifecycle


CLIENT_DIR = Path(__file__).resolve().parents[1] / 'assets/pro-native-bridge/client'
ENGINE_FAMILY = 'McgsStu'
DATA_CATALOG_COMMAND = 'data-catalog'
DATA_READ_COMMAND = 'data-read'
DATA_EDIT_COMMAND = 'data-edit'
RECIPE_CATALOG_COMMAND = 'recipe-catalog'
RECIPE_READ_COMMAND = 'recipe-read'
RECIPE_CELL_COMMAND = 'recipe-cell-edit'
STRATEGY_CATALOG_COMMAND = 'strategy-catalog'
STRATEGY_READ_COMMAND = 'strategy-source-read'
STRATEGY_EDIT_COMMAND = 'strategy-source-edit'
PAGE_PROPERTIES_READ_COMMAND = 'page-properties-read'
PAGE_BACKGROUND_EDIT_COMMAND = 'page-background-edit'
VISIBILITY_READ_COMMAND = 'control-visible-read'
VISIBILITY_EDIT_COMMAND = 'control-visible-mode-edit'
VISIBILITY_COMMANDS = (VISIBILITY_READ_COMMAND, VISIBILITY_EDIT_COMMAND)
MODULE_SPEC_COMMANDS = (DATA_CATALOG_COMMAND, DATA_READ_COMMAND, DATA_EDIT_COMMAND,
                        RECIPE_READ_COMMAND, RECIPE_CELL_COMMAND, STRATEGY_READ_COMMAND, STRATEGY_EDIT_COMMAND,
                        *VISIBILITY_COMMANDS)
READ_COMMANDS = ('inspect', 'capabilities', 'page-catalog', 'control-catalog', lifecycle.PROJECT_STATE,
                 DATA_CATALOG_COMMAND, DATA_READ_COMMAND, RECIPE_CATALOG_COMMAND, RECIPE_READ_COMMAND,
                 STRATEGY_CATALOG_COMMAND, STRATEGY_READ_COMMAND, PAGE_PROPERTIES_READ_COMMAND, VISIBILITY_READ_COMMAND)
PAGE_COMMANDS = ('control-catalog', 'page-view-open', PAGE_PROPERTIES_READ_COMMAND)
PAGE_CREATE_COMMAND = 'page-native-create'
PAGE_COPY_COMMAND = 'page-native-copy'
PAGE_CREATION_COMMANDS = (PAGE_CREATE_COMMAND, PAGE_COPY_COMMAND)
LABEL_COMMAND = 'label-properties-batch'
GEOMETRY_COMMAND = 'control-geometry-batch'
CLONE_COMMAND = 'control-template-clone-batch'
CREATE_COMMAND = 'control-native-create-batch'
LABEL_FIELDS = {'caption', 'caption_primary', 'text_color_bgr'}
NATIVE_CONTROL_RTTI = {0x5008: '.?AVCDrawLabel@@', 0x5025: '.?AVCDrawEdit@@', 0x5027: '.?AVCDrawButton@@'}
DATA_IDENTITY_FIELDS = {'name', 'native_id', 'native_type'}
DATA_METADATA_FIELDS = {'comment', 'unit'}


def required_sha(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError(f'{name} must be a lowercase SHA-256')
    return value


def process_identity(value, name, maximum):
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError(f'Missing or invalid Stu connection {name}')
    return value


def absolute_path(value, name):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f'{name} must be an absolute path')
    return Path(value).resolve()


def read_page_batch(path):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict) or options.keys() != {'page_id', 'page', 'changes'}:
        raise ValueError('A Stu batch requires one page_id, its full page name and changes')
    changes = options['changes']
    if not isinstance(changes, list) or not changes:
        raise ValueError('Specify at least one Stu control change')
    return options


def valid_page_name(value):
    return valid_text(value) and bool(value)


def valid_text(value):
    return isinstance(value, str) and '\0' not in value


def signed_int32(value):
    return type(value) is int and -0x80000000 <= value <= 0x7fffffff


def nonnegative_int32(value):
    return type(value) is int and 0 <= value <= 0x7fffffff


def page_creation_specification(path, copying):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    fields = {'page_name', 'expected_page_count'}
    if copying:
        fields.update(('source_page_id', 'source_page_name'))
    if not isinstance(options, dict) or options.keys() != fields:
        raise ValueError('Use the new page name and current page count, with the complete source selector for a copy')
    count = options['expected_page_count']
    if not valid_page_name(options['page_name']) or type(count) is not int or not 0 <= count < 0x7fffffff:
        raise ValueError('Stu page creation requires a new full page name and its current project page count')
    if copying and (not nonnegative_int32(options['source_page_id']) or not valid_page_name(options['source_page_name'])):
        raise ValueError('Stu page copying requires the original source page ID and full name')
    return options


def page_background_specification(path):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if (not isinstance(options, dict) or options.keys() != {'page_id', 'page', 'before', 'after'}
            or not nonnegative_int32(options['page_id']) or not valid_page_name(options['page'])):
        raise ValueError('Use the original Stu page ID and exact name with background before and after')
    for item in (options['before'], options['after']):
        if (not isinstance(item, dict) or item.keys() != {'background_color_bgr'}
                or type(item['background_color_bgr']) is not int or not 0 <= item['background_color_bgr'] <= 0xffffff):
            raise ValueError('Stu background editing requires an ordinary 24-bit COLORREF before and after')
    return options


def visibility_specification(path, editing):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    selector = {'page_id', 'page', 'top_level_path', 'control_name', 'native_type_id', 'animation_index'}
    fields = selector | {'expected_expression', 'expected_mode', 'mode'} if editing else selector
    if not isinstance(options, dict) or options.keys() != fields or not valid_visibility_identity(options):
        raise ValueError('Use the exact Stu page, top-level control and animation index')
    if editing and (not valid_text(options['expected_expression'])
                    or not visibility_mode(options['expected_mode']) or not visibility_mode(options['mode'])):
        raise ValueError('Changing Stu visibility mode requires the original expression and two modes of 0 or 1')
    return options


def visibility_mode(value):
    return type(value) is int and value in (0, 1)


def valid_visibility_identity(selector):
    path = selector.get('top_level_path')
    return (nonnegative_int32(selector.get('page_id')) and valid_page_name(selector.get('page'))
            and valid_page_name(selector.get('control_name')) and nonnegative_int32(selector.get('native_type_id'))
            and nonnegative_int32(selector.get('animation_index'))
            and isinstance(path, list) and len(path) == 1 and nonnegative_int32(path[0]))


def data_specification(path, operation):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict):
        raise ValueError('Stu data options must be an object')
    if operation == DATA_CATALOG_COMMAND:
        if (options.keys() - {'name', 'offset', 'limit'}
                or 'name' in options and not valid_text(options['name'])
                or 'offset' in options and not nonnegative_int32(options['offset'])
                or 'limit' in options and not (nonnegative_int32(options['limit']) and options['limit'] > 0)):
            raise ValueError('Data catalog accepts an optional name filter, nonnegative offset and positive limit')
        return options
    editing = operation == DATA_EDIT_COMMAND
    fields = DATA_IDENTITY_FIELDS | {'before', 'after'} if editing else DATA_IDENTITY_FIELDS
    if (options.keys() != fields or not valid_page_name(options['name'])
            or not signed_int32(options['native_id']) or not signed_int32(options['native_type'])):
        raise ValueError('Use the data catalog’s exact variable name, native ID and native type')
    if editing:
        before, after = options['before'], options['after']
        if (options['native_type'] not in (1, 2, 3) or not isinstance(before, dict) or not isinstance(after, dict)
                or not before or before.keys() != after.keys() or before.keys() - DATA_METADATA_FIELDS
                or not all(valid_text(value) for value in (*before.values(), *after.values()))):
            raise ValueError('Only matching before/after comment and unit fields of a Stu scalar may be edited')
    return options


def recipe_specification(path, editing):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict) or not valid_page_name(options.get('group_name')):
        raise ValueError('Use the exact Stu recipe group name')
    if editing:
        if (options.keys() != {'group_name', 'row_index', 'column_index', 'expected', 'after'}
                or not nonnegative_int32(options['row_index']) or not nonnegative_int32(options['column_index'])
                or not valid_text(options['expected']) or not valid_text(options['after'])):
            raise ValueError('A Stu recipe cell requires zero-based row and column indexes and two string values')
    elif (options.keys() - {'group_name', 'offset', 'limit'}
          or 'offset' in options and not nonnegative_int32(options['offset'])
          or 'limit' in options and not (nonnegative_int32(options['limit']) and options['limit'] > 0)):
        raise ValueError('Stu recipe reads accept an optional nonnegative offset and positive limit')
    return options


def strategy_specification(path, editing):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    fields = {'block_id', 'block_name', 'row_index'}
    if editing:
        fields.update(('expected_source_sha256_utf16le', 'source'))
    if (not isinstance(options, dict) or options.keys() != fields or not valid_page_name(options['block_name'])
            or not nonnegative_int32(options['block_id']) or not nonnegative_int32(options['row_index'])):
        raise ValueError('Use the current Stu strategy ID, exact name and original script row index')
    if editing:
        required_sha(options['expected_source_sha256_utf16le'], 'Original UTF-16LE script SHA')
        if strategy_source_sha(options['source']) is None:
            raise ValueError('The new Stu script must be complete UTF-16 text without a NUL')
    return options


def check_control_selector(item, fields):
    if not isinstance(item, dict) or item.keys() != fields:
        raise ValueError('Use the full native control selector, before and after for each change')
    name, native_type = item['control_name'], item['native_type_id']
    if not isinstance(name, str) or not name or '\0' in name:
        raise ValueError('Use the full current control_name')
    if type(native_type) is not int or not -0x80000000 <= native_type <= 0x7fffffff:
        raise ValueError('Use the native_type_id from the current Stu control catalog')
    return name


def label_specification(path):
    options = read_page_batch(path)
    names = set()
    for item in options['changes']:
        name = check_control_selector(item, {'control_name', 'native_type_id', 'before', 'after'})
        if name in names:
            raise ValueError('Each full label name must occur only once on the selected page')
        names.add(name)
        before, after = item['before'], item['after']
        if not isinstance(before, dict) or before.keys() != LABEL_FIELDS:
            raise ValueError('Use all three current label fields in before')
        color = before['text_color_bgr']
        if (not all(isinstance(before[key], str) for key in ('caption', 'caption_primary'))
                or type(color) is not int or not -0x80000000 <= color <= 0x7fffffff):
            raise ValueError('The current label captions or original signed color word are missing')
        if not isinstance(after, dict) or not after or after.keys() - {'caption', 'text_color_bgr'}:
            raise ValueError('Label changes accept caption and text_color_bgr')
        if 'caption' in after:
            caption = after['caption']
            if not isinstance(caption, str) or '\0' in caption or before['caption'] != before['caption_primary']:
                raise ValueError('Caption editing requires matching original captions and an ordinary text replacement')
        if 'text_color_bgr' in after:
            new_color = after['text_color_bgr']
            if type(new_color) is not int or not 0 <= new_color <= 0xffffff or not 0 <= color <= 0xffffff:
                raise ValueError('Color editing requires the original and requested colors to be 24-bit BGR')
    return options


def top_level_index(path):
    if (isinstance(path, list) and len(path) == 1 and type(path[0]) is int
            and 0 <= path[0] <= 0x7fffffff):
        return path[0]
    return None


def int32_rect(rect):
    return (isinstance(rect, list) and len(rect) == 4
            and all(type(value) is int and -0x80000000 <= value <= 0x7fffffff for value in rect))


def rect_from_state(state):
    return state['rect'] if isinstance(state, dict) and state.keys() == {'rect'} else None


def positive_rect(rect):
    left, top, right, bottom = rect
    return 0 < right - left <= 0x7fffffff and 0 < bottom - top <= 0x7fffffff


def check_target_rect(state):
    rect = rect_from_state(state)
    if not int32_rect(rect):
        raise ValueError('after.rect must contain four signed Int32 coordinates')
    if not positive_rect(rect):
        raise ValueError('The new Stu rectangle must have positive Int32 width and height')


def rectangle_batch(path, distinct_sources):
    options = read_page_batch(path)
    indexes = set()
    for item in options['changes']:
        check_control_selector(item, {'control_name', 'native_type_id', 'top_level_path', 'before', 'after'})
        index = top_level_index(item['top_level_path'])
        if index is None:
            raise ValueError('Use a current single-index top_level_path')
        if distinct_sources and index in indexes:
            raise ValueError('Use one distinct current top_level_path per geometry change')
        indexes.add(index)
        if not int32_rect(rect_from_state(item['before'])):
            raise ValueError('before.rect must contain four signed Int32 coordinates')
        check_target_rect(item['after'])
    return options


def geometry_specification(path):
    return rectangle_batch(path, distinct_sources=True)


def clone_specification(path):
    return rectangle_batch(path, distinct_sources=False)


def create_specification(path):
    options = read_page_batch(path)
    for item in options['changes']:
        if not isinstance(item, dict) or item.keys() != {'native_type_id', 'after'}:
            raise ValueError('Stu native creation accepts only native_type_id and after.rect for each control')
        native_type = item['native_type_id']
        if type(native_type) is not int or native_type not in NATIVE_CONTROL_RTTI:
            raise ValueError('Stu native creation accepts a label, input box or standard button type')
        check_target_rect(item['after'])
    return options


BATCH_SPECIFICATIONS = {
    LABEL_COMMAND: label_specification,
    GEOMETRY_COMMAND: geometry_specification,
    CLONE_COMMAND: clone_specification,
    CREATE_COMMAND: create_specification,
}
BATCH_COMMANDS = tuple(BATCH_SPECIFICATIONS)
COMMANDS = (*READ_COMMANDS, 'compile', 'page-view-open', *PAGE_CREATION_COMMANDS, *BATCH_COMMANDS,
            DATA_EDIT_COMMAND, RECIPE_CELL_COMMAND, STRATEGY_EDIT_COMMAND, PAGE_BACKGROUND_EDIT_COMMAND,
            VISIBILITY_EDIT_COMMAND)


def exact_page(view, options):
    return isinstance(view, dict) and all(
        type(view.get(key)) is type(options[key]) and view[key] == options[key] for key in ('page_id', 'page')
    )


def page_display_matches(display, expected=None):
    return (isinstance(display, dict) and nonnegative_int32(display.get('page_id'))
            and valid_page_name(display.get('page'))
            and all(nonnegative_int32(display.get(field)) and display[field] > 0 for field in ('width', 'height'))
            and type(display.get('background_color_bgr')) is int and 0 <= display['background_color_bgr'] <= 0xffffffff
            and (expected is None or exact_page(display, expected)))


def page_background_matches(receipt, expected=None):
    current, before = receipt.get('page_properties'), receipt.get('before')
    if (not page_display_matches(current, expected) or not page_display_matches(before, current)
            or any(before[field] != current[field] for field in ('width', 'height'))
            or max(before['background_color_bgr'], current['background_color_bgr']) > 0xffffff):
        return False
    return expected is None or (
        before['background_color_bgr'] == expected['before']['background_color_bgr']
        and current['background_color_bgr'] == expected['after']['background_color_bgr']
    )


def created_page_matches(receipt, operation, expected=None):
    new_id, new_name = receipt.get('new_page_id'), receipt.get('new_page_name')
    count, controls = receipt.get('page_count'), receipt.get('top_level_control_count')
    if (not nonnegative_int32(new_id) or not valid_page_name(new_name) or type(count) is not int or not 0 < count <= 0x7fffffff
            or type(controls) is not int or not 0 <= controls <= 0x7fffffff):
        return False
    if expected is not None and (new_name != expected['page_name'] or count != expected['expected_page_count'] + 1):
        return False
    if operation == PAGE_CREATE_COMMAND:
        return controls == 0
    source_id, source_name = receipt.get('source_page_id'), receipt.get('source_page_name')
    return (receipt.get('copy_mode') == 'native-page-archive' and nonnegative_int32(source_id) and source_id != new_id
            and valid_page_name(source_name) and source_name != new_name
            and (expected is None or (source_id, source_name) == (expected['source_page_id'], expected['source_page_name'])))


def data_record_matches(record, expected=None):
    if (not isinstance(record, dict) or not valid_page_name(record.get('name'))
            or not signed_int32(record.get('native_id')) or not signed_int32(record.get('native_type'))
            or not all(valid_text(record.get(key)) for key in ('comment', 'unit', 'initial_text'))):
        return False
    return expected is None or all(record[key] == expected[key] for key in DATA_IDENTITY_FIELDS)


def modified_data_fields(receipt):
    fields = receipt.get('modified_fields')
    if (not isinstance(fields, list) or any(not isinstance(field, str) or field not in DATA_METADATA_FIELDS
                                           for field in fields) or len(set(fields)) != len(fields)):
        return None
    return set(fields)


def data_receipt_matches(receipt, operation, expected):
    record = receipt.get('record')
    if not data_record_matches(record, expected):
        return False
    if operation == DATA_READ_COMMAND:
        return True
    changed = {key for key, value in expected['after'].items() if value != expected['before'][key]}
    return (modified_data_fields(receipt) == changed
            and all(record[key] == value for key, value in expected['after'].items()))


def recipe_summary_matches(record):
    return (isinstance(record, dict) and valid_page_name(record.get('group_name'))
            and nonnegative_int32(record.get('row_count')) and nonnegative_int32(record.get('column_count')))


def recipe_record_matches(record, expected=None):
    if not recipe_summary_matches(record):
        return False
    columns, rows, offset = record.get('columns'), record.get('rows'), record.get('row_offset')
    width, height = record['column_count'], record['row_count']
    if (not isinstance(columns, list) or len(columns) != width or not isinstance(rows, list)
            or not nonnegative_int32(offset) or offset + len(rows) > height):
        return False
    if expected is not None and (record['group_name'] != expected['group_name'] or offset != expected.get('offset', 0)
                                 or 'limit' in expected and len(rows) != min(expected['limit'], height - offset)):
        return False
    return (
        all(isinstance(column, dict) and nonnegative_int32(column.get('index')) and column['index'] == index
            and valid_text(column.get('variable_name')) and valid_text(column.get('caption'))
            and signed_int32(column.get('native_kind')) for index, column in enumerate(columns))
        and all(isinstance(row, list) and len(row) == width and all(valid_text(cell) for cell in row) for row in rows)
    )


def recipe_cell_matches(receipt, expected=None):
    group, before, value = receipt.get('group_name'), receipt.get('expected'), receipt.get('value')
    row, column, changed = receipt.get('row_index'), receipt.get('column_index'), receipt.get('changed')
    if (not valid_page_name(group) or not nonnegative_int32(row) or not nonnegative_int32(column)
            or not valid_text(before) or not valid_text(value) or type(changed) is not bool
            or changed != (before != value)):
        return False
    return expected is None or (
        (group, row, column, before, value)
        == (expected['group_name'], expected['row_index'], expected['column_index'], expected['expected'], expected['after'])
    )


def visibility_receipt_matches(receipt, editing, expected=None):
    record = receipt.get('record')
    if not isinstance(record, dict):
        return False
    identity = {**record, 'page_id': receipt.get('page_id'), 'page': receipt.get('page')}
    if (not valid_visibility_identity(identity) or record.get('native_class') != 'CAniVisible'
            or not valid_text(record.get('expression')) or not signed_int32(record.get('mode'))):
        return False
    fields = ('page_id', 'page', 'top_level_path', 'control_name', 'native_type_id', 'animation_index')
    if expected is not None and any(identity[field] != expected[field] for field in fields):
        return False
    if not editing:
        return True
    before_mode = receipt.get('before_mode')
    if not visibility_mode(before_mode) or not visibility_mode(record['mode']):
        return False
    changed = before_mode != record['mode']
    if receipt.get('changed') is not changed:
        return False
    return expected is None or (
        (before_mode, record['mode'], record['expression'])
        == (expected['expected_mode'], expected['mode'], expected['expected_expression'])
    )


def strategy_source_sha(value):
    if not valid_text(value):
        return None
    try:
        return hashlib.sha256(value.encode('utf-16-le')).hexdigest()
    except UnicodeEncodeError:
        return None


def strategy_summary_matches(summary):
    return (isinstance(summary, dict) and nonnegative_int32(summary.get('block_id'))
            and valid_page_name(summary.get('block_name')) and valid_text(summary.get('block_comment'))
            and nonnegative_int32(summary.get('row_count')) and type(summary.get('changed')) is bool)


def strategy_source_matches(receipt, operation, expected=None):
    summary = receipt.get('strategy')
    row, source = receipt.get('row_index'), receipt.get('source')
    digest = strategy_source_sha(source)
    if (not strategy_summary_matches(summary) or not nonnegative_int32(row) or row >= summary['row_count']
            or digest is None or receipt.get('source_sha256_utf16le') != digest):
        return False
    if expected is not None and ((summary['block_id'], summary['block_name'], row)
                                 != (expected['block_id'], expected['block_name'], expected['row_index'])):
        return False
    if operation == STRATEGY_READ_COMMAND:
        return True
    before = receipt.get('source_before_sha256_utf16le')
    requested = receipt.get('source_requested_sha256_utf16le')
    normalization = receipt.get('source_normalization')
    if (not isinstance(before, str) or not re.fullmatch(r'[0-9a-f]{64}', before)
            or not isinstance(requested, str) or not re.fullmatch(r'[0-9a-f]{64}', requested)
            or normalization not in ('exact', 'native_trim_right')
            or (normalization == 'exact') != (requested == digest)
            or receipt.get('source_after') != source or receipt.get('source_after_sha256_utf16le') != digest):
        return False
    if expected is None:
        return True
    source_requested = expected['source']
    if before != expected['expected_source_sha256_utf16le'] or requested != strategy_source_sha(source_requested):
        return False
    if normalization == 'exact':
        return source == source_requested
    return source_requested.startswith(source) and source_requested[len(source):].isspace()


def completed_changes(receipt, expected):
    changes = receipt.get('changes')
    count = receipt.get('completed_count')
    if (isinstance(changes, list) and type(count) is int and count > 0 and len(changes) == count
            and (expected is None or len(expected) == count)):
        return changes
    return None


def original_append(row, preservation_field):
    if not isinstance(row, dict) or not isinstance(row.get('actual'), dict):
        return None
    actual = row['actual']
    native_type = row.get('native_type_id')
    name, rect = actual.get('control_name'), actual.get('rect')
    index = top_level_index(actual.get('top_level_path'))
    if (type(native_type) is not int or native_type not in NATIVE_CONTROL_RTTI
            or type(actual.get('native_type_id')) is not int or actual['native_type_id'] != native_type
            or actual.get('native_class') != NATIVE_CONTROL_RTTI[native_type]
            or not isinstance(name, str) or not name or '\0' in name
            or index is None or not int32_rect(rect) or not positive_rect(rect)
            or actual.get(preservation_field) is not True):
        return None
    return name.casefold(), index, rect


def contiguous_indexes(indexes):
    return all(after == before + 1 for before, after in zip(indexes, indexes[1:]))


def clone_changes_match(receipt, expected=None):
    changed = completed_changes(receipt, expected)
    if changed is None:
        return False
    source_names = set()
    source_indexes = set()
    new_names = set()
    new_indexes = []
    selector_keys = ('control_name', 'native_type_id', 'top_level_path', 'before')
    for i, row in enumerate(changed):
        result = original_append(row, 'original_payload_preserved')
        if result is None:
            return False
        new_name, new_index, rect = result
        source_name = row.get('control_name')
        source_index = top_level_index(row.get('top_level_path'))
        if (not isinstance(source_name, str) or not source_name or '\0' in source_name
                or source_index is None or not int32_rect(rect_from_state(row.get('before')))):
            return False
        if expected is not None and (
                any(row[key] != expected[i][key] for key in selector_keys) or rect != expected[i]['after']['rect']):
            return False
        source_names.add(source_name.casefold())
        source_indexes.add(source_index)
        new_names.add(new_name)
        new_indexes.append(new_index)
    return (len(new_names) == len(changed) and source_names.isdisjoint(new_names)
            and max(source_indexes) < new_indexes[0] and contiguous_indexes(new_indexes))


def creation_changes_match(receipt, expected=None):
    changed = completed_changes(receipt, expected)
    if changed is None:
        return False
    names = set()
    indexes = []
    for i, row in enumerate(changed):
        result = original_append(row, 'original_defaults_preserved')
        if result is None:
            return False
        name, index, rect = result
        if expected is not None and (row['native_type_id'] != expected[i]['native_type_id']
                                     or rect != expected[i]['after']['rect']):
            return False
        names.add(name)
        indexes.append(index)
    return len(names) == len(changed) and contiguous_indexes(indexes)


APPENDED_CONTROL_CHECKS = {
    CLONE_COMMAND: ('clone_changes', clone_changes_match),
    CREATE_COMMAND: ('creation_changes', creation_changes_match),
}


@dataclass(frozen=True)
class Connection:
    editor: Path
    scope_file: Path
    scope_sha: str
    engine_sha: str
    bootstrap_sha: str
    process_id: int
    thread_id: int
    creation_filetime: int

    @classmethod
    def read(cls, path):
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or data.get('status') != 'connected':
            raise ValueError('Select a connected Stu receipt from turnkey prepare-online')
        target = data.get('target')
        active = data.get('active_engine')
        if not isinstance(target, dict) or not isinstance(active, dict):
            raise ValueError('The connection receipt lacks the current process or selected engine')
        editor = absolute_path(target.get('editor'), 'The connection editor')
        if editor.name.casefold() != 'mcgssetstu.exe':
            raise ValueError('The connection receipt must target McgsSetStu.exe')
        scope_sha = required_sha(data.get('scope_sha256'), 'The connection scope SHA')
        if active.get('engine_scope_sha256') != scope_sha:
            raise ValueError('The selected engine names a different scope')
        return cls(
            editor, absolute_path(data.get('scope_config'), 'The connection scope'), scope_sha,
            required_sha(active.get('sha256'), 'The selected engine SHA'),
            required_sha(active.get('bootstrap_scope_sha256'), 'The bootstrap scope SHA'),
            process_identity(target.get('pid'), 'PID', 0xffffffff),
            process_identity(target.get('ui_thread'), 'UI thread', 0xffffffff),
            process_identity(target.get('creation_filetime'), 'creation FILETIME', 0x7fffffffffffffff),
        )

    def request(self, operation, project, page_id=None, page=None, spec=None):
        if operation not in (*COMMANDS, *lifecycle.WIRE_ACTIONS):
            raise ValueError('This Stu client does not expose that action')
        request = {
            'op': operation, 'expected_project': str(project), 'expected_engine_family': ENGINE_FAMILY,
            'expected_process_id': self.process_id, 'expected_ui_thread_id': self.thread_id,
            'expected_creation_filetime': self.creation_filetime,
        }
        if operation in lifecycle.WIRE_ACTIONS:
            request['expected_engine_sha256'] = self.engine_sha
        if operation in BATCH_COMMANDS:
            request['options'] = BATCH_SPECIFICATIONS[operation](spec)
            page_id, page = request['options']['page_id'], request['options']['page']
        if operation in PAGE_CREATION_COMMANDS:
            request['options'] = page_creation_specification(spec, copying=operation == PAGE_COPY_COMMAND)
        if operation == PAGE_BACKGROUND_EDIT_COMMAND:
            request['options'] = page_background_specification(spec)
        if operation in (DATA_READ_COMMAND, DATA_EDIT_COMMAND) or operation == DATA_CATALOG_COMMAND and spec is not None:
            request['options'] = data_specification(spec, operation)
        if operation in (RECIPE_READ_COMMAND, RECIPE_CELL_COMMAND):
            request['options'] = recipe_specification(spec, editing=operation == RECIPE_CELL_COMMAND)
        if operation in (STRATEGY_READ_COMMAND, STRATEGY_EDIT_COMMAND):
            request['options'] = strategy_specification(spec, editing=operation == STRATEGY_EDIT_COMMAND)
        if operation in VISIBILITY_COMMANDS:
            request['options'] = visibility_specification(spec, editing=operation == VISIBILITY_EDIT_COMMAND)
        if operation in (*PAGE_COMMANDS, *BATCH_COMMANDS):
            if not nonnegative_int32(page_id) or not valid_page_name(page):
                raise ValueError('This Stu action requires the original page ID and full name')
        if operation in PAGE_COMMANDS:
            request['options'] = {'page_id': page_id, 'page': page}
        return request

    def verify_receipt(self, result, project, request=None):
        if result.get('ok') is not True:
            return result
        expected = {
            'engine_family': ENGINE_FAMILY, 'process_id': self.process_id, 'thread_id': self.thread_id,
            'creation_filetime': self.creation_filetime, 'engineering_delivery_scope_sha256': self.scope_sha,
            'bridge_bootstrap_scope_sha256': self.bootstrap_sha, 'engine_sha256': self.engine_sha,
        }
        if request is not None:
            expected['op'] = request['op']
        elif result.get('op') not in (*COMMANDS, *lifecycle.WIRE_ACTIONS):
            expected['op'] = 'one of the supported Stu commands'
        op = result.get('op')
        is_lifecycle = op in lifecycle.WIRE_ACTIONS
        project_fields = ('project_path', 'application_project_path')
        if is_lifecycle and (op == lifecycle.CLOSE or result.get('lifecycle_state') != 'open'):
            project_fields = ()
        if is_lifecycle:
            project_fields = ('expected_project', *project_fields)
        for key in project_fields:
            value = result.get(key)
            if not isinstance(value, str) or not Path(value).is_absolute() or Path(value).resolve() != project:
                expected[key] = str(project)
        if result.get('op') in READ_COMMANDS:
            expected['read_only'] = True
        mismatches = [key for key, value in expected.items()
                      if type(result.get(key)) is not type(value) or result.get(key) != value]
        requested = request['op'] if request is not None else None
        append_check = APPENDED_CONTROL_CHECKS.get(requested)
        if requested == 'page-view-open' or append_check is not None:
            if not exact_page(result.get('page_view'), request['options']):
                mismatches.append('page_view')
        if append_check is not None:
            field, verify_changes = append_check
            if not verify_changes(result, request['options']['changes']):
                mismatches.append(field)
        if requested in PAGE_CREATION_COMMANDS and not created_page_matches(result, requested, request['options']):
            mismatches.append('created_page')
        if requested in (DATA_READ_COMMAND, DATA_EDIT_COMMAND) and not data_receipt_matches(
                result, requested, request['options']):
            mismatches.append('variable_record')
        if requested == RECIPE_READ_COMMAND and not recipe_record_matches(result.get('record'), request['options']):
            mismatches.append('recipe_record')
        if requested == RECIPE_CELL_COMMAND and not recipe_cell_matches(result, request['options']):
            mismatches.append('recipe_cell')
        if requested in (STRATEGY_READ_COMMAND, STRATEGY_EDIT_COMMAND) and not strategy_source_matches(
                result, requested, request['options']):
            mismatches.append('strategy_source')
        if requested == PAGE_PROPERTIES_READ_COMMAND and not page_display_matches(result.get('page_properties'), request['options']):
            mismatches.append('page_properties')
        if requested == PAGE_BACKGROUND_EDIT_COMMAND and not page_background_matches(result, request['options']):
            mismatches.append('page_background')
        if requested in VISIBILITY_COMMANDS and not visibility_receipt_matches(
                result, requested == VISIBILITY_EDIT_COMMAND, request['options']):
            mismatches.append('visibility')
        if mismatches:
            failure = {'ok': False, 'status': 'native_receipt_identity_mismatch', 'mismatches': mismatches,
                       'request_id': result.get('request_id'), 'queue_request_sha256': result.get('queue_request_sha256'),
                       'automatic_retry': False}
            if (is_lifecycle or append_check is not None or requested in PAGE_CREATION_COMMANDS
                    or requested in (DATA_EDIT_COMMAND, RECIPE_CELL_COMMAND, STRATEGY_EDIT_COMMAND,
                                     PAGE_BACKGROUND_EDIT_COMMAND, VISIBILITY_EDIT_COMMAND)):
                failure['native_receipt'] = result
            return failure
        return result


def bind(connection):
    # Use the current skill's verified delivery and existing at-most-once queue client.
    if str(CLIENT_DIR) not in sys.path:
        sys.path.insert(0, str(CLIENT_DIR))
    from native_delivery_config import configure

    layout = configure(str(connection.scope_file), connection.scope_sha)
    if layout.editor_executable != connection.editor:
        raise ValueError('The delivery scope selects a different editor than the Stu connection')
    import edit_batch_client

    return layout, edit_batch_client


def execute(args, connection, layout, queue):
    reading_result = args.command in ('request-result', lifecycle.READ_REOPEN)
    project = args.project.expanduser().resolve(strict=not reading_result)
    if project.suffix.casefold() != '.mcs' or not reading_result and not project.is_file():
        raise ValueError('Select the exact current Stu .MCS project')
    output = queue.owned_file(args.out, False) if args.out else None
    if output is not None:
        if not output.is_relative_to(layout.runtime_root):
            raise ValueError('Receipt output must be inside the selected queue runtime')
        if os.path.lexists(output):
            raise FileExistsError(output)

    client = queue.load_client()
    try:
        if args.command in (lifecycle.REOPEN, lifecycle.READ_REOPEN):
            result = lifecycle.execute(args, project, connection, layout, queue, client)
        elif reading_result:
            result = queue.read_existing_result(args.id, args.request_sha256)
            if result.get('ok') is True:
                result['result'] = connection.verify_receipt(result['result'], project)
        else:
            request = connection.request(args.command, project, getattr(args, 'page_id', None),
                                         getattr(args, 'page', None), getattr(args, 'spec', None))
            request_id = args.id or 'stu-' + args.command + '-' + uuid.uuid4().hex
            result = connection.verify_receipt(queue.submit(request, request_id, args.timeout), project, request)
    except (client.SubmissionError, client.QueueTimeout) as error:
        result = {'ok': False, 'error_type': type(error).__name__, 'error': str(error),
                  'transport_state': error.state, 'automatic_retry': False}
    if output is not None:
        queue.write_new(output, result)
    return result


def exit_status(result):
    if result.get('ok') is not True:
        return 1
    receipt = result['result'] if result.get('status') == 'correlated_response_observed' else result
    if receipt.get('ok') is not True:
        return 1
    if receipt.get('op') == 'compile' and not (
            receipt.get('native_compile_verified') is True
            and type(receipt.get('errors')) is int and receipt['errors'] == 0):
        return 2
    if receipt.get('op') == 'page-view-open' and not (
            isinstance(receipt.get('page_view'), dict) and receipt['page_view'].get('exact_page_is_active') is True):
        return 2
    if receipt.get('op') == PAGE_PROPERTIES_READ_COMMAND:
        return 0 if page_display_matches(receipt.get('page_properties')) else 2
    if receipt.get('op') == PAGE_BACKGROUND_EDIT_COMMAND:
        if not page_background_matches(receipt):
            return 2
        display, before = receipt['page_properties'], receipt['before']
        changed = display['background_color_bgr'] != before['background_color_bgr']
        view = receipt.get('page_view')
        flags = ('view_refresh_verified', 'page_save_verified', 'root_save_verified')
        count = receipt.get('completed_count')
        verified = (receipt.get('read_only') is (not changed) and receipt.get('write_attempted') is changed
                    and receipt.get('native_result_may_be_partial') is not True
                    and type(count) is int and count == int(changed)
                    and all(receipt.get(flag) is changed for flag in flags)
                    and (receipt.get('status') == 'no_changes') == (not changed)
                    and (not changed or exact_page(view, display) and view.get('exact_page_is_active') is True))
        return 0 if verified else 2
    if receipt.get('op') in VISIBILITY_COMMANDS:
        editing = receipt['op'] == VISIBILITY_EDIT_COMMAND
        if not visibility_receipt_matches(receipt, editing):
            return 2
        if not editing:
            return 0 if receipt.get('read_only') is True else 2
        changed = receipt['changed']
        flags = ('view_refresh_verified', 'page_save_verified', 'root_save_verified', 'write_attempted')
        view, count = receipt.get('page_view'), receipt.get('completed_count')
        verified = (receipt.get('status') == ('applied_and_saved' if changed else 'no_changes')
                    and receipt.get('read_only') is (not changed)
                    and receipt.get('native_result_may_be_partial') is False
                    and type(count) is int and count == int(changed)
                    and all(receipt.get(flag) is changed for flag in flags)
                    and (not changed or exact_page(view, receipt) and view.get('exact_page_is_active') is True
                         and signed_int32(receipt.get('before_owner_flags'))
                         and signed_int32(receipt.get('applied_owner_flags'))
                         and receipt['applied_owner_flags'] == (receipt['before_owner_flags'] | 1)))
        return 0 if verified else 2
    if receipt.get('op') == DATA_READ_COMMAND and not data_record_matches(receipt.get('record')):
        return 2
    if receipt.get('op') == DATA_EDIT_COMMAND:
        fields = modified_data_fields(receipt)
        saves = ('data_module_saved', 'project_saved')
        if receipt.get('status') == 'no_changes':
            verified = (fields == set() and receipt.get('read_only') is True and receipt.get('write_attempted') is False
                        and all(receipt.get(flag) is False for flag in saves))
        else:
            verified = (bool(fields) and receipt.get('status') == 'applied_and_saved'
                        and receipt.get('read_only') is False and receipt.get('write_attempted') is True
                        and receipt.get('unselected_native_records_verified') is True
                        and all(receipt.get(flag) is True for flag in saves))
        return 0 if (verified and data_record_matches(receipt.get('record'))
                     and receipt.get('native_result_may_be_partial') is not True) else 2
    if receipt.get('op') == RECIPE_CATALOG_COMMAND:
        count, groups = receipt.get('recipe_count'), receipt.get('recipes')
        verified = (nonnegative_int32(count) and isinstance(groups, list) and count == len(groups)
                    and all(recipe_summary_matches(group) for group in groups))
        return 0 if verified else 2
    if receipt.get('op') == RECIPE_READ_COMMAND:
        return 0 if recipe_record_matches(receipt.get('record')) else 2
    if receipt.get('op') == RECIPE_CELL_COMMAND:
        saves = ('recipe_save_verified', 'root_save_verified', 'project_saved')
        verified = (recipe_cell_matches(receipt)
                    and receipt.get('native_named_recipe_readback') is True
                    and receipt.get('other_target_recipe_bytes_preserved') is True
                    and receipt.get('native_result_may_be_partial') is False
                    and receipt.get('read_only') is (not receipt['changed'])
                    and receipt.get('write_attempted') is receipt['changed']
                    and receipt.get('status') == ('applied_and_saved' if receipt['changed'] else 'no_changes')
                    and all(receipt.get(flag) is receipt['changed'] for flag in saves))
        return 0 if verified else 2
    if receipt.get('op') == STRATEGY_CATALOG_COMMAND:
        count, blocks = receipt.get('strategy_count'), receipt.get('strategies')
        verified = (nonnegative_int32(count) and isinstance(blocks, list) and len(blocks) == count
                    and all(strategy_summary_matches(block) for block in blocks)
                    and len({block['block_id'] for block in blocks}) == count)
        return 0 if verified else 2
    if receipt.get('op') == STRATEGY_READ_COMMAND:
        return 0 if strategy_source_matches(receipt, STRATEGY_READ_COMMAND) else 2
    if receipt.get('op') == STRATEGY_EDIT_COMMAND:
        if not strategy_source_matches(receipt, STRATEGY_EDIT_COMMAND):
            return 2
        changed = receipt['source_before_sha256_utf16le'] != receipt['source_after_sha256_utf16le']
        flags = ('native_script_compile_passed', 'native_strategy_compiled', 'native_strategy_saved',
                 'root_save_verified', 'native_saved')
        verified = (receipt.get('read_only') is (not changed) and receipt.get('write_attempted') is changed
                    and receipt.get('native_result_may_be_partial') is not True
                    and receipt.get('status') == ('applied_and_saved' if changed else 'no_changes')
                    and receipt.get('native_project_compile_required') is changed
                    and all(receipt.get(flag) is changed for flag in flags)
                    and (not changed or (receipt.get('unselected_strategy_nodes_verified') is True
                         and visibility_mode(receipt.get('original_project_compile_state_before'))
                         and visibility_mode(receipt.get('original_project_compile_state_after')))))
        return 0 if verified else 2
    if receipt.get('op') in PAGE_CREATION_COMMANDS:
        flags = ('native_saved', 'page_save_verified', 'root_save_verified',
                 'post_save_page_readback_verified', 'original_active_view_preserved')
        verified = (receipt.get('read_only') is False and receipt.get('write_attempted') is True
                    and receipt.get('native_result_may_be_partial') is not True
                    and type(receipt.get('completed_count')) is int and receipt['completed_count'] == 1
                    and type(receipt.get('native_page_save_called')) is bool
                    and all(receipt.get(flag) is True for flag in flags)
                    and created_page_matches(receipt, receipt['op']))
        return 0 if verified else 2
    if receipt.get('op') in BATCH_COMMANDS:
        flags = ('view_refresh_verified', 'page_save_verified', 'root_save_verified')
        completed = receipt.get('completed_count')
        append_check = APPENDED_CONTROL_CHECKS.get(receipt.get('op'))
        if append_check is not None:
            view = receipt.get('page_view')
            verified = (receipt.get('read_only') is False and receipt.get('write_attempted') is True
                        and receipt.get('native_result_may_be_partial') is not True
                        and isinstance(view, dict) and view.get('exact_page_is_active') is True
                        and type(view.get('page_id')) is int and 0 <= view['page_id'] <= 0x7fffffff
                        and isinstance(view.get('page'), str) and bool(view['page'])
                        and all(receipt.get(flag) is True for flag in flags) and append_check[1](receipt))
        elif receipt.get('status') == 'no_changes':
            verified = (receipt.get('read_only') is True and receipt.get('write_attempted') is False
                        and type(completed) is int and completed == 0
                        and all(receipt.get(flag) is False for flag in flags))
        else:
            verified = (receipt.get('write_attempted') is True and type(completed) is int and completed > 0
                        and all(receipt.get(flag) is True for flag in flags))
        return 0 if verified else 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection', required=True, type=Path, help='Connected turnkey prepare-online JSON receipt')
    commands = parser.add_subparsers(dest='command', required=True)
    for operation in (*COMMANDS, 'request-result', lifecycle.REOPEN, lifecycle.READ_REOPEN):
        command = commands.add_parser(operation, help='Run the original project check' if operation == 'compile' else None)
        command.add_argument('--project', required=True, type=Path)
        command.add_argument('--out', help='New result file inside the connection runtime')
        command.add_argument('--id', required=operation in ('request-result', lifecycle.READ_REOPEN))
        if operation == 'request-result':
            command.add_argument('--request-sha256', required=True)
        else:
            command.add_argument('--timeout', type=float, default=30)
        if operation == lifecycle.READ_REOPEN:
            command.add_argument('--continue-open', action='store_true', help='Submit only the unsubmitted open stage after a verified close')
        if operation in PAGE_COMMANDS:
            command.add_argument('--page-id', required=True, type=int)
            command.add_argument('--page', required=True, help='Exact current page name')
        if operation in BATCH_COMMANDS:
            help_text = ('Single-page batch with current source selectors and target rectangles' if operation == CLONE_COMMAND
                         else 'Single-page batch with original control field values')
            if operation == CREATE_COMMAND:
                help_text = 'Single-page batch with native control types and target rectangles'
            command.add_argument('--spec', required=True, type=Path, help=help_text)
        if operation in PAGE_CREATION_COMMANDS:
            command.add_argument('--spec', required=True, type=Path, help='New page name, current page count and copy selector')
        if operation == PAGE_BACKGROUND_EDIT_COMMAND:
            command.add_argument('--spec', required=True, type=Path, help='Exact page and current/requested background COLORREF')
        if operation in MODULE_SPEC_COMMANDS:
            command.add_argument('--spec', required=operation != DATA_CATALOG_COMMAND, type=Path,
                                 help='JSON options from the current native directory or record')
    args = parser.parse_args(argv)
    try:
        connection = Connection.read(args.connection)
        layout, queue = bind(connection)
        result = execute(args, connection, layout, queue)
    except (OSError, ValueError) as error:
        result = {'ok': False, 'error_type': type(error).__name__, 'error': str(error), 'automatic_retry': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_status(result)


if __name__ == '__main__':
    raise SystemExit(main())
