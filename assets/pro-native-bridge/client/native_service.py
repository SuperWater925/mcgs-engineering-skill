"""Persistent JSON-lines client for one selected native connection.

The interpreter, verified transport and connection caches stay alive across
read/edit/save calls. The native queue retains one durable request/result per
call and executes on the original UI thread. No automatic mutation retry.
"""
import json
from pathlib import Path
import sys
import time
import uuid

import edit_batch_client as batch


def dispatch(message):
    if not isinstance(message, dict):
        raise ValueError("Expected a JSON request object")
    method = message.get("method")
    if method == "status" and not message.get("id"):
        raise ValueError("status needs the original request id")
    request_id = message.get("id") or "persistent_" + uuid.uuid4().hex
    message["id"] = request_id
    if not isinstance(request_id, str) or not batch.re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
        raise ValueError("Invalid request id")
    if method == "status":
        record_path = batch.RUNTIME / "client-submissions" / (request_id + ".json")
        record = batch.read_json(record_path)[0] if record_path.is_file() else {}
        return {"id": request_id, "state": batch.load_client()._state(batch.RUNTIME, request_id, record.get("request_sha256")),
                "automatic_retry": False}
    if method not in ("inspect", "execute"):
        raise ValueError("Supported methods: inspect, execute, status, stop")
    project = str(Path(message["project"]).expanduser().resolve(strict=True))
    request = {"op": "engineering-edit-inspect" if method == "inspect" else "engineering-edit-batch",
               "expected_project": project}
    specification = message.get("specification")
    if specification is not None:
        if not isinstance(specification, dict):
            raise ValueError("specification must be an object")
        # Freeze exactly once, irrespective of control count. A repeated id
        # cannot replace a prior intent or silently replay a finished command.
        path = batch.RUNTIME / "persistent-input" / (request_id + ".json")
        sha = batch.write_new(path, specification)
    elif message.get("specification_file"):
        path = batch.input_file(message["specification_file"])
        _, sha = batch.read_json(path)
    elif method == "execute":
        raise ValueError("execute requires a specification")
    else:
        path = None
    if path is not None:
        prefix = "inspection" if method == "inspect" else "specification"
        request.update({prefix + "_file": str(path), prefix + "_sha256": sha})
    clock = time.perf_counter()
    result = batch.submit(request, request_id, message.get("timeout", 60))
    return {"id": request_id, "elapsed_seconds": time.perf_counter() - clock, "result": result}


def serve(input_stream=None, output_stream=None):
    source, sink = input_stream or sys.stdin, output_stream or sys.stdout
    sink.write(json.dumps({"ready": True, "protocol": "mcgs-native-jsonl/v1",
                           "scope_sha256": batch._LAYOUT.configuration_sha256,
                           "process_reused": True, "native_invoked": False}) + "\n")
    sink.flush()
    for line in source:
        if not line.strip():
            continue
        message = None
        try:
            message = json.loads(line)
            if isinstance(message, dict) and not message.get("id") and message.get("method") != "status":
                # Assign before dispatch so even validation/fsync/transport
                # errors return the durable request identity to the caller.
                message["id"] = "persistent_" + uuid.uuid4().hex
            if isinstance(message, dict) and message.get("method") == "stop":
                sink.write(json.dumps({"id": message.get("id"), "stopped": True, "pro_closed": False}) + "\n")
                sink.flush()
                return 0
            result = dispatch(message)
        except Exception as error:
            result = {"id": message.get("id") if isinstance(message, dict) else None,
                      "ok": False, "error_type": type(error).__name__, "error": str(error),
                      "automatic_retry": False}
            if hasattr(error, "state"):
                result["transport_state"] = error.state
        sink.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
        sink.flush()
    return 0
