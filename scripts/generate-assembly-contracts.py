#!/usr/bin/env python3
from __future__ import annotations

import json
import pprint
import sys
from pathlib import Path
from typing import Any

from garmentcad.catalog import GARMENTCODE_TOOLS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_OUTPUT = ROOT / "schemas/assembly-tools.schema.json"
PYTHON_OUTPUT = ROOT / "src/garmentcad/generated/assembly_commands.py"

REF = {"$ref": "#/$defs/objectReference"}
POINTS = {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}
NUMBERS = {"type": "array", "items": {"type": "number"}}
INTEGERS = {"type": "array", "items": {"type": "integer"}}


def fields(**values: str | dict[str, Any]) -> dict[str, dict[str, Any]]:
    primitive = {
        "str": {"type": "string"},
        "float": {"type": "number"},
        "int": {"type": "integer"},
        "bool": {"type": "boolean"},
        "numbers": NUMBERS,
        "integers": INTEGERS,
        "points": POINTS,
        "ref": REF,
        "object": {"type": "object"},
    }
    return {
        name: primitive[value] if isinstance(value, str) else value
        for name, value in values.items()
    }


CONTRACTS: dict[str, tuple[dict[str, dict[str, Any]], set[str]]] = {
    "panel.create": (
        fields(
            alias="str",
            vertices_mm="points",
            translation_mm="numbers",
            rotation_deg="numbers",
            uuid="str",
        ),
        {"alias", "vertices_mm"},
    ),
    "panel.delete": ({}, set()),
    "panel.transform": (
        fields(
            translation_mm="numbers",
            rotation_deg="numbers",
            translation_delta_mm="numbers",
            rotation_delta_deg="numbers",
            center_x="bool",
        ),
        set(),
    ),
    "panel.pivot": (fields(point_mm="numbers", replicate_placement="bool"), {"point_mm"}),
    "panel.mirror": (fields(alias="str", axis="str", origin_mm="float", uuid="str"), {"alias"}),
    "edge.split": (
        fields(panel="str", edge_index="int", fractions="numbers"),
        {"panel", "edge_index", "fractions"},
    ),
    "edge.extend": (
        fields(panel="str", edge_index="int", start_delta_mm="float", end_delta_mm="float"),
        {"panel", "edge_index"},
    ),
    "edge_sequence.transform": (
        fields(
            panel="str",
            edge_indices="integers",
            translation_delta_mm="numbers",
            snap_start_mm="numbers",
            rotation_deg="float",
            origin_mm="numbers",
            reflect_line_mm="points",
        ),
        {"panel", "edge_indices"},
    ),
    "edge.chamfer": (
        fields(
            panel="str", vertex_index="int", distance_before_mm="float", distance_after_mm="float"
        ),
        {"panel", "vertex_index", "distance_before_mm"},
    ),
    "dart.insert": (
        fields(
            panel="str", edge_index="int", intake_mm="float", depth_mm="float", position="float"
        ),
        {"panel", "edge_index", "intake_mm", "depth_mm"},
    ),
    "component.define": (
        fields(alias="str", panels={"type": "array", "items": {"type": "string"}}),
        {"alias", "panels"},
    ),
    "component.transform": (
        fields(component="str", translation_delta_mm="numbers", rotation_delta_deg="numbers"),
        {"component"},
    ),
    "component.mirror": (fields(component="str", axis="str", origin_mm="float"), {"component"}),
    "valentina.import": (fields(snapshot="object", sidecar="object"), {"snapshot"}),
    "interface.define": (
        fields(
            alias="str",
            panel="ref",
            edge_indices="integers",
            reverse="bool",
            ruffle="float",
            right_wrong="bool",
            uuid="str",
        ),
        {"alias", "panel", "edge_indices"},
    ),
    "interface.update": (
        fields(
            edge_indices="integers",
            reverse_order="bool",
            flip_edges="bool",
            right_wrong="bool",
            ruffle="float",
        ),
        set(),
    ),
    "interface.delete": ({}, set()),
    "stitch.create": (
        fields(alias="str", interface_a="ref", interface_b="ref", direction="str", uuid="str"),
        {"alias", "interface_a", "interface_b"},
    ),
    "stitch.delete": ({}, set()),
    "validate": ({}, set()),
}

