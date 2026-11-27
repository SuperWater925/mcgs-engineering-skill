"""Native McgsStu and McgsPro editing; software releases are recorded, structural codecs decide support."""
import argparse
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import sys
from collections import defaultdict
from collections.abc import Mapping

import native_format as f
from mcgs_family import identify_family
from mcs_input_text import InputRecord
from mcs_window_archive import ControlRecord, FormatError, WindowSettings
from 窗口事件归档 import (STU_COMMON_WINDOW_LAYERS, WINDOW_DISPATCH_ACTIONS, WINDOW_MOUSE_DOWN_SOURCE, 读取公共窗口槽,
                  改选公共窗口, 读取页面Click, 读取页面MouseDown)
from control_factory import CONTROL_CLICK_TYPES, control_click_event, edit_control_click, make_control, page_events, record
import offline_structure as structure

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
HOME = Path(__file__).resolve().parent.parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pwsh():
    configured = os.environ.get('MCGS_PWSH')
    path = configured or shutil.which('pwsh') or shutil.which('powershell')
    if not path or not Path(path).is_file():
        raise ValueError('A Windows PowerShell worker is required; set MCGS_PWSH to its executable path')
    return Path(path)


def db(request):
    process = subprocess.run([str(pwsh()), '-NoProfile', '-NonInteractive', '-File', str(HOME/'scripts/database.ps1')],
                             input=json.dumps(request, ensure_ascii=True).encode('ascii'),
                             capture_output=True, timeout=120)
    if process.returncode:
        error = process.stderr.decode('utf-8-sig', errors='replace')
        raise RuntimeError('Database operation failed: '+error[:1200])
    return json.loads(process.stdout.decode('utf-8-sig'))


def one(items):
    items=list(items)
    if len(items)!=1:
        raise ValueError(f'Unique object required, found {len(items)}')
    return items[0]


def system(data, name):
    return one(r for r in data['System']['rows'] if r['strName']==name)


def canonical(data):
    return {key: {'fields':[(v['name'],v['type'],v.get('auto_increment',False)) for v in value['fields']],
                  'indexes':sorted((x['name'],x['primary'],x['unique'],tuple(x['columns'])) for x in value.get('indexes',[])),
                  'rows':sorted(json.dumps(r,sort_keys=True,ensure_ascii=True) for r in value['rows'])}
            for key,value in data.items()}


def title(value):
    if not isinstance(value,str) or not value or '\x00' in value:
        raise ValueError('Object names require nonempty text without NUL; actual database fields determine storage capacity')
    return value


def set_variables(data, additions, updates, *, factory=False):
    row=system(data,'ObjData'); rows=f.variables(f.archive(row['lbContext']))
    stu = project_family(data) == 'Stu' if additions else False
    templates=load_factory_asset('primitives', 'Stu' if stu else 'Pro')
    validate_initial = {item['name'] for item in additions}
    validate_initial.update(item['name'] for item in updates if 'initial' in item)
    next_id = max((record['id'] for record in rows), default=-1) + 1 if additions else None
    known_names = {record['name'].casefold() for record in rows}
    for item in additions:
        if set(item)-{'name','type','initial','note','unit'}:
            raise ValueError('Unknown variable property')
        name=title(item['name']);kind=item['type']
        if name.casefold() in known_names or kind not in templates['variables']:
            raise ValueError('Duplicate variable or unsupported type')
        known_names.add(name.casefold())
        template=templates['variables'][kind]
        ident = next_id
        next_id += 1
        if kind == 'group':
            if set(item) != {'name', 'type'}:
                raise ValueError('A default data group accepts only name and type')
            if name.startswith('$'):
                raise ValueError('Native data-group name must be a user name')
            if not stu and len(name.encode('utf-8')) > 64:
                raise ValueError('Pro native data-group name exceeds 64 UTF-8 bytes')
            # This is the saved original default, including its empty member
            # lists. Active groups are never used as creation prototypes.
            rows.append({'id':ident, 'name':name, 'kind':template['kind'],
                         'note':'', 'unit':'', 'initial':template['initial'],
                         'prefix':bytes.fromhex(template['prefix']),
                         'extension':bytes.fromhex(template['extension'])})
            continue
        # Prefer an actual neutral scalar of this class. Compare the known
        # collection/retention configuration with the neutral schema before
        # reusing it; never inherit alarms or group membership accidentally.
        prototype=None
        neutral=bytes.fromhex(template['prefix'])
        _,neutral_middle=f.string(neutral,36)
        for existing in rows:
            if existing['kind']!=template['kind']:continue
            prefix=existing['prefix'];before,middle=f.string(prefix,36)
            extension=existing['extension']
            try:
                after,end=f.string(extension,12)
                clean_extension=extension[:12]==bytes(12) and not after
                if stu:
                    clean_extension = clean_extension and extension[end:] == struct.pack('<III', 0, 2, 0)
            except (ValueError,UnicodeError):clean_extension=False
            if (not before and prefix[4:36]==neutral[4:36] and
                    prefix[middle:middle+28]==neutral[neutral_middle:neutral_middle+28] and clean_extension):
                prototype=existing;break
        if stu and prototype is None and not factory:
            # Adding the first variable of a scalar class is common on a fresh
            # project. Require evidence of the factory tail in another current
            # scalar before selecting that family's neutral prototype.
            tail=bytes.fromhex(template['extension'])
            if not any(r['kind'] in (1,2,3) and r['extension']==tail for r in rows):
                raise ValueError('No matching neutral Stu scalar layout in the source project')
        rows.append({'id':ident,'name':name,'kind':template['kind'],
                     'note':item.get('note',''),'unit':item.get('unit',''),
                     'initial':str(item.get('initial','0')),
                     'prefix':prototype['prefix'] if prototype else bytes.fromhex(template['prefix']),
                     'extension':prototype['extension'] if prototype else bytes.fromhex(template['extension'])})
    for item in updates:
        if set(item)-{'name','initial','note','unit'}:
            raise ValueError('Unknown variable update')
        target=one(r for r in rows if r['name']==item['name'])
        if target['kind'] not in (1,2,3):
            raise ValueError('Only scalar variable properties can be changed')
        for key in ('initial','note','unit'):
            if key in item:target[key]=str(item[key])
    for r in rows:
        if r['name'] in validate_initial and r['kind'] in (1,2):
            try: value=float(r['initial'])
            except ValueError:raise ValueError('Numeric initial value required')
            if not __import__('math').isfinite(value) or (r['kind']==1 and value not in (0,1)):
                raise ValueError('Invalid numeric initial value')
    if additions or updates:
        row['lbContext']=f.wrap_like(row['lbContext'],f.pack_variables(rows))
    return {r['name']:r for r in rows}


