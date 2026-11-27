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
RECIPE_REFERENCE_READ_COMMAND = 'recipe-reference-inspect'
RECIPE_RENAME_COMMAND = 'recipe-rename-referenced'
RECIPE_REFERENCE_COMMANDS = (RECIPE_REFERENCE_READ_COMMAND, RECIPE_RENAME_COMMAND)
STRATEGY_CATALOG_COMMAND = 'strategy-catalog'
STRATEGY_READ_COMMAND = 'strategy-source-read'
STRATEGY_EDIT_COMMAND = 'strategy-source-edit'
TRIGGER_CATALOG_COMMAND = 'strategy-trigger-catalog'
TRIGGER_READ_COMMAND = 'strategy-trigger-read'
TRIGGER_COMMANDS = (TRIGGER_CATALOG_COMMAND, TRIGGER_READ_COMMAND)
LANGUAGE_CATALOG_COMMAND = 'language-catalog'
LANGUAGE_TEXT_COMMAND = 'language-text-edit'
LANGUAGE_ADD_COMMAND = 'language-add'
LANGUAGE_WRITES = (LANGUAGE_TEXT_COMMAND, LANGUAGE_ADD_COMMAND)
LANGUAGE_COMMANDS = (LANGUAGE_CATALOG_COMMAND, *LANGUAGE_WRITES)
PICTURE_CATALOG_COMMAND = 'picture-catalog'
PICTURE_IMPORT_COMMAND = 'picture-import'
PICTURE_COPY_COMMAND = 'picture-copy'
PICTURE_REPLACE_COMMAND = 'picture-replace'
PICTURE_EXPORT_COMMAND = 'picture-export'
PICTURE_WRITES = (PICTURE_IMPORT_COMMAND, PICTURE_COPY_COMMAND, PICTURE_REPLACE_COMMAND)
PICTURE_COMMANDS = (PICTURE_CATALOG_COMMAND, PICTURE_EXPORT_COMMAND, *PICTURE_WRITES)
PAGE_PROPERTIES_READ_COMMAND = 'page-properties-read'
PAGE_BACKGROUND_EDIT_COMMAND = 'page-background-edit'
PAGE_DESCRIPTION_READ_COMMAND = 'page-description-read'
PAGE_DESCRIPTION_EDIT_COMMAND = 'page-description-edit'
PAGE_DESCRIPTION_COMMANDS = (PAGE_DESCRIPTION_READ_COMMAND, PAGE_DESCRIPTION_EDIT_COMMAND)
PAGE_REFERENCE_READ_COMMAND = 'page-reference-inspect'
PAGE_RENAME_COMMAND = 'page-rename-referenced'
DATA_REFERENCE_READ_COMMAND = 'data-reference-inspect'
DATA_RENAME_COMMAND = 'data-rename-referenced'
REFERENCE_RENAME_COMMANDS = (PAGE_RENAME_COMMAND, DATA_RENAME_COMMAND)
REFERENCE_COMMANDS = (PAGE_REFERENCE_READ_COMMAND, DATA_REFERENCE_READ_COMMAND, *REFERENCE_RENAME_COMMANDS)
CONTROL_REFERENCE_READ_COMMAND = 'control-reference-inspect'
CONTROL_RENAME_COMMAND = 'control-rename-referenced'
CONTROL_REFERENCE_COMMANDS = (CONTROL_REFERENCE_READ_COMMAND, CONTROL_RENAME_COMMAND)
SERIAL_READ_COMMAND = 'device-serial-config-read'
SERIAL_EDIT_COMMAND = 'device-serial-config-edit'
SERIAL_COMMANDS = (SERIAL_READ_COMMAND, SERIAL_EDIT_COMMAND)
SERIAL_PARENT_DRIVER_KEYS = ('通用父设备_串口', '通用串口父设备')
VISIBILITY_READ_COMMAND = 'control-visible-read'
VISIBILITY_EDIT_COMMAND = 'control-visible-mode-edit'
VISIBILITY_COMMANDS = (VISIBILITY_READ_COMMAND, VISIBILITY_EDIT_COMMAND)
MODULE_SPEC_COMMANDS = (DATA_CATALOG_COMMAND, DATA_READ_COMMAND, DATA_EDIT_COMMAND,
                        RECIPE_READ_COMMAND, RECIPE_CELL_COMMAND, STRATEGY_READ_COMMAND, STRATEGY_EDIT_COMMAND,
                        DATA_REFERENCE_READ_COMMAND, *REFERENCE_RENAME_COMMANDS, TRIGGER_READ_COMMAND, *VISIBILITY_COMMANDS,
                        *LANGUAGE_COMMANDS, *PICTURE_COMMANDS, *CONTROL_REFERENCE_COMMANDS, *SERIAL_COMMANDS,
                        *RECIPE_REFERENCE_COMMANDS)
READ_COMMANDS = ('inspect', 'capabilities', 'page-catalog', 'control-catalog', lifecycle.PROJECT_STATE,
                 DATA_CATALOG_COMMAND, DATA_READ_COMMAND, RECIPE_CATALOG_COMMAND, RECIPE_READ_COMMAND,
                 STRATEGY_CATALOG_COMMAND, STRATEGY_READ_COMMAND, PAGE_PROPERTIES_READ_COMMAND,
                 PAGE_DESCRIPTION_READ_COMMAND, PAGE_REFERENCE_READ_COMMAND, DATA_REFERENCE_READ_COMMAND,
                 *TRIGGER_COMMANDS, VISIBILITY_READ_COMMAND, LANGUAGE_CATALOG_COMMAND,
                 PICTURE_CATALOG_COMMAND, PICTURE_EXPORT_COMMAND, CONTROL_REFERENCE_READ_COMMAND, SERIAL_READ_COMMAND,
                 RECIPE_REFERENCE_READ_COMMAND)
PAGE_COMMANDS = ('control-catalog', 'page-view-open', PAGE_PROPERTIES_READ_COMMAND,
                 PAGE_DESCRIPTION_READ_COMMAND, PAGE_REFERENCE_READ_COMMAND)
PAGE_CREATE_COMMAND = 'page-native-create'
PAGE_COPY_COMMAND = 'page-native-copy'
PAGE_GENERATE_COMMAND = 'page-native-generate'
PAGE_CREATION_COMMANDS = (PAGE_CREATE_COMMAND, PAGE_COPY_COMMAND)
LABEL_COMMAND = 'label-properties-batch'
GEOMETRY_COMMAND = 'control-geometry-batch'
CLONE_COMMAND = 'control-template-clone-batch'
CREATE_COMMAND = 'control-native-create-batch'
LABEL_FIELDS = {'caption', 'caption_primary', 'text_color_bgr'}
TEMPLATE_CONTROL_RTTI = {0x5008: '.?AVCDrawLabel@@', 0x5025: '.?AVCDrawEdit@@', 0x5027: '.?AVCDrawButton@@'}
NATIVE_LINE = 0x5002
SHAPE_CONTROL_RTTI = {NATIVE_LINE: '.?AVCDrawLine@@', 0x5004: '.?AVCDrawRect@@'}
NATIVE_CONTROL_RTTI = {**TEMPLATE_CONTROL_RTTI, **SHAPE_CONTROL_RTTI}
REFERENCE_CONTROL_RTTI = {0x5008: TEMPLATE_CONTROL_RTTI[0x5008], 0x5033: '.?AVCDrawSaveData@@'}
DATA_IDENTITY_FIELDS = {'name', 'native_id', 'native_type'}
DATA_EDIT_FIELDS = {'comment', 'unit', 'initial_text'}


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


def page_generation_specification(path):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if (not isinstance(options, dict) or options.keys() != {'page_id', 'page', 'expected_top_level_count'}
            or not nonnegative_int32(options['page_id']) or not valid_page_name(options['page'])
            or not nonnegative_int32(options['expected_top_level_count'])):
        raise ValueError('Use the exact original Stu page ID, name and current top-level control count')
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


