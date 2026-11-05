"""Correlated, at-most-once submission client; local file queue only.

When deployed, ROOT is this script's containing runtime directory.
The durable client submission record must not be deleted to retry an uncertain
operation. A timeout is neither cancellation nor permission to use a new ID.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

ROOT = Path(__file__).resolve().parent
MAX_RECEIPT_BYTES = (1 << 31) - 1  # CLR/x86 length representation, not a sample quota.
HOST_DIRECTORIES = ("inbox", "outbox", "processed", "claims", "claimed")
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {x + str(i) for x in ("COM", "LPT") for i in range(1, 10)}

_EVENT_KERNEL = None


def _event_kernel():
    global _EVENT_KERNEL
    if _EVENT_KERNEL is None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("OpenEventW", [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p], ctypes.c_void_p),
            ("CreateEventW", [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p], ctypes.c_void_p),
            ("SetEvent", [ctypes.c_void_p], ctypes.c_int),
            ("WaitForSingleObject", [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32),
            ("CloseHandle", [ctypes.c_void_p], ctypes.c_int),
        ):
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result
        _EVENT_KERNEL = kernel
    return _EVENT_KERNEL


def _signal_scope(root):
    try:
        value = json.loads((Path(root) / "active-engine.json").read_text(encoding="utf-8-sig"))
        scope = value.get("bootstrap_scope_sha256")
        if isinstance(scope, str) and re.fullmatch(r"[0-9a-f]{64}", scope):
            return scope
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _notify_submission(root):
    """Best-effort notification; durable submission and correlation are unchanged."""
    if os.name != "nt":
        return False
    try:
        scope = _signal_scope(root)
        if not scope:
            return False
        kernel = _event_kernel()
        handle = kernel.OpenEventW(2, False, "Local\\McgsInternalBridgeWake_" + scope)
        if not handle:
            return False
        try:
            return bool(kernel.SetEvent(handle))
        finally:
            kernel.CloseHandle(handle)
    except Exception:
        return False


class _ResponseWaiter:
    """One advisory event and one scope read for this request's lifetime."""
    def __init__(self, root, request_id):
        self.scope = self.kernel = self.handle = None
        if os.name == "nt":
            try:
                self.scope = _signal_scope(root)
                if self.scope:
                    self.kernel = _event_kernel()
                    self.handle = self.kernel.CreateEventW(None, False, False,
                        "Local\\McgsInternalBridgeReply_" + self.scope + "_" + request_id)
            except Exception:
                self.close()

    def notify_submission(self):
        if not self.scope or self.kernel is None:
            return False
        handle = None
        try:
            handle = self.kernel.OpenEventW(2, False, "Local\\McgsInternalBridgeWake_" + self.scope)
            return bool(handle and self.kernel.SetEvent(handle))
        except Exception:
            return False
        finally:
            if handle:
                try:
                    self.kernel.CloseHandle(handle)
                except Exception:
                    pass

    def wait(self, seconds):
        delay = max(0.0, min(0.1, seconds))
        if self.handle:
            try:
                if self.kernel.WaitForSingleObject(self.handle, max(1, int(delay * 1000))) in (0, 258):
                    return
            except Exception:
                pass
            self.close()
        time.sleep(delay)

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            try:
                self.kernel.CloseHandle(handle)
            except Exception:
                pass


def _response_waiter(root, request_id):
    return _ResponseWaiter(root, request_id)


def _wait_for_response(root, request_id, seconds):
    """Compatibility wrapper; new callers retain a waiter for the request."""
    waiter = _response_waiter(root, request_id)
    try:
        waiter.wait(seconds)
    finally:
        waiter.close()


class SubmissionError(ValueError):
    def __init__(self, message, state):
        super().__init__(message)
        self.state = state


class ReceiptError(SubmissionError):
    pass


class QueueTimeout(TimeoutError):
    def __init__(self, message, state):
        super().__init__(message)
        self.state = state


def _exists(path):
    return os.path.lexists(path)


def _not_reparse(path):
    # ROOT is canonical at connection setup. Resolve an explicitly configured
    # junction/UNC location; request uniqueness and exact receipt correlation
    # still apply to the real files.
    return Path(path).resolve(strict=True).stat()


