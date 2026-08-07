from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from garmentcad.catalog import ToolSpec, catalog_payload
from garmentcad.models import OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import execute_atomic
from garmentcad.simulation import SimulationClient


def result_payload(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def add_project_tools(server: FastMCP, kind: str) -> None:
    @server.tool(name="project_create")
    def project_create(path: str, name: str | None = None) -> dict[str, Any]:
        """Create an empty transactional garment project directory."""
        return Project.create(path, name).status()

    @server.tool(name="project_status")
    def project_status(path: str) -> dict[str, Any]:
        """Read project identity, revision, hash, and pending-operation count."""
        return Project.open(path).status()

    @server.tool(name="project_commit")
    def project_commit(path: str, preview_token: str) -> dict[str, Any]:
        """Commit one preview if its base revision is still current."""
        return result_payload(Project.open(path).commit(preview_token))

    @server.tool(name="project_discard")
    def project_discard(path: str, preview_token: str) -> dict[str, Any]:
        """Discard one uncommitted preview."""
        Project.open(path).discard(preview_token)
        return {"ok": True, "preview_token": preview_token}

    @server.tool(name="project_revert")
    def project_revert(path: str, revision: int, author: str = "agent") -> dict[str, Any]:
        """Reverse one committed revision by creating a new append-only revision."""
        return result_payload(Project.open(path).revert(revision, author=author))

    @server.tool(name="simulation_submit")
    def simulation_submit(path: str, worker_url: str | None = None) -> dict[str, Any]:
        """Upload the current revision to the configured GPU simulation worker."""
        return SimulationClient(worker_url).submit(Project.open(path))

    @server.tool(name="simulation_status")
    def simulation_status(job_id: str, worker_url: str | None = None) -> dict[str, Any]:
        """Poll a GPU simulation job and return render artifact paths when complete."""
        return SimulationClient(worker_url).status(job_id)

    @server.tool(name="tool_catalog")
    def tool_catalog() -> list[dict[str, str]]:
        """List stable atomic commands exposed by this server."""
        return catalog_payload(kind)

    @server.resource("garment://file/{path}")
    def garment_file(path: str) -> str:
        """Read a JSON project resource. Absolute paths are intentionally required."""
        resolved = Path("/" + path.lstrip("/")).resolve()
        if resolved.suffix not in {".json", ".val", ".vit", ".vst"}:
            raise ValueError("Unsupported resource type")
        return resolved.read_text(encoding="utf-8")


def register_atomic(server: FastMCP, spec: ToolSpec, domain: OperationDomain) -> None:
    def atomic_tool(
        project_path: str,
        arguments: dict[str, Any] | None = None,
        target: str | None = None,
        message: str = "",
        author: str = "agent",
        commit: bool = False,
    ) -> dict[str, Any]:
        return result_payload(
            execute_atomic(
                project_path,
                domain=domain,
                action=spec.action,
                arguments=arguments,
                target=target,
                message=message,
                author=author,
                commit=commit,
            )
        )

    atomic_tool.__name__ = spec.name
    atomic_tool.__doc__ = (
        spec.description + " Defaults to preview-only; commit requires explicit true."
    )
    server.tool(name=spec.name)(atomic_tool)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
