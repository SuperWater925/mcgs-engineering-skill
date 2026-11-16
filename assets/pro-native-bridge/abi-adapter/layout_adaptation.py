"""Derive consumed object fields from the selected editor's instructions/RTTI.

Reference offsets identify operands in an evidenced accessor, not target memory
addresses. An unavailable witness stays feature-local; there is no fallback to
an author's displacement. No process is opened or native code invoked here.
"""
from __future__ import annotations

import copy
import re
import struct
from collections import defaultdict

from capstone.x86 import X86_OP_MEM
from pe32 import PE32
from role_based_x86 import entry_chain
from x86_signature import attach_import_role_context, available, candidates, decode_signature, decoder, verify_context


# (semantic field, evidenced accessor/snippet, reference operand, operand kind).
# These are identities in the shipped reference catalogue, never callable RVAs.
WITNESSES = (
    ("app.root_document", "RootCheckStateReset", 0x520, "mem"),
    ("app.main_frame", "RootBookkeeping", 0x524, "mem"),
    ("root.object_model", "DocManage_ObjectModel", 0x2D4, "mem"),
    ("page.document", "Page_GetLoadedDocument_OR_LAZY_LOAD", 0x14, "mem"),
    ("document.archive_id", "OriginalMainAuxCallbackSite", 0x258, "mem"),
    ("document.name", "DocAdd", 0x25C, "mem"),
    ("document.attributes", "OriginalDocGeometryStyleStores", 0x268, "mem"),
    ("document.controls", "DocAdd", 0x2BC, "imm"),
    ("document.modified", "RootIsModified", 0x48, "mem"),
    ("document.compile_valid", "RootCheckStateReset", 0x114, "mem"),
    ("document.history_generated", "OriginalHistoryGenerated13Store", 0x28C, "mem"),
    ("control.owner_document", "DocAdd", 0x64, "mem"),
    ("control.rectangle", "LabelSetRect", 0x80, "imm"),
    ("control.raw_state", 0xDF95C, 0x60, "mem"),
    ("control.type_id", "ConditionalOperationLogDeclarationTypePredicate", 0xC, "mem"),
    ("button.shared_condition", 0x371140, 0x394, "imm"),
)


def operand_value(operand):
    return operand[5] if operand[0] == "mem" else operand[1]


def field_operands(model, kind, expected):
    found = []
    for i, token in enumerate(model["tokens"]):
        for j, operand in enumerate(token["operands"]):
            if (operand[0] == kind and operand_value(operand) == expected
                    and (kind != "mem" or operand[2] not in (None, "ebp", "esp"))
                    and (kind != "imm" or token["mnemonic"] in ("add", "lea"))):
                found.append((i, j))
    return found


def masked_witness(model, positions):
    result = copy.deepcopy(model)
    mask = bytearray.fromhex(model["mask_hex"])
    instructions = list(decoder().disasm(bytes.fromhex(model["bytes_hex"]), model["reference_rva"]))
    for i, j in positions:
        instruction = instructions[i]
        kind = model["tokens"][i]["operands"][j][0]
        start = instruction.disp_offset if kind == "mem" else instruction.imm_offset
        size = instruction.disp_size if kind == "mem" else instruction.imm_size
        if not size:
            raise ValueError("Layout witness has no encoded field operand")
        offset = model["instruction_offsets"][i] + start
        mask[offset:offset + size] = bytes(size)
    result["mask_hex"] = mask.hex()
    return result


def match_fields(model, actual, positions):
    count = len(model["tokens"])
    if len(actual["tokens"]) < count:
        return None
    observed = copy.deepcopy(actual["tokens"][:count])
    values = {}
    for i, j in positions:
        old = model["tokens"][i]["operands"][j]
        new = observed[i]["operands"][j] if j < len(observed[i]["operands"]) else []
        if not new or new[0] != old[0]:
            return None
        value = operand_value(new)
        if type(value) is not int or value < 0:
            return None
        values[i, j] = value
        new[5 if new[0] == "mem" else 1] = operand_value(old)
    return values if observed == model["tokens"] else None


