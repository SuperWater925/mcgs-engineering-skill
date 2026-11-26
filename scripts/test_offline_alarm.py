"""Known existing ObjData alarm layouts and metadata-only mutations."""
import copy
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/pro-3.5-cli/scripts'))
import mcgs_file as m


def sample_project(family, *, default_source=False, messages=('Test alarm description',),
                   alarm_kind=2, sensor_type='number', base_value=4.25):
    data = m.create_data({'pages':[{'name':'Main'}], 'variables':[
        {'type':sensor_type,'name':'AlarmSensor'}, {'type':'number','name':'OtherSensor'}]}, family)
    row = m.system(data, 'ObjData')
    records = m.f.variables(m.f.archive(row['lbContext']))
    sensor = next(record for record in records if record['name']=='AlarmSensor')
    extension = sensor['extension']
    assert extension[:8]==bytes(8)
    item_width, tail_width = (52,4) if family=='Stu' else (40,0)
    body = bytearray(struct.pack('<III', (11<<16)|7, 1, alarm_kind) + bytes(range(item_width-12)))
    if default_source:
        struct.pack_into('<I', body, 12, 0xffffffff)
        struct.pack_into('<d' if item_width==52 else '<f', body, 16, base_value)
    alarms = b''.join(bytes(body)+m.f.text(value)+bytes(tail_width) for value in messages)
    sensor['extension'] = struct.pack('<III', 0,1,len(messages)) + alarms + extension[8:]
    row['lbContext'] = m.f.wrap_like(row['lbContext'], m.f.pack_variables(records))
    return data