class VariableCatalog(Mapping):
    """Read ObjData only when an operation actually resolves a variable."""
    def __init__(self,data):
        self.data=data;self.loaded=None
    def _values(self):
        if self.loaded is None:self.loaded=set_variables(self.data,[],[])
        return self.loaded
    def __getitem__(self,key):return self._values()[key]
    def __iter__(self):return iter(self._values())
    def __len__(self):return len(self._values())


def control(item, variables, primitives, source_pages=()):
    return make_control(item, variables, primitives, source_pages)


def page_columns(data):
    names={field['name'] for field in data['WndUser']['fields']}
    # Native Pro currently uses strNote. Preserve an actual legacy annotation
    # column if supplied; never add a guessed column to the copied schema.
    note='strNote' if 'strNote' in names else ('strComment' if 'strComment' in names else None)
    columns=('iID','strName',note,'lbObjects','iDeleteFlag','iCompileFlag')
    if note is None or any(name not in names for name in columns):
        raise ValueError('Current WndUser schema is missing a native page field')
    return columns


def template_pages(data):
    result = []
    for row in data['WndUser']['rows']:
        _, values, _ = f.window(f.archive(row['lbObjects']),validate_settings=False)
        result.append({'id': row['iID'], 'controls': [record(kind, payload) for kind, payload in values]})
    return result


class SourcePages:
    """Resolve only explicitly requested clone pages from the original snapshot."""
    def __init__(self,rows,family='Pro'):self.rows=rows;self.loaded={};self.family=family
    def __iter__(self):
        for row in self.rows:
            try:yield self.page(row['iID'])
            except (ValueError,UnicodeError,struct.error):continue
    def page(self,ident):
        if ident not in self.loaded:
            row=one(r for r in self.rows if r['iID']==ident)
            _,values,_=f.window(f.archive(row['lbObjects']),validate_settings=False)
            self.loaded[ident]={'id':ident,'controls':[record(kind,payload) for kind,payload in values]}
        return self.loaded[ident]


def root_startup(blob, prefix_size, page_name, page_id):
    pos=prefix_size
    for strings in (True,False,True,False):
        count=struct.unpack_from('<H',blob,pos)[0];pos+=2
        for _ in range(count):
            if strings:_,pos=f.string(blob,pos)
            else:pos+=4
    return (blob[:prefix_size]+struct.pack('<H',1)+f.text(page_name)+struct.pack('<HI',1,page_id)
            +bytes(4)+blob[pos:])


def load_factory_asset(name,family):
    suffix='-stu' if family=='Stu' else ''
    return json.loads((HOME/'assets'/f'{name}{suffix}.json').read_text(encoding='utf-8'))


def page_display_properties(page):
    dimensions = {key: page[key] for key in ('width', 'height') if key in page}
    if any(type(value) is not int or not 1 <= value <= 0x7fffffff for value in dimensions.values()):
        raise ValueError('Page dimensions must be positive native Int32 values')
    if 'background' in page:
        color = page['background']
        if type(color) is not int or not 0 <= color <= 0xffffff:
            raise ValueError('Background requires a native COLORREF integer')
        dimensions['background'] = color
    if 'description' in page:
        description = page['description']
        if not isinstance(description, str) or '\0' in description:
            raise ValueError('Page description requires text without NUL')
        dimensions['description'] = description
    return dimensions


def inherited_page_description(settings, fallback):
    try:
        return settings.field('description').value
    except FormatError:
        return fallback


def create_data(spec,family='Pro',*,pending_event_generation=None):
    if set(spec)-{'variables','variable_arrays','pages','edits'}:raise ValueError('Unknown project property')
    data=load_factory_asset('blank-project',family)
    if project_family(data)!=family:raise ValueError('Factory seed family mismatch')
    presets=load_factory_asset('primitives',family)
    additions=spec.get('variables',[])+structure.expand_variable_arrays(spec.get('variable_arrays',[]))
    variables=set_variables(data,additions,[],factory=True)
    base=data['WndUser']['rows'][0];header,_,trailer=f.window(f.archive(base['lbObjects']))
    note_column=page_columns(data)[2]
    page_settings=WindowSettings.parse(trailer,identity=(base['iID'],base['strName']))
    default_note=inherited_page_description(page_settings,base[note_column])
    pages=[]
    for ident,item in enumerate(spec['pages'],1):
        if set(item)-{'name','controls','events','width','height','background','description'}:raise ValueError('Unknown page property')
        name=title(item['name']);controls=[control(c,variables,presets) for c in item.get('controls',[])]
        if len({f.common(b)['name'] for _,b in controls})!=len(controls):raise ValueError('Duplicate control name')
        row=copy.deepcopy(base);row.update(iID=ident,strName=name,iCompileFlag=0)
        new_trailer=f.page_properties(trailer,ident=ident,name=name,**page_display_properties(item))
        row[note_column]=item.get('description',default_note)
        new_trailer=page_events(new_trailer,item.get('events',{}),fresh=True,family=family)
        record_pending_window_dispatch(pending_event_generation, ident, name, new_trailer, item.get('events', {}), family)
        row['lbObjects']=f.wrap_like(base['lbObjects'],f.pack_window(header,controls,new_trailer))
        pages.append(row)
    if not pages or len({r['strName'] for r in pages})!=len(pages):raise ValueError('Unique nonempty page list required')
    data['WndUser']['rows']=pages
    root=data['WndControl']['rows'][0]
    root['lbObjects']=f.wrap_like(root['lbObjects'],root_startup(f.archive(root['lbObjects']),presets['root_prefix_size'],pages[0]['strName'],1))
    if 'edits' in spec:
        edits=spec['edits']
        if not isinstance(edits,dict) or 'source_sha256' in edits:
            raise ValueError('Initial edits require an edit specification without source_sha256')
        if 'delete_data_groups' in edits:
            raise ValueError('Data group deletion requires an existing source project')
        return edit_data(data,edits,pending_event_generation=pending_event_generation)
    return data


