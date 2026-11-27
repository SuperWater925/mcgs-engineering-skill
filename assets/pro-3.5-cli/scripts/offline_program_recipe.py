"""Typed recipe and strategy edits on an exported candidate database."""
from copy import deepcopy
import struct

import native_format as fmt
import mcgs_recipe_strategy as archive
from mcgs_family import identify_family


def one(rows, field, value):
    matches = [r for r in rows if r[field] == value]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {field}={value!r}, found {len(matches)}")
    return matches[0]


def text(value, empty=False):
    if not isinstance(value, str) or "\0" in value or (not empty and not value.strip()):
        raise ValueError("Expected text without NUL")
    return value


def keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required) - set(obj):
        raise ValueError(f"Expected fields {required}, allowed fields {allowed}")


def position(value, size, insertion=False):
    if type(value) is not int or not 0 <= value < size + int(insertion):
        raise ValueError("Index outside current list")
    return value


def recipe_state(data):
    rows = data["System"]["rows"]
    index = one(rows, "strName", "MCGS_RECIPE_DATA")
    raw = fmt.archive(index["lbContext"])
    names = archive.parse_recipe_index(raw)
    if archive.serialize_recipe_index(names) != raw or len({n.casefold() for n in names}) != len(names):
        raise ValueError("Recipe index fails byte roundtrip or contains duplicate names")
    groups = {}
    for name in names:
        row = one(rows, "strName", "MCGS_RECIPE_" + name)
        raw = fmt.archive(row["lbContext"])
        group = archive.RecipeGroup.parse(raw)
        if group.name != name or group.serialize() != raw:
            raise ValueError("Registered recipe identity or archive differs")
        groups[name] = (row, group)
    return rows, index, names, groups


def recipe_consumers(data, name):
    from mcs_plugin_controls import PluginControl, RecipeCore, utf8_write
    from mcs_window_archive import ControlRecord, write_count
    from 原生界面样式 import CommonEnvelope, GroupArchive

    # RecipeCore serializes the full group as a length-prefixed UTF-8 field.
    # When absent, no known native recipe consumer on that page can refer to it.
    encoded = utf8_write(name)
    def visit(control, page):
        if encoded not in control.payload:
            return
        if control.type_id == 0x503a:
            for child in GroupArchive.parse(control).children:
                yield from visit(child, page)
        elif control.type_id == 0x503d:
            plugin = PluginControl.parse(CommonEnvelope.parse(control).project_without_animations())
            if "recipe" in plugin.path.casefold():
                core = RecipeCore.parse(plugin.core)
                if core.group == name:
                    yield page, core

    for row in data["WndUser"]["rows"]:
        plain = fmt.archive(row["lbObjects"])
        if encoded not in plain:
            continue
        _, records, _ = fmt.window(plain, validate_settings=False)
        for kind, blob in records:
            yield from visit(ControlRecord(kind, blob, write_count(len(blob)), 0), row["strName"])


def verified_recipe_control(control, definition):
    from mcs_plugin_controls import PluginControl, RecipeCore
    from mcs_recipe_association import require_recipe_association
    from 原生界面样式 import CommonEnvelope

    if control.type_id != 0x503d:
        raise ValueError("Recipe group reference in an unsupported page control")
    common = CommonEnvelope.parse(control)
    plugin = PluginControl.parse(common.project_without_animations())
    if plugin.path.split("#", 1)[0].replace("/", "\\").rsplit("\\", 1)[-1].casefold() != "drawrecipe.ui":
        raise ValueError("Recipe group reference in an unsupported external control")
    core = RecipeCore.parse(plugin.core)
    require_recipe_association(core, definition)
    if (core.to_bytes() != plugin.core
            or common.restore_projected(plugin.to_record()).to_bytes() != control.to_bytes()):
        raise ValueError("Recipe control fails byte roundtrip")
    return common, plugin, core


def recipe_windows(data, encoded, source_literals=()):
    from mcs_window_archive import WindowArchive

    probes = (encoded, *source_literals)
    for row in data["WndUser"]["rows"]:
        raw = fmt.archive(row["lbObjects"])
        if not any(token in raw for token in probes):
            continue
        window = WindowArchive.parse(raw)
        if window.to_bytes() != raw or any(token in window.trailer or token in window.prefix for token in probes):
            raise ValueError("Unsupported window layout for recipe migration")
        yield row, window


def rewrite_recipe_tree(control, encoded, visit, source_literals=()):
    from 原生界面样式 import GroupArchive

    probes = (encoded, *source_literals)
    if not any(token in control.payload for token in probes):
        return control
    if control.type_id != 0x503a:
        return visit(control)
    group = GroupArchive.parse(control)
    if group.to_record().to_bytes() != control.to_bytes():
        raise ValueError("Recipe consumer parent group fails byte roundtrip")
    if source_literals:
        common = group.common
        envelope = (common.prefix, common.name.to_bytes(), common.metadata.value, group.tail)
        if any(token in part for token in probes for part in envelope):
            raise ValueError('An unsupported group envelope also references the recipe')
    group.children[:] = [rewrite_recipe_tree(child, encoded, visit, source_literals) for child in group.children]
    return group.to_record()


def prepare_recipe_consumer_rename(data, original, renamed):
    from mcs_plugin_controls import RecipeCore, utf8_write
    from mcs_recipe_association import require_recipe_association
    from mcs_window_archive import WindowArchive

    encoded = utf8_write(original.name)
    edits = []
    consumers = 0
    for row, window in recipe_windows(data, encoded):
        def rename(control, mask):
            nonlocal consumers
            # The residual scan independently examines unsupported controls
            # and all fields except a verified group binding.
            if control.type_id != 0x503d:
                return control
            common, plugin, core = verified_recipe_control(control, original)
            core.group = "" if mask else renamed.name
            plugin.core = core.to_bytes()
            if not mask:
                require_recipe_association(RecipeCore.parse(plugin.core), renamed)
                consumers += 1
            return common.restore_projected(plugin.to_record())

        original_controls = window.controls[:]
        window.controls[:] = [rewrite_recipe_tree(c, encoded, lambda q: rename(q, True)) for c in original_controls]
        masked = window.to_bytes()
        window.controls[:] = [rewrite_recipe_tree(c, encoded, lambda q: rename(q, False)) for c in original_controls]
        updated = window.to_bytes()
        if WindowArchive.parse(updated).to_bytes() != updated:
            raise ValueError("Updated recipe window fails byte roundtrip")
        if masked != fmt.archive(row["lbObjects"]):
            edits.append((row, masked, updated))
    if not consumers:
        raise ValueError("Recipe rename synchronization requires a verified DrawRecipe.ui consumer")
    return edits


