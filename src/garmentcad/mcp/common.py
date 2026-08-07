from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from garmentcad.artifacts import ArtifactStore
from garmentcad.catalog import ToolSpec
from garmentcad.generated.atomic_commands import ARGUMENT_SCHEMAS
from garmentcad.models import OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import execute_atomic
from garmentcad.storage import read_json


def result_payload(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def add_core_tools(
    server: FastMCP,
    specs: tuple[ToolSpec, ...],
    lazy_loader: Callable[[set[str]], None],
) -> None:
    loaded: set[str] = set()

    @server.tool(name="project_open")
    def project_open(path: str) -> dict[str, Any]:
        """Open an existing Garment Project and return compact current state."""
        return Project.open(path).status()

    @server.tool(name="project_status")
    def project_status(path: str) -> dict[str, Any]:
        """Refresh revision, content hash, GUI-dirty state, and project identity."""
        return Project.open(path).status()

    @server.tool(name="catalog_search")
    def catalog_search(query: str, limit: int = 20, load: bool = True) -> dict[str, Any]:
        """Search atomic tools by name/action/description and optionally load matches."""
        terms = [term.lower() for term in query.split() if term]
        matches = []
        for spec in specs:
            haystack = f"{spec.name} {spec.action} {spec.description}".lower()
            if all(term in haystack for term in terms):
                matches.append(spec)
            if len(matches) >= max(1, min(limit, 100)):
                break
        names = {spec.name for spec in matches}
        if load:
            lazy_loader(names - loaded)
            loaded.update(names)
        return {
            "matches": [
                spec.__dict__
                | (
                    {"arguments_schema": ARGUMENT_SCHEMAS[spec.action]}
                    if spec.action in ARGUMENT_SCHEMAS
                    else {}
                )
                for spec in matches
            ],
            "loaded": sorted(names) if load else [],
            "message": "Refresh the MCP tool list after loading before calling an atomic tool.",
        }

    @server.tool(name="resource_read")
    def resource_read(project_path: str, uri: str) -> Any:
        """Read a project change-set, preview, thumbnail, or content-addressed artifact."""
        project = Project.open(project_path)
        prefix = f"garment://project/{project.manifest.project_id}/changeset/"
        if uri.startswith(prefix):
            suffix = uri[len(prefix) :]
            parts = suffix.split("/")
            token = parts[0]
            base = project.root / ".garmentcad/changesets" / token
            if len(parts) == 1:
                value = read_json(base.with_suffix(".json"))
                if value is None:
                    raise FileNotFoundError(uri)
                return {"media_type": "application/json", "data": value}
            resource_name = parts[1]
            if resource_name == "assembly":
                filename = "assembly.json"
            elif resource_name == "thumbnail":
                filename = next(
                    (
                        candidate
                        for candidate in ("thumbnail.png", "thumbnail.svg")
                        if (base / candidate).is_file()
                    ),
                    None,
                )
            elif resource_name == "details" and len(parts) == 3:
                detail_name = parts[2]
                if not detail_name.startswith("issue-") or not detail_name.endswith(".json"):
                    raise ValueError("Unsupported change-set detail resource")
                filename = f"details/{detail_name}"
            else:
                raise ValueError("Unsupported change-set resource")
            if filename is None:
                raise FileNotFoundError(uri)
            path = base / filename
            if filename.endswith(".json"):
                return {"media_type": "application/json", "data": read_json(path)}
            media_type = "image/png" if filename.endswith(".png") else "image/svg+xml"
            image = (
                Image(path=path)
                if media_type == "image/png"
                else Image(data=path.read_bytes(), format="svg+xml")
            )
            return [
                {
                    "media_type": media_type,
                    "byte_length": path.stat().st_size,
                    "resource_uri": uri,
                },
                image,
            ]
        artifact_prefix = "garment://artifact/sha256/"
        if uri.startswith(artifact_prefix):
            digest = uri[len(artifact_prefix) :]
            path, metadata = ArtifactStore(project.root).resolve(digest)
            if metadata["media_type"].startswith("image/"):
                image_format = metadata["media_type"].split("/", 1)[1]
                return [
                    {
                        "media_type": metadata["media_type"],
                        "metadata": metadata,
                        "resource_uri": uri,
                    },
                    Image(data=path.read_bytes(), format=image_format),
                ]
            if metadata["media_type"] == "application/json":
                return {
                    "media_type": metadata["media_type"],
                    "metadata": metadata,
                    "data": read_json(path),
                }
            return {
                "media_type": metadata["media_type"],
                "metadata": metadata,
                "local_path": str(path),
            }
        raise ValueError("URI does not belong to this project")

    @server.tool(name="changeset_commit")
    def changeset_commit(path: str, preview_token: str) -> dict[str, Any]:
        """Atomically commit one valid preview at its recorded base revision/hash."""
        return result_payload(Project.open(path).commit(preview_token))


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
    tool = server._tool_manager.get_tool(spec.name)
    argument_schema = ARGUMENT_SCHEMAS.get(spec.action)
    if tool is not None and argument_schema is not None:
        tool.parameters["properties"]["arguments"] = {
            "anyOf": [argument_schema, {"type": "null"}],
            "default": None,
            "title": "Arguments",
        }
        tool.parameters["$defs"] = {
            "objectReference": {
                "type": "object",
                "properties": {
                    "uuid": {"type": "string"},
                    "alias": {"type": "string"},
                },
                "anyOf": [{"required": ["uuid"]}, {"required": ["alias"]}],
                "additionalProperties": False,
            }
        }
