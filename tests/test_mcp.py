from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ImageContent, TextContent
from v2_helpers import commit_sync

from garmentcad.artifacts import ArtifactStore
from garmentcad.catalog import GARMENTCODE_TOOLS, VALENTINA_TOOLS
from garmentcad.generated.assembly_commands import ARGUMENT_SCHEMAS as ASSEMBLY_SCHEMAS
from garmentcad.generated.assembly_commands import AssemblyCommands
from garmentcad.generated.atomic_commands import ARGUMENT_SCHEMAS as VALENTINA_SCHEMAS
from garmentcad.generated.atomic_commands import AtomicCommands
from garmentcad.mcp.garmentcode import mcp as garmentcode_mcp
from garmentcad.mcp.valentina import mcp as valentina_mcp
from garmentcad.project import Project
from garmentcad.storage import read_json
from garmentcad.valentina_coverage import coverage, enum_tools

CORE_TOOLS = {
    "project_create",
    "project_import",
    "project_open",
    "project_status",
    "catalog_search",
    "resource_read",
    "command_preview",
    "changeset_commit",
    "changeset_discard",
    "revision_revert",
}


def test_atomic_tool_names_are_unique_and_schema_generated():
    names = [tool.name for tool in (*GARMENTCODE_TOOLS, *VALENTINA_TOOLS)]
    assert len(names) == len(set(names))
    assert len(VALENTINA_TOOLS) == 97
    assert set(VALENTINA_SCHEMAS) == {spec.action for spec in VALENTINA_TOOLS}
    assert all(hasattr(AtomicCommands, spec.name) for spec in VALENTINA_TOOLS)
    assert all(schema["additionalProperties"] is False for schema in VALENTINA_SCHEMAS.values())
    assert all(
        hasattr(AssemblyCommands, spec.name)
        for spec in GARMENTCODE_TOOLS
        if spec.action in ASSEMBLY_SCHEMAS and spec.action != "assembly.sync_from_pattern"
    )
    assert not hasattr(AssemblyCommands, "assembly_sync_from_pattern")


@pytest.mark.asyncio
async def test_mcp_lazy_catalog_loads_only_native_atomic_matches():
    assert {tool.name for tool in garmentcode_mcp._tool_manager.list_tools()} == CORE_TOOLS
    result = await garmentcode_mcp._tool_manager.call_tool(
        "catalog_search", {"query": "panel 3d placement", "load": True}
    )
    assert result["matches"][0]["action"] == "panel.transform"
    loaded = {tool.name for tool in garmentcode_mcp._tool_manager.list_tools()}
    assert "panel_place_3d" in loaded and "stitch_create" not in loaded


@pytest.mark.asyncio
async def test_valentina_schema_is_strict_and_nested_piece_semantics_are_visible():
    assert {tool.name for tool in valentina_mcp._tool_manager.list_tools()} == CORE_TOOLS
    await valentina_mcp._tool_manager.call_tool(
        "catalog_search", {"query": "pattern piece", "load": True}
    )
    tool = valentina_mcp._tool_manager.get_tool("pattern_piece")
    arguments = tool.parameters["properties"]["arguments"]["anyOf"][0]
    assert arguments["additionalProperties"] is False
    assert arguments["properties"]["nodes"]["items"]["additionalProperties"] is False
    assert {"grainline", "piece_label", "pattern_label", "fold"} <= set(arguments["properties"])


@pytest.mark.asyncio
async def test_mcp_can_create_native_project_and_preview_without_committing(tmp_path):
    path = tmp_path / "from-scratch"
    result = await valentina_mcp._tool_manager.call_tool(
        "project_create", {"path": str(path), "name": "From scratch"}
    )
    assert result["project"]["schema_version"] == "2.0"
    assert (path / "pattern/main.val").is_file()
    assert (path / "assembly/main.garmentcode.json").is_file()

    project = Project.open(path)
    commit_sync(project, "front")
    preview = await garmentcode_mcp._tool_manager.call_tool(
        "command_preview",
        {
            "project_path": str(path),
            "action": "panel.transform",
            "target": "front",
            "arguments": {"translation_mm": [10, 20, 30]},
        },
    )
    assert preview["preview_token"] and project.current_revision == 1
    with pytest.raises(ToolError, match="Unknown action"):
        await garmentcode_mcp._tool_manager.call_tool(
            "command_preview",
            {"project_path": str(path), "action": "panel.create", "arguments": {}},
        )


