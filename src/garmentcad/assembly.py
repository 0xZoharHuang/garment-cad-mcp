from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any
from uuid import uuid4

from garmentcad.models import ChangeSummary, ObjectRef, Operation, ValidationIssue
from garmentcad.storage import read_json


def empty_assembly() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "units": "mm",
        "panels": {},
        "interfaces": {},
        "stitches": {},
    }


def _resolve(items: dict[str, Any], reference: ObjectRef | None) -> str:
    if reference is None:
        raise ValueError("This operation requires a target")
    if reference.uuid and reference.uuid in items:
        return reference.uuid
    if reference.alias:
        matches = [key for key, value in items.items() if value.get("alias") == reference.alias]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Alias is ambiguous: {reference.alias}")
    raise ValueError(f"Object not found: {reference.display()}")


def _point(value: Any, dimensions: int = 2) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != dimensions:
        raise ValueError(f"Expected a {dimensions}D point")
    return [float(component) for component in value]


def _panel_edges(vertices: list[list[float]]) -> list[dict[str, Any]]:
    return [
        {"id": str(uuid4()), "start": index, "end": (index + 1) % len(vertices), "curve": None}
        for index in range(len(vertices))
    ]


def _copy_edge_identity(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["id"] = source["id"]
    if source.get("alias") is not None:
        target["alias"] = source["alias"]


def _replace_edge(
    panel: dict[str, Any],
    interfaces: dict[str, Any],
    edge_index: int,
    inserted: list[list[float]],
) -> None:
    old_edges = panel["edges"]
    if edge_index < 0 or edge_index >= len(old_edges):
        raise ValueError("edge_index is out of range")
    original = old_edges[edge_index]
    panel["vertices_mm"][edge_index + 1 : edge_index + 1] = inserted
    new_edges = _panel_edges(panel["vertices_mm"])
    added = len(inserted)
    for index, old_edge in enumerate(old_edges):
        mapped = index if index <= edge_index else index + added
        _copy_edge_identity(new_edges[mapped], old_edge)
    replacement_ids = [edge["id"] for edge in new_edges[edge_index : edge_index + added + 1]]
    for interface in interfaces.values():
        ids = interface.get("edge_ids", [])
        if original["id"] in ids:
            position = ids.index(original["id"])
            ids[position : position + 1] = replacement_ids
    panel["edges"] = new_edges


def _panel_ref(value: Any) -> ObjectRef:
    if isinstance(value, str):
        return ObjectRef(uuid=value) if len(value) == 36 else ObjectRef(alias=value)
    return ObjectRef.model_validate(value)


def _distance(first: list[float], second: list[float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _lerp(first: list[float], second: list[float], fraction: float) -> list[float]:
    return [first[index] + (second[index] - first[index]) * fraction for index in range(2)]


def _rotate_2d(point: list[float], origin: list[float], angle_deg: float) -> list[float]:
    angle = math.radians(angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    x, y = point[0] - origin[0], point[1] - origin[1]
    return [
        origin[0] + x * cosine - y * sine,
        origin[1] + x * sine + y * cosine,
    ]


def _component_panels(
    components: dict[str, Any], panels: dict[str, Any], alias: str
) -> list[tuple[str, dict[str, Any]]]:
    if alias not in components:
        raise ValueError(f"Component not found: {alias}")
    return [(panel_id, panels[panel_id]) for panel_id in components[alias]]


def apply_operations(
    source: dict[str, Any], operations: list[Operation]
) -> tuple[dict[str, Any], ChangeSummary]:
    state = copy.deepcopy(source)
    state.setdefault("units", "mm")
    state.setdefault("panels", {})
    state.setdefault("interfaces", {})
    if isinstance(state.get("stitches"), list):
        state["stitches"] = {
            item.get("id", str(uuid4())): item for item in state.get("stitches", [])
        }
    state.setdefault("stitches", {})
    state.setdefault("components", {})
    summary = ChangeSummary()

    for operation in operations:
        try:
            _apply_one(state, operation, summary)
        except (IndexError, KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            summary.issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_assembly_operation",
                    message=f"{operation.action}: {error}",
                    objects=[operation.target] if operation.target else [],
                )
            )
    summary.issues.extend(validate_assembly(state))
    return state, summary


def _apply_one(state: dict[str, Any], operation: Operation, summary: ChangeSummary) -> None:
    action = operation.action
    args = operation.arguments
    panels = state["panels"]
    interfaces = state["interfaces"]
    stitches = state["stitches"]
    components = state["components"]

    if action == "panel.create":
        vertices = [_point(point) for point in args["vertices_mm"]]
        if len(vertices) < 3:
            raise ValueError("A panel needs at least three vertices")
        object_id = str(args.get("uuid") or uuid4())
        alias = str(args.get("alias") or object_id)
        if any(panel.get("alias") == alias for panel in panels.values()):
            raise ValueError(f"Panel alias already exists: {alias}")
        panels[object_id] = {
            "id": object_id,
            "alias": alias,
            "vertices_mm": vertices,
            "edges": _panel_edges(vertices),
            "translation_mm": _point(args.get("translation_mm", [0, 0, 0]), 3),
            "rotation_deg": _point(args.get("rotation_deg", [0, 0, 0]), 3),
        }
        summary.created.append(ObjectRef(uuid=object_id, alias=alias))
    elif action == "panel.delete":
        object_id = _resolve(panels, operation.target)
        panel = panels.pop(object_id)
        removed_interfaces = {
            key for key, interface in interfaces.items() if interface.get("panel_id") == object_id
        }
        for key in removed_interfaces:
            interfaces.pop(key)
        for key in list(stitches):
            if (
                stitches[key].get("interface_a") in removed_interfaces
                or stitches[key].get("interface_b") in removed_interfaces
            ):
                stitches.pop(key)
        summary.deleted.append(ObjectRef(uuid=object_id, alias=panel.get("alias")))
    elif action == "panel.transform":
        object_id = _resolve(panels, operation.target)
        panel = panels[object_id]
        if "translation_mm" in args:
            panel["translation_mm"] = _point(args["translation_mm"], 3)
        if "rotation_deg" in args:
            panel["rotation_deg"] = _point(args["rotation_deg"], 3)
        if "translation_delta_mm" in args:
            delta = _point(args["translation_delta_mm"], 3)
            panel["translation_mm"] = [
                panel["translation_mm"][index] + delta[index] for index in range(3)
            ]
        if "rotation_delta_deg" in args:
            delta = _point(args["rotation_delta_deg"], 3)
            panel["rotation_deg"] = [
                panel["rotation_deg"][index] + delta[index] for index in range(3)
            ]
        if args.get("center_x"):
            xs = [point[0] for point in panel["vertices_mm"]]
            panel["translation_mm"][0] = -(min(xs) + max(xs)) / 2
        summary.changed.append(ObjectRef(uuid=object_id, alias=panel.get("alias")))
    elif action == "panel.pivot":
        object_id = _resolve(panels, operation.target)
        panel = panels[object_id]
        pivot = _point(args["point_mm"])
        if args.get("replicate_placement"):
            panel["translation_mm"][0] += pivot[0]
            panel["translation_mm"][1] += pivot[1]
        panel["vertices_mm"] = [
            [point[0] - pivot[0], point[1] - pivot[1]] for point in panel["vertices_mm"]
        ]
        summary.changed.append(ObjectRef(uuid=object_id, alias=panel.get("alias")))
    elif action == "panel.mirror":
        source_id = _resolve(panels, operation.target)
        source = panels[source_id]
        axis = str(args.get("axis", "x"))
        if axis not in {"x", "y"}:
            raise ValueError("axis must be x or y")
        origin = float(args.get("origin_mm", 0))
        coordinate = 0 if axis == "x" else 1
        vertices = copy.deepcopy(source["vertices_mm"])
        for point in vertices:
            point[coordinate] = 2 * origin - point[coordinate]
        vertices.reverse()
        object_id = str(args.get("uuid") or uuid4())
        alias = str(args["alias"])
        panels[object_id] = {
            **{
                key: copy.deepcopy(value)
                for key, value in source.items()
                if key not in {"id", "alias", "edges", "vertices_mm"}
            },
            "id": object_id,
            "alias": alias,
            "vertices_mm": vertices,
            "edges": _panel_edges(vertices),
        }
        summary.created.append(ObjectRef(uuid=object_id, alias=alias))
    elif action == "edge.split":
        panel_id = _resolve(panels, _panel_ref(args["panel"]))
        panel = panels[panel_id]
        edge_index = int(args["edge_index"])
        fractions = sorted({float(value) for value in args["fractions"]})
        if not fractions or fractions[0] <= 0 or fractions[-1] >= 1:
            raise ValueError("fractions must contain values strictly between 0 and 1")
        edges = panel["edges"]
        if edge_index < 0 or edge_index >= len(edges):
            raise ValueError("edge_index is out of range")
        original = edges[edge_index]
        vertices = panel["vertices_mm"]
        start = vertices[original["start"]]
        end = vertices[original["end"]]
        inserted = [_lerp(start, end, fraction) for fraction in fractions]
        _replace_edge(panel, interfaces, edge_index, inserted)
        summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "edge.extend":
        panel_id = _resolve(panels, _panel_ref(args["panel"]))
        panel = panels[panel_id]
        edge = panel["edges"][int(args["edge_index"])]
        start = panel["vertices_mm"][edge["start"]]
        end = panel["vertices_mm"][edge["end"]]
        length = _distance(start, end)
        if math.isclose(length, 0):
            raise ValueError("Cannot extend a zero-length edge")
        unit = [(end[index] - start[index]) / length for index in range(2)]
        start_delta = float(args.get("start_delta_mm", 0))
        end_delta = float(args.get("end_delta_mm", 0))
        panel["vertices_mm"][edge["start"]] = [
            start[index] - unit[index] * start_delta for index in range(2)
        ]
        panel["vertices_mm"][edge["end"]] = [
            end[index] + unit[index] * end_delta for index in range(2)
        ]
        summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "edge_sequence.transform":
        panel_id = _resolve(panels, _panel_ref(args["panel"]))
        panel = panels[panel_id]
        indices = [int(value) for value in args["edge_indices"]]
        if not indices:
            raise ValueError("edge_indices must not be empty")
        selected = [panel["edges"][index] for index in indices]
        vertex_indices = list(
            dict.fromkeys(index for edge in selected for index in (edge["start"], edge["end"]))
        )
        origin = _point(args.get("origin_mm", panel["vertices_mm"][selected[0]["start"]]))
        if "snap_start_mm" in args:
            target = _point(args["snap_start_mm"])
            start = panel["vertices_mm"][selected[0]["start"]]
            shift = [target[0] - start[0], target[1] - start[1]]
        else:
            shift = _point(args.get("translation_delta_mm", [0, 0]))
        for index in vertex_indices:
            point = panel["vertices_mm"][index]
            point = [point[0] + shift[0], point[1] + shift[1]]
            if "rotation_deg" in args:
                point = _rotate_2d(point, origin, float(args["rotation_deg"]))
            if "reflect_line_mm" in args:
                line = args["reflect_line_mm"]
                first, second = _point(line[0]), _point(line[1])
                dx, dy = second[0] - first[0], second[1] - first[1]
                length_squared = dx * dx + dy * dy
                if math.isclose(length_squared, 0):
                    raise ValueError("reflect_line_mm points must differ")
                projection = (
                    (point[0] - first[0]) * dx + (point[1] - first[1]) * dy
                ) / length_squared
                projected = [first[0] + projection * dx, first[1] + projection * dy]
                point = [2 * projected[0] - point[0], 2 * projected[1] - point[1]]
            panel["vertices_mm"][index] = point
        summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "edge.chamfer":
        panel_id = _resolve(panels, _panel_ref(args["panel"]))
        panel = panels[panel_id]
        vertices = panel["vertices_mm"]
        vertex_index = int(args["vertex_index"])
        current = vertices[vertex_index]
        previous = vertices[(vertex_index - 1) % len(vertices)]
        following = vertices[(vertex_index + 1) % len(vertices)]
        before = float(args["distance_before_mm"])
        after = float(args.get("distance_after_mm", before))
        first = _lerp(current, previous, before / _distance(current, previous))
        second = _lerp(current, following, after / _distance(current, following))
        old_edges = panel["edges"]
        vertices[vertex_index : vertex_index + 1] = [first, second]
        new_edges = _panel_edges(vertices)
        for index, old_edge in enumerate(old_edges):
            mapped = index if index < vertex_index else index + 1
            _copy_edge_identity(new_edges[mapped], old_edge)
        panel["edges"] = new_edges
        summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "dart.insert":
        panel_id = _resolve(panels, _panel_ref(args["panel"]))
        panel = panels[panel_id]
        edge_index = int(args["edge_index"])
        edge = panel["edges"][edge_index]
        start = panel["vertices_mm"][edge["start"]]
        end = panel["vertices_mm"][edge["end"]]
        position = float(args.get("position", 0.5))
        intake = float(args["intake_mm"])
        depth = float(args["depth_mm"])
        length = _distance(start, end)
        center = _lerp(start, end, position)
        unit = [(end[index] - start[index]) / length for index in range(2)]
        normal = [-unit[1], unit[0]]
        leg_a = [center[index] - unit[index] * intake / 2 for index in range(2)]
        apex = [center[index] + normal[index] * depth for index in range(2)]
        leg_b = [center[index] + unit[index] * intake / 2 for index in range(2)]
        _replace_edge(panel, interfaces, edge_index, [leg_a, apex, leg_b])
        summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "component.define":
        alias = str(args["alias"])
        components[alias] = [_resolve(panels, _panel_ref(value)) for value in args["panels"]]
        summary.changed.extend(
            ObjectRef(uuid=panel_id, alias=panels[panel_id].get("alias"))
            for panel_id in components[alias]
        )
    elif action == "component.transform":
        alias = str(args["component"])
        members = _component_panels(components, panels, alias)
        delta_translation = _point(args.get("translation_delta_mm", [0, 0, 0]), 3)
        delta_rotation = _point(args.get("rotation_delta_deg", [0, 0, 0]), 3)
        for panel_id, panel in members:
            panel["translation_mm"] = [
                panel["translation_mm"][index] + delta_translation[index] for index in range(3)
            ]
            panel["rotation_deg"] = [
                panel["rotation_deg"][index] + delta_rotation[index] for index in range(3)
            ]
            summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "component.mirror":
        alias = str(args["component"])
        axis = str(args.get("axis", "x"))
        if axis not in {"x", "y"}:
            raise ValueError("axis must be x or y")
        coordinate = 0 if axis == "x" else 1
        origin = float(args.get("origin_mm", 0))
        for panel_id, panel in _component_panels(components, panels, alias):
            for point in panel["vertices_mm"]:
                point[coordinate] = 2 * origin - point[coordinate]
            panel["translation_mm"][coordinate] *= -1
            summary.changed.append(ObjectRef(uuid=panel_id, alias=panel.get("alias")))
    elif action == "valentina.import":
        from garmentcad.valentina_bridge import snapshot_to_assembly

        imported = snapshot_to_assembly(args["snapshot"], args.get("sidecar"))
        state.clear()
        state.update(imported)
        summary.created.extend(
            ObjectRef(uuid=panel_id, alias=panel.get("alias"))
            for panel_id, panel in state["panels"].items()
        )
    elif action == "interface.define":
        panel_ref = ObjectRef.model_validate(args["panel"])
        panel_id = _resolve(panels, panel_ref)
        edge_indices = [int(index) for index in args["edge_indices"]]
        object_id = str(args.get("uuid") or uuid4())
        alias = str(args.get("alias") or object_id)
        interfaces[object_id] = {
            "id": object_id,
            "alias": alias,
            "panel_id": panel_id,
            "edge_indices": edge_indices,
            "edge_ids": [panels[panel_id]["edges"][index]["id"] for index in edge_indices],
            "reverse": bool(args.get("reverse", False)),
            "ruffle": float(args.get("ruffle", 1.0)),
            "right_wrong": bool(args.get("right_wrong", False)),
        }
        summary.created.append(ObjectRef(uuid=object_id, alias=alias))
    elif action == "interface.delete":
        object_id = _resolve(interfaces, operation.target)
        item = interfaces.pop(object_id)
        for key in list(stitches):
            if object_id in (stitches[key].get("interface_a"), stitches[key].get("interface_b")):
                stitches.pop(key)
        summary.deleted.append(ObjectRef(uuid=object_id, alias=item.get("alias")))
    elif action == "interface.update":
        object_id = _resolve(interfaces, operation.target)
        item = interfaces[object_id]
        panel = panels[item["panel_id"]]
        if "edge_indices" in args:
            item["edge_indices"] = [int(index) for index in args["edge_indices"]]
            item["edge_ids"] = [panel["edges"][index]["id"] for index in item["edge_indices"]]
        if args.get("reverse_order"):
            item["edge_indices"].reverse()
            item["edge_ids"].reverse()
        if args.get("flip_edges"):
            item["reverse"] = not bool(item.get("reverse", False))
        if "right_wrong" in args:
            item["right_wrong"] = bool(args["right_wrong"])
        if "ruffle" in args:
            item["ruffle"] = float(args["ruffle"])
        summary.changed.append(ObjectRef(uuid=object_id, alias=item.get("alias")))
    elif action == "stitch.create":
        interface_a = _resolve(interfaces, ObjectRef.model_validate(args["interface_a"]))
        interface_b = _resolve(interfaces, ObjectRef.model_validate(args["interface_b"]))
        object_id = str(args.get("uuid") or uuid4())
        alias = str(args.get("alias") or object_id)
        stitches[object_id] = {
            "id": object_id,
            "alias": alias,
            "interface_a": interface_a,
            "interface_b": interface_b,
            "direction": str(args.get("direction", "auto")),
        }
        summary.created.append(ObjectRef(uuid=object_id, alias=alias))
    elif action == "stitch.delete":
        object_id = _resolve(stitches, operation.target)
        item = stitches.pop(object_id)
        summary.deleted.append(ObjectRef(uuid=object_id, alias=item.get("alias")))
    elif action == "validate":
        return
    else:
        raise ValueError(f"Unsupported assembly action: {action}")


def validate_assembly(state: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    panels = state.get("panels", {})
    interfaces = state.get("interfaces", {})
    stitches = state.get("stitches", {})
    for panel_id, panel in panels.items():
        vertices = panel.get("vertices_mm", [])
        area = 0.0
        for index, point in enumerate(vertices):
            following = vertices[(index + 1) % len(vertices)]
            area += point[0] * following[1] - following[0] * point[1]
        if math.isclose(area, 0.0, abs_tol=1e-6):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="degenerate_panel",
                    message=f"Panel {panel.get('alias', panel_id)} has zero area",
                    objects=[ObjectRef(uuid=panel_id, alias=panel.get("alias"))],
                )
            )
        intersections = _self_intersections(vertices)
        if intersections:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="panel_self_intersection",
                    message=f"Panel {panel.get('alias', panel_id)} self-intersects",
                    objects=[ObjectRef(uuid=panel_id, alias=panel.get("alias"))],
                    details={"edge_pairs": intersections},
                )
            )
    for interface_id, interface in interfaces.items():
        panel = panels.get(interface.get("panel_id"))
        if panel is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="missing_panel",
                    message=f"Interface {interface_id} references a missing panel",
                )
            )
            continue
        edge_count = len(panel.get("edges", []))
        if interface.get("edge_ids"):
            by_id = {edge["id"]: index for index, edge in enumerate(panel["edges"])}
            missing = [edge_id for edge_id in interface["edge_ids"] if edge_id not in by_id]
            if missing:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="missing_edge",
                        message=(
                            f"Interface {interface.get('alias', interface_id)} "
                            "references deleted edges"
                        ),
                        details={"edge_ids": missing},
                    )
                )
            else:
                interface["edge_indices"] = [by_id[edge_id] for edge_id in interface["edge_ids"]]
        if any(index < 0 or index >= edge_count for index in interface.get("edge_indices", [])):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_edge_index",
                    message=f"Interface {interface.get('alias', interface_id)} has an invalid edge",
                )
            )
    for stitch_id, stitch in stitches.items():
        if (
            stitch.get("interface_a") not in interfaces
            or stitch.get("interface_b") not in interfaces
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="missing_interface",
                    message=(
                        f"Stitch {stitch.get('alias', stitch_id)} references a missing interface"
                    ),
                )
            )
            continue
        side_a = interfaces[stitch["interface_a"]].get("edge_indices", [])
        side_b = interfaces[stitch["interface_b"]].get("edge_indices", [])
        if len(side_a) != len(side_b):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="unmatched_interface_partition",
                    message=(
                        f"Stitch {stitch.get('alias', stitch_id)} has {len(side_a)} edges "
                        f"on one side and {len(side_b)} on the other; native GarmentCode "
                        "will match and subdivide them"
                    ),
                )
            )
            continue
        lengths = []
        for interface_key in ("interface_a", "interface_b"):
            interface = interfaces[stitch[interface_key]]
            panel = panels[interface["panel_id"]]
            edge_ids = interface.get("edge_ids", [])
            selected = (
                [edge for edge in panel["edges"] if edge["id"] in edge_ids]
                if edge_ids
                else [panel["edges"][index] for index in interface["edge_indices"]]
            )
            lengths.append(
                sum(
                    _distance(
                        panel["vertices_mm"][edge["start"]],
                        panel["vertices_mm"][edge["end"]],
                    )
                    for edge in selected
                )
            )
        difference = abs(lengths[0] - lengths[1])
        if difference > 3.0:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="seam_length_mismatch",
                    message=(
                        f"Stitch {stitch.get('alias', stitch_id)} differs by {difference:.2f} mm"
                    ),
                    details={"side_lengths_mm": lengths, "difference_mm": difference},
                )
            )
    return issues


