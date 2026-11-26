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

from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG
from pe32 import PE32
from role_based_x86 import entry_chain
from rtti import locate_type
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


def common_window_compile_evidence(image, compile_start, field):
    """Match the original common-window branch and both native registrations."""
    call = re.compile(
        rb"\x8b\x55.\x52\x8b\x4d.\xe8(?P<callee>.{4})\x0f\xb6\xc0\x85\xc0\x75.", re.DOTALL)
    lookup = re.compile(
        rb"\x8b\x45(?P<doc>.)\x83\xb8(?P<field>.{4})\xff\x0f\x84.{4}"
        rb"\x6a\x00\xe8.{4}\x83\xc4\x04\x89\x45.\xe8.{4}\x89\x45(?P<service>.)"
        rb"\x8b\x4d(?P=doc)\x8b\x91(?P=field)\x52\x8d\x45.\x50"
        rb"\x8b\x4d(?P=service)\x8b\x11\x8b\x4d(?P=service)\x8b\x42\x28\xff\xd0", re.DOTALL)
    dependency = re.compile(
        rb"\x8b\x45.\x50\x8b\x4d(?P<map>.)\x8b\x11\x8b\x4d(?P=map)\x8b\x42\x04\xff\xd0", re.DOTALL)
    linked_owner_call = re.compile(
        rb"\x8b\x4d.\x51\x8b\x55\x08\x52\xe8(?P<callee>.{4})\x83\xc4\x08", re.DOTALL)
    graph_call = re.compile(rb"\x50\xe8(?P<callee>.{4})\x83\xc4\x0c", re.DOTALL)
    add_edge = bytes.fromhex("558bec8b4510508b4d0c518b55088b028b4d088b502cffd25dc3")

    def target(start, match):
        entry = start + match.end("callee") + struct.unpack("<i", match["callee"])[0]
        chain = entry_chain(image, entry)
        return chain[-1]["reference_rva"] if chain else entry

    matches = []
    for step in call.finditer(available(image, compile_start, 1024)):
        routine = target(compile_start, step)
        header = lookup.search(available(image, routine, 128))
        if header is None or header["field"] != field:
            continue
        owned_window = available(image, routine, 1024)
        if len(list(dependency.finditer(owned_window))) != 1:
            continue
        for related in linked_owner_call.finditer(owned_window):
            linked = target(routine, related)
            for registered in graph_call.finditer(available(image, linked, 640)):
                register = target(linked, registered)
                if available(image, register, len(add_edge)) == add_edge:
                    matches.append({"kind": "C0DocUser-public-window-compile-reference-registration",
                                    "primary_slot": 85, "actual_rva": compile_start + step.start(),
                                    "common_window_routine_rva": routine, "object_model_slot": 11})
    return matches[0] if len(matches) == 1 else None