def valid_page_description(text):
    if not valid_text(text):
        return False
    try:
        return len(text.encode('utf-16-le')) <= 2 * 32768
    except UnicodeEncodeError:
        return False


def project_text_id(value):
    return nonnegative_int32(value) and value >= 10000


def configured_languages(ids):
    return (isinstance(ids, list) and all(nonnegative_int32(value) for value in ids)
            and len(ids) == len(set(ids)))


def language_specification(path, operation):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict):
        raise ValueError('Stu language options must be a JSON object')
    if operation == LANGUAGE_CATALOG_COMMAND:
        if 'text_id' in options:
            valid = options.keys() == {'text_id'} and project_text_id(options['text_id'])
        else:
            limit = options.get('limit', 128)
            valid = (options.keys() <= {'offset', 'limit'} and nonnegative_int32(options.get('offset', 0))
                     and type(limit) is int and 1 <= limit <= 1024)
        if not valid:
            raise ValueError('Use an exact Stu project text ID or a nonnegative offset and a limit of 1 through 1024')
    elif operation == LANGUAGE_TEXT_COMMAND:
        if (options.keys() != {'text_id', 'language_id', 'before', 'after'} or not project_text_id(options['text_id'])
                or not nonnegative_int32(options['language_id'])
                or (options['before'] is not None and not valid_page_description(options['before']))
                or not valid_page_description(options['after']) or options['before'] == options['after']):
            raise ValueError('Select a Stu project text and configured language with exact before and different Unicode after')
    else:
        if (options.keys() != {'language_id', 'language_name', 'expected_configured_language_ids'}
                or not nonnegative_int32(options['language_id']) or not valid_page_description(options['language_name'])
                or not options['language_name'].strip() or not configured_languages(options['expected_configured_language_ids'])
                or not options['expected_configured_language_ids']
                or options['language_id'] in options['expected_configured_language_ids']):
            raise ValueError('Select an original built-in Stu language and the exact existing configured ID order')
    return options


def picture_specification(path, operation):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict):
        raise ValueError('Stu picture options must be a JSON object')
    if operation == PICTURE_CATALOG_COMMAND:
        limit = options.get('limit', 128)
        if (not options.keys() <= {'offset', 'limit'}
                or not nonnegative_int32(options.get('offset', 0)) or type(limit) is not int or not 1 <= limit <= 4096):
            raise ValueError('Use a nonnegative Stu picture offset and a limit of 1 through 4096')
        return options
    keys = {
        PICTURE_IMPORT_COMMAND: {'name', 'expected_count', 'source_file', 'source_sha256'},
        PICTURE_COPY_COMMAND: {'name', 'expected_count', 'source_name', 'source_content_hash'},
        PICTURE_REPLACE_COMMAND: {'name', 'expected_count', 'expected_content_hash', 'source_file', 'source_sha256'},
        PICTURE_EXPORT_COMMAND: {'name', 'expected_content_hash', 'destination_file'},
    }
    if options.keys() != keys[operation] or not valid_page_name(options['name']):
        raise ValueError('Use the exact Stu picture specification and a nonempty native name')
    if operation in PICTURE_WRITES and (not nonnegative_int32(options['expected_count']) or options['expected_count'] > 65536):
        raise ValueError('Use the exact original Stu picture count')
    if operation in (PICTURE_IMPORT_COMMAND, PICTURE_COPY_COMMAND) and (
            options['name'] != options['name'].strip() or len(options['name']) > 64 or re.search(r'[\r\n\t/\\.]', options['name'])):
        raise ValueError('Use a unique native Stu picture name without path characters')
    for key in ('source_name', 'source_content_hash', 'expected_content_hash'):
        if key in options and not valid_page_name(options[key]):
            raise ValueError(f'Use the exact original Stu {key}')
    for key in ('source_file', 'destination_file'):
        if key in options and (not valid_page_name(options[key]) or not Path(options[key]).is_absolute()
                or Path(options[key]).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.bmp', '.svg'}):
            raise ValueError('Use an absolute BMP, JPEG, PNG or SVG picture path')
    if 'source_sha256' in options:
        required_sha(options['source_sha256'], 'The original image file digest')
    return options


def page_description_specification(path):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if (not isinstance(options, dict) or options.keys() != {'page_id', 'page', 'before', 'after'}
            or not nonnegative_int32(options['page_id']) or not valid_page_name(options['page'])):
        raise ValueError('Use the original Stu page ID and exact name with description before and after')
    for item in (options['before'], options['after']):
        if not isinstance(item, dict) or item.keys() != {'description'} or not valid_page_description(item['description']):
            raise ValueError('Stu page descriptions require valid Unicode text of up to 32768 UTF-16 code units')
    return options


def reference_state_matches(state):
    return (isinstance(state, dict) and state.keys() == {'target_linker', 'first_reference_linker', 'status'}
            and valid_page_name(state['target_linker']) and valid_text(state['first_reference_linker'])
            and type(state['status']) is int and state['status'] in (0, 1, 2)
            and (state['status'] == 0) == (state['first_reference_linker'] == ''))


def reference_specification(path, operation):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict):
        raise ValueError('Stu reference options must be an object')
    page = operation == PAGE_RENAME_COMMAND
    editing = operation in REFERENCE_RENAME_COMMANDS
    fields = {'page_id', 'page'} if page else DATA_IDENTITY_FIELDS
    if editing:
        fields = fields | {'expected_reference', 'after'}
        if 'expected_consumer' in options:
            fields |= {'expected_consumer'}
    if (options.keys() != fields or
            (page and (not nonnegative_int32(options['page_id']) or not valid_page_name(options['page'])))
            or (not page and (not valid_page_name(options['name']) or not signed_int32(options['native_id'])
                              or not signed_int32(options['native_type'])))):
        raise ValueError('Use the exact Stu page or variable selector from the current native catalog')
    if editing:
        reference = options['expected_reference']
        if (not reference_state_matches(reference) or not valid_page_name(options['after'])
                or reference['status'] != int('expected_consumer' in options)):
            raise ValueError('Use the complete Stu reference and an exact Prog consumer when one is registered')
        if 'expected_consumer' in options:
            consumer = options['expected_consumer']
            if (not isinstance(consumer, dict) or
                    consumer.keys() != {'block_id', 'block_name', 'row_index', 'source_sha256_utf16le'} or
                    not nonnegative_int32(consumer['block_id']) or not valid_page_name(consumer['block_name']) or
                    not nonnegative_int32(consumer['row_index'])):
                raise ValueError('Use the current Stu Prog consumer ID, name and row')
            required_sha(consumer['source_sha256_utf16le'], 'Stu consumer source SHA-256')
    return options


