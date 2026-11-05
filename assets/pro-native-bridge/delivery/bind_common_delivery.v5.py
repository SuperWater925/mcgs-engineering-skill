"""Bind staged sources/profiles to an explicit portable layout; never run Pro.

Use the sibling configuration and bound Layout source produced by device-entry/
prepare_delivery_binding.py.  Output directories must be absent or empty; existing nonempty outputs are preserved.  The optional
compile entry is a separate PowerShell file and is never executed here.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re

from delivery_file_support import digest, regular, load, write_new, json_bytes, SHA


# These exact constants belong to the bound-only profile integrity checks in
# patch_common. They identify *named owned dependencies*, not vendor builds.
# The staged sources may not contain the constants until patch_common runs;
# include them in the same DAG as manifest provenance aliases before repinning.
COMMON_PROFILE_PIN_CONTRACTS = {
    "b55d593e93721b73f61226f00b7211b3efa7516542164e21b5aefe0bba6603a7": "strategy-properties/strategy-write-guard-profile.json",
    "ffbde9b8d445f31ef4563d65cd3b9adffece1e96abac4354f2b1395bf31dbb87": "extensions/strategy/strategy-extension-read-guard.json",
    "5e55e8163445bef097868905d766405a4fe2d6b9c2ef43f796fdb9ec4d98c8fe": "extensions/strategy/strategy-extension-write-guard.json",
    "e0a552d5a043915edac76af36b160d9c358055f5700814c237bd609d1a31de0d": "extensions/strategy/registration/registration-abi-guard.json",
    "19da1e70c09b8e17820913d7e242c11c1bf7d173be3b2467cbb78fdf5b757899": "extensions/strategy/delete/strategy-delete-abi-profile.json",
    "829e7df6560efe7594fc22a59b86d59005630601fd9b46340b78b201cfcc26a6": "static/document-dirty-save-abi-profile.json",
    "4b6f931919835cce377247f1edbb07d7df2cb64a1a11336de526f289aa26a505": "static/read-tree-guard-profile.json",
}


def need(value, message):
    if not value:
        raise ValueError(message)


def replace_once(text, old, new):
    need(text.count(old) == 1, "Expected one common source contract: " + old[:90])
    return text.replace(old, new)


def patch_common(name, text):
    # Exact pins for all audited path-only hot profile inputs.
    if name == 'strategy-properties__NativeStrategyProfile.cs':
        text = replace_once(text, 'string file=Path.Combine(NativeOperations.TaskRoot,"strategy-properties","strategy-write-guard-profile.json");', 'string file=Path.Combine(NativeOperations.TaskRoot,"strategy-properties","strategy-write-guard-profile.json");NativeMemory.Require(NativeMemory.Hash(file)=="b55d593e93721b73f61226f00b7211b3efa7516542164e21b5aefe0bba6603a7","Frozen shared strategy ABI file differs.");')
    if name == 'extensions__strategy__NativeStrategyExtensionProfile.cs':
        text = replace_once(text, 'string file=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy",profileName);', 'string file=Path.Combine(NativeOperations.TaskRoot,"extensions","strategy",profileName);string frozenReadProfileSha;switch(profileName.Replace((char)92,\'/\')){case "strategy-extension-read-guard.json":frozenReadProfileSha="ffbde9b8d445f31ef4563d65cd3b9adffece1e96abac4354f2b1395bf31dbb87";break;case "strategy-extension-write-guard.json":frozenReadProfileSha="5e55e8163445bef097868905d766405a4fe2d6b9c2ef43f796fdb9ec4d98c8fe";break;case "registration/registration-abi-guard.json":frozenReadProfileSha="e0a552d5a043915edac76af36b160d9c358055f5700814c237bd609d1a31de0d";break;case "delete/strategy-delete-abi-profile.json":frozenReadProfileSha="19da1e70c09b8e17820913d7e242c11c1bf7d173be3b2467cbb78fdf5b757899";break;default:throw new InvalidOperationException("Strategy read ABI path has no explicit compiled declaration.");}NativeMemory.Require(NativeMemory.Hash(file)==frozenReadProfileSha,"Frozen strategy read ABI file differs.");')
    if name == 'NativePageDuplicateProfile.reusable.cs':
        text = replace_once(text, 'var save=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"document-dirty-save-abi-profile.json"),Encoding.UTF8));', 'NativeMemory.Require(NativeMemory.Hash(Path.Combine(directory,"document-dirty-save-abi-profile.json"))=="829e7df6560efe7594fc22a59b86d59005630601fd9b46340b78b201cfcc26a6","Frozen document dirty/save ABI file differs.");var save=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"document-dirty-save-abi-profile.json"),Encoding.UTF8));')
    if name == 'NativePreparedPageCopy.v2.cs':
        text = replace_once(text, 'var save=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"document-dirty-save-abi-profile.json"),Encoding.UTF8));', 'NativeMemory.Require(NativeMemory.Hash(Path.Combine(directory,"document-dirty-save-abi-profile.json"))=="829e7df6560efe7594fc22a59b86d59005630601fd9b46340b78b201cfcc26a6","Frozen document dirty/save ABI file differs.");var save=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(directory,"document-dirty-save-abi-profile.json"),Encoding.UTF8));')
    if name == "NativeOperations.functional.cs":
        if 'NativeRequestPipeline.Prepare(request)' in text:
            text = replace_once(text, 'PrepareRequest(Dictionary<string,object> request){return NativeRequestPipeline.Prepare(request);}',
                'PrepareRequest(Dictionary<string,object> request){NativeEngineeringDeliveryLayout.Check();return NativeRequestPipeline.Prepare(request);}')
            text = replace_once(text, 'NativeEngineeringProjectScope.Enter(request); NativeOperationTrace.Begin(request);',
                'if(!NativeRequestPipeline.IsPrepared(request))NativeEngineeringDeliveryLayout.Check(); NativeEngineeringProjectScope.Enter(request); NativeOperationTrace.Begin(request);')
        else:
            text = replace_once(text, 'NativeEngineeringProjectScope.Enter(request); NativeOperationTrace.Begin(request);',
                'NativeEngineeringDeliveryLayout.Check(); NativeEngineeringProjectScope.Enter(request); NativeOperationTrace.Begin(request);')
        text = replace_once(text, 'result["write_attempted"]=NativeOperationTrace.MutationAttempted;',
            'result["engineering_delivery_scope_sha256"]=NativeEngineeringDeliveryLayout.ConfigurationSha256;result["write_attempted"]=NativeOperationTrace.MutationAttempted;')
        if 'new NativeRequestPipeline.TraceWriter(' in text:
            text = replace_once(text, 'new NativeRequestPipeline.TraceWriter(Path.Combine(NativeOperations.TaskRoot,"extensions","native-operation-trace.jsonl"))',
                'new NativeRequestPipeline.TraceWriter(Path.Combine(NativeEngineeringDeliveryLayout.WorkingRoot,"trace","native-operation-trace.jsonl"))')
        else:
            text = replace_once(text, 'string directory=Path.Combine(NativeOperations.TaskRoot,"extensions");',
                'string directory=Path.Combine(NativeEngineeringDeliveryLayout.WorkingRoot,"trace");')
        text, count = re.subn(r'internal const string TaskRoot=@"[^"]+";',
            'internal static string TaskRoot{get{return NativeEngineeringDeliveryLayout.TaskRoot;}}', text)
        need(count == 1, "NativeOperations task root definition differs")
        text = replace_once(text, 'string op=Text(request,"op");',
            'string op=Text(request,"op");NativeMemory.Require(op=="ping"||op=="engineering-edit-inspect"||op=="engineering-edit-batch"||op=="engineering-project-lifecycle-read"||op=="engineering-project-close-reopen-original","Delivery exposes explicit engineering and original project lifecycle entries only; historical trial routes remain isolated.");')
        text = replace_once(text,
            'var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(NativeOperations.TaskRoot,"static","read-tree-guard-profile.json"),Encoding.UTF8));',
            'string rootProfile=Path.Combine(NativeEngineeringDeliveryLayout.EvidenceRoot,"static","read-tree-guard-profile.json");NativeMemory.Require(NativeMemory.Hash(rootProfile)=="4b6f931919835cce377247f1edbb07d7df2cb64a1a11336de526f289aa26a505","Bound root ABI profile differs.");var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(rootProfile,Encoding.UTF8));')
    elif name == "NativeEngineeringProjectScope.cs":
        text, count = re.subn(r'internal static string ExpectedProjectPath \{get\{return expected\?\?[^;]+;\}\}',
            'internal static string ExpectedProjectPath {get{NativeMemory.Require(expected!=null,"No explicit engineering project request is active.");return expected;}}', text)
        need(count == 1, "Project scope fallback differs")
        text = replace_once(text, 'object raw;NativeMemory.Require(request.TryGetValue("expected_project",out raw)',
            'object delivery;NativeMemory.Require(request.TryGetValue("engineering_delivery_scope_sha256",out delivery)&&delivery is string&&(string)delivery==NativeEngineeringDeliveryLayout.ConfigurationSha256,"Request delivery configuration differs.");object raw;NativeMemory.Require(request.TryGetValue("expected_project",out raw)')
    elif name == "NativeEngineeringDirectExecution.cs":
        text = replace_once(text,
            '{"schema",1},{"purpose",NativeUsableEditPermit.Purpose}',
            '{"schema",1},{"purpose",NativeUsableEditPermit.Purpose},{"engineering_delivery_scope_sha256",NativeEngineeringDeliveryLayout.ConfigurationSha256}')
    elif name == "NativeUsableEditPermit.cs":
        text = replace_once(text,
            'internal static Plan LoadDirectPlan(',
            'internal static Dictionary<string,object> DirectPlanRequest(Dictionary<string,object> document){return new Dictionary<string,object>{{"expected_project",Fixture},{"engineering_delivery_scope_sha256",NativeEngineeringDeliveryLayout.ConfigurationSha256}};}\n  internal static Plan LoadDirectPlan(')
        text = replace_once(text,
            'new Plan(new Dictionary<string,object>{{"expected_project",Fixture}},engine,context,summary,kinds,document)',
            'new Plan(DirectPlanRequest(document),engine,context,summary,kinds,document)')
        text = replace_once(text, 'Path.GetFullPath(Path.Combine(NativeOperations.TaskRoot,"coverage-20261101","usable-edit-0001"))',
            'NativeEngineeringDeliveryLayout.EngineeringRoot')
        text = replace_once(text, 'internal static string Fixture{',
            'internal static string WorkingRoot{get{return NativeEngineeringDeliveryLayout.WorkingRoot;}}\n  internal static string Fixture{')
        text = replace_once(text, 'root=DirectoryRoot.TrimEnd', 'root=WorkingRoot.TrimEnd')
        text = replace_once(text, 'Permit must be a regular file inside usable-edit-0001.',
            'Permit must be a regular file inside the bound engineering runtime directory.')
        text = replace_once(text, 'ClaimFile=Path.Combine(DirectoryRoot,"claims",',
            'ClaimFile=Path.Combine(WorkingRoot,"claims",')
        text = replace_once(text, 'Require(Convert.ToInt32(Document["schema"])==1',
            'Require(HashString(Document,"engineering_delivery_scope_sha256")==NativeEngineeringDeliveryLayout.ConfigurationSha256&&HashString(request,"engineering_delivery_scope_sha256")==NativeEngineeringDeliveryLayout.ConfigurationSha256,"Permit/request delivery configuration differs.");Require(Convert.ToInt32(Document["schema"])==1')
    elif name == "NativeEngineeringLargeReceipt.cs":
        text = replace_once(text, 'Path.Combine(NativeOperations.TaskRoot,"runtime","claimed",',
            'Path.Combine(NativeEngineeringDeliveryLayout.RuntimeRoot,"claimed",')
        text = replace_once(text, 'Path.Combine(NativeUsableEditPermit.DirectoryRoot,"reply-payloads")',
            'Path.Combine(NativeEngineeringDeliveryLayout.WorkingRoot,"reply-payloads")')
        text = replace_once(text, '{"engineering_payload",new Dictionary',
            '{"engineering_delivery_scope_sha256",NativeEngineeringDeliveryLayout.ConfigurationSha256},{"engineering_payload",new Dictionary')
    elif name == "NativeEngineeringComparisonEvidence.cs":
        text = replace_once(text, 'Path.Combine(NativeUsableEditPermit.DirectoryRoot,"comparison-failures")',
            'Path.Combine(NativeEngineeringDeliveryLayout.WorkingRoot,"comparison-failures")')
    elif name == "NativeProjectLifecycle.cs":
        # Project/profile inputs retain the explicit TaskRoot/EngineeringRoot
        # boundaries. Only permit, permanent claim and newly written snapshot
        # move to the configured writable runtime.
        marker = '  static string HashString(Dictionary<string,object>d,string key)'
        runtime_owned = ('  static string RuntimeOwned(string file,bool existing){string p=Owned(file,existing),root=Path.GetFullPath(NativeEngineeringDeliveryLayout.WorkingRoot).TrimEnd(\'\\\\\')+"\\\\";Need(p.StartsWith(root,StringComparison.OrdinalIgnoreCase),"Lifecycle permit/output must be inside configured WorkingRoot.");return p;}\n')
        text = replace_once(text, marker, runtime_owned + marker)
        if 'static string SnapshotDestination(' in text:
            # Direct lifecycle destinations are explicit user paths. Only the
            # optional legacy permit branch retains its former runtime binding.
            need('string copy=SnapshotDestination(S(request,"closed_copy_file"));' in text,
                 'Direct lifecycle snapshot destination contract differs')
            text = replace_once(text, 'ExistingProject(project);if(legacyOwned)Owned(destination,false);',
                'ExistingProject(project);if(legacyOwned)RuntimeOwned(destination,false);')
            text = replace_once(text, 'Directory.CreateDirectory(Path.GetDirectoryName(destination));if(legacyOwned)Owned(destination,false);',
                'Directory.CreateDirectory(Path.GetDirectoryName(destination));if(legacyOwned)RuntimeOwned(destination,false);')
        else:
            text = replace_once(text, 'string copy=Owned(S(request,"closed_copy_file"),false);',
                'string copy=RuntimeOwned(S(request,"closed_copy_file"),false);')
            text = replace_once(text, 'ExistingProject(project);Owned(destination,false);',
                'ExistingProject(project);RuntimeOwned(destination,false);')
            text = replace_once(text, 'Directory.CreateDirectory(Path.GetDirectoryName(destination));Owned(destination,false);',
                'Directory.CreateDirectory(Path.GetDirectoryName(destination));RuntimeOwned(destination,false);')
        text = replace_once(text, 'permitFile=Owned(S(request,"permit_file"),true);',
            'permitFile=RuntimeOwned(S(request,"permit_file"),true);')
        text = replace_once(text, 'Guid trial;Need(N(document["schema"])==1',
            'Need(HashString(document,"engineering_delivery_scope_sha256")==NativeEngineeringDeliveryLayout.ConfigurationSha256,"Lifecycle permit delivery configuration differs.");Guid trial;Need(N(document["schema"])==1')
        if 'static string SnapshotDestination(' in text:
            text = replace_once(text, 'copy=Owned(S(document,"closed_copy_file"),false);',
                'copy=RuntimeOwned(S(document,"closed_copy_file"),false);')
        else:
            text = replace_once(text, 'string copy=Owned(S(document,"closed_copy_file"),false);',
                'string copy=RuntimeOwned(S(document,"closed_copy_file"),false);')
        text = replace_once(text, 'claim=Path.Combine(NativeUsableEditPermit.DirectoryRoot,"claims",',
            'claim=Path.Combine(NativeEngineeringDeliveryLayout.WorkingRoot,"claims",')
    # Both export and native import use actual owned runtime assets, not the
    # immutable ABI payload. Other DirectoryRoot occurrences remain read-only.
    text = text.replace('Path.Combine(NativeUsableEditPermit.DirectoryRoot,"resource-exports")',
                        'Path.Combine(NativeEngineeringDeliveryLayout.WorkingRoot,"resource-exports")')
    # These sources only use TaskRoot for immutable ABI data/provenance or old
    # historical trial routes, which the delivery gate does not expose. Keep
    # current project, user input, claim and output ownership in the six explicit
    # runtime sources below. Page-copy's caller-supplied safe-export input also
    # remains TaskRoot; only its ABI directory moves.
    runtime_owners = {"NativeOperations.functional.cs", "NativeEngineeringProjectScope.cs",
        "NativeUsableEditPermit.cs", "NativeEngineeringLargeReceipt.cs",
        "NativeEngineeringComparisonEvidence.cs", "NativeProjectLifecycle.cs"}
    if name == "NativePreparedPageCopy.v2.cs":
        text = replace_once(text, 'Path.Combine(NativeOperations.TaskRoot,"static")',
            'Path.Combine(NativeEngineeringDeliveryLayout.EvidenceRoot,"static")')
    elif name not in runtime_owners:
        text = text.replace("NativeOperations.TaskRoot", "NativeEngineeringDeliveryLayout.EvidenceRoot")
    return text


def path_rewriter(old_task, old_install, new_task, new_install, new_program=None, new_editor=None):
    # The old Program prefix must move to the explicit editor directory first;
    # other installation-relative resources still belong to InstallRoot.
    pairs = [(str(PureWindowsPath(old_install) / "Program"), str(PureWindowsPath(new_program or (PureWindowsPath(new_install) / "Program")))),
             (str(PureWindowsPath(old_task)), str(PureWindowsPath(new_task))),
             (str(PureWindowsPath(old_install)), str(PureWindowsPath(new_install)))]
    old_editor = str(PureWindowsPath(old_install) / "Program" / "McgsSetPro.exe")
    selected_editor = str(PureWindowsPath(new_editor or (PureWindowsPath(pairs[0][1]) / "McgsSetPro.exe")))

    def path(text):
        if not isinstance(text, str):
            return text
        windows = text.replace("/", "\\")
        if windows.casefold() == old_editor.casefold():
            return selected_editor
        for old, new in pairs:
            if windows.casefold() == old.casefold() or windows.casefold().startswith(old.casefold().rstrip("\\")+"\\"):
                return new.rstrip("\\") + windows[len(old.rstrip("\\")):]
        return text

    source_pairs, exact_editor_keys = {}, set()
    for old, new in [(old_editor, selected_editor), *pairs]:
        for a, b in ((old, new), (old.replace("\\", "\\\\"), new.replace("\\", "\\\\")),
                     (old.replace("\\", "/"), new.replace("\\", "/"))):
            source_pairs[a.casefold()] = b
            if old == old_editor:
                exact_editor_keys.add(a.casefold())
    patterns = []
    for value in sorted(source_pairs, key=len, reverse=True):
        boundary = r'''(?=(?:\\)?['"]|$)''' if value in exact_editor_keys else r'''(?=[\\/'"]|$)'''
        patterns.append(re.escape(value) + boundary)
    prefixes = re.compile("|".join(patterns), re.I)

    def source(text):
        # Replace longest prefixes once so a new path sharing the old prefix
        # cannot be rewritten again by the broader InstallRoot mapping.
        return prefixes.sub(lambda match: source_pairs[match.group(0).casefold()], text)
    return path, source


def bind(stage, config_file, layout_source, output, engine_name, abi_catalog=None):
    stage, output = Path(stage).resolve(), Path(output).resolve()
    need(not output.exists() or (output.is_dir() and not any(output.iterdir())),
         "Bound source output is not empty; preserve its existing files")
    manifest_file = regular(stage / "source-and-dependency-manifest.json")
    manifest, config = load(manifest_file), load(config_file)
    config_file, layout_source = regular(config_file), regular(layout_source)
    scope_sha = digest(config_file.read_bytes())
    layout_text = layout_source.read_text(encoding="utf-8-sig")
    need(layout_text.count('ExpectedConfigurationSha256="'+scope_sha+'"') == 1,
         "Layout source is not bound to this exact sibling configuration")
    need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.dll", engine_name), "Engine file name differs")
    need(config_file.name == Path(engine_name).with_suffix(".scope.json").name,
         "Configuration must have the eventual engine sibling name")
    # Import the original, independently staged strict filesystem contract.
    device_entry = Path(__file__).resolve().parent / "device-entry-v2"
    import sys
    sys.path.insert(0, str(device_entry))
    from native_delivery_config import validate_mapping
    layout = validate_mapping(config, config_file, scope_sha)
    need(output.is_relative_to(layout.runtime_root) and not output.is_relative_to(layout.engineering_root),
         "Build outputs must be inside the declared runtime, outside immutable engineering payload")
    adapter = Path(__file__).resolve().parent.parent / "abi-adapter"
    sys.path.insert(0, str(adapter))
    from abi_binding import TargetBinding, patch_runtime_source
    # Resolve files from this scope's selected installation before path changes
    # and the existing content-addressed dependency graph are materialized.
    output.mkdir(parents=True, exist_ok=True)
    need(not any(output.iterdir()), "Bound source output gained existing files before native API resolution")
    abi_target = TargetBinding(stage, manifest, layout, output / "abi-resolution", abi_catalog)
    path, source_paths = path_rewriter(manifest["original_task_root"], manifest["original_install_root"],
                                     str(layout.engineering_root / "task-evidence"), config["install_root"], str(layout.program_root), str(layout.editor_executable))
    artifacts, original_by_hash = {}, {}
    for row in manifest["owned_artifacts"]:
        relative = row["task_relative_file"]
        file = regular(stage / "artifacts" / relative)
        data = file.read_bytes()
        need(digest(data) == row["sha256"], "Staged ABI/static dependency changed")
        data = abi_target.overrides.get(relative, data)
        text = data.decode("utf-8-sig")
        if file.suffix == ".json":
            original = json.loads(text)
            def visit(value, key=None):
                if isinstance(value, dict):
                    return {k: visit(v,k) for k,v in value.items()}
                if isinstance(value, list):
                    return [visit(v) for v in value]
                return abi_target.module_file_value(path(value),key)
            rewritten = json_bytes(visit(original)).decode("utf-8")
        else:
            rewritten = source_paths(abi_target.source_module_paths(text,manifest["original_install_root"]))
        artifacts[relative] = {"old_sha": row["sha256"], "text": rewritten, "source": file}
        original_by_hash.setdefault(row["sha256"], relative)
        for alias in row.get("origin_sha256_aliases",[]):
            need(isinstance(alias,str) and re.fullmatch("[a-f0-9]{64}",alias),"Invalid exact ABI-only provenance hash alias")
            need(alias not in original_by_hash or original_by_hash[alias]==relative,"ABI provenance hash alias collides")
            original_by_hash[alias]=relative

    for pin, relative in COMMON_PROFILE_PIN_CONTRACTS.items():
        need(relative in artifacts, "Named bound integrity dependency is absent: " + relative)
        need(pin not in original_by_hash or original_by_hash[pin] == relative,
             "Named bound integrity pin conflicts with another selected dependency: " + relative)
        original_by_hash[pin] = relative

    # Exact content-addressed dependency DAG. No hash is removed or replaced
    # by a wildcard; all changed path-bearing artifacts receive new SHA pins.
    resolved, resolving = {}, set()
    def materialize(relative):
        if relative in resolved:
            return resolved[relative]
        need(relative not in resolving, "Pinned source/profile dependency cycle requires explicit resolution")
        resolving.add(relative)
        row = artifacts[relative]
        def changed(match):
            old = match.group(0)
            other = original_by_hash.get(old)
            return old if other is None else digest(materialize(other))
        if row["source"].suffix == ".json":
            def rehash(value, provenance=False):
                if isinstance(value,dict):
                    return {key:rehash(item,provenance or key=="_mcgs_abi_resolution") for key,item in value.items()}
                if isinstance(value,list):
                    return [rehash(item,provenance) for item in value]
                return SHA.sub(changed,value) if isinstance(value,str) and not provenance else value
            # Resolver provenance records the *reference* digest. It is not a
            # dependency pin to the current file and must not create a self-DAG.
            text=json_bytes(rehash(json.loads(row["text"]))).decode("utf-8")
        else:
            text = SHA.sub(changed, row["text"])
        data = text.encode("utf-8")
        resolving.remove(relative)
        resolved[relative] = data
        return data
    for relative in artifacts:
        materialize(relative)
    changed_sha = {alias:digest(resolved[relative]) for alias,relative in original_by_hash.items()}

    prepared_sources = []
    for row in manifest["sources"]:
        file = regular(stage / "sources" / row["name"])
        data = file.read_bytes()
        need(digest(data) == row["sha256"], "Selected staged C# changed")
        text = abi_target.patch_addresses(row["name"], data.decode("utf-8-sig"))
        before_common_pins=set(SHA.findall(text))
        text=patch_common(row["name"],text)
        for introduced in set(SHA.findall(text))-before_common_pins:
            need(introduced in changed_sha,
                 "Added bound profile integrity check has no named dependency mapping: " + row["name"] + ":" + introduced)
        text = abi_target.source_module_paths(patch_runtime_source(row["name"], text),manifest["original_install_root"])
        text = source_paths(text)
        text = SHA.sub(lambda m: changed_sha.get(m.group(0), m.group(0)), text)
        for pin, relative in COMMON_PROFILE_PIN_CONTRACTS.items():
            need(pin not in text or changed_sha[pin] == pin,
                 "Bound profile integrity pin was not regenerated from its final dependency: " + relative)
        prepared_sources.append((row, text.encode("utf-8")))

    output.mkdir(parents=True, exist_ok=True)
    need({item.name for item in output.iterdir()} == {"abi-resolution"},
         "Bound source output gained unrelated files before writing; preserve them")
    copied, patched = [], []
    original_engineering = PureWindowsPath(manifest["original_engineering_relative_root"])
    # A separate immutable evidence tree preserves legacy relative ABI paths
    # without replacing original task evidence. Usable-edit profiles also have
    # their short EngineeringRoot-relative path. No payload writes to TaskRoot.
    destinations = {}
    for relative, data in resolved.items():
        rel = Path(relative)
        targets = [(layout.engineering_root / "task-evidence" / rel,
                    output / "payload-evidence" / rel)]
        windows_rel = PureWindowsPath(relative)
        if windows_rel.is_relative_to(original_engineering):
            engineering_relative = str(windows_rel.relative_to(original_engineering))
            targets.append((layout.engineering_root / engineering_relative,
                            output / "payload-engineering" / engineering_relative))
        for target, staged_file in set(targets):
            if target in destinations:
                need(destinations[target] == digest(data), "Two ABI artifacts collide after relocation")
                continue
            destinations[target] = digest(data)
            write_new(staged_file, data)
            copied.append({"planned_file": str(target), "staged_file": str(staged_file),
                           "sha256": digest(data), "original_relative_file": relative})
    # Index hashes are the final DAG hashes, including resolved profiles and
    # relocated child dependencies. Hash() still returns actual file digests.
    index_data = json_bytes(abi_target.index(resolved, layout, copied))
    need(len(index_data) <= 16*1024*1024, "Current native API index exceeds the runtime JSON parser's byte-safe capacity")
    index_relative = "abi-target-profile-index.json"
    index_staged = output / "payload-evidence" / index_relative
    write_new(index_staged, index_data)
    copied.append({"planned_file":str(layout.engineering_root / "task-evidence" / index_relative),
                   "staged_file":str(index_staged),"sha256":digest(index_data),
                   "original_relative_file":index_relative})
    for row, value in prepared_sources:
        destination = output / "sources" / row["name"]
        write_new(destination,value)
        patched.append({"name": row["name"], "original_sha256": row["sha256"], "sha256": digest(value)})
    helper_file = regular(adapter / "NativeAbiTargetProfiles.cs")
    helper_raw = helper_file.read_bytes()
    helper_text = helper_raw.decode("utf-8-sig")
    helper_text = replace_once(helper_text, "__BOUND_ABI_PROFILE_INDEX_SHA256__", digest(index_data))
    helper_value = helper_text.encode("utf-8")
    write_new(output / "sources" / helper_file.name, helper_value)
    patched.append({"name":helper_file.name,"original_sha256":digest(helper_raw),
                    "sha256":digest(helper_value),"added_target_resolution_runtime":True})
    write_new(output / "sources" / "NativeEngineeringDeliveryLayout.cs", layout_source.read_bytes())
    write_new(output / config_file.name, config_file.read_bytes())
    assembly = output / engine_name
    # This concrete build command is deliberately generated, never invoked.
    script = """param([Parameter(Mandatory=$true)][string]$Csc)\n$ErrorActionPreference='Stop'\n$root=$PSScriptRoot\n$src=Get-ChildItem -LiteralPath (Join-Path $root 'sources') -Filter '*.cs' | Sort-Object Name | ForEach-Object FullName\nif (-not $src) {throw 'No bound selected sources'}\n$assembly=Join-Path $root 'ENGINE_NAME'\nif (Test-Path -LiteralPath $assembly) {throw 'Assembly output exists; choose a new bound directory'}\n& $Csc /nologo /target:library /platform:x86 /optimize+ /r:System.Core.dll /r:System.Web.Extensions.dll ('/out:'+$assembly) $src\nif ($LASTEXITCODE -ne 0) {throw 'Bound source compile failed; preserve all outputs'}\n""".replace("ENGINE_NAME",engine_name)
    write_new(output / "build-bound-source.ps1",script.encode("utf-8"))
    result = {"schema":1,"kind":"portable source/profile binding; not activated",
        "source_manifest_file":str(manifest_file),"source_manifest_sha256":digest(manifest_file.read_bytes()),
        "engineering_delivery_scope_sha256":scope_sha,"scope_file":str(output/config_file.name),
        "project_identity":"per engineering request.expected_project; existing owned MCP only",
        "selected_sources":patched,"layout_source_sha256":digest(layout_source.read_bytes()),
        "relocated_owned_dependencies":copied,"assembly":str(assembly),
        "guard_bytes_RTTI_native_imports_and_non_path_values_changed":True,
        "native_api_resolution":abi_target.summary(),
        "native_api_profile_index_sha256":digest(index_data),
        "compiled_profile_integrity_pins":[{"profile":relative,"sha256":digest(resolved[relative])}
                                          for relative in sorted(set(COMMON_PROFILE_PIN_CONTRACTS.values()))],
        "object_field_offsets_and_existing_call_contracts_changed":False,
        "new_profile_hashes_fully_repinned":True,"historical_routes_exposed":False,
        "exposed_engineering_operations":["engineering-edit-inspect","engineering-edit-batch",
            "engineering-project-lifecycle-read","engineering-project-close-reopen-original"],
        "lifecycle_requires_own_dedicated_scope_bound_permit":True,
        "legacy_owned_proof_files_mirrored_at_task_boundary":False,
        "immutable_evidence_root":str(layout.engineering_root / "task-evidence"),
        "original_task_profiles_overwritten":False,
        "payload_promotion_performed":False,"installed_skill_or_declared_payload_modified":False,
        "vendor_binaries_projects_prior_runtime_receipts_bundled":False,
        "compiled":False,"host_invoked":False,"deployment_and_functional_acceptance_pending":True}
    write_new(output / "bound-source-manifest.json",json_bytes(result))
    return {"ok":True,"source_count":len(patched)+1,"bound_manifest_sha256":digest((output/"bound-source-manifest.json").read_bytes()),
            "build_entry":str(output/"build-bound-source.ps1"),"compiled":False,"host_invoked":False}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-stage",required=True)
    parser.add_argument("--scope-json",required=True)
    parser.add_argument("--bound-layout-source",required=True)
    parser.add_argument("--output-directory",required=True)
    parser.add_argument("--engine-file-name",required=True)
    parser.add_argument("--abi-catalog",help="Optional sparse reference catalog; defaults to the packaged catalog")
    args=parser.parse_args()
    print(json.dumps(bind(args.source_stage,args.scope_json,args.bound_layout_source,args.output_directory,
                          args.engine_file_name,args.abi_catalog),ensure_ascii=True,indent=2))
