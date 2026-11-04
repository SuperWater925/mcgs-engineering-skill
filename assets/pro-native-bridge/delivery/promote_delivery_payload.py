"""Validate/promote only the newly bound, immutable own ABI payload.

No application, queue, activation, registry, vendor binary or project access.
The default prints the complete file plan. --commit uses CreateNew, retains
partial output on error, and never replaces an existing payload or record.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def need(value, message):
    if not value:
        raise ValueError(message)


def path(text):
    p = Path(os.fspath(text))
    need(p.is_absolute(), "Use explicit absolute paths")
    p = Path(os.path.abspath(p))
    for item in (p, *p.parents):
        if os.path.lexists(item):
            info = os.lstat(item)
            need(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                 "Payload path has a reparse ancestor")
    return p


def read(file, expected=None, maximum=32 * 1024 * 1024):
    file = path(file)
    info = file.stat()
    need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= maximum, "Payload input is not a bounded regular file")
    raw = file.read_bytes()
    need(len(raw) == info.st_size and len(raw) <= maximum, "Payload input changed while reading")
    if expected is not None:
        need(isinstance(expected, str) and re.fullmatch("[a-f0-9]{64}", expected), "Exact SHA256 is required")
        need(hashlib.sha256(raw).hexdigest() == expected, "Bound payload input SHA differs")
    return raw


def write_new(file, raw):
    path(file.parent)
    with file.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bound-manifest", required=True)
    parser.add_argument("--bound-manifest-sha256", required=True)
    parser.add_argument("--scope-json", required=True)
    parser.add_argument("--scope-sha256", required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    manifest_file, scope_file, record = map(path, (args.bound_manifest, args.scope_json, args.record))
    manifest = json.loads(read(manifest_file, args.bound_manifest_sha256).decode("utf-8-sig"))
    scope = json.loads(read(scope_file, args.scope_sha256).decode("utf-8-sig"))
    need(manifest.get("schema") == 1 and scope.get("schema") == 1, "Unknown payload binding schema")
    need(manifest.get("engineering_delivery_scope_sha256") == args.scope_sha256,
         "Bound source manifest and scope differ")
    need(path(manifest["scope_file"]) == scope_file, "Manifest scope source differs")
    root = path(scope["engineering_root"])
    runtime = path(scope["runtime_root"])
    need(root.is_dir() and runtime.is_dir() and not root.is_relative_to(runtime)
         and not runtime.is_relative_to(root), "Immutable payload and runtime must be disjoint")
    need(manifest_file.is_relative_to(runtime), "Bound manifest must remain in its declared runtime")
    need(record.is_relative_to(manifest_file.parent) and not os.path.lexists(record),
         "Promotion record must be a new file under this bound output")
    need(manifest.get("original_task_profiles_overwritten") is False
         and manifest.get("payload_promotion_performed") is False,
         "Only an unpromoted isolated evidence payload is accepted")
    rows = manifest.get("relocated_owned_dependencies")
    need(isinstance(rows, list) and rows, "Bound manifest has no immutable dependency files")
    plan, seen = [], set()
    for row in rows:
        source, target = path(row["staged_file"]), path(row["planned_file"])
        need(source.is_relative_to(manifest_file.parent), "Staged source escapes its bound directory")
        need(target != root and target.is_relative_to(root), "Payload destination escapes EngineeringRoot")
        key = os.path.normcase(str(target))
        need(key not in seen and not os.path.lexists(target), "Payload destination repeats or already exists")
        seen.add(key)
        raw = read(source, row["sha256"])
        plan.append((source, target, row["sha256"], len(raw)))
    result = {"schema": 1, "utc": datetime.now(timezone.utc).isoformat(),
              "kind": "immutable own ABI payload promotion", "file_count": len(plan),
              "engineering_root": str(root), "bound_manifest_sha256": args.bound_manifest_sha256,
              "engineering_delivery_scope_sha256": args.scope_sha256,
              "host_invoked": False, "activated": False, "old_profiles_overwritten": False,
              "committed": args.commit, "files": [{"source": str(a), "target": str(b),
                  "sha256": c, "bytes": n} for a, b, c, n in plan]}
    if args.commit:
        for source, target, sha, size in plan:
            # Recheck exactly each selected source and target, with no broad
            # catch/retry/rollback. A partial failure preserves every new file.
            raw = read(source, sha)
            need(len(raw) == size and not os.path.lexists(target), "Payload changed since planning")
            target.parent.mkdir(parents=True, exist_ok=True)
            path(target.parent)
            write_new(target, raw)
            read(target, sha)
        write_new(record, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