def rotate_meter_compile_fields(image):
    """Identify the original CDrawRotateTbl expression cache pairs and image branch."""
    names = [f"control.rotate_meter.{role}_{i}" for i in range(6) for role in ("source", "program")]
    names.append("control.rotate_meter.conditional_image")
    unavailable = {key: {"status": "unresolved", "reason": "Original CDrawRotateTbl compiler layout differs"}
                   for key in names}

    def allocation_pair(ops):
        load, advance, push = ops
        if (load.mnemonic, advance.mnemonic, push.mnemonic) != ("mov", "add", "push"):
            return None
        a, b, c = load.operands, advance.operands, push.operands
        if not (len(a) == len(b) == 2 and len(c) == 1 and
                (a[0].type, a[1].type, b[0].type, b[1].type, c[0].type) ==
                (X86_OP_REG, X86_OP_MEM, X86_OP_REG, X86_OP_IMM, X86_OP_REG) and
                a[0].reg == b[0].reg == c[0].reg and load.reg_name(a[1].mem.base) == "ebp"):
            return None
        return (a[1].mem.disp, b[1].imm)

    try:
        tables = [row for row in locate_type(image, ".?AVCDrawRotateTbl@@")["tables"] if row["col_offset"] == 0]
        if len(tables) != 1 or len(tables[0]["slot_entry_rvas"]) <= 31:
            return unavailable
        entry = tables[0]["slot_entry_rvas"][31]
        chain = entry_chain(image, entry)
        start = chain[-1]["reference_rva"] if chain else entry
        ops = []
        for ins in decoder().disasm(available(image, start, 1024), start):
            ops.append(ins)
            if ins.mnemonic == "ret":
                break
        calls = []
        for i, ins in enumerate(ops[9:-1], 9):
            if ins.mnemonic != "call" or not ins.operands or ins.operands[0].type != X86_OP_IMM:
                continue
            if ops[i - 4].mnemonic != "push" or ops[i - 4].op_str != "3":
                continue
            if ops[i + 1].mnemonic != "add" or ops[i + 1].op_str != "esp, 0x10":
                continue
            cache = allocation_pair(ops[i - 9:i - 6])
            source = allocation_pair(ops[i - 3:i])
            if cache and source and cache[0] == source[0] and cache[1] == source[1] + 4:
                calls.append((i, source[1], cache[1], ins.operands[0].imm))
        if len(calls) != 6 or len({call[3] for call in calls}) != 1:
            return unavailable
        if len({off for _, a, b, _ in calls for off in (a, b)}) != 12:
            return unavailable

        # The successful last expression is followed by a separate optional
        # image registration. Its disabled state gives the narrower host shape.
        remaining = ops[calls[-1][0] + 1:]
        condition = None
        for i, (compare, branch) in enumerate(zip(remaining, remaining[1:])):
            if (compare.mnemonic != "cmp" or branch.mnemonic != "je" or
                    len(compare.operands) != 2 or compare.operands[0].type != X86_OP_MEM or
                    compare.operands[1].type != X86_OP_IMM or compare.operands[1].imm != 0 or
                    not branch.operands or branch.operands[0].type != X86_OP_IMM):
                continue
            fallthrough = [ins for ins in remaining[i+2:] if ins.address < branch.operands[0].imm]
            if len([ins for ins in fallthrough if ins.mnemonic == "call"]) == 1:
                condition = compare
                break
        if condition is None:
            return unavailable

        fields = {}
        for index, (i, src, dst, callee) in enumerate(calls):
            evidence = {"kind": "CDrawRotateTbl-expression-compiler-input-and-cache", "primary_slot": 31,
                        "actual_rva": ops[i].address, "compiler_entry_rva": callee}
            for role, offset in (("source", src), ("program", dst)):
                fields[f"control.rotate_meter.{role}_{index}"] = {
                    "status": "resolved", "offset": offset, "evidence": [evidence]}
        fields["control.rotate_meter.conditional_image"] = {
            "status": "resolved", "offset": condition.operands[0].mem.disp,
            "evidence": [{"kind": "CDrawRotateTbl-conditional-image-compile", "primary_slot": 31,
                          "actual_rva": condition.address}]}
        return fields
    except (ValueError, IndexError, KeyError, struct.error):
        return unavailable


def window_script_compile_evidence(image, compile_start, public_field):
    """Identify the three original page-script compiler input/cache pairs."""
    owner_call = re.compile(
        rb"\x8b\x4d.\x51\x8b\x4d.\xe8(?P<routine>.{4})\x0f\xb6\xd0\x85\xd2\x75.", re.DOTALL)
    inputs = [
        rb"\x8b\x45(?P<doc>.)\x05(?P<cache>.{4})\x50\x8b\x4d\x08\x51"
        rb"\x8b\x55(?P=doc)\x81\xc2(?P<source>.{4})\x52",
        rb"\x8b\x4d(?P<doc>.)\x81\xc1(?P<cache>.{4})\x51\x8b\x55\x08\x52"
        rb"\x8b\x45(?P=doc)\x05(?P<source>.{4})\x50",
        rb"\x8b\x55(?P<doc>.)\x81\xc2(?P<cache>.{4})\x52\x8b\x45\x08\x50"
        rb"\x8b\x4d(?P=doc)\x81\xc1(?P<source>.{4})\x51",
    ]
    compile_call = rb"\xe8(?P<routine>.{4})\x83\xc4\x0c\x0f\xb6"
    expected = [(0x150, 0x160), (0x154, 0x174), (0x15C, 0x188)]

    def target(start, call):
        entry = start + call.end("routine") + struct.unpack("<i", call["routine"])[0]
        chain = entry_chain(image, entry)
        return chain[-1]["reference_rva"] if chain else entry

    candidates = []
    for call in owner_call.finditer(available(image, compile_start, 1024)):
        routine = target(compile_start, call)
        raw = available(image, routine, 624)
        terminal = next((item for item in decoder().disasm(raw, routine) if item.mnemonic == "ret"), None)
        if terminal is None or terminal.op_str != "4":
            continue
        routine_bytes = raw[:terminal.address - routine + terminal.size]
        records = []
        for pattern, pair in zip(inputs, expected):
            matches = [node for node in re.finditer(pattern + compile_call, routine_bytes, re.DOTALL)
                       if (struct.unpack("<I", node["source"])[0], struct.unpack("<I", node["cache"])[0]) == pair]
            if len(matches) != 1:
                break
            record = matches[0]
            records.append({"source_offset": pair[0], "cache_offset": pair[1],
                            "source_cache_call_rva": routine + record.start(),
                            "actual_compiler_rva": target(routine, record)})
        if len(records) == len(expected) and len({row["actual_compiler_rva"] for row in records}) == 1:
            candidates.append({"kind": "C0DocUser-current-owner-script-compile", "primary_slot": 85,
                               "actual_rva": compile_start + call.start(), "pairs": records})
    if len(candidates) != 1:
        return None
    return {"status": "resolved", "offset": public_field, "evidence": candidates}