def inspect_controls(records):
    from control_factory import GroupArchive
    from animation_edits import CLICK_PAGE_CONTROL_TYPES, inspect_items
    from 原生界面样式 import CommonEnvelope
    from 原生趋势样式 import HISTORY_CURVE_TYPE, history_curve_configuration, history_curve_pens
    from 当前存盘浏览样式 import SAVED_DATA_TYPE, saved_data_style

    controls=[]
    for index,(kind,b) in enumerate(records):
        c={'index':index,'kind':hex(kind),'sha256':hashlib.sha256(b).hexdigest()}
        try:
            props=f.common(b);c.update(name=props['name'],bounds=props['bounds'])
            if kind==0x5008 and f.u32(b,props['name_end'])==12:
                c['text']=f.string(b,props['name_end']+14)[0]
            if kind in CONTROL_CLICK_TYPES:
                try:
                    _, _, event = control_click_event(record(kind, b))
                    c['click_event_source'] = {**event.click_identity(), 'source': event.source.value,
                                               'compiled_size': len(event.compiled.value)}
                except (ValueError, UnicodeError, struct.error):
                    pass
            if kind in CLICK_PAGE_CONTROL_TYPES and b'CAniClick' in b:
                try:
                    pages = [{key: item[key] for key in ('index', 'sha256', 'page_target')}
                             for item in inspect_items(CommonEnvelope.parse(record(kind, b))) if 'page_target' in item]
                    if pages:
                        c['click_animation_pages'] = pages
                except (ValueError, UnicodeError, struct.error):
                    pass
            if kind == HISTORY_CURVE_TYPE:
                try:
                    pens = history_curve_pens(record(kind,b))
                    c['history_curve_pens'] = pens
                    c['history_curve_colors'] = [{'trace_index': pen['trace_index'], 'color': pen['color']} for pen in pens]
                    c.update(history_curve_configuration(record(kind, b)))
                except (ValueError, UnicodeError, struct.error) as error:
                    c['history_curve_colors_unavailable'] = str(error)
                    c['history_curve_pens_unavailable'] = str(error)
            if kind == SAVED_DATA_TYPE:
                try:
                    c.update(saved_data_style(record(kind,b)))
                except (ValueError, UnicodeError, struct.error) as error:
                    c['row_height_unavailable'] = str(error)
            if kind==0x503a:
                group=GroupArchive.parse(record(kind,b))
                if group.to_record().payload!=b:raise ValueError('Native group does not round-trip')
                c['children']=inspect_controls((child.type_id,child.payload) for child in group.children)
        except (ValueError,UnicodeError,struct.error):c['properties']='opaque'
        controls.append(c)
    return controls


def inspect_data(data):
    result={'version':project_version(data),
            'variables':[], 'pages':[]}
    family = None
    try:
        family=project_family(data)
        prefix=load_factory_asset('primitives',family)['root_prefix_size']
        result['main_page_lists']=structure.main_page_lists(data,prefix)
    except (ValueError, struct.error) as error:
        result['main_page_lists_unavailable']=str(error)
    variables=f.variables(f.archive(system(data,'ObjData')['lbContext']))
    for row in variables:
        result['variables'].append({k:row[k] for k in ('id','name','kind','initial','note','unit')})
    storage_template = (load_factory_asset('primitives', family)['variables']['group']
                        if family and result['version'] in structure.HISTORY_STORAGE_PROFILES else None)
    result['data_groups']=structure.inspect_data_groups(variables, storage_template=storage_template, version=result['version'])
    from offline_alarm import inspect_alarm_definitions, inspect_alarm_storage
    try:
        result['alarm_storage']=inspect_alarm_storage(data,variables)
    except ValueError as error:
        result['alarm_storage_unavailable']=str(error)
    try:
        result['alarm_definitions']=inspect_alarm_definitions(data,variables)
    except ValueError as error:
        result['alarm_definitions_unavailable']=str(error)
    page_names={row['iID']:row['strName'] for row in data['WndUser']['rows']}
    for row in data['WndUser']['rows']:
        _,records,trailer=f.window(f.archive(row['lbObjects']))
        page={'id':row['iID'],'name':row['strName'],'controls':inspect_controls(records)}
        settings=WindowSettings.parse(trailer,identity=(row['iID'],row['strName']))
        try:
            page['description']=settings.field('description').value
            page['description_mirror_matches']=row[page_columns(data)[2]]==page['description']
        except (ValueError, struct.error) as error:
            page['description_unavailable']=str(error)
        try:
            slots=读取公共窗口槽(settings.event_tail)
            references=[None if ident==-1 else {'id':ident,'name':page_names.get(ident)} for ident in slots]
            page['common_page']=references[0]
            if family=='Stu' and len(slots)==len(STU_COMMON_WINDOW_LAYERS):
                page['common_page_layers']=dict(zip(STU_COMMON_WINDOW_LAYERS,references,strict=True))
        except (ValueError, struct.error) as error:
            page['common_page_unavailable']=str(error)
        try:
            click = 读取页面Click(settings.event_tail)
            page['click_event_source'] = {**click.click_identity(), 'source': click.source.value,
                                         'compiled_size': len(click.compiled.value)}
        except (ValueError, struct.error):
            pass
        try:
            mouse_down, bindings = 读取页面MouseDown(settings.event_tail, family=family)
            page[WINDOW_MOUSE_DOWN_SOURCE] = {**mouse_down.identity(), 'source': mouse_down.source.value,
                                               'compiled_size': len(mouse_down.compiled.value),
                                               'parameter_bindings': bindings}
        except (ValueError, struct.error):
            pass
        result['pages'].append(page)
    return result


