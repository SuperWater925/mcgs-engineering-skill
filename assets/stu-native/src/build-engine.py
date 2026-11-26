"""Build the reusable x86 Stu design-time business engine without a vendor install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--csc", type=Path, default=Path(os.environ["SystemRoot"]) /
                        "Microsoft.NET/Framework/v4.0.30319/csc.exe")
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    assembly = output / "McgsStuBusinessEngine.dll"
    files = sorted(HERE.glob("*.cs"))
    subprocess.run([str(args.csc), "/nologo", "/target:library", "/platform:x86", "/codepage:65001", "/optimize+",
                    "/reference:System.Web.Extensions.dll", "/out:" + str(assembly), *map(str, files)], check=True)
    authorities = sorted((HERE.parent / "profile").glob("*.py")) + [HERE.parent / "profile/reference.json"]
    source_files = [Path(__file__).resolve(), *files, *authorities]
    manifest = {"family": "stu", "file": assembly.name, "sha256": sha256(assembly),
                "sources": [{"file": path.relative_to(REPO).as_posix(), "sha256": sha256(path)}
                            for path in sorted(source_files)]}
    manifest_file = output / "stu-engine-manifest.json"
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest_file)


if __name__ == "__main__":
    main()
