"""TARGET SIDE: resolve native DATA and deploy one unchanged precompiled DLL.

No C# generation, Csc, editor start, injection or project operation takes place.
Only the current installation's supported functions become available; unresolved
entries retain feature-local failures instead of an author-version whitelist.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import time
import uuid

from portable_support import ROOT, BINDING_SCHEMA, CONTRACT, PORTABLE_FIELDS, binder_module, digest, encoded, need, reference_aliases, source_key, validate_portable_scope, write_new


class PreparationProgress:
    """Atomic, file-only preparation snapshots; never an online-ready receipt."""
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.started = time.perf_counter()
        self.started_utc = datetime.now(timezone.utc).isoformat()
        self.previous = None
        self.last_echo = 0.0

    def __call__(self, row):
        if not isinstance(row, dict) or not isinstance(row.get("phase"), str):
            raise ValueError("Preparation progress must provide a phase dictionary")
        self.emit(row["phase"], **{key: value for key, value in row.items()
                                   if key not in {"schema", "status", "phase", "started_at_utc",
                                                  "updated_at_utc", "elapsed_seconds", "materialization_complete",
                                                  "vendor_invoked", "host_invoked", "compiled", "automatic_retry"}})

    def emit(self, phase, status="running", **details):
        elapsed = time.perf_counter() - self.started
        value = {"schema": "mcgs-portable-engine-progress/v1", "status": status,
                 "phase": phase, "started_at_utc": self.started_utc,
                 "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                 "elapsed_seconds": round(elapsed, 3),
                 "materialization_complete": status == "completed",
                 "vendor_invoked": False, "host_invoked": False, "compiled": False,
                 "automatic_retry": False, **details}
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(encoded(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
        if self.previous is None or self.previous.get("phase") != phase or status != "running" or elapsed - self.last_echo >= 5:
            count = ""
            if "completed" in value and "total" in value:
                count = " {}/{}".format(value["completed"], value["total"])
            print("[prepare] {}{} ({:.1f}s)".format(phase, count, elapsed), file=sys.stderr, flush=True)
            self.last_echo = elapsed
        self.previous = value

    def failed(self, error):
        previous = self.previous or {}
        self.emit("failed", status="failed", last_phase=previous.get("phase"),
                  error={"type": type(error).__name__, "message": str(error)},
                  partial_work_preserved=True)


def _report(progress, phase, **details):
    if progress is not None:
        progress.emit(phase, **details)


def resolve_source_tables(target):
    """Derive runtime maps from resolution evidence, without transforming C#."""
    from pe32 import PE32
    addresses, guards, ordinals = {}, {}, {}
    for entry in target.source_catalog["entries"]:
        if entry.get("status") != "confirmed":
            continue
        alias, old = entry["module"], entry["reference_rva"]
        mapped = target.result["rva_maps"].get(alias, {}).get(hex(old))
        value = mapped["actual_rva"] if mapped else None
        if value is not None:
            if entry["address_kind"] == "preferred_PE_VA_literal":
                value += target.result["modules"][alias]["actual"]["image_base"]
            elif entry["address_kind"] == "reference_base_encoded_RVA":
                value += entry["output_preferred_base"]
        row = {"source": PureWindowsPath(entry["source"]).name, "module": alias,
               "reference_rva": old, "actual_rva": mapped["actual_rva"] if mapped else None,
               "encoded_value": value, "emitted_numeric_value": value,
               "address_kind": entry["address_kind"], "status": "resolved" if mapped else "unresolved",
               "span": [entry["start"], entry["end"]]}
        addresses[source_key(entry)] = row
        target.source_changes.append(row)
    for guard in target.source_catalog.get("source_guards", []):
        alias, old = guard["module"], guard["reference_rva"]
        match = next((item for item in target.result["functions"] if item["module"] == alias
                      and item["reference_rva"] == old and item["status"] == "resolved"
                      and len(item.get("guard_bytes_at_reference_preferred_base", "")) == 2 * guard["length"]), None)
        mapped = target.result["rva_maps"].get(alias, {}).get(hex(old))
        state = {"id": guard["id"], "module": alias, "reference_rva": old,
                 "actual_rva": mapped["actual_rva"] if mapped else None, "length": guard["length"],
                 "status": "verified" if match else "unresolved",
                 "reference_preferred_base": target.catalog["reference_modules"][alias]["image_base"],
                 "details": "Resolved current full source guard" if match else "Full source guard was not uniquely located"}
        if match:
            state.update(actual_rva=match["actual_rva"], bytes_at_reference_preferred_base=match["guard_bytes_at_reference_preferred_base"],
                         highlow_offsets=match["actual_relocation_offsets"], proof_id=match["proof_id"])
        guards[guard["id"]] = state
        target.guard_changes.append(state)
    images = {}
    for ordinal in target.source_catalog.get("source_ordinals", []):
        alias, old, rva = ordinal["module"], ordinal["reference_ordinal"], ordinal["reference_rva"]
        mapped = target.result["rva_maps"].get(alias, {}).get(hex(rva))
        actual = proof = None
        if mapped and alias in target.actual_module_paths:
            if alias not in images:
                images[alias] = PE32(target.actual_module_paths[alias])
            pe, goal = images[alias], mapped["actual_rva"]
            same = pe.exports_by_ordinal.get(old)
            if same and same["rva"] == goal and not same.get("forwarder"):
                actual, proof = old, "Current original ordinal exports the uniquely located target"
            else:
                names = {export for row in target.catalog["signatures"] if row["module"] == alias and row["reference_rva"] == rva for export in row.get("exports", [])}
                named = {pe.exports[name]["ordinal"] for name in names if name in pe.exports and pe.exports[name]["rva"] == goal and not pe.exports[name].get("forwarder")}
                candidates = {number for number, row in pe.exports_by_ordinal.items() if row["rva"] == goal and not row.get("forwarder")}
                if len(named) == 1:
                    actual, proof = next(iter(named)), "Unique matching named export for the located target"
                elif len(candidates) == 1:
                    actual, proof = next(iter(candidates)), "Unique actual ordinal for the located target"
        state = {"source": PureWindowsPath(ordinal["source"]).name, "span": [ordinal["start"], ordinal["end"]],
                 "module": alias, "reference_ordinal": old, "reference_rva": rva, "actual_ordinal": actual,
                 "actual_rva": mapped["actual_rva"] if mapped else None,
                 "status": "verified" if actual is not None else "unresolved", "proof": proof}
        ordinals[source_key(ordinal, "o")] = state
        target.ordinal_changes.append(state)
    return addresses, guards, ordinals