def recipe_refresh_targets(data, row, window, definition, encoded):
    page_name = row['strName']
    if sum(candidate['strName'].casefold() == page_name.casefold() for candidate in data['WndUser']['rows']) != 1:
        return set()
    try:
        names = [fmt.common(control.payload)['name'].casefold() for control in window.controls]
    except (ValueError, UnicodeError, struct.error):
        return set()
    targets = set()
    for control in window.controls:
        if control.type_id == 0x503d and encoded in control.payload:
            common, _, _ = verified_recipe_control(control, definition)
            if names.count(common.name.value.casefold()) == 1:
                targets.add(f'{page_name}.{common.name.value}.Refresh')
    return targets


def rewrite_recipe_controls(data, original, changed, edit_columns, *, order_only=False):
    from mcs_plugin_controls import RecipeCore, utf8_write
    from mcs_recipe_association import require_recipe_association
    from mcs_window_archive import WindowArchive

    encoded = utf8_write(original.name)
    if order_only:
        version = fmt.archive(one(data['System']['rows'], 'strName', 'MCGSVER')['lbContext'])
        order_only = identify_family(version.decode('utf-16le').rstrip('\0')) == 'Pro'
    source_literals = ()
    if order_only:
        from mcgs_text import narrow_encoding
        literal = f'"{original.name}"'
        source_literals = (literal.encode('utf-16le'), literal.encode('utf-8'))
        encoding = narrow_encoding()
        narrow = literal.encode(encoding, errors='replace')
        if narrow.decode(encoding) == literal and narrow not in source_literals:
            source_literals += (narrow,)
    variables = None

    def rewrite(control):
        nonlocal variables
        if order_only and control.type_id == 0x5027:
            from offline_recipe_references import require_recipe_reorder_safe_button
            if variables is None:
                objects = one(data['System']['rows'], 'strName', 'ObjData')['lbContext']
                variables = {record['name']: record for record in fmt.variables(fmt.archive(objects))}
            require_recipe_reorder_safe_button(control, original.name, refresh_targets, variables)
            return control
        common, plugin, core = verified_recipe_control(control, original)
        edit_columns(core.columns)
        plugin.core = core.to_bytes()
        require_recipe_association(RecipeCore.parse(plugin.core), changed)
        return common.restore_projected(plugin.to_record())

    for row, window in recipe_windows(data, encoded, source_literals):
        refresh_targets = recipe_refresh_targets(data, row, window, original, encoded) if order_only else set()
        window.controls[:] = [rewrite_recipe_tree(control, encoded, rewrite, source_literals) for control in window.controls]
        result = window.to_bytes()
        if WindowArchive.parse(result).to_bytes() != result:
            raise ValueError("Updated recipe window fails byte roundtrip")
        if result != fmt.archive(row["lbObjects"]):
            row["lbObjects"] = fmt.wrap_like(row["lbObjects"], result)


def sync_recipe_columns(data, original, changed, index, operation, template_index=None):
    def update(columns):
        # Zero is the control-only serial column; group field zero follows it.
        slot = index + 1
        if operation == "delete_column":
            del columns[slot]
        else:
            target = changed.fields[index]
            template = deepcopy(columns[template_index + 1]) if template_index is not None else None
            if operation == "insert_column":
                columns.insert(slot, template)
            elif template is not None:
                columns[slot] = template
            if target.data_type != columns[slot].values[0]:
                raise ValueError("Changing a bound recipe column type requires native display settings")
            columns[slot].binding = target.binding
            columns[slot].title = target.title

    rewrite_recipe_controls(data, original, changed, update)


def reorder_recipe_columns(data, group, order, sync):
    n = len(group.fields)
    if (not isinstance(order, list) or len(order) != n - 1 or any(type(i) is not int for i in order)
            or sorted(order) != list(range(1, n))):
        raise ValueError("Recipe column order must be a permutation of all nonreserved field indices")
    if order == list(range(1, n)):
        return
    original = deepcopy(group) if sync else None
    permutation = [0, *order]
    group.fields = [group.fields[i] for i in permutation]
    group.records = [[row[i] for i in permutation] for row in group.records]
    if sync:
        def update(columns):
            columns[2:] = [columns[i + 1] for i in order]

        rewrite_recipe_controls(data, original, group, update, order_only=True)


