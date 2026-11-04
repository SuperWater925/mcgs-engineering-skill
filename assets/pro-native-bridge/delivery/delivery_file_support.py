"""Small file-only support for the frozen source delivery binder.

There is deliberately no recursive task/evidence discovery in the deployable
tool. Its sole inputs are an explicitly reviewed source-stage manifest and the
hash-matching selected source/ABI files already shipped beside it.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(os.path.abspath(os.fspath(path)))
    for at in (path, *path.parents):
        if os.path.lexists(at):
            info = os.lstat(at)
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Reparse-point delivery input: " + str(at))
    if not path.is_file():
        raise ValueError("Expected regular file: " + str(path))
    return path


def load(path):
    return json.loads(regular(path).read_text(encoding="utf-8-sig"))


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
