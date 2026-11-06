"""Explicit immutable layout for delivery clients. Pure files; no process/native API."""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import threading

TRANSPORT_SHA256 = "298e62cf5798acc03d82af5dd5b5751703a1e65348e12a485780239c01fe3417"
CLR_MAX_LENGTH = (1 << 31) - 1
_FIELDS = {"schema", "task_root", "engineering_root", "runtime_root", "install_root", "transport_client_file", "transport_client_sha256"}
_PORTABLE_FIELDS = {"portable_engine_contract", "portable_binding_file", "portable_binding_sha256"}
_OPTIONAL_FIELDS = {"editor_executable"} | _PORTABLE_FIELDS
_current = None
_verified_files = {}
_verification_lock = threading.RLock()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _not_reparse(path):
    # Bind the real target, including installations reached through junctions.
    # File-ID/size/time and SHA checks below still detect target replacement.
    return Path(path).expanduser().resolve(strict=False)


def _regular(path, maximum):
    path = _not_reparse(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
        raise ValueError("Delivery input is not a bounded regular file: " + str(path))
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        # Windows/Python versions may expose different ctime semantics through
        # path stat versus fstat. Compare IDs/size/mtime across those APIs, then
        # compare ctime only within the same API before/after the read.
        if _identity(opened)[:4] != _identity(info)[:4]:
            raise ValueError("Delivery input identity changed before opening")
        data = stream.read(maximum + 1)
        final = os.fstat(stream.fileno())
    if _identity(final) != _identity(opened) or _identity(path.stat()) != _identity(info) or len(data) != info.st_size or len(data) > maximum:
        raise ValueError("Delivery input changed while reading")
    return data


def _verify_file(path, maximum, expected_sha256):
    """Reuse a verified digest only while the exact file identity is unchanged.

    Every check still examines path ancestors and regular-file metadata. Replace,
    resize, mtime or ctime changes invalidate the cache. Filesystems without a
    nonzero file ID always take the full-read/hash path. This cache is local to
    one client process and never attests vendor ABI or native memory.
    """
    path = _not_reparse(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
        raise ValueError("Delivery input is not a bounded regular file: " + str(path))
    identity = _identity(info)
    key = (os.path.normcase(str(path)), maximum, expected_sha256)
    with _verification_lock:
        if info.st_ino and _verified_files.get(key) == identity:
            return
        data = _regular(path, maximum)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError("Bound delivery file SHA changed: " + str(path))
        final = _identity(path.stat())
        if final != identity:
            raise ValueError("Bound delivery file changed during verification")
        if info.st_ino:
            _verified_files[key] = final


def _absolute(text):
    if not isinstance(text, str) or not text or "\0" in text or not Path(text).is_absolute():
        raise ValueError("Delivery paths must be explicit absolute strings")
    return _not_reparse(text)


def _directory(text):
    path = _absolute(text)
    if not path.is_dir():
        raise ValueError("Delivery directory is absent: " + str(path))
    return path


@dataclass(frozen=True)
class DeliveryLayout:
    configuration_file: Path
    configuration_sha256: str
    task_root: Path
    engineering_root: Path
    runtime_root: Path
    install_root: Path
    transport_client_file: Path
    transport_client_sha256: str
    editor_executable: Path | None = None
    portable_binding_file: Path | None = None
    portable_binding_sha256: str | None = None

    @property
    def program_root(self):
        return (self.editor_executable or self.install_root / "Program" / "McgsSetPro.exe").parent

    @property
    def working_root(self):
        return self.runtime_root / "engineering"

    @property
    def evidence_root(self):
        return self.engineering_root / "task-evidence"

    def check(self):
        _verify_file(self.configuration_file, CLR_MAX_LENGTH, self.configuration_sha256)
        for path in (self.task_root, self.engineering_root, self.runtime_root, self.install_root):
            if not _not_reparse(path).is_dir():
                raise ValueError("Bound delivery directory changed")
        if not _not_reparse(self.evidence_root).is_dir():
            raise ValueError("Bound immutable task-evidence payload has not been deployed")
        _verify_file(self.transport_client_file, CLR_MAX_LENGTH, self.transport_client_sha256)
        if self.portable_binding_file is not None:
            _verify_file(self.portable_binding_file, CLR_MAX_LENGTH, self.portable_binding_sha256)


def load(path, expected_sha256):
    if not isinstance(expected_sha256, str) or re.fullmatch("[a-f0-9]{64}", expected_sha256) is None:
        raise ValueError("An exact bound configuration SHA256 is required")
    path = _absolute(path)
    raw = _regular(path, CLR_MAX_LENGTH)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Delivery configuration SHA differs")
    data = json.loads(raw.decode("utf-8-sig"))
    return validate_mapping(data, path, expected_sha256)


def _selected_editor(data, install):
    editor = _absolute(data["editor_executable"]) if "editor_executable" in data else install / "Program" / "McgsSetPro.exe"
    if not editor.is_file() or not editor.is_relative_to(install):
        raise ValueError("Selected editor must be an existing executable inside the declared installation root: " + str(editor))
    if "editor_executable" in data:
        # This is a package asset path, never a discovery of user/task locations.
        package = Path(__file__).resolve().parent.parent
        if package.name == "delivery":
            package = package.parent
        helper = package / "bootstrap" / "pe_image.py"
        spec = importlib.util.spec_from_file_location("mcgs_delivery_pe_image", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.pe32_identity(editor)
    return editor


def validate_mapping(data, configuration_file, configuration_sha256):
    """Validate file-only binding input before creating any output directory."""
    path = _absolute(os.fspath(configuration_file))
    if not isinstance(configuration_sha256, str) or re.fullmatch("[a-f0-9]{64}", configuration_sha256) is None:
        raise ValueError("An exact configuration SHA256 is required")
    if not isinstance(data, dict) or not _FIELDS.issubset(data) or not set(data).issubset(_FIELDS | _OPTIONAL_FIELDS) or type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("Unknown delivery layout schema or fields")
    task, engineering, runtime, install = (_directory(data[key]) for key in ("task_root", "engineering_root", "runtime_root", "install_root"))
    if task == Path(task.anchor) or runtime == task or not runtime.is_relative_to(task):
        raise ValueError("Runtime must be an explicit child of an owned task directory, not a whole volume")
    if engineering.is_relative_to(runtime) or runtime.is_relative_to(engineering):
        raise ValueError("Frozen engineering payload and writable runtime must be disjoint")
    transport = _absolute(data["transport_client_file"])
    if not (transport.is_relative_to(task) or transport.is_relative_to(engineering)):
        raise ValueError("Transport source is outside both declared roots")
    if data["transport_client_sha256"] != TRANSPORT_SHA256:
        raise ValueError("Verified at-most-once transport source differs")
    _verify_file(transport, CLR_MAX_LENGTH, TRANSPORT_SHA256)
    editor = _selected_editor(data, install)
    binding, binding_sha = None, None
    if _PORTABLE_FIELDS.intersection(data):
        if not _PORTABLE_FIELDS.issubset(data) or data["portable_engine_contract"] != "mcgs-portable-engine/v1":
            raise ValueError("Portable engine binding fields must be supplied together")
        if transport.parent != runtime:
            raise ValueError("Portable queue transport must be directly inside runtime_root")
        binding, binding_sha = _absolute(data["portable_binding_file"]), data["portable_binding_sha256"]
        if not binding.is_relative_to(engineering) or not isinstance(binding_sha, str) or re.fullmatch("[a-f0-9]{64}", binding_sha) is None:
            raise ValueError("Portable binding must declare actual SHA and an engineering-payload path")
        _verify_file(binding, CLR_MAX_LENGTH, binding_sha)
    return DeliveryLayout(path, configuration_sha256, task, engineering, runtime, install, transport, TRANSPORT_SHA256, editor, binding, binding_sha)


def configure(path, expected_sha256):
    global _current
    value = load(path, expected_sha256)
    if _current is not None and value != _current:
        raise ValueError("Client delivery layout is already bound; do not rebind one process")
    _current = value
    return value


def current():
    if _current is None:
        raise ValueError("Use the native_engineering.py entry with explicit --scope-config and --scope-sha256; no implicit directory discovery")
    _current.check()
    return _current