def validate_common_page_target(data, host, target):
    """Follow every archived slot reachable from the proposed new edge."""
    if target == -1:
        return
    pages = defaultdict(list)
    for row in data['WndUser']['rows']:
        if not row['iDeleteFlag']:
            pages[row['iID']].append(row)
    active, visited = {host}, set()
    stack = [(target, False)]
    while stack:
        ident, complete = stack.pop()
        if complete:
            active.remove(ident)
            visited.add(ident)
            continue
        if ident in active:
            raise ValueError(f'Public window change would introduce or use a reference cycle at page ID {ident}')
        if ident == -1 or ident in visited:
            continue
        matches = pages.get(ident, ())
        if len(matches) != 1:
            raise ValueError(f'Public-window chain references missing or ambiguous current page ID {ident}')
        row = matches[0]
        try:
            _, _, trailer = f.window(f.archive(row['lbObjects']), validate_settings=False)
            settings = WindowSettings.parse(trailer, identity=(ident, row['strName']))
            settings.field('id')
            if settings.to_bytes() != trailer:
                raise ValueError('Public-window target settings do not round-trip')
            slots = 读取公共窗口槽(settings.event_tail)
        except (ValueError, struct.error) as error:
            raise ValueError('Cannot read the public-window target chain for '+row['strName']) from error
        active.add(ident)
        stack.append((ident, True))
        stack.extend((ref, False) for ref in reversed(slots))


def change_common_page(data, owner, trailer, change, family):
    fields = ('owner_name','source','target')
    layered = isinstance(change, dict) and 'layer' in change
    structure.exact(change, fields+('layer',) if layered else fields, 'Public window change')
    layer = change.get('layer')
    if layered and (family!='Stu' or layer not in STU_COMMON_WINDOW_LAYERS):
        raise ValueError('Explicit public-window layers require Stu and bottom, middle or top')
    if owner['iDeleteFlag'] or change['owner_name'] != owner['strName']:
        raise ValueError('Public window host ID/name differs from the current page')
    references = {}
    for key in ('source', 'target'):
        item = change[key]
        if item is None:
            references[key] = -1
            continue
        structure.exact(item, ('id','name'), 'Public window identity')
        if type(item['id']) is not int or not 0 < item['id'] <= 0x7fffffff:
            raise ValueError('Invalid public-window page ID')
        references[key] = structure._page(data,item)['iID']
    source, target = references['source'], references['target']
    settings = WindowSettings.parse(trailer, identity=(owner['iID'], owner['strName']))
    settings.field('id')
    if settings.to_bytes()!=trailer:
        raise ValueError('Public-window host settings do not round-trip')
    before = settings.event_tail
    settings.event_tail = 改选公共窗口(before, source, target, 层级=layer)
    if settings.event_tail == before:
        return trailer
    validate_common_page_target(data, owner['iID'], target)
    return settings.to_bytes()


def record_pending_window_dispatch(pending, page_id, page_name, trailer, changes, family):
    if pending is None:
        return
    actions = changes.keys() & WINDOW_DISPATCH_ACTIONS
    if not actions:
        return
    operation, = actions
    if operation == 'delete_click_event':
        identity = changes[operation]
    else:
        settings = WindowSettings.parse(trailer, identity=(page_id,page_name))
        event = (读取页面MouseDown(settings.event_tail, family=family)[0] if operation == WINDOW_MOUSE_DOWN_SOURCE else
                 读取页面Click(settings.event_tail))
        if event.compiled.value:
            return
        identity = event.identity()
    pending.append({'page_id': page_id, 'page_name': page_name, 'owner': 'window', 'operation': operation,
                    'event_type_id': identity['event_type_id'], 'event_id': identity['event_id'],
                    'event_name': identity['name'],
                    'required_action': 'page-native-generate' if family == 'Stu' else 'reference-sync'})


def record_pending_control_click(receipt, page, change, kind, payload, family):
    if receipt is None or 'click_event_source' not in change['edits']:
        return
    _, _, event = control_click_event(record(kind, payload))
    if not event.compiled.value:
        pending = {'page_id': page['iID'], 'control_name': change['name'],
                   'event_type_id': event.event_id, 'event_id': event.kind,
                   'event_name': event.event_name.value,
                   'required_action': 'reference-sync' if family == 'Pro' else 'compile'}
        if 'path' in change:
            pending['control_path'] = change['path']
        receipt.append(pending)


def edit_control_path(records, change, edit):
    from control_patch import at_path, replace_path
    from 原生界面样式 import CommonEnvelope

    path = change['path']
    if (not isinstance(path, list) or not path or any(type(index) is not int or index < 0 for index in path)
            or path[0] >= len(records)):
        raise ValueError('Control path requires valid sibling indexes')
    root = record(*records[path[0]])
    siblings = [root]
    local_path = [0, *path[1:]]
    original = at_path(siblings, local_path)
    if (hashlib.sha256(original.payload).hexdigest() != change['sha256']
            or CommonEnvelope.parse(original).name.value != change['name']):
        raise ValueError('Control path/name/SHA preimage mismatch')
    changed = edit(original)
    replace_path(siblings, local_path, changed)
    updated = siblings[0]
    if at_path(siblings, local_path).payload != changed.payload:
        raise ValueError('Changed control did not round-trip through its group path')
    replace_path(siblings, local_path, original)
    if siblings[0].payload != root.payload:
        raise ValueError('Control path edit changed another native field')
    records[path[0]] = updated.type_id, updated.payload
    return changed


def validate_click_animation_page(rows, selector):
    if (not isinstance(selector, dict) or selector.keys() != {'id', 'name'}
            or type(selector['id']) is not int or not 0 < selector['id'] <= 0x7fffffff
            or not isinstance(selector['name'], str) or not selector['name'] or '\0' in selector['name']):
        raise ValueError('Click animation page requires a current native ID and exact name')
    match = [row for row in rows if row['iID'] == selector['id']
             or row['strName'].casefold() == selector['name'].casefold()]
    if (len(match) != 1 or (match[0]['iID'], match[0]['strName'], match[0]['iDeleteFlag'])
            != (selector['id'], selector['name'], 0)):
        raise ValueError('Click animation page ID/name does not uniquely match an active window')
    _, _, trailer = f.window(f.archive(match[0]['lbObjects']))
    settings = WindowSettings.parse(trailer, identity=(selector['id'], selector['name']))
    if (settings.field('id').value, settings.field('name').value) != (selector['id'], selector['name']):
        raise ValueError('Click animation page settings identity differs')


