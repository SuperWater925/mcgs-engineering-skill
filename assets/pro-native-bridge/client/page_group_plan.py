"""Plan Pro group and ungroup commands from a current original drawing capture."""
from hashlib import sha256
import json
import re

from page_plan import PLAN_FEATURE, fields, forest_paths, int_vector, path_key, require, require_native_length, selector
from project_plan import session_program


DESIGN = "mcgs-page-group-design/v1"
REVIEW = "mcgs-page-group-review/v1"
COORDINATES = "original-cell-coordinate-roles/v1"
FLATTEN_CELLS = "original-cell-flatten/v1"
GENERATION = ("process_id", "creation_filetime", "native_thread_id", "editor_image_sha256", "root")
IDENTITY = ("class", "type_id", "name", "native_id", "rectangle")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def group_request(design):
    fields(design, ("schema", "project_path", "page", "operation", "controls"), ("save", "flatten_selected_cells"))
    require(design["schema"] == DESIGN and type(design.get("save", False)) is bool,
            "Use a Pro group design and a Boolean save option")
    path_key(design["project_path"])
    page = fields(design["page"], ("id", "name"))
    require(type(page["id"]) is int and page["id"] >= 0 and native_name(page["name"]),
            "Identify the current page by ID and exact name")
    operation, controls = design["operation"], design["controls"]
    require(type(design.get("flatten_selected_cells", False)) is bool and
            (not design.get("flatten_selected_cells") or operation == "group"),
            "Flattening selected static cells is available only while grouping")
    require(operation in ("group", "ungroup") and isinstance(controls, list) and
            (len(controls) >= 2 if operation == "group" else len(controls) == 1),
            "Group at least two top-level controls or ungroup one native cell")
    seen = set()
    for item in controls:
        fields(item, ("path", "name", "class"), ("native_id", "complete"))
        index, = int_vector(item["path"], 1)
        require(index >= 0 and index not in seen and native_name(item["name"]) and native_name(item["class"]),
                "Identify distinct current top-level controls by path, name and class")
        require("native_id" not in item or type(item["native_id"]) is int, "Invalid original control ID")
        require("complete" not in item or native_address(item["complete"]), "Invalid original control address")
        seen.add(index)
    return {"page_id": page["id"], "page_name": page["name"]}, "control-" + operation


def native_name(value):
    return isinstance(value, str) and bool(value) and "\0" not in value


def native_address(value):
    return isinstance(value, str) and re.fullmatch(r"0x[0-9A-Fa-f]{8}", value) is not None and value != "0x00000000"


def read_action(action_id, kind, page, controls):
    return {"action_id": action_id, "kind": kind, "target": {**page, "controls": controls},
            "after": {"coordinate_contract": COORDINATES}}


def inspect_groups(design):
    page, kind = group_request(design)
    controls = []
    for item in design["controls"]:
        controls.append({"control_name": item["name"], "class": item["class"], "control_path": item["path"],
                         **{k: item[k] for k in ("complete", "native_id") if k in item}})
    result = {"commit": False, "actions": [read_action("group-preimage", kind, page, controls)]}
    require_native_length(result)
    return result


def group_capture(receipt, project, action):
    require(receipt.get("ok") is True and receipt.get("op") == "engineering-edit-inspect" and
            receipt.get("inspection_completed") is True and receipt.get("write_attempted") is False and
            receipt.get("all_requested_features_available") is True and
            path_key(receipt["actual_project"]) == path_key(project),
            "Use the complete independent native drawing inspection for this project")
    records = receipt["action_preimages"]
    require(len(records) == 1, "Use the original single drawing inspection receipt")
    record, = records
    require(all(record[key] == action[key] for key in ("action_id", "kind", "target")),
            "The drawing inspection selector differs from this group design")
    before = record["before"]
    page = before["page"]
    target = action["target"]
    require(page["page_id"] == target["page_id"] and page["page_name"] == target["page_name"] and
            native_address(page["page_iobject"]) and native_address(page["document"]) and
            native_address(page["view"]) and native_name(before.get("page_linker")) and
            SHA256.fullmatch(before.get("group_preimage_sha256", "")),
            "The original native page or group-coordinate preimage is unavailable")
    graph = before["reference_graph"]
    require(graph.get("complete_registered_native_graph") is True and
            graph.get("bidirectional_edges_consistent") is True and
            graph.get("edge_count") == len(graph["edges"]),
            "Native drawing inspection needs the complete bidirectional registered reference graph")
    forest = forest_paths(before["forest"], page["document"])
    complete = {row["complete"]: row for row in forest.values()}
    require(len(complete) == len(forest) and all(native_address(key) for key in complete),
            "Original native identities repeat or are missing")
    return before, forest