def _self_intersections(vertices: list[list[float]]) -> list[list[int]]:
    def orientation(a: list[float], b: list[float], c: list[float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    count = len(vertices)
    intersections = []
    for first in range(count):
        a, b = vertices[first], vertices[(first + 1) % count]
        for second in range(first + 1, count):
            if second in {first, (first + 1) % count, (first - 1) % count}:
                continue
            c, d = vertices[second], vertices[(second + 1) % count]
            if (
                orientation(a, b, c) * orientation(a, b, d) < 0
                and orientation(c, d, a) * orientation(c, d, b) < 0
            ):
                intersections.append([first, second])
    return intersections


def preview_assembly(
    project_root: Path, operations: list[Operation]
) -> tuple[dict[str, Any], ChangeSummary]:
    source = read_json(project_root / "assembly/assembly.json", default=empty_assembly())
    state, summary = apply_operations(source, operations)
    if not any(issue.severity == "error" for issue in summary.issues):
        from garmentcad.garmentcode_facade import GarmentCodeFacade

        facade = GarmentCodeFacade()
        if facade.available:
            try:
                diagnostics = facade.validate(state)
                summary.measurements["garmentcode.panels"] = float(
                    len(diagnostics.get("panels", {}))
                )
                summary.measurements["garmentcode.interfaces"] = float(
                    len(diagnostics.get("interfaces", {}))
                )
                summary.measurements["garmentcode.stitches"] = float(
                    len(diagnostics.get("stitches", {}))
                )
                for alias, panel in diagnostics.get("panels", {}).items():
                    if not panel.get("closed") or not panel.get("chained"):
                        summary.issues.append(
                            ValidationIssue(
                                severity="error",
                                code="garmentcode_open_panel",
                                message=f"Native GarmentCode panel {alias} is not a closed chain",
                                details=panel,
                            )
                        )
                    if panel.get("self_intersecting"):
                        summary.issues.append(
                            ValidationIssue(
                                severity="error",
                                code="garmentcode_self_intersection",
                                message=f"Native GarmentCode panel {alias} self-intersects",
                                details=panel,
                            )
                        )
                for alias, stitch in diagnostics.get("stitches", {}).items():
                    summary.measurements[f"stitch.{alias}.length_difference_mm"] = float(
                        stitch.get("length_difference_mm", 0.0)
                    )
                    if not stitch.get("native_matching"):
                        summary.issues.append(
                            ValidationIssue(
                                severity="error",
                                code="garmentcode_incompatible_stitch",
                                message=f"Native GarmentCode cannot match stitch {alias}",
                                details=stitch,
                            )
                        )
                if not diagnostics.get("roundtrip_ok"):
                    summary.issues.append(
                        ValidationIssue(
                            severity="error",
                            code="garmentcode_roundtrip_failed",
                            message="Pinned GarmentCode could not round-trip the assembly",
                        )
                    )
            except Exception as error:
                summary.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="garmentcode_native_validation_failed",
                        message=str(error),
                    )
                )
    return state, summary