def _materialize(scope_base_json, engine_file, engine_sha256, output_directory, source_stage=None,
                 engine_file_name=None, abi_catalog=None, actual_modules=None, progress=None, abi_cache_root=None):
    started = time.perf_counter()
    legacy = binder_module()
    from abi_binding import TargetBinding
    from native_delivery_config import validate_mapping
    from managed_pe import ManagedImage, verify_scope_binding
    stage = Path(source_stage or ROOT / "delivery/source").resolve()
    output, engine = Path(output_directory).resolve(), Path(engine_file).resolve()
    name = engine_file_name or engine.name
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.dll", name), "Engine name must be one DLL basename")
    raw_engine = engine.read_bytes()
    need(re.fullmatch(r"[a-f0-9]{64}", engine_sha256) and digest(raw_engine) == engine_sha256, "Published OWN engine SHA differs")
    identity = verify_scope_binding(raw_engine, "0" * 64)
    need(identity.get("runtime_scope_binding") == CONTRACT, "Selected DLL is not the generic precompiled engine")
    need(not output.exists() or output.is_dir() and not any(output.iterdir()), "Materialization output must be new/empty; do not replay partial work")
    config = json.loads(Path(scope_base_json).read_text(encoding="utf-8-sig"))
    need(not PORTABLE_FIELDS.intersection(config), "Provide fresh base scope, not a previous portable binding")
    base_raw = encoded(config)
    layout = validate_mapping(config, output / Path(name).with_suffix(".scope.json"), digest(base_raw))
    need(layout.transport_client_file.parent == layout.runtime_root, "The at-most-once queue client must be in runtime_root because its own directory is the queue root")
    need(output.is_relative_to(layout.runtime_root), "Preparation output must be inside this connection's runtime")
    need(not any(layout.engineering_root.iterdir()), "Portable engineering payload must be new and empty")
    manifest_raw = (stage / "source-and-dependency-manifest.json").read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    own_image = ManagedImage(raw_engine)
    own_type = "McgsInternalBridge.NativePortableRuntime"
    need(own_image.string_constant(own_type, "SourceManifestSha256") == digest(manifest_raw), "Published OWN engine and source data release differ")
    need(own_image.string_constant(own_type, "SourceCatalogSha256") == digest((ROOT / "abi-adapter/catalogs/source-addresses.json").read_bytes()), "Published OWN engine and source map release differ")
    compact = own_image.string_constant(own_type, "EvidenceLayout", optional=True) == "flat-v1"

    # Keep logical names for the ABI catalog. A flat-capable DLL routes both
    # historical spellings to one immutable file under its evidence root.
    proof_names = {row["task_relative_file"]: row["task_relative_file"] + ".txt"
                   for row in manifest["owned_artifacts"] if Path(row["task_relative_file"]).suffix.casefold() == ".cs"}
    old_engineering = PureWindowsPath(manifest["original_engineering_relative_root"])
    artifact_targets = {}
    artifact_paths = {}
    for ordinal, row in enumerate(manifest["owned_artifacts"]):
        relative = row["task_relative_file"]
        deployed = PureWindowsPath(proof_names.get(relative, relative))
        targets = [layout.evidence_root.joinpath(*deployed.parts)]
        if deployed.is_relative_to(old_engineering):
            targets.append(layout.engineering_root.joinpath(*deployed.relative_to(old_engineering).parts))
        if compact:
            short_path = layout.evidence_root / "a" / (f"{ordinal:03x}" + deployed.suffix)
            logical = PureWindowsPath(relative)
            targets.append(layout.evidence_root.joinpath(*logical.parts))
            if logical.is_relative_to(old_engineering):
                targets.append(layout.engineering_root.joinpath(*logical.relative_to(old_engineering).parts))
            for logical_path in targets:
                key = str(logical_path)
                need(artifact_paths.setdefault(key, str(short_path)) == str(short_path),
                     "Owned evidence alias collision: " + key)
            targets = [short_path]
        for target_path in targets:
            if os.name == "nt":
                file_units = len(str(target_path).encode("utf-16-le")) // 2
                parent_units = len(str(target_path.parent).encode("utf-16-le")) // 2
                need(file_units < 260 and parent_units < 248,
                     "Native evidence exceeds the .NET path limit; use a shorter connection directory: " + str(target_path))
        artifact_targets[relative] = targets
    output.mkdir(parents=True, exist_ok=True)
    resolution_started = time.perf_counter()
    _report(progress, "native_data_resolution")
    callbacks = {"progress_callback": progress} if progress is not None else {}
    target = TargetBinding(stage, manifest, layout, output / "abi", abi_catalog, actual_modules,
                           cache_root=abi_cache_root, compact_profiles=compact, **callbacks)
    _report(progress, "source_address_tables")
    addresses, guards, ordinals = resolve_source_tables(target)
    resolution_seconds = time.perf_counter() - resolution_started
    _report(progress, "profile_materialization", source_addresses=len(addresses),
            source_guards=len(guards), source_ordinals=len(ordinals),
            total=len(manifest["owned_artifacts"]))
    aliases = reference_aliases(stage, manifest, legacy.COMMON_PROFILE_PIN_CONTRACTS)
    path, source_paths = legacy.path_rewriter(manifest["original_task_root"], manifest["original_install_root"],
                                              str(layout.evidence_root), str(layout.install_root), str(layout.program_root), str(layout.editor_executable))
    # One immutable C# review artifact is DATA, not an engine source input. Keep
    # it explicitly as .cs.txt so target preparation never emits a C# source.
    proof_paths = {str(layout.evidence_root / old).casefold(): str(layout.evidence_root / new) for old, new in proof_names.items()}
    artifacts = {}
    for row in manifest["owned_artifacts"]:
        relative = row["task_relative_file"]
        file = stage / "artifacts" / relative
        raw = target.overrides.get(relative)
        if raw is None:
            raw = file.read_bytes()
        text = raw.decode("utf-8-sig")
        if file.suffix == ".json":
            def visit(value, key=None):
                if isinstance(value, dict):
                    return {k: visit(v, k) for k, v in value.items()}
                if isinstance(value, list):
                    return [visit(v) for v in value]
                value = target.module_file_value(path(value), key)
                return proof_paths.get(value.casefold(), value) if isinstance(value, str) else value
            text = encoded(visit(json.loads(text))).decode("utf-8")
        else:
            text = source_paths(target.source_module_paths(text, manifest["original_install_root"]))
        artifacts[relative] = {"source": file, "text": text}
    resolved, resolving = {}, set()
    hash_token = re.compile(r"(?<![a-fA-F0-9])[a-f0-9]{64}(?![a-fA-F0-9])")
    def materialize_artifact(relative):
        if relative in resolved:
            return resolved[relative]
        need(relative not in resolving, "Owned profile SHA dependency cycle: " + relative)
        resolving.add(relative)
        row = artifacts[relative]
        def replace(match):
            other = aliases.get(match.group(0))
            return match.group(0) if other is None else digest(materialize_artifact(other))
        if row["source"].suffix == ".json":
            def rehash(value, provenance=False):
                if isinstance(value, dict):
                    return {key: rehash(item, provenance or key == "_mcgs_abi_resolution") for key, item in value.items()}
                if isinstance(value, list):
                    return [rehash(item, provenance) for item in value]
                return hash_token.sub(replace, value) if isinstance(value, str) and not provenance else value
            raw = encoded(rehash(json.loads(row["text"])))
        else:
            raw = hash_token.sub(replace, row["text"]).encode("utf-8")
        resolving.remove(relative)
        resolved[relative] = raw
        return raw
    for relative in artifacts:
        materialize_artifact(relative)
    _report(progress, "artifact_write", total=len(resolved))
    copied = []
    destinations = {}
    for relative, raw in resolved.items():
        for destination in artifact_targets[relative]:
            if destination in destinations:
                need(destinations[destination] == digest(raw), "Owned evidence destination collision")
                continue
            write_new(destination, raw)
            destinations[destination] = digest(raw)
            copied.append({"planned_file": str(destination), "sha256": digest(raw), "original_relative_file": relative})
    _report(progress, "binding_write", artifacts_written=len(copied))
    index_file = layout.evidence_root / "abi-target-profile-index.json"
    index_raw = encoded(target.index(resolved, layout, copied))
    need(len(index_raw) <= 16 * 1024 * 1024, "Native data index exceeds managed parser bound")
    write_new(index_file, index_raw)
    binding = {"schema": BINDING_SCHEMA, "engine_contract": CONTRACT,
               "source_manifest_sha256": digest(manifest_raw),
               "source_catalog_sha256": digest((ROOT / "abi-adapter/catalogs/source-addresses.json").read_bytes()),
               "profile_index_file": str(index_file), "profile_index_sha256": digest(index_raw),
               "source_addresses": addresses, "source_guards": guards, "source_ordinals": ordinals,
               "artifact_sha256": {relative: digest(raw) for relative, raw in resolved.items()},
               "module_files": {alias: str(file) for alias, file in target.actual_module_paths.items()},
               "vendor_whole_file_sha_admission": False, "feature_scoped_failure": True,
               "target_source_generation": False, "target_compiler_required": False}
    if compact:
        binding["artifact_paths"] = artifact_paths
    binding_file = layout.engineering_root / "portable-engine-binding.json"
    binding_raw = encoded(binding)
    write_new(binding_file, binding_raw)
    config.update(portable_engine_contract=CONTRACT, portable_binding_file=str(binding_file), portable_binding_sha256=digest(binding_raw))
    scope_raw = encoded(config)
    scope_file = output / Path(name).with_suffix(".scope.json")
    # Verify metadata against this portable contract before making the engine
    # selectable. Legacy bound engines are not mistaken for generic engines.
    identity = verify_scope_binding(raw_engine, digest(scope_raw))
    need(identity.get("runtime_scope_binding") == CONTRACT, "Selected DLL is not the generic precompiled engine")
    validate_portable_scope(config)
    write_new(output / name, raw_engine)
    write_new(scope_file, scope_raw)
    result = {"schema": "mcgs-portable-engine-materialization/v1", "engine_contract": CONTRACT,
              "engine_file": str(output / name), "engine_sha256": engine_sha256,
              "engine_scope_file": str(scope_file), "scope_sha256": digest(scope_raw),
              "engineering_delivery_scope_sha256": digest(scope_raw),
              "binding_file": str(binding_file), "binding_sha256": digest(binding_raw),
              "profile_index_file": str(index_file), "profile_index_sha256": digest(index_raw),
              "evidence_layout": "flat-v1" if compact else "legacy",
              "copied_artifacts": copied, "native_api_resolution": target.summary(),
              "timings_seconds": {"native_data_resolution": resolution_seconds, "total": time.perf_counter() - started},
              "compiled": False, "target_source_generation": False, "target_compiler_required": False,
              "engine_bytes_unchanged": True, "vendor_invoked": False, "host_invoked": False}
    write_new(output / "materialization-manifest.json", encoded(result))
    return result


