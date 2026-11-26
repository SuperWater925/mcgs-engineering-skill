"""Pure scheduling and receipt regressions for same-page native clone batches."""
import sys
import hashlib
import json
import os
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
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
    import edit_batch_client as batch


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


class DirectRemainderTests(unittest.TestCase):
    def setUp(self):
        self.rename = {"action_id": "rename", "kind": "picture-rename",
                       "target": {"module_id": 11, "name": "A"}, "after": {"name": "B"}}
        self.root_save = {"action_id": "root", "kind": "root-flush", "target": {}, "after": {}}
        self.spec = {"commit": False, "actions": [
            {"action_id": "replace", "kind": "picture-replace", "target": {}, "after": {}},
            self.rename, self.root_save]}
        self.claim = {"execution_mode": "direct", "claim_call_entered": False,
                      "claim_completed_returned": False, "claim_state_ambiguous_or_partial_possible": False}
        self.receipt = {"ok": False, "execution_mode": "direct", "requested_action_count": 3,
                        "completed_action_count": 1, "failed_action_id": "rename",
                        "direct_action_results": [
                            {"action_id": "replace", "result": {"ok": True}},
                            {"action_id": "rename", "result": {"ok": False, "actions": [],
                                 "permit_status": self.claim, "write_attempted": True}}]}

    def test_draft_preserves_suffix_and_scope(self):
        corrected = dict(self.rename, after={"name": "B", "module_semantic": {"module_id": 11}})
        summary, remaining = batch.direct_remainder(self.spec, self.receipt, corrected)
        self.assertEqual(summary, {"completed_action_ids": ["replace"], "failed_action_id": "rename",
                                  "failed_before_action_claim": True, "unattempted_action_ids": ["root"]})
        self.assertEqual(remaining, {"actions": [corrected, self.root_save], "commit": False})
        self.assertEqual(self.spec["actions"][1], self.rename)
        with self.assertRaisesRegex(ValueError, "same failed action"):
            batch.direct_remainder(self.spec, self.receipt, dict(corrected, target={}))

    def test_no_draft_for_unverified_boundary_or_missing_dependency(self):
        self.claim["claim_call_entered"] = True
        summary, remaining = batch.direct_remainder(self.spec, self.receipt)
        self.assertFalse(summary["failed_before_action_claim"])
        self.assertIsNone(remaining)
        with self.assertRaisesRegex(ValueError, "may already have modified"):
            batch.direct_remainder(self.spec, self.receipt, self.rename)
        self.claim["claim_call_entered"] = False
        self.root_save["after"]["dep"] = {"$native_result": {"action_id": "replace", "path": "/apply"}}
        with self.assertRaisesRegex(ValueError, "outside the remaining actions"):
            batch.direct_remainder(self.spec, self.receipt, self.rename)
        self.root_save["after"]["dep"]["$native_result"]["action_id"] = "rename"
        self.assertIsNotNone(batch.direct_remainder(self.spec, self.receipt, self.rename)[1])
        self.receipt["native_batch_finalization_failed"] = True
        with self.assertRaisesRegex(ValueError, "grouped results"):
            batch.direct_remainder(self.spec, self.receipt, self.rename)
        del self.receipt["native_batch_finalization_failed"]
        self.receipt["direct_action_results"][0]["action_id"] = "root"
        with self.assertRaisesRegex(ValueError, "differ from the submitted prefix"):
            batch.direct_remainder(self.spec, self.receipt, self.rename)

    def test_pending_queue_never_reads_or_writes_a_spec(self):
        with patch.object(batch, "read_existing_result", return_value={"ok": False,
                          "status": "no_correlated_response_yet", "automatic_retry": False}), \
                patch.object(batch, "load_client") as load_client:
            report = batch.plan_remainder("original", "0" * 64, "replacement.json", "output.json")
        self.assertEqual(report["status"], "no_correlated_response_yet")
        self.assertFalse(report["host_invoked"])
        load_client.assert_not_called()

    def test_exact_original_bytes_and_exclusive_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            specification = root / "original.json"
            spec_bytes = json.dumps(self.spec).encode()
            specification.write_bytes(spec_bytes)
            replacement = root / "replacement.json"
            replacement.write_text(json.dumps(self.rename), encoding="utf-8")
            output = root / "out.json"
            project = str(root / "sample.MCP")
            request = {"request_id": "original", "op": "engineering-edit-batch",
                       "engineering_delivery_scope_sha256": "bound", "expected_project": project,
                       "specification_file": str(specification),
                       "specification_sha256": hashlib.sha256(spec_bytes).hexdigest()}
            payload = json.dumps(request).encode()
            digest = hashlib.sha256(payload).hexdigest()
            self.receipt.update(op=request["op"], engineering_delivery_scope_sha256="bound",
                                actual_project=project, queue_claim_token="done")
            claim = {"request_id": "original", "request_sha256": digest, "status": "completed",
                     "response_published": True, "claim_token": "done"}
            transport = SimpleNamespace(_paths=lambda path, key: {"processed": "raw", "claims": "claim"},
                                        _read=lambda path, limit: payload, _json=lambda path: claim)
            with patch.object(batch, "read_existing_result", return_value={"ok": True, "result": self.receipt}), \
                    patch.object(batch, "load_client", return_value=transport), \
                    patch.multiple(batch, TASK=root, RUNTIME=root, _LAYOUT=SimpleNamespace(configuration_sha256="bound")):
                report = batch.plan_remainder("original", digest, replacement, output)
                self.assertEqual(report["status"], "remainder_specification_written")
                self.assertFalse(report["host_invoked"])
                self.assertEqual(json.loads(output.read_bytes())["actions"], [self.rename, self.root_save])
                with self.assertRaises(FileExistsError):
                    batch.plan_remainder("original", digest, replacement, output)
                specification.write_bytes(spec_bytes + b" ")
                with self.assertRaisesRegex(ValueError, "Original specification bytes"):
                    batch.plan_remainder("original", digest)
                claim["response_published"] = False
                with self.assertRaisesRegex(ValueError, "claim does not confirm"):
                    batch.plan_remainder("original", digest)


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