def resolve_model(model, positions, image, mapped):
    """Prefer already established function identity; otherwise a unique witness.

    Only declared field operands vary. Width, other operands, branches, imports
    and callee roles retain their original proof. Witness matches are not
    promoted into callable-function mappings.
    """
    def match(rva, tied_to_entry):
        try:
            available_span = len(available(image, rva, model["match_length"]))
            if not available_span:
                return None
            actual = decode_signature(image, rva, available_span)
            values = match_fields(model, actual, positions)
            if values is None:
                return None
            context = verify_context(None, image, model, actual, model["reference_rva"], rva,
                                     verify_targets=not tied_to_entry)
            if context is not None:
                return rva, values, tied_to_entry
        except (ValueError, IndexError, KeyError, struct.error):
            return None
        return None

    if mapped:
        nearest = []
        entry = mapped["actual_rva"]
        chain = entry_chain(image, entry)
        for rva in ([part["reference_rva"] for part in chain] if chain else [entry]):
            matched = match(rva, True)
            if matched is not None:
                nearest.append(matched)
        if nearest:
            return nearest[0] if len(nearest) == 1 else None
        starts = set()
        for rva in ([part["reference_rva"] for part in chain] if chain else [entry]):
            # Decode through a changed prologue at instruction boundaries.
            # A witness beginning outside this linear entry region must prove
            # its full context through the independent search below.
            span = len(available(image, rva, 15 * len(model["tokens"])))
            if span:
                try:
                    current = decode_signature(image, rva, span)
                except (ValueError, IndexError, KeyError, struct.error):
                    continue
                starts.update(rva + offset for offset in current["instruction_offsets"][1:])
        nearest = [found for start in sorted(starts) if (found := match(start, True)) is not None]
        if nearest:
            return nearest[0] if len(nearest) == 1 else None

    signature = masked_witness(model, positions)
    matches = [found for rva in candidates(image, signature) if (found := match(rva, False)) is not None]
    return matches[0] if len(matches) == 1 else None


def designer_client_fields(image):
    """Locate C0DocUser stores of the native child-window client rectangle."""
    stores = re.compile(
        rb"\x8d\x45(?P<rect>.)\x50\x8b\x4d.\xe8(?P<client>.{4})"
        rb"\x8d\x4d(?P=rect)\xe8(?P<width>.{4})\x8b\x4d(?P<doc>.)\x89\x81(?P<x>.{4})"
        rb"\x8d\x4d(?P=rect)\xe8(?P<height>.{4})\x8b\x55(?P=doc)\x89\x82(?P<y>.{4})", re.DOTALL)
    cast = re.compile(rb"\x6a\x00\x68(?P<to>.{4})\x68(?P<from>.{4}).{9,30}\xe8(?P<call>.{4})\x83\xc4\x14\x89\x45(?P<doc>.)", re.DOTALL)

    def rel32(match, field, origin):
        return origin + match.end(field) + struct.unpack("<i", match[field])[0]

    def body(entry):
        chain = entry_chain(image, entry)
        return chain[-1]["reference_rva"] if chain else entry

    def calls_import(entry, dll, symbol):
        current = body(entry)
        for ins in decoder().disasm(available(image, current, 48), current):
            if ins.mnemonic in ("ret", "int3"):
                break
            if ins.mnemonic not in ("call", "jmp") or not ins.operands:
                continue
            operand = ins.operands[0]
            if operand.type == X86_OP_MEM and not operand.mem.base and not operand.mem.index:
                row = image.imports_by_iat.get((operand.mem.disp & 0xffffffff) - image.image_base)
                if row and (dll is None or row["dll"].casefold() == dll) and row.get("name") == symbol:
                    return True
        return False

    matches = []
    for section, data in image.iter_regions(executable=True):
        for row in stores.finditer(data):
            start = max(0, row.start() - 128)
            ownership = data[start:row.start()]
            for conversion in cast.finditer(ownership):
                if conversion["doc"] != row["doc"]:
                    continue
                try:
                    type_rva = image.va_to_rva(struct.unpack("<I", conversion["to"])[0])
                    if image.cstring(type_rva + 8) != ".?AVC0DocUser@@":
                        continue
                    if not calls_import(rel32(conversion, "call", section.rva + start), None, "__RTDynamicCast"):
                        continue
                    if not calls_import(rel32(row, "client", section.rva), "user32.dll", "GetClientRect"):
                        continue
                    width, height = (body(rel32(row, field, section.rva)) for field in ("width", "height"))
                    if not (image.read(width, 22).endswith(bytes.fromhex("8b40082b018be55dc3"))
                            and image.read(height, 23).endswith(bytes.fromhex("8b400c2b41048be55dc3"))):
                        continue
                except (ValueError, IndexError, struct.error):
                    continue
                x, y = (struct.unpack("<I", row[field])[0] for field in ("x", "y"))
                if y == x + 4:
                    matches.append((x, y, section.rva + row.start()))
                break
    return matches[0] if len(matches) == 1 else None