def sha256_text(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def control_reference_consumers(consumers):
    if not isinstance(consumers, list) or not consumers:
        return False
    owners = set()
    shared = {'owner', 'kind', 'source_sha256_utf16le'}
    for consumer in consumers:
        if (not isinstance(consumer, dict) or not valid_page_name(consumer.get('owner'))
                or not sha256_text(consumer.get('source_sha256_utf16le')) or consumer['owner'] in owners):
            return False
        owners.add(consumer['owner'])
        kind = consumer.get('kind')
        if kind == 'strategy-prog':
            if (consumer.keys() != shared | {'block_id', 'block_name', 'row_index'}
                    or not nonnegative_int32(consumer['block_id']) or not valid_page_name(consumer['block_name'])
                    or not nonnegative_int32(consumer['row_index'])):
                return False
            continue
        fields = shared | {'page_id', 'page'}
        if kind == 'button-release':
            fields |= {'top_level_path', 'control_name', 'native_type_id'}
        elif kind != 'page-open':
            return False
        if (consumer.keys() != fields or not nonnegative_int32(consumer['page_id'])
                or not valid_page_name(consumer['page'])):
            return False
        if kind == 'button-release' and (top_level_index(consumer['top_level_path']) is None
                or not valid_page_name(consumer['control_name']) or consumer['native_type_id'] != 0x5027):
            return False
    return True


def control_reference_specification(path, editing):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict):
        raise ValueError('Use the current Stu page and exact top-level control selector')
    native_type = options.get('native_type_id')
    if not nonnegative_int32(native_type) or native_type not in REFERENCE_CONTROL_RTTI:
        raise ValueError('Use a supported Stu reference control type')
    fields = {'page_id', 'page', 'top_level_path', 'control_name', 'native_type_id'}
    referenced = native_type == 0x5033
    if editing:
        fields.update(('after', 'expected_reference'))
        if referenced:
            fields.update(('expected_graph_sha256', 'expected_consumers'))
    if (options.keys() != fields
            or not nonnegative_int32(options['page_id']) or not valid_page_name(options['page'])
            or not valid_page_name(options['control_name']) or top_level_index(options['top_level_path']) is None):
        raise ValueError('Use the current Stu page and exact top-level control selector')
    if editing:
        before, after = options['expected_reference'], options['after']
        old_name = options['control_name']
        if (not reference_state_matches(before) or before['status'] != int(referenced) or not valid_page_name(after)
                or not before['target_linker'].endswith('.' + old_name) or old_name.casefold() == after.casefold()):
            raise ValueError('Use the current Stu control reference and a different valid name')
        if referenced and (not sha256_text(options['expected_graph_sha256'])
                           or not control_reference_consumers(options['expected_consumers'])):
            raise ValueError('Use the exact Stu registered graph digest and all supported consumer preimages')
    return options


def serial_specification(path, editing):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    keys = {'path', 'native_id', 'field', 'before', 'after'} if editing else {'path'}
    if not isinstance(options, dict) or options.keys() != keys or not valid_serial_path(options['path']):
        raise ValueError('Stu serial configuration requires the exact single parent device path')
    if editing and (not nonnegative_int32(options['native_id']) or options['field'] != 'baud_rate'
                    or (options['before'], options['after']) not in ((9600, 19200), (19200, 9600))
                    or any(type(options[key]) is not int for key in ('before', 'after'))):
        raise ValueError('Stu serial edit requires the current native ID and a change between 9600 and 19200 baud')
    return options


def valid_serial_path(path):
    return isinstance(path, list) and len(path) == 1 and valid_page_name(path[0])


def recipe_consumer_records(consumers):
    if not isinstance(consumers, dict) or consumers.keys() != {'recipe_controls', 'script_literal_references'}:
        return False
    controls, scripts = consumers['recipe_controls'], consumers['script_literal_references']
    if not isinstance(controls, list) or not isinstance(scripts, list):
        return False
    control_fields = {'page_id', 'page_name', 'control_name', 'reference_linker', 'recipe_name', 'plugin_image_sha256'}
    script_fields = {'kind', 'owner_id', 'owner_name', 'index', 'literal_count', 'source_sha256_utf16le'}
    control_links = set()
    for control in controls:
        if (not isinstance(control, dict) or control.keys() != control_fields
                or not nonnegative_int32(control['page_id'])
                or not all(valid_page_name(control[key]) for key in ('page_name', 'control_name', 'reference_linker', 'recipe_name'))
                or not sha256_text(control['plugin_image_sha256']) or control['reference_linker'] in control_links):
            return False
        control_links.add(control['reference_linker'])
    script_keys = set()
    for script in scripts:
        if (not isinstance(script, dict) or script.keys() != script_fields or script['kind'] not in ('strategy', 'close')
                or not nonnegative_int32(script['owner_id']) or not valid_page_name(script['owner_name'])
                or not nonnegative_int32(script['index']) or (script['kind'] == 'close' and script['index'] != 2)
                or not nonnegative_int32(script['literal_count']) or script['literal_count'] == 0
                or not sha256_text(script['source_sha256_utf16le'])):
            return False
        identity = (script['kind'], script['owner_id'], script['index'])
        if identity in script_keys:
            return False
        script_keys.add(identity)
    return True


def recipe_reference_specification(path, editing):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(options, dict):
        raise ValueError('Stu recipe naming requires the exact registered recipe group selector')
    fields = {'group_name'}
    referenced = 'expected_consumers' in options
    if editing:
        fields.update(('after','expected_recipe_index','expected_reference','expected_archive_sha256','expected_index_sha256'))
        if referenced:
            fields.add('expected_consumers')
    elif 'include_referenced_consumers' in options:
        if options['include_referenced_consumers'] is not True:
            raise ValueError('Set include_referenced_consumers to true to inspect supported recipe consumers')
        fields.add('include_referenced_consumers')
    if options.keys() != fields or not valid_page_name(options['group_name']):
        raise ValueError('Stu recipe naming requires the exact registered recipe group selector')
    if editing:
        name, after, reference = options['group_name'], options['after'], options['expected_reference']
        if (not valid_page_name(after) or name.casefold() == after.casefold()
                or not nonnegative_int32(options['expected_recipe_index'])
                or not reference_state_matches(reference) or reference['status'] != int(referenced)
                or not (reference['target_linker'] == name or reference['target_linker'].endswith('.' + name))):
            raise ValueError('Use the current recipe index and reference preimage and choose a different group name')
        required_sha(options['expected_archive_sha256'], 'Stu original recipe archive SHA-256')
        required_sha(options['expected_index_sha256'], 'Stu original recipe index SHA-256')
        if referenced and (not recipe_consumer_records(options['expected_consumers'])
                           or not all(options['expected_consumers'].values())
                           or any(row['recipe_name'] != name for row in options['expected_consumers']['recipe_controls'])):
            raise ValueError('Use the complete Stu recipe control and script consumer preimages for this group')
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
                or not before or before.keys() != after.keys() or before.keys() - DATA_EDIT_FIELDS
                or not all(valid_text(value) for value in (*before.values(), *after.values()))):
            raise ValueError('Use matching before/after fields for a Stu scalar comment, unit or initial value')
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


def trigger_specification(path):
    options = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if (not isinstance(options, dict) or options.keys() != {'block_id', 'block_name'}
            or not nonnegative_int32(options['block_id']) or not valid_page_name(options['block_name'])):
        raise ValueError('Use the original Stu strategy block ID and exact name')
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


def valid_control_geometry(rect, native_type):
    if native_type != NATIVE_LINE:
        return positive_rect(rect)
    x1, y1, x2, y2 = rect
    return (x1, y1) != (x2, y2) and abs(x1 - x2) <= 0x7fffffff and abs(y1 - y2) <= 0x7fffffff


def check_target_rect(state, native_type=None):
    rect = rect_from_state(state)
    if not int32_rect(rect):
        raise ValueError('after.rect must contain four signed Int32 coordinates')
    if not valid_control_geometry(rect, native_type):
        if native_type == NATIVE_LINE:
            raise ValueError('A Stu line needs distinct ordered endpoints with signed Int32 distances')
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
        check_target_rect(item['after'], item['native_type_id'] if distinct_sources else None)
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
            raise ValueError('Unknown Stu default control type')
        check_target_rect(item['after'], native_type)
    return options


BATCH_SPECIFICATIONS = {
    LABEL_COMMAND: label_specification,
    GEOMETRY_COMMAND: geometry_specification,
    CLONE_COMMAND: clone_specification,
    CREATE_COMMAND: create_specification,
}
BATCH_COMMANDS = tuple(BATCH_SPECIFICATIONS)
COMMANDS = (*READ_COMMANDS, 'compile', 'page-view-open', *PAGE_CREATION_COMMANDS, PAGE_GENERATE_COMMAND, *BATCH_COMMANDS,
            DATA_EDIT_COMMAND, RECIPE_CELL_COMMAND, STRATEGY_EDIT_COMMAND, PAGE_BACKGROUND_EDIT_COMMAND,
            PAGE_DESCRIPTION_EDIT_COMMAND, *REFERENCE_RENAME_COMMANDS, VISIBILITY_EDIT_COMMAND, *LANGUAGE_WRITES,
            *PICTURE_WRITES, CONTROL_RENAME_COMMAND, SERIAL_EDIT_COMMAND, RECIPE_RENAME_COMMAND)


