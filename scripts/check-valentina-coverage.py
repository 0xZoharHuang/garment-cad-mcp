#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from garmentcad.valentina_coverage import coverage, gui_dialog_command_coverage

root = Path(__file__).resolve().parents[1]
header = root / "upstream/valentina/src/libs/vmisc/def.h"
result = coverage(header)
unmapped = {name: record for name, record in result.items() if record["status"] == "unmapped"}
dialog_result = gui_dialog_command_coverage(
    root / "upstream/valentina/src/libs/vtools/tools"
)
direct_dialogs = {
    name: record
    for name, record in dialog_result.items()
    if record["status"] != "shared_command_dto"
}
print(
    json.dumps(
        {"tool_enum": result, "gui_dialog_commands": dialog_result},
        indent=2,
        sort_keys=True,
    )
)
if unmapped:
    raise SystemExit(f"Unmapped Valentina Tool enum values: {', '.join(unmapped)}")
if direct_dialogs:
    raise SystemExit(
        "GUI tool creation bypasses shared Command DTO: "
        + ", ".join(sorted(direct_dialogs))
    )
