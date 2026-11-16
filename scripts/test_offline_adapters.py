"""Offline structural regressions; no vendor process, database or device use."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native'),str(ROOT/'assets/pro-3.5-cli/scripts')]
import control_factory as factory
import control_patch
import native_format as fmt
import mcgs_file
from mcs_input_text import InputRecord, InputMetadata
from mcs_button_control import ButtonArchive
from mcs_window_archive import Reader, WindowSettings, OleVariant, write_count, write_cstring
from 原生界面样式 import CommonEnvelope, MultiState


def preset(kind):
    return factory.primitive_record(kind)


class OfflineAdapters(unittest.TestCase):
    def test_geometry_entry_points_match(self):
        for kind,bounds in [('line',[15,10,3,10]),('rectangle',[1,2,81,42]),('label',[1,2,91,42])]:
            original=preset(kind)
            a=control_patch.edit(original,{'bounds':bounds})
            b=factory.edit_control(original.type_id,original.payload,{'bounds':bounds})
            self.assertEqual(a.payload,b)
            self.assertEqual(list(CommonEnvelope.parse(a).rect),bounds)

    def test_multistate_geometry_uses_same_dispatch(self):
        original=preset('rectangle');original.type_id=0x502a
        states=MultiState(CommonEnvelope.parse(original),[0.,1.],[],[[],[]],[[],[]],b'tail')
        original=states.to_record();bounds=[1,2,301,102]
        a=control_patch.edit(original,{'bounds':bounds})
        b=factory.edit_control(original.type_id,original.payload,{'bounds':bounds})
        self.assertEqual(a.payload,b)
        self.assertEqual(MultiState.parse(a).tail,b'tail')

    def test_input_expression_limits_do_not_block_style(self):
        original=preset('numeric-input');q=InputRecord.parse(original)
        q.set_limits(minimum='MinSet',maximum='MaxSet + 10')
        original.payload=q.to_bytes()
        changed=control_patch.edit(original,{'unit':'kPa','font':{'height':23}})
        value=InputRecord.parse(changed)
        self.assertEqual(value.limit('minimum'),'MinSet')
        self.assertEqual(value.limit('maximum'),'MaxSet + 10')
        self.assertEqual(value.unit,'kPa')
        changed.payload=factory.edit_control(changed.type_id,changed.payload,{'minimum':-50})
        value=InputRecord.parse(changed)
        self.assertEqual(value.limit('minimum'),-50)
        self.assertEqual(value.limit('maximum'),'MaxSet + 10')

    def test_button_events_and_unknown_tails_survive_style(self):
        original=preset('button');q=ButtonArchive.parse(original)
        name=b'CEventDispatch'
        event=(b'\xff\xff'+struct.pack('<HH',0,len(name))+name+bytes(8)+struct.pack('<I',1)+
               write_cstring('Click')+struct.pack('<I',1)+write_cstring('')+bytes(4)+
               write_cstring('Motor = 1')+bytes(2))
        q.metadata.empty_events=write_count(1)+event
        q.metadata.tail=b'outer-extension';q.metadata.extension_extra=b'nested-extension'
        q.metadata.properties.tail=b'property-extension';q.tail=b'control-extension'
        original.payload=q.to_bytes()
        changed=control_patch.edit(original,{'text':'Run','font':{'height':24}})
        result=ButtonArchive.parse(changed)
        self.assertEqual(result.metadata.empty_events,q.metadata.empty_events)
        self.assertEqual(result.metadata.tail,q.metadata.tail)
        self.assertEqual(result.metadata.extension_extra,q.metadata.extension_extra)
        self.assertEqual(result.metadata.properties.tail,q.metadata.properties.tail)
        self.assertEqual(result.tail,q.tail)
        self.assertTrue(result.summary()['native_generic_click_event'])

    def test_local_button_prototype_is_neutral_and_clone_keeps_actions(self):
        original=preset('button');q=ButtonArchive.parse(original)
        q.release_script.value='Motor = 1';q.metadata.properties.press_script.value='Flag = 1'
        q.enabled_expression.value='Allowed';original.payload=q.to_bytes()
        data=bytearray(original.payload);struct.pack_into('<f',data,0,333.75);original.payload=bytes(data)
        pages=[{'id':1,'controls':[original]}];before=original.payload
        new=factory.primitive_record('button',source_pages=pages)
        self.assertEqual(new.payload[:4],original.payload[:4])
        neutral=ButtonArchive.parse(new)
        self.assertEqual(neutral.release_script.value,'')
        self.assertEqual(neutral.metadata.properties.press_script.value,'')
        self.assertEqual(neutral.enabled_expression.value,'1')
        descriptor={'page_id':1,'path':[0],'name':CommonEnvelope.parse(original).name.value,
                    'kind':original.type_id,'sha256':hashlib.sha256(original.payload).hexdigest()}
        kind,payload=factory.make_control({'type':'button','name':'Clone','bounds':[1,2,91,42],
                                         'clone_from':descriptor},{},source_pages=pages)
        clone=ButtonArchive.parse(factory.record(kind,payload))
        self.assertEqual(clone.release_script.value,'Motor = 1')
        self.assertEqual(clone.enabled_expression.value,'Allowed')
        self.assertEqual(original.payload,before)

    def test_window_leading_properties_and_integer_width(self):
        def integer(value,vt=3):
            wire=struct.pack('<H',vt)+struct.pack('<I' if vt==19 else '<i',value)
            return OleVariant.parse(Reader(wire))
        props=[integer(7),OleVariant(8,'Page',struct.pack('<HI',8,8)+'Page'.encode('utf-16le'))]
        props.extend(integer(0) for _ in range(14));props[6]=integer(800,19);props[7]=integer(480)
        original=WindowSettings(b'',props,b'events',identity=(7,'Page'))
        original.properties.insert(0,OleVariant.parse(Reader(bytes(2))))
        copied=WindowSettings.parse(original.to_bytes(),identity=(7,'Page')).clone(8,'New')
        self.assertEqual(copied.field('width').value,800)
        self.assertEqual(copied.field('width').vt,19)
        copied.field('width').value=1024
        self.assertEqual(WindowSettings.parse(copied.to_bytes(),identity=(8,'New')).field('width').value,1024)
        self.assertEqual(copied.event_tail,b'events')

    def test_unknown_alarm_layout_preserved_on_variable_edit(self):
        templates=json.loads((ROOT/'assets/pro-3.5-cli/assets/primitives.json').read_text(encoding='utf-8'))
        template=templates['variables']['number']
        row={'id':3,'name':'Temperature','kind':2,'note':'','unit':'C','initial':'0',
             'prefix':bytes.fromhex(template['prefix']),
             'extension':bytes(4)+struct.pack('<II',1,1)+bytes.fromhex('abababab')*15+
                         write_cstring('High alarm')+struct.pack('<2I',91,92)+bytes(4)+write_cstring('')}
        # pack_variables also performs its full structural readback.
        blob=fmt.pack_variables(fmt.VariableRecords([row]))
        read=fmt.variables(blob);self.assertEqual(read[0]['extension'],row['extension'])
        read[0]['initial']='20';changed=fmt.pack_variables(read)
        self.assertEqual(fmt.variables(changed)[0]['extension'],row['extension'])


if __name__=='__main__':unittest.main()
