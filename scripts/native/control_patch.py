"""Bounded existing-control edits shared by Stu and Pro. No database access."""
from __future__ import annotations
import copy
import math
import struct
from 原生界面样式 import CommonEnvelope, GroupArchive, MultiState, edit_font
from mcs_input_text import InputRecord, LabelRecord, InputMetadata
from mcs_button_control import ButtonArchive
from control_geometry import resize
from 当前存盘浏览样式 import SAVED_DATA_STYLE_FIELDS, edit_saved_data_style
from 原生趋势样式 import HISTORY_CURVE_EDIT_FIELDS, edit_history_curve_colors, edit_history_curve_pens

def text(value):
    if not isinstance(value,str) or '\0' in value:raise ValueError('Expected text without NUL')
    return value

def edit(record,changes,variables=None,picture_references=None):
    allowed={'bounds','fill','border','text','font','unit','binding','minimum','maximum','press_source','release_source','repair_input_metadata','state_edits','state_layout','button_pictures','animations'} | SAVED_DATA_STYLE_FIELDS | HISTORY_CURVE_EDIT_FIELDS
    if not isinstance(changes,dict):raise ValueError('Control edit must be an object')
    if not changes or set(changes)-allowed:raise ValueError('Unknown or empty control edit')
    if HISTORY_CURVE_EDIT_FIELDS & changes.keys():
        if len(changes) != 1:
            raise ValueError('History curve pens require a dedicated edit')
        if 'history_curve_colors' in changes:
            return edit_history_curve_colors(record, changes['history_curve_colors'])
        return edit_history_curve_pens(record, changes['history_curve_pens'])
    if SAVED_DATA_STYLE_FIELDS & changes.keys():
        if changes.keys() - SAVED_DATA_STYLE_FIELDS:
            raise ValueError('Saved-data browser styling requires a dedicated edit')
        return edit_saved_data_style(record, changes, variables)
    cm=CommonEnvelope.parse(record)
    if cm.to_record().payload!=record.payload:raise ValueError('Control original roundtrip differs')
    if 'bounds' in changes:
        record=resize(record,changes['bounds'])
    cm=CommonEnvelope.parse(record)
    for key in ('fill','border'):
        if key in changes and (type(changes[key])is not int or not 0<=changes[key]<=0xffffff):raise ValueError('Colors use integer COLORREF 0..0xffffff')
    cm.set_common_colors(**{k:changes[k] for k in ('fill','border') if k in changes})
    record=cm.to_record()
    special=set(changes)-{'bounds','fill','border'}
    if 'animations' in special:
        from animation_edits import edit_items
        record=edit_items(record,changes['animations'])
        cm=CommonEnvelope.parse(record)
        special.remove('animations')
    if not special:return record
    if 'state_layout' in special:
        record = edit_state_layout(record, changes['state_layout'])
        special.remove('state_layout')
        if not special:
            return record
    if 'state_edits' in changes:
        if special!={'state_edits'}:raise ValueError('State edits cannot be mixed with other class-specific properties')
        return edit_states(record,changes['state_edits'],picture_references)
    projected=cm.project_without_animations()
    kind=record.type_id
    parsers={0x5008:LabelRecord,0x5025:InputRecord,0x5027:ButtonArchive}
    if kind not in parsers:raise ValueError('Class-specific edit requires label/input/standard button')
    q=parsers[kind].parse(projected)
    if q.to_bytes()!=projected.payload:raise ValueError('Class original roundtrip differs')
    if 'button_pictures' in changes:
        if kind!=0x5027:raise ValueError('Button picture slots require a standard button')
        from picture_resources import replace_picture
        slots=changes['button_pictures']
        if not isinstance(slots,dict) or not slots or set(slots)-{'primary','properties'}:raise ValueError('Button picture slots are primary/properties')
        for slot,spec in slots.items():
            owner=q if slot=='primary' else q.metadata.properties
            if not owner.picture:raise ValueError('Requested button picture slot is not serialized/enabled')
            owner.picture=replace_picture(owner.picture,spec,picture_references)
    if 'repair_input_metadata' in changes:
        if kind!=0x5025 or changes['repair_input_metadata'] is not True:raise ValueError('Metadata length repair requires an input and true')
        metadata=InputMetadata.parse(q.common.metadata,q.appearance);metadata.normalize_counts()
        q.common.metadata=metadata.to_bytes();InputMetadata.parse(q.common.metadata)
    if 'text' in changes:
        value=text(changes['text'])
        if kind==0x5008:q.caption=value
        elif kind==0x5027:q.caption.value=q.metadata.properties.caption.value=value
        else:raise ValueError('Caption requires label or button')
    if 'font' in changes:
        font=changes['font']
        q.font=edit_font(q.font,font)
        if kind==0x5027:q.metadata.properties.font=edit_font(q.metadata.properties.font,font)
    if special & {'unit','binding','minimum','maximum'}:
        if kind!=0x5025:raise ValueError('Input properties require an input control')
        if 'unit' in changes:q.set_unit(text(changes['unit']))
        if 'binding' in changes:
            name=text(changes['binding']);target=(variables or {}).get(name)
            if target is None or target['kind'] not in (1,2,3):raise ValueError('Binding must resolve to an existing scalar object')
            # Preserve numeric versus character editor semantics.
            if (q.variable_type==3)!=(target['kind']==3):raise ValueError('Numeric/character binding kind differs')
            if (q.variable,q.variable_id,q.variable_type)!=(name,target['id'],target['kind']):
                q.variable=name;q.properties[5]=target['id'];q.properties[6]=target['kind'];q.expression_cache=b''
        if special & {'minimum','maximum'}:
            q.set_limits(**{key:changes[key] for key in ('minimum','maximum') if key in changes})
    for key in ('press_source','release_source'):
        if key in changes:
            if kind!=0x5027:raise ValueError('Native press/release source requires a standard button')
            value=text(changes[key]);owner=q.metadata.properties if key=='press_source' else q
            attr='press_script' if key=='press_source' else 'release_script'
            cache='press_compiled' if key=='press_source' else 'release_compiled'
            if getattr(owner,attr).value!=value:
                getattr(owner,attr).value=value;getattr(owner,cache).value=b''
    projected.payload=q.to_bytes()
    # Reparse both the class body and the animation-bearing native result.
    if parsers[kind].parse(projected).to_bytes()!=projected.payload:raise ValueError('Changed class roundtrip differs')
    out=cm.restore_projected(projected)
    if CommonEnvelope.parse(out).to_record().payload!=out.payload:raise ValueError('Changed common roundtrip differs')
    if CommonEnvelope.parse(out).prefix[cm.animation_start:cm.animation_end]!=cm.prefix[cm.animation_start:cm.animation_end]:raise ValueError('Animation bytes changed')
    return out