TARGET_ACTIONS = {
    "panel.delete",
    "panel.transform",
    "panel.pivot",
    "panel.mirror",
    "interface.update",
    "interface.delete",
    "stitch.delete",
}


def schemas() -> dict[str, dict[str, Any]]:
    result = {}
    for action, (properties, required) in CONTRACTS.items():
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = sorted(required)
        result[action] = schema
    return result


def schema_document(values: dict[str, dict[str, Any]]) -> str:
    return (
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://garmentcad.local/schemas/assembly-tools.schema.json",
                "$defs": {
                    "objectReference": {
                        "type": "object",
                        "properties": {"uuid": {"type": "string"}, "alias": {"type": "string"}},
                        "anyOf": [{"required": ["uuid"]}, {"required": ["alias"]}],
                        "additionalProperties": False,
                    },
                    **{action.replace(".", "_"): schema for action, schema in values.items()},
                },
                "type": "object",
                "properties": {"action": {"enum": sorted(values)}, "arguments": {"type": "object"}},
                "required": ["action", "arguments"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def python_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return "ObjectReference"
    if schema.get("type") == "array":
        item = schema.get("items", {})
        return f"list[{python_type(item)}]"
    return {
        "string": "str",
        "number": "float",
        "integer": "int",
        "boolean": "bool",
        "object": "dict[str, Any]",
    }.get(schema.get("type"), "Any")


def class_name(action: str) -> str:
    return "".join(part.title() for part in action.replace(".", "_").split("_")) + "Arguments"


def python_module(values: dict[str, dict[str, Any]]) -> str:
    specs = {spec.action: spec for spec in GARMENTCODE_TOOLS}
    lines = [
        "# Generated by scripts/generate-assembly-contracts.py; do not edit.",
        "# ruff: noqa",
        "from __future__ import annotations",
        "",
        "from pathlib import Path",
        "from typing import Any, NotRequired, Required, TypedDict, Unpack",
        "",
        "from garmentcad.models import OperationDomain, ToolResult",
        "from garmentcad.sdk import execute_atomic",
        "",
        "class ObjectReference(TypedDict, total=False):",
        "    uuid: NotRequired[str]",
        "    alias: NotRequired[str]",
        "",
    ]
    for action, schema in values.items():
        lines.append(f"class {class_name(action)}(TypedDict, total=False):")
        required = set(schema.get("required", []))
        if not schema["properties"]:
            lines.append("    pass")
        for name, field_schema in schema["properties"].items():
            marker = "Required" if name in required else "NotRequired"
            lines.append(f"    {name}: {marker}[{python_type(field_schema)}]")
        lines.append("")
    lines += [
        "class AssemblyCommands:",
        '    """Schema-generated typed GarmentCode assembly recipe surface."""',
        "",
        "    def __init__(self, project_path: str | Path) -> None:",
        "        self.project_path = Path(project_path)",
        "",
    ]
    for action in values:
        name = specs[action].name
        lines += [f"    def {name}(", "        self,", "        *,"]
        if action in TARGET_ACTIONS:
            lines.append("        target: str,")
        lines += [
            '        message: str = "",',
            '        author: str = "agent",',
            "        commit: bool = False,",
            f"        **arguments: Unpack[{class_name(action)}],",
            "    ) -> ToolResult:",
            "        return execute_atomic(",
            "            self.project_path,",
            "            domain=OperationDomain.ASSEMBLY,",
            f"            action={action!r},",
            "            arguments=dict(arguments),",
        ]
        if action in TARGET_ACTIONS:
            lines.append("            target=target,")
        lines += [
            "            message=message,",
            "            author=author,",
            "            commit=commit,",
            "        )",
            "",
        ]
    lines += [
        "ARGUMENT_SCHEMAS: dict[str, dict[str, Any]] = "
        + pprint.pformat(values, width=96, sort_dicts=True),
        "",
    ]
    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Generated assembly contract is stale: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main() -> None:
    check = "--check" in sys.argv[1:]
    values = schemas()
    catalog_actions = {spec.action for spec in GARMENTCODE_TOOLS}
    if missing := sorted(set(values) - catalog_actions):
        raise SystemExit(f"Assembly contract actions are absent from catalog: {missing}")
    write_or_check(SCHEMA_OUTPUT, schema_document(values), check)
    write_or_check(PYTHON_OUTPUT, python_module(values), check)


if __name__ == "__main__":
    main()
