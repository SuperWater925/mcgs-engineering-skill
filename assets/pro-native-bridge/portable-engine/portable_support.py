"""Shared release/target DATA contracts for the precompiled portable engine.

This module never starts an editor, generates target C#, or invokes a compiler.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = "mcgs-portable-engine/v1"
BINDING_SCHEMA = "mcgs-portable-engine-binding/v1"
PORTABLE_FIELDS = {"portable_engine_contract", "portable_binding_file", "portable_binding_sha256"}
SHA = re.compile(r"[a-f0-9]{64}")


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_new(file, raw):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("xb") as stream:
        stream.write(raw)
        stream.flush()


def binder_module():
    for folder in (ROOT / "delivery", ROOT / "delivery/device-entry-v2", ROOT / "abi-adapter", ROOT / "bootstrap"):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("mcgs_portable_legacy_binder", ROOT / "delivery/bind_common_delivery.v5.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_key(row, kind="a"):
    return kind + ":" + PureWindowsPath(row["source"]).name + ":" + str(row["start"]) + ":" + str(row["end"])


def reference_aliases(stage, manifest, common_pins):
    aliases = {}
    for row in manifest["owned_artifacts"]:
        relative = row["task_relative_file"]
        need(digest((Path(stage) / "artifacts" / relative).read_bytes()) == row["sha256"], "Owned dependency changed: " + relative)
        # Identical immutable files may occur under several evidence roles.
        # Match the existing dependency DAG's canonical first-content alias.
        aliases.setdefault(row["sha256"], relative)
        for value in row.get("origin_sha256_aliases", []):
            need(isinstance(value, str) and SHA.fullmatch(value), "Invalid owned SHA alias")
            need(value not in aliases or aliases[value] == relative, "Owned SHA alias collision")
            aliases[value] = relative
    known = {row["task_relative_file"] for row in manifest["owned_artifacts"]}
    for value, relative in common_pins.items():
        need(relative in known and (value not in aliases or aliases[value] == relative), "Named owned SHA alias differs: " + relative)
        aliases[value] = relative
    return aliases


def validate_portable_scope(scope, verify_files=True):
    """Optional extension; legacy scopes remain unchanged and return None."""
    present = PORTABLE_FIELDS.intersection(scope)
    if not present:
        return None
    need(present == PORTABLE_FIELDS and scope["portable_engine_contract"] == CONTRACT, "Portable engine scope contract differs")
    file = Path(scope["portable_binding_file"])
    need(file.is_absolute() and file.resolve().is_relative_to(Path(scope["engineering_root"]).resolve()), "Portable binding must be inside its declared engineering payload")
    need(isinstance(scope["portable_binding_sha256"], str) and SHA.fullmatch(scope["portable_binding_sha256"]), "Portable binding requires its actual SHA")
    if not verify_files:
        return None
    raw = file.read_bytes()
    need(digest(raw) == scope["portable_binding_sha256"], "Portable binding bytes differ")
    binding = json.loads(raw.decode("utf-8-sig"))
    need(binding.get("schema") == BINDING_SCHEMA and binding.get("engine_contract") == CONTRACT, "Portable binding schema differs")
    index = Path(binding["profile_index_file"])
    need(index.is_absolute() and index.resolve().is_relative_to((Path(scope["engineering_root"]) / "task-evidence").resolve()), "Portable index escapes evidence root")
    need(SHA.fullmatch(binding["profile_index_sha256"]) and digest(index.read_bytes()) == binding["profile_index_sha256"], "Portable index SHA differs")
    return binding
