"""Pro native engineering client. Default edits execute directly in one queue call.

The native UI-thread worker reads current targets and prepares its execution
state in memory; no permit file or human approval token is needed. Optional
legacy prepare/--permit remains compatible. Request IDs are at-most-once and
unknown timeouts are never automatically retried. This is a candidate until
integrated/bound; no vendor licensing is changed.
"""
import argparse
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

from native_delivery_config import current as delivery_layout
_LAYOUT = delivery_layout()
TASK = _LAYOUT.task_root
RUNTIME = _LAYOUT.runtime_root
CLIENT_SHA = "298e62cf5798acc03d82af5dd5b5751703a1e65348e12a485780239c01fe3417"
# The native JavaScriptSerializer and x86 arrays use signed Int32 lengths.
# This is a representation boundary, not a sampled engineering payload quota.
CLR_MAX_LENGTH = (1 << 31) - 1


@lru_cache(maxsize=1)
def load_client():
    _LAYOUT.check()
    path = _LAYOUT.transport_client_file
    if _LAYOUT.transport_client_sha256 != CLIENT_SHA:
        raise ValueError("Existing at-most-once client source differs; review before reuse")
    spec = importlib.util.spec_from_file_location("mcgs_verified_transport", path)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    client.ROOT = RUNTIME  # Existing verified transport, explicit configured queue.
    return client


