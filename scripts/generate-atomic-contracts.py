#!/usr/bin/env python3
from __future__ import annotations

import json
import pprint
import re
import sys
from pathlib import Path
from typing import Any

from garmentcad.catalog import VALENTINA_TOOLS

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ROOT / "upstream/valentina/src/app/valentina/core/vcommandservice.cpp",
    ROOT / "upstream/valentina/src/app/puzzle/vpcommandservice.cpp",
)
SCHEMA_OUTPUT = ROOT / "schemas/atomic-tools.schema.json"
PYTHON_OUTPUT = ROOT / "src/garmentcad/generated/atomic_commands.py"

ACTION_RE = re.compile(r'action == QStringLiteral\("([^"]+)"\)')
VALUE_RE = re.compile(
    r'arguments\.value\(QStringLiteral\("([^"]+)"\)\)\.(toString|toDouble|toInt|toInteger|toBool|toArray|toObject)'
)
REQUIRED_STRING_RE = re.compile(r'RequiredString\(arguments, QStringLiteral\("([^"]+)"\)')
REQUIRED_OBJECT_RE = re.compile(
    r'ResolveObject\(arguments\.value\(QStringLiteral\("([^"]+)"\)\)\.toObject\(\)'
)

TYPE_SCHEMAS: dict[str, dict[str, Any]] = {
    "toString": {"type": "string"},
    "toDouble": {"type": "number"},
    "toInt": {"type": "integer"},
    "toInteger": {"type": "integer"},
    "toBool": {"type": "boolean"},
    "toArray": {"type": "array", "items": {}},
    "toObject": {"$ref": "#/$defs/objectReference"},
}

# These selectors are resolved by helper functions outside individual action branches.
SHEET_SELECTOR_PROPERTIES = {
    "sheet_uuid": {"type": "string"},
    "sheet": {"type": "string"},
    "sheet_index": {"type": "integer"},
}
PIECE_SELECTOR_PROPERTIES = {
    "piece_id": {"type": "string"},
    "piece": {"type": "string"},
    "copy_number": {"type": "integer"},
}

# Some arguments are consumed by shared helpers or are renamed to `options` at
# the native boundary, so the source regex cannot infer them from an action
# branch. Keep their types explicit here; the per-action allowlist below still
# prevents accidental schema expansion.
FIELD_SCHEMA_OVERRIDES = {
    **{
        name: {"type": "string"}
        for name in {
            "path",
            "axis",
            "notes",
            "customer",
            "email",
            "birth_date",
            "gender",
            "known_measurements_uuid",
            "name",
            "alias",
            "dimension",
            "format",
            "output_path",
        }
    },
    **{
        name: {"type": "number"}
        for name in {
            "base_a_mm",
            "base_b_mm",
            "base_c_mm",
            "min_mm",
            "max_mm",
            "value_mm",
            "x_scale",
            "y_scale",
        }
    },
    **{
        name: {"type": "boolean"}
        for name in {
            "read_only",
            "full_circumference",
            "special_units",
            "binary_dxf",
            "text_as_paths",
            "unified",
            "tiles_scheme",
            "show_grainline",
            "hide_ruler",
        }
    },
    "labels": {"type": "array", "items": {}},
    "exclude_mm": {"type": "array", "items": {"type": "number"}},
}