def language_receipt_matches(receipt, operation, options=None):
    ids = receipt.get('configured_language_ids')
    if (not configured_languages(ids) or not signed_int32(receipt.get('current_language_id'))
            or not signed_int32(receipt.get('preview_language_id')) or not project_text_id(receipt.get('next_project_text_id'))):
        return False
    if operation == LANGUAGE_CATALOG_COMMAND:
        definitions, texts, count = (receipt.get(key) for key in ('language_definitions', 'project_texts', 'project_text_count'))
        if (receipt.get('read_only') is not True or not nonnegative_int32(count) or not isinstance(texts, list)
                or len(texts) > count or not isinstance(definitions, list)
                or type(receipt.get('language_dirty')) is not int or receipt['language_dirty'] not in (0, 1)
                or not all(isinstance(item, dict) and nonnegative_int32(item.get('language_id')) and all(
                    valid_text(item.get(field)) for field in ('name', 'font_primary', 'font_alternate')) for item in definitions)):
            return False
        definition_ids = {item['language_id'] for item in definitions}
        if len(definition_ids) != len(definitions) or not set(ids) <= definition_ids:
            return False
        text_ids = []
        for text in texts:
            if not isinstance(text, dict) or not project_text_id(text.get('text_id')) or not isinstance(text.get('translations'), list):
                return False
            translations = text['translations']
            if not all(isinstance(item, dict) and nonnegative_int32(item.get('language_id'))
                       and valid_text(item.get('text')) for item in translations):
                return False
            if len({item['language_id'] for item in translations}) != len(translations):
                return False
            text_ids.append(text['text_id'])
        if text_ids != sorted(set(text_ids)):
            return False
        if options is None:
            return True
        if 'text_id' in options:
            return text_ids in ([], [options['text_id']])
        return len(texts) == min(options.get('limit', 128), count - options.get('offset', 0))
    flags = ('write_attempted', 'language_module_saved', 'root_save_verified',
             'unselected_translations_verified', 'language_selectors_preserved')
    language = receipt.get('language_id')
    if (receipt.get('read_only') is not False or receipt.get('native_result_may_be_partial') is not False
            or receipt.get('automatic_retry') is not False or receipt.get('status') != 'applied_and_saved'
            or not all(receipt.get(flag) is True for flag in flags) or not nonnegative_int32(language) or language not in ids
            or options is not None and language != options['language_id']):
        return False
    if operation == LANGUAGE_TEXT_COMMAND:
        return (project_text_id(receipt.get('text_id')) and valid_page_description(receipt.get('text'))
                and (options is None or (receipt['text_id'], receipt['text']) == (options['text_id'], options['after'])))
    return (valid_page_name(receipt.get('language_name')) and receipt.get('native_font_mapping_refreshed') is True
            and (options is None or (receipt['language_name'] == options['language_name']
                 and ids == options['expected_configured_language_ids'] + [language])))


def picture_record_matches(record):
    if not isinstance(record, dict):
        return False
    formats = {0: 'bmp', 1: 'jpeg', 2: 'png', 3: 'svg'}
    kind = record.get('image_kind')
    return (nonnegative_int32(record.get('index')) and valid_page_name(record.get('name'))
            and valid_text(record.get('content_hash')) and signed_int32(kind) and nonnegative_int32(record.get('cached_bytes'))
            and type(record.get('reference_only')) is bool and record.get('file_format') == formats.get(kind, 'unknown'))


def picture_receipt_matches(receipt, operation, options=None):
    count = receipt.get('picture_count')
    if not nonnegative_int32(count) or receipt.get('automatic_retry') is not False:
        return False
    if operation == PICTURE_CATALOG_COMMAND:
        rows = receipt.get('records')
        if (receipt.get('read_only') is not True or not isinstance(rows, list) or len(rows) > count
                or not all(picture_record_matches(row) and row['index'] < count for row in rows)
                or type(receipt.get('picture_module_dirty')) is not int or receipt['picture_module_dirty'] not in (0, 1)):
            return False
        indices = [row['index'] for row in rows]
        if indices and indices != list(range(indices[0], indices[0] + len(indices))):
            return False
        if options is None:
            return True
        offset = options.get('offset', 0)
        return indices == list(range(offset, min(count, offset + options.get('limit', 128)))) and offset <= count
    record = receipt.get('record')
    if (not picture_record_matches(record) or record['index'] >= count or record['reference_only']
            or not record['content_hash'] or record['file_format'] == 'unknown' or not re.fullmatch(r'[0-9a-f]{64}',
                receipt.get('file_sha256') if isinstance(receipt.get('file_sha256'), str) else '')
            or options is not None and record['name'] != options['name']):
        return False
    if operation == PICTURE_EXPORT_COMMAND:
        destination = receipt.get('destination_file')
        return (receipt.get('read_only') is True and receipt.get('file_written') is True
                and valid_page_name(destination) and Path(destination).is_absolute()
                and nonnegative_int32(receipt.get('file_bytes')) and receipt['file_bytes'] > 0
                and (options is None or (Path(destination).resolve() == Path(options['destination_file']).resolve()
                     and record['content_hash'] == options['expected_content_hash'])))
    flags = ('write_attempted', 'native_module_saved', 'root_saved', 'native_catalog_preserved', 'native_archive_readback_verified')
    replacing = operation == PICTURE_REPLACE_COMMAND
    return (receipt.get('read_only') is False and receipt.get('native_result_may_be_partial') is False
            and all(receipt.get(flag) is True for flag in flags) and receipt.get('native_object_identity_preserved') is replacing
            and type(receipt.get('input_header_normalized')) is bool and receipt.get('status') == 'applied_and_saved'
            and (replacing or record['index'] == count - 1)
            and (options is None or (count == options['expected_count'] + (0 if replacing else 1)
                 and (operation != PICTURE_COPY_COMMAND or record['content_hash'] == options['source_content_hash'])
                 and ('source_sha256' not in options or receipt['input_header_normalized']
                      or receipt['file_sha256'] == options['source_sha256']))))


def page_generation_matches(receipt, options=None):
    flags = ('native_page_generate_return', 'native_selected_page_generated', 'view_refresh_verified',
             'page_save_verified', 'root_save_verified', 'write_attempted')
    return (receipt.get('status') == 'applied_and_saved' and receipt.get('read_only') is False
            and receipt.get('native_result_may_be_partial') is False and receipt.get('automatic_retry') is False
            and type(receipt.get('completed_count')) is int and receipt['completed_count'] == 1
            and all(receipt.get(flag) is True for flag in flags) and nonnegative_int32(receipt.get('page_id'))
            and valid_page_name(receipt.get('page')) and nonnegative_int32(receipt.get('top_level_control_count'))
            and exact_page(receipt.get('page_view'), receipt) and receipt['page_view'].get('exact_page_is_active') is True
            and (options is None or (exact_page(receipt, options)
                 and receipt['top_level_control_count'] == options['expected_top_level_count'])))


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


def page_description_matches(receipt, editing, expected=None):
    current = receipt.get('page_description')
    if (not isinstance(current, dict) or not nonnegative_int32(current.get('page_id'))
            or not valid_page_name(current.get('page')) or not valid_page_description(current.get('description'))
            or expected is not None and not exact_page(current, expected)):
        return False
    if not editing:
        return True
    before = receipt.get('before')
    return (exact_page(before, current) and valid_page_description(before.get('description'))
            and receipt.get('adjacent_string_preserved') is True
            and (expected is None or (before['description'], current['description'])
                 == (expected['before']['description'], expected['after']['description'])))