def common_window_field(image):
    """Cross-check the original public-window lookup and archive DWORD write."""
    lookup = re.compile(
        rb"\x8b\x45(?P<doc>.)\x83\xb8(?P<field>.{4})\xff\x0f\x84.{4}"
        rb"\xe8.{4}\x89\x45(?P<service>.)\x8b\x4d(?P=doc)\x8b\x91(?P=field)\x52"
        rb"\x8b\x45(?P=service)\x8b\x10\x8b\x4d(?P=service)\x8b\x42\x1c\xff\xd0", re.DOTALL)
    store = re.compile(
        rb"\x8b\x45.\x8b\x88(?P<field>.{4})\x51\x8b\x4d\x08\xe8(?P<write>.{4})"
        rb"\xc7\x45.\xff\xff\xff\xff", re.DOTALL)
    dword_writer = re.compile(
        rb"\x55\x8b\xec\x51\x89\x4d.\x6a\x04\x8d\x45\x08\x50\x8b\x4d.\xe8.{4}\x8b\xe5\x5d\xc2\x04\x00", re.DOTALL)
    selection_store = re.compile(
        rb"\x8d\x95.{4}\x52\x8b\x85(?P<service>.{4})\x8b\x10\x8b\x8d(?P=service)"
        rb"\x8b\x42\x24\xff\xd0\x8b\x8d.{4}\x89\x81(?P<field>.{4})", re.DOTALL)

    def body(entry):
        chain = entry_chain(image, entry)
        return chain[-1]["reference_rva"] if chain else entry

    try:
        tables = [row for row in locate_type(image, ".?AVC0DocUser@@")["tables"] if row["col_offset"] == 0]
        if len(tables) != 1 or len(tables[0]["slot_entry_rvas"]) <= 103:
            return None
        slots = tables[0]["slot_entry_rvas"]
        draw_start, archive_start = body(slots[101]), body(slots[103])
        uses = list(lookup.finditer(available(image, draw_start, 256)))
        if len(uses) != 1:
            return None
        use = uses[0]
        saves = []
        for hit in store.finditer(available(image, archive_start, 4096)):
            if hit["field"] != use["field"]:
                continue
            write_entry = archive_start + hit.end("write") + struct.unpack("<i", hit["write"])[0]
            if dword_writer.match(available(image, body(write_entry), 32)):
                saves.append(hit)
        offset = struct.unpack("<I", use["field"])[0]
        if len(saves) != 1 or offset == 0 or offset % 4:
            return None
        result = {"status": "resolved", "offset": offset, "evidence": [
            {"kind": "C0DocUser-public-window-ID-lookup", "primary_slot": 101, "actual_rva": draw_start + use.start()},
            {"kind": "C0DocUser-public-window-archive-DWORD", "primary_slot": 103,
             "actual_rva": archive_start + saves[0].start()},
        ]}
        try:
            selection_start = body(slots[102])
            writes = [row for row in selection_store.finditer(available(image, selection_start, 4096))
                      if row["field"] == use["field"]]
        except (ValueError, IndexError, KeyError, struct.error):
            return result
        if len(writes) == 1:
            result["write_evidence"] = {"kind": "C0DocUser-public-window-original-dialog-ID-store", "primary_slot": 102,
                                        "actual_rva": selection_start + writes[0].start()}
        try:
            original_compile = common_window_compile_evidence(image, body(slots[85]), use["field"])
        except (ValueError, IndexError, KeyError, struct.error):
            original_compile = None
        if original_compile is not None:
            result["compile_evidence"] = original_compile
            try:
                script_compile = window_script_compile_evidence(image, body(slots[85]), offset)
            except (ValueError, IndexError, KeyError, struct.error):
                script_compile = None
            if script_compile is not None:
                result["script_compile_evidence"] = script_compile
        return result
    except (ValueError, IndexError, KeyError, struct.error):
        return None


