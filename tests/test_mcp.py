from __future__ import annotations

import json
import subprocess

import pytest

from garmentcad.catalog import GARMENTCODE_TOOLS, VALENTINA_TOOLS
from garmentcad.mcp.garmentcode import mcp as garmentcode_mcp
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