PROPERTY_ALLOWLISTS = {
    "measurement.file_save": {"path"},
    "measurement.set": {
        "path",
        "name",
        "value_mm",
        "formula",
        "shift_a_mm",
        "shift_b_mm",
        "shift_c_mm",
        "description",
        "full_name",
        "special_units",
        "dimension",
    },
    "measurement.rename": {"path", "name", "new_name"},
    "measurement.remove": {"path", "name"},
    "measurement.dimension_set": {
        "path",
        "axis",
        "min_mm",
        "max_mm",
        "step_mm",
        "base_mm",
        "body_measurement",
        "name",
    },
    "measurement.file_metadata_set": {
        "path",
        "notes",
        "customer",
        "email",
        "birth_date",
        "gender",
        "known_measurements_uuid",
        "read_only",
        "full_circumference",
    },
    "measurement.dimension_labels_set": {"path", "axis", "labels"},
    "measurement.restriction_set": {
        "path",
        "base_a_mm",
        "base_b_mm",
        "min_mm",
        "max_mm",
        "exclude_mm",
    },
    "measurement.restriction_remove": {"path", "base_a_mm", "base_b_mm"},
    "measurement.correction_set": {
        "path",
        "name",
        "base_a_mm",
        "base_b_mm",
        "base_c_mm",
        "value_mm",
    },
    "measurement.value_alias_set": {
        "path",
        "name",
        "alias",
        "base_a_mm",
        "base_b_mm",
        "base_c_mm",
    },
    "layout.generate": {
        "raw_layout_path",
        "sheet_width_mm",
        "sheet_height_mm",
        "auto_arrange",
        "piece_gap_mm",
        "allow_rotation",
        "rotation_count",
        "follow_grainline",
        "prefer_one_sheet",
        "auto_crop_length",
        "auto_crop_width",
        "timeout_ms",
    },
    "layout.sheet_add": {
        "name",
        "width_mm",
        "height_mm",
        "margin_left_mm",
        "margin_top_mm",
        "margin_right_mm",
        "margin_bottom_mm",
    },
    "layout.sheet_update": {
        "width_mm",
        "height_mm",
        "margin_left_mm",
        "margin_top_mm",
        "margin_right_mm",
        "margin_bottom_mm",
        "name",
        "ignore_margins",
    },
    "layout.settings_update": {
        "title",
        "description",
        "piece_gap_mm",
        "sticky_edges",
        "follow_grainline",
        "boundary_with_notches",
        "cut_on_fold",
        "horizontal_scale",
        "vertical_scale",
    },
    "layout.place": {"x_mm", "y_mm"},
    "layout.move_piece": {"dx_mm", "dy_mm"},
    "layout.rotate_piece": {"angle_deg"},
    "layout.flip_piece": {"axis"},
    "layout.print": {"output_path"},
    "export.layout": {
        "format",
        "output_path",
        "x_scale",
        "y_scale",
        "binary_dxf",
        "text_as_paths",
        "unified",
        "tiles_scheme",
        "show_grainline",
        "hide_ruler",
    },
}

REQUIRED_FIELDS = {
    "pattern.formula_evaluate": {"formula"},
    "measurement.file_open": {"source_path"},
    "measurement.set": {"name"},
    "measurement.rename": {"name", "new_name"},
    "measurement.remove": {"name"},
    "measurement.dimension_set": {"axis"},
    "measurement.dimension_labels_set": {"axis", "labels"},
    "measurement.restriction_set": {"base_a_mm", "min_mm", "max_mm"},
    "measurement.restriction_remove": {"base_a_mm"},
    "measurement.correction_set": {"name", "base_a_mm", "value_mm"},
    "measurement.value_alias_set": {"name", "alias"},
    "measurement.increment_set": {"name"},
    "measurement.increment_remove": {"name"},
    "measurement.final_measurement_set": {"name", "formula"},
    "layout.generate": {"raw_layout_path"},
    "pattern.piece": {"nodes"},
    "pattern.piece_path": {"nodes"},
    "pattern.group": {"objects"},
    "pattern.rotation": {"objects"},
    "pattern.move": {"objects"},
    "pattern.flipping_by_line": {"objects"},
    "pattern.flipping_by_axis": {"objects"},
}


def _top_level_action_blocks(source: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"(?m)^    if \(action ==", source)]
    return [
        source[start : starts[index + 1] if index + 1 < len(starts) else len(source)]
        for index, start in enumerate(starts)
    ]


