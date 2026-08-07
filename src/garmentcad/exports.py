from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from garmentcad.artifacts import ArtifactStore
from garmentcad.garmentcode_facade import GarmentCodeFacade
from garmentcad.project import Project
from garmentcad.storage import canonical_json, read_json

SUPPORTED_GARMENTCODE_EXPORTS = {"json", "obj", "usd"}


def _cross(a: list[float], b: list[float], c: list[float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_triangle(
    point: list[float], a: list[float], b: list[float], c: list[float], orientation: float
) -> bool:
    epsilon = 1e-9
    return all(
        orientation * value >= -epsilon
        for value in (_cross(a, b, point), _cross(b, c, point), _cross(c, a, point))
    )


def triangulate_polygon(points: list[list[float]]) -> list[tuple[int, int, int]]:
    """Triangulate one non-self-intersecting simple polygon, preserving input indices."""
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
        ear = None
        for offset, current in enumerate(remaining):
            previous = remaining[offset - 1]
            following = remaining[(offset + 1) % len(remaining)]
            if orientation * _cross(points[previous], points[current], points[following]) <= 1e-9:
                continue
            if any(
                candidate not in {previous, current, following}
                and _point_in_triangle(
                    points[candidate],
                    points[previous],
                    points[current],
                    points[following],
                    orientation,
                )
                for candidate in remaining
            ):
                continue
            ear = (offset, previous, current, following)
            break
        if ear is None:
            raise ValueError("Panel is not a triangulatable simple polygon")
        offset, previous, current, following = ear
        faces.append((previous, current, following))
        remaining.pop(offset)
    faces.append(tuple(remaining))
    return faces


def _mesh_data(assembly: dict[str, Any]) -> list[dict[str, Any]]:
    panels, _ = GarmentCodeFacade().mesh(assembly)
    for panel in panels:
        panel["faces"] = triangulate_polygon(panel["boundary_2d_mm"])
    return panels


def _obj(panels: list[dict[str, Any]]) -> bytes:
    lines = ["# garment-cad-mcp GarmentCode mesh", "# units: millimetres"]
    vertex_offset = 1
    for panel in panels:
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
    return ("\n".join(lines) + "\n").encode()


def _usd_identifier(value: str) -> str:
    identifier = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not identifier or identifier[0].isdigit():
        identifier = f"panel_{identifier}"
    return identifier


def _usda(panels: list[dict[str, Any]]) -> bytes:
    lines = ["#usda 1.0", "(", "    metersPerUnit = 0.001", '    upAxis = "Y"', ")", ""]
    for panel in panels:
        points = ", ".join(
            "(" + ", ".join(f"{value:.9g}" for value in point) + ")"
            for point in panel["vertices_3d_mm"]
        )
        indices = ", ".join(str(index) for face in panel["faces"] for index in face)
        counts = ", ".join("3" for _ in panel["faces"])
        lines.extend(
            [
                f'def Mesh "{_usd_identifier(panel["name"])}"',
                "{",
                f"    point3f[] points = [{points}]",
                f"    int[] faceVertexCounts = [{counts}]",
                f"    int[] faceVertexIndices = [{indices}]",
                '    uniform token subdivisionScheme = "none"',
                "}",
                "",
            ]
        )
    return ("\n".join(lines) + "\n").encode()


def export_garmentcode(
    project: Project | str | Path, formats: list[str] | None = None
) -> dict[str, Any]:
    project = project if isinstance(project, Project) else Project.open(project)
    requested = list(dict.fromkeys(formats or ["json", "obj", "usd"]))
    unsupported = sorted(set(requested) - SUPPORTED_GARMENTCODE_EXPORTS)
    if unsupported:
        raise ValueError(f"Unsupported GarmentCode export formats: {unsupported}")
    assembly = read_json(project.root / "assembly/assembly.json")
    if assembly is None:
        raise FileNotFoundError("assembly/assembly.json")
    facade = GarmentCodeFacade()
    native, diagnostics = facade.convert(assembly)
    meshes = _mesh_data(assembly) if set(requested) & {"obj", "usd"} else []
    payloads = {
        "json": ("garmentcode.json", canonical_json(native)),
        "obj": ("garmentcode.obj", _obj(meshes)),
        "usd": ("garmentcode.usda", _usda(meshes)),
    }
    store = ArtifactStore(project.root)
    resources = {}
    for format_name in requested:
        filename, payload = payloads[format_name]
        resources[format_name] = store.put(
            payload,
            filename=filename,
            kind="garmentcode_export",
            revision=project.current_revision,
            metadata={
                "project_id": project.manifest.project_id,
                "source_revision": assembly.get("source_revision"),
                "format": format_name,
                "native_roundtrip_ok": diagnostics.get("roundtrip_ok", False),
            },
        )
    return {
        "ok": True,
        "revision": project.current_revision,
        "resources": resources,
        "diagnostics": diagnostics,
    }
