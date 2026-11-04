"""Pure source generation for explicit counter/timer semantics; never calls MCGS.

emit(action) accepts class_name, fields, bindings and an explicit state_contract.
Bindings must come from the current native catalog; this module reports the IDs it
requires and does not independently attest a supplied catalog or timer reservation.
No legacy action is created. The caller installs the returned text in a lawful Prog.
"""
from decimal import Decimal, InvalidOperation
import re


class ContractError(ValueError):
    pass


_IDENTIFIER = re.compile(r"[A-Za-z_\u3400-\u9fff][A-Za-z0-9_\u3400-\u9fff]*\Z")
_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?\Z")


def emit(action: dict) -> dict:
    """Return source, required_bindings, required_timer_ids and exact limits.

    Counter fields use the original UI names; only event_index 2/3 (rising/falling)
    have a closed sampled-Boolean implementation here. Timer fields likewise use
    the UI names, with a separately reserved timer_id and explicit false-condition
    policy. State roles are names in bindings, not arbitrary expressions or IDs
    inserted into the script. All writes require exclusive_state_variable_ids.
    """
    if not isinstance(action, dict):
        raise ContractError("action must be a mapping")
    kind, fields = action["class_name"], action["fields"]
    supplied, state = action["bindings"], action["state_contract"]
    required, writes = {}, set()

    def bind(role, expected_type, writing=False, field=None, initial=None):
        value = supplied[role]
        name, native_id, native_type = value["name"], value["native_id"], value["native_type"]
        if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
            raise ContractError(role + " requires a verified bare script variable name")
        if type(native_id) is not int or native_id < 0 or type(native_type) is not int or native_type != expected_type:
            raise ContractError(role + " native ID/type differs from its required current catalog record")
        if field is not None and fields[field] != name:
            raise ContractError(role + " must equal the original UI field's exact variable name")
        if initial is not None and value.get("initial_text") != initial:
            raise ContractError(role + " requires its explicit original initial_text=" + initial)
        required[role] = {"name": name, "native_id": native_id, "native_type": native_type,
                          "access": "write" if writing else "read"}
        if writing:
            if native_id in writes:
                raise ContractError("Every mutable state role requires a distinct native variable")
            writes.add(native_id)
        return name

    def expression(field, variable_type):
        raw = fields[field]
        if not isinstance(raw, str) or not raw:
            raise ContractError(field + " must be exact text")
        if _DECIMAL.fullmatch(raw):
            try:
                number = Decimal(raw)
            except InvalidOperation as exc:
                raise ContractError(field + " is not a finite numeric literal") from exc
            if not number.is_finite():
                raise ContractError(field + " is not finite")
            return "(" + raw + ")", number
        return bind(field, variable_type, field=field), None

    def common():
        exclusive = state["exclusive_state_variable_ids"]
        if not isinstance(exclusive, list) or any(type(x) is not int for x in exclusive):
            raise ContractError("exclusive_state_variable_ids must be explicit native IDs")
        if len(exclusive) != len(set(exclusive)) or set(exclusive) != writes:
            raise ContractError("Exclusive native state IDs must exactly equal all generated writes")
        read_ids = {x["native_id"] for x in required.values() if x["access"] == "read"}
        if writes & read_ids:
            raise ContractError("Output/state variables must not alias an input/reset/preset variable")
        by_id = {}
        for value in required.values():
            old = by_id.setdefault(value["native_id"], value)
            if (old["name"], old["native_type"]) != (value["name"], value["native_type"]):
                raise ContractError("One native ID was supplied with contradictory names/types")

    source, timer_ids, limits = [], [], []
    if kind == "CStgyFuncCounter":
        event = fields["event_index"]
        if event not in (2, 3):
            raise ContractError("Only original event2 rising/event3 falling have closed sampled-edge semantics; alarm/event and two-stage events are not guessed")
        signal = bind("counter_object", 1, field="counter_object")
        current = bind("current_value", 2, True, "current_value", "0")
        done = bind("state_variable", 1, True, "state_variable", "0")
        previous = bind("previous", 1, True, initial="0")
        ready = bind("initialized", 1, True, initial="0")
        reset, reset_literal = expression("reset_condition", 1)
        preset, preset_literal = expression("preset_value", 2)
        if reset_literal is not None and reset_literal not in (0, 1):
            raise ContractError("Literal reset condition must be Boolean 0/1")
        if preset_literal is not None and preset_literal < 0:
            raise ContractError("Preset must be nonnegative")
        if state["initial_previous"] != "sample_input" or state["initial_value"] != "0":
            raise ContractError("Initialization must explicitly sample the input and begin at zero")
        if state["reset_priority"] != "reset_before_edge":
            raise ContractError("Reset priority must be explicit")
        if state["invocation_contract"] != "each_input_transition_at_most_one_edge_per_invocation":
            raise ContractError("Sampled edges cannot substitute for an unobserved event count")
        policy = state["count_policy"]
        if policy not in ("count_each_selected_edge", "saturate_at_preset"):
            raise ContractError("A counter count policy must be explicitly selected")
        source += [f"IF {ready}=0 THEN", f"  {current}=0", f"  {done}=0", f"  {previous}={signal}", f"  {ready}=1", "ENDIF"]
        source += [f"IF {reset}<>0 THEN", f"  {current}=0", "ELSE"]
        conditions = (f"{previous}=0", f"{signal}<>0") if event == 2 else (f"{previous}<>0", f"{signal}=0")
        source += [f"  IF {conditions[0]} THEN", f"    IF {conditions[1]} THEN"]
        if policy == "saturate_at_preset":
            source += [f"      IF {current}<{preset} THEN", f"        {current}={current}+1", "      ENDIF"]
        else:
            source += [f"      {current}={current}+1"]
        source += ["    ENDIF", "  ENDIF", "ENDIF", f"IF {current}>={preset} THEN", f"  {done}=1", "ELSE", f"  {done}=0", "ENDIF", f"{previous}={signal}"]
        limits += ["Sampled Boolean edge algorithm with explicitly chosen count/reset policies; not claimed byte-for-byte equivalent to the unsupported legacy runtime block.",
                   "The caller must invoke once per relevant input transition; multiple transitions between invocations cannot be reconstructed.",
                   "Numeric object precision/range still applies; unbounded counting is not an infinite-precision integer."]
    elif kind == "CStgyFuncTimer":
        slot = action["timer_id"]
        reservation = action["timer_reservation"]
        if type(slot) is not int or not 0 <= slot <= 127 or reservation["timer_id"] != slot:
            raise ContractError("An explicitly reserved system timer ID0..127 is required")
        if not isinstance(reservation["owner"], str) or not reservation["owner"] or not re.fullmatch(r"[a-f0-9]{64}", reservation["project_sources_sha256"]):
            raise ContractError("Timer reservation requires an owner and exact complete source-catalog SHA")
        if reservation["exclusive_for_this_action"] is not True:
            raise ContractError("Timer ownership must be explicitly declared, never inferred from an unused-looking number")
        signal, _ = expression("timing_condition", 1)
        reset, reset_literal = expression("reset_condition", 1)
        preset, preset_literal = expression("preset_seconds", 2)
        if reset_literal is not None and reset_literal not in (0, 1):
            raise ContractError("Literal reset condition must be Boolean 0/1")
        if preset_literal is not None and preset_literal <= 0:
            raise ContractError("Finite timer preset must be positive; native nonpositive means unlimited")
        current = bind("current_seconds", 2, True, "current_seconds", "0")
        done = bind("state_variable", 1, True, "state_variable", "0")
        ready = bind("initialized", 2, True, initial="0")
        result = bind("last_result", 2, True, initial="0")
        cached_preset = bind("preset_cache", 2, True, initial="0")
        interval = state["interval_seconds"]
        if not isinstance(interval, str) or not _DECIMAL.fullmatch(interval) or Decimal(interval) < Decimal("0.1"):
            raise ContractError("Timer interval must be an explicit finite decimal >=0.1 seconds")
        false_policy = state["condition_false_policy"]
        if false_policy not in ("pause_and_resume", "reset_when_false"):
            raise ContractError("False-condition behavior must be explicitly selected")
        if state["output_mode"] != "poll_original_TimerValue" or state["reset_priority"] != "reset_before_run":
            raise ContractError("Timer output/reset contract differs")
        source += [f"IF {ready}<>-1 THEN", f"  IF {preset}<=0 THEN", f"    {result}=!TimerStop({slot})", f"    {ready}=-1", "  ENDIF", "ENDIF"]
        source += [f"IF {ready}=0 THEN", f"  {ready}=-1", f"  {result}=!TimerStop({slot})"]
        for call in (f"!TimerReset({slot},0)", f"!TimerSetLimit({slot},{preset},1)", f"!TimerChangeInterval({slot},{interval})"):
            source += [f"  IF {result}=0 THEN", f"    {result}={call}", "  ENDIF"]
        source += [f"  IF {result}=0 THEN", f"    {ready}=1", f"    {current}=0", f"    {done}=0", f"    {cached_preset}={preset}", "  ENDIF", "ENDIF", f"IF {ready}=1 THEN", f"  IF {cached_preset}<>{preset} THEN", f"    {result}=!TimerSetLimit({slot},{preset},1)", f"    IF {result}=0 THEN", f"      {cached_preset}={preset}", "    ELSE", f"      {ready}=-1", "    ENDIF", "  ENDIF", "ENDIF", f"IF {ready}=1 THEN", f"  IF {reset}<>0 THEN", f"    {result}=!TimerStop({slot})", f"    IF {result}=0 THEN", f"      {result}=!TimerReset({slot},0)", "    ENDIF", "  ELSE", f"    IF {signal}<>0 THEN", f"      IF !TimerValue({slot})<{preset} THEN", f"        IF !TimerState({slot})<>1 THEN", f"          {result}=!TimerRun({slot})", "        ENDIF", "      ENDIF", "    ELSE", f"      IF !TimerState({slot})=1 THEN", f"        {result}=!TimerStop({slot})", "      ENDIF"]
        if false_policy == "reset_when_false":
            source += [f"      IF {result}=0 THEN", f"        {result}=!TimerReset({slot},0)", "      ENDIF"]
        source += ["    ENDIF", "  ENDIF", f"  IF {result}=0 THEN", f"    {current}=!TimerValue({slot})", f"    IF {current}>={preset} THEN", f"      {done}=1", "    ELSE", f"      {done}=0", "    ENDIF", "  ELSE", f"    {ready}=-1", "  ENDIF", "ENDIF"]
        timer_ids = [{"timer_id": slot, "owner": reservation["owner"], "reservation": reservation}]
        limits += ["Uses the original timer functions with stop-at-limit mode1 and an explicit pause/reset policy; it is not an inferred implementation of unsupported legacy Timer block flags.",
                   "System timer IDs are global runtime slots, distinct from CObjData IDs, strategy IDs and row numbers. No timer is allocated or exercised by this generator.",
                   "Nonzero native operation status latches initialized=-1; application code must explicitly decide recovery rather than silently retry.",
                   "This finite-delay adapter latches initialized=-1 if a dynamic preset becomes nonpositive; native unlimited-timer semantics are exposed by the original APIs, not silently treated as a finite delay.",
                   "Preset/interval use native rounding. Poll output updates on each invocation. No blocking TimerWaitFor is emitted."]
    else:
        raise ContractError("This module emits only Counter/Timer alternatives")
    common()
    return {"source": "\r\n".join(source) + "\r\n", "required_bindings": required,
            "required_timer_ids": timer_ids,
            "source_evidence": ["timer-counter-source-semantics.json", "timer-counter-native-static-proof.json"],
            "semantic_limits": limits + ["Supplied native bindings/reservation must be independently reconciled with the fresh project catalog; this pure generator does not attest them.",
                                        "Install as a product-supported original Prog and use the original project Check; Linux runtime behavior has not been exercised."],
            "runtime_called": False, "native_check_passed": False}
