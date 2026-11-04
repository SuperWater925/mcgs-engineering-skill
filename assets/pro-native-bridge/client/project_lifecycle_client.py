"""Original project Close/Open client. Default execution needs no permit.

Current native state is read/prepared in the same worker call. Original UI,
saved-state and ABI/identity requirements remain. Legacy --permit is optional;
unknown request timeouts are never retried automatically.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import uuid

import edit_batch_client as batch

READ_OP = "engineering-project-lifecycle-read"
EXECUTE_OP = "engineering-project-close-reopen-original"
PURPOSE = "native-project-lifecycle-close-reopen"
PERMISSIONS = ("close_current_project", "reopen_same_project", "copy_closed_snapshot",
               "allow_original_ui", "allow_original_open_persistence",
               "preserve_original_warnings_and_exceptions")


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Lifecycle needs an exact lowercase SHA256")
    return value


def _working_new(path):
    value = batch.owned_file(path, False)
    if not value.is_relative_to(batch._LAYOUT.working_root):
        raise ValueError("Lifecycle permit, receipt and closed snapshot must stay in configured WorkingRoot")
    if value.exists():
        raise FileExistsError(value)
    return value


def _same_path(first, second):
    return str(Path(first).absolute()).casefold() == str(Path(second).absolute()).casefold()


def prepare(snapshot_file, output, permissions):
    batch._LAYOUT.check()
    snapshot_path = batch.owned_file(snapshot_file)
    snapshot, snapshot_sha = batch.read_json(snapshot_path)
    required = ("process_id", "creation_filetime", "native_thread_id", "actual_project",
                "editor_image_sha256", "abi_profile_sha256", "native_summary_utf8_sha256",
                "state_utf8_sha256", "native_summary", "state", "closed_copy_file")
    if snapshot.get("ok") is not True or snapshot.get("ready") is not True or snapshot.get("op") != READ_OP:
        raise ValueError("A successful fresh lifecycle-read receipt is required")
    if snapshot.get("engineering_delivery_scope_sha256") != batch._LAYOUT.configuration_sha256:
        raise ValueError("Lifecycle inspection belongs to another delivery configuration")
    if not all(key in snapshot for key in required):
        raise ValueError("Lifecycle read lacks its exact native preimage or identity")
    if set(permissions) != set(PERMISSIONS) or any(permissions[key] is not True for key in PERMISSIONS):
        raise ValueError("All six original lifecycle permissions must be explicitly selected")
    for key in ("process_id", "creation_filetime", "native_thread_id"):
        if type(snapshot[key]) is not int or snapshot[key] <= 0:
            raise ValueError("Lifecycle read has an invalid native identity: " + key)
    state, summary = snapshot["state"], snapshot["native_summary"]
    if not isinstance(state, dict) or not isinstance(summary, dict) or state.get("root_modified") != 0:
        raise ValueError("Lifecycle read must prove the original project saved")
    for key in ("process_id", "creation_filetime", "native_thread_id"):
        if state.get(key) != snapshot[key]:
            raise ValueError("Lifecycle read identity fields conflict: " + key)
    # Core actual_project may use the editor's uppercase spelling. State's
    # Project string participates in the exact C# digest, so preserve its case
    # and spelling verbatim for both the permit and subsequent expected_project.
    project = batch.owned_file(state["actual_project"])
    if not _same_path(snapshot["actual_project"], project):
        raise ValueError("Lifecycle read project fields conflict")
    project_sha = _hash(state["project_sha256"])
    if summary.get("disk_sha256") != project_sha:
        raise ValueError("Lifecycle native state/summary storage preimages conflict")
    closed_copy = _working_new(snapshot["closed_copy_file"])
    if closed_copy.suffix.casefold() != ".mcp" or _same_path(closed_copy, project):
        raise ValueError("Lifecycle closed snapshot needs a distinct owned .MCP path")
    target = _working_new(output)
    # The two digests come verbatim from C# JavaScriptSerializer. Python does not
    # reserialize or invent either native preimage digest.
    permit = {"schema": 1, "purpose": PURPOSE, "trial_id": str(uuid.uuid4()),
        "engineering_delivery_scope_sha256": batch._LAYOUT.configuration_sha256,
        "process_id": snapshot["process_id"], "creation_filetime": snapshot["creation_filetime"],
        "ui_thread_id": snapshot["native_thread_id"], "project_path": str(project),
        "project_sha256": project_sha, "editor_image_sha256": _hash(snapshot["editor_image_sha256"]),
        "abi_profile_sha256": _hash(snapshot["abi_profile_sha256"]),
        "native_summary_utf8_sha256": _hash(snapshot["native_summary_utf8_sha256"]),
        "state_utf8_sha256": _hash(snapshot["state_utf8_sha256"]),
        "closed_copy_file": str(closed_copy), "commit": False, "root_save": False,
        "permissions": permissions,
        "preparation_evidence": {"snapshot_file": str(snapshot_path), "snapshot_sha256": snapshot_sha,
            "csharp_preimage_digests_copied_verbatim": True}}
    batch.write_new(target, permit)
    return {"ok": True, "permit_file": str(target),
        "permit_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "closed_copy_file": str(closed_copy), "host_submission": False,
        "project_close_or_open_called": False, "automatic_retry": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("lifecycle-read")
    read.add_argument("--project", required=True)
    read.add_argument("--closed-copy")
    plan = commands.add_parser("prepare-close-reopen")
    plan.add_argument("--snapshot", required=True)
    plan.add_argument("--out", required=True)
    for permission in PERMISSIONS:
        plan.add_argument("--" + permission.replace("_", "-"), action="store_true", required=True)
    execute = commands.add_parser("close-reopen")
    execute.add_argument("--permit")
    execute.add_argument("--project")
    execute.add_argument("--closed-copy")
    for command in (read, execute):
        command.add_argument("--id", default=None)
        command.add_argument("--timeout", type=float, default=180)
        command.add_argument("--out")
    args = parser.parse_args()
    if args.command == "prepare-close-reopen":
        result = prepare(args.snapshot, args.out, {key: getattr(args, key) for key in PERMISSIONS})
    else:
        output = _working_new(args.out) if args.out else None
        if args.command == "lifecycle-read":
            project = batch.input_file(args.project)
            copy = Path(args.closed_copy).absolute() if args.closed_copy else batch._LAYOUT.working_root / "lifecycle" / (uuid.uuid4().hex + ".mcp")
            if copy.suffix.casefold() != ".mcp" or _same_path(copy, project):
                raise ValueError("Lifecycle closed snapshot needs a distinct owned .MCP path")
            request = {"op": READ_OP, "expected_project": str(project), "closed_copy_file": str(copy)}
        else:
            if args.permit:
                if args.project or args.closed_copy:
                    raise ValueError("Legacy permit cannot be combined with direct arguments")
                permit_path = batch.owned_file(args.permit)
                permit, permit_sha = batch.read_json(permit_path)
                if permit.get("purpose") != PURPOSE or permit.get("engineering_delivery_scope_sha256") != batch._LAYOUT.configuration_sha256:
                    raise ValueError("Dedicated lifecycle permit belongs to another purpose/configuration")
                _working_new(permit["closed_copy_file"])
                request = {"op": EXECUTE_OP, "expected_project": permit["project_path"],
                           "permit_file": str(permit_path), "permit_sha256": permit_sha}
            else:
                if not args.project:
                    raise ValueError("Direct close-reopen requires --project")
                project = Path(args.project).expanduser().resolve(strict=True)
                if not project.is_file() or project.suffix.casefold() != ".mcp":
                    raise ValueError("Project must be an existing MCP file")
                request = {"op": EXECUTE_OP, "expected_project": str(project)}
                if args.closed_copy:
                    copy = Path(args.closed_copy).absolute() if args.closed_copy else batch._LAYOUT.working_root / "lifecycle" / (uuid.uuid4().hex + ".mcp")
                    if copy.suffix.casefold() != ".mcp" or _same_path(copy, project):
                        raise ValueError("Closed snapshot needs a distinct runtime .MCP path")
                    request["closed_copy_file"] = str(copy)
        client = batch.load_client()
        try:
            result = batch.submit(request, args.id or ("lifecycle_" + uuid.uuid4().hex), args.timeout)
        except (client.SubmissionError, client.QueueTimeout) as error:
            result = {"ok": False, "error_type": type(error).__name__, "error": str(error),
                      "transport_state": error.state, "automatic_retry": False}
        if output is not None:
            batch.write_new(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