class OfflineAlarmTests(unittest.TestCase):
    def test_alarm_enabled_edits_only_the_selected_checkbox_word(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = sample_project(family, messages=('Selected alarm', 'Other alarm'))
                original = copy.deepcopy(data)
                selected, other = m.inspect_data(data)['alarm_definitions']
                self.assertIs(selected['enabled'], True)
                identity = {key:selected[key] for key in ('variable', 'index', 'sha256')}
                row = m.system(data, 'ObjData')
                before = m.f.archive(row['lbContext'])
                records = m.f.variables(before)
                ident = selected['variable']['id']
                record = next(record for record in records if record['id'] == ident)
                start, end, _ = records.alarm_spans[ident][0]
                wire = record['extension'][start:end]
                self.assertEqual(before.count(wire), 1)
                offset = before.index(wire) + 4

                with self.assertRaisesRegex(ValueError, 'enabled must be a boolean'):
                    m.edit_data(data, {'alarm_edits': [{**identity, 'enabled': 0}]})
                self.assertEqual(data, original)
                m.edit_data(data, {'alarm_edits': [{**identity, 'enabled': False}]})
                self.assertEqual(m.f.archive(row['lbContext']), before[:offset] + bytes(4) + before[offset+4:])
                selected, retained = m.inspect_data(data)['alarm_definitions']
                self.assertIs(selected['enabled'], False)
                self.assertEqual(retained, other)
                m.edit_data(data, {'alarm_edits': [{**identity, 'sha256': selected['sha256'], 'enabled': True}]})
                self.assertEqual(data, original)

    def test_message_retarget_preserves_the_application_dictionary_and_other_alarms(self):
        for family, start in (('Stu',16), ('Pro',12)):
            with self.subTest(family=family):
                data = sample_project(family,messages=('\x0710114','\x0710115'))
                row = m.system(data,'MCGSLINGUIST')
                definition = struct.pack('<I',0)+m.f.text('English')
                definition += (m.f.text('Arial')+struct.pack('<II',100,0xffffffff))*2
                texts = {10114:'Old alarm',10115:'Other alarm',42:'New alarm'}
                entries = b''.join(struct.pack('<III',key,1,0)+m.f.text(value) for key,value in texts.items())
                plain = bytes(start)+struct.pack('<III',1,0,1)+definition+struct.pack('<I',len(texts))+entries
                row['lbContext'] = m.f.wrap(plain+struct.pack('<I',1))
                original = copy.deepcopy(data)
                old, other = m.inspect_data(data)['alarm_definitions']
                self.assertTrue(old['message_text_id_editable'])
                self.assertEqual(old['message_text_id'],10114)
                selection = {k:old[k] for k in ('variable','index','sha256')}
                with self.assertRaisesRegex(ValueError,'no verified existing translations'):
                    m.edit_data(data, {'alarm_edits':[{**selection,'message_text_id':99}]})
                self.assertEqual(data,original)
                bad_map = copy.deepcopy(data)
                m.system(bad_map,'MCGSLINGUIST')['lbContext'] = m.f.wrap(plain)
                self.assertFalse(m.inspect_data(bad_map)['alarm_definitions'][0]['message_text_id_editable'])
                self.assertEqual(m.inspect_data(bad_map)['alarm_definitions'][0]['priority'],old['priority'])

                m.edit_data(data, {'alarm_edits':[{**selection,'message_text_id':42}]})
                self.assertEqual(m.system(data,'MCGSLINGUIST'),m.system(original,'MCGSLINGUIST'))
                updated, retained = m.inspect_data(data)['alarm_definitions']
                self.assertEqual(updated['message_text_id'],42)
                self.assertEqual(updated['message_translations'],{0:'New alarm'})
                self.assertEqual(retained,other)
                original_blob = m.f.archive(m.system(original,'ObjData')['lbContext'])
                changed_blob = m.f.archive(m.system(data,'ObjData')['lbContext'])
                self.assertEqual(len(original_blob)-len(changed_blob),6)

    def test_upper_limit_uses_native_width_and_retains_unknown_parameter_sources(self):
        for family, format_code in (('Stu','<d'), ('Pro','<f')):
            with self.subTest(family=family):
                source = sample_project(family)
                blocked, = m.inspect_data(source)['alarm_definitions']
                self.assertFalse(blocked['upper_limit_value_editable'])
                selection = {k:blocked[k] for k in ('variable','index','sha256')}
                with self.assertRaisesRegex(ValueError, 'default parameter source'):
                    m.edit_data(source, {'alarm_edits':[{**selection,'upper_limit_value':21}]})

                data = sample_project(family, default_source=True)
                snapshot, = m.inspect_data(data)['alarm_definitions']
                self.assertTrue(snapshot['upper_limit_value_editable'])
                self.assertEqual(snapshot['upper_limit_value'],4.25)
                selection = {k:snapshot[k] for k in ('variable','index','sha256')}
                old = m.f.archive(m.system(data,'ObjData')['lbContext'])
                for invalid in (True, float('nan'), float('inf'), 10**500):
                    with self.assertRaisesRegex(ValueError, 'finite floating-point'):
                        m.edit_data(data, {'alarm_edits':[{**selection,'upper_limit_value':invalid}]})
                    self.assertEqual(m.f.archive(m.system(data,'ObjData')['lbContext']),old)
                value = 12345.678901234
                m.edit_data(data, {'alarm_edits':[{**selection,'upper_limit_value':value}]})
                new = m.f.archive(m.system(data,'ObjData')['lbContext'])
                position = old.index(struct.pack(format_code,4.25))
                encoded = struct.pack(format_code,value)
                self.assertEqual(new,old[:position]+encoded+old[position+len(encoded):])
                after, = m.inspect_data(data)['alarm_definitions']
                self.assertEqual(after['upper_limit_value'],struct.unpack(format_code,encoded)[0])

    def test_switch_equals_uses_native_base_value_only_for_exact_default_source(self):
        for family, format_code in (('Stu','<d'), ('Pro','<f')):
            with self.subTest(family=family):
                blocked = sample_project(family,alarm_kind=6,sensor_type='boolean')
                entry, = m.inspect_data(blocked)['alarm_definitions']
                selection = {key:entry[key] for key in ('variable','index','sha256')}
                self.assertFalse(entry['switch_equals_value_editable'])
                with self.assertRaisesRegex(ValueError,'verified default parameter source'):
                    m.edit_data(blocked,{'alarm_edits':[{**selection,'switch_equals_value':1}]})

                data = sample_project(family,default_source=True,alarm_kind=6,sensor_type='boolean',base_value=0)
                original = copy.deepcopy(data)
                entry, = m.inspect_data(data)['alarm_definitions']
                self.assertTrue(entry['switch_equals_value_editable'])
                self.assertFalse(entry['upper_limit_value_editable'])
                self.assertEqual(entry['switch_equals_value'],0)
                selection = {key:entry[key] for key in ('variable','index','sha256')}
                for invalid in (True,1.0,-1,2):
                    with self.assertRaisesRegex(ValueError,'must be integer 0 or 1'):
                        m.edit_data(data,{'alarm_edits':[{**selection,'switch_equals_value':invalid}]})
                    self.assertEqual(data,original)
                row = m.system(data,'ObjData')
                before = m.f.archive(row['lbContext'])
                records = m.f.variables(before)
                sensor = next(record for record in records if record['id']==entry['variable']['id'])
                start,end,_ = records.alarm_spans[sensor['id']][0]
                wire = sensor['extension'][start:end]
                self.assertEqual(before.count(wire),1)
                point = before.index(wire)+16
                encoded = struct.pack(format_code,1)
                m.edit_data(data,{'alarm_edits':[{**selection,'switch_equals_value':1}]})
                self.assertEqual(m.f.archive(row['lbContext']),before[:point]+encoded+before[point+len(encoded):])
                actual, = m.inspect_data(data)['alarm_definitions']
                self.assertEqual(actual['switch_equals_value'],1)
                selection['sha256'] = actual['sha256']
                m.edit_data(data,{'alarm_edits':[{**selection,'switch_equals_value':0}]})
                self.assertEqual(data,original)

    def test_existing_metadata_preserves_all_other_bytes_and_rejects_unknown_mirrors(self):
        for family in ('Stu','Pro'):
            with self.subTest(family=family):
                data = sample_project(family)
                original = copy.deepcopy(data)
                entries = m.inspect_data(data)['alarm_definitions']
                first, = entries
                self.assertTrue(first['editable'])
                selector = {k:first[k] for k in ('variable','index','sha256')}

                for invalid, reason in (({**selector,'sha256':'0'*64,'priority':42}, 'preimage'),
                                        ({**selector,'group':True}, 'integer range')):
                    with self.assertRaisesRegex(ValueError, reason):
                        m.edit_data(data, {'alarm_edits':[invalid]})
                    self.assertEqual(data,original)
                with self.assertRaisesRegex(ValueError, 'repeated'):
                    m.edit_data(data, {'alarm_edits':[{**selector,'group':20}]*2})
                self.assertEqual(data,original)
                unknown = copy.deepcopy(data)
                unknown['Alarm']['rows'].append({'iAlarmID':1})
                self.assertIn('mirror mapping',m.inspect_data(unknown)['alarm_definitions_unavailable'])
                with self.assertRaisesRegex(ValueError, 'mirror mapping'):
                    m.edit_data(unknown, {'alarm_edits':[{**selector,'priority':20}]})

                m.edit_data(data, {'alarm_edits':[{**selector,'priority':42}]})
                after, = m.inspect_data(data)['alarm_definitions']
                self.assertEqual((after['group'],after['priority']),(11,42))
                before_raw, after_raw = [
                    m.f.archive(m.system(d,'ObjData')['lbContext']) for d in (original,data)]
                self.assertEqual(len(after_raw),len(before_raw))
                self.assertEqual([(old,new) for old,new in zip(before_raw,after_raw) if old!=new],[(7,42)])
                self.assertEqual(set(k for k in data if data[k]!=original[k]),{'System'})


if __name__=='__main__':
    unittest.main()
