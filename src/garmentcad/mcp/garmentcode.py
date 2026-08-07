from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from garmentcad.catalog import GARMENTCODE_TOOLS
from garmentcad.mcp.common import add_core_tools, result_payload
from garmentcad.models import OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import execute_atomic, reference
from garmentcad.simulation import SimulationClient
from garmentcad.storage import read_json

mcp = FastMCP("garmentcode-cad")


def project_create(path: str, name: str | None = None) -> dict[str, Any]:
    """Create an empty transactional Garment Project."""
    return Project.create(path, name).status()


def changeset_discard(project_path: str, preview_token: str) -> dict[str, Any]:
    """Discard one immutable preview without changing project truth."""
    Project.open(project_path).discard(preview_token)
    return {"ok": True, "preview_token": preview_token}


def revision_revert(project_path: str, revision: int, author: str = "agent") -> dict[str, Any]:
    """Append a reverse revision from the stored preimage."""
    return result_payload(Project.open(project_path).revert(revision, author=author))


def simulation_submit(project_path: str, worker_url: str | None = None) -> dict[str, Any]:
    """Submit the current revision as a self-contained AutoDL bundle."""
    return SimulationClient(worker_url).submit(Project.open(project_path))


def simulation_status(job_id: str, worker_url: str | None = None) -> dict[str, Any]:
    """Poll an AutoDL simulation job."""
    return SimulationClient(worker_url).status(job_id)


def simulation_cancel(job_id: str, worker_url: str | None = None) -> dict[str, Any]:
    """Cancel a queued or running AutoDL simulation job."""
    return SimulationClient(worker_url).cancel(job_id)


def simulation_download(
    project_path: str, job_id: str, worker_url: str | None = None
) -> dict[str, Any]:
    """Download job results into the current revision's content-addressed artifacts."""
    resources = SimulationClient(worker_url).download(Project.open(project_path), job_id)
    return {"ok": True, "resources": resources}


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


def panel_delete(project_path: str, panel: str, commit: bool = False) -> dict[str, Any]:
    """Delete a panel and dependent interfaces/stitches."""
    return _run(project_path, "panel.delete", target=panel, commit=commit)


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


def panel_mirror(
    project_path: str,
    panel: str,
    alias: str,
    axis: str = "x",
    origin_mm: float = 0,
    commit: bool = False,
) -> dict[str, Any]:
    """Create a mirrored panel copy across x=origin or y=origin."""
    return _run(
        project_path,
        "panel.mirror",
        {"alias": alias, "axis": axis, "origin_mm": origin_mm},
        target=panel,
        commit=commit,
    )


def edge_split(
    project_path: str,
    panel: str,
    edge_index: int,
    fractions: list[float],
    commit: bool = False,
) -> dict[str, Any]:
    """Split an edge at normalized fractions strictly between zero and one."""
    return _run(
        project_path,
        "edge.split",
        {"panel": panel, "edge_index": edge_index, "fractions": fractions},
        commit=commit,
    )


def edge_extend(
    project_path: str,
    panel: str,
    edge_index: int,
    start_delta_mm: float = 0,
    end_delta_mm: float = 0,
    commit: bool = False,
) -> dict[str, Any]:
    """Extend or shorten both endpoints of a straight edge."""
    return _run(
        project_path,
        "edge.extend",
        {
            "panel": panel,
            "edge_index": edge_index,
            "start_delta_mm": start_delta_mm,
            "end_delta_mm": end_delta_mm,
        },
        commit=commit,
    )


