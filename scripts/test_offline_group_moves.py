"""Reference and geometry regressions for moving controls between native groups."""

import copy
import unittest

from test_offline_structure import controls, m, selector


def fixture():
    child = {'type': 'rectangle', 'name': 'TransferItem', 'bounds': [2500, 2500, 5000, 5000]}
    source = {'type': 'group', 'name': 'SourceGroup', 'bounds': [10, 20, 410, 420], 'children': [
        child, {**child, 'name': 'RemainHere', 'bounds': [0, 0, 2000, 2000]}]}
    nested = {'type': 'group', 'name': 'NestedGroup', 'bounds': [1250, 1250, 8750, 8750], 'children': [
        {**child, 'name': 'NestedMarker'}]}
    destination = {**source, 'name': 'DestGroup', 'children': [nested]}
    return [source, destination]


def move_spec(source, destination, index=0):
    return {'pages': [{'id': 1, 'group_operations': [{
        'action': 'move', 'source': [selector(row) for row in source],
        'destination': [selector(row) for row in destination], 'insert_at': index,
    }]}]}


class GroupMoves(unittest.TestCase):
    def test_nested_moves_preserve_page_geometry_and_rebuild_only_two_paths(self):
        for family in ('Stu', 'Pro'):
            with self.subTest(family=family):
                data = m.create_data({'pages': [{'name': 'Main', 'controls': fixture()}]}, family)
                before = copy.deepcopy(data)
                left, right = controls(data)
                item, stays = left['children']
                inner = right['children'][0]
                edit = move_spec([left, item], [right, inner])
                m.edit_data(data, edit)
                moved_left, moved_right = controls(data)
                moved_inner = moved_right['children'][0]
                moved, marker = moved_inner['children']
                self.assertEqual(moved_left['children'], [{**stays, 'index': 0}])
                self.assertEqual(marker, {**inner['children'][0], 'index': 1})
                self.assertEqual(moved['bounds'], [1667, 1667, 5000, 5000])
                self.assertEqual(moved['name'], item['name'])
                move_back = move_spec([moved_right, moved_inner, moved], [moved_left])
                m.edit_data(data, move_back)
                self.assertEqual(m.canonical(data), m.canonical(before))

    def test_move_checks_current_owners_and_unresolved_source_consumers(self):
        data = m.create_data({'pages': [{'name': 'Main', 'controls': fixture()},
                                         {'name': 'Other'}]}, 'Pro')
        left, right = controls(data)
        inner = right['children'][0]
        edit = move_spec([left, left['children'][0]], [right, inner])
        stale = copy.deepcopy(edit)
        stale['pages'][0]['group_operations'][0]['destination'][1]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
            m.edit_data(copy.deepcopy(data), stale)
        m.edit_data(data, {'pages': [{'id': 2, 'events': {'open': 'Main.SourceGroup.TransferItem=1'}}]})
        with self.assertRaisesRegex(ValueError, 'Referenced object'):
            m.edit_data(data, edit)


if __name__ == '__main__':
    unittest.main()