def derive_layout(catalog, resolution, module_files):
    image = PE32(module_files["editor"])
    models = [s for s in catalog["signatures"] if s["module"] == "editor"]
    groups = defaultdict(list)
    fields = {}
    for key, selector, old, kind in WITNESSES:
        choices = [s for s in models if selector in s.get("names", [])
                   or type(selector) is int and s["reference_rva"] == selector]
        choices = [s for s in choices if field_operands(s, kind, old)]
        if not choices:
            fields[key] = {"status": "unresolved", "reason": "No declared accessor operand"}
            continue
        model = max(choices, key=lambda s: len(s["tokens"]))
        groups[model["id"]].append((key, model, old, kind))
    dependencies = set()
    targets = {}
    for rows in groups.values():
        for relocation in rows[0][1]["relocations"]:
            role = (relocation.get("import") or {}).get("export_role")
            if role is None:
                continue
            module, old = role["module"], role["reference_rva"]
            if module in module_files:
                dependencies.add(module)
            mapping = resolution["rva_maps"].get(module, {}).get(hex(old))
            if mapping:
                targets[module, old] = {mapping["actual_rva"]}
    images = {module: PE32(module_files[module]) for module in sorted(dependencies - {"editor"})}
    attach_import_role_context({"editor": image, **images}, targets)
    for rows in groups.values():
        model = rows[0][1]
        positions = set()
        for key, _, old, kind in rows:
            positions.update(field_operands(model, kind, old))
        mapped = resolution["rva_maps"].get("editor", {}).get(hex(model["reference_rva"]))
        matched = resolve_model(model, positions, image, mapped)
        for key, _, old, kind in rows:
            values = {matched[1][p] for p in field_operands(model, kind, old)} if matched else set()
            if len(values) != 1:
                fields[key] = {"status": "unresolved", "reason": "Accessor witness missing or ambiguous", "witness": model["id"]}
                continue
            value = values.pop()
            fields[key] = {"status": "resolved", "offset": value, "reference_offset": old,
                           "evidence": [{"kind": "current-instruction-operand", "witness": model["id"],
                                         "actual_rva": matched[0], "operand_kind": kind,
                                         "existing_function_identity": matched[2]}]}

    # Existing attributes represent 17 individually modelled archive fields;
    # this is their extent, not a limit on additional fields in a newer editor.
    fields["document.attributes_count"] = {"status": "resolved", "offset": 17,
        "evidence": [{"kind": "modelled-archive-field-extent", "additional_fields": "preserved-unmodified"}]}
    client_fields = designer_client_fields(image)
    for index, axis in enumerate(("width", "height")):
        key = "document.designer_client_" + axis
        fields[key] = ({"status": "resolved", "offset": client_fields[index],
                        "evidence": [{"kind": "C0DocUser-GetClientRect-result-store", "actual_rva": client_fields[2],
                                      "coordinate": axis}]}
                       if client_fields else {"status": "unresolved", "reason": "No unique C0DocUser client-extent store witness"})
    return {"schema": 1, "pointer_size": 4, "editor_sha256": image.identity()["sha256"],
            "fields": fields, "unknown_fields_block_only_consumers": True,
            "all_native_layouts_adapted": False}