def recipe_edits(data, edits):
    rows, index, names, groups = recipe_state(data)
    variables = None
    language_texts = None

    def require_column_title(title):
        nonlocal language_texts
        if not title.startswith('\x07'):
            return
        text_id = fmt.language_text_id(title)
        if text_id is None:
            raise ValueError('Recipe column title has an invalid native language text ID')
        if language_texts is None:
            language_texts = fmt.language_texts(data)
        if text_id not in language_texts:
            raise ValueError(f'Recipe column title text ID {text_id} is missing from the current project')

    def column(spec, current_title=None):
        nonlocal variables
        keys(spec, ("binding", "title", "type"), ("binding", "title", "type"))
        binding, title, kind = text(spec["binding"]), text(spec["title"]), spec["type"]
        if type(kind) is not int or kind not in (1, 2, 3):
            raise ValueError("Recipe field type must be 1, 2 or 3")
        if variables is None:
            variables = fmt.variables(fmt.archive(one(rows, "strName", "ObjData")["lbContext"]))
        if one(variables, "name", binding)["kind"] != kind:
            raise ValueError("Recipe binding type differs from target variable")
        if title != current_title:
            require_column_title(title)
        return archive.RecipeField(binding, title, kind)

    def record(values, width):
        if not isinstance(values, list) or len(values) != width:
            raise ValueError("Recipe record width differs from column count")
        return [text(v, empty=True) for v in values]

    for edit in edits:
        op, name = edit["op"], text(edit["name"])
        if op == "add_group":
            keys(edit, ("op", "name", "columns", "records", "template"))
            key = "MCGS_RECIPE_" + name
            if any(r["strName"].casefold() == key.casefold() for r in rows):
                raise ValueError("Recipe group name collision")
            if "template" in edit or groups:
                template = groups[edit.get("template", next(iter(groups), None))][1]
                if not template.fields or template.fields[0].binding or template.fields[0].data_type != 3:
                    raise ValueError("Unexpected template name column")
                first = deepcopy(template.fields[0])
                marker, tail = template.format_marker, template.log_tail
            else:
                version = fmt.archive(one(rows, "strName", "MCGSVER")["lbContext"]).decode("utf-16le").rstrip("\0")
                family = identify_family(version)
                # Measured native first-group defaults for both product families.
                layouts = {"Pro": (1134562542, ()), "Stu": (1134564147, (0, 2, 0))}
                if family not in layouts:
                    raise ValueError("Cannot determine first recipe group layout")
                first = archive.RecipeField("", "配方名称", 3)
                marker, tail = layouts[family]
            require_column_title(first.title)
            fields = [first] + [column(c) for c in edit.get("columns", [])]
            items = [record(r, len(fields)) for r in edit.get("records", [])]
            group = archive.RecipeGroup(marker, name, fields, items, tail)
            if set(index) != {"iID", "strName", "lbContext"}:
                raise ValueError("Unknown System row layout for new group")
            row = {"iID": max(r["iID"] for r in rows) + 1, "strName": key,
                   "lbContext": (groups[edit.get("template", next(iter(groups)))][0] if groups else index)["lbContext"]}
            from mcs_recipe_association import require_recipe_association
            for page, core in recipe_consumers(data, name):
                require_recipe_association(core, group)
            groups[name] = (row, group)
            rows.append(row)
            names.append(name)
        else:
            if name not in groups:
                raise ValueError("Unknown registered recipe group")
            row, group = groups[name]
            structural = op in ("delete_group", "insert_column", "delete_column", "reorder_columns")
            updated_column = None
            if op == "update_column":
                i = position(edit["index"], len(group.fields))
                updated_column = column(edit["column"], group.fields[i].title)
                structural = updated_column != group.fields[i]
            sync = edit.get("sync_controls", False)
            if type(sync) is not bool:
                raise ValueError("sync_controls must be boolean")
            if structural and not sync:
                consumer = next(recipe_consumers(data, name), None)
                if consumer is not None:
                    raise ValueError(f"Recipe group {name!r} is used on page {consumer[0]!r}; column schema must match")
            if op == "rename_group":
                keys(edit, ("op", "name", "new_name", "sync_controls"), ("new_name",))
                new = text(edit["new_name"])
                key = "MCGS_RECIPE_" + new
                if new == name or any(other is not row and other["strName"].casefold() == key.casefold()
                                      for other in rows):
                    raise ValueError("Recipe group name unchanged or occupied")
                slot = names.index(name)
                page_edits = []
                declaration_projections = {}
                if sync:
                    from offline_recipe_references import variable_name_projections
                    after_name = deepcopy(group)
                    after_name.name = new
                    page_edits = prepare_recipe_consumer_rename(data, group, after_name)
                    declaration_projections = variable_name_projections(rows, (name, new))
                guard_group = archive.RecipeGroup(group.format_marker, "", group.fields,
                                                  [] if sync else group.records, group.log_tail)
                names[slot] = ""
                require_unused_names(data, (name, new), {
                    (id(row), "strName"): "",
                    (id(row), "lbContext"): guard_group.serialize(),
                    (id(index), "lbContext"): archive.serialize_recipe_index(names),
                    **declaration_projections,
                    **{(id(owner), "lbObjects"): masked for owner, masked, _ in page_edits}})
                group.name = names[slot] = new
                row["strName"] = key
                groups[new] = groups.pop(name)
                for owner, _, updated in page_edits:
                    owner["lbObjects"] = fmt.wrap_like(owner["lbObjects"], updated)
            elif op == "delete_group":
                keys(edit, ("op", "name"))
                rows.remove(row)
                names.remove(name)
                del groups[name]
                require_unused_names(data, (name,), {
                    (id(index), "lbContext"): archive.serialize_recipe_index(names)})
                continue
            elif op in ("insert_record", "update_record", "delete_record"):
                keys(edit, ("op", "name", "index") if op == "delete_record" else ("op", "name", "index", "values"))
                i = position(edit["index"], len(group.records), op == "insert_record")
                if op == "delete_record":
                    del group.records[i]
                elif op == "insert_record":
                    group.records.insert(i, record(edit["values"], len(group.fields)))
                else:
                    group.records[i] = record(edit["values"], len(group.fields))
            elif op == "reorder_columns":
                keys(edit, ("op", "name", "order", "sync_controls"), ("order",))
                reorder_recipe_columns(data, group, edit["order"], sync)
            elif op in ("insert_column", "update_column", "delete_column"):
                allowed = {"op", "name", "index"}
                allowed.add("sync_controls")
                if sync and op != "delete_column":
                    allowed.add("display_template_index")
                if op != "delete_column":
                    allowed.update(("column", "values"))
                keys(edit, allowed)
                i = position(edit["index"], len(group.fields), op == "insert_column")
                if i == 0:
                    raise ValueError("The native name column is required")
                field = updated_column if op == "update_column" else column(edit["column"]) if op == "insert_column" else None
                if sync:
                    original = deepcopy(group)
                    template_index = None
                    changing_type = op == "update_column" and field.data_type != group.fields[i].data_type
                    if op == "insert_column" or changing_type:
                        if changing_type and "display_template_index" not in edit:
                            raise ValueError("Changing a bound recipe column type requires native display settings")
                        template_index = position(edit.get("display_template_index"), len(group.fields))
                        if template_index == 0:
                            raise ValueError("A recipe display column requires a nonreserved template")
                        if group.fields[template_index].data_type != field.data_type:
                            raise ValueError("Recipe display template type differs from the new field type")
                    elif "display_template_index" in edit:
                        raise ValueError("A display template is only used for insertion or column type changes")
                if op == "delete_column":
                    del group.fields[i]
                    for r in group.records:
                        del r[i]
                else:
                    if op == "insert_column" or "values" in edit:
                        values = record(edit.get("values", []), len(group.records))
                        for r, v in zip(group.records, values):
                            if op == "insert_column":
                                r.insert(i, v)
                            else:
                                r[i] = v
                    if op == "insert_column":
                        group.fields.insert(i, field)
                    else:
                        if group.records and field.data_type != group.fields[i].data_type and "values" not in edit:
                            raise ValueError("Changing column type requires replacement values")
                        group.fields[i] = field
                if sync:
                    sync_recipe_columns(data, original, group, i, op, template_index)
            else:
                raise ValueError(f"Unknown recipe edit {op}")
        row["lbContext"] = fmt.wrap_like(row["lbContext"], group.serialize())
    index["lbContext"] = fmt.wrap_like(index["lbContext"], archive.serialize_recipe_index(names))
    recipe_state(data)


