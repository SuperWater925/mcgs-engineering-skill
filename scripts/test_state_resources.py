"""Pure state/resource editing regressions; no database or vendor process."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/native'),str(ROOT/'assets/pro-3.5-cli/scripts')]
import control_factory as factory
import control_patch as cp
import native_tool as nt
from mcs_button_control import CString,ButtonArchive
from mcs_window_archive import Reader,write_cstring
from 原生界面样式 import CommonEnvelope,GroupArchive,MultiChild,MultiState,fonts
from picture_resources import Picture,PictureResource,CELL_TAG,raster_details,replace_picture


def string(value):return CString.parse(Reader(write_cstring(value)))
def digest(value):return hashlib.sha256(value).hexdigest()
def raster(kind='PNG',size=(2,3),color=(12,34,56)):
    from PIL import Image
    stream=io.BytesIO();Image.new('RGB',size,color).save(stream,format=kind);return stream.getvalue()


def states():
    q=ButtonArchive.parse(factory.primitive_record('button'))
    base=factory.primitive_record('rectangle');base.type_id=0x502a
    header=struct.pack('<18I',*range(18))
    texts=[[MultiChild(string('text'),header,None,string('State '+str(i)),q.font,bytes(range(28)))] for i in range(3)]
    pictures=[[MultiChild(string('image'),header,struct.pack('<I',128)+write_cstring('Picture1'),None,None,bytes(range(12)))] for i in range(3)]
    return MultiState(CommonEnvelope.parse(base),[0.,1.,2.],[[2,1],[2,2],[2,3]],pictures,texts,b'opaque-binding-and-tail').to_record()


def vector_resource(root_metadata_suffix=b'', root_tail=b'', first_child=None):
    child=factory.primitive_record('rectangle')
    base=copy.deepcopy(child);base.type_id=0x503a
    common=CommonEnvelope.parse(base)
    common.metadata.value+=root_metadata_suffix
    group=GroupArchive(common,[child if first_child is None else first_child,copy.deepcopy(child)],root_tail)
    root=group.to_record().payload
    # A fixed original allocation with nonzero opaque padding must survive.
    width,height=32,32;pixels=width*3*height
    body=b'VECT'+struct.pack('<I',len(CELL_TAG)+len(root))+struct.pack('<2I',400,200)+CELL_TAG+root
    header=struct.pack('<2sIHHI',b'BM',54+pixels,0,0,54)+struct.pack('<IiiHHIIiiII',40,width,height,1,24,0,pixels,0,0,0,0)
    payload=header+body+bytes([165])*(pixels-len(body))
    return PictureResource(string('Vector'),string('opaque-id'),16,width,height,payload)


class StateAndResourceEdits(unittest.TestCase):
    def test_history_trace_pens_preserve_every_unrequested_native_field(self):
        import mcgs_file as project
        from 原生趋势样式 import HistoryCurveStyle, history_curve_colors, history_curve_pens

        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                presets = project.load_factory_asset('primitives', family)
                record = factory.primitive_record('history-curve', presets)
                common = CommonEnvelope.parse(record)
                spans = HistoryCurveStyle(common.content).curve_pens()
                self.assertEqual(len(spans), 16)
                original = bytearray(common.content)
                start = spans[0].offset
                struct.pack_into('<IiiI', original, start, 6, 1, 75, 0xa000ff00)
                common.content = bytes(original)
                record = common.to_record()

                edits = {'history_curve_pens': [{'trace_index': 0, 'width': 4, 'color': 0x102030},
                                                {'trace_index': 1, 'style': 2, 'width': 1}]}
                changed = cp.edit(record, edits)
                expected = bytearray(original)
                struct.pack_into('<IiiI', expected, start, 6, 4, 75, 0xa0102030)
                struct.pack_into('<Ii', expected, spans[1].offset, 2, 1)
                self.assertEqual(CommonEnvelope.parse(changed).content, bytes(expected))
                self.assertEqual(factory.edit_control(record.type_id, record.payload, edits), changed.payload)
                self.assertEqual(history_curve_pens(changed)[0], {'trace_index': 0, 'style': 6, 'width': 4, 'color': 0x102030})
                self.assertEqual(history_curve_colors(changed)[0], {'trace_index': 0, 'color': 0x102030})
                legacy = cp.edit(record, {'history_curve_colors': [{'trace_index': 0, 'color': 0x102030}]})
                expected = original[:start+12] + b'\x30\x20\x10' + original[start+15:]
                self.assertEqual(CommonEnvelope.parse(legacy).content, bytes(expected))
                for style, width in ((2, 3), (5, 1), (6, 7), (True, 1), (6, True)):
                    with self.assertRaisesRegex(ValueError, 'style 1..4 at width 1'):
                        cp.edit(record, {'history_curve_pens': [{'trace_index': 0, 'style': style, 'width': width}]})

    def test_exact_state_subfields_and_inverse(self):
        original=states();q=MultiState.parse(original)
        edits={'state_edits':[{'state':1,'fill':0x123456,'texts':[{'child':0,'text':'Changed','font':{'height':25,'weight':600},'color':0xabcdef}]}]}
        result=MultiState.parse(cp.edit(original,edits))
        self.assertEqual(result.levels,q.levels);self.assertEqual(result.tail,q.tail)
        self.assertEqual(result.common.metadata.to_bytes(),q.common.metadata.to_bytes())
        self.assertEqual(result.images,q.images)
        for i in (0,2):self.assertEqual(result.texts[i][0].to_bytes(),q.texts[i][0].to_bytes())
        self.assertEqual(result.fills[1],[2,0x123456])
        self.assertEqual(result.texts[1][0].caption.value,'Changed')
        self.assertEqual(fonts(result.texts[1][0].font)[0]['height'],25)
        self.assertEqual(result.texts[1][0].tail[4:],q.texts[1][0].tail[4:])
        self.assertEqual(struct.unpack_from('<I',result.texts[1][0].tail)[0],0xabcdef)
        self.assertEqual(original.payload,states().payload)

    def test_font_style_flags_in_native_button_and_state_child(self):
        rec = factory.primitive_record("button")
        before = ButtonArchive.parse(rec)
        settings = {"italic": True, "underline": True, "strikeout": True}
        changed = ButtonArchive.parse(cp.edit(rec, {"font": settings}))
        for original, updated in ((before.font, changed.font),
                                  (before.metadata.properties.font, changed.metadata.properties.font)):
            self.assertTrue(all(all(row[key] for key in settings) for row in fonts(updated)))
            self.assertEqual(len(original), len(updated))
        with self.assertRaisesRegex(ValueError, "boolean"):
            cp.edit(rec, {"font": {"italic": 1}})
        with self.assertRaisesRegex(ValueError, "boolean"):
            cp.edit(rec, {"font": {"italic": None}})
        result = MultiState.parse(cp.edit(states(), {"state_edits": [
            {"state": 1, "texts": [{"child": 0, "font": {"underline": True}}]}]}))
        self.assertTrue(all(row["underline"] for row in fonts(result.texts[1][0].font)))

    def test_explicit_layout_maps_children_fills_and_rounded_thresholds(self):
        q = MultiState.parse(states())
        q.tail = bytes(4) + write_cstring("Flag") + bytes(16) + write_cstring("") + bytes(4)
        source = q.to_record()
        layout = [{"source": 2, "threshold": -1, "texts": [{"state": 1, "child": 0}, 0]},
                  {"source": 0, "threshold": 0, "images": []},
                  {"source": 2, "threshold": 3.5}]
        result = cp.edit(source, {"state_layout": layout, "state_edits": [
            {"state": 0, "texts": [{"child": 1, "text": "Copy"}]}]})
        after = MultiState.parse(result)
        self.assertEqual(after.levels, [-1, 0, 3.5])
        self.assertEqual(after.fills, [q.fills[i] for i in (2, 0, 2)])
        self.assertEqual([c.caption.value for c in after.texts[0]], ["State 1", "Copy"])
        self.assertEqual(after.images[1], [])
        self.assertEqual(after.tail, q.tail)
        self.assertEqual(after.common.metadata.to_bytes(), q.common.metadata.to_bytes())
        for layout in ([{"source": 0, "threshold": 1}, {"source": 1, "threshold": 1.00000001}],
                       [{"source": 0, "images": [False]}], [{"source": True}]):
            with self.assertRaises(ValueError):
                cp.edit(source, {"state_layout": layout})

    def test_unknown_tail_only_accepts_existing_threshold_sequence(self):
        source = states()
        with self.assertRaises(ValueError):
            cp.edit(source, {"state_layout": [{"source": 0}]})
        source.type_id = 0x5028
        with self.assertRaises(ValueError):
            cp.edit(source, {"state_layout": [{"source": 0}]})
        after = MultiState.parse(cp.edit(source, {"state_layout": [
            {"source": 0}, {"source": 1, "texts": []}, {"source": 2}]}))
        self.assertEqual(after.texts[1], [])

    def test_button_layout_preserves_independently_observed_action_suffix(self):
        q = MultiState.parse(states())
        q.common.record.type_id = 0x5028
        action = struct.pack("<10I", 0, 0, 0, 0x3f800000, 0x42c80000, 0, 5, 1, 0, 1) + write_cstring("") + bytes(10)
        self.assertTrue(digest(action).startswith("54d3a59ad1aa"))
        q.tail = (write_cstring("Read") + bytes(16) + write_cstring("Write") + bytes(16) + action)
        changed = MultiState.parse(cp.edit(q.to_record(), {"state_layout": [{"source": 1}]}))
        self.assertEqual(changed.levels, [1.0])
        self.assertEqual(changed.tail, q.tail)

    def test_create_and_clone_multistate_in_both_families(self):
        import mcgs_file as project
        from 原生界面样式 import MultiButtonTail, GenericMetadata
        for family in ("Stu", "Pro"):
            presets = project.load_factory_asset("primitives", family)
            variables = {"Flag": {"id": 145, "kind": 1}, "Action": {"id": 322, "kind": 2}}
            for typ in ("multi-state-button", "multi-state-display"):
                item = {"type": typ, "name": "First", "bounds": [1, 2, 121, 42], "binding": "Flag",
                        "state_layout": [{"source": 0}, {"source": 1}, {"source": 1, "threshold": 2}],
                        "state_edits": [{"state": 2, "texts": [{"child": 0, "text": "Third"}]}]}
                if typ == "multi-state-button":
                    item["write_binding"] = "Action"
                kind, payload = factory.make_control(item, variables, presets)
                rec = factory.record(kind, payload)
                state = MultiState.parse(rec)
                self.assertEqual(state.texts[2][0].caption.value, "Third")
                self.assertEqual(state.common.rect, tuple(item["bounds"]))
                self.assertFalse(GenericMetadata.parse(state.common.metadata.value).events)
                if typ == "multi-state-button":
                    tail = MultiButtonTail.parse(state.tail)
                    self.assertEqual((tail.input_expression.value, tail.input_words), ("Flag", [145, 0, 1, 0]))
                    self.assertEqual((tail.output_expression.value, tail.output_words), ("Action", [322, 0, 2, 0]))
                else:
                    r = Reader(state.tail)
                    self.assertEqual((r.u32(), r.cstring()[0]), (0, "Flag"))
                page = {"id": 1, "controls": [rec]}
                clone = {"type": typ, "name": "Second", "bounds": [5, 4, 125, 44],
                         "clone_from": {"page_id": 1, "path": [0], "name": "First", "kind": kind, "sha256": digest(payload)}}
                ck, cb = factory.make_control(clone, variables, presets, [page])
                result = MultiState.parse(factory.record(ck, cb))
                self.assertEqual(result.tail, state.tail)
                self.assertEqual(result.levels, state.levels)
                self.assertEqual(result.common.name.value, "Second")
                with self.assertRaisesRegex(ValueError, "existing Boolean or numeric"):
                    factory.make_control({**item, "binding": "Missing"}, variables, presets)

    def test_state_indexes_and_unknown_properties_rejected(self):
        for edits in ([{'state':True,'fill':1}],[{'state':3,'fill':1}],
                      [{'state':0,'fill':1},{'state':0,'fill':2}],
                      [{'state':0,'texts':[{'child':1,'text':'bad'}]}],
                      [{'state':0,'texts':[{'child':0,'color':-1}]}],
                      [{'state':0,'threshold':7}]):
            with self.subTest(edits=edits),self.assertRaises(ValueError):cp.edit(states(),{'state_edits':edits})

    def test_state_picture_reference_and_embedded_raster(self):
        original=states();before=MultiState.parse(original)
        for kind in ('BMP','PNG','JPEG'):
            payload=raster(kind)
            changed=cp.edit(original,{'state_edits':[{'state':2,'images':[{'child':0,'picture':{'embedded_hex':payload.hex()}}]}]})
            after=MultiState.parse(changed);p=Picture.parse(after.images[2][0].picture)
            self.assertEqual((p.width,p.height,p.payload),(2,3,payload))
            self.assertEqual(after.texts,before.texts)
            self.assertEqual(after.images[0][0].to_bytes(),before.images[0][0].to_bytes())
        with self.assertRaises(ValueError):cp.edit(original,{'state_edits':[{'state':0,'images':[{'child':0,'picture':{'reference':'Missing'}}]}]},picture_references={'Picture1'})
        changed=cp.edit(original,{'state_edits':[{'state':0,'images':[{'child':0,'picture':{'reference':'Picture2'}}]}]},picture_references={'Picture1','Picture2'})
        self.assertEqual(Picture.parse(MultiState.parse(changed).images[0][0].picture).reference.value,'Picture2')

    def test_button_picture_slot_preserves_actions_and_other_slot(self):
        original=factory.primitive_record('button');q=ButtonArchive.parse(original)
        q.release_script.value='Flag=1';q.metadata.properties.press_script.value='Flag=0'
        q.metadata.properties.words[16]=1
        q.metadata.properties.picture=struct.pack('<I',128)+write_cstring('Picture1')
        original.payload=q.to_bytes();before=original.payload
        changed=cp.edit(original,{'button_pictures':{'properties':{'embedded_hex':raster().hex()}}})
        after=ButtonArchive.parse(changed)
        self.assertEqual(after.picture,q.picture);self.assertEqual(after.release_script.value,'Flag=1')
        self.assertEqual(after.metadata.properties.press_script.value,'Flag=0')
        after.metadata.properties.picture=q.metadata.properties.picture
        self.assertEqual(after.to_bytes(),before)

    def test_valid_raster_above_16_megapixels_has_no_product_gate(self):
        # Actual compressed PNG, just above the removed arbitrary pixel cap.
        payload=raster('PNG',(8192,2049))
        details=raster_details(payload)
        self.assertEqual((details['width'],details['height']),(8192,2049))

    def test_unknown_embedded_payload_is_preserved_but_not_decoded(self):
        raw=struct.pack('<4I',2,10,20,7)+b'unknown'
        self.assertEqual(Picture.parse(raw).to_bytes(),raw)
        with self.assertRaises((ValueError,OSError)):replace_picture(raw,{'embedded_hex':b'unknown'.hex()})
        with self.assertRaises(ValueError):Picture.parse(raw[:-1])

    def test_raster_resource_dimensions_identity_and_unknown_rejection(self):
        q=PictureResource(string('Existing'),string('id'),2,2,3,raster())
        before=q.to_bytes();q.replace_raster(raster('PNG',(5,7)))
        after=PictureResource.parse(q.to_bytes())
        self.assertEqual((after.width,after.height),(5,7))
        self.assertEqual(after.name.value,'Existing');self.assertEqual(after.identity.value,'id')
        old=PictureResource.parse(before);old.payload=b'VSopaque'
        self.assertEqual(PictureResource.parse(old.to_bytes()).payload,b'VSopaque')
        with self.assertRaises((ValueError,OSError)):old.replace_raster(raster())
        with self.assertRaises(ValueError):raster_details(raster()+b'junk')
        with self.assertRaises(ValueError):PictureResource.parse(before+b'junk')

    def test_kind_zero_bitmap_replacement_preserves_exact_original_routing(self):
        canonical = PictureResource.from_raster('Existing bitmap', raster('BMP'))
        original = canonical.to_bytes()
        with self.assertRaisesRegex(ValueError, 'standard 24-bit BMP'):
            canonical.replace_raster(raster('PNG'))
        self.assertEqual(canonical.to_bytes(), original)
        new_payload = raster('BMP', (5, 7))
        canonical.replace_raster(new_payload)
        after = PictureResource.parse(canonical.to_bytes())
        self.assertEqual((after.kind, after.width, after.height, after.payload), (0, 5, 7, new_payload))
        for field in ('name', 'identity'):
            self.assertEqual(getattr(after, field).to_bytes(),
                             getattr(PictureResource.parse(original), field).to_bytes())
        legacy = PictureResource(string('Legacy bitmap'), string('legacy-id'), 2, 2, 3, raster('BMP'))
        legacy.replace_raster(new_payload)
        self.assertEqual((legacy.kind, legacy.identity.value, legacy.payload), (2, 'legacy-id', new_payload))

    def test_vector_edit_preserves_allocation_padding_and_other_child(self):
        q=vector_resource();before=q.to_bytes();g,end=q.vector();first=g.children[0];other=g.children[1].to_bytes()
        q.edit_vector([{'path':[0],'sha256':digest(first.payload),'edits':{'fill':0x445566}}])
        after,afterend=q.vector()
        self.assertEqual(end,afterend);self.assertEqual(after.children[1].to_bytes(),other)
        self.assertEqual(q.payload[end:],PictureResource.parse(before).payload[end:])
        self.assertEqual(q.payload[:87],PictureResource.parse(before).payload[:87])
        cp.replace_path(after.children,[0],first)
        self.assertEqual(after.to_record().payload,g.to_record().payload)
        self.assertEqual(len(q.to_bytes()),len(before))
        with self.assertRaises(ValueError):q.edit_vector([{'path':[0],'sha256':'0'*64,'edits':{'fill':0}}])
        malformed=PictureResource.parse(before);malformed.payload=malformed.payload[:58]+struct.pack('<I',2**32-1)+malformed.payload[62:]
        with self.assertRaises(ValueError):malformed.vector()

    def test_stu_vector_preserves_exact_root_tail(self):
        metadata_suffix=struct.pack('<I',10000)
        tail=bytes(12)
        q=vector_resource(metadata_suffix,tail)
        before=PictureResource.parse(q.to_bytes())
        group,end=before.vector()
        original=group.children[0]
        self.assertEqual(group.tail,tail)
        self.assertEqual(group.to_record().payload,before.payload[87:end])
        q.edit_vector([{'path':[0],'sha256':digest(original.payload),'edits':{'fill':0x445566}}])
        after,after_end=q.vector()
        self.assertEqual(after_end,end)
        self.assertEqual(after.tail,tail)
        self.assertEqual(q.payload[end-12:],before.payload[end-12:])
        self.assertEqual(after.common.metadata.to_bytes(),group.common.metadata.to_bytes())
        after.children[0]=original
        self.assertEqual(after.to_record().payload,before.payload[87:end])
        for suffix,invalid_tail in ((metadata_suffix,b''),(metadata_suffix,bytes(11)),
                                    (metadata_suffix,bytes(13)),(metadata_suffix,bytes(11)+b'\x01'),
                                    (b'',tail),(struct.pack('<I',10001),tail)):
            with self.subTest(suffix=suffix,tail=invalid_tail):
                malformed=vector_resource(suffix,invalid_tail)
                raw=malformed.to_bytes()
                with self.assertRaisesRegex(ValueError,'VECT root'):
                    malformed.edit_vector([{'path':[0],'sha256':digest(original.payload),'edits':{'fill':1}}])
                self.assertEqual(malformed.to_bytes(),raw)

    def test_vector_bitmap_bounds_keep_the_complete_embedded_image(self):
        common = CommonEnvelope.parse(factory.primitive_record('rectangle'))
        common.record.type_id = 0x5009
        common.content = Picture(2, None, 46, 46, b'VS\x00\x00opaque-original-image').to_bytes()
        child = common.to_record()
        metadata_suffix = struct.pack('<I', 10000)
        for suffix, tail in ((b'', b''), (metadata_suffix, bytes(12))):
            with self.subTest(suffix=suffix):
                q = vector_resource(suffix, tail, child)
                before, end = q.vector()
                original = q.to_bytes()
                target = [888, 3633, 2375, 6387]
                changes = [{'path': [0], 'sha256': digest(child.payload), 'edits': {'bounds': target}}]
                q.edit_vector(changes)
                after, after_end = q.vector()
                expected = bytearray(child.payload)
                struct.pack_into('<4i', expected, common.rect_offset, *target)
                self.assertEqual(after.children[0].payload, bytes(expected))
                self.assertEqual(CommonEnvelope.parse(after.children[0]).content, common.content)
                self.assertEqual(after.children[1].to_bytes(), before.children[1].to_bytes())
                self.assertEqual((after_end, after.tail), (end, tail))
                self.assertEqual(q.payload[end:], PictureResource.parse(original).payload[end:])
                inverse = [{'path': [0], 'sha256': digest(expected), 'edits': {'bounds': list(common.rect)}}]
                q.edit_vector(inverse)
                self.assertEqual(q.to_bytes(), original)
        common.content = Picture(0x80, string('ExternallyBound')).to_bytes()
        linked = common.to_record()
        q = vector_resource(first_child=linked)
        with self.assertRaisesRegex(ValueError, 'native embedded image'):
            q.edit_vector([{'path': [0], 'sha256': digest(linked.payload), 'edits': {'bounds': [1, 2, 3, 4]}}])

    def test_vector_label_font_changes_only_a_fixed_size_native_font(self):
        from mcs_input_text import LabelRecord

        child = factory.primitive_record('label')
        source = LabelRecord.parse(CommonEnvelope.parse(child).project_without_animations())
        metadata_suffix = struct.pack('<I', 10000)
        for suffix, tail in ((b'', b''), (metadata_suffix, bytes(12))):
            with self.subTest(suffix=suffix):
                q = vector_resource(suffix, tail, child)
                initial = q.to_bytes()
                for edit in ({'text': 'New caption'}, {'font': {'family': 'Another face'}}):
                    with self.assertRaises(ValueError):
                        q.edit_vector([{'path': [0], 'sha256': digest(child.payload), 'edits': edit}])
                    self.assertEqual(q.to_bytes(), initial)
                q.edit_vector([{'path': [0], 'sha256': digest(child.payload),
                                'edits': {'font': {'height': 23, 'weight': 610, 'italic': True}}}])
                group, end = q.vector()
                updated = group.children[0]
                after = LabelRecord.parse(CommonEnvelope.parse(updated).project_without_animations())
                self.assertEqual(updated.payload, child.payload.replace(source.font, after.font, 1))
                self.assertEqual(len(after.font), len(source.font))
                self.assertTrue(all((f['height'],f['weight'],f['italic']) == (23,610,True) for f in fonts(after.font)))
                group.children[0] = child
                self.assertEqual(PictureResource.parse(initial).payload[87:end], group.to_record().payload)

    def test_resources_and_batch_share_manifest_preimages(self):
        q=vector_resource();raw=q.to_bytes();g,_=q.vector();key='MCGS_PICTURE_DATA_1'
        class Export:
            directory=Path('.')
            index={'sha256':'a'*64,'project_family':'Pro'}
            rows={('System',key):{}}
            fp={'fingerprints':{'System':{key:{'lbContext':f'binary:{len(raw)}:{digest(raw)}'}}}}
            def blob(self,table,row,field):return raw
        spec={'input_sha256':'a'*64,'resources':[{'key':key,'sha256':digest(raw),'edits':{'vector_children':[{'path':[0],'sha256':digest(g.children[0].payload),'edits':{'fill':123}}]}}]}
        # BatchExport normally verifies a real export. Seed its verified cache to
        # exercise the real resources dispatcher without any database provider.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);nt.save(root/'spec.json',spec)
            nt.save(root/'plan.json',{'input_sha256':'a'*64,'steps':[{'command':'resources','spec':'spec.json'}]})
            from unittest.mock import patch
            original=nt.BatchExport.__init__
            def init(view,export):
                original(view,export);view.verified[('System',key,'lbContext')]=raw
            with patch.object(nt.BatchExport,'__init__',init):
                proof=nt.batch_edit(Export(),root/'plan.json',root/'out')
            manifest=nt.load(root/'out/manifest.json')
            self.assertEqual(proof['fields'],1)
            self.assertEqual(manifest['operations'][0]['before'],Export.fp['fingerprints']['System'][key])
            self.assertFalse(proof['native_compile_verified'])


if __name__=='__main__':unittest.main()
