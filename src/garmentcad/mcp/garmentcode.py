from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from garmentcad.mcp.common import add_project_tools, result_payload
from garmentcad.models import OperationDomain
from garmentcad.sdk import execute_atomic, reference

mcp = FastMCP("garmentcode-cad")
add_project_tools(mcp, "garmentcode")


def _run(
    project_path: str,
    action: str,
    arguments: dict[str, Any] | None = None,
    *,
    target: str | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    return result_payload(
        execute_atomic(
            project_path,
            domain=OperationDomain.ASSEMBLY,
            action=action,
            arguments=arguments,
            target=target,
            commit=commit,
        )
    )


@mcp.tool()
def panel_create(
    project_path: str,
    alias: str,
    vertices_mm: list[list[float]],
    translation_mm: list[float] | None = None,
    rotation_deg: list[float] | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Create one polygonal sewing panel. Preview-only unless commit is true."""
    return _run(
        project_path,
        "panel.create",
        {
            "alias": alias,
            "vertices_mm": vertices_mm,
            "translation_mm": translation_mm or [0, 0, 0],
            "rotation_deg": rotation_deg or [0, 0, 0],
        },
        commit=commit,
    )


@mcp.tool()
def panel_delete(project_path: str, panel: str, commit: bool = False) -> dict[str, Any]:
    """Delete a panel and dependent interfaces/stitches."""
    return _run(project_path, "panel.delete", target=panel, commit=commit)


@mcp.tool()
def panel_transform(
    project_path: str,
    panel: str,
    translation_mm: list[float] | None = None,
    rotation_deg: list[float] | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Set the 3D placement of one panel."""
    arguments = {}
    if translation_mm is not None:
        arguments["translation_mm"] = translation_mm
    if rotation_deg is not None:
        arguments["rotation_deg"] = rotation_deg
    return _run(project_path, "panel.transform", arguments, target=panel, commit=commit)


@mcp.tool()
def interface_define(
    project_path: str,
    alias: str,
    panel: str,
    edge_indices: list[int],
    reverse: bool = False,
    commit: bool = False,
) -> dict[str, Any]:
    """Define an ordered sewing interface from edges of one panel."""
    panel_ref = reference(panel)
    return _run(
        project_path,
        "interface.define",
        {
            "alias": alias,
            "panel": panel_ref.model_dump(exclude_none=True) if panel_ref else {},
            "edge_indices": edge_indices,
            "reverse": reverse,
        },
        commit=commit,
    )


@mcp.tool()
def interface_delete(project_path: str, interface: str, commit: bool = False) -> dict[str, Any]:
    """Delete an interface and its dependent stitches."""
    return _run(project_path, "interface.delete", target=interface, commit=commit)


@mcp.tool()
def stitch_create(
    project_path: str,
    alias: str,
    interface_a: str,
    interface_b: str,
    commit: bool = False,
) -> dict[str, Any]:
    """Sew two interfaces; their edge partitions must currently match."""
    left = reference(interface_a)
    right = reference(interface_b)
    return _run(
        project_path,
        "stitch.create",
        {
            "alias": alias,
            "interface_a": left.model_dump(exclude_none=True) if left else {},
            "interface_b": right.model_dump(exclude_none=True) if right else {},
        },
        commit=commit,
    )


@mcp.tool()
def stitch_delete(project_path: str, stitch: str, commit: bool = False) -> dict[str, Any]:
    """Delete one stitch relation."""
    return _run(project_path, "stitch.delete", target=stitch, commit=commit)


@mcp.tool()
def assembly_validate(project_path: str) -> dict[str, Any]:
    """Preview a no-op validation of the current assembly."""
    return _run(project_path, "validate")


def main() -> None:
    mcp.run(transport="stdio")
