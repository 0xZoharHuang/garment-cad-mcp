from __future__ import annotations

import json
import subprocess

import pytest
from mcp.types import ImageContent, TextContent

from garmentcad.catalog import GARMENTCODE_TOOLS, VALENTINA_TOOLS
from garmentcad.mcp.garmentcode import mcp as garmentcode_mcp
from garmentcad.mcp.valentina import mcp as valentina_mcp
from garmentcad.models import Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import GarmentSDK
from garmentcad.storage import read_json
from garmentcad.valentina_coverage import coverage, enum_tools


def test_atomic_tool_names_are_unique():
    names = [tool.name for tool in (*GARMENTCODE_TOOLS, *VALENTINA_TOOLS)]
    assert len(names) == len(set(names))
    assert len(VALENTINA_TOOLS) >= 49


@pytest.mark.asyncio
async def test_mcp_starts_with_only_five_core_tools_and_loads_on_search():
    initial = {tool.name for tool in garmentcode_mcp._tool_manager.list_tools()}
    assert initial == {
        "project_open",
        "project_status",
        "catalog_search",
        "resource_read",
        "changeset_commit",
    }
    await garmentcode_mcp._tool_manager.call_tool(
        "catalog_search", {"query": "panel create", "load": True}
    )
    loaded = {tool.name for tool in garmentcode_mcp._tool_manager.list_tools()}
    assert "panel_create" in loaded
    assert "stitch_create" not in loaded


@pytest.mark.asyncio
async def test_valentina_mcp_starts_with_only_five_core_tools_and_loads_on_search():
    initial = {tool.name for tool in valentina_mcp._tool_manager.list_tools()}
    assert initial == {
        "project_open",
        "project_status",
        "catalog_search",
        "resource_read",
        "changeset_commit",
    }
    await valentina_mcp._tool_manager.call_tool(
        "catalog_search", {"query": "pattern line", "load": True}
    )
    loaded = {tool.name for tool in valentina_mcp._tool_manager.list_tools()}
    assert "pattern_line" in loaded


@pytest.mark.asyncio
async def test_thumbnail_resource_returns_compact_metadata_and_image_content(tmp_path):
    project = Project.create(tmp_path / "resource-project")
    preview = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="panel.create",
                arguments={
                    "alias": "front",
                    "vertices_mm": [[0, 0], [100, 0], [100, 150], [0, 150]],
                },
            )
        ]
    )
    resource_tool = garmentcode_mcp._tool_manager.get_tool("resource_read")
    result = await resource_tool.run(
        {"project_path": str(project.root), "uri": preview.thumbnails[0]},
        convert_result=True,
    )
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], TextContent)
    assert "byte_length" in result[0].text
    assert isinstance(result[1], ImageContent)
    assert result[1].mimeType == "image/svg+xml"


@pytest.mark.asyncio
async def test_sdk_and_mcp_generate_semantically_identical_changesets(tmp_path):
    sdk_project = Project.create(tmp_path / "sdk-project")
    mcp_project = Project.create(tmp_path / "mcp-project")
    vertices = [[0, 0], [120, 0], [100, 180], [0, 180]]

    sdk_result = GarmentSDK(sdk_project.root).panel_create("front", vertices)
    if garmentcode_mcp._tool_manager.get_tool("panel_create") is None:
        await garmentcode_mcp._tool_manager.call_tool(
            "catalog_search", {"query": "panel create", "load": True}
        )
    mcp_result = await garmentcode_mcp._tool_manager.call_tool(
        "panel_create",
        {
            "project_path": str(mcp_project.root),
            "alias": "front",
            "vertices_mm": vertices,
        },
    )

    sdk_change = read_json(
        sdk_project.root / f".garmentcad/changesets/{sdk_result.preview_token}.json"
    )
    mcp_change = read_json(
        mcp_project.root / f".garmentcad/changesets/{mcp_result['preview_token']}.json"
    )

    def contract(change):
        return {
            "base_revision": change["base_revision"],
            "author": change["author"],
            "message": change["message"],
            "operations": [
                {
                    "domain": operation["domain"],
                    "action": operation["action"],
                    "target": operation["target"],
                    "arguments": operation["arguments"],
                }
                for operation in change["operations"]
            ],
            "summary": {
                bucket: [item["alias"] for item in change["summary"][bucket]]
                for bucket in ("created", "changed", "deleted")
            }
            | {
                "measurements": change["summary"]["measurements"],
                "issues": change["summary"]["issues"],
            },
        }

    assert contract(sdk_change) == contract(mcp_change)


def test_generated_schemas_are_current():
    process = subprocess.run(
        ["uv", "run", "scripts/generate-schemas.py", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    schema = json.loads(open("schemas/changeset.schema.json", encoding="utf-8").read())
    assert "base_content_hash" in schema["properties"]


def test_every_valentina_tool_enum_is_constructible_or_explained():
    header = open("upstream/valentina/src/libs/vmisc/def.h", encoding="utf-8").name
    from pathlib import Path

    tools = enum_tools(Path(header))
    records = coverage(Path(header))
    assert set(records) == set(tools)
    assert not {name for name, record in records.items() if record["status"] == "unmapped"}
