from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from garmentcad.catalog import GARMENTCODE_TOOLS
from garmentcad.mcp.common import PREVIEW_WRITE, add_core_tools, register_atomic, result_payload
from garmentcad.models import OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import GarmentSDK, execute_atomic
from garmentcad.simulation import SimulationClient

mcp = FastMCP("garmentcode-cad")


def simulation_submit(project_path: str, worker_url: str | None = None) -> dict[str, Any]:
    """Submit the current native GarmentCode document as a self-contained GPU bundle."""
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
    """Download immutable GPU results into the project artifact store."""
    resources = SimulationClient(worker_url).download(Project.open(project_path), job_id)
    return {"ok": True, "resources": resources}


def garmentcode_export(project_path: str, formats: list[str] | None = None) -> dict[str, Any]:
    """Export JSON/OBJ/USD from the native GarmentCode truth document."""
    from garmentcad.exports import export_garmentcode

    return export_garmentcode(project_path, formats)


def assembly_sync_from_pattern(
    project_path: str,
    bindings: dict[str, Any] | None = None,
    message: str = "",
    author: str = "agent",
) -> dict[str, Any]:
    """Preview a native GarmentCode projection of current Valentina truth."""
    return result_payload(
        GarmentSDK(project_path).sync_assembly_from_pattern(
            bindings=bindings,
            message=message,
            author=author,
        )
    )


def simulation_configure(
    project_path: str,
    body_mesh: str,
    body_measurements: str,
    body_segmentation: str,
    fabric: str,
    simulation_config: str,
    camera_config: str,
) -> dict[str, Any]:
    """Preview the complete body, fabric, simulation, and camera input selection."""
    return result_payload(
        execute_atomic(
            project_path,
            domain=OperationDomain.SIMULATION,
            action="simulation.configure",
            arguments={
                "body_mesh": body_mesh,
                "body_measurements": body_measurements,
                "body_segmentation": body_segmentation,
                "fabric": fabric,
                "simulation_config": simulation_config,
                "camera_config": camera_config,
            },
        )
    )


SPECIAL: dict[str, Any] = {
    "assembly_sync_from_pattern": assembly_sync_from_pattern,
    "garmentcode_export": garmentcode_export,
    "simulation_submit": simulation_submit,
    "simulation_configure": simulation_configure,
    "simulation_status": simulation_status,
    "simulation_cancel": simulation_cancel,
    "simulation_download": simulation_download,
}


def load_tools(names: set[str]) -> None:
    for spec in GARMENTCODE_TOOLS:
        if spec.name not in names or mcp._tool_manager.get_tool(spec.name) is not None:
            continue
        if implementation := SPECIAL.get(spec.name):
            mcp.tool(name=spec.name, annotations=PREVIEW_WRITE)(implementation)
            continue
        domain = (
            OperationDomain.SIMULATION
            if spec.action.startswith("simulation.")
            else OperationDomain.ASSEMBLY
        )
        register_atomic(mcp, spec, domain)


add_core_tools(mcp, GARMENTCODE_TOOLS, load_tools)
if os.environ.get("GARMENTCAD_MCP_TOOL_MODE", "lazy").lower() == "eager":
    load_tools({spec.name for spec in GARMENTCODE_TOOLS})


def main() -> None:
    mcp.run(transport="stdio")