def at_path(controls,path):
    if not isinstance(path,list) or not path or any(type(i)is not int or i<0 for i in path):raise ValueError('Control path requires nonnegative indexes')
    try:
        record=controls[path[0]]
        if len(path)==1:return record
        return at_path(GroupArchive.parse(record).children,path[1:])
    except IndexError:raise ValueError('Control path outside existing records')

def replace_path(controls,path,replacement):
    if len(path)==1:controls[path[0]]=replacement;return
    group=GroupArchive.parse(controls[path[0]])
    replace_path(group.children,path[1:],replacement)
    controls[path[0]]=group.to_record()


def _color(value):
    if type(value) is not int or not 0<=value<=0xffffff:
        raise ValueError('Colors use integer COLORREF 0..0xffffff')
    return value


def _check_state_tail(q):
    from mcs_window_archive import Reader
    if q.common.record.type_id == 0x5028:
        from 原生界面样式 import MultiButtonTail
        bindings = MultiButtonTail.parse(q.tail)
        if bindings.to_bytes() != q.tail:
            raise ValueError("Multi-state button binding roundtrip differs")
        # The identical action suffix occurs on native 2/5/10-state
        # buttons, and its alternate first word on 1/2-state buttons.
        r = Reader(bindings.rest)
        mode = r.u32()
        fields = [r.u32() for _ in range(9)]
        if (mode not in (0, 1) or fields != [0, 0, 0x3f800000, 0x42c80000, 0, 5, 1, 0, 1]
                or r.cstring()[0] or r.take(10) != bytes(10) or r.pos != len(bindings.rest)):
            raise ValueError("Button action tail lacks a verified threshold mapping")
    else:
        # Complete observed display tail contains binding data and no
        # per-state array. The second string can hold a condition.
        r = Reader(q.tail)
        if r.u32() not in (0, 1):
            raise ValueError("Unknown display binding mode")
        r.cstring()
        r.take(16)
        r.cstring()
        r.take(4)
        if r.pos != len(q.tail):
            raise ValueError("Unknown display binding tail extent")


def inspect_state_layout(q):
    info = {"thresholds": q.levels, "fills": q.fills,
            "texts_per_state": [len(items) for items in q.texts],
            "images_per_state": [len(items) for items in q.images]}
    try:
        if len(q.levels) != len(q.fills):
            raise ValueError("State fill count differs from thresholds")
        _check_state_tail(q)
        info["threshold_layout_verified"] = True
    except (ValueError, UnicodeError) as error:
        info.update(threshold_layout_verified=False, reason=str(error))
    return info