def materialize(scope_base_json, engine_file, engine_sha256, output_directory, source_stage=None,
                engine_file_name=None, abi_catalog=None, actual_modules=None, progress_file=None, abi_cache_root=None):
    """Prepare files with optional atomic progress, preserving the original API.

    A running snapshot after a killed process is partial work, not permission
    to replay preparation or a native engineering request.
    """
    progress = PreparationProgress(progress_file) if progress_file is not None else None
    try:
        _report(progress, "validation")
        result = _materialize(scope_base_json, engine_file, engine_sha256, output_directory,
                              source_stage, engine_file_name, abi_catalog, actual_modules, progress, abi_cache_root)
        if progress is not None:
            progress.emit("completed", status="completed", engine_file=result["engine_file"],
                          materialization_manifest=str(Path(output_directory) / "materialization-manifest.json"),
                          meaning="File preparation completed; host connection and native project checks were not performed")
        return result
    except BaseException as error:
        if progress is not None:
            try:
                progress.failed(error)
            except (OSError, ValueError, TypeError):
                # Preserve the actual preparation failure if diagnostic output
                # itself became unavailable; no successful result is emitted.
                pass
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-base-json", required=True)
    parser.add_argument("--engine-file", required=True)
    parser.add_argument("--engine-sha256", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--source-stage", default=str(ROOT / "delivery/source"))
    parser.add_argument("--engine-file-name")
    parser.add_argument("--abi-catalog")
    parser.add_argument("--abi-cache-root", help="Reuse verified static PE resolution across connections")
    parser.add_argument("--progress-file", help="Atomic preparation-phase JSON; does not start or inspect Pro")
    parser.add_argument("--actual-module", action="append", default=[])
    args = parser.parse_args()
    binder_module()
    from module_selection import parse_module_overrides
    print(json.dumps(materialize(args.scope_base_json, args.engine_file, args.engine_sha256, args.output_directory,
                                 args.source_stage, args.engine_file_name, args.abi_catalog,
                                 parse_module_overrides(args.actual_module), args.progress_file, args.abi_cache_root), ensure_ascii=False, indent=2))