def edit_data(data,spec,*,pending_event_generation=None):
    if set(spec)-{'source_sha256','add_variables','variable_arrays','variables','delete_variables','rename_variables','data_group_orders','data_group_members','data_group_storage','data_group_archive_settings','delete_data_groups','retarget_main_pages','main_page_lists','pages','add_pages','rename_pages','delete_pages','picture_library','recipe_edits','strategy_edits','alarm_edits'}:raise ValueError('Unknown edit property')
    group_deletions=structure.data_group_deletions(spec) if 'delete_data_groups' in spec else []
    originals=copy.deepcopy(data['WndUser']['rows']); source_pages=SourcePages(originals, project_family(data))
    additions=spec.get('add_variables',[])+structure.expand_variable_arrays(spec.get('variable_arrays',[]))
    variables=(set_variables(data,additions,spec.get('variables',[]))
               if additions or spec.get('variables') else VariableCatalog(data))
    primitives=load_factory_asset('primitives',source_pages.family)
    from picture_resources import uses_picture_reference
    picture_references = None
    for page in spec.get('pages',[]):
        if set(page)-{'id','controls','add_controls','events','remove_controls','control_order','groups','group_operations','width','height','background','description','common_page'}:raise ValueError('Unknown page edit')
        row=one(r for r in data['WndUser']['rows'] if r['iID']==page['id'])
        original_window=f.archive(row['lbObjects'])
        header,records,trailer=f.window(original_window,validate_settings='events' in page)
        if dimensions := page_display_properties(page):
            trailer=f.page_properties(trailer, identity=(row['iID'], row['strName']), **dimensions)
        if 'description' in page:row[page_columns(data)[2]]=page['description']
        common_page_changed=False
        if 'common_page' in page:
            if type(page['id']) is not int:raise ValueError('Invalid public-window host page ID')
            updated_trailer=change_common_page(data,row,trailer,page['common_page'],source_pages.family)
            common_page_changed=updated_trailer!=trailer
            trailer=updated_trailer
        removals=page.get('remove_controls',[])
        if removals:
            removed={structure.control_index(records, value) for value in removals}
            surviving=[record for index,record in enumerate(records) if index not in removed]
            # Exclude only the deleted control's own source, never other pages
            # or events on this page.
            settings=WindowSettings.parse(trailer,identity=(row['iID'],row['strName']))
            for index in removed:
                kind, payload = records[index]
                for name in structure.control_names(kind,payload):
                    external = name if kind == 0x503a else row['strName']+'.'+name
                    structure.require_unreferenced(data,external,excluded_page=row['iID'])
                    if structure.occurrences(settings.event_tail,name) or any(structure.occurrences(raw,name) for _,raw in surviving):
                        raise ValueError('Another control or event on the page references '+name)
        if removals or 'control_order' in page:
            records=structure.arrange_controls(records,removals,page.get('control_order'))
        for change in page.get('controls',[]):
            if set(change) == {'name', 'sha256', 'edits', 'path'}:
                edits = change['edits']
                if not isinstance(edits, dict):
                    raise ValueError('Control path requires a dedicated native Click edit')
                if edits.keys() == {'click_event_source'}:
                    changed = edit_control_path(records, change, lambda original: edit_control_click(original, edits['click_event_source']))
                    record_pending_control_click(pending_event_generation, row, change, changed.type_id,
                                                 changed.payload, source_pages.family)
                elif edits.keys() == {'click_animation_page'}:
                    from animation_edits import retarget_click_animation
                    action = edits['click_animation_page']
                    if not isinstance(action, dict) or action.keys() != {'index', 'sha256', 'source', 'target'}:
                        raise ValueError('Click animation page requires index, sha256, source and target')
                    for key in ('source', 'target'):
                        validate_click_animation_page(data['WndUser']['rows'], action[key])
                    edit_control_path(records, change, lambda original: retarget_click_animation(original, **action))
                else:
                    raise ValueError('Control path requires a dedicated native Click edit')
                continue
            if set(change)!={'name','sha256','edits'}:raise ValueError('Name, sha256 and edits required')
            hits=[]
            for index,(kind,b) in enumerate(records):
                try:
                    if f.common(b)['name']==change['name']:hits.append(index)
                except (ValueError,UnicodeError,struct.error):pass
            index=one(hits);kind,b=records[index]
            if hashlib.sha256(b).hexdigest()!=change['sha256']:raise ValueError('Control preimage mismatch')
            edits=dict(change['edits'])
            if 'name' in edits:title(edits['name'])
            if picture_references is None and uses_picture_reference(edits):
                from offline_picture_library import library
                _, names, _ = library(data['System']['rows'])
                picture_references = {name.value for name in names}
            changed=f.edit_control(kind,b,edits,variables,picture_references=picture_references)
            record_pending_control_click(pending_event_generation, row, change, kind, changed, source_pages.family)
            if 'name' in edits and edits['name'] != change['name']:
                old = change['name']
                structure.require_unreferenced(data, row['strName']+'.'+old, excluded_page=row['iID'])
                settings = WindowSettings.parse(trailer, identity=(row['iID'], row['strName']))
                others = [raw for i, (_, raw) in enumerate(records) if i != index]
                # Scan the renamed object too, after removing its own identity.
                checked = f.edit_control(kind,changed,{'name':'_' if old != '_' else 'X'},variables)
                if any(structure.occurrences(raw, old) for raw in [settings.event_tail, checked, *others]):
                    raise ValueError('A control or event on '+row['strName']+' references '+old)
            records[index]=(kind,changed)
        for addition in page.get('add_controls',[]):
            payload=dict(addition)
            index=payload.pop('insert_at',len(records))
            if type(index)is not int or not 0<=index<=len(records):
                raise ValueError('insert_at must be a valid current sibling index')
            records.insert(index,control(payload,variables,primitives,source_pages))
        for group in page.get('groups', []):
            if set(group) - {'path','remove_controls','control_order','add_controls'}:
                raise ValueError('Unknown group operation')
            removed_names = []
            def change_children(children):
                removals = group.get('remove_controls', [])
                for selector in removals:
                    removed_names.extend(structure.control_names(*children[structure.control_index(children,selector)]))
                updated = structure.arrange_controls(children, removals, group.get('control_order'))
                for item in group.get('add_controls', []):
                    payload = dict(item)
                    at = payload.pop('insert_at', len(updated))
                    if type(at) is not int or not 0 <= at <= len(updated):
                        raise ValueError('Invalid group insertion index')
                    added = control(payload,variables,primitives,source_pages)
                    added_name = f.common(added[1])['name'].casefold()
                    if any(f.common(raw)['name'].casefold() == added_name for _,raw in updated):
                        raise ValueError('Duplicate group child name')
                    updated.insert(at, added)
                return updated
            records = structure.group_siblings(records, group['path'], change_children)
            if removed_names:
                settings = WindowSettings.parse(trailer, identity=(row['iID'],row['strName']))
                for name in removed_names:
                    structure.require_unreferenced(data,name,excluded_page=row['iID'])
                    if any(structure.occurrences(raw,name) for raw in [settings.event_tail, *(b for _,b in records)]):
                        raise ValueError('Surviving page object references group child '+name)
        for operation in page.get('group_operations', []):
            if operation.get('action') == 'move':
                from offline_group_moves import move_between_groups
                updated, selected = move_between_groups(records, operation)
                settings = WindowSettings.parse(trailer, identity=(row['iID'], row['strName']))
                source_root = operation['source'][0]['index']
                candidates = [settings.event_tail, structure.without_control_names(*records[source_root])]
                candidates.extend(body for index, (_,body) in enumerate(records) if index != source_root)
                for name in structure.control_names(*selected):
                    structure.require_unreferenced(data, name, excluded_page=row['iID'])
                    if any(structure.occurrences(raw,name) for raw in candidates):
                        raise ValueError('Moving changes a referenced object path: '+name)
                records = updated
                continue
            if operation.get('action') == 'group':
                title(operation['name'])
            updated = structure.regroup(records, operation, source_pages.family)
            affected = (operation['members'] if operation['action'] == 'group' else [operation['member']])
            settings = WindowSettings.parse(trailer, identity=(row['iID'], row['strName']))
            for member in affected:
                selected = records[member['index']]
                candidates = [settings.event_tail, structure.without_control_names(*selected)]
                candidates.extend(body for index, (_, body) in enumerate(records) if index != member['index'])
                for name in structure.control_names(*selected):
                    structure.require_unreferenced(data, name, excluded_page=row['iID'])
                    if any(structure.occurrences(raw,name) for raw in candidates):
                        raise ValueError('Grouping changes a referenced object path: '+name)
            records = updated
        names=[]
        for _,b in records:
            try:names.append(f.common(b)['name'])
            except (ValueError,UnicodeError,struct.error):pass
        if len(set(names))!=len(names):raise ValueError('Duplicate control name')
        if 'events' in page:
            events = page['events']
            editing_mouse_down = isinstance(events, dict) and WINDOW_MOUSE_DOWN_SOURCE in events
            if (row['iDeleteFlag'] and (editing_mouse_down or
                    source_pages.family == 'Stu' and isinstance(events, dict) and events.keys() & WINDOW_DISPATCH_ACTIONS)):
                raise ValueError('Window dispatch requires an active page')
            if editing_mouse_down:
                settings = WindowSettings.parse(trailer, identity=(row['iID'], row['strName']))
                if (settings.field('id').value, settings.field('name').value) != settings.identity:
                    raise ValueError('MouseDown window settings do not match the active page')
                _, bindings = 读取页面MouseDown(settings.event_tail, family=source_pages.family)
                bound = bindings[0]
                target = variables.get(bound['name'])
                if not target or (target['id'], target['kind']) != (bound['id'], bound['native_type_word']):
                    raise ValueError('MouseDown first parameter differs from the named number variable')
            trailer=page_events(trailer,events,family=source_pages.family)
            record_pending_window_dispatch(pending_event_generation, row['iID'], row['strName'], trailer, events,
                                           source_pages.family)
        updated_window=f.pack_window(header,records,trailer,validate_settings='events' in page)
        if updated_window!=original_window:row['lbObjects']=f.wrap_like(row['lbObjects'],updated_window)
        if common_page_changed or set(page)-{'id','description','common_page'} or set(page)=={'id'}:
            row['iCompileFlag']=0
    ids={r['iID'] for r in data['WndUser']['rows']};names={r['strName'].casefold() for r in data['WndUser']['rows']}
    for page in spec.get('add_pages',[]):
        if set(page)-{'id','name','template_page_id','controls','events','width','height','background','description'}:raise ValueError('Unknown new page property')
        if 'template_page_id' not in page:raise ValueError('New page needs explicit template_page_id')
        template=one(r for r in originals if r['iID']==page['template_page_id'])
        ident=page.get('id',max(ids,default=0)+1);name=title(page['name'])
        if type(ident)is not int or not 0<ident<=2147483647 or ident in ids or name.casefold() in names:raise ValueError('New page ID/name is invalid or repeated')
        header,_,trailer=f.window(f.archive(template['lbObjects']))
        settings=WindowSettings.parse(trailer,identity=(template['iID'],template['strName'])).clone(ident,name)
        events=page.get('events',{})
        trailer=page_events(f.page_properties(settings.to_bytes(), **page_display_properties(page)),events,fresh=True,
                            family=source_pages.family)
        record_pending_window_dispatch(pending_event_generation, ident, name, trailer, events, source_pages.family)
        records=[control(c,variables,primitives,source_pages) for c in page.get('controls',[])]
        if len({f.common(b)['name'] for _,b in records})!=len(records):raise ValueError('Duplicate new page control name')
        row=copy.deepcopy(template);row.update(iID=ident,strName=name,iCompileFlag=0,iDeleteFlag=0)
        note_column=page_columns(data)[2]
        row[note_column]=page.get('description',inherited_page_description(settings,template[note_column]))
        row['lbObjects']=f.wrap_like(template['lbObjects'],f.pack_window(header,records,trailer))
        data['WndUser']['rows'].append(row);ids.add(ident);names.add(name.casefold())
    if 'main_page_lists' in spec:
        structure.replace_main_page_lists(data,spec['main_page_lists'],primitives['root_prefix_size'])
    structure.retarget_main_pages(data,spec.get('retarget_main_pages',[]),primitives['root_prefix_size'])
    structure.rename_pages(data,spec.get('rename_pages',[]),primitives['root_prefix_size'])
    structure.remove_pages(data,spec.get('delete_pages',[]),primitives['root_prefix_size'])
    if spec.get('picture_library'):
        from offline_picture_library import edit_picture_library
        edit_picture_library(data,spec['picture_library'])
    if spec.get('recipe_edits') or spec.get('strategy_edits'):
        from offline_program_recipe import apply_program_recipe
        apply_program_recipe(data,spec)
    structure.remove_variables(data,spec.get('delete_variables',[]),spec.get('rename_variables',[]))
    if 'alarm_edits' in spec:
        from offline_alarm import edit_alarm_definitions
        edit_alarm_definitions(data,spec['alarm_edits'])
    if 'data_group_members' in spec:
        structure.replace_data_group_members(data,spec['data_group_members'],primitives['variables']['group'],source_pages.family)
    if 'data_group_orders' in spec:
        structure.reorder_data_groups(data,spec['data_group_orders'])
    if 'data_group_storage' in spec:
        structure.edit_history_storage(data,spec['data_group_storage'],primitives['variables']['group'],project_version(data))
    if 'data_group_archive_settings' in spec:
        structure.edit_history_archive_settings(data,spec['data_group_archive_settings'],primitives['variables']['group'],project_version(data))
    if group_deletions:
        structure.delete_default_data_groups(data,group_deletions,primitives['variables']['group'])
    return data