def row_index(rows, addresses, key):
    result = {row["complete"]: row[key] for row in rows}
    require(len(result) == len(rows) and result.keys() == addresses,
            "The drawing inspection does not cover all original objects: " + key)
    return result


def native_rect(row, model):
    x1, y1, x2, y2 = int_vector(row["rectangle"], 4)
    require(all(-2**31 <= n < 2**31 for n in (x1, y1, x2, y2)), "Native geometry does not fit signed Win32")
    if model == "directed-line":
        require((x1, y1) != (x2, y2), "Original line has coincident endpoints")
        return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    require(x1 <= x2 and y1 <= y2, "Original control bounds are inverted")
    return [x1, y1, x2, y2]


def mul_div(value, multiplier, divisor):
    product = value * multiplier
    magnitude = (abs(product) + divisor // 2) // divisor
    return -magnitude if product < 0 else magnitude


def convert(rect, outer, model, grouping):
    result = []
    for index, value in enumerate(rect):
        axis = index % 2
        origin = outer[axis]
        width = outer[axis + 2] - origin
        require(0 < width < 2**31 and (not grouping or -2**31 <= value - origin < 2**31),
                "Original group coordinates overflow or have a degenerate axis")
        projected = (mul_div(value - origin, 10000, width) if grouping
                     else origin + mul_div(value, width, 10000))
        require(-2**31 <= projected < 2**31, "Projected group coordinates overflow the original signed rectangle")
        result.append(projected)
    native_rect({"rectangle": result}, model)
    return result


def covered(value, path):
    return value == path or value.startswith(path + ".")


def require_reference_scope(edges, affected, removed):
    for edge in edges:
        source, target = edge["source"], edge["target"]
        moving_source = any(covered(source, path) for path in affected)
        moving_target = any(covered(target, path) for path in affected)
        require(not moving_target or moving_source, "An external original consumer references this group selection")
        require(not any(source == path or covered(target, path) for path in removed),
                "An old group has a registered reference that cannot be moved by the original operation")


def project_tree(row, properties, linkers, replacements, children):
    item = {key: row[key] for key in (*IDENTITY, "complete")}
    item["rectangle"] = replacements.get(row["complete"], row["rectangle"])
    item["properties"] = properties[row["complete"]]
    item["linker"] = linkers[row["complete"]]
    item["children"] = [project_tree(child, properties, linkers, replacements, child["children"])
                        for child in children]
    return item


def compile_groups(design, receipt):
    page, kind = group_request(design)
    action = inspect_groups(design)["actions"][0]
    existing, forest = group_capture(receipt, design["project_path"], action)
    require(all(receipt.get(key) is not None for key in GENERATION) and
            SHA256.fullmatch(receipt.get("project_sha256", "")), "Native group capture lacks original project identity")
    required = {"page-view-open", kind, "control-group"}
    if design.get("save"):
        required.update(("page-flush", "root-flush"))
    features = {PLAN_FEATURE, COORDINATES}
    if design.get("flatten_selected_cells"):
        features.add(FLATTEN_CELLS)
    require(required <= set(receipt["compiled_kinds"]) and
            features <= set(receipt["features"]),
            "The loaded engine lacks group-plan actions or project identity preflight")
    roots = existing["forest"]
    selected = []
    for item in design["controls"]:
        row = forest.get(tuple(item["path"]))
        require(row is not None and all(row[key] == item[key] for key in item),
                "The selected top-level path or control identity changed")
        selected.append(row)
    selected.sort(key=lambda row: row["path"])
    identities = {row["complete"] for row in forest.values()}
    roles = row_index(existing["coordinate_roles"], identities, "model")
    properties = row_index(existing["control_properties"], identities, "properties")
    linkers = row_index(existing["control_linkers"], identities, "linker")
    require(all(native_name(value) for value in linkers.values()) and
            len(set(linkers.values())) == len(linkers), "Original drawing object paths are missing or ambiguous")
    selecting = {row["complete"] for row in selected}
    remaining = [row for row in roots if row["complete"] not in selecting]
    grouping = kind == "control-group"
    if grouping:
        cells = [row for row in selected if roles[row["complete"]] == "native-cell-container"]
        require(bool(cells) == design.get("flatten_selected_cells", False),
                "Grouping a static native cell needs explicit flatten_selected_cells and replaces that cell")
    else:
        require(roles[selected[0]["complete"]] == "native-cell-container",
                "Ungroup planning needs the verified original CDrawCell container")
        cells = selected
    require(all(cell["children"] for cell in cells), "A selected native cell must contain retained members")
    removed = {row["complete"] for row in cells}
    members = [child for row in selected for child in (row["children"] if row["complete"] in removed else [row])]
    require(members and all(roles[row["complete"]] in ("bounding-rectangle", "directed-line") for row in members),
            "A member has a separate native transform or no verified coordinate role")
    # The native drawing forest and registered object namespace are distinct.
    # The original Cell commands preserve the page-scoped linkers of their members.
    require(all(linkers[row["complete"]] == existing["page_linker"] + "." + row["name"]
                for row in [*selected, *members]), "A selected original drawing does not have a page-scoped linker")
    coordinates = {row["complete"]: row["rectangle"] for row in members}
    if grouping:
        for cell in cells:
            old_bounds = native_rect(cell, "bounding-rectangle")
            for member in cell["children"]:
                address = member["complete"]
                coordinates[address] = convert(member["rectangle"], old_bounds, roles[address], grouping=False)
    boxes = [native_rect({"rectangle": coordinates[row["complete"]]}, roles[row["complete"]]) for row in members]
    outer = ([min(box[0] for box in boxes), min(box[1] for box in boxes),
              max(box[2] for box in boxes), max(box[3] for box in boxes)] if grouping
             else native_rect(selected[0], "bounding-rectangle"))
    if not grouping:
        names = [row["name"].casefold() for row in [*members, *remaining]]
        require(len(set(names)) == len(names), "Ungroup would collide with an original top-level name")
    edges = existing["reference_graph"]["edges"]
    require_reference_scope(edges, [linkers[key] for key in {*selecting, *coordinates}], [linkers[key] for key in removed])
    replacements = {row["complete"]: convert(coordinates[row["complete"]], outer, roles[row["complete"]], grouping)
                    for row in members}
    flags = {row["complete"]: (4 if not grouping and len(members) == 1 else 2 if i == len(members) - 1 else 1)
             for i, row in enumerate(members)}
    survivors = []
    for row in forest.values():
        address = row["complete"]
        if address in removed:
            continue
        survivors.append({"complete": address, "name": row["name"], "properties": properties[address],
                          "rectangle": replacements.get(address, row["rectangle"]),
                          **({"raw_DWORD60": flags[address]} if address in flags else {})})
    after = {"coordinate_contract": COORDINATES, "group_preimage_sha256": existing["group_preimage_sha256"],
             "surviving_controls": survivors, **({"group_rectangle": outer} if grouping else {})}
    if design.get("flatten_selected_cells"):
        after["flatten_selected_cells"] = True
    project = design["project_path"]
    review_id = sha256(json.dumps([design, after["group_preimage_sha256"]], ensure_ascii=False,
                                  sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]
    target = {**page, "controls": [selector(row) for row in selected]}
    edit = {"action_id": f"{kind}-{review_id}", "kind": kind, "target": target, "after": after}
    activation = {"action_id": f"group-view-{review_id}", "kind": "page-view-open", "target": page, "after": {"open": True}}
    preflight = {key: receipt[key] for key in ("process_id", "creation_filetime", "root", "project_sha256")}
    preflight.update(project_path=receipt["actual_project"], pages=[])
    specification = {"commit": False, "actions": [activation, edit], "required_features": sorted(features),
                     "design_preflight": preflight}
    require_native_length(specification)
    steps = [{"step_id": "group-edit", "specification": specification}]
    if design.get("save"):
        steps.append({"step_id": "group-save", "specification": {"commit": False, "actions": [
            {"action_id": f"group-page-flush-{review_id}", "kind": "page-flush", "target": page, "after": {}},
            {"action_id": f"group-root-flush-{review_id}", "kind": "root-flush", "target": {}, "after": {}},
        ]}})
    fresh = read_action(f"group-readback-{review_id}", "control-group", page, [])
    inspection = {"commit": False, "actions": [fresh]}
    require_native_length(inspection)
    post = [project_tree(row, properties, linkers, replacements, row["children"]) for row in remaining]
    moved = [project_tree(row, properties, linkers, replacements, row["children"]) for row in members]
    if grouping:
        post.append({"class": "CDrawCell", "type_id": 0x5039, "rectangle": outer, "children": moved,
                     "new_native_group": True})
    else:
        post.extend(moved)
    review = {"schema": REVIEW, "review_id": review_id, "project_path": project,
              "project_sha256": receipt["project_sha256"], **{key: receipt[key] for key in GENERATION},
              "page_identity": {field: existing["page"][field] for field in ("page_iobject", "document", "view")},
              "page_linker": existing["page_linker"], "page_attributes": existing["page"]["attributes"],
              "page_catalog": existing["page"]["pages"], "expected_forest": post,
              "original_linkers": linkers, "reference_edges": edges, "readback_action": fresh,
              "native_execution_performed": False, "save_requested": design.get("save", False)}
    return session_program(project, steps), inspection, review


def report_groups(review, receipt):
    require(review.get("schema") == REVIEW, "Use the Pro group review generated with this program")
    readback, forest = group_capture(receipt, review["project_path"], review["readback_action"])
    require(all(receipt.get(key) == review[key] for key in GENERATION),
            "Use an independent inspection of the same project generation for the group report")
    addresses = {row["complete"] for row in forest.values()}
    properties = row_index(readback["control_properties"], addresses, "properties")
    linkers = row_index(readback["control_linkers"], addresses, "linker")
    require(COORDINATES in receipt["features"], "The readback lacks the native group-coordinate contract")
    differences = []

    def compare(expected, actual, path):
        if len(expected) != len(actual):
            differences.append({"path": path, "field": "sibling_count", "expected": len(expected), "actual": len(actual)})
        for index, (wanted, row) in enumerate(zip(expected, actual)):
            place = [*path, index]
            if wanted.get("new_native_group"):
                keys = ("class", "type_id", "rectangle")
                logical_path = review["page_linker"] + "." + row["name"]
                if (not native_name(row["name"]) or row["complete"] in review["original_linkers"] or
                        sum(peer["name"] == row["name"] for peer in forest.values()) != 1):
                    differences.append({"path": place, "field": "new_group_identity"})
            else:
                keys = (*IDENTITY, "complete")
                logical_path = wanted["linker"]
                current = properties[row["complete"]]
                if wanted["properties"] != current:
                    differences.append({"path": place, "field": "properties", "expected": wanted["properties"],
                                        "actual": current})
            if linkers[row["complete"]] != logical_path:
                differences.append({"path": place, "field": "linker", "expected": logical_path,
                                    "actual": linkers[row["complete"]]})
            for key in keys:
                if wanted[key] != row[key]:
                    differences.append({"path": place, "field": key, "expected": wanted[key], "actual": row[key]})
            compare(wanted["children"], row["children"], place)

    compare(review["expected_forest"], readback["forest"], [])
    if (readback["page_linker"] != review["page_linker"] or
            any(readback["page"][field] != value for field, value in review["page_identity"].items())):
        differences.append({"path": [], "field": "page_identity"})
    if review["page_catalog"] != readback["page"]["pages"]:
        differences.append({"path": [], "field": "page_catalog"})
    if review["page_attributes"] != readback["page"]["attributes"]:
        differences.append({"path": [], "field": "page_attributes"})

    expected_edges = sorted((edge["source"], edge["target"]) for edge in review["reference_edges"])
    actual_edges = sorted((edge["source"], edge["target"]) for edge in readback["reference_graph"]["edges"])
    if expected_edges != actual_edges:
        differences.append({"path": [], "field": "reference_edges"})
    return {"schema": "mcgs-page-group-readback/v1", "project_path": review["project_path"],
            "review_id": review["review_id"], "business_readback_passed": not differences,
            "differences": differences, "file_readback": "unverified", "native_project_check": "unverified",
            "close_reopen": "unverified", "simulation": "unverified"}
