"""Persistent GarmentCode document used by garment-cad-mcp.

This module deliberately lives with the open-source CAD object model.  The
transaction/MCP layer may transport commands and bytes, but it must never
implement a second geometry kernel.
"""

from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from scipy.spatial.transform import Rotation

from pygarment.garmentcode.component import Component
from pygarment.garmentcode.connector import StitchingRule
from pygarment.garmentcode.edge import CircleEdge, CurveEdge, Edge, EdgeSequence
from pygarment.garmentcode.edge_factory import CircleEdgeFactory
from pygarment.garmentcode.interface import Interface
from pygarment.garmentcode.panel import Panel


def _uuid() -> str:
    return str(uuid4())


def empty_document() -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "engine": "GarmentCode",
        "units": "mm",
        "source_project_id": None,
        "source_revision": None,
        "source_pattern_hash": None,
        "panels": {},
        "interfaces": {},
        "stitches": {},
        "components": {},
        "native_pattern": None,
    }


class GarmentDocument:
    """Serializable owner of native GarmentCode sewing and placement state."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = copy.deepcopy(state or empty_document())
        if self.state.get("schema_version") != "2.0":
            raise ValueError("GarmentCode document schema must be 2.0")
        self.state.setdefault("panels", {})
        self.state.setdefault("interfaces", {})
        self.state.setdefault("stitches", {})
        self.state.setdefault("components", {})

    @classmethod
    def load(cls, path: str | Path) -> "GarmentDocument":
        import json

        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        import json

        self.compile()
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    @staticmethod
    def _ref(items: dict[str, Any], value: Any) -> str:
        if isinstance(value, str):
            if value in items:
                return value
            matches = [key for key, item in items.items() if item.get("alias") == value]
        else:
            value = value or {}
            if value.get("uuid") in items:
                return str(value["uuid"])
            matches = [
                key for key, item in items.items() if item.get("alias") == value.get("alias")
            ]
        if len(matches) != 1:
            raise ValueError(f"Object reference resolves to {len(matches)} objects: {value}")
        return matches[0]

    @staticmethod
    def _edge(edge_data: dict[str, Any], vertices_cm: list[list[float]]):
        start = vertices_cm[int(edge_data["start"])]
        end = vertices_cm[int(edge_data["end"])]
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
                start, end, float(radius_mm) / 10.0, bool(large_arc), bool(right)
            )
            native.label = label
            return native
        if kind in {"quadratic", "cubic", "bezier"}:
            return CurveEdge(start, end, control_points=params, relative=True, label=label)
        raise ValueError(f"Unsupported edge curvature: {kind}")

    def _build(self) -> tuple[Component, dict[str, Panel], dict[str, Interface], dict[str, Any]]:
        panels: dict[str, Panel] = {}
        panels_by_id: dict[str, Panel] = {}
        edge_objects: dict[str, dict[str, Any]] = {}
        diagnostics: dict[str, Any] = {"panels": {}, "interfaces": {}, "stitches": {}}

        for panel_id, raw in self.state["panels"].items():
            alias = str(raw.get("alias") or panel_id)
            if alias in panels:
                raise ValueError(f"Duplicate panel alias: {alias}")
            vertices_cm = [
                [float(coordinate) / 10.0 for coordinate in point]
                for point in raw["vertices_mm"]
            ]
            panel = Panel(alias, label=str(raw.get("label") or ""))
            panel.edges = EdgeSequence(
                *[self._edge(edge, vertices_cm) for edge in raw.get("edges", [])]
            )
            panel.translation = np.asarray(
                [float(value) / 10.0 for value in raw.get("translation_mm", [0, 0, 0])]
            )
            panel.rotation = Rotation.from_euler(
                "XYZ", raw.get("rotation_deg", [0, 0, 0]), degrees=True
            )
            panels[alias] = panel
            panels_by_id[str(panel_id)] = panel
            edge_objects[str(panel_id)] = {
                str(edge["id"]): panel.edges[index]
                for index, edge in enumerate(raw.get("edges", []))
            }

        interfaces: dict[str, Interface] = {}
        for interface_id, raw in self.state["interfaces"].items():
            panel_id = str(raw["panel_id"])
            panel = panels_by_id[panel_id]
            if raw.get("edge_ids"):
                selected = [edge_objects[panel_id][str(edge)] for edge in raw["edge_ids"]]
            else:
                selected = [panel.edges[int(index)] for index in raw.get("edge_indices", [])]
            if not selected:
                raise ValueError(f"Interface {raw.get('alias', interface_id)} has no edges")
            native = Interface(
                panel,
                EdgeSequence(*selected),
                ruffle=float(raw.get("ruffle", 1.0)),
                right_wrong=bool(raw.get("right_wrong", False)),
            )
            if raw.get("reverse_order"):
                native.reverse()
            if raw.get("flip_edges"):
                native.flip_edges()
            interfaces[str(interface_id)] = native
            lengths = native.projecting_lengths().tolist()
            diagnostics["interfaces"][str(raw.get("alias") or interface_id)] = {
                "edge_count": len(native),
                "projected_edge_lengths_mm": [value * 10.0 for value in lengths],
                "projected_length_mm": sum(lengths) * 10.0,
            }

        root = Component("garmentcad")
        root.subs = list(panels.values())
        for stitch_id, raw in self.state["stitches"].items():
            left = interfaces[str(raw["interface_a"])]
            right = interfaces[str(raw["interface_b"])]
            direction = raw.get("direction", "auto")
            if direction == "opposed":
                right.flip_edges()
            elif direction not in {"auto", "same"}:
                raise ValueError(f"Unsupported stitch direction: {direction}")
            left_length = sum(left.projecting_lengths().tolist()) * 10.0
            right_length = sum(right.projecting_lengths().tolist()) * 10.0
            rule = StitchingRule(left, right)
            root.stitching_rules.rules.append(rule)
            diagnostics["stitches"][str(raw.get("alias") or stitch_id)] = {
                "native_matching": rule.isMatching(),
                "edge_pairs": len(left),
                "direction": direction,
                "side_lengths_mm": [left_length, right_length],
                "length_difference_mm": abs(left_length - right_length),
            }

        diagnostics["panels"] = {
            name: {
                "edge_count": len(panel.edges),
                "closed": bool(panel.edges.isLoop()),
                "chained": bool(panel.edges.isChained()),
                "self_intersecting": bool(panel.is_self_intersecting()),
            }
            for name, panel in panels.items()
        }
        return root, panels_by_id, interfaces, diagnostics

    def compile(self) -> dict[str, Any]:
        root, _, _, diagnostics = self._build()
        pattern = root.assembly().pattern
        self.state["native_pattern"] = {
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
        return diagnostics

    def sync_from_valentina(
        self,
        snapshot: dict[str, Any],
        *,
        source_project_id: str,
        source_pattern_hash: str,
        bindings: dict[str, Any] | None = None,
    ) -> None:
        previous = self.state
        state = empty_document()
        state["source_project_id"] = source_project_id
        state["source_revision"] = snapshot.get("revision")
        state["source_pattern_hash"] = source_pattern_hash
        edge_aliases: dict[str, list[tuple[str, str]]] = {}
        old_panels = {item.get("alias"): item for item in previous.get("panels", {}).values()}
        old_edge_aliases = {
            str(edge["id"]): str(edge.get("alias") or "")
            for panel in previous.get("panels", {}).values()
            for edge in panel.get("edges", [])
        }
        for piece in snapshot.get("pieces", []):
            panel_id = str(piece["uuid"])
            contour = piece["contour"]
            old = old_panels.get(piece["alias"], {})
            edges = []
            for index, node in enumerate(contour):
                edge_id = str(node["edge_uuid"])
                edge_alias = str(node["edge_alias"])
                edges.append(
                    {
                        "id": edge_id,
                        "start": index,
                        "end": (index + 1) % len(contour),
                        "alias": edge_alias,
                        "curve": node.get("curve"),
                    }
                )
                edge_aliases.setdefault(edge_alias, []).append((panel_id, edge_id))
            state["panels"][panel_id] = {
                "id": panel_id,
                "alias": piece["alias"],
                "vertices_mm": [[node["x_mm"], node["y_mm"]] for node in contour],
                "edges": edges,
                "translation_mm": old.get("translation_mm", [0, 0, 0]),
                "rotation_deg": old.get("rotation_deg", [0, 0, 0]),
                "seam_allowance_mm": piece.get("seam_allowance_mm"),
            }
        for interface_id, raw in previous.get("interfaces", {}).items():
            aliases = list(
                dict.fromkeys(
                    old_edge_aliases.get(str(edge_id), "")
                    for edge_id in raw.get("edge_ids", [])
                )
            )
            if not aliases or any(alias not in edge_aliases for alias in aliases):
                continue
            resolved = [item for alias in aliases for item in edge_aliases[alias]]
            if len({panel_id for panel_id, _ in resolved}) != 1:
                continue
            state["interfaces"][interface_id] = {
                **copy.deepcopy(raw),
                "panel_id": resolved[0][0],
                "edge_ids": [edge_id for _, edge_id in resolved],
            }
        for stitch_id, raw in previous.get("stitches", {}).items():
            if raw.get("interface_a") in state["interfaces"] and raw.get(
                "interface_b"
            ) in state["interfaces"]:
                state["stitches"][stitch_id] = copy.deepcopy(raw)
        new_panel_ids = {
            panel.get("alias"): panel_id for panel_id, panel in state["panels"].items()
        }
        for alias, members in previous.get("components", {}).items():
            old_aliases = [
                previous["panels"][panel_id].get("alias")
                for panel_id in members
                if panel_id in previous.get("panels", {})
            ]
            if old_aliases and all(name in new_panel_ids for name in old_aliases):
                state["components"][alias] = [new_panel_ids[name] for name in old_aliases]
        self.state = state
        self._apply_bindings(bindings or {}, edge_aliases)

    def _apply_bindings(
        self, bindings: dict[str, Any], edge_aliases: dict[str, list[tuple[str, str]]]
    ) -> None:
        interfaces_by_alias: dict[str, str] = {}
        for raw in bindings.get("interfaces", []):
            resolved = [
                item for alias in raw["edges"] for item in edge_aliases[str(alias)]
            ]
            panels = {panel_id for panel_id, _ in resolved}
            if len(panels) != 1:
                raise ValueError(f"Interface {raw['alias']} spans multiple panels")
            interface_id = str(raw.get("uuid") or _uuid())
            panel_id = resolved[0][0]
            self.state["interfaces"][interface_id] = {
                "id": interface_id,
                "alias": raw["alias"],
                "panel_id": panel_id,
                "edge_ids": [edge_id for _, edge_id in resolved],
                "reverse_order": bool(raw.get("reverse", False)),
                "flip_edges": bool(raw.get("reverse", False)),
                "ruffle": float(raw.get("ruffle", 1.0)),
                "right_wrong": bool(raw.get("right_wrong", False)),
            }
            interfaces_by_alias[raw["alias"]] = interface_id
        for raw in bindings.get("stitches", []):
            stitch_id = str(raw.get("uuid") or _uuid())
            self.state["stitches"][stitch_id] = {
                "id": stitch_id,
                "alias": raw["alias"],
                "interface_a": interfaces_by_alias[raw["interface_a"]],
                "interface_b": interfaces_by_alias[raw["interface_b"]],
                "direction": raw.get("direction", "auto"),
            }

    def apply(self, operation: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
        action = str(operation["action"])
        arguments = operation.get("arguments") or {}
        target = operation.get("target")
        summary = {"created": [], "changed": [], "deleted": []}
        panels = self.state["panels"]
        interfaces = self.state["interfaces"]
        stitches = self.state["stitches"]

        if action == "panel.transform":
            panel_id = self._ref(panels, target)
            _, native_panels, _, _ = self._build()
            panel = native_panels[panel_id]
            if "translation_mm" in arguments:
                panel.translate_to(np.asarray(arguments["translation_mm"], dtype=float) / 10.0)
            if "translation_delta_mm" in arguments:
                panel.translate_by(np.asarray(arguments["translation_delta_mm"], dtype=float) / 10.0)
            if "rotation_deg" in arguments:
                panel.rotate_to(Rotation.from_euler("XYZ", arguments["rotation_deg"], degrees=True))
            if "rotation_delta_deg" in arguments:
                panel.rotate_by(
                    Rotation.from_euler("XYZ", arguments["rotation_delta_deg"], degrees=True)
                )
            if arguments.get("center_x"):
                panel.center_x()
            panels[panel_id]["translation_mm"] = (panel.translation * 10.0).tolist()
            panels[panel_id]["rotation_deg"] = panel.rotation.as_euler(
                "XYZ", degrees=True
            ).tolist()
            summary["changed"].append({"uuid": panel_id, "alias": panels[panel_id]["alias"]})
        elif action == "component.define":
            alias = str(arguments["alias"])
            self.state["components"][alias] = [self._ref(panels, value) for value in arguments["panels"]]
            summary["created"].append({"alias": alias})
        elif action == "component.transform":
            alias = str(arguments["component"])
            panel_ids = self.state["components"].get(alias)
            if panel_ids is None:
                raise ValueError(f"Component not found: {alias}")
            _, native_panels, _, _ = self._build()
            component = Component(alias)
            component.subs = [native_panels[panel_id] for panel_id in panel_ids]
            if "translation_mm" in arguments:
                component.translate_to(
                    np.asarray(arguments["translation_mm"], dtype=float) / 10.0
                )
            if "translation_delta_mm" in arguments:
                component.translate_by(
                    np.asarray(arguments["translation_delta_mm"], dtype=float) / 10.0
                )
            if "rotation_delta_deg" in arguments:
                component.rotate_by(
                    Rotation.from_euler("XYZ", arguments["rotation_delta_deg"], degrees=True)
                )
            for panel_id in panel_ids:
                panel = native_panels[panel_id]
                panels[panel_id]["translation_mm"] = (panel.translation * 10.0).tolist()
                panels[panel_id]["rotation_deg"] = panel.rotation.as_euler(
                    "XYZ", degrees=True
                ).tolist()
                summary["changed"].append(
                    {"uuid": panel_id, "alias": panels[panel_id]["alias"]}
                )
        elif action == "interface.define":
            interface_id = str(arguments.get("uuid") or _uuid())
            panel_id = self._ref(panels, arguments["panel"])
            edge_indices = [int(value) for value in arguments["edge_indices"]]
            panel_edges = panels[panel_id]["edges"]
            interfaces[interface_id] = {
                "id": interface_id,
                "alias": str(arguments["alias"]),
                "panel_id": panel_id,
                "edge_ids": [panel_edges[index]["id"] for index in edge_indices],
                "reverse_order": bool(arguments.get("reverse", False)),
                "flip_edges": bool(arguments.get("reverse", False)),
                "ruffle": float(arguments.get("ruffle", 1.0)),
                "right_wrong": bool(arguments.get("right_wrong", False)),
            }
            summary["created"].append(
                {"uuid": interface_id, "alias": interfaces[interface_id]["alias"]}
            )
        elif action == "interface.update":
            interface_id = self._ref(interfaces, target)
            item = interfaces[interface_id]
            if "edge_indices" in arguments:
                panel_edges = panels[item["panel_id"]]["edges"]
                item["edge_ids"] = [panel_edges[int(index)]["id"] for index in arguments["edge_indices"]]
            if arguments.get("reverse_order"):
                item["reverse_order"] = not item.get("reverse_order", False)
            if arguments.get("flip_edges"):
                item["flip_edges"] = not item.get("flip_edges", False)
            for key in ("right_wrong", "ruffle"):
                if key in arguments:
                    item[key] = arguments[key]
            summary["changed"].append({"uuid": interface_id, "alias": item["alias"]})
        elif action == "interface.delete":
            interface_id = self._ref(interfaces, target)
            item = interfaces.pop(interface_id)
            for stitch_id in list(stitches):
                if interface_id in {
                    stitches[stitch_id]["interface_a"],
                    stitches[stitch_id]["interface_b"],
                }:
                    stitches.pop(stitch_id)
            summary["deleted"].append({"uuid": interface_id, "alias": item["alias"]})
        elif action == "stitch.create":
            stitch_id = str(arguments.get("uuid") or _uuid())
            stitches[stitch_id] = {
                "id": stitch_id,
                "alias": str(arguments["alias"]),
                "interface_a": self._ref(interfaces, arguments["interface_a"]),
                "interface_b": self._ref(interfaces, arguments["interface_b"]),
                "direction": arguments.get("direction", "auto"),
            }
            summary["created"].append({"uuid": stitch_id, "alias": stitches[stitch_id]["alias"]})
        elif action == "stitch.update":
            stitch_id = self._ref(stitches, target)
            item = stitches[stitch_id]
            for key in ("interface_a", "interface_b"):
                if key in arguments:
                    item[key] = self._ref(interfaces, arguments[key])
            if "direction" in arguments:
                item["direction"] = arguments["direction"]
            summary["changed"].append({"uuid": stitch_id, "alias": item["alias"]})
        elif action == "stitch.delete":
            stitch_id = self._ref(stitches, target)
            item = stitches.pop(stitch_id)
            summary["deleted"].append({"uuid": stitch_id, "alias": item["alias"]})
        elif action == "validate":
            pass
        else:
            raise ValueError(f"Unsupported native GarmentDocument action: {action}")
        self.compile()
        return summary

    def diagnostics(self) -> dict[str, Any]:
        return self.compile()

    @staticmethod
    def _cross(a: list[float], b: list[float], c: list[float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    @classmethod
    def _triangulate(cls, points: list[list[float]]) -> list[tuple[int, int, int]]:
        """Triangulate a native linearized panel boundary for interchange export."""
        if len(points) < 3:
            raise ValueError("A mesh panel needs at least three boundary points")
        area = sum(
            point[0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * point[1]
            for index, point in enumerate(points)
        )
        if math.isclose(area, 0.0, abs_tol=1e-9):
            raise ValueError("Cannot triangulate a zero-area panel")
        orientation = 1.0 if area > 0 else -1.0
        remaining = list(range(len(points)))
        faces: list[tuple[int, int, int]] = []
        while len(remaining) > 3:
            ear: tuple[int, int, int, int] | None = None
            for offset, current in enumerate(remaining):
                previous = remaining[offset - 1]
                following = remaining[(offset + 1) % len(remaining)]
                if orientation * cls._cross(
                    points[previous], points[current], points[following]
                ) <= 1e-9:
                    continue
                if any(
                    candidate not in {previous, current, following}
                    and all(
                        orientation * value >= -1e-9
                        for value in (
                            cls._cross(points[previous], points[current], points[candidate]),
                            cls._cross(points[current], points[following], points[candidate]),
                            cls._cross(points[following], points[previous], points[candidate]),
                        )
                    )
                    for candidate in remaining
                ):
                    continue
                ear = offset, previous, current, following
                break
            if ear is None:
                raise ValueError("Native panel boundary is not a triangulatable simple polygon")
            offset, previous, current, following = ear
            faces.append((previous, current, following))
            remaining.pop(offset)
        faces.append(tuple(remaining))
        return faces

    def _native_meshes(self) -> list[dict[str, Any]]:
        root, _, _, _ = self._build()
        meshes: list[dict[str, Any]] = []
        for panel in root.subs:
            boundary_cm: list[list[float]] = []
            for edge in panel.edges:
                segments = edge.linearize(n_verts_inside=0 if type(edge) is Edge else 9)
                for segment in segments:
                    point = [float(value) for value in segment.start]
                    if not boundary_cm or not np.allclose(boundary_cm[-1], point, atol=1e-9):
                        boundary_cm.append(point)
            if len(boundary_cm) > 1 and np.allclose(
                boundary_cm[0], boundary_cm[-1], atol=1e-9
            ):
                boundary_cm.pop()
            meshes.append(
                {
                    "name": panel.name,
                    "vertices_3d_mm": [
                        [float(value) * 10.0 for value in panel.point_to_3D(point)]
                        for point in boundary_cm
                    ],
                    "faces": self._triangulate(boundary_cm),
                }
            )
        return meshes

    @staticmethod
    def _usd_identifier(value: str) -> str:
        identifier = re.sub(r"[^A-Za-z0-9_]", "_", value)
        return identifier if identifier and not identifier[0].isdigit() else f"panel_{identifier}"

    def export(self, output_directory: str | Path, formats: list[str]) -> dict[str, Path]:
        """Export derivatives from reconstructed native objects, never from a transport kernel."""
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        requested = list(dict.fromkeys(formats))
        unsupported = sorted(set(requested) - {"json", "obj", "usd"})
        if unsupported:
            raise ValueError(f"Unsupported GarmentCode export formats: {unsupported}")
        paths: dict[str, Path] = {}
        if "json" in requested:
            self.compile()
            path = output / "garmentcode.json"
            import json

            path.write_text(
                json.dumps(self.state["native_pattern"], ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            paths["json"] = path
        if set(requested) & {"obj", "usd"}:
            meshes = self._native_meshes()
            if "obj" in requested:
                lines = ["# GarmentCode native reconstruction", "# units: millimetres"]
                vertex_offset = 1
                for panel in meshes:
                    lines.append(f"o {panel['name']}")
                    lines.extend(
                        "v " + " ".join(f"{value:.9g}" for value in point)
                        for point in panel["vertices_3d_mm"]
                    )
                    lines.extend(
                        "f " + " ".join(str(vertex_offset + index) for index in face)
                        for face in panel["faces"]
                    )
                    vertex_offset += len(panel["vertices_3d_mm"])
                path = output / "garmentcode.obj"
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                paths["obj"] = path
            if "usd" in requested:
                lines = ["#usda 1.0", "(", "    metersPerUnit = 0.001", '    upAxis = "Y"', ")", ""]
                for panel in meshes:
                    points = ", ".join(
                        "(" + ", ".join(f"{value:.9g}" for value in point) + ")"
                        for point in panel["vertices_3d_mm"]
                    )
                    indices = ", ".join(str(index) for face in panel["faces"] for index in face)
                    counts = ", ".join("3" for _ in panel["faces"])
                    lines.extend(
                        [
                            f'def Mesh "{self._usd_identifier(panel["name"])}"',
                            "{",
                            f"    point3f[] points = [{points}]",
                            f"    int[] faceVertexCounts = [{counts}]",
                            f"    int[] faceVertexIndices = [{indices}]",
                            '    uniform token subdivisionScheme = "none"',
                            "}",
                            "",
                        ]
                    )
                path = output / "garmentcode.usda"
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                paths["usd"] = path
        return paths