def read(path):
    return db({'action':'read','path':str(Path(path).resolve())})


def ensure_output(path,suffix):
    path=Path(path).absolute()
    if path.suffix.lower()!=suffix or path.exists() or not path.parent.is_dir():
        raise ValueError('New '+suffix+' output in an existing directory required')
    for parent in (path,*path.parents):
        if parent.is_symlink() or (parent.exists() and getattr(parent.stat(),'st_file_attributes',0)&1024):
            raise ValueError('Linked output rejected')
    return path


def project_version(data):
    return f.archive(system(data,'MCGSVER')['lbContext']).decode('utf-16le').rstrip('\x00')


def project_family(data):
    family=identify_family(project_version(data))
    if family not in ('Stu','Pro'):raise ValueError('Unrecognized native project family')
    return family


def write_project(output,spec,source=None,*,batch_plan=None):
    if batch_plan is not None and source is None:
        raise ValueError('A bounded batch plan requires an existing project')
    suffix=Path(output).suffix.lower()
    if suffix not in ('.mcp','.mcs'):
        raise ValueError('Expected a new native .mcs or .mcp output')
    output=ensure_output(output,suffix)
    with tempfile.TemporaryDirectory(prefix='.mcgs-create-',dir=output.parent) as workspace:
        candidate=Path(workspace)/output.name
        options={'batch_plan':batch_plan} if batch_plan is not None else {}
        result=_build_candidate(candidate,spec,source,**options)
        # Windows rename refuses a concurrently created destination.
        if os.name=='nt':
            candidate.rename(output)
        else:
            os.link(candidate,output)
        result['output']=str(output)
        return result