def edit_state_layout(record, layout):
    """Map final rows and children explicitly to original state indexes."""
    original = MultiState.parse(record)
    if not isinstance(layout, list) or not layout or len(original.fills) != len(original.levels):
        raise ValueError("State layout requires aligned fills and a nonempty final list")
    q = copy.deepcopy(original)
    q.levels, q.fills, q.images, q.texts = [], [], [], []
    for row in layout:
        if not isinstance(row, dict) or "source" not in row or set(row) - {"source", "threshold", "texts", "images"}:
            raise ValueError("Expected state source and optional threshold/child mappings")
        source = row["source"]
        if type(source) is not int or not 0 <= source < len(original.levels):
            raise ValueError("Invalid original state index")
        threshold = row.get("threshold", original.levels[source])
        if type(threshold) not in (int, float) or not -3.4028234663852886e38 <= threshold <= 3.4028234663852886e38:
            raise ValueError("Threshold must be finite float32")
        q.levels.append(struct.unpack("<f", struct.pack("<f", threshold))[0])
        q.fills.append(original.fills[source][:])
        for key in ("images", "texts"):
            groups = getattr(original, key)
            refs = row.get(key, list(range(len(groups[source]))))
            if not isinstance(refs, list):
                raise ValueError("State child mapping must be an ordered list")
            children = []
            for ref in refs:
                state, index = source, ref
                if isinstance(ref, dict) and set(ref) == {"state", "child"}:
                    state, index = ref["state"], ref["child"]
                if (type(state) is not int or not 0 <= state < len(groups)
                        or type(index) is not int or not 0 <= index < len(groups[state])):
                    raise ValueError("Invalid original state/child index")
                children.append(copy.deepcopy(groups[state][index]))
            getattr(q, key).append(children)
    if any(a >= b for a, b in zip(q.levels, q.levels[1:])):
        raise ValueError("Final float32 thresholds must increase strictly")
    if q.levels != original.levels:
        _check_state_tail(original)
    out = q.to_record()
    after = MultiState.parse(out)
    if (after.levels, after.fills, after.images, after.texts, after.tail) != (q.levels, q.fills, q.images, q.texts, original.tail):
        raise ValueError("State layout verification failed")
    return out


def edit_states(record, edits, picture_references=None):
    """Edit existing state children only; retain thresholds, binding and metadata."""
    from picture_resources import replace_picture
    q=MultiState.parse(record)
    before=q.to_record().payload
    if not isinstance(edits,list) or not edits:raise ValueError('state_edits requires a nonempty list')
    selected=set()
    for spec in edits:
        if not isinstance(spec,dict) or set(spec)-{'state','fill','texts','images'} or 'state' not in spec or len(spec)<2:
            raise ValueError('State edit requires state and fill/texts/images')
        state=spec['state']
        if type(state) is not int or not 0<=state<len(q.levels):raise ValueError('State index outside existing thresholds')
        if state in selected:raise ValueError('Duplicate state index')
        selected.add(state)
        if 'fill' in spec:
            if len(q.fills)!=len(q.levels):raise ValueError('State fill count differs from thresholds')
            # Keep the original brush style; changing its color does not enable it.
            q.fills[state][1]=_color(spec['fill'])
        for collection in ('texts','images'):
            if collection not in spec:continue
            updates=spec[collection]
            if not isinstance(updates,list) or not updates:raise ValueError('State child edits require a nonempty list')
            children=getattr(q,collection)[state];seen=set()
            for item in updates:
                fields={'child','text','font','color'} if collection=='texts' else {'child','picture'}
                if not isinstance(item,dict) or set(item)-fields or 'child' not in item or len(item)<2:
                    raise ValueError('Unknown or empty state child edit')
                index=item['child']
                if type(index) is not int or not 0<=index<len(children) or index in seen:
                    raise ValueError('State child index is duplicate or outside existing children')
                seen.add(index);child=children[index]
                if 'text' in item:child.caption.value=text(item['text'])
                if 'font' in item:child.font=edit_font(child.font,item['font'])
                if 'color' in item:child.set_text_color(_color(item['color']))
                if 'picture' in item:child.picture=replace_picture(child.picture,item['picture'],picture_references)
    out=q.to_record()
    reread=MultiState.parse(out)
    if reread.to_record().payload!=out.payload:raise ValueError('Edited state byte roundtrip differs')
    # Strong inverse proof: restore exactly the authorized subfields, not the
    # entire control. This catches accidental changes in any opaque/native part.
    original=MultiState.parse(record)
    for spec in edits:
        state=spec['state']
        if 'fill' in spec:reread.fills[state][1]=original.fills[state][1]
        for collection in ('texts','images'):
            for item in spec.get(collection,[]):
                index=item['child'];dst=getattr(reread,collection)[state][index];src=getattr(original,collection)[state][index]
                if 'text' in item:dst.caption=copy.deepcopy(src.caption)
                if 'font' in item:dst.font=src.font
                if 'color' in item:dst.tail=src.tail[:4]+dst.tail[4:]
                if 'picture' in item:dst.picture=src.picture
    if reread.to_record().payload!=before:raise ValueError('State edit changed an unrequested field')
    return out