DEFAULT_TRIGGER_ID = 0x4A4D4120


def trigger_rows_for(rows, trigger):
    fields = trigger.fields
    matching_role = [row for row in rows if row["lStgyID"] == fields["strategy_id"]
                     and row["lType"] == fields["trigger_type"]]
    # Original default triggers can share a marker instead of the database ID.
    exact = [row for row in matching_role
             if row["iID"] == fields["trigger_id"] or fields["trigger_id"] == DEFAULT_TRIGGER_ID]
    if not exact and trigger.class_name == "CTriggerEvent" and fields["trigger_type"] == 4:
        # The database cursor key can differ from the ID inside both native
        # Event payloads. strategy_state verifies that fallback role exactly.
        return matching_role
    return exact


def read_trigger_row(row, trigger):
    payload = fmt.archive(row["lbContext"])
    reader = archive.Reader(payload)
    result = archive.Node(trigger.class_name, archive.read_node_fields(reader, trigger.class_name), trigger.schema)
    reader.finish()
    if archive.serialize_trigger_payload(result) != payload:
        raise ValueError("Trigger row fails byte roundtrip")
    return result


EVENT_DIRECT_SWITCH_PREFIX = bytes.fromhex("030000000000000001000000030000000000000025")
EVENT_DIRECT_SWITCH_SUFFIX = bytes.fromhex("472c0000000001")
# Native order, including the two compound transitions rejected by the original compilers.
EVENT_CONDITION_NAMES = ("rising", "falling", "rising_then_falling", "falling_then_rising", "change")
EDITABLE_EVENT_EDGES = {"rising": 0, "falling": 1, "change": 4}
EVENT_TRIGGER_NOTE = "当确定的条件满足时运行"


def event_variable(data, name):
    obj = one(data["System"]["rows"], "strName", "ObjData")
    return one(fmt.variables(fmt.archive(obj["lbContext"])), "name", name)


def matching_event_cache_variants(data, fields, mirror):
    # Pro Event mirrors can hold independently compiled direct-switch
    # programs. A root save can also store that program while the verified
    # DAO copy remains empty. Preserve each original cache.
    if fields["trigger_type"] != 4 or {key for key in fields if fields[key] != mirror[key]} != {"event_cache"}:
        return False
    name = fields["event_expression"]
    if not name.isidentifier():
        return False
    caches = (fields["event_cache"], mirror["event_cache"])
    compiled = [cache for cache in caches if cache]
    start = len(EVENT_DIRECT_SWITCH_PREFIX)
    if any(len(cache) != start + 4 + len(EVENT_DIRECT_SWITCH_SUFFIX)
           or not cache.startswith(EVENT_DIRECT_SWITCH_PREFIX) or not cache.endswith(EVENT_DIRECT_SWITCH_SUFFIX)
           for cache in compiled):
        return False
    ids = [fmt.u32(cache, start) for cache in compiled]
    if any(ident > 0x7fffffff for ident in ids):
        return False
    current = event_variable(data, name)
    return current["kind"] == 1 and current["id"] in ids


