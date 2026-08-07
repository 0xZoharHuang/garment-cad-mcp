from __future__ import annotations

from typing import Any
from uuid import uuid4

from garmentcad.assembly import empty_assembly
from garmentcad.models import SewingSidecar


def snapshot_to_assembly(
    snapshot: dict[str, Any], sidecar: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Convert the native VCommandService snapshot contract without reading `.val` XML."""
    assembly = empty_assembly()
    assembly["source_revision"] = snapshot.get("revision")
    edge_aliases: dict[str, tuple[str, str]] = {}
    for piece in snapshot.get("pieces", []):
        panel_id = str(piece.get("uuid") or uuid4())
        alias = str(piece["alias"])
        contour = piece["contour"]
        vertices = [[float(node["x_mm"]), float(node["y_mm"])] for node in contour]
        edges = []
        for index, node in enumerate(contour):
            edge_id = str(node.get("edge_uuid") or uuid4())
            edge_alias = node.get("edge_alias")
            edge = {
                "id": edge_id,
                "start": index,
                "end": (index + 1) % len(vertices),
                "curve": node.get("curve"),
                "alias": edge_alias,
                "label": node.get("label"),
            }
            edges.append(edge)
            if edge_alias:
                edge_aliases[str(edge_alias)] = (panel_id, edge_id)
        assembly["panels"][panel_id] = {
            "id": panel_id,
            "alias": alias,
            "vertices_mm": vertices,
            "edges": edges,
            "translation_mm": piece.get("translation_mm", [0, 0, 0]),
            "rotation_deg": piece.get("rotation_deg", [0, 0, 0]),
            "grainline_deg": piece.get("grainline_deg"),
            "seam_allowance_mm": piece.get("seam_allowance_mm"),
        }
    validated_sidecar = SewingSidecar.model_validate(sidecar or {}).model_dump(
        mode="json", exclude_none=True
    )
    _apply_sidecar(assembly, validated_sidecar, edge_aliases)
    return assembly


def _apply_sidecar(
    assembly: dict[str, Any],
    sidecar: dict[str, Any],
    edge_aliases: dict[str, tuple[str, str]],
) -> None:
    interface_by_alias: dict[str, str] = {}
    for item in sidecar.get("interfaces", []):
        resolved = [edge_aliases[alias] for alias in item["edges"]]
        panel_ids = {panel_id for panel_id, _ in resolved}
        if len(panel_ids) != 1:
            raise ValueError(f"Interface {item['alias']} spans multiple panels")
        panel_id = resolved[0][0]
        edge_ids = [edge_id for _, edge_id in resolved]
        panel = assembly["panels"][panel_id]
        by_id = {edge["id"]: index for index, edge in enumerate(panel["edges"])}
        interface_id = str(item.get("uuid") or uuid4())
        assembly["interfaces"][interface_id] = {
            "id": interface_id,
            "alias": item["alias"],
            "panel_id": panel_id,
            "edge_ids": edge_ids,
            "edge_indices": [by_id[edge_id] for edge_id in edge_ids],
            "reverse": bool(item.get("reverse", False)),
            "ruffle": float(item.get("ruffle", 1.0)),
            "right_wrong": bool(item.get("right_wrong", False)),
        }
        interface_by_alias[item["alias"]] = interface_id
    for item in sidecar.get("stitches", []):
        stitch_id = str(item.get("uuid") or uuid4())
        assembly["stitches"][stitch_id] = {
            "id": stitch_id,
            "alias": item["alias"],
            "interface_a": interface_by_alias[item["interface_a"]],
            "interface_b": interface_by_alias[item["interface_b"]],
            "direction": item.get("direction", "auto"),
        }