def method_return_cleanup(image, entry):
    """Read the current callee's consistent x86 RET cleanup across its control flow."""
    chain = entry_chain(image, entry)
    start = chain[-1]["reference_rva"] if chain else entry
    code = {ins.address: ins for ins in decoder().disasm(available(image, start, 4096), start)}
    pending, seen, returns = [start], set(), set()
    while pending:
        address = pending.pop()
        if address in seen:
            continue
        seen.add(address)
        ins = code.get(address)
        if ins is None:
            return None
        if ins.mnemonic == "ret":
            returns.add(ins.operands[0].imm if ins.operands else 0)
            continue
        if ins.mnemonic.startswith("j") or ins.mnemonic.startswith("loop"):
            if not ins.operands or ins.operands[0].type != X86_OP_IMM:
                return None
            pending.append(ins.operands[0].imm)
            if ins.mnemonic == "jmp":
                continue
        if ins.mnemonic in ("int3", "ud2"):
            return None
        pending.append(ins.address + ins.size)
    return returns.pop() if len(returns) == 1 else None


def group_receiver_uses(image, start, roles, virtual_entries=None):
    """Follow complete-this aliases through decoded control flow to list calls.

    Only values common to every incoming path survive a join. Registers, stack
    spills, mov/lea/add/sub and push/pop are modelled; an unknown write forgets
    the value. This accepts equivalent receiver setup without guessing a field.
    """
    instructions = {ins.address: ins for ins in decoder().disasm(available(image, start, 4096), start)}
    states = {start: ({"ecx": ("this", 0), "esp": ("stack", 0)}, {})}
    pending = [start]
    virtual_entries = virtual_entries or {}
    cleanups = {}
    parents = {alias: parent for parent, aliases in (
        ("eax", ("eax", "ax", "al", "ah")), ("ebx", ("ebx", "bx", "bl", "bh")),
        ("ecx", ("ecx", "cx", "cl", "ch")), ("edx", ("edx", "dx", "dl", "dh")),
        ("esi", ("esi", "si", "sil")), ("edi", ("edi", "di", "dil")),
        ("esp", ("esp", "sp", "spl")), ("ebp", ("ebp", "bp", "bpl"))) for alias in aliases}

    def parent(register):
        name = instruction.reg_name(register)
        return parents.get(name, name)

    def store_stack(stack, offset, size, value):
        # Stored symbols denote complete four-byte pointers, not individual bytes.
        for existing in list(stack):
            if existing < offset + size and offset < existing + 4:
                del stack[existing]
        if size == 4 and value is not None:
            stack[offset] = value

    def address(operand, registers):
        if operand.type != X86_OP_MEM or operand.mem.index:
            return None
        base = registers.get(instruction.reg_name(operand.mem.base))
        return (base[0], base[1] + operand.mem.disp) if base else None

    def read(operand, registers, stack):
        if operand.type == X86_OP_REG:
            return registers.get(instruction.reg_name(operand.reg)) if operand.size == 4 else None
        if operand.type == X86_OP_IMM:
            return ("absolute", operand.imm)
        location = address(operand, registers)
        if operand.size != 4 or location is None:
            return None
        if location[0] == "stack":
            return stack.get(location[1])
        # GetNext returns the CDraw* data slot in the already resolved drawing list.
        if location == ("drawlist_slot", 0):
            return ("control", 0)
        if location[0] in ("this", "control") and location[1] == 0:
            return ("vtable", 0)
        if location[0] == "vtable" and location[1] >= 0 and location[1] % 4 == 0:
            return ("virtual", location[1] // 4)
        return None

    def write(operand, value, registers, stack):
        if operand.type == X86_OP_REG:
            key = parent(operand.reg)
            if value is None or operand.size != 4:
                registers.pop(key, None)
            else:
                registers[key] = value
        elif operand.type == X86_OP_MEM:
            location = address(operand, registers)
            if location and location[0] == "stack":
                store_stack(stack, location[1], operand.size, value)
            elif location is None or location[0] not in ("this", "control"):
                # An unresolved destination may cover a previously spilled pointer.
                stack.clear()

    def role_index(operand, registers, stack):
        target = read(operand, registers, stack)
        if target and target[0] == "absolute":
            for index, entries in enumerate(roles):
                if target[1] in entries or target[1] - image.image_base in entries:
                    return index
        return None

    def successor(next_address, registers, stack):
        if next_address not in instructions:
            return
        previous = states.get(next_address)
        merged = (registers, stack) if previous is None else (
            {key: value for key, value in previous[0].items() if registers.get(key) == value},
            {key: value for key, value in previous[1].items() if stack.get(key) == value})
        if previous != merged:
            states[next_address] = merged
            pending.append(next_address)

    while pending:
        cursor = pending.pop()
        instruction = instructions[cursor]
        registers, stack = (dict(part) for part in states[cursor])
        operands, mnemonic = instruction.operands, instruction.mnemonic
        following = instruction.address + instruction.size
        if mnemonic.startswith("ret") or mnemonic in ("int3", "ud2"):
            continue
        if mnemonic.startswith("j") or mnemonic.startswith("loop"):
            if operands and operands[0].type == X86_OP_IMM:
                successor(operands[0].imm, registers, stack)
            if mnemonic != "jmp":
                successor(following, registers, stack)
            continue
        if mnemonic == "mov" and len(operands) == 2:
            write(operands[0], read(operands[1], registers, stack), registers, stack)
        elif mnemonic == "lea" and len(operands) == 2:
            write(operands[0], address(operands[1], registers), registers, stack)
        elif mnemonic in ("add", "sub") and len(operands) == 2 and operands[1].type == X86_OP_IMM:
            value = read(operands[0], registers, stack)
            if value:
                value = (value[0], value[1] + (1 if mnemonic == "add" else -1) * operands[1].imm)
            write(operands[0], value, registers, stack)
        elif mnemonic == "push" and operands:
            value = read(operands[0], registers, stack)
            sp = registers.get("esp")
            if sp and sp[0] == "stack":
                registers["esp"] = ("stack", sp[1] - operands[0].size)
                store_stack(stack, sp[1] - operands[0].size, operands[0].size, value)
            else:
                stack.clear()
        elif mnemonic == "pop" and operands:
            sp = registers.get("esp")
            value = stack.get(sp[1]) if sp and sp[0] == "stack" else None
            write(operands[0], value, registers, stack)
            if sp:
                registers["esp"] = (sp[0], sp[1] + operands[0].size)
        elif mnemonic == "call":
            role = role_index(operands[0], registers, stack) if operands else None
            target = read(operands[0], registers, stack) if operands else None
            callee = None
            if target and target[0] == "virtual":
                callee = virtual_entries.get(target[1])
            elif target and target[0] == "absolute":
                callee = target[1] if image.is_executable(target[1]) else target[1] - image.image_base
            if callee is not None and callee not in cleanups:
                cleanups[callee] = method_return_cleanup(image, callee) if image.is_executable(callee) else None
            cleanup = cleanups.get(callee)
            sp = registers.get("esp")
            for register in ("eax", "ecx", "edx"):
                registers.pop(register, None)
            if cleanup is None:
                registers.pop("esp", None)
            elif sp:
                registers["esp"] = (sp[0], sp[1] + cleanup)
            if role == 1:
                registers["eax"] = ("drawlist_slot", 0)
        else:
            for operand in operands:
                if operand.type == X86_OP_MEM and operand.access & 2:
                    write(operand, None, registers, stack)
            _, writes = instruction.regs_access()
            for register in writes:
                registers.pop(parent(register), None)
        successor(following, registers, stack)

    uses = defaultdict(set)
    for cursor, (registers, stack) in states.items():
        instruction = instructions[cursor]
        if instruction.mnemonic != "call" or not instruction.operands:
            continue
        target = read(instruction.operands[0], registers, stack)
        receiver = registers.get("ecx")
        if not target or target[0] != "absolute" or not receiver or receiver[0] != "this" or receiver[1] <= 0:
            continue
        candidates = (target[1], target[1] - image.image_base)
        for index, entries in enumerate(roles):
            if any(value in entries for value in candidates):
                uses[receiver[1]].add(index)
    return [offset for offset, calls in uses.items() if calls == set(range(len(roles)))]


def group_children_fields(image, resolution):
    """Resolve Cell/Unit separately from their actual primary methods and this flow."""
    mapping = resolution.get("rva_maps", {}).get("editor", {})

    def body(entry):
        chain = entry_chain(image, entry)
        return chain[-1]["reference_rva"] if chain else entry

    roles = []
    for reference in (0x47C80, 0x278B3):
        resolved = mapping.get(hex(reference))
        if not resolved:
            return {"group." + name + ".children": {"status": "unresolved",
                    "reason": "Current list iteration function role is unresolved"}
                    for name in ("CDrawCell", "CDrawUnit")}
        entry = resolved["actual_rva"]
        roles.append({entry, body(entry)})
    result = {}
    for name in ("CDrawCell", "CDrawUnit"):
        key = "group." + name + ".children"
        tables = [row for row in locate_type(image, ".?AV" + name + "@@")["tables"]
                  if row["col_offset"] == 0]
        witnesses, seen = [], set()
        if len(tables) == 1:
            for slot, entry in enumerate(tables[0]["slot_entry_rvas"]):
                start = body(entry)
                if start in seen:
                    continue
                seen.add(start)
                choices = group_receiver_uses(image, start, roles, dict(enumerate(tables[0]["slot_entry_rvas"])))
                if len(choices) == 1:
                    witnesses.append({"kind": "current-class-this-flow-list-receiver", "class": name,
                                      "primary_slot": slot, "actual_rva": start, "offset": choices[0],
                                      "list_iteration_roles": [sorted(role) for role in roles]})
        offsets = {row["offset"] for row in witnesses}
        if len(witnesses) >= 2 and len(offsets) == 1:
            result[key] = {"status": "resolved", "offset": offsets.pop(), "evidence": witnesses}
        else:
            result[key] = {"status": "unresolved", "reason": "Class-specific child-list receiver witnesses are missing or disagree"}
    return result


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
    public_window = common_window_field(image)
    fields["document.common_window_id"] = public_window or {
        "status": "unresolved", "reason": "C0DocUser public-window lookup and archive witnesses are missing or disagree"}
    fields["document.common_window_id_write"] = (
        {"status": "resolved", "offset": public_window["offset"],
         "evidence": public_window["evidence"] + [public_window["write_evidence"]]}
        if public_window and "write_evidence" in public_window else
        {"status": "unresolved", "reason": "The original public-window dialog store was not uniquely located"})
    fields["document.common_window_id_nonempty_compile"] = (
        {"status": "resolved", "offset": public_window["offset"],
         "evidence": public_window["evidence"] + [public_window["compile_evidence"]]}
        if public_window and "compile_evidence" in public_window else
        {"status": "unresolved", "reason": "The original populated host common-window compiler was not uniquely located"})
    fields["document.common_window_script_compile"] = (
        public_window["script_compile_evidence"]
        if public_window and "script_compile_evidence" in public_window else
        {"status": "unresolved", "reason": "The original page-script compiler inputs and cache locations differ"})
    fields.update(rotate_meter_compile_fields(image))
    fields.update(group_children_fields(image, resolution))
    return {"schema": 1, "pointer_size": 4, "editor_sha256": image.identity()["sha256"],
            "fields": fields, "unknown_fields_block_only_consumers": True,
            "all_native_layouts_adapted": False}