def csharp_method(source, name):
    """Extract the actual production method, retaining its executable body."""
    match = re.search(r"(?m)^\s*(?:internal |public )?static [^\r\n]+?\b" + re.escape(name) +
                      r"(?:<[^\r\n]+?>)?\(", source)
    if match is None:
        match = re.search(r"(?m)^\s*internal [^\r\n]+?\b" + re.escape(name) + r"\(", source)
    if match is None:
        raise AssertionError("Missing production method: " + name)
    opening = source.index("{", match.end())
    depth = 0
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/|[{}]',
                         source[opening:], re.S)
    for token in tokens:
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():opening + token.end()]
    raise AssertionError("Unclosed production method: " + name)


class NativeCloneImplementationTests(unittest.TestCase):
    """Run production scheduling/partial-refresh methods in a managed-only host."""
    @classmethod
    def setUpClass(cls):
        candidates = [shutil.which("csc"), str(Path(os.environ.get("WINDIR", "C:/Windows")) /
                      "Microsoft.NET/Framework/v4.0.30319/csc.exe")]
        compiler = next((path for path in candidates if path and Path(path).is_file()), None)
        if compiler is None:
            if os.environ.get("CI"):
                raise AssertionError("Windows CI must provide the .NET Framework C# compiler")
            raise unittest.SkipTest("Managed implementation fixture needs the .NET Framework C# compiler")
        cls.temporary = TemporaryDirectory(prefix="mcgs-clone-contract-")
        cls.addClassCleanup(cls.temporary.cleanup)
        work = Path(cls.temporary.name)
        source_dir = Path(__file__).resolve().parents[1] / "assets/pro-native-bridge/delivery/source/sources"
        direct = (source_dir / "NativeEngineeringDirectExecution.cs").read_text(encoding="utf-8-sig")
        template = (source_dir / "NativeCurrentTemplateControlOperations.cs").read_text(encoding="utf-8-sig")
        collections = (source_dir / "NativeDynamicCollections.cs").read_text(encoding="utf-8-sig")
        methods = "\n".join(csharp_method(direct, name) for name in (
            "DirectBoolean", "DirectReference", "DirectCommit", "IsDirectClone", "TryClonePage",
            "DirectLegacyProjectionActions", "DirectCloneRunEnd"))
        iterators = "\n".join(csharp_method(collections, name) for name in (
            "DepthFirst", "ChildValues", "DictionaryValues"))
        partial = csharp_method(template, "RefreshPartial")
        host = r'''
using System;using System.Collections;using System.Collections.Generic;using System.Web.Script.Serialization;
static class NativeMemory {
 internal static int Serializer;
 internal static void Require(bool value,string reason){if(!value)throw new InvalidOperationException(reason);}
 internal static int I32(IntPtr p,int offset){return Serializer;}
}
static class NativeOperationTrace {internal static void BeforeMutation(string phase){}}
static class NativePageControlPreparation {
 internal static void Same(object a,object b,string message){NativeMemory.Require(new JavaScriptSerializer().Serialize(a)==new JavaScriptSerializer().Serialize(b),message);}
}
static class NativeDomainProjectCheck {internal const string Kind="project-check";}
static class NativeDynamicCollections { ITERATORS }
class BatchProbe {
 internal bool mutationUnverified,MutationEntered=true,Drift;
 internal int AppliedCount=1,RefreshCalls,ValidationCalls;
 internal IntPtr View=new IntPtr(1),Root=new IntPtr(2),Page=new IntPtr(3),Doc=new IntPtr(4);
 internal readonly Dictionary<string,object> initialPage=new Dictionary<string,object>{{"page_id",3},{"attributes",new object[0]},{"pages",new object[0]}};
 internal readonly List<object> expected=new List<object>();
 internal readonly FakeShared Shared=new FakeShared();internal readonly FakeTemplate Template=new FakeTemplate();
 internal Dictionary<string,object> IncompleteReport(object first,object last){return new Dictionary<string,object>();}
 internal void ValidateCurrent(){ValidationCalls++;}
 internal object SnapshotForest(FakeTemplate api,IntPtr doc,List<IntPtr> top){return Drift?(object)new[]{1}:(object)new object[0];}
 internal void invalidate(IntPtr view,int flag){RefreshCalls++;}internal void update(IntPtr view){RefreshCalls++;}
 internal class FakeShared {
  internal FakeShared Shared{get{return this;}}
  internal IntPtr RootDoc(){return new IntPtr(2);}internal IntPtr Document(IntPtr p,int id){return new IntPtr(4);}
  internal List<IntPtr> TopControls(IntPtr doc){return new List<IntPtr>();}
  internal int[] Attributes(IntPtr doc){return new int[0];}internal object[] PageRows(){return new object[0];}
 }
 internal class FakeTemplate {
  internal FakeTemplate Engine{get{return this;}}
  internal IntPtr Address(int rva){return new IntPtr(rva);}internal IntPtr View(IntPtr doc){return new IntPtr(1);}
 }
 PARTIAL
 internal object Run(){var result=RefreshPartial("first","failed");result["refresh_calls"]=RefreshCalls;result["validation_calls"]=ValidationCalls;return result;}
}
class Harness {
 static Dictionary<string,object> Map(object value){return(Dictionary<string,object>)value;}
 static string Kind(Dictionary<string,object> action){return Convert.ToString(action["kind"]);}
 // Persistence is not exercised by this clone-only managed fixture.
 static bool IsPersistence(string kind){return false;}
 METHODS
 static void Main(){var json=new JavaScriptSerializer();var request=json.Deserialize<Dictionary<string,object>>(Console.In.ReadToEnd());
  if(request.ContainsKey("refresh")){NativeMemory.Serializer=Convert.ToInt32(request["serializer"]);var batch=new BatchProbe{mutationUnverified=Convert.ToBoolean(request["pending"]),Drift=Convert.ToBoolean(request["drift"]),AppliedCount=Convert.ToInt32(request["applied"])};Console.Write(json.Serialize(batch.Run()));return;}
  var actions=new List<Dictionary<string,object>>();foreach(object value in(IEnumerable)request["actions"])actions.Add(Map(value));
  var affected=DirectLegacyProjectionActions(actions);var ends=new List<int>();for(int i=0;i<actions.Count;i++)ends.Add(DirectCloneRunEnd(request,actions,i,affected));
  Console.Write(json.Serialize(new Dictionary<string,object>{{"legacy",new List<string>(affected)},{"ends",ends}}));
 }
}
'''
        host = host.replace("ITERATORS", iterators).replace("PARTIAL", partial).replace("METHODS", methods)
        source = work / "CloneContractHost.cs"
        source.write_text(host, encoding="utf-8")
        cls.executable = work / "CloneContractHost.exe"
        built = subprocess.run([compiler, "/nologo", "/target:exe", "/reference:System.Web.Extensions.dll",
                                "/out:" + str(cls.executable), str(source)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stdout + built.stderr)

    def invoke(self, request):
        result = subprocess.run([str(self.executable)], input=json.dumps(request), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_old_forest_page_and_parent_projections_keep_single_action_contract(self):
        for pointer in ("/apply/forest_after/0/path", "/apply/page_after/top_level_controls", "/apply",
                        "/applies/0/forest_after", "/result/actions/0/apply/page_after", ""):
            with self.subTest(pointer=pointer):
                actions = [action("first"), action("second"), action("third"), action("fourth")]
                actions[-1]["after"]["legacy"] = {"$native_result": {"action_id": "second", "path": pointer}}
                result = self.invoke({"actions": actions})
                self.assertEqual(result["legacy"], ["second"])
                self.assertEqual(result["ends"], [0, 1, 3, 3])

    def test_local_result_dependencies_do_not_disable_shared_clone_baseline(self):
        actions = [action("first"), action("second"), action("third")]
        actions[1]["source"]["control_name"] = {"$native_result": {
            "action_id": "first", "path": "/apply/resulting_control/name"}}
        result = self.invoke({"actions": actions})
        self.assertEqual(result, {"legacy": [], "ends": [2, 2, 2]})

    def test_partial_refresh_skips_unknown_serializer_or_insertion_state(self):
        result = self.invoke({"refresh": True, "pending": True, "drift": False, "serializer": 0, "applied": 2})
        self.assertEqual(result["refresh_calls"], 0)
        self.assertEqual(result["validation_calls"], 0)
        self.assertTrue(result["partial_refresh_skipped"])

    def test_partial_refresh_requires_exact_verified_prefix_and_idle_serializer(self):
        for drift, serializer in ((True, 0), (False, 1)):
            result = self.invoke({"refresh": True, "pending": False, "drift": drift,
                                  "serializer": serializer, "applied": 2})
            self.assertEqual(result["refresh_calls"], 0)
            self.assertIn("partial_refresh_error", result)
        result = self.invoke({"refresh": True, "pending": False, "drift": False, "serializer": 0, "applied": 2})
        self.assertEqual(result["refresh_calls"], 2)
        self.assertTrue(result["verified_prefix_before_refresh"])
        self.assertTrue(result["partial_refresh_returned"])


if __name__ == "__main__":
    unittest.main()