def reference_receipt_matches(receipt, operation, expected=None):
    before = receipt.get('before_reference')
    if not reference_state_matches(before):
        return False
    incoming = receipt.get('registered_incoming_edges')
    if not isinstance(incoming, list) or any(not isinstance(edge, dict) or edge.keys() != {'source', 'target'}
                                             or not all(valid_page_name(value) for value in edge.values()) for edge in incoming):
        return False
    page = operation in (PAGE_REFERENCE_READ_COMMAND, PAGE_RENAME_COMMAND)
    if page:
        if not nonnegative_int32(receipt.get('page_id')) or expected is not None and receipt['page_id'] != expected['page_id']:
            return False
    else:
        data = expected
        if expected is not None and operation == DATA_RENAME_COMMAND:
            data = {**expected, 'name': expected['after']}
        if not data_record_matches(receipt.get('record'), data):
            return False

    if operation not in REFERENCE_RENAME_COMMANDS:
        if expected is None:
            return True
        name = expected['page' if page else 'name']
        return before['target_linker'] == name or before['target_linker'].endswith('.' + name)
    expected_incoming = [] if before['status'] == 0 else [
        {'source': before['first_reference_linker'], 'target': before['target_linker']}]
    if incoming != expected_incoming or receipt.get('complete_registered_graph_preserved') is not True:
        return False
    old_name, new_name = receipt.get('old_name'), receipt.get('new_name')
    current, old = receipt.get('after_reference'), receipt.get('old_reference_after')
    if (not valid_page_name(old_name) or not valid_page_name(new_name) or old_name.casefold() == new_name.casefold()
            or not reference_state_matches(current) or not reference_state_matches(old)
            or not (before['target_linker'] == old_name or before['target_linker'].endswith('.' + old_name))
            or current['target_linker'] != before['target_linker'][:-len(old_name)] + new_name
            or old != {'target_linker': before['target_linker'], 'status': 0, 'first_reference_linker': ''}
            or (current['status'], current['first_reference_linker']) != (before['status'], before['first_reference_linker'])):
        return False
    consumer = receipt.get('strategy_consumer')
    if before['status'] == 1:
        if (not isinstance(consumer, dict) or not nonnegative_int32(consumer.get('block_id'))
                or not valid_page_name(consumer.get('block_name')) or not nonnegative_int32(consumer.get('row_index'))):
            return False
        hashes = (consumer.get('source_before_sha256_utf16le'), consumer.get('source_after_sha256_utf16le'))
        if hashes[0] == hashes[1] or not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes):
            return False
        if expected is not None:
            selected = expected.get('expected_consumer')
            if not selected or (any(consumer[key] != selected[key] for key in ('block_id', 'block_name', 'row_index'))
                                or hashes[0] != selected['source_sha256_utf16le']):
                return False
    elif before['status'] != 0 or consumer is not None:
        return False
    return expected is None or (
        before == expected['expected_reference'] and (old_name, new_name) == (expected['page' if page else 'name'], expected['after'])
    )


def control_reference_matches(receipt, operation, expected=None):
    before, control = receipt.get('before_reference'), receipt.get('control')
    page_id, page = receipt.get('page_id'), receipt.get('page')
    native_type = control.get('native_type_id') if isinstance(control, dict) else None
    if (not reference_state_matches(before) or not isinstance(control, dict)
            or not nonnegative_int32(page_id) or not valid_page_name(page)
            or not valid_page_name(control.get('name')) or not nonnegative_int32(native_type)
            or native_type not in REFERENCE_CONTROL_RTTI or control.get('native_class') != REFERENCE_CONTROL_RTTI[native_type]
            or control.get('document_owned') is not True or top_level_index(control.get('top_level_path')) is None):
        return False
    edges = [receipt.get('registered_incoming_edges'), receipt.get('registered_outgoing_edges')]
    if any(not isinstance(rows, list) or any(not isinstance(edge, dict) or edge.keys() != {'source', 'target'}
           or not all(valid_page_name(value) for value in edge.values()) for edge in rows) for rows in edges):
        return False
    if expected is not None and (page_id != expected['page_id'] or page != expected['page']
                                 or native_type != expected['native_type_id']
                                 or control['top_level_path'] != expected['top_level_path']):
        return False
    referenced = native_type == 0x5033
    if referenced:
        consumers = receipt.get('reference_consumers')
        graph = receipt.get('registered_graph_sha256')
        if (before['status'] != 1 or not control_reference_consumers(consumers) or not sha256_text(graph)
                or {item['owner'] for item in consumers} != {edge['source'] for edge in edges[0]}):
            return False
        owners = {item['owner'] for item in consumers}
        if before['first_reference_linker'] not in owners:
            return False
    if operation == CONTROL_REFERENCE_READ_COMMAND:
        return (receipt.get('read_only') is True and before['target_linker'].endswith('.' + control['name'])
                and (expected is None or control['name'] == expected['control_name']))

    old_name, new_name = receipt.get('old_name'), receipt.get('new_name')
    after, cleared = receipt.get('after_reference'), receipt.get('old_reference_after')
    if (not valid_page_name(old_name) or not valid_page_name(new_name) or old_name.casefold() == new_name.casefold()
            or before['status'] != int(referenced) or not before['target_linker'].endswith('.' + old_name)
            or cleared != dict(before, status=0, first_reference_linker='')
            or not reference_state_matches(after) or after['status'] != before['status']
            or after['target_linker'] != before['target_linker'][:-len(old_name)] + new_name
            or control['name'] != new_name):
        return False
    saved_pages = {page_id}
    flags = ('complete_registered_graph_preserved', 'page_save_verified', 'root_save_verified',
             'write_attempted', 'target_view_closed')
    if referenced:
        after_graph = receipt.get('registered_graph_sha256_after')
        after_consumers = receipt.get('reference_consumers_after')
        if (after['first_reference_linker'] not in owners or not sha256_text(after_graph) or after_graph == graph
                or not control_reference_consumers(after_consumers)
                or not same_consumer_identities(consumers, after_consumers)
                or expected is not None and (graph, consumers) != (expected['expected_graph_sha256'], expected['expected_consumers'])):
            return False
        saved_pages.update(item['page_id'] for item in consumers if 'page_id' in item)
        if any(item['kind'] == 'strategy-prog' for item in consumers):
            flags += ('strategy_save_verified',)
    elif (edges != [[], []] or after['first_reference_linker'] != before['first_reference_linker']
          or receipt.get('reference_scope_zero_edges') is not True):
        return False
    saved = receipt.get('saved_page_ids')
    return (receipt.get('read_only') is False and receipt.get('native_result_may_be_partial') is False
            and receipt.get('status') == 'applied_and_saved' and isinstance(saved, list)
            and all(nonnegative_int32(item) for item in saved) and len(saved) == len(saved_pages) and set(saved) == saved_pages
            and all(receipt.get(flag) is True for flag in flags)
            and (expected is None or (before,old_name,new_name) == (expected['expected_reference'],
                                                                   expected['control_name'],expected['after'])))


def same_consumer_identities(before, after):
    digest = 'source_sha256_utf16le'
    return (len(before) == len(after) and
            all(old[digest] != new[digest] and {k: v for k, v in old.items() if k != digest} ==
                {k: v for k, v in new.items() if k != digest} for old, new in zip(before, after)))