def discover() -> dict[str, dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    required_by_action: dict[str, set[str]] = {}
    for source_path in SOURCES:
        for block in _top_level_action_blocks(source_path.read_text(encoding="utf-8")):
            actions = set(ACTION_RE.findall(block))
            fields = {
                name: TYPE_SCHEMAS[conversion] for name, conversion in VALUE_RE.findall(block)
            }
            required_strings = set(REQUIRED_STRING_RE.findall(block))
            required_objects = set(REQUIRED_OBJECT_RE.findall(block))
            for name in required_strings:
                fields.setdefault(name, {"type": "string"})
            for name in required_objects:
                fields.setdefault(name, {"$ref": "#/$defs/objectReference"})
            for action in actions:
                discovered.setdefault(action, {}).update(fields)
                required_by_action.setdefault(action, set()).update(required_objects)

    for action in discovered:
        if action in {"layout.sheet_update", "layout.place"}:
            discovered[action].update(SHEET_SELECTOR_PROPERTIES)
        if action in {
            "layout.place",
            "layout.move_piece",
            "layout.rotate_piece",
            "layout.flip_piece",
        }:
            discovered[action].update(PIECE_SELECTOR_PROPERTIES)
        allowlist = PROPERTY_ALLOWLISTS.get(action)
        if allowlist is not None:
            for name in allowlist:
                if name in FIELD_SCHEMA_OVERRIDES:
                    discovered[action].setdefault(name, FIELD_SCHEMA_OVERRIDES[name])
            selectors = set(SHEET_SELECTOR_PROPERTIES) | set(PIECE_SELECTOR_PROPERTIES)
            discovered[action] = {
                name: value
                for name, value in discovered[action].items()
                if name in allowlist or name in selectors
            }
        if "alias" in discovered[action]:
            required_by_action.setdefault(action, set()).add("alias")
        required_by_action.setdefault(action, set()).update(REQUIRED_FIELDS.get(action, set()))

    expected = {spec.action for spec in VALENTINA_TOOLS}
    if set(discovered) != expected:
        missing = sorted(expected - set(discovered))
        extra = sorted(set(discovered) - expected)
        raise RuntimeError(f"Atomic contract coverage mismatch; missing={missing}, extra={extra}")

    schemas: dict[str, dict[str, Any]] = {}
    for action, properties in sorted(discovered.items()):
        required = sorted(
            name for name in required_by_action.get(action, set()) if name in properties
        )
        schema: dict[str, Any] = {
            "type": "object",
            "properties": dict(sorted(properties.items())),
            # Native handlers remain the final validator. Keeping extensions legal is
            # necessary for formula alternatives and upstream-compatible attributes.
            "additionalProperties": True,
        }
        if required:
            schema["required"] = required
        schemas[action] = schema
    return schemas


def schema_document(schemas: dict[str, dict[str, Any]]) -> str:
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://garmentcad.local/schemas/atomic-tools.schema.json",
        "$defs": {
            "objectReference": {
                "type": "object",
                "properties": {"uuid": {"type": "string"}, "alias": {"type": "string"}},
                "anyOf": [{"required": ["uuid"]}, {"required": ["alias"]}],
                "additionalProperties": False,
            },
            **{action.replace(".", "_"): value for action, value in schemas.items()},
        },
        "type": "object",
        "properties": {
            "action": {"enum": sorted(schemas)},
            "arguments": {"type": "object"},
        },
        "required": ["action", "arguments"],
    }
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _python_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return "ObjectReference"
    return {
        "string": "str",
        "number": "float",
        "integer": "int",
        "boolean": "bool",
        "array": "list[Any]",
        "object": "dict[str, Any]",
    }.get(schema.get("type"), "Any")


def _class_name(action: str) -> str:
    return "".join(part.title() for part in action.replace(".", "_").split("_")) + "Arguments"


def python_module(schemas: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Generated by scripts/generate-atomic-contracts.py; do not edit.",
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
    for action, schema in schemas.items():
        class_name = _class_name(action)
        required = set(schema.get("required", []))
        lines.append(f"class {class_name}(TypedDict, total=False):")
        if not schema["properties"]:
            lines.append("    pass")
        for name, field_schema in schema["properties"].items():
            marker = "Required" if name in required else "NotRequired"
            lines.append(f"    {name}: {marker}[{_python_type(field_schema)}]")
        lines.append("")

    lines.extend(
        [
            "class AtomicCommands:",
            '    """Schema-generated typed Valentina/Tape/Puzzle recipe surface."""',
            "",
            "    def __init__(self, project_path: str | Path) -> None:",
            "        self.project_path = Path(project_path)",
            "",
        ]
    )
    domain_by_prefix = {
        "pattern": "PATTERN",
        "measurement": "MEASUREMENTS",
        "layout": "LAYOUT",
        "export": "EXPORT",
    }
    for spec in VALENTINA_TOOLS:
        class_name = _class_name(spec.action)
        domain = domain_by_prefix[spec.action.split(".", 1)[0]]
        lines.extend(
            [
                f"    def {spec.name}(",
                "        self,",
                "        *,",
                "        target: str | None = None,",
                '        message: str = "",',
                '        author: str = "agent",',
                "        commit: bool = False,",
                f"        **arguments: Unpack[{class_name}],",
                "    ) -> ToolResult:",
                "        return execute_atomic(",
                "            self.project_path,",
                f"            domain=OperationDomain.{domain},",
                f"            action={spec.action!r},",
                "            arguments=dict(arguments),",
                "            target=target,",
                "            message=message,",
                "            author=author,",
                "            commit=commit,",
                "        )",
                "",
            ]
        )

    lines.extend(
        [
            "ARGUMENT_SCHEMAS: dict[str, dict[str, Any]] = "
            + pprint.pformat(schemas, width=96, sort_dicts=True),
            "",
        ]
    )
    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Generated atomic contract is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    check = "--check" in sys.argv[1:]
    schemas = discover()
    write_or_check(SCHEMA_OUTPUT, schema_document(schemas), check)
    write_or_check(PYTHON_OUTPUT, python_module(schemas), check)


if __name__ == "__main__":
    main()