def strategy_state(data):
    row = one(data["Stgy"]["rows"], "iStgyID", 0)
    registry_row = one(data["System"]["rows"], "strName", "StgyAndTrigger")
    plain = fmt.archive(row["lbObjects"])
    registry_plain = fmt.archive(registry_row["lbContext"])
    registry = archive.StrategyAndTrigger.parse(registry_plain)
    if registry.serialize() != registry_plain or archive.serialize_strategy_array(registry.strategies) != plain:
        raise ValueError("Strategy archive copies differ")
    ids = [s.fields["tail_words"][2] for s in registry.strategies]
    rows = data["Trigger"]["rows"]
    unmatched = {r["iID"]: r for r in rows}
    if len(set(ids)) != len(ids) or len(unmatched) != len(rows):
        raise ValueError("Duplicate database identities")
    native_id_counts = {}
    for trigger in registry.triggers:
        ident = trigger.fields["trigger_id"]
        native_id_counts[ident] = native_id_counts.get(ident, 0) + 1
    for t in registry.triggers:
        fields = t.fields
        candidates = trigger_rows_for(unmatched.values(), t)
        if fields["strategy_id"] not in ids or len(candidates) != 1:
            raise ValueError("Trigger linkage differs or is ambiguous")
        dbrow = candidates[0]
        table_copy = read_trigger_row(dbrow, t)
        if t.class_name == "CTriggerEvent" and dbrow["iID"] != fields["trigger_id"]:
            ident = fields["trigger_id"]
            if (fields["trigger_type"] != 4 or not 0 < ident <= 0x7fffffff or ident == DEFAULT_TRIGGER_ID
                    or not 0 < dbrow["iID"] <= 0x7fffffff or native_id_counts[ident] != 1
                    or sum(r["lStgyID"] == fields["strategy_id"] and r["lType"] == 4 for r in rows) != 1
                    or dbrow["strNote"] != fields["note"] or table_copy.fields != fields):
                raise ValueError("Independently keyed Event trigger requires exact unique identities and matching payloads")
        if t.class_name == "CTriggerLoop":
            # Native saved fixtures differ by one high-word count at this single
            # field. Leave each physical copy intact, require all other fields.
            old = table_copy.fields["loop_tail"][0]
            if fields["loop_tail"][0] == old + 0x10000:
                table_copy.fields["loop_tail"][0] = fields["loop_tail"][0]
        if fields != table_copy.fields and not (
            t.class_name == "CTriggerEvent" and matching_event_cache_variants(data, fields, table_copy.fields)
        ):
            raise ValueError("Trigger duplicate payload differs")
        del unmatched[dbrow["iID"]]
    if unmatched:
        raise ValueError("Trigger table contains unlinked rows")
    return row, registry_row, registry


def linked_event_row(registry, trigger_rows, block):
    strategy_id = block.fields["tail_words"][2]
    linked = [trigger for trigger in registry.triggers if trigger.fields["strategy_id"] == strategy_id]
    if len(linked) != 1 or linked[0].class_name != "CTriggerEvent" or linked[0].fields["trigger_type"] != 4:
        raise ValueError("Operation requires one linked native Event trigger")
    event = linked[0]
    rows = trigger_rows_for(trigger_rows, event)
    if len(rows) != 1:
        raise ValueError("Event trigger must match exactly one native database row")
    return event, rows[0]


def select_event_variable(data, selector):
    keys(selector, ("id", "name"), ("id", "name"))
    name, ident = text(selector["name"]), selector["id"]
    if not name.isidentifier() or type(ident) is not int or not 0 <= ident <= 0x7fffffff:
        raise ValueError("Event trigger variable requires an exact native ID and a single identifier")
    variable = event_variable(data, name)
    if variable["id"] != ident or variable["kind"] not in (1, 2):
        raise ValueError("Event trigger variable ID/name differs or is not a switch or numeric scalar")
    return name


def event_edge_mode(edge):
    if edge in ("rising_then_falling", "falling_then_rising"):
        raise ValueError("The verified original Event compilers reject both compound transitions")
    if not isinstance(edge, str) or edge not in EDITABLE_EVENT_EDGES:
        raise ValueError(f"Event trigger edge requires one of {', '.join(EDITABLE_EVENT_EDGES)}")
    return EDITABLE_EVENT_EDGES[edge]


def set_event_trigger_variable(data, registry, trigger_rows, block, selector):
    name = select_event_variable(data, selector)
    event, row = linked_event_row(registry, trigger_rows, block)
    if event.fields["event_expression"] == name:
        return
    mirror = read_trigger_row(row, event)
    for target in (event, mirror):
        target.fields["event_expression"] = name
        target.fields["event_cache"] = b""
    row["lbContext"] = fmt.wrap_like(row["lbContext"], archive.serialize_trigger_payload(mirror))


def set_event_trigger_edge(registry, trigger_rows, block, edge):
    new_mode = event_edge_mode(edge)
    event, row = linked_event_row(registry, trigger_rows, block)
    # Both designers store the selected condition in the second trailing
    # DWORD. Keep the first word and each compiled expression unchanged.
    mode = event.fields["event_words"][1]
    if not 0 <= mode < len(EVENT_CONDITION_NAMES):
        raise ValueError("The existing Event trigger uses an unrecognized condition")
    if new_mode == mode:
        return
    mirror = read_trigger_row(row, event)
    event.fields["event_words"][1] = mirror.fields["event_words"][1] = new_mode
    row["lbContext"] = fmt.wrap_like(row["lbContext"], archive.serialize_trigger_payload(mirror))


def linked_loop_pair(registry, trigger_rows, block):
    strategy_id = block.fields["tail_words"][2]
    linked = [trigger for trigger in registry.triggers if trigger.fields["strategy_id"] == strategy_id]
    if len(linked) != 1 or linked[0].class_name != "CTriggerLoop" or linked[0].fields["trigger_type"] != 2:
        raise ValueError("Operation requires one linked native Loop trigger")
    canonical = linked[0]
    rows = trigger_rows_for(trigger_rows, canonical)
    if len(rows) != 1:
        raise ValueError("Loop trigger must match exactly one database row")
    row = rows[0]
    mirror = read_trigger_row(row, canonical)
    return canonical, row, mirror


LOOP_CALENDAR_FIELDS = ("month", "day", "hour", "minute", "second")
LOOP_CALENDAR_RANGES = ((1, 12), (1, 31), (0, 23), (0, 59), (0, 59))
LOOP_CALENDAR_PERIODS = ("year", "month", "day", "hour", "minute")


def native_calendar_period(packed):
    selector = packed >> 16
    if packed & 0xffff != 1 or not 1 <= selector <= len(LOOP_CALENDAR_PERIODS):
        raise ValueError("Loop trigger has an unrecognized native calendar selector")
    return selector - 1


def require_loop_interval(interval_ms):
    if type(interval_ms) is not int or not 100 <= interval_ms <= 2147483647:
        raise ValueError("Loop interval_ms must be an integer in the original range 100..2147483647")


