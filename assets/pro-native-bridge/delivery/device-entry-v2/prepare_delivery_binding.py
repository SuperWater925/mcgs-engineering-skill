"""Prepare a new portable layout/source binding using files only.

This never starts Pro, submits a request, builds a DLL, or activates an engine.
All directories are explicit. Outputs use CreateNew semantics in a new owned
staging directory; copying a config beside a compiled DLL remains a later step.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from native_delivery_config import TRANSPORT_SHA256, _absolute, _not_reparse, _regular, validate_mapping


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_new(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(args):
    engine_name = args.engine_file_name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.dll", engine_name):
        raise ValueError("engine-file-name must be a single explicit DLL filename")
    output = _absolute(args.output_directory)
    if os.path.lexists(output) and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("Binding output directory is not empty; preserve its existing files")
    source = _absolute(args.layout_source)
    source_bytes = _regular(source, 1024 * 1024)
    source_sha = digest(source_bytes)
    if source_sha != args.layout_source_sha256 or re.fullmatch("[a-f0-9]{64}", args.layout_source_sha256) is None:
        raise ValueError("Unbound layout source SHA differs")
    source_text = source_bytes.decode("utf-8")
    token = 'ExpectedConfigurationSha256="PENDING"'
    if source_text.count(token) != 1:
        raise ValueError("Layout source is not the single unbound PENDING candidate")
    values = {"schema": 1, "task_root": str(_absolute(args.task_root)),
              "engineering_root": str(_absolute(args.engineering_root)),
              "runtime_root": str(_absolute(args.runtime_root)),
              "install_root": str(_absolute(args.install_root)),
              "transport_client_file": str(_absolute(args.transport_client_file)),
              "transport_client_sha256": TRANSPORT_SHA256}
    if getattr(args, "editor_executable", None):
        values["editor_executable"] = str(_absolute(args.editor_executable))
    config_bytes = encoded(values)
    config_sha = digest(config_bytes)
    config_name = Path(engine_name).with_suffix(".scope.json").name
    layout = validate_mapping(values, output / config_name, config_sha)
    if output == layout.task_root or not output.is_relative_to(layout.task_root):
        raise ValueError("Binding output must be a child of the explicit owned task root")
    if output.is_relative_to(layout.engineering_root):
        raise ValueError("Binding generation cannot write inside frozen engineering payload")
    replacement = 'ExpectedConfigurationSha256="' + config_sha + '"'
    bound_bytes = source_text.replace(token, replacement).encode("utf-8")
    if bound_bytes.replace(replacement.encode("utf-8"), token.encode("utf-8")) != source_bytes:
        raise ValueError("Bound source delta is not exactly reversible")
    manifest = {"schema": 1, "utc": datetime.now(timezone.utc).isoformat(),
                "kind": "file-only-portable-layout-binding", "host_invoked": False,
                "compiled": False, "activated": False, "project_bound": False,
                "pid_bound": False, "engine_file_name": engine_name,
                "configuration_file_name": config_name,
                "configuration_sha256": config_sha,
                "unbound_layout_source": str(source), "unbound_layout_source_sha256": source_sha,
                "bound_layout_source_file_name": "NativeEngineeringDeliveryLayout.cs",
                "bound_layout_source_sha256": digest(bound_bytes),
                "delta": "Only ExpectedConfigurationSha256 PENDING literal is replaced; no native ABI guard changes",
                "transport_client_file": str(layout.transport_client_file),
                "transport_client_sha256": layout.transport_client_sha256,
                "request_scope_field": "engineering_delivery_scope_sha256",
                "required_followup": ["Integrate the common portable core/profile/output patches",
                                      "Compile the bound source with exact frozen source/profile inputs",
                                      "Place the exact config bytes beside the matching DLL before activation",
                                      "Use a fresh request.expected_project and native inspection; never reuse old claims"]}
    # All validation above finishes before the one new directory is claimed.
    # A later file error leaves the partial directory intact; it is not retried.
    _not_reparse(output.parent)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("Binding output directory gained existing files before writing; preserve them")
    write_new(output / config_name, config_bytes)
    write_new(output / "NativeEngineeringDeliveryLayout.cs", bound_bytes)
    write_new(output / "binding-manifest.json", encoded(manifest))
    return {"ok": True, "output_directory": str(output), **manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("task-root", "engineering-root", "runtime-root", "install-root", "transport-client-file",
                 "engine-file-name", "layout-source", "layout-source-sha256", "output-directory"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--editor-executable", help="Explicit PE32/I386 editor path; omitted keeps the legacy InstallRoot/Program/McgsSetPro.exe layout")
    args = parser.parse_args()
    result = prepare(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