def to_garmentcode(state: dict[str, Any]) -> dict[str, Any]:
    """Return native GarmentCode JSON. Project millimetres become centimetres."""
    from garmentcad.garmentcode_facade import GarmentCodeFacade

    facade = GarmentCodeFacade()
    if facade.available:
        converted, _ = facade.convert(state)
        return converted

    # Portable fallback for schema inspection before bootstrap. Acceptance tests
    # and production MCP use the native facade above.
    pattern_panels: dict[str, Any] = {}
    panel_names: dict[str, str] = {}
    for panel_id, panel in state.get("panels", {}).items():
        name = panel.get("alias") or panel_id
        panel_names[panel_id] = name
        pattern_panels[name] = {
            "translation": [value / 10.0 for value in panel.get("translation_mm", [0, 0, 0])],
            "rotation": panel.get("rotation_deg", [0, 0, 0]),
            "vertices": [[value / 10.0 for value in point] for point in panel["vertices_mm"]],
            "edges": [
                {
                    "endpoints": [edge["start"], edge["end"]],
                    **({"curvature": edge["curve"]} if edge.get("curve") else {}),
                    **({"label": edge["label"]} if edge.get("label") else {}),
                }
                for edge in panel.get("edges", [])
            ],
        }
    stitches = []
    interfaces = state.get("interfaces", {})
    for stitch in state.get("stitches", {}).values():
        sides = []
        for key in ("interface_a", "interface_b"):
            interface = interfaces[stitch[key]]
            sides.append(
                [
                    {"panel": panel_names[interface["panel_id"]], "edge": edge_index}
                    for edge_index in interface["edge_indices"]
                ]
            )
        stitches.extend([[left, right] for left, right in zip(*sides, strict=True)])
    return {
        "pattern": {"panels": pattern_panels, "stitches": stitches},
        "parameters": {},
        "parameter_order": [],
        "properties": {
            "units_in_meter": 100,
            "curvature_coords": "relative",
            "normalize_panel_translation": False,
            "normalized_edge_loops": True,
        },
    }


def thumbnail_svg(state: dict[str, Any], width: int = 640, height: int = 480) -> str:
    polygons = [panel.get("vertices_mm", []) for panel in state.get("panels", {}).values()]
    points = [point for polygon in polygons for point in polygon]
    if not points:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            '<rect width="100%" height="100%" fill="#f7f7f5"/></svg>'
        )
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    scale = min((width - 40) / max(max_x - min_x, 1), (height - 40) / max(max_y - min_y, 1))
    shapes = []
    for panel in state.get("panels", {}).values():
        coordinates = " ".join(
            f"{20 + (point[0] - min_x) * scale:.2f},{height - 20 - (point[1] - min_y) * scale:.2f}"
            for point in panel["vertices_mm"]
        )
        shapes.append(
            f'<polygon points="{coordinates}" fill="#dce9f7" stroke="#183153" stroke-width="2"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        '<rect width="100%" height="100%" fill="#f7f7f5"/>' + "".join(shapes) + "</svg>"
    )
