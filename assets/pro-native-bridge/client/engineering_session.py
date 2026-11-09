"""Stage a complete change program, then execute in one existing Pro session.

This client performs engineering edits, not acceptance tests. It never opens or
closes a project, reruns a failed request, or resumes an ambiguous mutation.
Every dependent step gets a fresh native preimage in the same editor process.
"""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import uuid

import edit_batch_client as batch

from native_delivery_config import current as delivery_layout
_LAYOUT = delivery_layout()
ROOT = _LAYOUT.working_root
PURPOSE = "native-engineering-session-program"
NAME = re.compile(r"[A-Za-z0-9_-]{1,60}\Z")

# These adapters keep action order and use fresh native targets inside one direct
# request. Creation appends roots; none changes page identity or control order.
# Keep unknown, layering, reference, persistence and editor-switch actions as
# boundaries rather than inferring compatibility from their names.
MERGE_KINDS = frozenset({"control-native-create", "control-geometry",
    "control-geometry-batch", "control-properties", "control-properties-batch"})
MAX_RPC_ACTIONS = 8
MAX_RPC_SPEC_BYTES = 8 * 1024 * 1024


def json_copy(value):
    require_json_value(value)
    return copy.deepcopy(value)


def require_json_value(value, ancestors=None):
    """Keep the JSON value contract without serializing merely to clone it."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) not in (dict, list):
        raise ValueError("Expected a finite JSON-representable value")
    ancestors = set() if ancestors is None else ancestors
    if id(value) in ancestors:
        raise ValueError("Cyclic values are not JSON-representable")
    ancestors.add(id(value))
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        children = value.values()
    else:
        children = value
    for child in children:
        require_json_value(child, ancestors)
    ancestors.remove(id(value))


def encoded_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def encoded_size(value):
    # write_new uses indented JSON. Measure those actual file bytes for the
    # configurable merge budget; this is not a native action-count capacity.
    return len(encoded_json(value))


class BackgroundWriter:
    """Bounded derived-file writes; every error is observed before success.

    Submitted objects become read-only to the caller. Unique RPC originals and
    submission records are not sent here: they retain synchronous fsync.
    """
    def __init__(self, workers):
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="engineering-io")
        self.pending = deque()
        self.limit = max(8, workers * 2)
        self.paths = set()
        self.errors = []
        self.submitted = self.max_pending = 0

    def check(self):
        while self.pending and self.pending[0].done():
            self._observe(self.pending.popleft())
        if self.errors:
            raise self.errors[0]

    def _observe(self, future):
        try:
            future.result()
        except Exception as error:
            self.errors.append(error)

    def submit(self, path, value=None, encoded=None):
        self.check()
        path = Path(path)
        if path in self.paths:
            raise FileExistsError("A derived output path was already scheduled: " + str(path))
        while len(self.pending) >= self.limit:
            self._observe(self.pending.popleft())
            self.check()
        self.paths.add(path)
        if encoded is None:
            future = self.executor.submit(batch.write_new, path, value, durable=False)
        else:
            future = self.executor.submit(batch.write_new_bytes, path, encoded, durable=False)
        self.pending.append(future)
        self.submitted += 1
        self.max_pending = max(self.max_pending, len(self.pending))
        return future

    def drain(self):
        while self.pending:
            self._observe(self.pending.popleft())
        self.executor.shutdown(wait=True)
        if self.errors:
            raise self.errors[0]


def prepare_group_data(steps, start, results, merge_steps, max_merged_actions):
    members = next_direct_group(steps, start, results, merge_steps, max_merged_actions)
    for member in members:
        specification = member["specification"]
        if member["step"].get("mode", "edit") != "inspect":
            specification["trial_id"] = str(uuid.uuid4())
        member["encoded"] = encoded_json(specification)
        member["sha256"] = hashlib.sha256(member["encoded"]).hexdigest()
    read_only = members[0]["step"].get("mode", "edit") == "inspect"
    group_spec = group_encoded = group_sha = None
    property_batches = {}
    if not read_only:
        group_spec = {key: copy.deepcopy(value) for key, value in members[0]["specification"].items() if key != "actions"}
        group_spec["actions"] = [copy.deepcopy(action) for member in members for action in member["specification"]["actions"]]
        property_batches = coalesce_property_actions(group_spec)
        group_spec["trial_id"] = str(uuid.uuid4())
        group_encoded = encoded_json(group_spec)
        group_sha = hashlib.sha256(group_encoded).hexdigest()
        if len(members) > 1 and len(group_encoded) > MAX_RPC_SPEC_BYTES:
            raise ValueError("Prepared merged specification exceeds its grouping byte budget")
    return {"members": members, "end": start + len(members), "read_only": read_only,
        "group_spec": group_spec, "group_encoded": group_encoded, "group_sha256": group_sha, "property_batches": property_batches,
        "prepared_thread_id": threading.get_ident()}


class PreparationPipeline:
    """Prefetch only a bounded same-page segment with no result references.

    Workers encode JSON only. They never write files, read native state, or
    publish requests. A speculative error is raised only at its original step.
    """
    def __init__(self, steps, workers, merge_steps, max_merged_actions):
        self.steps, self.merge_steps, self.max_actions = steps, merge_steps, max_merged_actions
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="engineering-prepare") if workers else None
        self.pending, self.cached = deque(), {}
        self.window = max(1, workers * 2)
        self.background_chunks = self.background_groups_used = 0

    def get(self, index, results):
        if index not in self.cached and self.pending and self.pending[0][0] == index:
            _, _, future = self.pending.popleft()
            self.cached.update(future.result())
        if index in self.cached:
            value = self.cached.pop(index)
            if isinstance(value, Exception):
                raise value
            self.background_groups_used += 1
            return value
        return prepare_group_data(self.steps, index, results, self.merge_steps, self.max_actions)

    def _chunk(self, start, end):
        prepared = {}
        while start < end:
            try:
                value = prepare_group_data(self.steps[:end], start, {"steps": {}}, self.merge_steps, self.max_actions)
                prepared[start] = value
                start = value["end"]
            except Exception as error:
                prepared[start] = error
                break
        return prepared

    def schedule_after(self, current):
        if self.executor is None or current["read_only"]:
            return
        signature = merge_signature(current["members"][0]["step"], current["members"][0]["specification"])
        if signature is None:
            return
        start = current["end"]
        for value in self.cached.values():
            if not isinstance(value, Exception):
                start = max(start, value["end"])
        if self.pending:
            start = max(start, self.pending[-1][1])
        limit = MAX_RPC_ACTIONS if self.max_actions is None else self.max_actions
        while len(self.pending) < self.window and start < len(self.steps):
            end, count, ids = start, 0, set()
            while end < len(self.steps):
                step = self.steps[end]
                spec = step["specification"]
                if any(references(spec)) or merge_signature(step, spec) != signature:
                    break
                action_ids = {row["action_id"] for row in spec["actions"]}
                if end > start and (not self.merge_steps or count + len(action_ids) > limit or ids & action_ids):
                    break
                count += len(action_ids)
                ids.update(action_ids)
                end += 1
                if not self.merge_steps:
                    break
            if end == start:
                break
            future = self.executor.submit(self._chunk, start, end)
            self.pending.append((start, end, future))
            self.background_chunks += 1
            start = end

    def close(self):
        if self.executor is not None:
            self.executor.shutdown(wait=True, cancel_futures=True)


def persistence_deferred(specification):
    scope = specification.get("save_scope", {})
    return (specification.get("commit", False) is False and isinstance(scope, dict)
            and scope.get("root_save", False) is False and specification.get("root_save", False) is False)


def merge_signature(step, specification):
    if step.get("mode", "edit") != "edit" or not persistence_deferred(specification):
        return None
    pages = set()
    for action in specification["actions"]:
        page = action["target"].get("page_id")
        if action["kind"] not in MERGE_KINDS or type(page) is not int:
            return None
        pages.add(page)
        # Do not combine an adapter payload that also names another page.
        def same_page(value):
            if isinstance(value, dict):
                return ("page_id" not in value or value["page_id"] == page) and all(same_page(v) for v in value.values())
            return not isinstance(value, list) or all(same_page(v) for v in value)
        if not same_page(action):
            return None
    if len(pages) != 1:
        return None
    metadata = {key: value for key, value in specification.items() if key not in ("actions", "trial_id")}
    return (next(iter(pages)), json.dumps(metadata, ensure_ascii=False, sort_keys=True, allow_nan=False))


def native_save_step(step, specification):
    """Only group explicit saves whose native direct scope is set by the kind."""
    if (step.get("mode", "edit") != "edit"
            or set(specification) - {"actions", "commit", "save_scope", "trial_id"}
            or len(specification["actions"]) != 1):
        return None
    scope = specification.get("save_scope", {})
    if (not isinstance(scope, dict) or set(scope) - {
            "root_save", "affected_page_ids", "strategy_ids", "module_ids",
            "created_page_actions", "created_strategy_actions", "main_control_document", "linguist_document"}
            or type(scope.get("root_save", False)) is not bool):
        return None
    action = specification["actions"][0]
    if set(action) != {"action_id", "kind", "target", "after"} or action["after"]:
        return None
    target = action["target"]
    if (action["kind"] == "page-flush" and not scope.get("root_save")
            and set(target) == {"page_id", "page_name"}
            and type(target["page_id"]) is int and isinstance(target["page_name"], str) and target["page_name"]):
        return "page-flush"
    if action["kind"] == "root-flush" and not target:
        return "root-flush"
    return None


def next_direct_group(steps, start, results, merge_steps=True, max_merged_actions=None):
    """Resolve only completed dependencies; never send a client $ref to native."""
    limit = MAX_RPC_ACTIONS if max_merged_actions is None else max_merged_actions
    members, signature, ids, action_count = [], None, set(), 0
    saving = False
    action_bytes, metadata_bytes = 0, None
    for index in range(start, len(steps)):
        step = steps[index]
        # A prior step in this prospective RPC has no receipt yet. Finish that
        # RPC first, then resolve it locally with the original JSON pointer.
        if any(parts[1] in {row["step"]["step_id"] for row in members}
               for parts in references(step["specification"])):
            break
        try:
            specification = resolve(step["specification"], results)
            validate_spec(specification, step.get("mode", "edit") == "inspect")
        except Exception:
            if members:
                # Preserve the original sequential failure boundary: a later
                # bad pointer must not prevent an earlier valid step executing.
                break
            raise
        save_kind = native_save_step(step, specification)
        if not members:
            saving = save_kind == "page-flush"
        current = merge_signature(step, specification) if not saving else save_kind
        current_ids = {action["action_id"] for action in specification["actions"]}
        compatible = (save_kind is not None if saving else signature is not None and current == signature)
        if members and (not merge_steps or not compatible or ids & current_ids):
            break
        # Encode each new action once for an exact pretty-JSON byte estimate;
        # do not repeatedly encode the growing prefix. In the group array every
        # action line is indented four additional ASCII spaces.
        new_bytes = 0
        for action in specification["actions"]:
            data = encoded_json(action)[:-1]
            new_bytes += len(data) + 4 * (data.count(b"\n") + 1)
        if metadata_bytes is None:
            metadata_bytes = encoded_size(dict(specification, actions=[], trial_id="00000000-0000-0000-0000-000000000000"))
        candidate_count = action_count + len(specification["actions"])
        candidate_bytes = metadata_bytes + action_bytes + new_bytes + 2 * candidate_count + 2
        if members and (candidate_count > limit or candidate_bytes > MAX_RPC_SPEC_BYTES):
            break
        members.append({"index": index, "step": step, "specification": specification,
                        "action_offset": action_count, "action_count": len(specification["actions"])})
        action_count += len(specification["actions"])
        action_bytes += new_bytes
        ids.update(current_ids)
        signature = current
        if not merge_steps or signature is None or saving and save_kind == "root-flush":
            break
    return members


PROPERTY_BATCH_KIND = "control-properties-batch"
PROPERTY_PAGE_KEYS = ("page_id", "page_name")
PROPERTY_CONTROL_KEYS = ("control_name", "rtti", "control_path", "component_path")


def property_batch_page(action):
    if action["kind"] != "control-properties" or set(action) != {"action_id", "kind", "target", "after"}:
        return None
    target, after = action["target"], action["after"]
    if (not set(target) <= set(PROPERTY_PAGE_KEYS + PROPERTY_CONTROL_KEYS)
            or type(target.get("page_id")) is not int
            or any(not isinstance(target.get(key), str) or not target[key] for key in ("page_name", "control_name", "rtti"))
            or ("component_path" in target and not isinstance(target["component_path"], list))):
        return None
    path = target.get("control_path")
    if not isinstance(path, list) or not path or any(type(index) is not int or index < 0 for index in path):
        return None
    if set(after) != {"properties"} or not isinstance(after["properties"], list) or not after["properties"]:
        return None
    return tuple(target[key] for key in PROPERTY_PAGE_KEYS)


def property_control_target(action):
    return {key: action["target"][key] for key in PROPERTY_CONTROL_KEYS if key in action["target"]}


def coalesce_property_actions(specification):
    """Compile contiguous, independent property edits to the existing native batch."""
    if not persistence_deferred(specification) or not specification.get("coalesce_native_properties", True):
        return {}
    actions = specification["actions"]
    wire, batches = [], {}
    start = 0
    while start < len(actions):
        first = actions[start]
        page = property_batch_page(first)
        end = start + 1
        if page is not None:
            paths = {tuple(first["target"]["control_path"])}
            while end < len(actions) and property_batch_page(actions[end]) == page:
                path = tuple(actions[end]["target"]["control_path"])
                if path in paths:
                    break
                paths.add(path)
                end += 1
        if end == start + 1:
            wire.append(first)
        else:
            members = actions[start:end]
            identifier = first["action_id"]
            batches[identifier] = members
            wire.append({"action_id": identifier, "kind": PROPERTY_BATCH_KIND,
                         "target": dict(zip(PROPERTY_PAGE_KEYS, page)),
                         "after": {"controls": [{"target": property_control_target(member),
                                                  "properties": member["after"]["properties"]}
                                                 for member in members]}})
        start = end
    specification["actions"] = wire
    return batches


def check_direct_prefix(rows, expected, results=False):
    if not isinstance(rows, list) or len(rows) > len(expected):
        raise ValueError("Native direct prefix has an invalid length")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("action_id") != expected[index]:
            raise ValueError("Native direct prefix differs from submitted order")
        if results:
            if not isinstance(row.get("result"), dict):
                raise ValueError("Native direct action lacks a result object")
            if row["result"].get("ok") is not True and index != len(rows) - 1:
                raise ValueError("Native direct result continued after a failed action")


def property_snapshots(snapshot, originals):
    rows = snapshot.get("controls")
    if not isinstance(rows, list) or len(rows) != len(originals):
        raise ValueError("Native property batch snapshot has an invalid control count")
    common = {key: snapshot[key] for key in ("abi_profile_sha256", "page", "root_modified", "compile_valid")}
    output = []
    for row, original in zip(rows, originals):
        if not isinstance(row, dict) or row.get("target") != property_control_target(original):
            raise ValueError("Native property batch snapshot differs from submitted control order")
        output.append({**common, **{key: row[key] for key in ("control", "selected_owner", "properties")}})
    return output


def expand_property_batch_receipt(receipt, wire_actions, batches):
    """Project verified native outcomes to the original action IDs for session references."""
    if not batches:
        return receipt
    expected = [action["action_id"] for action in wire_actions]
    raw_results = receipt.get("direct_action_results", [])
    check_direct_prefix(raw_results, expected, results=True)
    expanded = dict(receipt)
    individual, preimages = [], []
    inspection = receipt.get("direct_inspection")
    captured_batches = set()
    if isinstance(inspection, dict):
        raw_preimages = inspection.get("action_preimages", [])
        check_direct_prefix(raw_preimages, expected)
        for row in raw_preimages:
            originals = batches.get(row["action_id"])
            if originals is None:
                preimages.append(row)
                continue
            for original, snapshot in zip(originals, property_snapshots(row["before"], originals)):
                preimages.append({**row, "action_id": original["action_id"], "kind": original["kind"],
                                  "target": original["target"], "before": snapshot})
            captured_batches.add(row["action_id"])
        expanded["direct_inspection"] = {**inspection, "action_preimages": preimages}
    for row in raw_results:
        originals = batches.get(row["action_id"])
        if originals is None:
            individual.append(row)
            continue
        outcome = row["result"]
        provenance = {"native_action_id": row["action_id"],
                      "action_ids": [original["action_id"] for original in originals]}
        if outcome.get("ok") is not True:
            individual.append({**row, "native_property_batch": provenance})
            if outcome.get("write_attempted") is not False:
                expanded["unverified_property_batch_action_ids"] = provenance["action_ids"]
            break
        reports = outcome["actions"]
        applied = [report["apply"] for report in reports
                   if report["unit"] == PROPERTY_BATCH_KIND and "apply" in report]
        if row["action_id"] not in captured_batches or len(applied) != 1 or applied[0].get("ok") is not True:
            raise ValueError("Successful native property batch lacks its preimage or one verified apply report")
        snapshots = property_snapshots(applied[0]["after"], originals)
        for index, (original, snapshot) in enumerate(zip(originals, snapshots)):
            native_apply = {"ok": True, "kind": original["kind"], "after": snapshot,
                            "native_getter_setter_used": True, "automatic_undo_redo_replay": False,
                            "original_history_store_projection": applied[0].get("original_history_store_projection"),
                            "full_persistence_acceptance_pending": True, "native_property_batch": provenance}
            # Shared native work is measured and counted once in the first projection.
            projected_reports = [{"unit": original["kind"], "apply": native_apply}]
            if index == 0:
                for key in ("original_history_captures", "native_refreshes"):
                    native_apply[key] = applied[0][key]
                projected_reports.extend(report for report in reports if "flush" in report)
            projected = {**row, "action_id": original["action_id"], "native_property_batch": provenance,
                         "result": {**outcome, "actions": projected_reports}}
            if index:
                projected.pop("timings_ms", None)
                projected["result"].pop("phase_timings_ms", None)
            if index != len(originals) - 1:
                projected["result"].pop("root_save", None)
            individual.append(projected)
    expanded["direct_action_results"] = individual
    return expanded


def split_direct_receipt(receipt, members):
    """Split a correlated native prefix without changing any per-step indices.

    Native direct_action_results is the authoritative sequential prefix. The
    first missing/failed action belongs to one failed step; later steps were not
    executed. A group finalization failure is conservatively assigned to the
    last step, even if all its individual actions returned successfully.
    """
    expected = [action["action_id"] for row in members for action in row["specification"]["actions"]]
    individual = receipt.get("direct_action_results", [])
    check_direct_prefix(individual, expected, results=True)
    successful = sum(row["result"].get("ok") is True for row in individual)
    complete = receipt.get("ok") is True
    if complete and (successful != len(expected) or len(individual) != len(expected)):
        raise ValueError("Successful native RPC lacks complete per-action results")
    first_failed = None if complete else min(successful, len(expected) - 1)
    finalization_failed = receipt.get("native_batch_finalization_failed") is True
    if finalization_failed:
        boundary_id = receipt.get("batch_finalization_action_id", receipt.get("failed_action_id"))
        if complete or not individual or successful != len(individual) or boundary_id != individual[-1]["action_id"]:
            raise ValueError("Native batch finalization failure does not identify its last successful action")
        # A factory sub-run can finalize before a later properties action in the
        # same RPC. That last factory step is partial; the next one was not run.
        first_failed = len(individual) - 1
    output = []
    parent_inspect = receipt.get("direct_inspection")
    preimages = parent_inspect.get("action_preimages", []) if isinstance(parent_inspect, dict) else []
    check_direct_prefix(preimages, expected)
    unverified = set(receipt.get("unverified_property_batch_action_ids", ()))
    for member in members:
        offset, count = member["action_offset"], member["action_count"]
        selected = individual[offset:offset + count]
        state = "completed" if first_failed is None or offset + count <= first_failed else "failed" if offset <= first_failed < offset + count else "not-executed"
        if state == "not-executed" and unverified.intersection(expected[offset:offset + count]):
            state = "partial"
        if state == "not-executed":
            output.append((member, state, None, None))
            continue
        apply = {key: json_copy(value) for key, value in receipt.items()
                 if key not in ("actions", "direct_action_results", "direct_inspection")}
        reports, flushes = [], []
        for row in selected:
            for report in row["result"].get("actions", []):
                (flushes if "flush" in report else reports).append(json_copy(report))
        apply.update(ok=state == "completed", actions=reports + flushes,
            direct_action_results=json_copy(selected), requested_action_count=count,
            completed_action_count=sum(row["result"].get("ok") is True for row in selected))
        # Top-level action-specific status must come from this step, never the
        # final action of another step sharing the RPC.
        for key in ("status", "root_save", "permit_status", "explicit_child_flushes_requested", "root_save_requested", "persistence_scope"):
            apply.pop(key, None)
            if selected and key in selected[-1]["result"]:
                apply[key] = json_copy(selected[-1]["result"][key])
        if state == "completed":
            for key in ("error", "managed_stack", "comparison_evidence", "failed_action_id", "owned_cleanup_error",
                        "native_abi", "failure_category", "affected_feature",
                        "native_batch_finalization_failed", "batch_finalization_action_id"):
                apply.pop(key, None)
            apply["phase"] = selected[-1]["result"].get("phase", "client-split-direct-step-completed")
            apply["native_result_may_be_partial"] = False
            apply["write_attempted"] = any(row["result"].get("write_attempted") is True for row in selected)
        else:
            apply["native_result_may_be_partial"] = True
            apply["group_finalization_failed"] = finalization_failed or successful == len(expected)
        inspect = None
        if isinstance(parent_inspect, dict):
            inspect = {key: json_copy(value) for key, value in parent_inspect.items() if key != "action_preimages"}
            inspect["action_preimages"] = json_copy(preimages[offset:offset + count])
            # New engines reuse the summary already captured for each action.
            # Never label the RPC's first summary as a later step's preimage.
            if selected and isinstance(selected[0].get("direct_summary"), dict):
                inspect["native_summary"] = json_copy(selected[0]["direct_summary"])
                digest = selected[0].get("direct_summary_utf8_sha256")
                if digest is not None:
                    inspect["native_summary_utf8_sha256"] = digest
                else:
                    inspect.pop("native_summary_utf8_sha256", None)
                inspect["native_summary_scope"] = ("shared-native-property-batch" if "native_property_batch" in selected[0]
                                                   else "this-step-first-action")
            elif offset:
                inspect.pop("native_summary", None)
                inspect.pop("native_summary_utf8_sha256", None)
                inspect["native_summary_scope"] = "unavailable-for-this-step"
            apply["direct_inspection"] = inspect
        output.append((member, state, inspect, apply))
    return output


def run_direct_program(program, manifest, directory, timeout, merge_steps=True, max_merged_actions=None,
                       prepare_workers=1, io_workers=1):
    results, identity = {"steps": {}}, None
    pending = {"page_ids": set(), "strategy_ids": set(), "unknown": False}
    status = {"ok": False, "session_id": manifest["session_id"], "completed_steps": [],
        "execution_mode": "direct", "approval_required": False, "automatic_retry": False,
        "automatic_resume": False, "project_open_close_operations": 0,
        "engineering_acceptance_verified": False, "rpc_count": 0, "merged_rpc_count": 0,
        "native_property_batches_submitted": 0, "native_save_groups_submitted": 0,
        "merge_compatible_steps": merge_steps,
        "max_merged_actions": MAX_RPC_ACTIONS if max_merged_actions is None else max_merged_actions}
    active_step, phase, members = None, "resolve-and-freeze", []
    writer = BackgroundWriter(io_workers)
    preparation = PreparationPipeline(program["steps"], prepare_workers, merge_steps, max_merged_actions)

    def journal(event, payload, critical=False):
        if critical:
            batch.write_new(directory / (event + ".json"), payload)
        else:
            writer.submit(directory / (event + ".json"), payload)
        print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)

    def prefix(member):
        return "%04d-%s" % (member["index"] + 1, member["step"]["step_id"])

    def check_identity(inspect):
        nonlocal identity
        values = tuple(inspect.get(key) for key in ("process_id", "creation_filetime", "native_thread_id", "actual_project", "editor_image_sha256"))
        if any(value is None for value in values):
            raise ValueError("Inspection is missing editor/project identity")
        if identity is None:
            identity = values
            journal("editor-identity", dict(zip(("process_id", "creation_filetime", "ui_thread_id", "project_path", "editor_image_sha256"), identity)))
        elif values != identity:
            raise ValueError("Editor, UI thread or project changed during the session")

    try:
        index = 0
        while index < len(program["steps"]):
            active_step = program["steps"][index]["step_id"]
            phase = "prepare-pure-json"
            writer.check()
            prepared = preparation.get(index, results)
            members = prepared["members"]
            phase = "freeze-prepared-json"
            for member in members:
                spec_file = directory / (prefix(member) + "-specification.json")
                if prepared["read_only"]:
                    batch.write_new_bytes(spec_file, member["encoded"])
                else:
                    writer.submit(spec_file, encoded=member["encoded"])
                member["spec_file"] = spec_file
                journal(prefix(member) + "-begin", {"step_id": member["step"]["step_id"],
                    "description": member["step"]["description"], "specification_sha256": member["sha256"],
                    "rpc_first_step": active_step, "rpc_action_offset": member["action_offset"],
                    "rpc_action_count": member["action_count"], "rpc_step_count": len(members)})
            read_only = prepared["read_only"]
            if read_only:
                phase = "inspect"
                status["rpc_count"] += 1
                member = members[0]
                inspect = batch.submit({"op": "engineering-edit-inspect", "expected_project": program["project_path"],
                    "inspection_file": str(member["spec_file"]), "inspection_sha256": member["sha256"]},
                    "eng_" + manifest["session_id"] + "_%04d_read" % index, timeout)
                writer.submit(directory / (prefix(member) + "-inspect.json"), inspect)
                if inspect.get("ok") is not True:
                    journal(prefix(member) + "-failed", {"step_id": active_step, "mode": "inspect", "edit_submitted": False})
                    raise RuntimeError("Native engineering inspection did not complete successfully")
                check_identity(inspect)
                results["steps"][active_step] = {"inspect": inspect}
                status["completed_steps"].append(active_step)
                journal(prefix(member) + "-complete", {"step_id": active_step, "ok": True, "mode": "inspect", "edit_submitted": False, "committed": False})
            else:
                request_id = "eng_" + manifest["session_id"] + "_%04d_direct" % index
                group_file = directory / (prefix(members[0]) + "-rpc-specification.json")
                batch.write_new_bytes(group_file, prepared["group_encoded"])
                group_record = {"schema": 1, "request_id": request_id, "specification_file": str(group_file),
                    "specification_sha256": prepared["group_sha256"], "steps": [{"step_id": member["step"]["step_id"],
                    "action_offset": member["action_offset"], "action_count": member["action_count"]} for member in members],
                    "automatic_retry": False, "automatic_resume": False}
                property_batches = prepared["property_batches"]
                if property_batches:
                    group_record["native_property_batches"] = {key: [action["action_id"] for action in actions]
                                                                 for key, actions in property_batches.items()}
                journal(prefix(members[0]) + "-rpc-begin", group_record, critical=True)
                preparation.schedule_after(prepared)
                writer.check()
                phase = "direct-execute"
                status["rpc_count"] += 1
                status["merged_rpc_count"] += len(members) > 1
                status["native_property_batches_submitted"] += len(property_batches)
                if len(members) > 1 and native_save_step(members[0]["step"], members[0]["specification"]) == "page-flush":
                    status["native_save_groups_submitted"] += 1
                try:
                    receipt = batch.execute(program["project_path"], group_file, request_id, timeout,
                                            specification_sha256=group_record["specification_sha256"])
                except Exception:
                    # A timeout/publication error may have executed any prefix.
                    # Leave every member unresolved, retain the request ID, stop.
                    status["ambiguous_steps"] = [member["step"]["step_id"] for member in members]
                    for member in members:
                        try:
                            journal(prefix(member) + "-partial", {"step_id": member["step"]["step_id"],
                                "request_id": request_id, "status": "execution-unknown-no-replay",
                                "execution_may_be_partial": True, "automatic_retry": False})
                        except Exception as io_error:
                            status.setdefault("background_io_errors", []).append(str(io_error))
                    raise
                receipt_file = directory / (prefix(members[0]) + "-rpc-response.json")
                receipt_sha = batch.write_new(receipt_file, receipt)
                phase = "split-direct-response"
                receipt = expand_property_batch_receipt(receipt, prepared["group_spec"]["actions"], property_batches)
                split = split_direct_receipt(receipt, members)
                parent_inspect = receipt.get("direct_inspection")
                if isinstance(parent_inspect, dict):
                    check_identity(parent_inspect)
                failed = None
                for member, state, inspect, apply in split:
                    name = member["step"]["step_id"]
                    provenance = {**group_record, "response_file": str(receipt_file), "response_sha256": receipt_sha,
                        "action_offset": member["action_offset"], "action_count": member["action_count"]}
                    if state == "not-executed":
                        journal(prefix(member) + "-not-executed", {"step_id": name, "reason": "native RPC stopped at an earlier action", "rpc": provenance})
                        continue
                    apply["client_step_rpc"] = provenance
                    if inspect is not None:
                        inspect["client_step_rpc"] = provenance
                        writer.submit(directory / (prefix(member) + "-inspect.json"), inspect)
                    writer.submit(directory / (prefix(member) + "-apply.json"), apply)
                    results["steps"][name] = {"inspect": inspect, "apply": apply}
                    if state in ("failed", "partial"):
                        if state == "failed":
                            failed = name
                        elif name not in status.setdefault("ambiguous_steps", []):
                            status["ambiguous_steps"].append(name)
                        journal(prefix(member) + "-" + state, {"step_id": name, "execution_may_be_partial": True,
                            "completed_action_count": apply["completed_action_count"], "rpc": provenance})
                        continue
                    actions = member["specification"]["actions"]
                    if any(action["kind"] in ("reference-sync", "strategy-working-reference-sync") for action in actions):
                        scopes = list(reference_sync_scopes(apply))
                        if not scopes:
                            raise ValueError("Reference synchronization returned no verified native owner scope")
                        for scope in scopes:
                            if scope["all_project_owners"]:
                                pending = {"page_ids": set(), "strategy_ids": set(), "unknown": False}
                            else:
                                pending["page_ids"].difference_update(scope["page_ids"])
                                pending["strategy_ids"].difference_update(scope["strategy_ids"])
                    changed = pending_reference_owners(actions)
                    for key in ("page_ids", "strategy_ids"):
                        pending[key].update(changed[key])
                    pending["unknown"] |= changed["unknown"]
                    status["completed_steps"].append(name)
                    journal(prefix(member) + "-complete", {"step_id": name, "ok": True,
                        "native_status": apply.get("status"), "committed": member["specification"].get("commit", False),
                        "pending_reference_sync": {"page_ids": sorted(pending["page_ids"]), "strategy_ids": sorted(pending["strategy_ids"]), "unknown": pending["unknown"]},
                        "rpc": provenance})
                if failed is not None:
                    active_step = failed
                    raise RuntimeError("Native engineering action failed or returned a partial result; no replay")
            index += len(members)
        status.update(ok=True, status="engineering-program-completed-acceptance-remains-separate")
    except Exception as error:
        status.update(error_type=type(error).__name__, error=str(error), failed_step=active_step,
            phase=phase, execution_may_be_partial=True)
        if phase == "split-direct-response":
            unresolved = []
            for member in members:
                name = member["step"]["step_id"]
                if name in status["completed_steps"] or any((directory / (prefix(member) + suffix)) in writer.paths or (directory / (prefix(member) + suffix)).exists()
                        for suffix in ("-failed.json", "-partial.json", "-not-executed.json")):
                    continue
                unresolved.append(name)
                try:
                    journal(prefix(member) + "-partial", {"step_id": name,
                        "status": "correlated-response-not-safely-split-no-replay", "execution_may_be_partial": True,
                        "error_type": type(error).__name__, "error": str(error), "automatic_retry": False})
                except Exception as io_error:
                    status.setdefault("background_io_errors", []).append(str(io_error))
            if unresolved:
                status["ambiguous_steps"] = unresolved
        if hasattr(error, "state"):
            status["transport_state"] = error.state
    preparation.close()
    try:
        writer.drain()
    except Exception as error:
        status.update(ok=False, status="derived-output-persistence-failed-no-replay")
        status.setdefault("background_io_errors", []).append(type(error).__name__ + ": " + str(error))
        status.setdefault("error_type", type(error).__name__)
        status.setdefault("error", str(error))
        status.setdefault("phase", "drain-derived-files")
    status["pipeline"] = {"prepare_workers": prepare_workers, "io_workers": io_workers,
        "background_prepared_chunks": preparation.background_chunks,
        "background_prepared_groups_used": preparation.background_groups_used,
        "derived_files_submitted": writer.submitted, "maximum_pending_derived_files": writer.max_pending,
        "derived_file_queue_limit": writer.limit, "drained_before_return": True,
        "critical_records_synchronously_durable": True}
    status["pending_reference_sync"] = {"page_ids": sorted(pending["page_ids"]), "strategy_ids": sorted(pending["strategy_ids"]), "unknown": pending["unknown"]}
    batch.write_new(directory / "execution-result.json", status)
    return status


def contains_deferred_references(value):
    if isinstance(value, dict):
        if value.get("defer_native_final_compile_and_reference_rebuild") is True:
            return True
        return any(contains_deferred_references(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_deferred_references(child) for child in value)
    return False


def needs_current_references(kind):
    return kind == "reference-redirect" or kind.endswith(("-rename", "-delete"))


def pending_reference_owners(actions):
    result = {"page_ids": set(), "strategy_ids": set(), "unknown": False}
    control_kinds = {"control-geometry-batch", "control-properties", "control-properties-batch", "button-actions-batch",
        "control-event-list", "control-collection", "control-animation-list", "control-clone", "control-template-clone",
        "control-native-create", "page-history"}
    for action in actions:
        if action["kind"] not in control_kinds and not contains_deferred_references(action.get("after", {})):
            continue
        target = action["target"]
        if type(target.get("page_id")) is int:
            result["page_ids"].add(target["page_id"])
        elif type(target.get("block_id", target.get("strategy_id"))) is int:
            result["strategy_ids"].add(target.get("block_id", target.get("strategy_id")))
        else:
            result["unknown"] = True
    return result


def reference_sync_scopes(receipt):
    if isinstance(receipt, dict):
        if "reference_sync_scope" in receipt:
            scope = receipt["reference_sync_scope"]
            if not isinstance(scope, dict) or type(scope.get("all_project_owners")) is not bool:
                raise ValueError("Native reference synchronization receipt has an invalid scope")
            for key in ("page_ids", "strategy_ids"):
                if not isinstance(scope.get(key), list) or any(type(item) is not int for item in scope[key]):
                    raise ValueError("Native reference synchronization owner IDs are invalid")
            yield scope
        else:
            for value in receipt.values():
                yield from reference_sync_scopes(value)
    elif isinstance(receipt, list):
        for value in receipt:
            yield from reference_sync_scopes(value)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def within_root(path, exists=True):
    path = batch.owned_file(path, False)
    if not exists and not path.is_relative_to(ROOT):
        raise ValueError("New session files must stay inside the configured runtime engineering directory")
    if exists and not path.is_file():
        raise ValueError("Expected an existing session file")
    return path


def pointer_parts(pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/steps/"):
        raise ValueError("A result reference must start with /steps/")
    parts = []
    for part in pointer[1:].split("/"):
        if re.search(r"~(?![01])", part):
            raise ValueError("Invalid JSON pointer escape")
        parts.append(part.replace("~1", "/").replace("~0", "~"))
    if len(parts) < 4 or parts[2] not in ("inspect", "apply"):
        raise ValueError("Reference must select a prior step's inspect/apply receipt")
    return parts


def references(value):
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) != {"$ref"}:
                raise ValueError("A result reference must contain only $ref")
            yield pointer_parts(value["$ref"])
        else:
            for child in value.values():
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def resolve(value, results):
    if isinstance(value, dict):
        if "$ref" in value:
            selected = results
            for part in pointer_parts(value["$ref"]):
                if isinstance(selected, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", part):
                        raise ValueError("Result reference array index is invalid")
                    selected = selected[int(part)]
                elif isinstance(selected, dict):
                    selected = selected[part]
                else:
                    raise ValueError("Result reference crosses a scalar")
            # Copy the selected JSON value; never mutate a retained receipt.
            return json_copy(selected)
        return {key: resolve(child, results) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve(child, results) for child in value]
    return value


def validate_spec(specification, read_only=False):
    require_json_value(specification)
    if not isinstance(specification, dict):
        raise ValueError("Each step needs a specification object")
    actions = specification.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("Each step needs a nonempty engineering action list")
    action_ids = set()
    for action in actions:
        required = ("action_id", "kind", "target") if read_only else ("action_id", "kind", "target", "after")
        if not isinstance(action, dict) or not all(key in action for key in required):
            raise ValueError("Every selector needs action_id/kind/target; edit actions also need after")
        action_id = action["action_id"]
        if not isinstance(action_id, str) or not NAME.fullmatch(action_id) or action_id in action_ids:
            raise ValueError("Action id is invalid or repeated")
        action_ids.add(action_id)
        if not isinstance(action["kind"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", action["kind"]):
            raise ValueError("Action kind must be a literal compiled engineering kind")
        if not isinstance(action["target"], dict) or ("after" in action and not isinstance(action["after"], dict)):
            raise ValueError("Action target and after must be objects")
        if "before" in action or "abi_profile_sha256" in action:
            raise ValueError("Session actions obtain fresh before/ABI from their own inspection")
    if "trial_id" in specification:
        raise ValueError("The staging process assigns unique step trial IDs")
    commit = specification.get("commit", False)
    if commit and "save_scope" not in specification:
        specification["save_scope"] = {"root_save": False}
    if type(commit) is not bool:
        raise ValueError("Step commit must be Boolean")
    if type(specification.get("coalesce_native_properties", True)) is not bool:
        raise ValueError("coalesce_native_properties must be Boolean")
    if read_only and (commit or specification.get("save_scope", {}).get("root_save")):
        raise ValueError("An inspection step cannot authorize persistence")
    if commit:
        saves = specification.get("save_scope")
        if not isinstance(saves, dict) or type(saves.get("root_save")) is not bool:
            raise ValueError("root_save must be a Boolean when a save_scope is supplied")
    return len(actions)


def stage(program_file, directory):
    program_file = batch.input_file(program_file)
    program, program_sha = batch.read_json(program_file)
    if program.get("schema") != 1 or program.get("purpose") != PURPOSE:
        raise ValueError("Unsupported engineering session program schema/purpose")
    project = batch.input_file(program.get("project_path", ""))
    if project.suffix.lower() != ".mcp":
        raise ValueError("This session runner requires the current Pro MCP file")
    steps = program.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("A session program needs a nonempty step list")
    directory = within_root(Path(directory) / "manifest.json", False).parent
    if directory.exists():
        raise FileExistsError("Session directory already exists; it cannot be reused")
    seen, modes, prepared, action_count = set(), {}, [], 0
    references_need_sync = False
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"step_id", "description", "specification", "mode"}:
            raise ValueError("Unsupported session step fields")
        name = step.get("step_id")
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in seen:
            raise ValueError("Session step id is invalid or repeated")
        specification = step.get("specification")
        mode = step.get("mode", "edit")
        if mode not in ("edit", "inspect"):
            raise ValueError("Session step mode must be edit or inspect")
        action_count += validate_spec(specification, mode == "inspect")
        if mode == "edit":
            actions = specification["actions"]
            if any(action["kind"] in ("reference-sync", "strategy-working-reference-sync") for action in actions):
                references_need_sync = False
            affected = pending_reference_owners(actions)
            references_need_sync |= bool(affected["page_ids"] or affected["strategy_ids"] or affected["unknown"])
        for parts in references(specification):
            if parts[1] not in seen:
                raise ValueError("Only an earlier completed step may supply a result reference")
            if modes[parts[1]] == "inspect" and parts[2] == "apply":
                raise ValueError("An inspection-only step has no apply receipt")
        seen.add(name)
        modes[name] = mode
        prepared.append({"step_id": name, "description": str(step.get("description", name)), "mode": mode,
                         "specification": specification})
    # All program validation precedes creating any stage files or host request.
    directory.mkdir(parents=True)
    batch.write_new(directory / "program.json", dict(program, project_path=str(project), steps=prepared))
    manifest = {"schema": 1, "purpose": PURPOSE, "session_id": uuid.uuid4().hex,
        "source_program_file": str(program_file), "source_program_sha256": program_sha,
        "program_sha256": sha(directory / "program.json"), "project_path": str(project),
        "runner_sha256": sha(__file__), "batch_client_sha256": sha(batch.__file__),
        "engineering_delivery_scope_sha256": _LAYOUT.configuration_sha256,
        "scope_configuration_file": str(_LAYOUT.configuration_file),
        "step_count": len(prepared), "action_count": action_count,
        "host_invoked": False, "engineering_acceptance_verified": False,
        "automatic_retry": False, "automatic_resume": False,
        "project_open_close_operations": 0}
    batch.write_new(directory / "manifest.json", manifest)
    return {"ok": True, "session_directory": str(directory), **manifest}


def run(directory, timeout, legacy_permits=False, merge_steps=True, max_merged_actions=None,
        prepare_workers=1, io_workers=1):
    directory = within_root(Path(directory) / "manifest.json").parent
    manifest_file = directory / "manifest.json"
    manifest, manifest_sha = batch.read_json(manifest_file)
    if manifest.get("schema") != 1 or manifest.get("purpose") != PURPOSE:
        raise ValueError("Invalid staged session manifest")
    _LAYOUT.check()
    if manifest.get("engineering_delivery_scope_sha256") != _LAYOUT.configuration_sha256 or not directory.is_relative_to(ROOT):
        raise ValueError("Staged session is outside or bound to another delivery runtime")
    if sha(__file__) != manifest["runner_sha256"] or sha(batch.__file__) != manifest["batch_client_sha256"]:
        raise ValueError("Session implementation changed after staging; prepare a new stage")
    program_file = within_root(directory / "program.json")
    if sha(program_file) != manifest["program_sha256"]:
        raise ValueError("Staged engineering program changed")
    program, _ = batch.read_json(program_file)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Per-request timeout must be finite and positive")
    if max_merged_actions is not None and (type(max_merged_actions) is not int or max_merged_actions < 1):
        raise ValueError("max merged actions must be a positive integer merge budget")
    if type(prepare_workers) is not int or prepare_workers < 0 or type(io_workers) is not int or io_workers < 1:
        raise ValueError("prepare workers must be nonnegative and IO workers positive")
    # This durable claim is never cleared, including after timeout or failure.
    batch.write_new(directory / ("execution-claim.json" if legacy_permits else "execution-start.json"), {"schema": 1,
        "session_id": manifest["session_id"], "manifest_sha256": manifest_sha,
        "owner_pid": os.getpid(), "utc": datetime.now(timezone.utc).isoformat(),
        "automatic_retry": False, "automatic_resume": False})
    if not legacy_permits:
        return run_direct_program(program, manifest, directory, timeout, merge_steps, max_merged_actions, prepare_workers, io_workers)
    results, identity = {"steps": {}}, None
    pending_references = {"page_ids": set(), "strategy_ids": set(), "unknown": False}
    status = {"ok": False, "session_id": manifest["session_id"],
        "completed_steps": [], "execution_mode": "legacy-permit" if legacy_permits else "direct", "approval_required": False, "automatic_retry": False, "automatic_resume": False,
        "project_open_close_operations": 0, "engineering_acceptance_verified": False}
    active_step, phase = None, "claimed"

    def journal(event, payload):
        batch.write_new(directory / (event + ".json"), payload)
        print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)

    try:
        for index, step in enumerate(program["steps"]):
            active_step = step["step_id"]
            prefix = "%04d-%s" % (index + 1, active_step)
            phase = "resolve-and-freeze"
            specification = resolve(step["specification"], results)
            read_only = step.get("mode", "edit") == "inspect"
            validate_spec(specification, read_only)
            if legacy_permits and not read_only and any(needs_current_references(action["kind"]) for action in specification["actions"]):
                if pending_references["page_ids"] or pending_references["strategy_ids"] or pending_references["unknown"]:
                    raise ValueError("A reference-dependent mutation requires explicit native reference-sync for all pending owners first")
            if not read_only:
                specification["trial_id"] = str(uuid.uuid4())
            spec_file = directory / (prefix + "-specification.json")
            batch.write_new(spec_file, specification)
            journal(prefix + "-begin", {"step_id": active_step,
                "description": step["description"], "specification_sha256": sha(spec_file)})
            if read_only or legacy_permits:
                phase = "inspect"
                inspect = batch.submit({"op": "engineering-edit-inspect",
                    "expected_project": program["project_path"], "inspection_file": str(spec_file),
                    "inspection_sha256": sha(spec_file)},
                    "eng_" + manifest["session_id"] + "_%04d_read" % index, timeout)
                inspect_file = directory / (prefix + "-inspect.json")
                batch.write_new(inspect_file, inspect)
                if inspect.get("ok") is not True:
                    raise RuntimeError("Native engineering inspection did not complete successfully")
                current_identity = tuple(inspect.get(key) for key in
                    ("process_id", "creation_filetime", "native_thread_id", "actual_project", "editor_image_sha256"))
                if any(item is None for item in current_identity):
                    raise ValueError("Inspection is missing editor/project identity")
                if identity is None:
                    identity = current_identity
                    journal("editor-identity", dict(zip(("process_id", "creation_filetime", "ui_thread_id",
                        "project_path", "editor_image_sha256"), identity)))
                elif identity != current_identity:
                    raise ValueError("Editor, UI thread or project changed during the session")
                if read_only:
                    results["steps"][active_step] = {"inspect": inspect}
                    status["completed_steps"].append(active_step)
                    journal(prefix + "-complete", {"step_id": active_step, "ok": True,
                        "mode": "inspect", "edit_submitted": False, "committed": False})
                    continue
                compiled = set(inspect.get("compiled_kinds", []))
                if any(action["kind"] not in compiled for action in specification["actions"]):
                    raise ValueError("A requested action has no implementation in the loaded candidate")
                phase = "prepare-permit"
                permit_file = directory / (prefix + "-permit.json")
                prepared = batch.prepare(inspect_file, spec_file, permit_file)
                phase = "apply"
                apply = batch.submit({"op": "engineering-edit-batch", "expected_project": program["project_path"],
                    "permit_file": str(permit_file), "permit_sha256": prepared["permit_sha256"]},
                    "eng_" + manifest["session_id"] + "_%04d_edit" % index, timeout)
            else:
                phase = "direct-execute"
                apply = batch.execute(program["project_path"], spec_file,
                    "eng_" + manifest["session_id"] + "_%04d_direct" % index, timeout)
                inspect = apply.get("direct_inspection")
                if inspect is not None:
                    batch.write_new(directory / (prefix + "-inspect.json"), inspect)
                    current_identity = tuple(inspect.get(key) for key in
                        ("process_id", "creation_filetime", "native_thread_id", "actual_project", "editor_image_sha256"))
                    if identity is None:
                        identity = current_identity
                        journal("editor-identity", dict(zip(("process_id", "creation_filetime", "ui_thread_id",
                            "project_path", "editor_image_sha256"), identity)))
                    elif identity != current_identity:
                        raise ValueError("Editor, UI thread or project changed during the session")
                results["steps"][active_step] = {"inspect": inspect, "apply": apply}
            batch.write_new(directory / (prefix + "-apply.json"), apply)
            if apply.get("ok") is not True:
                raise RuntimeError("Native engineering action failed or returned a partial result; no replay")
            if any(action["kind"] in ("reference-sync", "strategy-working-reference-sync") for action in specification["actions"]):
                scopes = list(reference_sync_scopes(apply))
                if not scopes:
                    raise ValueError("Reference synchronization returned no verified native owner scope")
                for scope in scopes:
                    if scope["all_project_owners"]:
                        pending_references = {"page_ids": set(), "strategy_ids": set(), "unknown": False}
                    else:
                        pending_references["page_ids"].difference_update(scope["page_ids"])
                        pending_references["strategy_ids"].difference_update(scope["strategy_ids"])
            changed_references = pending_reference_owners(specification["actions"])
            for key in ("page_ids", "strategy_ids"):
                pending_references[key].update(changed_references[key])
            pending_references["unknown"] |= changed_references["unknown"]
            results["steps"][active_step] = {"inspect": inspect, "apply": apply}
            status["completed_steps"].append(active_step)
            journal(prefix + "-complete", {"step_id": active_step, "ok": True,
                "native_status": apply.get("status"), "committed": specification.get("commit", False),
                "pending_reference_sync": {"page_ids": sorted(pending_references["page_ids"]),
                    "strategy_ids": sorted(pending_references["strategy_ids"]), "unknown": pending_references["unknown"]}})
        status["ok"] = True
        status["status"] = "engineering-program-completed-acceptance-remains-separate"
    except Exception as error:
        status.update(error_type=type(error).__name__, error=str(error),
            failed_step=active_step, phase=phase, execution_may_be_partial=True)
        if hasattr(error, "state"):
            status["transport_state"] = error.state
    status["pending_reference_sync"] = {"page_ids": sorted(pending_references["page_ids"]),
        "strategy_ids": sorted(pending_references["strategy_ids"]), "unknown": pending_references["unknown"]}
    batch.write_new(directory / "execution-result.json", status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    staging = commands.add_parser("stage")
    staging.add_argument("--program", required=True)
    staging.add_argument("--directory", required=True)
    execution = commands.add_parser("run")
    execution.add_argument("--directory", required=True)
    execution.add_argument("--timeout", type=float, default=30)
    execution.add_argument("--legacy-permits", action="store_true", help="Use the old inspect/permit/apply file workflow")
    execution.add_argument("--no-merge-steps", action="store_true", help="Keep one direct RPC per edit step; explicit inspections are always retained")
    execution.add_argument("--max-merged-actions", type=int, default=MAX_RPC_ACTIONS,
        help="Cross-step grouping budget (default8); an existing single step is never split or rejected by this budget")
    execution.add_argument("--prepare-workers", type=int, default=1, help="In-process pure JSON preparation threads;0 disables lookahead")
    execution.add_argument("--io-workers", type=int, default=1, help="Bounded derived-output writer threads; drained before return")
    args = parser.parse_args()
    result = stage(args.program, args.directory) if args.command == "stage" else run(args.directory, args.timeout, args.legacy_permits, not args.no_merge_steps, args.max_merged_actions, args.prepare_workers, args.io_workers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