def _build_candidate(output,spec,source,*,batch_plan=None):
    batch_result=None
    pending_event_generation=[]
    if source:
        source=Path(source).resolve()
        before_sha=sha(source)
        if before_sha!=spec.get('source_sha256'):raise ValueError('Source SHA256 mismatch')
        before=read(source)
        family=project_family(before)
        if output.suffix.lower()!={'Stu':'.mcs','Pro':'.mcp'}[family]:
            raise ValueError('Output extension differs from the source project family')
        after=copy.deepcopy(before)
        if batch_plan is not None:
            scripts=Path(__file__).resolve().parents[3]/'scripts'
            if str(scripts) not in sys.path:sys.path.insert(0,str(scripts))
            from native_tool import apply_project_batch
            batch_result=apply_project_batch(after,before_sha,family,batch_plan)
        after=edit_data(after,spec,pending_event_generation=pending_event_generation)
        if sha(source)!=before_sha:raise ValueError('Source changed while planning')
        with source.open('rb') as src,output.open('xb') as dst:shutil.copyfileobj(src,dst)
        if sha(output)!=before_sha:raise ValueError('Copied source differs before transaction')
        changes=[]
        removals=[]
        picture_renumbers=[]
        trigger_kinds={2:'loop',3:'user',4:'event'}
        new_page_templates={}
        existing_ids={r['iID'] for r in before['WndUser']['rows']}
        next_id=max(existing_ids,default=0)+1
        for page in spec.get('add_pages',[]):
            ident=page.get('id',next_id);new_page_templates[ident]=page['template_page_id']
            existing_ids.add(ident);next_id=max(existing_ids)+1
        for table,new in after.items():
            key={'System':'iID','WndUser':'iID','WndControl':'iID','Stgy':'iStgyID','Trigger':'iID'}.get(table)
            old_rows={row[key]:row for row in before[table]['rows']} if key else None
            if not key:
                if canonical({table:before[table]})!=canonical({table:new}):raise ValueError('Unexpected table modification')
                continue
            remaining={row[key] for row in new['rows']}
            for ident,old in old_rows.items():
                if ident in remaining:continue
                if table=='WndUser':
                    operation='delete-page'
                elif table=='System' and (old['strName'].startswith('MCGS_PICTURE_DATA_') or old['strName'].startswith('MCGS_RECIPE_') and old['strName']!='MCGS_RECIPE_DATA'):
                    operation='delete-library-row'
                elif table=='Trigger' and spec.get('strategy_edits') and old['lType'] in trigger_kinds:
                    operation=f"delete-{trigger_kinds[old['lType']]}-trigger"
                    removals.append({'action':operation,'table':table,'id':ident,'name':old['strNote'],
                                     'lStgyID':old['lStgyID'],'lType':old['lType']})
                    continue
                else:raise ValueError('Unexpected deleted '+table+' row')
                removals.append({'action':operation,'table':table,'id':ident,'name':old['strName']})
            for row in new['rows']:
                old=old_rows.get(row[key])
                if old is None:
                    if table=='WndUser' and row[key] in new_page_templates:
                        columns=page_columns(before)
                        changes.append({'action':'insert-page','table':'WndUser','template_key':new_page_templates[row[key]],'values':{name:row[name] for name in columns}})
                    elif table=='System' and (row['strName'] in ('MCGS_PICTURE_LIST','MCGS_PICTURE_MANAGER_INFO') or row['strName'].startswith(('MCGS_PICTURE_DATA_','MCGS_RECIPE_')) and row['strName']!='MCGS_RECIPE_DATA'):
                        changes.append({'action':'insert-library-row','table':'System','values':row})
                    elif table=='Trigger' and spec.get('strategy_edits') and row['lType'] in trigger_kinds:
                        operation=f"insert-{trigger_kinds[row['lType']]}-trigger"
                        changes.append({'action':operation,'table':'Trigger','values':row})
                    else:raise ValueError('Unexpected new '+table+' row')
                    continue
                values={k:v for k,v in row.items() if v!=old[k]}
                if table=='System' and 'strName' in values:
                    if spec.get('picture_library') and set(values) <= {'strName','lbContext'}:
                        old_slot = re.fullmatch(r'MCGS_PICTURE_DATA_(0|[1-9][0-9]*)',old['strName'])
                        new_slot = re.fullmatch(r'MCGS_PICTURE_DATA_(0|[1-9][0-9]*)',row['strName'])
                        if old_slot and new_slot and int(new_slot[1]) < int(old_slot[1]):
                            picture_renumbers.append((int(old_slot[1]), {
                                'action':'renumber-picture-row','table':table,'id':row[key],
                                'name':old['strName'],'values':{'strName':row['strName']}}))
                            if 'lbContext' in values:
                                changes.append({'action':'update','table':table,'key':key,'id':row[key],
                                                'values':{'lbContext':values['lbContext']}})
                            continue
                    if (not spec.get('recipe_edits') or set(values)-{'strName','lbContext'} or
                            not all(name.startswith('MCGS_RECIPE_') and name!='MCGS_RECIPE_DATA'
                                    for name in (old['strName'],row['strName']))):
                        raise ValueError('Unexpected System row rename')
                    changes.append({'action':'rename-library-row','table':table,'id':row[key],'name':old['strName'],
                                    'values':{k:row[k] for k in ('strName','lbContext')}})
                    continue
                if values:changes.append({'action':'update','table':table,'key':key,'id':row[key],'values':values})
        ordered_renumbers = [op for _, op in sorted(picture_renumbers, key=lambda item: item[0])]
        db({'action':'write','path':str(output),'changes':removals+ordered_renumbers+changes,'expected_sha256':before_sha})
    else:
        before_sha=None
        after=create_data(spec, 'Stu' if output.suffix.lower()=='.mcs' else 'Pro',
                          pending_event_generation=pending_event_generation)
        db({'action':'create','path':str(output),'seed':after})
    actual=read(output)
    if canonical(actual)!=canonical(after):
        raise ValueError('Output full-table readback mismatch; candidate is not accepted')
    if source and sha(source)!=before_sha:raise ValueError('Original changed; candidate is not accepted')
    result={'status':'file_readback_passed','output':str(output),'sha256':sha(output),
            'source_unchanged':True if source else None,'tables_checked':len(actual),
            'pages':len(actual['WndUser']['rows']),'host_validation':'pending','physically_tested':False}
    if batch_result is not None:result['bounded_batch']=batch_result
    if pending_event_generation:result['pending_original_event_generation']=pending_event_generation
    return result