def serial_record_matches(record):
    if (not isinstance(record, dict) or not valid_serial_path(record.get('path'))
            or record.get('name') != record['path'][0] or record.get('driver_key') not in SERIAL_PARENT_DRIVER_KEYS
            or record.get('native_class') != 'CDevHalComm' or not nonnegative_int32(record.get('native_id'))
            or record.get('stop_bits') != '1' or record.get('parity') != 'none'):
        return False
    fields = {'port_number': 1, 'data_bits': 8, 'child_driver_count': 0}
    baud, codes = record.get('baud_rate'), record.get('native_codes')
    return (all(type(record.get(key)) is int and record[key] == value for key, value in fields.items())
            and type(baud) is int and baud in (9600, 19200) and isinstance(codes, dict)
            and codes == {'port_number': 1, 'baud_rate': 6 if baud == 9600 else 8,
                          'data_bits': 1, 'stop_bits': 0, 'parity': 0}
            and all(type(item) is int for item in codes.values()))


def serial_receipt_matches(receipt, operation, expected=None):
    record = receipt.get('record')
    calls = receipt.get('explicit_driver_runtime_calls')
    if (not serial_record_matches(record) or type(calls) is not int or calls != 0
            or receipt.get('native_result_may_be_partial') is not False
            or expected is not None and record['path'] != expected['path']):
        return False
    if operation == SERIAL_READ_COMMAND:
        return (receipt.get('status') == 'serial_config_read' and receipt.get('read_only') is True
                and receipt.get('write_attempted') is False)
    before = receipt.get('previous_record')
    if not serial_record_matches(before) or before['baud_rate'] == record['baud_rate']:
        return False
    check = receipt.get('original_check')
    if (not isinstance(check, dict) or check.get('ok') is not True or check.get('native_compile_executed') is not True
            or check.get('native_compile_verified') is not True or check.get('compile_result') != 0
            or check.get('compile_valid') != 1 or check.get('errors') != 0 or not nonnegative_int32(check.get('warnings'))):
        return False
    codes = dict(before['native_codes'], baud_rate=record['native_codes']['baud_rate'])
    return (record == dict(before, baud_rate=record['baud_rate'], native_codes=codes)
            and receipt.get('status') == 'serial_config_saved' and receipt.get('modified_field') == 'baud_rate'
            and receipt.get('read_only') is False and all(receipt.get(flag) is True for flag in (
                'write_attempted','device_document_saved','project_saved'))
            and (expected is None or (record['native_id'],before['baud_rate'],record['baud_rate']) == (
                expected['native_id'],expected['before'],expected['after'])))


def recipe_reference_matches(receipt, operation, expected=None):
    group, index, count = receipt.get('group_name'), receipt.get('recipe_index'), receipt.get('recipe_count')
    before, record = receipt.get('before_reference'), receipt.get('record')
    original_hashes = (receipt.get('recipe_archive_sha256'), receipt.get('recipe_index_sha256'))
    writing = operation == RECIPE_RENAME_COMMAND
    current_group = receipt.get('new_name') if writing else group
    if (not valid_page_name(group) or not nonnegative_int32(index) or not nonnegative_int32(count) or index >= count
            or not reference_state_matches(before) or not isinstance(record, dict) or record.get('group_name') != current_group
            or not all(isinstance(item, str) and re.fullmatch(r'[0-9a-f]{64}', item) for item in original_hashes)):
        return False
    edges = receipt.get('registered_incoming_edges')
    if not isinstance(edges, list) or any(not isinstance(edge, dict) or edge.keys() != {'source', 'target'}
                                          or not all(valid_page_name(value) for value in edge.values()) for edge in edges):
        return False
    scope = receipt.get('consumer_scope')
    scope_fields = {'user_pages', 'pages_with_controls', 'pages_with_source', 'pages_with_dispatch',
                    'strategy_blocks', 'strategies_with_rows', 'event_triggers'}
    page_counts = ('pages_with_controls', 'pages_with_source', 'pages_with_dispatch')
    if (not isinstance(scope, dict) or scope.keys() != scope_fields
            or not all(nonnegative_int32(value) for value in scope.values())
            or any(scope[field] > scope['user_pages'] for field in page_counts)
            or scope['strategies_with_rows'] > scope['strategy_blocks']
            or not (before['target_linker'] == group or before['target_linker'].endswith('.' + group))):
        return False
    consumer_free = (before['status'] == 0 and not edges
                     and not any(scope[field] for field in (*page_counts, 'strategies_with_rows', 'event_triggers')))
    if receipt.get('no_recipe_consumers_verified') is not consumer_free:
        return False
    referenced = receipt.get('referenced_consumers_supported') is True
    if not writing:
        if receipt.get('read_only') is not True or (expected is not None and group != expected['group_name']):
            return False
        if 'referenced_consumers_supported' in receipt or (expected is not None and expected.get('include_referenced_consumers')):
            reasons = receipt.get('unsupported_recipe_consumer_reasons')
            if (type(receipt.get('referenced_consumers_supported')) is not bool
                    or not recipe_consumer_records(receipt.get('recipe_consumers'))
                    or not isinstance(reasons, list) or not all(valid_page_name(item) for item in reasons)):
                return False
        return not referenced or recipe_consumer_readback_matches(receipt.get('recipe_consumers'), before, group, edges)
    old_name, new_name = receipt.get('old_name'), receipt.get('new_name')
    after, cleared = receipt.get('after_reference'), receipt.get('old_reference_after')
    if (old_name != group or not valid_page_name(new_name) or old_name.casefold() == new_name.casefold()
            or (not referenced and not consumer_free)
            or cleared != dict(before, status=0, first_reference_linker='')
            or not reference_state_matches(after) or after['status'] != before['status']
            or after['first_reference_linker'] != before['first_reference_linker']
            or after['target_linker'] != before['target_linker'][:-len(old_name)] + new_name):
        return False
    if expected is not None and referenced != ('expected_consumers' in expected):
        return False
    if referenced and not recipe_consumer_write_matches(receipt, before, group, new_name, edges, expected):
        return False
    before_hashes = (receipt.get('before_recipe_archive_sha256'), receipt.get('before_recipe_index_sha256'))
    saved_hashes = (receipt.get('saved_recipe_archive_sha256'), receipt.get('saved_recipe_index_sha256'))
    flags = ('write_attempted', 'recipe_save_verified', 'root_save_verified', 'project_saved',
             'native_index_verified', 'target_recipe_payload_preserved', 'old_named_blob_preserved')
    return (before_hashes == original_hashes
            and all(isinstance(saved, str) and re.fullmatch(r'[0-9a-f]{64}', saved) and saved != original
                    for original, saved in zip(original_hashes, saved_hashes))
            and receipt.get('read_only') is False
            and receipt.get('native_result_may_be_partial') is False and receipt.get('status') == 'applied_and_saved'
            and all(receipt.get(flag) is True for flag in flags)
            and (expected is None or (old_name, new_name, index, before, *original_hashes) == (
                expected['group_name'], expected['after'], expected['expected_recipe_index'], expected['expected_reference'],
                expected['expected_archive_sha256'], expected['expected_index_sha256'])))


def recipe_consumer_readback_matches(consumers, before, group, edges):
    if before['status'] != 1 or not recipe_consumer_records(consumers):
        return False
    controls = consumers['recipe_controls']
    return (bool(controls) and bool(consumers['script_literal_references'])
            and {row['reference_linker'] for row in controls} == {edge['source'] for edge in edges}
            and all(row['recipe_name'] == group for row in controls))


