"""Portable thin entry for the existing Pro internal engineering clients.

Stage is files only; inspect/run/apply submit to the
already configured stable queue and retain its at-most-once semantics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from native_delivery_config import configure


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--scope-config", default=os.environ.get("MCGS_NATIVE_SCOPE_CONFIG"), help="Connection layout; can be set once by MCGS_NATIVE_SCOPE_CONFIG")
    parser.add_argument("--scope-sha256", default=None, help="Optional exact connection-layout pin; computed from selected layout by default")
    options, rest = parser.parse_known_args()
    if not rest or any(value in ('-h', '--help') for value in rest):
        parser.print_help()
        print('\nCommands: layout, inspect, execute/apply, stage, run, close-reopen, lifecycle-read.')
        print('Direct edit: execute --project PROJECT.mcp --spec edit.json [--out result.json]')
        print('Program: stage --program program.json --directory NEW_SESSION; run --directory NEW_SESSION')
        print('Direct run merges compatible same-page edits (default8 actions; --max-merged-actions N). --no-merge-steps disables merging; inspect/save/check/page switches stay separate.')
        print('Pipeline: --prepare-workers N (default1,0 disables lookahead), --io-workers N (default1); all output writers drain before run returns.')
        print('Lifecycle: close-reopen --project PROJECT.mcp [--closed-copy snapshot.mcp]')
        print('Select a connection once with --scope-config or MCGS_NATIVE_SCOPE_CONFIG. No permit is required.')
        return 0
    if not options.scope_config:
        adjacent = Path(__file__).with_name("connection.scope.json")
        if not adjacent.is_file():
            raise ValueError("Choose a native bridge connection with --scope-config or MCGS_NATIVE_SCOPE_CONFIG")
        options.scope_config = str(adjacent)
    scope_sha = options.scope_sha256 or hashlib.sha256(Path(options.scope_config).read_bytes()).hexdigest()
    layout = configure(options.scope_config, scope_sha)
    if not rest or rest[0] not in {"layout", "stage", "run", "inspect", "prepare", "apply", "execute",
                                  "lifecycle-read", "prepare-close-reopen", "close-reopen"}:
        raise ValueError("Use layout/stage/run/inspect/execute/apply/prepare/lifecycle-read/prepare-close-reopen/close-reopen; no arbitrary native operation is exposed")
    if rest[0] == "layout":
        if len(rest) != 1:
            raise ValueError("layout takes no additional fields")
        layout.check()
        print(json.dumps({"ok": True, "configuration_sha256": layout.configuration_sha256,
                          "task_root": str(layout.task_root), "engineering_root": str(layout.engineering_root),
                          "runtime_root": str(layout.runtime_root), "working_root": str(layout.working_root),
                          "evidence_root": str(layout.evidence_root),
                          "host_invoked": False}, ensure_ascii=False, indent=2))
        return 0
    sys.argv = [sys.argv[0], *rest]
    if rest[0] in {"lifecycle-read", "prepare-close-reopen", "close-reopen"}:
        import project_lifecycle_client
        return project_lifecycle_client.main()
    if rest[0] in {"stage", "run"}:
        import engineering_session
        return engineering_session.main()
    import edit_batch_client
    return edit_batch_client.main()


if __name__ == "__main__":
    raise SystemExit(main())
