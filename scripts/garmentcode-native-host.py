#!/usr/bin/env python3
"""JSON command host running inside the pinned GarmentCode compatibility environment."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from pygarment.garmentcode.component import Component
from pygarment.garmentcode.connector import StitchingRule
from pygarment.garmentcode.edge import CircleEdge, CurveEdge, Edge, EdgeSequence
from pygarment.garmentcode.edge_factory import CircleEdgeFactory
from pygarment.garmentcode.interface import Interface
from pygarment.garmentcode.panel import Panel
from pygarment.pattern.core import BasicPattern
from scipy.spatial.transform import Rotation


def _edge(panel: dict[str, Any], edge_data: dict[str, Any], vertices: list[list[float]]):
    start = vertices[int(edge_data["start"])]
    end = vertices[int(edge_data["end"])]
    label = str(edge_data.get("alias") or edge_data.get("label") or "")
    curvature = edge_data.get("curve") or edge_data.get("curvature")
    if not curvature:
        return Edge(start, end, label=label)
    kind = curvature.get("type")
    params = curvature.get("params", curvature.get("control_points", []))
    if kind == "circle":
        if "control_y" in curvature:
            return CircleEdge(start, end, cy=float(curvature["control_y"]), label=label)
        radius_mm, large_arc, right = params
        native = CircleEdgeFactory.from_points_radius(
            start,
            end,
            float(radius_mm) / 10.0,
            bool(large_arc),
            bool(right),
        )
        native.label = label
        return native
    if kind in {"quadratic", "cubic", "bezier"}:
        return CurveEdge(start, end, control_points=params, relative=True, label=label)
    raise ValueError(f"Unsupported edge curvature: {kind}")


def _build(assembly: dict[str, Any]):
    panels: dict[str, Panel] = {}
    panel_ids: dict[str, str] = {}
    edge_ids: dict[str, dict[str, Any]] = {}
    for panel_id, panel_data in assembly.get("panels", {}).items():
        name = str(panel_data.get("alias") or panel_id)
        if name in panels:
            raise ValueError(f"Duplicate panel alias: {name}")
        vertices = [[float(value) / 10.0 for value in point] for point in panel_data["vertices_mm"]]
        native = Panel(name, label=str(panel_data.get("label") or ""))
        native.edges = EdgeSequence(
            *[_edge(panel_data, item, vertices) for item in panel_data.get("edges", [])]
        )
        native.translation = np.asarray(
            [float(value) / 10.0 for value in panel_data.get("translation_mm", [0, 0, 0])]
        )
        native.rotation = Rotation.from_euler(
            "XYZ", panel_data.get("rotation_deg", [0, 0, 0]), degrees=True
        )
        panels[name] = native
        panel_ids[str(panel_id)] = name
        edge_ids[str(panel_id)] = {
            str(item["id"]): native.edges[index]
            for index, item in enumerate(panel_data.get("edges", []))
        }

    interfaces: dict[str, Interface] = {}
    interface_metrics: dict[str, Any] = {}
    for interface_id, item in assembly.get("interfaces", {}).items():
        panel_id = str(item["panel_id"])
        panel = panels[panel_ids[panel_id]]
        selected = []
        if item.get("edge_ids"):
            selected = [edge_ids[panel_id][str(edge_id)] for edge_id in item["edge_ids"]]
        else:
            selected = [panel.edges[int(index)] for index in item.get("edge_indices", [])]
        if not selected:
            raise ValueError(f"Interface {item.get('alias', interface_id)} has no edges")
        native = Interface(
            panel,
            EdgeSequence(*selected),
            ruffle=item.get("ruffle", 1.0),
            right_wrong=bool(item.get("right_wrong", False)),
        )
        if item.get("reverse"):
            native.reverse(with_edge_dir_reverse=True)
        interfaces[str(interface_id)] = native
        lengths_cm = native.projecting_lengths().tolist()
        interface_metrics[str(item.get("alias") or interface_id)] = {
            "edge_count": len(native),
            "projected_edge_lengths_mm": [value * 10.0 for value in lengths_cm],
            "projected_length_mm": sum(lengths_cm) * 10.0,
        }

    component = Component("garmentcad")
    component.subs = list(panels.values())
    stitch_metrics: dict[str, Any] = {}
    for stitch_id, item in assembly.get("stitches", {}).items():
        left = interfaces[str(item["interface_a"])]
        right = interfaces[str(item["interface_b"])]
        direction = item.get("direction", "auto")
        if direction == "opposed":
            right.flip_edges()
        elif direction not in {"auto", "same"}:
            raise ValueError(f"Unsupported stitch direction: {direction}")
        probe = StitchingRule(left, right)
        stitch_metrics[str(item.get("alias") or stitch_id)] = {
            "native_matching": probe.isMatching(),
            "edge_pairs": len(left),
            "direction": direction,
        }
        component.stitching_rules.rules.append(probe)

    panel_metrics = {
        name: {
            "edge_count": len(panel.edges),
            "closed": bool(panel.edges.isLoop()),
            "chained": bool(panel.edges.isChained()),
            "self_intersecting": bool(panel.is_self_intersecting()),
        }
        for name, panel in panels.items()
    }
    return component, {
        "panels": panel_metrics,
        "interfaces": interface_metrics,
        "stitches": stitch_metrics,
    }


def _convert(assembly: dict[str, Any]) -> dict[str, Any]:
    component, diagnostics = _build(assembly)
    pattern = component.assembly().pattern
    document = {
        "pattern": pattern,
        "parameters": {},
        "parameter_order": [],
        "properties": {
            "units_in_meter": 100,
            "curvature_coords": "relative",
            "normalize_panel_translation": False,
            "normalized_edge_loops": True,
        },
    }
    with tempfile.TemporaryDirectory(prefix="garmentcode-roundtrip-") as temporary:
        path = Path(temporary) / "pattern.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        reloaded = BasicPattern(str(path))
        roundtrip_panels = set(reloaded.pattern["panels"])
    diagnostics["roundtrip_ok"] = roundtrip_panels == set(pattern["panels"])
    diagnostics["native_classes"] = {
        "Panel": f"{Panel.__module__}.{Panel.__name__}",
        "Edge": f"{Edge.__module__}.{Edge.__name__}",
        "EdgeSequence": f"{EdgeSequence.__module__}.{EdgeSequence.__name__}",
        "Interface": f"{Interface.__module__}.{Interface.__name__}",
        "Component": f"{Component.__module__}.{Component.__name__}",
    }
    return {"garmentcode": document, "diagnostics": diagnostics}


def _mesh(assembly: dict[str, Any]) -> dict[str, Any]:
    component, diagnostics = _build(assembly)
    panels = []
    for panel in component.subs:
        boundary_cm: list[list[float]] = []
        for edge in panel.edges:
            segments = edge.linearize(n_verts_inside=0 if type(edge) is Edge else 9)
            for segment in segments:
                point = [float(value) for value in segment.start]
                if not boundary_cm or not np.allclose(boundary_cm[-1], point, atol=1e-9):
                    boundary_cm.append(point)
        if len(boundary_cm) > 1 and np.allclose(boundary_cm[0], boundary_cm[-1], atol=1e-9):
            boundary_cm.pop()
        vertices_3d_mm = [
            [float(value) * 10.0 for value in panel.point_to_3D(point)]
            for point in boundary_cm
        ]
        panels.append(
            {
                "name": panel.name,
                "boundary_2d_mm": [[value * 10.0 for value in point] for point in boundary_cm],
                "vertices_3d_mm": vertices_3d_mm,
            }
        )
    diagnostics["mesh_panels"] = len(panels)
    return {"panels": panels, "diagnostics": diagnostics}


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    if method == "service.info":
        return {
            "protocol_version": "1.0",
            "application": "GarmentCode",
            "units": {"public": "mm", "native": "cm"},
            "handlers": ["assembly.convert", "assembly.validate", "assembly.mesh"],
            "native_classes": ["Panel", "Edge", "EdgeSequence", "Interface", "Component"],
        }
    if method in {"assembly.convert", "assembly.validate"}:
        converted = _convert(request["assembly"])
        return (
            converted if method == "assembly.convert" else {"diagnostics": converted["diagnostics"]}
        )
    if method == "assembly.mesh":
        return _mesh(request["assembly"])
    raise ValueError(f"Unknown method: {method}")


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            response = dispatch(request)
        response["native_log"] = captured.getvalue()
        response["ok"] = True
        status = 0
    except Exception as error:
        response = {
            "ok": False,
            "error": {
                "code": "garmentcode_native_error",
                "message": str(error),
                "type": type(error).__name__,
            },
        }
        status = 1
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