def set_loop_interval(registry, trigger_rows, block, interval_ms, switch_from_calendar=False):
    require_loop_interval(interval_ms)
    canonical, row, mirror = linked_loop_pair(registry, trigger_rows, block)
    words = canonical.fields["loop_tail"]
    mirror_words = mirror.fields["loop_tail"]
    if words[0] & 0xffff or mirror_words[0] & 0xffff:
        if not switch_from_calendar:
            raise ValueError("Loop interval editing requires the original interval mode")
        if block.fields["tail_words"][2] == 1:
            raise ValueError("The original default Loop locks its calendar mode")
        if words != mirror_words:
            raise ValueError("Interval mode conversion requires matching native calendar mirrors")
        period = native_calendar_period(words[0])
        # Root Store preserves selector+1. The Trigger row keeps the interval decoder's selector.
        words[0] = (period + 1) << 16
        mirror_words[0] = period << 16
    elif words[1] == mirror_words[1] == interval_ms:
        return
    if words[1] != mirror_words[1]:
        raise ValueError("Loop trigger interval differs between archive copies")
    words[1] = mirror_words[1] = interval_ms
    row["lbContext"] = fmt.wrap_like(row["lbContext"], archive.serialize_trigger_payload(mirror))


def set_loop_calendar(registry, trigger_rows, block, patch):
    if not patch:
        raise ValueError("Loop calendar requires a period or clock field")
    selected = patch.get("calendar_period", "day")
    if selected not in LOOP_CALENDAR_PERIODS:
        raise ValueError("Loop calendar period must be year, month, day, hour or minute")
    canonical, row, mirror = linked_loop_pair(registry, trigger_rows, block)
    words = canonical.fields["loop_tail"]
    mirror_words = mirror.fields["loop_tail"]
    if block.fields["tail_words"][2] == 1:
        raise ValueError("The original default Loop locks its calendar mode")
    if not 100 <= words[1] <= 2147483647:
        raise ValueError("The original Loop interval must remain in the native range 100..2147483647")
    if words[0] & 0xffff == 0:
        canonical_selector, row_selector = (value[0] >> 16 for value in (words, mirror_words))
        # In interval mode the original reader retains an inactive selector,
        # including legacy values outside the calendar menu. The conversion
        # sets a new active selector after checking the exact linked archives.
        if (mirror_words[0] & 0xffff or words[1:] != mirror_words[1:]
                or canonical_selector not in (row_selector, row_selector + 1)):
            raise ValueError("Calendar conversion requires matching native interval archives")
        period = LOOP_CALENDAR_PERIODS.index(selected)
        required = LOOP_CALENDAR_FIELDS[period:]
        if not all(key in patch for key in required):
            needed = required[0] if len(required) == 1 else ", ".join(required[:-1]) + " and " + required[-1]
            raise ValueError("Changing an interval Loop to " + selected + " calendar requires " + needed)
    else:
        if words != mirror_words:
            raise ValueError("Calendar editing requires matching native calendar mirrors")
        original_period = native_calendar_period(words[0])
        period = LOOP_CALENDAR_PERIODS.index(selected) if "calendar_period" in patch else original_period

    clock = [patch.get(key, value) for key, value in zip(LOOP_CALENDAR_FIELDS, words[2:7], strict=True)]
    for index, (key, value, (minimum, maximum)) in enumerate(zip(LOOP_CALENDAR_FIELDS, clock, LOOP_CALENDAR_RANGES, strict=True)):
        if (index >= period or key in patch) and (type(value) is not int or not minimum <= value <= maximum):
            raise ValueError(f"Loop calendar {key} must be an integer in {minimum}..{maximum}")
    packed = ((period + 1) << 16) | 1
    if words[0] == packed and words[2:7] == clock:
        return
    words[0] = mirror_words[0] = packed
    words[2:7] = mirror_words[2:7] = clock
    row["lbContext"] = fmt.wrap_like(row["lbContext"], archive.serialize_trigger_payload(mirror))


def script_cell(source):
    condition = archive.Node("CStgyConnIF", dict(state_word=0, label="", compiled=b"", expression="\x010"))
    action = archive.Node("CStgyFuncProg", dict(state_word=1, label="脚本程序", compiled=b"", source=source))
    return archive.Node("CStrategyCell", dict(conditions=[condition], actions=[action]))


def require_unused_names(data, names, projected):
    """Inspect all exported fields with the edited structural identities removed."""
    from offline_picture_library import mentions
    for table, content in data.items():
        for row in content["rows"]:
            for field, value in row.items():
                replacement = projected.get((id(row), field), value)
                if isinstance(replacement, dict) and "binary" in replacement:
                    replacement = fmt.archive(replacement)
                for name in names:
                    hit = (mentions(replacement, name) if isinstance(replacement, bytes)
                           else isinstance(replacement, str) and name.casefold() in replacement.casefold())
                    if hit:
                        owner = f" [{row['strName']}]" if row.get("strName") else ""
                        raise ValueError(f"Possible name reference in {table}.{field}{owner}: {name!r}")


def require_strategy_metadata_target(registry, trigger_rows, block, kind=None):
    ident = block.fields["tail_words"][2]
    linked = [row for row in registry.triggers if row.fields["strategy_id"] == ident]
    if len(linked) != 1:
        raise ValueError("Strategy metadata editing requires exactly one linked native trigger")
    trigger = linked[0]
    class_name = trigger.class_name
    if kind is not None and class_name != kind:
        raise ValueError("Selected strategy has a different native trigger type")
    if class_name == "CTriggerLoop" and ident >= 2:
        linked_loop_pair(registry, trigger_rows, block)
    elif class_name == "CTriggerEvent" and ident >= 3:
        linked_event_row(registry, trigger_rows, block)
    elif class_name != "CTriggerUser" or trigger.fields["trigger_type"] != 3:
        raise ValueError("Strategy metadata requires a native user trigger or a supported custom Loop/Event trigger")