def edge_chamfer(
    project_path: str,
    panel: str,
    vertex_index: int,
    distance_before_mm: float,
    distance_after_mm: float | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Replace one corner with a straight chamfer."""
    return _run(
        project_path,
        "edge.chamfer",
        {
            "panel": panel,
            "vertex_index": vertex_index,
            "distance_before_mm": distance_before_mm,
            "distance_after_mm": distance_after_mm or distance_before_mm,
        },
        commit=commit,
    )


def dart_insert(
    project_path: str,
    panel: str,
    edge_index: int,
    intake_mm: float,
    depth_mm: float,
    position: float = 0.5,
    commit: bool = False,
) -> dict[str, Any]:
    """Insert a cut dart into a straight boundary edge."""
    return _run(
        project_path,
        "dart.insert",
        {
            "panel": panel,
            "edge_index": edge_index,
            "intake_mm": intake_mm,
            "depth_mm": depth_mm,
            "position": position,
        },
        commit=commit,
    )


def component_define(
    project_path: str, alias: str, panels: list[str], commit: bool = False
) -> dict[str, Any]:
    """Group existing panels under one component alias."""
    return _run(
        project_path,
        "component.define",
        {"alias": alias, "panels": panels},
        commit=commit,
    )


def valentina_import_revision(
    project_path: str,
    snapshot_relative_path: str = "pattern/snapshot.json",
    sidecar_relative_path: str = "assembly/sewing-sidecar.json",
    commit: bool = False,
) -> dict[str, Any]:
    """Import a VCommandService snapshot and explicit sewing-semantics sidecar."""
    project = Project.open(project_path)

    def project_file(relative: str) -> dict[str, Any]:
        path = (project.root / relative).resolve()
        if project.root not in path.parents:
            raise ValueError("Import path must stay inside the project")
        value = read_json(path)
        if value is None:
            raise FileNotFoundError(path)
        return value

    return _run(
        project_path,
        "valentina.import",
        {
            "snapshot": project_file(snapshot_relative_path),
            "sidecar": project_file(sidecar_relative_path),
        },
        commit=commit,
    )


def interface_define(
    project_path: str,
    alias: str,
    panel: str,
    edge_indices: list[int],
    reverse: bool = False,
    ruffle: float = 1.0,
    right_wrong: bool = False,
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
            "ruffle": ruffle,
            "right_wrong": right_wrong,
        },
        commit=commit,
    )


def interface_delete(project_path: str, interface: str, commit: bool = False) -> dict[str, Any]:
    """Delete an interface and its dependent stitches."""
    return _run(project_path, "interface.delete", target=interface, commit=commit)


def stitch_create(
    project_path: str,
    alias: str,
    interface_a: str,
    interface_b: str,
    direction: str = "auto",
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
            "direction": direction,
        },
        commit=commit,
    )


def stitch_delete(project_path: str, stitch: str, commit: bool = False) -> dict[str, Any]:
    """Delete one stitch relation."""
    return _run(project_path, "stitch.delete", target=stitch, commit=commit)


def assembly_validate(project_path: str) -> dict[str, Any]:
    """Preview a no-op validation of the current assembly."""
    return _run(project_path, "validate")


LAZY_TOOLS = {
    "project_create": project_create,
    "changeset_discard": changeset_discard,
    "revision_revert": revision_revert,
    "simulation_submit": simulation_submit,
    "simulation_status": simulation_status,
    "simulation_cancel": simulation_cancel,
    "simulation_download": simulation_download,
    "panel_create": panel_create,
    "panel_delete": panel_delete,
    "panel_transform": panel_transform,
    "panel_mirror": panel_mirror,
    "edge_split": edge_split,
    "edge_extend": edge_extend,
    "edge_chamfer": edge_chamfer,
    "dart_insert": dart_insert,
    "component_define": component_define,
    "valentina_import_revision": valentina_import_revision,
    "interface_define": interface_define,
    "interface_delete": interface_delete,
    "stitch_create": stitch_create,
    "stitch_delete": stitch_delete,
    "assembly_validate": assembly_validate,
}


def load_tools(names: set[str]) -> None:
    for name in names:
        mcp.tool(name=name)(LAZY_TOOLS[name])


add_core_tools(mcp, GARMENTCODE_TOOLS, load_tools)


def main() -> None:
    mcp.run(transport="stdio")
