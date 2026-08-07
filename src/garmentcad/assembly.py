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
    summary = ChangeSummary()

    for operation in operations:
        try:
            _apply_one(state, operation, summary)
        except (KeyError, TypeError, ValueError) as error:
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
        summary.changed.append(ObjectRef(uuid=object_id, alias=panel.get("alias")))
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
            "reverse": bool(args.get("reverse", False)),
        }
        summary.created.append(ObjectRef(uuid=object_id, alias=alias))
    elif action == "interface.delete":
        object_id = _resolve(interfaces, operation.target)
        item = interfaces.pop(object_id)
        for key in list(stitches):
            if object_id in (stitches[key].get("interface_a"), stitches[key].get("interface_b")):
                stitches.pop(key)
        summary.deleted.append(ObjectRef(uuid=object_id, alias=item.get("alias")))
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
                    severity="error",
                    code="unmatched_interface_partition",
                    message=(
                        f"Stitch {stitch.get('alias', stitch_id)} has {len(side_a)} edges "
                        f"on one side and {len(side_b)} on the other"
                    ),
                )
            )
    return issues


def preview_assembly(
    project_root: Path, operations: list[Operation]
) -> tuple[dict[str, Any], ChangeSummary]:
    source = read_json(project_root / "assembly/assembly.json", default=empty_assembly())
    return apply_operations(source, operations)


def to_garmentcode(state: dict[str, Any]) -> dict[str, Any]:
    """Return GarmentCode-compatible JSON. Project millimetres become centimetres."""
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
                {key: value for key, value in edge.items() if key in {"start", "end", "curvature"}}
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
        "properties": {"units_in_meter": 100, "curvature_coords": "relative"},
    }
