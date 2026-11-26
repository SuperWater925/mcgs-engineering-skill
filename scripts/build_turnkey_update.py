"""Build a small publisher-side patch for a verified complete bundle ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

from check_repository import MANIFEST, file_manifest, package_files
import turnkey_bundle as bundle
from turnkey_bundle import _relative, REPOSITORY
from turnkey_publisher_assets import STU_MANIFEST, read_directory, shared_bridge_payload, stu_engine_payload


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def row(name, raw):
    return {"file": name, "size": len(raw), "sha256": sha(raw)}


def publisher_tools(repo, business, explicit=None):
    """Require fresh publisher tools; never carry the base launcher's old code."""
    candidates = [Path(explicit)] if explicit else [
        *([Path(os.environ['MCGS_PUBLISHER_TOOLS'])] if os.environ.get('MCGS_PUBLISHER_TOOLS') else []),
        Path(business).parent / 'tools', Path(repo) / 'local-artifacts/turnkey-tools']
    diagnostics = []
    expected = {'McgsStart.exe': 'assets/turnkey-setup/Launcher.cs',
                'InstallerChoice.exe': 'assets/turnkey-setup/InstallerChoice.cs'}
    for directory in candidates:
        try:
            manifest = json.loads((directory / 'publisher-tools-manifest.json').read_text(encoding='utf-8-sig'))
            if manifest.get('schema') != 'mcgs-publisher-tools/v1':
                raise ValueError('Publisher tools manifest schema differs')
            artifacts = manifest['artifacts']
            if len(artifacts) != len(expected):
                raise ValueError('Publisher tools manifest artifact set differs')
            for name, source in expected.items():
                matches = [entry for entry in artifacts if entry.get('file') == name]
                if len(matches) != 1:
                    raise ValueError('Publisher tool is missing or duplicated: ' + name)
                entry = matches[0]
                if (entry.get('source') != source or entry.get('source_sha256') != file_sha(Path(repo) / source)
                        or entry.get('sha256') != file_sha(directory / name)):
                    raise ValueError('Publisher tool source or output differs: ' + name)
            return {'McgsStart.exe': (directory / 'McgsStart.exe').read_bytes(),
                    'tools/McgsStart.exe': (directory / 'McgsStart.exe').read_bytes(),
                    'tools/InstallerChoice.exe': (directory / 'InstallerChoice.exe').read_bytes(),
                    'tools/publisher-tools-manifest.json': (directory / 'publisher-tools-manifest.json').read_bytes()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            diagnostics.append(str(directory.absolute()) + ': ' + str(error))
    raise ValueError('Matching publisher tools are required. Run scripts/build_turnkey_tools.ps1 -Output <fresh-tools> '
                     'then supply --tools <fresh-tools>. ' + '; '.join(diagnostics))


def build(base_zip, base_sha256, business, version, output, tools=None, *, stu_engine_build=None, bridge_build=None):
    repo = Path(__file__).resolve().parents[1]
    if not re.fullmatch(r"v[0-9]+(?:\.[0-9]+){2}-[a-z0-9.-]+", version):
        raise ValueError("Supply a release tag such as v2026.11.10-online-update")
    if file_sha(base_zip) != base_sha256:
        raise ValueError("Complete base ZIP SHA256 differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repo):
        raise ValueError("Build the update from a committed source tree")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    source_files = package_files(repo)
    if file_manifest(repo, source_files) != json.loads((repo / MANIFEST).read_bytes()):
        raise ValueError("Source package manifest differs")

    with ZipFile(base_zip) as archive:
        roots = [name for name in archive.namelist() if name.count("/") == 1 and name.endswith("/bundle.json")]
        if len(roots) != 1:
            raise ValueError("Complete base ZIP must contain one bundle root")
        bundle_name, = roots
        root = bundle_name.removesuffix("bundle.json")
        base_bundle = archive.read(bundle_name)
        base_files = archive.read(root + "bundle-files.json")
        target = json.loads(base_bundle)
        if target["schema"] != "mcgs-turnkey-bundle/v1" or target["skill_directory"] != "skill":
            raise ValueError("Complete base bundle layout differs")
        previous_stu = target.get("business_engines", {}).get("stu")
        stu_payload = {}
        retired_stu = set()
        if previous_stu:
            _relative(previous_stu)
            stu_directory = PurePosixPath(previous_stu).parent
            retired_stu = {previous_stu, (stu_directory / STU_MANIFEST).as_posix()}
        if stu_engine_build or previous_stu:
            published_stu = read_directory(stu_engine_build) if stu_engine_build else (
                lambda name: archive.read(root + (stu_directory / name).as_posix()))
            try:
                stu_name, assets = stu_engine_payload(repo, published_stu)
            except (OSError, KeyError, ValueError) as error:
                if stu_engine_build:
                    raise
                raise ValueError("The base Stu engine is missing or stale. Supply --stu-engine-build.") from error
            if not stu_engine_build and stu_name != PurePosixPath(previous_stu).name:
                raise ValueError("The base Stu engine manifest names a different DLL. Supply --stu-engine-build.")
            stu_directory = PurePosixPath("engine/business/stu") if stu_engine_build else stu_directory
            stu_payload = {(stu_directory / name).as_posix(): raw for name, raw in assets.items()}
            target["business_engines"] = {**target.get("business_engines", {}), "stu": (stu_directory / stu_name).as_posix()}

        bridge_payload = {}
        bridge_prefix = '/'.join(_relative(target["bridge_artifacts"])) + '/'
        if bridge_build or stu_payload:
            published_bridge = read_directory(bridge_build) if bridge_build else (
                lambda name: archive.read(root + bridge_prefix + name))
            try:
                assets = shared_bridge_payload(repo, published_bridge,
                    verify_generated=bool(bridge_build and (Path(bridge_build) / 'source').is_dir()))
            except (OSError, KeyError, ValueError) as error:
                if bridge_build:
                    raise
                raise ValueError("A Stu-enabled update needs --bridge-build or a verified shared bridge in its base.") from error
            bridge_payload = {bridge_prefix + name: raw for name, raw in assets.items()}

    target.update(release=version[1:], release_tag=version, source_commit=commit)
    baseline = {entry["file"]: entry for entry in json.loads(base_files)["files"]}
    target_rows = {name: entry for name, entry in baseline.items()
                   if not name.startswith("skill/") and name not in retired_stu
                   and (not bridge_payload or not name.startswith(bridge_prefix))}

    engine_path = business / Path(target["business_engine"]).name
    release_file = business / "portable-engine-manifest.json"
    release = json.loads(release_file.read_bytes())
    source = repo / "assets/pro-native-bridge"
    if (release["sha256"] != file_sha(engine_path)
            or release["source_manifest_sha256"] != file_sha(source / "delivery/source/source-and-dependency-manifest.json")
            or release["source_catalog_sha256"] != file_sha(source / "abi-adapter/catalogs/source-addresses.json")):
        raise ValueError("Precompiled engine does not match the source release")
    replacements = {
        **publisher_tools(repo, business, tools),
        **stu_payload,
        **bridge_payload,
        **{"skill/" + path.relative_to(repo).as_posix(): path.read_bytes()
           for path in [*source_files, repo / MANIFEST]},
        "bundle.json": encoded(target),
        target["business_engine"]: engine_path.read_bytes(),
        str(Path(target["business_engine"]).parent / release_file.name).replace("\\", "/"): release_file.read_bytes(),
        "使用说明.md": (repo / "references/turnkey-start-zh.md").read_bytes(),
        "第三方许可说明.md": (repo / "references/turnkey-third-party.md").read_bytes(),
    }
    for name, raw in replacements.items():
        _relative(name)
        target_rows[name] = row(name, raw)
    replacements["bundle-files.json"] = encoded({
        "schema": 1, "files": sorted(target_rows.values(), key=lambda entry: entry["file"].casefold()),
    })
    # Every current skill file and engine is shipped. A receiver can upgrade
    # any prior update, including a file reverted to the original base bytes.
    payload = dict(replacements)
    source_contract = {key: release[key] for key in ('source_manifest_sha256', 'source_catalog_sha256')}
    if stu_payload:
        source_contract['stu_engine_source_sha256'] = bundle.stu_engine_source_sha256(repo)
    manifest = {
        "schema": "mcgs-turnkey-update/v1",
        "base_bundle_sha256": sha(base_bundle),
        "base_files_sha256": sha(base_files),
        "target_files_sha256": sha(replacements["bundle-files.json"]),
        "target_release": target["release"],
        "source_contract": source_contract,
        "payload": [row(name, payload[name]) for name in sorted(payload)],
    }
    output.mkdir(parents=True, exist_ok=False)
    asset = output / f"mcgs-engineering-update-{version[1:]}-win-x64.zip"
    with ZipFile(asset, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("update.json", encoded(manifest))
        archive.write(repo / "references/turnkey-update-zh.md", "使用说明.md")
        for name in ("apply_turnkey_update.py", "turnkey_bundle.py"):
            archive.write(repo / "scripts" / name, "scripts/" + name)
        for name, raw in payload.items():
            archive.writestr("payload/" + name, raw)
    with ZipFile(asset) as archive:
        if archive.testzip() is not None:
            raise ValueError("Update ZIP CRC verification failed")
    digest = file_sha(asset)
    index = output / "mcgs-engineering-index.json"
    index.write_bytes(encoded({
        "schema": "mcgs-engineering-release-index/v1", "release_tag": version,
        "source_commit": commit, "source_contract": source_contract,
        "skill_manifest_sha256": file_sha(repo / MANIFEST),
        "update": {"file": asset.name, "size": asset.stat().st_size, "sha256": digest,
                   "url": f"https://github.com/{REPOSITORY}/releases/download/{version}/{asset.name}"},
    }))
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {asset.name}\n{file_sha(index)}  {index.name}\n", encoding="ascii")
    return {"archive": str(asset), "sha256": digest, "payload_files": len(payload),
            "bytes": asset.stat().st_size, "source_commit": commit, "release_index": str(index),
            "stu_engine_included": bool(stu_payload), "shared_bridge_included": bool(bridge_payload)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-zip", required=True, type=Path)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--business", required=True, type=Path)
    parser.add_argument("--tools", type=Path, help="Fresh publisher tools with source/output manifest; auto-discovered when omitted")
    parser.add_argument("--stu-engine-build", type=Path, help="Optional publisher Stu DLL and source manifest")
    parser.add_argument("--bridge-build", type=Path, help="Current publisher shared bridge build")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.base_zip, args.base_sha256, args.business, args.version, args.output, args.tools,
                           stu_engine_build=args.stu_engine_build, bridge_build=args.bridge_build), indent=2))