def test_codex_eager_mode_registers_all_valentina_atomic_tools():
    process = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            (
                "from garmentcad.mcp.valentina import mcp; "
                "assert len(mcp._tool_manager.list_tools()) == 107"
            ),
        ],
        env={**__import__("os").environ, "GARMENTCAD_MCP_TOOL_MODE": "eager"},
        capture_output=True, text=True, check=False,
    )
    assert process.returncode == 0, process.stderr


def test_core_annotations_distinguish_reads_previews_and_commits():
    assert valentina_mcp._tool_manager.get_tool("project_open").annotations.readOnlyHint is True
    preview = valentina_mcp._tool_manager.get_tool("command_preview")
    commit = valentina_mcp._tool_manager.get_tool("changeset_commit")
    assert preview.annotations.destructiveHint is False
    assert commit.annotations.readOnlyHint is False


@pytest.mark.asyncio
async def test_sdk_and_mcp_generate_same_native_changeset_contract(tmp_path):
    sdk_project = Project.create(tmp_path / "sdk")
    mcp_project = Project.create(tmp_path / "mcp")
    commit_sync(sdk_project, "front")
    commit_sync(mcp_project, "front")
    sdk = AssemblyCommands(sdk_project.root).panel_place_3d(
        target="front", translation_mm=[10, 20, 30]
    )
    if garmentcode_mcp._tool_manager.get_tool("panel_place_3d") is None:
        await garmentcode_mcp._tool_manager.call_tool(
            "catalog_search", {"query": "panel 3d placement", "load": True}
        )
    mcp = await garmentcode_mcp._tool_manager.call_tool(
        "panel_place_3d",
        {
            "project_path": str(mcp_project.root),
            "target": "front",
            "arguments": {"translation_mm": [10, 20, 30]},
        },
    )
    left = read_json(sdk_project.root / f".garmentcad/changesets/{sdk.token}.json")
    right = read_json(mcp_project.root / f".garmentcad/changesets/{mcp['preview_token']}.json")
    for change in (left, right):
        change.pop("id")
        change.pop("project_id")
        change.pop("created_at")
        change.pop("base_content_hash")
        change.pop("preview_content_hash")
        change.pop("preview_resources")
        for operation in change["operations"]:
            operation.pop("id")
    assert left == right


@pytest.mark.asyncio
async def test_content_addressed_image_resource_is_multimodal(tmp_path):
    project = Project.create(tmp_path / "resource")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    uri = ArtifactStore(project.root).put(png, filename="front.png", kind="simulation", revision=0)
    result = await garmentcode_mcp._tool_manager.get_tool("resource_read").run(
        {"project_path": str(project.root), "uri": uri}, convert_result=True
    )
    assert isinstance(result[0], TextContent) and isinstance(result[1], ImageContent)
    assert result[1].mimeType == "image/png"


def test_generated_schemas_are_current():
    for script in (
        "generate-schemas.py",
        "generate-atomic-contracts.py",
        "generate-assembly-contracts.py",
    ):
        process = subprocess.run(
            ["uv", "run", f"scripts/{script}", "--check"],
            capture_output=True, text=True, check=False,
        )
        assert process.returncode == 0, process.stderr


def test_every_valentina_tool_enum_and_gui_dialog_is_covered():
    header = Path("upstream/valentina/src/libs/vmisc/def.h")
    records = coverage(header)
    assert set(records) == set(enum_tools(header))
    assert not {name for name, record in records.items() if record["status"] == "unmapped"}
    from garmentcad.valentina_coverage import gui_dialog_command_coverage

    dialogs = gui_dialog_command_coverage(Path("upstream/valentina/src/libs/vtools/tools"))
    assert len(dialogs) >= 41
    assert not {
        name for name, record in dialogs.items() if record["status"] != "shared_command_dto"
    }


def test_every_valentina_catalog_action_has_native_replay_coverage():
    replay = "\n".join(
        (Path("tests") / name).read_text(encoding="utf-8")
        for name in ("test_native_valentina.py", "test_native_puzzle.py")
    )
    assert not {spec.action for spec in VALENTINA_TOOLS if spec.action not in replay}
