from __future__ import annotations

import base64
import inspect
import json
import subprocess

import pytest
from mcp.types import ImageContent, TextContent

from garmentcad.artifacts import ArtifactStore
from garmentcad.catalog import GARMENTCODE_TOOLS, VALENTINA_TOOLS
from garmentcad.generated.assembly_commands import (
    ARGUMENT_SCHEMAS as ASSEMBLY_ARGUMENT_SCHEMAS,
)
from garmentcad.generated.assembly_commands import AssemblyCommands
from garmentcad.generated.atomic_commands import ARGUMENT_SCHEMAS, AtomicCommands
from garmentcad.mcp.garmentcode import LAZY_TOOLS as GARMENTCODE_LAZY_TOOLS
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
    search = await valentina_mcp._tool_manager.call_tool(
        "catalog_search", {"query": "pattern line", "load": True}
    )
    loaded = {tool.name for tool in valentina_mcp._tool_manager.list_tools()}
    assert "pattern_line" in loaded
    assert search["matches"][0]["arguments_schema"]["properties"]

    along_line = next(spec for spec in VALENTINA_TOOLS if spec.action == "pattern.along_line")
    if valentina_mcp._tool_manager.get_tool(along_line.name) is None:
        await valentina_mcp._tool_manager.call_tool(
            "catalog_search", {"query": "along line", "load": True}
        )
    schema = valentina_mcp._tool_manager.get_tool(along_line.name).parameters
    arguments = schema["properties"]["arguments"]["anyOf"][0]
    assert {"alias", "first_point", "second_point", "length_mm"} <= set(arguments["properties"])
    assert {"alias", "first_point", "second_point"} <= set(arguments["required"])


def test_every_valentina_action_has_generated_schema_and_typed_recipe_method():
    assert set(ARGUMENT_SCHEMAS) == {spec.action for spec in VALENTINA_TOOLS}
    assert all(hasattr(AtomicCommands, spec.name) for spec in VALENTINA_TOOLS)


def test_every_assembly_action_has_generated_schema_and_typed_recipe_method():
    assembly_specs = [
        spec for spec in GARMENTCODE_TOOLS if spec.action in ASSEMBLY_ARGUMENT_SCHEMAS
    ]
    assert len(assembly_specs) == len(ASSEMBLY_ARGUMENT_SCHEMAS)
    assert all(hasattr(AssemblyCommands, spec.name) for spec in assembly_specs)


def test_garmentcode_mcp_signatures_match_generated_assembly_contract():
    targets = {
        "panel.delete": "panel",
        "panel.transform": "panel",
        "panel.pivot": "panel",
        "panel.mirror": "panel",
        "interface.update": "interface",
        "interface.delete": "interface",
        "stitch.delete": "stitch",
    }
    by_action = {spec.action: spec for spec in GARMENTCODE_TOOLS}
    for action, schema in ASSEMBLY_ARGUMENT_SCHEMAS.items():
        if action == "valentina.import":
            # This adapter obtains the snapshot from the current native revision.
            continue
        function = GARMENTCODE_LAZY_TOOLS[by_action[action].name]
        exposed = set(inspect.signature(function).parameters) - {"project_path", "commit"}
        if target := targets.get(action):
            exposed.remove(target)
        assert exposed == set(schema["properties"]), action


@pytest.mark.asyncio
async def test_garmentcode_catalog_returns_generated_argument_schema():
    result = await garmentcode_mcp._tool_manager.call_tool(
        "catalog_search", {"query": "edge sequence transform", "load": False}
    )
    match = next(item for item in result["matches"] if item["action"] == "edge_sequence.transform")
    assert set(match["arguments_schema"]["required"]) == {"panel", "edge_indices"}
    assert "reflect_line_mm" in match["arguments_schema"]["properties"]


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
async def test_content_addressed_render_resource_returns_image_content(tmp_path):
    project = Project.create(tmp_path / "render-resource")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    uri = ArtifactStore(project.root).put(
        png,
        filename="front.png",
        kind="simulation",
        revision=0,
    )
    resource_tool = garmentcode_mcp._tool_manager.get_tool("resource_read")
    result = await resource_tool.run(
        {"project_path": str(project.root), "uri": uri}, convert_result=True
    )
    assert isinstance(result, list)
    assert isinstance(result[0], TextContent)
    assert isinstance(result[1], ImageContent)
    assert result[1].mimeType == "image/png"


