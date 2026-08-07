#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from garmentcad.models import (
    AliasRegistry,
    AssemblyDocument,
    ChangeSet,
    ObjectRef,
    Operation,
    ProjectManifest,
    Revision,
    SimulationJob,
    ToolResult,
    ValidationIssue,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "schemas"
MODELS = {
    "object-reference": ObjectRef,
    "alias-registry": AliasRegistry,
    "assembly": AssemblyDocument,
    "project": ProjectManifest,
    "command": Operation,
    "changeset": ChangeSet,
    "revision": Revision,
    "validation": ValidationIssue,
    "tool-result": ToolResult,
    "simulation-job": SimulationJob,
}


def generated() -> dict[str, str]:
    result = {}
    for name, model in MODELS.items():
        schema = TypeAdapter(model).json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://garmentcad.local/schemas/{name}.schema.json"
        result[f"{name}.schema.json"] = (
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return result


def main() -> None:
    check = "--check" in sys.argv[1:]
    OUTPUT.mkdir(exist_ok=True)
    for filename, contents in generated().items():
        path = OUTPUT / filename
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != contents:
                raise SystemExit(f"Generated schema is stale: {path}")
        else:
            path.write_text(contents, encoding="utf-8")


if __name__ == "__main__":
    main()
