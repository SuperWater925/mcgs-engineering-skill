"""Build a small publisher-side patch for a verified complete bundle ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

from check_repository import MANIFEST, file_manifest, package_files
from turnkey_bundle import _relative


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def row(name, raw):
    return {"file": name, "size": len(raw), "sha256": sha(raw)}


def build(base_zip, base_sha256, business, version, output):
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
    target.update(release=version[1:], release_tag=version, source_commit=commit)
    baseline = {entry["file"]: entry for entry in json.loads(base_files)["files"]}
    target_rows = {name: entry for name, entry in baseline.items() if not name.startswith("skill/")}

    engine_path = business / Path(target["business_engine"]).name
    release_file = business / "portable-engine-manifest.json"
    release = json.loads(release_file.read_bytes())
    source = repo / "assets/pro-native-bridge"
    if (release["sha256"] != file_sha(engine_path)
            or release["source_manifest_sha256"] != file_sha(source / "delivery/source/source-and-dependency-manifest.json")
            or release["source_catalog_sha256"] != file_sha(source / "abi-adapter/catalogs/source-addresses.json")):
        raise ValueError("Precompiled engine does not match the source release")
    replacements = {
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
    payload = {name: raw for name, raw in replacements.items() if row(name, raw) != baseline.get(name)}
    manifest = {
        "schema": "mcgs-turnkey-update/v1",
        "base_bundle_sha256": sha(base_bundle),
        "base_files_sha256": sha(base_files),
        "target_files_sha256": sha(replacements["bundle-files.json"]),
        "target_release": target["release"],
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
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {asset.name}\n", encoding="ascii")
    return {"archive": str(asset), "sha256": digest, "payload_files": len(payload),
            "bytes": asset.stat().st_size, "source_commit": commit}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-zip", required=True, type=Path)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--business", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.base_zip, args.base_sha256, args.business, args.version, args.output), indent=2))
