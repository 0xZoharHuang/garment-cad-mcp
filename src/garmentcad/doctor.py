from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from garmentcad.backends import JsonLineCommandBackend
from garmentcad.catalog import VALENTINA_TOOLS


def run_doctor() -> dict:
    repository = Path(__file__).resolve().parents[2]
    revisions = json.loads((repository / ".upstream-revisions.json").read_text(encoding="utf-8"))
    schema_check = subprocess.run(
        ["uv", "run", "scripts/generate-schemas.py", "--check"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    command = os.environ.get("GARMENTCAD_VALENTINA_COMMAND")
    if not command:
        bundled_host = repository / "scripts/valentina-command-host.sh"
        command = str(bundled_host) if bundled_host.is_file() else None
    puzzle_command = os.environ.get("GARMENTCAD_PUZZLE_COMMAND")
    if not puzzle_command:
        bundled_host = repository / "scripts/puzzle-command-host.sh"
        puzzle_command = str(bundled_host) if bundled_host.is_file() else None
    command_info = None
    if command:
        previous = os.environ.get("GARMENTCAD_VALENTINA_COMMAND")
        os.environ["GARMENTCAD_VALENTINA_COMMAND"] = command
        try:
            command_info = JsonLineCommandBackend().service_info()
        except Exception:
            command_info = None
        finally:
            if previous is None:
                os.environ.pop("GARMENTCAD_VALENTINA_COMMAND", None)
            else:
                os.environ["GARMENTCAD_VALENTINA_COMMAND"] = previous
    puzzle_info = None
    if puzzle_command:
        previous = os.environ.get("GARMENTCAD_PUZZLE_COMMAND")
        os.environ["GARMENTCAD_PUZZLE_COMMAND"] = puzzle_command
        try:
            puzzle_info = JsonLineCommandBackend(
                "GARMENTCAD_PUZZLE_COMMAND"
            ).service_info()
        except Exception:
            puzzle_info = None
        finally:
            if previous is None:
                os.environ.pop("GARMENTCAD_PUZZLE_COMMAND", None)
            else:
                os.environ["GARMENTCAD_PUZZLE_COMMAND"] = previous
    expected_handlers = {spec.action for spec in VALENTINA_TOOLS}
    actual_handlers = set(command_info.get("handlers", [])) if command_info else set()
    actual_handlers.update(puzzle_info.get("handlers", []) if puzzle_info else [])
    missing_handlers = sorted(expected_handlers - actual_handlers)
    checks = {
        "python_3_12": sys.version_info[:2] == (3, 12),
        "macos_arm64": platform.system() == "Darwin" and platform.machine() == "arm64",
        "cmake": shutil.which("cmake") is not None,
        "qmake_or_qtpaths": bool(shutil.which("qmake") or shutil.which("qtpaths")),
        "qbs": shutil.which("qbs") is not None,
        "valentina_source": (repository / "upstream/valentina").exists(),
        "garmentcode_source": (repository / "upstream/garmentcode").exists(),
        "warp_source": (repository / "upstream/nvidia-warp-garmentcode").exists(),
        "upstream_pins": all(
            (repository / record["path"]).is_dir() and len(record["revision"]) == 40
            for record in revisions.values()
        ),
        "schemas_current": schema_check.returncode == 0,
        "valentina_command": bool(command_info and command_info.get("ok")),
        "puzzle_command": bool(puzzle_info and puzzle_info.get("ok")),
        "valentina_handler_coverage": not missing_handlers,
        "autodl_worker_url": bool(os.environ.get("GARMENTCAD_WORKER_URL")),
    }
    required = {
        "python_3_12",
        "macos_arm64",
        "cmake",
        "qmake_or_qtpaths",
        "qbs",
        "valentina_source",
        "garmentcode_source",
        "warp_source",
        "upstream_pins",
        "schemas_current",
        "valentina_command",
        "puzzle_command",
        "valentina_handler_coverage",
    }
    return {
        "ok": all(checks[key] for key in required),
        "checks": checks,
        "valentina_command_info": command_info,
        "puzzle_command_info": puzzle_info,
        "missing_valentina_handlers": missing_handlers,
    }
