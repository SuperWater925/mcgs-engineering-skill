"""Locate the Stu online roles in an installed PE without loading the editor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "pro-native-bridge" / "abi-adapter"))
from pe32 import PE32, import_identity
from rtti import locate_type
from x86_signature import normalized_guard_bytes


class UnknownRole(ValueError):
    """The selected image did not prove the layout or role this action uses."""


def _anchor(value, relocated):
    ranges = []
    start = 0
    for end in (*relocated, len(value)):
        ranges.append((start, value[start:end]))
        start = end + 4
    return max(ranges, key=lambda row: len(row[1]))


def _candidates(image, value, relocated):
    offset, literal = _anchor(value, relocated)
    for address in image.find_bytes(literal, executable=True):
        start = address - offset
        if start >= 0 and image.is_executable(start):
            yield start


def _variable_operands(evidence):
    return sorted([*evidence["reloc_offsets"], *(offset + 1 for offset in evidence.get("relative_calls", []))])


def _verify(image, address, evidence):
    original = bytes.fromhex(evidence["bytes"])
    sites = evidence["reloc_offsets"]
    if not image.is_executable(address):
        return None
    try:
        actual, actual_sites = normalized_guard_bytes(image, address, len(original), image.image_base)
    except ValueError:
        return None
    if actual_sites != sites:
        return None
    source_masked = bytearray(original)
    actual_masked = bytearray(actual)
    positive_result = evidence.get("positive_result_offset")
    if positive_result is not None:
        if struct.unpack_from("<i", actual, positive_result)[0] <= 0:
            return None
        # The caller has already identified this exact mov-eax-immediate role.
        # A build can use another positive limit without changing the layout.
        source_masked[positive_result:positive_result + 4] = actual[positive_result:positive_result + 4]
    for delta, operand in zip(sites, evidence["highlow_roles"], strict=True):
        target = image.u32(address + delta) - image.image_base
        section = image.section_for_rva(target)
        if (section is None or section.executable != operand["executable"]
                or section.writable != operand["writable"]):
            return None
        if operand.get("import") is not None:
            imported = image.imports_by_iat.get(target)
            if imported is None or import_identity(imported) != operand["import"]:
                return None
        source_masked[delta:delta + 4] = actual_masked[delta:delta + 4] = bytes(4)
    for offset in evidence.get("relative_calls", []):
        if not (0 <= offset <= len(actual) - 5 and original[offset] == actual[offset] == 0xe8):
            return None
        if not image.is_executable(_follow_call(image, address + offset)):
            return None
        source_masked[offset + 1:offset + 5] = actual_masked[offset + 1:offset + 5] = bytes(4)
    if source_masked != actual_masked:
        return None
    return {"rva": address, "bytes": actual.hex(), "reloc_offsets": sites}


def _find_body(image, evidence):
    original = bytes.fromhex(evidence["bytes"])
    matches = []
    for address in _candidates(image, original, _variable_operands(evidence)):
        guard = _verify(image, address, evidence)
        if guard is not None:
            matches.append(guard)
            if len(matches) > 1:
                break
    if len(matches) != 1:
        raise UnknownRole("matching executable body is absent or ambiguous")
    return matches[0]


def _follow_jump(image, address):
    opcode = image.read(address, 1)
    if opcode == b"\xe9":
        return address + 5 + struct.unpack("<i", image.read(address + 1, 4))[0], 5
    if opcode == b"\xeb":
        return address + 2 + struct.unpack("<b", image.read(address + 1, 1))[0], 2
    return None


def _follow_call(image, address):
    if image.read(address, 1) != b"\xe8":
        raise UnknownRole("verified caller does not contain the declared direct call")
    return address + 5 + struct.unpack("<i", image.read(address + 1, 4))[0]


def _dispatch_case(image, witness, table_operand, limit_offset, index):
    if not 0 <= limit_offset < len(bytes.fromhex(witness["bytes"])):
        raise UnknownRole("declared native factory limit lies outside its witness")
    last_index = struct.unpack("<b", image.read(witness["rva"] + limit_offset, 1))[0]
    if table_operand not in witness["reloc_offsets"] or not 0 <= index <= last_index:
        raise UnknownRole("declared factory case is outside the verified switch")
    table = image.u32(witness["rva"] + table_operand) - image.image_base
    slot = table + index * 4
    if slot not in image.relocations:
        raise UnknownRole("declared factory case has no relocated native target")
    return image.u32(slot) - image.image_base


def _from_entry(image, entry, evidence):
    address = entry
    guards = []
    seen = set()
    while address not in seen and image.is_executable(address):
        seen.add(address)
        match = _verify(image, address, evidence)
        if match is not None:
            return {"rva": entry, "guards": [*guards, match]}
        jump = _follow_jump(image, address)
        if jump is None:
            break
        target, size = jump
        guards.append({"rva": address, "bytes": image.read(address, size).hex(), "reloc_offsets": []})
        address = target
    raise UnknownRole("native entry does not lead to the verified function body")


def _verified_layout(image, profile, domain):
    layout = dict(domain["layout"])
    data_roles = [
        (name, operands, writable)
        for key, writable in (("shared_writable_rva", True), ("shared_readonly_rva", False))
        for name, operands in domain.get(key, {}).items()
    ]
    for name, operands, writable in data_roles:
        values = set()
        for role, offset in operands:
            witness = profile["functions"][role]["guards"][-1]
            if offset not in witness["reloc_offsets"]:
                raise UnknownRole(f"{name} is not confirmed by the declared relocated instructions")
            values.add(image.u32(witness["rva"] + offset) - image.image_base)
        if len(values) != 1:
            raise UnknownRole(f"{name} instructions reference different native storage")
        rva = values.pop()
        section = image.section_for_rva(rva)
        if section is None or section.executable or section.writable != writable or not section.readable or rva % 4:
            raise UnknownRole(f"{name} does not match its aligned native data role")
        layout[name] = rva
    for caller, offset, target in domain.get("call_targets", []):
        origin = profile["functions"][caller]["guards"][-1]["rva"]
        if _follow_call(image, origin + offset) != profile["functions"][target]["rva"]:
            raise UnknownRole(f"{caller} no longer calls {target}")
    for table, slot, role in domain.get("slot_targets", []):
        if profile["tables"][table]["slots"].get(str(slot)) != profile["functions"][role]["rva"]:
            raise UnknownRole(f"{table} slot {slot} no longer points to {role}")
    for role, offset, table in domain.get("table_operands", []):
        witness = profile["functions"][role]["guards"][-1]
        if offset not in witness["reloc_offsets"] or (
                image.u32(witness["rva"] + offset) - image.image_base != profile["tables"][table]["rva"]):
            raise UnknownRole(f"{role} no longer references the original {table} table")
    return layout


def build_profile(image):
    reference = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    profile = {
        "schema": 1,
        "product": "stu",
        "preferred_image_base": image.image_base,
        "image": image.identity(),
        "capabilities": {},
        "tables": {},
        "functions": {},
        "imports": {},
        "layout": {},
    }
    errors = {}
    rtti = {}
    for name, table in reference["tables"].items():
        rtti_name, offset = table["rtti"], table["offset"]
        if rtti_name not in rtti:
            rtti[rtti_name] = locate_type(image, rtti_name)["tables"]
        bases = table.get("nonvirtual_bases", {})
        candidates = [row for row in rtti[rtti_name] if row["col_offset"] == offset
                      and row["constructor_displacement_offset"] == 0
                      and all(any(base["decorated_name"] == key and base["pmd"] == [base_offset, -1, 0]
                                  for base in row["hierarchy"]["bases"])
                              for key, base_offset in bases.items())]
        if len(candidates) != 1:
            errors[name] = "declared RTTI class/subobject is absent or ambiguous"
            continue
        current = candidates[0]
        profile["tables"][name] = {
            "rva": current["vtable_rva"],
            "rtti": rtti_name,
            "col_offset": offset,
            "col_rva": current["col_rva"],
            "slots": {slot: current["slot_entry_rvas"][int(slot)] for slot in table["slots"]
                      if int(slot) < len(current["slot_entry_rvas"])},
        }

    for name, identity in reference.get("imports", {}).items():
        imports = [rva for rva, imported in image.imports_by_iat.items()
                   if import_identity(imported) == identity]
        if len(imports) != 1:
            errors[name] = "declared native import is absent or ambiguous"
            continue
        profile["imports"][name] = {"rva": imports[0], **identity}

    for name, function in reference["functions"].items():
        try:
            slot = function.get("slot")
            caller = function.get("caller")
            case = function.get("dispatch_case")
            if slot:
                owner, index = slot
                if owner not in profile["tables"]:
                    raise UnknownRole("declared vtable prerequisite is unknown")
                entry = profile["tables"][owner]["slots"].get(str(index))
                if entry is None:
                    raise UnknownRole("declared native vtable slot is absent")
                resolved = _from_entry(image, entry, function)
            elif caller:
                owner, offset = caller
                parent = profile["functions"].get(owner)
                if parent is None:
                    raise UnknownRole("declared native caller is unknown")
                guard = parent["guards"][-1]
                if not 0 <= offset <= len(bytes.fromhex(guard["bytes"])) - 5:
                    raise UnknownRole("declared call lies outside the verified caller")
                entry = _follow_call(image, guard["rva"] + offset)
                resolved = _from_entry(image, entry, function)
            elif case:
                owner, table_operand, limit_offset, index = case
                parent = profile["functions"].get(owner)
                if parent is None:
                    raise UnknownRole("declared native factory is unknown")
                entry = _dispatch_case(image, parent["guards"][-1], table_operand, limit_offset, index)
                resolved = _from_entry(image, entry, function)
            else:
                guard = _find_body(image, function)
                resolved = {"rva": guard["rva"], "guards": [guard]}
            profile["functions"][name] = resolved
        except (ValueError, struct.error) as exc:
            errors[name] = str(exc)

    for name, domain in reference["capabilities"].items():
        failures = {
            item: errors.get(item, "declared role was not found")
            for role_group in ("tables", "functions", "imports")
            for item in domain.get(role_group, [])
            if item not in profile[role_group]
        }
        for dependency in domain.get("depends", []):
            if profile["capabilities"][dependency]["state"] != "verified":
                failures[dependency] = "required action layout is unknown"
        if not failures:
            try:
                verified_layout = _verified_layout(image, profile, domain)
            except (ValueError, struct.error) as exc:
                failures["layout"] = str(exc)
        if failures:
            profile["capabilities"][name] = {
                "state": "unknown",
                "reason": "Current image did not prove all required roles",
                "unresolved": failures,
            }
            continue
        profile["capabilities"][name] = {
            "state": "verified",
            "requires_runtime_identity": True,
            "tables": domain["tables"],
            "functions": domain["functions"],
        }
        if domain.get("imports"):
            profile["capabilities"][name]["imports"] = domain["imports"]
        profile["layout"].update(verified_layout)
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor", required=True, type=Path, help="Path to the actual McgsSetStu.exe")
    parser.add_argument("--out", type=Path, help="New JSON output path (default: stdout)")
    args = parser.parse_args()
    try:
        profile = build_profile(PE32(args.editor))
        report = json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            with args.out.open("x", encoding="utf-8", newline="\n") as output:
                output.write(report)
        else:
            print(report, end="")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