def _directory(path, create=False):
    if create:
        path.mkdir(exist_ok=True)
    info = _not_reparse(path)
    if not stat.S_ISDIR(info.st_mode):
        raise OSError("Queue path is not a directory: " + str(path))


def _read(path, maximum=MAX_RECEIPT_BYTES):
    path = Path(path).resolve(strict=True)
    info = _not_reparse(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise OSError("Queue record is not a bounded regular file: " + str(path))
    if os.name != "nt":
        with path.open("rb") as stream:
            data = stream.read(maximum + 1)
    else:
        # Share delete as well as read/write, so inspection cannot block the
        # host's atomic claim/outbox publication.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x00200080, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            parts, total = [], 0
            while True:
                buffer, count = ctypes.create_string_buffer(65536), ctypes.c_uint32()
                if not kernel.ReadFile(handle, buffer, 65536, ctypes.byref(count), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not count.value:
                    break
                total += count.value
                if total > maximum:
                    raise OSError("Queue record exceeds maximum length")
                parts.append(buffer.raw[:count.value])
            data = b"".join(parts)
        finally:
            kernel.CloseHandle(handle)
    if len(data) > maximum:
        raise OSError("Queue record exceeds maximum length")
    return data


def _json(path):
    value = json.loads(_read(path).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Queue record must be a JSON object")
    return value


def _paths(root, request_id):
    return {name: root / name / (request_id + ".json") for name in HOST_DIRECTORIES}


def _state(root, request_id, payload_sha):
    result = {"request_id": request_id, "queue_request_sha256": payload_sha,
              "automatic_retry": False, "timeout_is_cancellation": False, "host": {}}
    for name, path in _paths(root, request_id).items():
        try:
            present = _exists(path)
            entry = {"exists": present}
            if present:
                _not_reparse(path)
                if name == "claims":
                    claim = _json(path)
                    # Deliberately omit any payload, result, or account content.
                    entry["metadata"] = {key: claim[key] for key in
                        ("status", "request_id", "request_sha256", "owner_process_id", "owner_process_start_ticks", "claim_token", "business_dispatch_entered", "response_published", "error_type") if key in claim}
            result["host"][name] = entry
        except Exception as error:
            result["host"][name] = {"inspection_error": type(error).__name__ + ": " + str(error)}
    reservation = root / "client-submissions" / (request_id + ".json")
    try:
        result["client_submission_exists"] = _exists(reservation)
        if result["client_submission_exists"]:
            item = _json(reservation)
            result["client_submission"] = {key: item[key] for key in ("phase", "request_sha256", "owner_pid", "submission_token") if key in item}
    except Exception as error:
        result["client_submission_inspection_error"] = type(error).__name__ + ": " + str(error)
    return result


def _unused(paths):
    return [name for name, path in paths.items() if _exists(path)]


def _write_new(path, data):
    # A failed write/flush leaves an occupied record. It is intentionally never
    # removed as though no submission had been attempted.
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _record_phase(path, token, phase):
    current = _json(path)
    if current.get("submission_token") != token:
        raise OSError("Client submission ownership changed")
    current["phase"] = phase
    current.setdefault("phase_utc", {})[phase] = datetime.now(timezone.utc).isoformat()
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".staging")
    try:
        _write_new(temporary, _encoded(current))
        os.replace(temporary, path)  # Only our owned client metadata, never inbox.
    finally:
        if _exists(temporary):
            temporary.unlink()


def _publish_no_replace(temporary, target):
    if os.name == "nt":
        # Windows rename fails if target exists. Do not use Path.replace.
        os.rename(temporary, target)
    else:
        # Equivalent same-volume no-overwrite publication on POSIX.
        os.link(temporary, target)
        temporary.unlink()


def invoke(op, expected_project=None, request_id=None, timeout=30):
    if not isinstance(op, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", op):
        raise ValueError("Operation must be lower-case ASCII [a-z][a-z0-9_-], at most 80 characters")
    if request_id is None:
        request_id = op.replace("-", "_")[:67] + "_" + uuid.uuid4().hex[:12]
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id) or request_id.upper() in RESERVED:
        raise ValueError("Request id must be 1..80 ASCII letters/numbers, underscore or hyphen, excluding reserved device names")
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Timeout must be finite and nonnegative")
    request = {"op": op, "schema": 1, "request_id": request_id}
    if expected_project:
        request["expected_project"] = str(Path(expected_project).resolve())
    payload = _encoded(request)
    payload_sha = hashlib.sha256(payload).hexdigest()
    root = Path(ROOT).absolute()
    root.mkdir(parents=True, exist_ok=True)
    _directory(root)
    for name in HOST_DIRECTORIES:
        path = root / name
        if name in ("inbox", "outbox"):
            _directory(path, True)
        elif _exists(path):
            _directory(path)
    submissions = root / "client-submissions"
    _directory(submissions, True)
    paths = _paths(root, request_id)
    if _unused(paths):
        raise SubmissionError("Request id already exists in host state; do not resubmit", _state(root, request_id, payload_sha))
    reservation = submissions / (request_id + ".json")
    token = uuid.uuid4().hex
    record = {"schema": 1, "request_id": request_id, "request_sha256": payload_sha,
              "owner_pid": os.getpid(), "submission_token": token, "phase": "reserved"}
    try:
        _write_new(reservation, _encoded(record))
    except Exception as error:
        raise SubmissionError("Client id reservation failed or is already occupied; no automatic retry: " + type(error).__name__, _state(root, request_id, payload_sha)) from error
    waiter = _response_waiter(root, request_id)
    try:
        temporary = paths["inbox"].parent / ("." + request_id + "." + token + ".staging")
        published = False
        try:
            _write_new(temporary, payload)
            if _unused(paths):
                raise SubmissionError("Host state appeared before publication; no automatic retry", _state(root, request_id, payload_sha))
            _publish_no_replace(temporary, paths["inbox"])
            published = True
            _record_phase(reservation, token, "published")
            waiter.notify_submission()
        except Exception as error:
            # The durable record survives all errors. An OS error can leave the
            # publication outcome uncertain; never regenerate an ID or resend.
            if not published and _exists(temporary):
                temporary.unlink()
            if isinstance(error, SubmissionError):
                raise
            raise SubmissionError("Submission could not be confirmed; inspect state and never automatically retry: " + type(error).__name__, _state(root, request_id, payload_sha)) from error
        deadline = time.monotonic() + timeout
        while True:
            if _exists(paths["outbox"]):
                try:
                    receipt = _json(paths["outbox"])
                    if receipt.get("request_id") != request_id:
                        raise ValueError("Response request_id does not match submitted id")
                    if receipt.get("queue_request_sha256") != payload_sha:
                        raise ValueError("Response queue_request_sha256 does not match exact submitted bytes")
                except Exception as error:
                    raise ReceiptError("Untrusted or uncorrelated queue response: " + str(error), _state(root, request_id, payload_sha)) from error
                try:
                    _record_phase(reservation, token, "correlated-response")
                except Exception as error:
                    # The business receipt is already correlated. A client journal
                    # bookkeeping failure must not hide it or imply non-execution.
                    receipt["client_transport_warning"] = {
                        "correlated_response_verified": True,
                        "client_journal_update_failed": type(error).__name__ + ": " + str(error),
                        "automatic_retry": False,
                        "transport_state": _state(root, request_id, payload_sha),
                    }
                return receipt
            if time.monotonic() >= deadline:
                raise QueueTimeout("No correlated response before timeout. Execution outcome is unknown; do not resubmit with this or a new id.", _state(root, request_id, payload_sha))
            waiter.wait(max(0, deadline - time.monotonic()))
    finally:
        waiter.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("op")
    parser.add_argument("--project")
    parser.add_argument("--id")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        result = invoke(args.op, args.project, args.id, args.timeout)
    except (SubmissionError, QueueTimeout) as error:
        result = {"ok": False, "error_type": type(error).__name__, "error": str(error), "transport_state": error.state}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if result.get("ok") else 1)