def read_json(path):
    data = Path(path).read_bytes()
    if len(data) > CLR_MAX_LENGTH:
        raise ValueError("JSON input exceeds the native Int32 length representation")
    result = json.loads(data.decode("utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result, hashlib.sha256(data).hexdigest()


def owned_file(path, must_exist=True):
    path = Path(path).expanduser().resolve(strict=False)
    if not path.is_relative_to(TASK):
        raise ValueError("Permit/output must stay in the owned task directory")
    if must_exist and not path.is_file():
        raise ValueError("Expected existing regular file")
    return path


def write_new_bytes(path, data, durable=True):
    path = owned_file(path, False)
    if not path.is_relative_to(RUNTIME):
        raise ValueError("Delivery outputs must stay in the configured writable runtime, never frozen profiles")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        if durable:
            os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def write_new(path, value, durable=True):
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    return write_new_bytes(path, data, durable)


def expand_receipt(receipt, request_id, request_sha):
    reference = receipt.get("engineering_payload")
    if reference is None:
        return receipt
    if not isinstance(reference, dict) or set(reference) != {
        "schema", "file", "byte_length", "sha256", "request_id", "queue_request_sha256"
    } or reference["schema"] != 1:
        raise ValueError("Unknown complete engineering receipt schema")
    if reference["request_id"] != request_id or reference["queue_request_sha256"] != request_sha:
        raise ValueError("Complete engineering receipt names another request")
    expected = _LAYOUT.working_root / "reply-payloads" / (request_id + ".json")
    path = owned_file(reference["file"])
    if path != expected or type(reference["byte_length"]) is not int or not 0 < reference["byte_length"] <= CLR_MAX_LENGTH:
        raise ValueError("Complete engineering receipt path or bound differs")
    data = load_client()._read(path, maximum=reference["byte_length"])
    if len(data) != reference["byte_length"] or hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise ValueError("Complete engineering receipt length or SHA differs")
    full = json.loads(data.decode("utf-8-sig"))
    if not isinstance(full, dict) or full.get("request_id") != request_id or full.get("queue_request_sha256") != request_sha:
        raise ValueError("Complete engineering result is not correlated")
    for key, value in receipt.items():
        if key == "engineering_payload":
            continue
        if key in full and full[key] != value:
            raise ValueError("Complete engineering result conflicts with its queue envelope: " + key)
        full[key] = value
    full["engineering_payload_receipt"] = reference
    return full


def submit(request, request_id, timeout):
    client = load_client()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id) or request_id.upper() in client.RESERVED:
        raise ValueError("Invalid request id")
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Timeout must be finite and nonnegative")
    _LAYOUT.check()
    if "permit_file" in request and request.get("op") in {"engineering-edit-batch", "engineering-project-close-reopen-original"}:
        permit, permit_sha = read_json(owned_file(request["permit_file"]))
        if permit_sha != request["permit_sha256"] or permit.get("engineering_delivery_scope_sha256") != _LAYOUT.configuration_sha256:
            raise ValueError("Permit is not exactly bound to this delivery configuration")
    request = dict(request, schema=1, request_id=request_id,
        engineering_delivery_scope_sha256=_LAYOUT.configuration_sha256)
    payload = client._encoded(request)
    if len(payload) > CLR_MAX_LENGTH:
        raise ValueError("Queue request exceeds the native Int32 length representation")
    payload_sha = hashlib.sha256(payload).hexdigest()
    root = RUNTIME.absolute()
    root.mkdir(parents=True, exist_ok=True)
    client._directory(root)
    for name in client.HOST_DIRECTORIES:
        path = root / name
        if name in ("inbox", "outbox"):
            client._directory(path, True)
        elif client._exists(path):
            client._directory(path)
    submissions = root / "client-submissions"
    client._directory(submissions, True)
    paths = client._paths(root, request_id)
    if client._unused(paths):
        raise client.SubmissionError("Request id already has host state; do not resubmit", client._state(root, request_id, payload_sha))
    reservation = submissions / (request_id + ".json")
    token = uuid.uuid4().hex
    record = {"schema": 1, "request_id": request_id, "request_sha256": payload_sha,
              "owner_pid": os.getpid(), "submission_token": token, "phase": "reserved"}
    try:
        client._write_new(reservation, client._encoded(record))
    except Exception as error:
        raise client.SubmissionError("Client id already occupied or reservation failed; no retry", client._state(root, request_id, payload_sha)) from error
    waiter_factory = getattr(client, "_response_waiter", None)
    waiter = waiter_factory(root, request_id) if callable(waiter_factory) else None
    try:
        temporary = paths["inbox"].parent / ("." + request_id + "." + token + ".staging")
        published = False
        try:
            client._write_new(temporary, payload)
            if client._unused(paths):
                raise client.SubmissionError("Host state appeared before publication", client._state(root, request_id, payload_sha))
            client._publish_no_replace(temporary, paths["inbox"])
            published = True
            client._record_phase(reservation, token, "published")
            if waiter is not None:
                waiter.notify_submission()
            else:
                notify = getattr(client, "_notify_submission", None)
                if callable(notify):
                    notify(root)  # Best-effort wake; durable queue remains authoritative.
        except Exception as error:
            if not published and client._exists(temporary):
                temporary.unlink()  # Only this client's unpublished staging record.
            if isinstance(error, client.SubmissionError):
                raise
            raise client.SubmissionError("Publication outcome requires inspection; do not resend", client._state(root, request_id, payload_sha)) from error
        deadline = time.monotonic() + timeout
        while True:
            if client._exists(paths["outbox"]):
                try:
                    receipt = client._json(paths["outbox"])
                    if receipt.get("request_id") != request_id or receipt.get("queue_request_sha256") != payload_sha:
                        raise ValueError("Receipt does not correlate with submitted bytes")
                    receipt = expand_receipt(receipt, request_id, payload_sha)
                    if receipt.get("ok") is True and receipt.get("engineering_delivery_scope_sha256") != _LAYOUT.configuration_sha256:
                        raise ValueError("Native engine has not attested this exact bound delivery configuration")
                except Exception as error:
                    raise client.ReceiptError(str(error), client._state(root, request_id, payload_sha)) from error
                try:
                    client._record_phase(reservation, token, "correlated-response")
                except Exception as error:
                    receipt["client_transport_warning"] = {"correlated_response_verified": True,
                        "client_journal_update_failed": type(error).__name__ + ": " + str(error),
                        "automatic_retry": False, "transport_state": client._state(root, request_id, payload_sha)}
                return receipt
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise client.QueueTimeout("No correlated response; execution is unknown, do not resubmit", client._state(root, request_id, payload_sha))
            if waiter is not None:
                waiter.wait(remaining)
            else:
                wait = getattr(client, "_wait_for_response", None)
                if callable(wait):
                    wait(root, request_id, remaining)
                else:
                    time.sleep(min(0.1, remaining))
    finally:
        if waiter is not None:
            waiter.close()


def input_file(path):
    """Logical request input may be anywhere; it is not an authorization document."""
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Expected an existing specification file")
    return path


def execute(project, specification_path, request_id=None, timeout=30, specification_sha256=None):
    path = input_file(specification_path)
    if specification_sha256 is None:
        _, specification_sha = read_json(path)
    else:
        # A session has just frozen and hashed this file. Reuse that digest;
        # native verifies the bytes against it before parsing or applying.
        if not isinstance(specification_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", specification_sha256):
            raise ValueError("Specification SHA must be64 lowercase hex characters")
        if not 0 < path.stat().st_size <= CLR_MAX_LENGTH:
            raise ValueError("JSON input must be nonempty and fit the native Int32 length representation")
        specification_sha = specification_sha256
    return submit({"op": "engineering-edit-batch", "expected_project": str(Path(project).expanduser().resolve(strict=True)),
                   "specification_file": str(path), "specification_sha256": specification_sha},
                  request_id or ("direct_" + uuid.uuid4().hex), timeout)


def prepare(snapshot_path, specification_path, output):
    _LAYOUT.check()
    snapshot, snapshot_sha = read_json(owned_file(snapshot_path))
    if snapshot.get("engineering_delivery_scope_sha256") != _LAYOUT.configuration_sha256:
        raise ValueError("Inspection is not bound to this delivery configuration")
    specification, specification_sha = read_json(owned_file(specification_path))
    required = ("ok", "process_id", "creation_filetime", "native_thread_id", "actual_project",
                "editor_image_sha256", "native_summary_utf8_sha256")
    if not all(key in snapshot for key in required) or snapshot["ok"] is not True:
        raise ValueError("Need a successful engineering-edit-inspect receipt, including native C# digest")
    actions = specification.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("Specification needs a nonempty prepared action list")
    seen = set()
    observed = {row["action_id"]: row for row in snapshot.get("action_preimages", [])}
    for action in actions:
        if not isinstance(action, dict) or not all(key in action for key in
                ("action_id", "kind", "target", "after")):
            raise ValueError("Action lacks its kind, target or explicit after values")
        action_id = action["action_id"]
        if not isinstance(action_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", action_id) or action_id in seen:
            raise ValueError("Action id invalid or repeated")
        seen.add(action_id)
        if "before" not in action or "abi_profile_sha256" not in action:
            row = observed.get(action_id)
            if row is None or row["kind"] != action["kind"] or row["target"] != action["target"]:
                raise ValueError("Action needs its own matching native inspection preimage: " + action_id)
            action.setdefault("before", row["before"])
            action.setdefault("abi_profile_sha256", row["abi_profile_sha256"])
    trial_id = specification.get("trial_id", str(uuid.uuid4()))
    try:
        uuid.UUID(trial_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Batch trial_id must be a GUID") from error
    commit = specification.get("commit", False)
    if not isinstance(commit, bool):
        raise ValueError("commit must be a Boolean")
    save_scope = specification.get("save_scope", {"affected_page_ids": [], "strategy_ids": [],
        "created_page_actions": [], "created_strategy_actions": [], "root_save": False})
    if not isinstance(save_scope, dict) or not isinstance(save_scope.get("root_save"), bool):
        raise ValueError("save_scope requires an explicit root_save Boolean")
    if "main_control_document" in save_scope and not isinstance(save_scope["main_control_document"], bool):
        raise ValueError("main_control_document must be Boolean")
    if "linguist_document" in save_scope and not isinstance(save_scope["linguist_document"], bool):
        raise ValueError("linguist_document must be Boolean")
    modules = save_scope.get("module_ids", [])
    if not isinstance(modules, list) or any(type(n) is not int or not 0 <= n <= 63 for n in modules) or len(set(modules)) != len(modules):
        raise ValueError("module_ids must list unique bounded native module IDs")
    save_scope["module_ids"] = modules
    for key in ("affected_page_ids", "strategy_ids"):
        entries = save_scope.get(key)
        if not isinstance(entries, list) or any(type(n) is not int or n < 0 for n in entries) or len(set(entries)) != len(entries):
            raise ValueError("save_scope requires unique nonnegative " + key)
    for key in ("created_page_actions", "created_strategy_actions"):
        entries = save_scope.get(key, [])
        if not isinstance(entries, list) or any(n not in seen for n in entries) or len(set(entries)) != len(entries):
            raise ValueError("save_scope created action is absent/repeated: " + key)
        save_scope[key] = entries
    if not commit and save_scope["root_save"]:
        raise ValueError("commit=false cannot authorize explicit RootSave")
    permit = {"schema": 1, "purpose": "native-usable-edit-batch", "trial_id": trial_id,
        "engineering_delivery_scope_sha256": _LAYOUT.configuration_sha256,
        "process_id": snapshot["process_id"], "creation_filetime": snapshot["creation_filetime"],
        "ui_thread_id": snapshot["native_thread_id"], "project_path": snapshot["actual_project"],
        "project_sha256": snapshot["native_summary"]["disk_sha256"],
        "editor_image_sha256": snapshot["editor_image_sha256"],
        "native_summary_utf8_sha256": snapshot["native_summary_utf8_sha256"],
        "actions": actions, "commit": commit, "save_scope": save_scope,
        "preparation_evidence": {"snapshot_file": str(Path(snapshot_path).absolute()), "snapshot_sha256": snapshot_sha,
            "specification_file": str(Path(specification_path).absolute()), "specification_sha256": specification_sha}}
    write_new(output, permit)
    return {"ok": True, "permit_file": str(Path(output).absolute()), "permit_sha256": hashlib.sha256(Path(output).read_bytes()).hexdigest(),
        "action_count": len(actions), "commit": commit, "project_access": False, "host_submission": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("prepare")
    plan.add_argument("--snapshot", required=True); plan.add_argument("--spec", required=True); plan.add_argument("--out", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--project", required=True)
    inspect.add_argument("--spec", help="Optional owned logical target selectors; no mutations")
    apply = commands.add_parser("apply")
    apply.add_argument("--permit", help="Optional legacy prepared-permit compatibility")
    apply.add_argument("--project", help="Current Pro project for default direct execution")
    apply.add_argument("--spec", help="Logical edit specification, not a permit")
    execute_cmd = commands.add_parser("execute")
    execute_cmd.add_argument("--project", required=True); execute_cmd.add_argument("--spec", required=True)
    for sub in (inspect, apply, execute_cmd):
        sub.add_argument("--id", default=None); sub.add_argument("--timeout", type=float, default=30); sub.add_argument("--out")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.snapshot, args.spec, args.out)
    else:
        # Refuse an occupied result before reserving or publishing any request.
        output = owned_file(args.out, False) if args.out else None
        if output is not None and output.exists():
            raise FileExistsError(output)
        if args.command == "inspect":
            request = {"op": "engineering-edit-inspect", "expected_project": str(Path(args.project).expanduser().resolve(strict=True))}
            if args.spec:
                specification_path = input_file(args.spec)
                _, specification_sha = read_json(specification_path)
                request.update(inspection_file=str(specification_path), inspection_sha256=specification_sha)
        elif args.command == "execute" or not args.permit:
            if not args.project or not args.spec:
                raise ValueError("Direct apply needs --project and --spec")
            specification_path = input_file(args.spec)
            _, specification_sha = read_json(specification_path)
            request = {"op": "engineering-edit-batch", "expected_project": str(Path(args.project).expanduser().resolve(strict=True)),
                       "specification_file": str(specification_path), "specification_sha256": specification_sha}
        else:
            permit_path = owned_file(args.permit)
            permit, permit_sha = read_json(permit_path)
            request = {"op": "engineering-edit-batch", "expected_project": permit["project_path"],
                "permit_file": str(permit_path), "permit_sha256": permit_sha}
        client = load_client()
        try:
            result = submit(request, args.id or ("direct_" + uuid.uuid4().hex), args.timeout)
        except (client.SubmissionError, client.QueueTimeout) as error:
            result = {"ok": False, "error_type": type(error).__name__, "error": str(error), "transport_state": error.state}
        if output is not None:
            write_new(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