@pytest.mark.asyncio
async def test_change_set_detail_resource_is_on_demand_and_default_result_is_compact(tmp_path):
    project = Project.create(tmp_path / "detail-resource")
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
    assert len(json.dumps(preview.model_dump(mode="json"))) < 8_192
    token = preview.token
    detail = project.root / f".garmentcad/changesets/{token}/details/issue-0000.json"
    detail.parent.mkdir(parents=True, exist_ok=True)
    detail.write_text('{"dependents":[1,2,3]}\n', encoding="utf-8")
    uri = (
        f"garment://project/{project.manifest.project_id}/changeset/{token}/details/issue-0000.json"
    )
    resource_tool = garmentcode_mcp._tool_manager.get_tool("resource_read")
    result = await resource_tool.run(
        {"project_path": str(project.root), "uri": uri}, convert_result=True
    )
    assert isinstance(result, list)
    assert isinstance(result[0], TextContent)
    assert '"dependents"' in result[0].text


@pytest.mark.asyncio
async def test_sdk_and_mcp_generate_semantically_identical_changesets(tmp_path):
    sdk_project = Project.create(tmp_path / "sdk-project")
    mcp_project = Project.create(tmp_path / "mcp-project")
    vertices = [[0, 0], [120, 0], [100, 180], [0, 180]]

    sdk_result = GarmentSDK(sdk_project.root).assembly_commands.panel_create(
        alias="front", vertices_mm=vertices
    )
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
    atomic_process = subprocess.run(
        ["uv", "run", "scripts/generate-atomic-contracts.py", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert atomic_process.returncode == 0, atomic_process.stderr
    schema = json.loads(open("schemas/changeset.schema.json", encoding="utf-8").read())
    assert "base_content_hash" in schema["properties"]


def test_every_valentina_tool_enum_is_constructible_or_explained():
    header = open("upstream/valentina/src/libs/vmisc/def.h", encoding="utf-8").name
    from pathlib import Path

    tools = enum_tools(Path(header))
    records = coverage(Path(header))
    assert set(records) == set(tools)
    assert not {name for name, record in records.items() if record["status"] == "unmapped"}


def test_every_native_gui_dialog_emits_shared_command_dto():
    import re
    from pathlib import Path

    from garmentcad.valentina_coverage import gui_dialog_command_coverage

    records = gui_dialog_command_coverage(Path("upstream/valentina/src/libs/vtools/tools"))
    assert len(records) >= 41
    assert not {
        name for name, record in records.items() if record["status"] != "shared_command_dto"
    }

    command_service = Path(
        "upstream/valentina/src/app/valentina/core/vcommandservice.cpp"
    ).read_text(encoding="utf-8")
    assert not re.findall(r"VTool[A-Za-z0-9_]+::Create\(initData\)", command_service)
    assert command_service.count("CreateToolFromCommand<") >= 40
    assert all(
        marker in command_service
        for marker in (
            "VToolLineCommandData",
            "VToolAlongLineCommandData",
            "VToolEndLineCommandData",
        )
    )


def test_every_native_layout_export_format_is_mapped():
    import re
    from pathlib import Path

    from garmentcad.valentina_coverage import layout_export_formats

    formats = layout_export_formats(Path("upstream/valentina/src/libs/vlayout/vlayoutdef.h"))
    exportable = set(formats) - {"NC"}  # Reserved for future G-code in upstream.

    valentina = Path("upstream/valentina/src/app/valentina/core/vcommandservice.cpp").read_text(
        encoding="utf-8"
    )
    valentina_values = {
        int(value)
        for value in re.findall(
            r'\{QStringLiteral\("[a-z0-9_]+"\), \{(\d+), QStringLiteral\("\.[a-z0-9]+"\)\}\}',
            valentina,
        )
    }
    assert {formats[name] for name in exportable} <= valentina_values

    puzzle = Path("upstream/valentina/src/app/puzzle/vpmainwindow.cpp").read_text(encoding="utf-8")
    puzzle_names = set(
        re.findall(
            r'\{QStringLiteral\("[a-z0-9_]+"\), LayoutExportFormats::([A-Z0-9_]+)\}',
            puzzle,
        )
    )
    assert exportable <= puzzle_names


def test_every_valentina_catalog_action_has_native_replay_coverage():
    from pathlib import Path

    replay_sources = "\n".join(
        (Path("tests") / filename).read_text(encoding="utf-8")
        for filename in ("test_native_valentina.py", "test_native_puzzle.py")
    )
    assert not {spec.action for spec in VALENTINA_TOOLS if spec.action not in replay_sources}
