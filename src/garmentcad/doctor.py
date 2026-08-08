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
from garmentcad.garmentcode_facade import GarmentCodeFacade

EXPECTED_UPSTREAM_REVISIONS = {
    "valentina": "b75c9bff3be3f2f8e07d95778f953538799f4cd5",
    "garmentcode": "d449629979028123a5c4dc9e732a2ec19b7fce31",
    "nvidia-warp-garmentcode": "63baf6855efdd89b2834b74640f84b3bb0d86b50",
}


def run_doctor() -> dict:
    repository = Path(__file__).resolve().parents[2]
    revisions = json.loads((repository / ".upstream-revisions.json").read_text(encoding="utf-8"))
    schema_check = subprocess.run(
        ["uv", "run", "scripts/generate-schemas.py", "--check"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    atomic_contract_check = subprocess.run(
        ["uv", "run", "scripts/generate-atomic-contracts.py", "--check"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assembly_contract_check = subprocess.run(
        ["uv", "run", "scripts/generate-assembly-contracts.py", "--check"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
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
            puzzle_info = JsonLineCommandBackend("GARMENTCAD_PUZZLE_COMMAND").service_info()
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
    garmentcode_info = None
    try:
        garmentcode_info = GarmentCodeFacade().service_info()
    except Exception:
        garmentcode_info = None
    garmentcode_python = repository / "build/garmentcode-venv/bin/python"
    warp_library = repository / "upstream/nvidia-warp-garmentcode/warp/bin/libwarp.dylib"
    warp_architectures: set[str] = set()
    if warp_library.is_file() and shutil.which("lipo"):
        lipo = subprocess.run(
            ["lipo", "-archs", str(warp_library)],
            capture_output=True,
            text=True,
            check=False,
        )
        if lipo.returncode == 0:
            warp_architectures = set(lipo.stdout.split())
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
            name in revisions
            and revisions[name]["revision"] == expected
            and (repository / revisions[name]["path"]).is_dir()
            for name, expected in EXPECTED_UPSTREAM_REVISIONS.items()
        ),
        "schemas_current": schema_check.returncode == 0,
        "atomic_contracts_current": atomic_contract_check.returncode == 0,
        "assembly_contracts_current": assembly_contract_check.returncode == 0,
        "valentina_command": bool(command_info and command_info.get("ok")),
        "puzzle_command": bool(puzzle_info and puzzle_info.get("ok")),
        "garmentcode_compat_python": garmentcode_python.is_file(),
        "garmentcode_command": bool(
            garmentcode_info
            and garmentcode_info.get("ok")
            and garmentcode_info.get("units") == {"public": "mm", "native": "cm"}
        ),
        "warp_cpu_universal": {"arm64", "x86_64"}.issubset(warp_architectures),
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
        "atomic_contracts_current",
        "assembly_contracts_current",
        "valentina_command",
        "puzzle_command",
        "garmentcode_compat_python",
        "garmentcode_command",
        "warp_cpu_universal",
        "valentina_handler_coverage",
    }
    return {
        "ok": all(checks[key] for key in required),
        "checks": checks,
        "valentina_command_info": command_info,
        "puzzle_command_info": puzzle_info,
        "garmentcode_command_info": garmentcode_info,
        "warp_architectures": sorted(warp_architectures),
        "missing_valentina_handlers": missing_handlers,
    }
