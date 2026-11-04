"""Generate lawful Prog source for explicit data/window/device/beep semantics.

No native code, runtime, PLC, process, queue or GUI is called. Supplied bindings
must be resolved from the current native inventory by the caller. This emitter
never derives a native ID, object expression, driver command or legacy flag.
"""
from decimal import Decimal, InvalidOperation
import re


class ContractError(ValueError):
    pass


_IDENTIFIER = re.compile(r"[A-Za-z_\u3400-\u9fff][A-Za-z0-9_\u3400-\u9fff]*\Z")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?\Z")
_KEYWORDS = {"IF", "THEN", "ELSE", "ENDIF", "WHILE", "BREAK", "ENDWHILE", "AND", "OR", "XOR", "NOT", "EXIT", "BYTE", "INTEGER", "SINGLE", "FLOAT", "STRING", "DIM"}
_EVIDENCE = {
    "vendor_help_contract": {"file": "data-window-device-source-semantics.json", "help_chm_sha256": "3bcc697f247a81b67f668ed972913d4f163a76c325827e4872e0bce455756556"},
    "script_window_func": {"path": r"C:\McgsPro\Program\plugins\script\script_window_func.dll", "sha256": "762203d18cade1199a2ddc91889af07eca4839ad05a4d3559a21789933eb633a", "set_window_argument_codes": [261, 4], "return_code": 4, "argument_metadata_va": "0x64304a40", "dispatch_va": "0x64303d50"},
    "script_tool_func": {"path": r"C:\McgsPro\Program\plugins\script\script_tool_func.dll", "sha256": "ab914207ae03c94df95eb1560434288a2edd00228af7c7ba08a6e4001c220988", "set_device_argument_codes": [262, 3, 8], "return_code": 4, "argument_metadata_va": "0x62a100b0", "dispatch_va": "0x62a0d7c0", "beep_argument_metadata_va": "0x62a10080", "beep_dispatch_va": "0x62a0c240"},
}


