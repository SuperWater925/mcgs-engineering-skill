"""Pure scheduling and receipt regressions for same-page native clone batches."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets/pro-native-bridge/client"))
# These fixtures call pure grouping and receipt functions. Provide only the
# import-time layout attributes; no transport or Pro installation is loaded.
fixture_root = Path(__file__).resolve().parent
with patch("native_delivery_config.current", return_value=SimpleNamespace(
        task_root=fixture_root, runtime_root=fixture_root, working_root=fixture_root)):
    import engineering_session as session


def action(name, page=3, source_page=None, kind="control-template-clone", source_name="Template"):
    return {
        "action_id": name,
        "kind": kind,
        "target": {"page_id": page, "page_name": f"Page {page}"},
        "source": {"page_id": page if source_page is None else source_page,
                   "page_name": f"Page {page if source_page is None else source_page}",
                   "class": "CDrawButton", "control_name": source_name},
        "after": {"rectangle": [20, 30, 40, 50]},
    }


def step(name, **options):
    return {"step_id": name, "specification": {"actions": [action(name, **options)]}}


def native_row(name):
    return {
        "action_id": name,
        "result": {
            "ok": True,
            "actions": [{"apply": {"clone_batch_applied": True}}],
        },
    }


class CloneBatchSessionTests(unittest.TestCase):
    def test_adjacent_same_page_clones_share_rpc(self):
        steps = [step("first"), step("second"), step("other", page=4), step("cross", source_page=4)]
        group = session.next_direct_group(steps, 0, {})
        self.assertEqual([row["step"]["step_id"] for row in group], ["first", "second"])
        self.assertEqual(len(session.next_direct_group(steps, 0, {}, merge_steps=False)), 1)
        self.assertIsNone(session.merge_signature(steps[3], steps[3]["specification"]))

    def test_clone_source_can_reference_real_prior_receipt(self):
        first = step("first")
        second = step("second", source_name={"$ref": "/steps/first/apply/actions/0/apply/resulting_control/name"})
        group = session.next_direct_group([first, second], 0, {})
        self.assertEqual(len(group), 2)
        self.assertEqual(group[1]["specification"]["actions"][0]["source"]["control_name"], {
            "$native_result": {"action_id": "first", "path": "/apply/resulting_control/name"},
        })
        with self.assertRaisesRegex(ValueError, "earlier action"):
            session.validate_spec(group[1]["specification"])

    def test_result_reference_in_unrelated_source_is_rejected(self):
        other = action("other", kind="control-geometry", source_name={
            "$native_result": {"action_id": "first", "path": "/apply/resulting_control/name"},
        })
        with self.assertRaisesRegex(ValueError, "clone source"):
            session.validate_spec({"actions": [other]}, prior_native_ids=["first"])

    def test_identity_only_property_batch_keeps_exact_source_guards(self):
        def property_action(name, address):
            return {
                "action_id": name, "kind": "control-properties",
                "target": {"page_id": 3, "page_name": "Page 3", "control_name": name,
                           "rtti": ".?AVCDrawLabel@@", "complete": address, "native_id": 7},
                "after": {"properties": [{"native_key": "caption", "tag": 8, "value": name}]},
            }

        spec = {"actions": [property_action("first", "0x9000"), property_action("second", "0xA000")]}
        groups = session.coalesce_property_actions(spec)
        self.assertEqual(list(groups), ["first"])
        controls = spec["actions"][0]["after"]["controls"]
        self.assertEqual([row["target"]["complete"] for row in controls], ["0x9000", "0xA000"])
        self.assertTrue(all(row["target"]["native_id"] == 7 for row in controls))
        duplicate = {"actions": [property_action("first", "0xA000"), property_action("second", "0xa000")]}
        self.assertEqual(session.coalesce_property_actions(duplicate), {})

    def test_final_forest_only_in_final_derived_step(self):
        group = session.next_direct_group([step("first"), step("second")], 0, {})
        final = {"first_action_id": "first", "last_action_id": "second", "forest_after": [{"path": [4]}]}
        receipt = {"ok": True, "direct_action_results": [native_row("first"), native_row("second")],
                   "native_clone_batches": [final]}
        derived = session.split_direct_receipt(receipt, group)
        self.assertEqual([row[1] for row in derived], ["completed", "completed"])
        self.assertEqual(derived[0][3]["native_clone_batches"], [])
        self.assertEqual(derived[1][3]["native_clone_batches"], [final])

    def test_failed_clone_finalization_keeps_entire_scope_unverified(self):
        group = session.next_direct_group([step("first"), step("second"), step("tail")], 0, {})
        receipt = {
            "ok": False, "direct_action_results": [native_row("first"), native_row("second")],
            "native_batch_finalization_failed": True, "batch_finalization_action_id": "second",
            "incomplete_native_clone_batch": {"first_action_id": "first", "last_action_id": "second"},
        }
        derived = session.split_direct_receipt(receipt, group)
        self.assertEqual([row[1] for row in derived], ["partial", "failed", "not-executed"])
        self.assertTrue(derived[0][3]["native_result_may_be_partial"])
        self.assertIsNone(derived[2][3])


if __name__ == "__main__":
    unittest.main()