def strategy_content_nodes(block):
    """Walk the known native row, cell, condition and program ownership."""
    for row in block.fields["rows"]:
        if row is None:
            continue
        if row.class_name != "CStrategyRow":
            raise ValueError("Unrecognized native strategy row")
        yield row
        for cell in row.fields["cells"]:
            if cell is None:
                continue
            if cell.class_name != "CStrategyCell":
                raise ValueError("Unrecognized native strategy cell")
            yield cell
            for field, expected_class in (("conditions", "CStgyConnIF"), ("actions", "CStgyFuncProg")):
                for node in cell.fields[field]:
                    if node is None:
                        continue
                    if node.class_name != expected_class:
                        raise ValueError("Unrecognized native strategy condition or action")
                    yield node


def require_owned_timed_strategy_body(registry, block):
    nodes = list(strategy_content_nodes(block))
    if not any(node.class_name == "CStgyFuncProg" for node in nodes):
        raise ValueError("Nonempty custom Loop/Event deletion requires recognized native script actions")
    identities = {id(node) for node in nodes}
    for other in registry.strategies:
        if other is not block and any(id(node) in identities for node in strategy_content_nodes(other)):
            raise ValueError("Native strategy contents are shared with another block")


def strategy_edits(data, edits):
    row, registry_row, registry = strategy_state(data)
    trigger_rows = data["Trigger"]["rows"]
    next_strategy_id = max((node.fields["tail_words"][2] for node in registry.strategies), default=-1) + 1
    event_ids = (node.fields["trigger_id"] for node in registry.triggers
                 if node.class_name == "CTriggerEvent" and node.fields["trigger_id"] != DEFAULT_TRIGGER_ID)
    next_trigger_id = max(max((r["iID"] for r in trigger_rows), default=0), max(event_ids, default=0)) + 1
    for edit in edits:
        op, name = edit["op"], text(edit["name"])
        if op in ("add_user_strategy", "add_loop_strategy", "add_event_strategy"):
            is_loop = op == "add_loop_strategy"
            is_event = op == "add_event_strategy"
            fields = ("op", "name", "comment")
            if is_event:
                keys(edit, (*fields, "variable", "edge"), ("variable",))
            else:
                keys(edit, (*fields, "interval_ms" if is_loop else "source"))
            if any(n.fields["name"].casefold() == name.casefold() for n in registry.strategies):
                raise ValueError("Strategy name collision")
            if next_trigger_id == DEFAULT_TRIGGER_ID:
                next_trigger_id += 1
            strategy_id, trigger_id = next_strategy_id, next_trigger_id
            next_strategy_id += 1
            next_trigger_id += 1
            minimum_strategy_id = 3 if is_event else 2
            if not minimum_strategy_id <= strategy_id <= 0x7fffffff or not 0 < trigger_id <= 0x7fffffff:
                raise ValueError("No available native strategy or trigger ID")
            if is_loop:
                interval = edit.get("interval_ms", 60000)
                require_loop_interval(interval)
                strategy_rows = []
                comment = text(edit.get("comment", ""), empty=True)
                note = "按照设定的时间循环运行"
                kind, trigger_class = 2, "CTriggerLoop"
            elif is_event:
                expression = select_event_variable(data, edit["variable"])
                edge = event_edge_mode(edit.get("edge", "rising"))
                strategy_rows = []
                comment = text(edit.get("comment", ""), empty=True)
                note = EVENT_TRIGGER_NOTE
                kind, trigger_class = 4, "CTriggerEvent"
            else:
                source = text(edit["source"])
                strategy_rows = [archive.Node("CStrategyRow", dict(cells=[script_cell(source)]))]
                note = comment = text(edit.get("comment", "供其他策略、按钮等使用"), empty=True)
                kind, trigger_class = 3, "CTriggerUser"
            block = archive.Node("CStrategyBlock", dict(rows=strategy_rows, name=name, comment=comment,
                                                        tail_words=[0, 0, strategy_id, 1, 0]))
            archive.refresh_strategy_metadata_length(block)
            trigger_fields = dict(trigger_id=trigger_id, strategy_id=strategy_id, trigger_type=kind,
                                  note=note, common_tail=[0, 0, 0])
            if is_loop:
                # A newly created original custom Loop starts with interval mode and an inactive selector 1.
                trigger_fields["loop_tail"] = [0x10000, interval, 1, 1, 0, 0, 0, 0]
            if is_event:
                # The original Event starts with an empty CByteArray and zero delay.
                trigger_fields.update(event_cache=b"", event_expression=expression, event_words=[0, edge])
            trigger = archive.Node(trigger_class, trigger_fields)
            donor = next((r for r in trigger_rows if r["lType"] == kind), trigger_rows[0] if trigger_rows else None)
            if donor is None or set(donor) != {"iID","lStgyID","lType","lbContext","strNote","iTemp1","iTemp2"}:
                raise ValueError("Expected native trigger row layout")
            trigger_rows.append(dict(iID=trigger_id, lStgyID=strategy_id, lType=kind, strNote=note, iTemp1=None, iTemp2=None,
                                     lbContext=fmt.wrap_like(donor["lbContext"], archive.serialize_trigger_payload(trigger))))
            registry.strategies.append(block)
            registry.triggers.append(trigger)
            continue
        blocks = [n for n in registry.strategies if n.fields["name"] == name]
        if len(blocks) != 1:
            raise ValueError("Expected one named strategy")
        block = blocks[0]
        if op == "set_event_trigger_variable":
            keys(edit, ("op", "name", "variable"), ("variable",))
            set_event_trigger_variable(data, registry, trigger_rows, block, edit["variable"])
            continue
        if op == "set_event_trigger_edge":
            keys(edit, ("op", "name", "edge"), ("edge",))
            set_event_trigger_edge(registry, trigger_rows, block, edit["edge"])
            continue
        if op == "set_loop_interval":
            keys(edit, ("op", "name", "interval_ms", "switch_from_calendar"), ("interval_ms",))
            switch = edit.get("switch_from_calendar", False)
            if type(switch) is not bool:
                raise ValueError("switch_from_calendar must be boolean")
            set_loop_interval(registry, trigger_rows, block, edit["interval_ms"], switch)
            continue
        if op == "set_loop_calendar":
            fields = ("calendar_period", *LOOP_CALENDAR_FIELDS)
            keys(edit, ("op", "name", *fields))
            set_loop_calendar(registry, trigger_rows, block, {key:edit[key] for key in fields if key in edit})
            continue
        if op in ("delete_user_strategy", "delete_loop_strategy", "delete_event_strategy"):
            keys(edit, ("op", "name"))
            strategy_id = block.fields["tail_words"][2]
            if op == "delete_event_strategy":
                if strategy_id < 3:
                    raise ValueError("Only a custom Event can be removed")
                trigger, linked_row = linked_event_row(registry, trigger_rows, block)
            elif op == "delete_loop_strategy":
                if strategy_id < 2:
                    raise ValueError("Only a custom Loop can be removed")
                trigger, linked_row, _ = linked_loop_pair(registry, trigger_rows, block)
            else:
                linked = [t for t in registry.triggers if t.fields["strategy_id"] == strategy_id]
                if len(linked) != 1 or linked[0].class_name != "CTriggerUser":
                    raise ValueError("Operation requires a single native user trigger")
                trigger = linked[0]
                linked_row = one(trigger_rows, "lStgyID", strategy_id)
                if (linked_row["lType"] != 3 or trigger.fields["trigger_type"] != 3
                        or linked_row["iID"] != trigger.fields["trigger_id"]):
                    raise ValueError("Delete requires an exact linked trigger row")
            if op != "delete_user_strategy" and block.fields["rows"]:
                require_owned_timed_strategy_body(registry, block)
            # Each serializer builds its own MFC map from surviving nodes.
            # Database IDs in their fields are independent of map positions.
            registry.strategies.remove(block)
            registry.triggers.remove(trigger)
            trigger_rows.remove(linked_row)
            require_unused_names(data, (name,), {
                (id(row), "lbObjects"): archive.serialize_strategy_array(registry.strategies),
                (id(registry_row), "lbContext"): registry.serialize()})
            continue
        rename_classes = {"rename_user_strategy": "CTriggerUser", "rename_loop_strategy": "CTriggerLoop",
                          "rename_event_strategy": "CTriggerEvent"}
        if op in rename_classes or op == "set_strategy_comment":
            require_strategy_metadata_target(registry, trigger_rows, block, rename_classes.get(op))
            if op == "set_strategy_comment":
                keys(edit, ("op", "name", "comment"), ("comment",))
                comment = text(edit["comment"], empty=True)
                if block.fields["comment"] != comment:
                    block.fields["comment"] = comment
                    archive.refresh_strategy_metadata_length(block)
                continue
            keys(edit, ("op", "name", "new_name"), ("new_name",))
            new = text(edit["new_name"])
            if new == name or any(other is not block and other.fields["name"].casefold() == new.casefold()
                                  for other in registry.strategies):
                raise ValueError("Strategy name unchanged or occupied")
            block.fields["name"] = ""
            archive.refresh_strategy_metadata_length(block)
            require_unused_names(data, (name, new), {
                (id(row), "lbObjects"): archive.serialize_strategy_array(registry.strategies),
                (id(registry_row), "lbContext"): registry.serialize()})
            block.fields["name"] = new
            archive.refresh_strategy_metadata_length(block)
            continue
        rows = block.fields["rows"]
        if op in ("insert_script_row", "delete_script_row"):
            keys(edit, ("op","name","row","source") if op == "insert_script_row" else ("op","name","row"))
            i = position(edit["row"], len(rows), op == "insert_script_row")
            if op == "insert_script_row":
                rows.insert(i, archive.Node("CStrategyRow", dict(cells=[script_cell(text(edit["source"]))])))
            else:
                # A script-row deletion must not remove unrelated cells/actions.
                archive.single_program_action(archive.Node("CStrategyBlock", dict(rows=[rows[i]])))
                del rows[i]
        elif op in ("set_script", "set_condition"):
            keys(edit, ("op", "name", "row", "cell", "index", "value"))
            cells = rows[position(edit["row"], len(rows))].fields["cells"]
            cell = cells[position(edit["cell"], len(cells))]
            nodes = cell.fields["actions" if op == "set_script" else "conditions"]
            node = nodes[position(edit["index"], len(nodes))]
            if node is None or node.class_name != ("CStgyFuncProg" if op == "set_script" else "CStgyConnIF"):
                raise ValueError("Selected strategy node class differs")
            field = "source" if op == "set_script" else "expression"
            value = text(edit["value"])
            if value != node.fields[field]:
                member = "actions" if op == "set_script" else "conditions"
                references = sum(other is node for block in registry.strategies
                                 for other_row in block.fields["rows"] if other_row is not None
                                 for other_cell in other_row.fields["cells"] if other_cell is not None
                                 for other in other_cell.fields[member])
                if references != 1:
                    raise ValueError("Selected strategy node is shared across multiple paths")
                node.fields[field] = value
                node.fields["compiled"] = b""
        else:
            raise ValueError(f"Unknown strategy edit {op}")
    strategy_bytes = archive.serialize_strategy_array(registry.strategies)
    if strategy_bytes != fmt.archive(row["lbObjects"]):
        row["lbObjects"] = fmt.wrap_like(row["lbObjects"], strategy_bytes)
    registry_bytes = registry.serialize()
    if registry_bytes != fmt.archive(registry_row["lbContext"]):
        registry_row["lbContext"] = fmt.wrap_like(registry_row["lbContext"], registry_bytes)
    strategy_state(data)


def apply_program_recipe(data, spec):
    candidate = dict(data)
    touched = set()
    for field, tables, handler in (("recipe_edits", ("System", "WndUser"), recipe_edits),
                                  ("strategy_edits", ("System", "Stgy", "Trigger"), strategy_edits)):
        edits = spec.get(field, [])
        if not isinstance(edits, list):
            raise ValueError(f"{field} must be an array")
        if edits:
            for table in set(tables) - touched:
                candidate[table] = deepcopy(data[table])
            touched.update(tables)
            handler(candidate, edits)
    for table in touched:
        data[table] = candidate[table]