def _exact(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        raise ContractError("Missing or unknown explicit contract fields; legacy flags are not inferred")


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ContractError(label + " is outside its exact integral contract")
    return value


def _name(value):
    if not isinstance(value, str) or value == "_" or not _IDENTIFIER.fullmatch(value) or value.upper() in _KEYWORDS:
        raise ContractError("An actual bare object/variable name is required; no script text is accepted as a name")
    return value


def _expression(value):
    if not isinstance(value, str) or len(value) > 65536 or not value or any(_name(part) != part for part in value.split(".")):
        raise ContractError("Typed object expression must be an actual bare/qualified identifier from the native binding")
    return value


def _literal(value):
    if not isinstance(value, str) or len(value) > 131072 or "\0" in value or any(ord(c) < 32 and c not in "\r\n\t" for c in value):
        raise ContractError("String literal contains unsupported control characters or exceeds its explicit bound")
    value.encode("utf-16le", "strict")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t") + '"'


def _number(value):
    if not isinstance(value, str) or len(value) > 512 or not _NUMBER.fullmatch(value):
        raise ContractError("Numeric input must be exact finite decimal source text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ContractError("Invalid numeric literal") from error
    if not parsed.is_finite() or abs(parsed.adjusted()) > 308 or (parsed and parsed.copy_abs() < Decimal("1e-308")):
        raise ContractError("Numeric literal exceeds the bounded native floating-point contract")
    return value, parsed


def emit(action: dict) -> dict:
    """Return exactly source/required_bindings/required_timer_ids/source_evidence/semantic_limits.

    operation: data-assign | window-operation | device-operation | beep.
    The caller verifies returned required_bindings against its fresh native
    receipt before installing this text in a legal CStgyFuncProg row.
    """
    if not isinstance(action, dict) or "operation" not in action:
        raise ContractError("operation is required")
    kind = action["operation"]
    required = []
    limits = ["Configuration source generation only; no runtime, PLC or device operation was executed.",
              "The caller must resolve every supplied name, ID, native type and script_expression against the current complete native inventory; this module does not attest caller-supplied bindings.",
              "This explicit script contract is not a general equivalence claim for unsupported legacy flags/actions."]
    evidence = {"vendor_help": dict(_EVIDENCE["vendor_help_contract"])}

    def data(binding, writing=False, expected=None):
        _exact(binding, ("name", "native_id", "native_type"), ("writable", "flags", "initial_text"))
        name = _name(binding["name"])
        native_id = _integer(binding["native_id"], 0, 2147483647, "native variable ID")
        native_type = _integer(binding["native_type"], 1, 3, "CObjData native type")
        if expected is not None and native_type != expected:
            raise ContractError("Supplied data binding native type is incompatible; implicit conversion is not invented")
        if writing and binding.get("writable") is not True:
            raise ContractError("Assignment/result binding must explicitly be writable in the actual inventory")
        row = {"name": name, "native_id": native_id, "native_type": native_type, "access": "write" if writing else "read"}
        if "flags" in binding:
            row["flags"] = _integer(binding["flags"], 0, 4294967295, "actual data flags")
        if "initial_text" in binding:
            if not isinstance(binding["initial_text"], str):
                raise ContractError("initial_text must be the exact actual string")
            row["initial_text"] = binding["initial_text"]
        for old in required:
            if old.get("object_kind", "data") == "data" and old["native_id"] == native_id and (old["name"], old["native_type"]) != (name, native_type):
                raise ContractError("One native variable ID has contradictory name/type bindings")
        required.append(row)
        return name, native_type

    def typed(binding, object_kind):
        keys = ("object_kind", "name", "script_expression", "page_id") if object_kind == "window" else ("object_kind", "name", "script_expression", "native_serial", "path", "driver_uid")
        _exact(binding, keys)
        if binding["object_kind"] != object_kind:
            raise ContractError("Typed object binding kind differs")
        name, expression = _name(binding["name"]), _expression(binding["script_expression"])
        if expression.split(".")[-1] != name:
            raise ContractError("Actual typed expression leaf differs from its bound object name")
        row = dict(binding)
        if object_kind == "window":
            _integer(binding["page_id"], 0, 2147483647, "actual page ID")
            row["native_id"] = binding["page_id"]
            row["native_type"] = "window-reference-0x105"
        else:
            _integer(binding["native_serial"], 0, 2147483647, "actual device serial")
            if any(not isinstance(binding[x], str) or not binding[x] or "\0" in binding[x] for x in ("path", "driver_uid")):
                raise ContractError("Device path/driver UID must be exact actual nonempty strings")
            row["native_id"] = binding["native_serial"]
            row["native_type"] = "device-reference-0x106"
        row["access"] = "read"
        required.append(row)
        return expression

    def call_result(call):
        if "result" in action:
            result, _ = data(action["result"], True, 2)
            return result + "=" + call
        return call

    if kind == "data-assign":
        _exact(action, ("operation", "target", "value"))
        target, native_type = data(action["target"], True)
        value = action["value"]
        if not isinstance(value, dict) or "kind" not in value:
            raise ContractError("Explicit literal or data-object value is required")
        if value["kind"] == "data-object":
            _exact(value, ("kind", "binding"))
            expression, _ = data(value["binding"], False, native_type)
        elif value["kind"] == "literal":
            _exact(value, ("kind", "native_type", "text"))
            if type(value["native_type"]) is not int or value["native_type"] != native_type:
                raise ContractError("Literal native type must match the target; type coercion is not inferred")
            if native_type == 3:
                expression = _literal(value["text"])
            else:
                expression, parsed = _number(value["text"])
                if native_type == 1 and parsed not in (0, 1):
                    raise ContractError("Switch-object literal must be exactly Boolean0/1")
        else:
            raise ContractError("Unsupported assignment value kind")
        source = target + "=" + expression
        limits.append("CObjData1=switch,2=numeric,3=string. Assignment accepts same-type values only; group objects, read-only system objects and guessed numeric/string coercions are rejected.")
    elif kind == "window-operation":
        _exact(action, ("operation", "target", "mode"), ("result",))
        expression = typed(action["target"], "window")
        mode = _integer(action["mode"], 1, 5, "window operation")
        source = call_result("!SetWindow(" + expression + "," + str(mode) + ")")
        evidence["installed_declaration"] = dict(_EVIDENCE["script_window_func"])
        limits += ["Window modes1=open visible,2=open hidden,3=close,4=print,5=refresh. Native typed window reference is required, never a quoted name or invented numeric ID.",
                   "A print operation may cause original runtime printing/UI behavior; generating source does not execute it."]
    elif kind == "device-operation":
        _exact(action, ("operation", "target", "mode"), ("result", "period_ms", "command", "driver_command_contract"))
        expression = typed(action["target"], "device")
        mode = _integer(action["mode"], 1, 6, "device operation")
        command = ""
        if mode == 5:
            if "period_ms" not in action or "command" in action or "driver_command_contract" in action:
                raise ContractError("Cycle change requires only an explicit positive period_ms")
            command = str(_integer(action["period_ms"], 1, 2147483647, "device period milliseconds"))
        elif mode == 6:
            if "command" not in action or "driver_command_contract" not in action or "period_ms" in action:
                raise ContractError("Driver command requires exact command text and its explicit provider contract")
            if not isinstance(action["driver_command_contract"], str) or not action["driver_command_contract"].strip():
                raise ContractError("Provider-specific command semantics cannot be guessed")
            command = action["command"]
        elif any(key in action for key in ("command", "period_ms", "driver_command_contract")):
            raise ContractError("Modes1..4 take an empty command, no unused parameter fields")
        source = call_result("!SetDevice(" + expression + "," + str(mode) + "," + _literal(command) + ")")
        evidence["installed_declaration"] = dict(_EVIDENCE["script_tool_func"])
        if mode == 6:
            evidence["caller_bound_driver_command_contract"] = action["driver_command_contract"]
        limits += ["Device modes1=start,2=stop,3=query state,4=one collection,5=change collection period in milliseconds,6=provider-specific command.",
                   "Mode3 returns1 running/0 stopped; other documented returns0 success,-1 failure,-2 timeout. Optional numeric result binding preserves the actual return.",
                   "The first argument is the actual typed device reference resolved by the installed declaration, not a fabricated path string. Driver command safety and meaning remain the explicit bound provider contract."]
    elif kind == "beep":
        _exact(action, ("operation",), ("result",))
        source = call_result("!Beep()")
        evidence["installed_declaration"] = dict(_EVIDENCE["script_tool_func"])
        limits.append("Only original no-argument buzzer Beep is represented. This is never a WAV/file playback adapter or an equivalence claim for legacy sound flags.")
    else:
        raise ContractError("Unsupported operation; statistics, WAV playback, strategy-wide Exit and arbitrary legacy flags are not substituted")
    return {"source": source + "\r\n", "required_bindings": required, "required_timer_ids": [],
            "source_evidence": evidence, "semantic_limits": limits}
