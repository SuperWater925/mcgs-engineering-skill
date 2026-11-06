"""RELEASE SIDE: generate the single portable engine's managed sources.

No target installation is inspected. Compilation is a separate release action;
recipients receive the unchanged DLL and never run this builder or Csc.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path, PureWindowsPath
import re
import sys

from portable_support import ROOT, CONTRACT, binder_module, digest, encoded, need, reference_aliases, source_key, write_new


def _runtime_expression(name, row, kind):
    return "NativePortableRuntime." + name + "(" + json.dumps(source_key(row, kind)) + ")"


def patch_catalogued_source(name, text, catalog):
    from inventory import arguments, mask_csharp
    masked, unused = mask_csharp(text)
    patches = {}
    counts = Counter()
    for entry in catalog["entries"]:
        if entry.get("status") != "confirmed" or PureWindowsPath(entry["source"]).name != name:
            continue
        start, end = entry["start"], entry["end"]
        need(text[start:end] == entry["original_literal"], "Classified address source span changed: " + name)
        expression = _runtime_expression("Address", entry, "a")
        if entry["address_kind"] == "PE_RVA_constant":
            # Consts remain valid C# compile-time metadata. Every classified
            # pointer-producing consumer reads the current runtime table.
            symbol = re.search(r"(\w+)\s*=\s*$", masked[:start])
            need(symbol is not None, "Classified address const has no symbol")
            found = 0
            for consumer in entry["consumers"]:
                opening = masked.find("(", consumer["offset"])
                unused_end, spans = arguments(masked, opening)
                need(spans, "Classified const consumer is incomplete")
                for a, b in spans:
                    for match in re.finditer(r"\b" + re.escape(symbol.group(1)) + r"\b", masked[a:b]):
                        span = (a + match.start(), a + match.end())
                        need(span not in patches or patches[span] == expression, "Classified const consumers overlap")
                        patches[span] = expression
                        found += 1
            need(found, "Classified const has no runtime consumer")
        else:
            patches[start, end] = expression
        counts["source_addresses"] += 1
    for field, kind in (("source_guards", "g"), ("source_ordinals", "o")):
        for row in catalog.get(field, []):
            if PureWindowsPath(row["source"]).name != name:
                continue
            a, b = row["start"], row["end"]
            need(text[a:b] == row["original_literal"], "Classified " + field + " source span changed: " + name)
            patches[a, b] = ("NativePortableRuntime.GuardHex(" + json.dumps(row["id"]) + ")") if kind == "g" else _runtime_expression("Ordinal", row, kind)
            counts[field] += 1
    next_start = len(text)
    for (a, b), value in sorted(patches.items(), reverse=True):
        need(b <= next_start, "Portable source replacements overlap")
        text = text[:a] + value + text[b:]
        next_start = a
    # A guard may have been a const string field. Runtime expressions must
    # never be left in a const declaration (including multi-field declarations).
    text = deconst_runtime_fields(text)
    return text, counts


def local_declaration(masked, position):
    stack, boundary = [], 0
    for match in re.finditer(r"[{};]", masked[:position]):
        char = match.group()
        if char == "{":
            header = masked[boundary:match.start()]
            stack.append("type" if re.search(r"\b(?:namespace|class|struct|interface|enum)\b", header) else "block")
        elif char == "}" and stack:
            stack.pop()
        boundary = match.end()
    return "block" in stack


def deconst_runtime_fields(text):
    from inventory import mask_csharp
    masked, unused = mask_csharp(text)
    patches = []
    for match in re.finditer(r"\bconst\s+(?:string|int|uint|long|ulong)\b", masked):
        end = masked.find(";", match.end())
        need(end >= 0, "Const declaration is incomplete")
        if "NativePortableRuntime." in text[match.end():end]:
            patches.append((match.start(), match.start() + len("const"), "" if local_declaration(masked, match.start()) else "static readonly"))
    for a, b, value in reversed(patches):
        text = text[:a] + value + text[b:]
    return text


def patch_owned_literals(text, aliases, manifest, catalog):
    from inventory import mask_csharp
    unused, strings = mask_csharp(text)
    module_names = {row.get("basename", "").casefold(): alias for alias, row in catalog["reference_modules"].items()}
    task = str(PureWindowsPath(manifest["original_task_root"]))
    install = str(PureWindowsPath(manifest["original_install_root"]))
    old_editor = str(PureWindowsPath(install) / "Program/McgsSetPro.exe")
    old_program = str(PureWindowsPath(install) / "Program")
    patches, counts = [], Counter()
    for a, b, value in strings:
        expression = None
        if value in aliases:
            expression = "NativePortableRuntime.ArtifactSha(" + json.dumps(aliases[value]) + ")"
            counts["artifact_sha_lookups"] += 1
        else:
            windows = value.replace("/", "\\")
            basename = PureWindowsPath(windows).name.casefold()
            if PureWindowsPath(windows).is_absolute() and basename in module_names:
                expression = "NativePortableRuntime.ModuleFile(" + json.dumps(module_names[basename]) + ")"
                counts["module_file_lookups"] += 1
            elif windows.casefold() == old_editor.casefold():
                expression = "NativeEngineeringDeliveryLayout.EditorExecutable"
            else:
                for old, root in ((old_program, "ProgramRoot"), (task, "EvidenceRoot"), (install, "InstallRoot")):
                    if windows.casefold() == old.casefold() or windows.casefold().startswith(old.casefold().rstrip("\\") + "\\"):
                        tail = windows[len(old):].lstrip("\\")
                        expression = "NativeEngineeringDeliveryLayout." + root
                        if tail:
                            expression = "Path.Combine(" + expression + ",@\"" + tail.replace('"', '""') + "\")"
                        counts["root_lookups"] += 1
                        break
        if expression:
            patches.append((a, b, expression))
    for a, b, value in reversed(patches):
        text = text[:a] + value + text[b:]
    return deconst_runtime_fields(text), counts


def propagate_runtime_string_aliases(prepared):
    """A const alias of a now-runtime digest must also become readonly.

    Keep literal key/kind constants usable in case labels. This only follows
    string field dependencies of runtime readonly fields, including aliases in
    other owned source files, rather than de-consting every string in the SDK.
    """
    from inventory import mask_csharp
    dynamic = set()
    texts = [(name, raw.decode("utf-8")) for name, raw in prepared]
    readonly = re.compile(r"\bstatic\s+readonly\s+string\s+([^;]+);", re.S)
    const = re.compile(r"\bconst\s+string\s+([^;]+);", re.S)
    for unused_name, text in texts:
        masked, unused = mask_csharp(text)
        for match in readonly.finditer(masked):
            dynamic.update(re.findall(r"\b(\w+)\s*=", match.group(1)))
    while True:
        changed, next_texts = False, []
        for name, text in texts:
            masked, unused = mask_csharp(text)
            patches = []
            for match in const.finditer(masked):
                body = match.group(1)
                declared = set(re.findall(r"\b(\w+)\s*=", body))
                consumed = set(re.findall(r"\b\w+\b", body)) - declared
                if consumed.intersection(dynamic):
                    patches.append((match.start(), match.start() + len("const"), "" if local_declaration(masked, match.start()) else "static readonly"))
                    dynamic.update(declared)
            for a, b, value in reversed(patches):
                text = text[:a] + value + text[b:]
                changed = True
            next_texts.append((name, text))
        texts = next_texts
        if not changed:
            return [(name, text.encode("utf-8")) for name, text in texts]


def build(source_stage, output_directory, engine_file_name="McgsEngineering.Portable.dll"):
    legacy = binder_module()
    from abi_binding import patch_runtime_source
    from abi_locator import load_catalog, DEFAULT_CATALOG
    stage, output = Path(source_stage).resolve(), Path(output_directory).resolve()
    need(not output.exists() or output.is_dir() and not any(output.iterdir()), "Release source output must be new/empty")
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.dll", engine_file_name), "Engine name must be one DLL basename")
    manifest_raw = (stage / "source-and-dependency-manifest.json").read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8-sig"))
    source_catalog_raw = (ROOT / "abi-adapter/catalogs/source-addresses.json").read_bytes()
    source_catalog = json.loads(source_catalog_raw.decode("utf-8-sig"))
    catalog = load_catalog(DEFAULT_CATALOG)
    aliases = reference_aliases(stage, manifest, legacy.COMMON_PROFILE_PIN_CONTRACTS)
    rows = {row["name"]: row for row in manifest["sources"]}
    for row in [*source_catalog["entries"], *source_catalog.get("source_guards", []), *source_catalog.get("source_ordinals", [])]:
        name = PureWindowsPath(row["source"]).name
        need(name in rows and rows[name]["sha256"] == row["source_sha256"], "Runtime source map is from another source set")
    prepared, stats = [], Counter()
    for row in manifest["sources"]:
        raw = (stage / "sources" / row["name"]).read_bytes()
        need(digest(raw) == row["sha256"], "Release raw source changed: " + row["name"])
        text, counts = patch_catalogued_source(row["name"], raw.decode("utf-8-sig"), source_catalog)
        stats.update(counts)
        text = patch_runtime_source(row["name"], legacy.patch_common(row["name"], text))
        text, counts = patch_owned_literals(text, aliases, manifest, catalog)
        stats.update(counts)
        need(manifest["original_task_root"].casefold() not in text.casefold() and manifest["original_install_root"].casefold() not in text.casefold(), "Release source retains an original machine root: " + row["name"])
        prepared.append((row["name"], text.encode("utf-8")))
    prepared = propagate_runtime_string_aliases(prepared)
    helper = (ROOT / "abi-adapter/NativeAbiTargetProfiles.cs").read_text(encoding="utf-8-sig")
    helper = legacy.replace_once(helper, 'internal const string ExpectedIndexSha256="__BOUND_ABI_PROFILE_INDEX_SHA256__";', 'internal static string ExpectedIndexSha256{get{return NativePortableRuntime.IndexSha256;}}')
    helper = legacy.replace_once(helper, 'indexPath=Path.Combine(NativeEngineeringDeliveryLayout.EvidenceRoot,IndexName);', 'indexPath=NativePortableRuntime.IndexFile;')
    prepared.append(("NativeAbiTargetProfiles.cs", helper.encode("utf-8")))
    for name in ("NativeEngineeringDeliveryLayout.cs", "NativePortableRuntime.cs"):
        raw = Path(__file__).with_name(name).read_bytes()
        if name == "NativePortableRuntime.cs":
            need(raw.count(b"__PORTABLE_SOURCE_MANIFEST_SHA256__") == 1, "Portable source manifest token differs")
            raw = raw.replace(b"__PORTABLE_SOURCE_MANIFEST_SHA256__", digest(manifest_raw).encode("ascii"))
            need(raw.count(b"__PORTABLE_SOURCE_CATALOG_SHA256__") == 1, "Portable source catalog token differs")
            raw = raw.replace(b"__PORTABLE_SOURCE_CATALOG_SHA256__", digest(source_catalog_raw).encode("ascii"))
        prepared.append((name, raw))
    for name, raw in prepared:
        write_new(output / "sources" / name, raw)
    script = '''param([Parameter(Mandatory=$true)][string]$Csc)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$src=Get-ChildItem -LiteralPath (Join-Path $root 'sources') -Filter '*.cs' | Sort-Object Name | ForEach-Object FullName
$assembly=Join-Path $root 'ENGINE'
if (Test-Path -LiteralPath $assembly) {throw 'Release DLL output already exists'}
& $Csc /nologo /target:library /platform:x86 /optimize+ /r:System.Core.dll /r:System.Web.Extensions.dll ('/out:'+$assembly) $src
if ($LASTEXITCODE -ne 0) {throw 'Portable release compile failed'}
'''.replace("ENGINE", engine_file_name)
    write_new(output / "build-release.ps1", script.encode("utf-8"))
    result = {"schema": "mcgs-portable-engine-release-sources/v1", "engine_contract": CONTRACT,
              "source_manifest_sha256": digest(manifest_raw), "source_catalog_sha256": digest(source_catalog_raw),
              "engine_file_name": engine_file_name, "selected_source_count": len(prepared),
              "sources": [{"name": name, "sha256": digest(raw)} for name, raw in prepared],
              "runtime_lookup_counts": dict(stats), "target_compiler_required": False,
              "compiler_invoked": False, "vendor_invoked": False,
              "runtime_scope_binding": "actual sibling scope and data binding SHA, checked per request",
              "same_release_dll_across_targets": True}
    write_new(output / "release-source-manifest.json", encoded(result))
    return {**result, "output_directory": str(output), "build_entry": str(output / "build-release.ps1")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-stage", default=str(ROOT / "delivery/source"))
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--engine-file-name", default="McgsEngineering.Portable.dll")
    args = parser.parse_args()
    print(json.dumps(build(args.source_stage, args.output_directory, args.engine_file_name), ensure_ascii=False, indent=2))