def recipe_consumer_write_matches(receipt, before, group, new_name, edges, expected):
    old, new = receipt.get('recipe_consumers'), receipt.get('recipe_consumers_after')
    if (not recipe_consumer_readback_matches(old, before, group, edges) or not recipe_consumer_records(new)
            or (expected is not None and old != expected['expected_consumers'])
            or new['recipe_controls'] != [dict(control, recipe_name=new_name) for control in old['recipe_controls']]
            or not same_consumer_identities(old['script_literal_references'], new['script_literal_references'])):
        return False
    pairs = zip(old['script_literal_references'], new['script_literal_references'])
    updates = [dict(previous, source_after_sha256_utf16le=current['source_sha256_utf16le']) for previous, current in pairs]
    pages = {row['page_id'] for row in old['recipe_controls']}
    pages.update(row['owner_id'] for row in old['script_literal_references'] if row['kind'] == 'close')
    saved = receipt.get('saved_page_ids')
    return (receipt.get('script_updates') == updates and receipt.get('complete_registered_graph_preserved') is True
            and receipt.get('strategy_save_verified') is True and isinstance(saved, list)
            and len(saved) == len(pages) and all(nonnegative_int32(page) for page in saved) and set(saved) == pages)


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
    if (not isinstance(fields, list) or any(not isinstance(field, str) or field not in DATA_EDIT_FIELDS
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


def trigger_receipt_matches(receipt, operation, expected=None):
    if receipt.get('all_requested_features_available') is not True or receipt.get('unavailable') != []:
        return False
    if operation == TRIGGER_READ_COMMAND:
        strategy = receipt.get('strategy')
        if not strategy_summary_matches(strategy) or expected is not None and any(
                strategy[key] != expected[key] for key in ('block_id', 'block_name')):
            return False
        if 'trigger' not in receipt:
            return False
        if receipt['trigger'] is None:
            return True
        rows = [receipt['trigger']]
        if not isinstance(rows[0], dict) or any(rows[0].get(key) != strategy[key] for key in ('block_id', 'block_name')):
            return False
    else:
        count, rows = receipt.get('trigger_count'), receipt.get('triggers')
        if not nonnegative_int32(count) or not isinstance(rows, list) or len(rows) != count:
            return False
    types = ('CTriggerStart', 'CTriggerEnd', 'CTriggerLoop', 'CTriggerUser', 'CTriggerEvent')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        kind = row.get('native_type')
        if (not nonnegative_int32(kind) or kind >= len(types) or row.get('native_class') != types[kind]
                or not nonnegative_int32(row.get('trigger_id'))
                or not nonnegative_int32(row.get('block_id')) or row['block_id'] in seen or not valid_page_name(row.get('block_name'))
                or not valid_text(row.get('note'))):
            return False
        seen.add(row['block_id'])
        if kind == 2:
            schedule = row.get('schedule')
            if not isinstance(schedule, dict) or not all(signed_int32(schedule.get(field)) for field in (
                    'native_mode', 'interval_ms', 'native_calendar_period', 'month', 'day', 'hour', 'minute', 'second')):
                return False
        if kind == 4 and not valid_text(row.get('expression')):
            return False
        words = row.get('raw_common_fields')
        if not isinstance(words, list) or len(words) != 3 or any(type(word) is not int or not 0 <= word <= 0xffffffff for word in words):
            return False
        if kind == 4:
            words = row.get('raw_event_fields')
            if not isinstance(words, list) or len(words) != 2 or any(type(word) is not int or not 0 <= word <= 0xffffffff for word in words):
                return False
    return True


def completed_changes(receipt, expected):
    changes = receipt.get('changes')
    count = receipt.get('completed_count')
    if (isinstance(changes, list) and type(count) is int and count > 0 and len(changes) == count
            and (expected is None or len(expected) == count)):
        return changes
    return None


def original_append(row, preservation_field, classes):
    if not isinstance(row, dict) or not isinstance(row.get('actual'), dict):
        return None
    actual = row['actual']
    native_type = row.get('native_type_id')
    name, rect = actual.get('control_name'), actual.get('rect')
    index = top_level_index(actual.get('top_level_path'))
    if (type(native_type) is not int or native_type not in classes
            or type(actual.get('native_type_id')) is not int or actual['native_type_id'] != native_type
            or actual.get('native_class') != classes[native_type]
            or not isinstance(name, str) or not name or '\0' in name
            or index is None or not int32_rect(rect) or not valid_control_geometry(rect, native_type)
            or actual.get(preservation_field) is not True):
        return None
    return name.casefold(), index, rect


def contiguous_indexes(indexes):
    return all(after == before + 1 for before, after in zip(indexes, indexes[1:]))


def geometry_changes_match(receipt, expected=None):
    rows = receipt.get('changes')
    if not isinstance(rows, list) or not rows or expected is not None and len(rows) != len(expected):
        return False
    indices, changed = set(), 0
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            return False
        index = top_level_index(row.get('top_level_path'))
        native_type = row.get('native_type_id')
        before, after = rect_from_state(row.get('before')), rect_from_state(row.get('actual'))
        if (index is None or index in indices or not nonnegative_int32(native_type)
                or not valid_page_name(row.get('control_name')) or not valid_page_name(row.get('native_class'))
                or not int32_rect(before) or not int32_rect(after) or not valid_control_geometry(after, native_type)):
            return False
        if native_type in NATIVE_CONTROL_RTTI and row['native_class'] != NATIVE_CONTROL_RTTI[native_type]:
            return False
        if expected is not None and (
                any(row[key] != expected[i][key] for key in ('control_name', 'native_type_id', 'top_level_path', 'before'))
                or after != expected[i]['after']['rect']):
            return False
        if before != after:
            if native_type in SHAPE_CONTROL_RTTI and row.get('original_style_preserved') is not True:
                return False
            changed += 1
        indices.add(index)
    count = receipt.get('completed_count')
    return type(count) is int and count == changed


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
        result = original_append(row, 'original_payload_preserved', TEMPLATE_CONTROL_RTTI)
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
        result = original_append(row, 'original_defaults_preserved', NATIVE_CONTROL_RTTI)
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
        if operation == PAGE_GENERATE_COMMAND:
            request['options'] = page_generation_specification(spec)
        if operation == PAGE_BACKGROUND_EDIT_COMMAND:
            request['options'] = page_background_specification(spec)
        if operation == PAGE_DESCRIPTION_EDIT_COMMAND:
            request['options'] = page_description_specification(spec)
        if operation in (DATA_REFERENCE_READ_COMMAND, *REFERENCE_RENAME_COMMANDS):
            request['options'] = reference_specification(spec, operation)
        if operation in CONTROL_REFERENCE_COMMANDS:
            request['options'] = control_reference_specification(spec, editing=operation == CONTROL_RENAME_COMMAND)
        if operation in SERIAL_COMMANDS:
            request['options'] = serial_specification(spec, editing=operation == SERIAL_EDIT_COMMAND)
        if operation in RECIPE_REFERENCE_COMMANDS:
            request['options'] = recipe_reference_specification(spec, editing=operation == RECIPE_RENAME_COMMAND)
        if operation in (DATA_READ_COMMAND, DATA_EDIT_COMMAND) or operation == DATA_CATALOG_COMMAND and spec is not None:
            request['options'] = data_specification(spec, operation)
        if operation in (RECIPE_READ_COMMAND, RECIPE_CELL_COMMAND):
            request['options'] = recipe_specification(spec, editing=operation == RECIPE_CELL_COMMAND)
        if operation in (STRATEGY_READ_COMMAND, STRATEGY_EDIT_COMMAND):
            request['options'] = strategy_specification(spec, editing=operation == STRATEGY_EDIT_COMMAND)
        if operation == TRIGGER_READ_COMMAND:
            request['options'] = trigger_specification(spec)
        if operation in LANGUAGE_WRITES or operation == LANGUAGE_CATALOG_COMMAND and spec is not None:
            request['options'] = language_specification(spec, operation)
        if operation in (*PICTURE_WRITES, PICTURE_EXPORT_COMMAND) or operation == PICTURE_CATALOG_COMMAND and spec is not None:
            request['options'] = picture_specification(spec, operation)
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
        if requested == GEOMETRY_COMMAND and (
                not geometry_changes_match(result, request['options']['changes'])
                or result.get('status') != 'no_changes' and not exact_page(result.get('page_view'), request['options'])):
            mismatches.append('geometry_changes')
        if requested in PAGE_CREATION_COMMANDS and not created_page_matches(result, requested, request['options']):
            mismatches.append('created_page')
        if requested == PAGE_GENERATE_COMMAND and not page_generation_matches(result, request['options']):
            mismatches.append('generated_page')
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
        if requested in TRIGGER_COMMANDS and result.get('all_requested_features_available') is True and not trigger_receipt_matches(
                result, requested, request.get('options')):
            mismatches.append('strategy_trigger')
        if requested in LANGUAGE_COMMANDS and not language_receipt_matches(result, requested, request.get('options', {})):
            mismatches.append('language_state')
        if requested in PICTURE_COMMANDS and not picture_receipt_matches(result, requested, request.get('options', {})):
            mismatches.append('picture_state')
        if requested == PICTURE_EXPORT_COMMAND and not mismatches:
            try:
                destination = Path(result['destination_file'])
                with destination.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != result['file_sha256'] or destination.stat().st_size != result['file_bytes']:
                    mismatches.append('picture_export_file')
            except OSError:
                mismatches.append('picture_export_file')
        if requested == PAGE_PROPERTIES_READ_COMMAND and not page_display_matches(result.get('page_properties'), request['options']):
            mismatches.append('page_properties')
        if requested == PAGE_BACKGROUND_EDIT_COMMAND and not page_background_matches(result, request['options']):
            mismatches.append('page_background')
        if requested in PAGE_DESCRIPTION_COMMANDS and not page_description_matches(
                result, requested == PAGE_DESCRIPTION_EDIT_COMMAND, request['options']):
            mismatches.append('page_description')
        if requested in REFERENCE_COMMANDS and not reference_receipt_matches(result, requested, request['options']):
            mismatches.append('registered_reference')
        if requested in CONTROL_REFERENCE_COMMANDS and not control_reference_matches(result, requested, request['options']):
            mismatches.append('control_reference')
        if requested in SERIAL_COMMANDS and not serial_receipt_matches(result, requested, request['options']):
            mismatches.append('serial_device')
        if requested in RECIPE_REFERENCE_COMMANDS and not recipe_reference_matches(result, requested, request['options']):
            mismatches.append('recipe_reference')
        if requested in VISIBILITY_COMMANDS and not visibility_receipt_matches(
                result, requested == VISIBILITY_EDIT_COMMAND, request['options']):
            mismatches.append('visibility')
        if mismatches:
            failure = {'ok': False, 'status': 'native_receipt_identity_mismatch', 'mismatches': mismatches,
                       'request_id': result.get('request_id'), 'queue_request_sha256': result.get('queue_request_sha256'),
                       'automatic_retry': False}
            if (is_lifecycle or append_check is not None or requested in PAGE_CREATION_COMMANDS
                     or requested in (PAGE_GENERATE_COMMAND, *PICTURE_WRITES, PICTURE_EXPORT_COMMAND, *LANGUAGE_WRITES, *REFERENCE_RENAME_COMMANDS,
                                      GEOMETRY_COMMAND, DATA_EDIT_COMMAND, RECIPE_CELL_COMMAND, STRATEGY_EDIT_COMMAND,
                                      PAGE_BACKGROUND_EDIT_COMMAND, PAGE_DESCRIPTION_EDIT_COMMAND, VISIBILITY_EDIT_COMMAND,
                                      CONTROL_RENAME_COMMAND, SERIAL_EDIT_COMMAND, RECIPE_RENAME_COMMAND)):
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
    if receipt.get('op') == PAGE_GENERATE_COMMAND:
        return 0 if page_generation_matches(receipt) else 2
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
    if receipt.get('op') in PAGE_DESCRIPTION_COMMANDS:
        editing = receipt['op'] == PAGE_DESCRIPTION_EDIT_COMMAND
        if not page_description_matches(receipt, editing):
            return 2
        if not editing:
            return 0 if receipt.get('read_only') is True else 2
        current = receipt['page_description']
        changed = current['description'] != receipt['before']['description']
        view, count = receipt.get('page_view'), receipt.get('completed_count')
        flags = ('view_refresh_verified', 'page_save_verified', 'root_save_verified', 'write_attempted')
        verified = (receipt.get('status') == ('applied_and_saved' if changed else 'no_changes')
                    and receipt.get('read_only') is (not changed)
                    and receipt.get('native_result_may_be_partial') is False
                    and type(count) is int and count == int(changed)
                    and all(receipt.get(flag) is changed for flag in flags)
                    and (not changed or exact_page(view, current) and view.get('exact_page_is_active') is True))
        return 0 if verified else 2
    if receipt.get('op') in CONTROL_REFERENCE_COMMANDS:
        return 0 if control_reference_matches(receipt, receipt['op']) else 2
    if receipt.get('op') in SERIAL_COMMANDS:
        return 0 if serial_receipt_matches(receipt, receipt['op']) else 2
    if receipt.get('op') in RECIPE_REFERENCE_COMMANDS:
        return 0 if recipe_reference_matches(receipt, receipt['op']) else 2
    if receipt.get('op') in REFERENCE_COMMANDS:
        operation = receipt['op']
        if not reference_receipt_matches(receipt, operation):
            return 2
        if operation not in REFERENCE_RENAME_COMMANDS:
            return 0 if receipt.get('read_only') is True else 2
        count = receipt.get('completed_count')
        flags = ('page_save_verified',) if operation == PAGE_RENAME_COMMAND else (
            'data_module_saved', 'project_saved', 'unselected_native_records_verified')
        if operation == PAGE_RENAME_COMMAND and receipt.get('saved_page_ids') != [receipt['page_id']]:
            return 2
        verified = (receipt.get('status') == 'applied_and_saved' and receipt.get('read_only') is False
                    and receipt.get('native_result_may_be_partial') is False and type(count) is int and count == 1
                    and all(receipt.get(flag) is True for flag in (
                        'write_attempted', 'root_save_verified', 'original_active_view_preserved', *flags)))
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
    if receipt.get('op') in TRIGGER_COMMANDS:
        return 0 if trigger_receipt_matches(receipt, receipt['op']) and receipt.get('read_only') is True else 2
    if receipt.get('op') in LANGUAGE_COMMANDS:
        return 0 if language_receipt_matches(receipt, receipt['op']) else 2
    if receipt.get('op') in PICTURE_COMMANDS:
        return 0 if picture_receipt_matches(receipt, receipt['op']) else 2
    if receipt.get('op') in BATCH_COMMANDS:
        flags = ('view_refresh_verified', 'page_save_verified', 'root_save_verified')
        completed = receipt.get('completed_count')
        append_check = APPENDED_CONTROL_CHECKS.get(receipt.get('op'))
        if receipt.get('op') == GEOMETRY_COMMAND:
            if not geometry_changes_match(receipt):
                return 2
            view = receipt.get('page_view')
            changed = completed > 0
            verified = (receipt.get('status') == ('applied_and_saved' if changed else 'no_changes')
                        and receipt.get('read_only') is (not changed)
                        and receipt.get('write_attempted') is changed
                        and receipt.get('native_result_may_be_partial') is False
                        and all(receipt.get(flag) is changed for flag in flags)
                        and (not changed or isinstance(view, dict) and view.get('exact_page_is_active') is True
                             and nonnegative_int32(view.get('page_id')) and valid_page_name(view.get('page'))))
        elif append_check is not None:
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
        if operation == PAGE_GENERATE_COMMAND:
            command.add_argument('--spec', required=True, type=Path, help='Exact current page and top-level control count')
        if operation == PAGE_BACKGROUND_EDIT_COMMAND:
            command.add_argument('--spec', required=True, type=Path, help='Exact page and current/requested background COLORREF')
        if operation == PAGE_DESCRIPTION_EDIT_COMMAND:
            command.add_argument('--spec', required=True, type=Path, help='Exact page and current/requested description')
        if operation in MODULE_SPEC_COMMANDS:
            command.add_argument('--spec', required=operation not in (DATA_CATALOG_COMMAND, LANGUAGE_CATALOG_COMMAND, PICTURE_CATALOG_COMMAND), type=Path,
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