def main():
    if sys.version_info < (3,11):
        raise ValueError('Python 3.11 or newer is required')
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    doctor=sub.add_parser('doctor');doctor.add_argument('--workdir',default='.')
    demo=sub.add_parser('demo');demo.add_argument('--directory',required=True)
    view=sub.add_parser('inspect');view.add_argument('source')
    for cmd in ('create','edit'):
        help_text=('Create a Stu (.mcs) or Pro (.mcp) project from variables/pages; --template uses the edit schema'
                   if cmd=='create' else 'Edit a new copy using source_sha256 and variables/pages/add_variables/add_pages')
        p=sub.add_parser(cmd,description=help_text)
        p.add_argument('--spec',required=True,help='JSON project specification')
        p.add_argument('--output',required=True,help='New filename in an existing directory')
        if cmd=='edit':
            p.add_argument('--source',required=True)
            p.add_argument('--batch-plan',help='Apply the bounded batch-edit plan before the structural edit in one copy')
        else:p.add_argument('--template',help='Create from a Stu or Pro template using an edit specification and its source_sha256; use the same family for output')
    args=parser.parse_args()
    if args.command=='doctor':
        result=db({'action':'doctor'})
        folder=Path(args.workdir).resolve()
        if not folder.is_dir():raise ValueError('Existing writable doctor workdir required')
        scratch=folder/('.mcgs-doctor-'+__import__('uuid').uuid4().hex+'.mdb')
        seed={'Probe':{'fields':[{'name':'iID','type':3,'size':4},{'name':'payload','type':205,'size':4}],
                       'rows':[{'iID':1,'payload':f.wrap(bytes([0,1,2,255]))}]}}
        try:
            db({'action':'create','path':str(scratch),'seed':seed})
            observed=read(scratch)
            if canonical(observed)!=canonical(seed):raise ValueError('Provider BLOB roundtrip failed')
            result['ace_create_and_blob_readback']=True
        finally:
            if scratch.is_file():scratch.unlink()
        result.update(python=sys.version,python_packages_required=[],mcp_server_required=False,
                      target_family='McgsPro', template_provenance='McgsPro 3.5.1.6963', software_version_gate=False)
    elif args.command=='demo':
        folder=Path(args.directory).absolute();folder.mkdir(exist_ok=False)
        initial=json.loads((HOME/'examples/create.json').read_text(encoding='utf-8'))
        first=write_project(folder/'demo.mcp',initial)
        observed=inspect_data(read(folder/'demo.mcp'))
        label=one(c for c in observed['pages'][0]['controls'] if c.get('name')=='标题')
        plan={'source_sha256':first['sha256'],
              'variables':[{'name':'设定值','initial':'35'}],
              'pages':[{'id':1,'controls':[{'name':'标题','sha256':label['sha256'],
                        'edits':{'text':'离线修改后的工程标题'}}]}]}
        (folder/'edit.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        second=write_project(folder/'demo-edited.mcp',plan,folder/'demo.mcp')
        result={'create':first,'edit':second,'host_validation':'pending'}
        (folder/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    elif args.command=='inspect':
        result=inspect_data(read(args.source));result['source_sha256']=sha(args.source)
    else:
        spec=json.loads(Path(args.spec).read_text(encoding='utf-8-sig'))
        template=getattr(args,'template',None)
        result=write_project(args.output,spec,getattr(args,'source',None) or template,
                             batch_plan=getattr(args,'batch_plan',None))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'error','type':type(exc).__name__,'message':str(exc)},ensure_ascii=False))
        sys.exit(1)
