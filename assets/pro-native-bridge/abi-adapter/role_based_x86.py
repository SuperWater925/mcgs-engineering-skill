"""Resolve independently identified native roles despite implementation changes.

No old-RVA fallback, guessed role or private-layout proof is produced here.
The caller must reject competing identities and retain dependency tracking.
"""
from __future__ import annotations
import copy
import struct

from adaptive_x86 import _effective_thunk
from x86_signature import decode_signature


def entry_chain(image, address):
    """Decode the current entry and its unconditional same-image thunk chain."""
    cursor, chain, seen = address, [], set()
    try:
        while cursor not in seen and image.is_executable(cursor):
            seen.add(cursor)
            section = image.section_for_rva(cursor)
            remaining = section.raw_size - (cursor - section.rva)
            if remaining <= 0:
                return None
            part = decode_signature(image, cursor, min(32, remaining))
            chain.append(part)
            transfer = _effective_thunk(part)
            if transfer is None:
                return chain
            cursor = transfer["reference_target_rva"]
    except (ValueError, KeyError, IndexError, struct.error):
        return None
    return None


def match(reference, image, address, identity):
    if (not isinstance(identity, dict) or identity.get("independent") is not True
            or identity.get("actual_rva") != address or not identity.get("proof_id")
            or identity.get("kind") not in ("named-export", "rtti-slot", "proven-caller-role")
            or not image.is_executable(address)):
        return None
    if identity["kind"] == "named-export" and not identity.get("names"):
        return None
    if identity["kind"] == "rtti-slot" and (not identity.get("method_names")
            or not identity.get("decorated_name") or type(identity.get("slot_index")) is not int
            or identity["slot_index"] < 0):
        return None
    if identity["kind"] == "proven-caller-role" and not identity.get("supporting_proof_ids"):
        return None
    chain = entry_chain(image, address)
    if chain is None:
        return None
    entry, body = chain[0], chain[-1]
    # An entry ending in a return or jump has a meaningful short prefix.
    # Use complete live entry instructions even if adjacent code is readable.
    guard_span = entry["match_length"]
    proof = {"kind": "current-interface-role", "identity": copy.deepcopy(identity),
             "actual_entry_rva": address, "actual_body_rva": body["reference_rva"],
             "actual_entry_chain": [part["reference_rva"] for part in chain],
             "live_entry_guard_span": guard_span, "implementation_bytes_may_differ": True,
             "private_layout_proved": False, "calling_contract": "declared-native-interface-role",
             "old_terminal_body_not_required": True}
    return {"actual": body, "context": {"normalization_proofs": [proof], "referents": []},
            "adaptive": True, "identity": identity, "evidence": proof}
