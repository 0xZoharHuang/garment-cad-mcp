from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def run_doctor() -> dict:
    repository = Path(__file__).resolve().parents[2]
    revisions = json.loads((repository / ".upstream-revisions.json").read_text(encoding="utf-8"))
    schema_check = subprocess.run(
        ["uv", "run", "scripts/generate-schemas.py", "--check"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
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
        "valentina_command": bool(os.environ.get("GARMENTCAD_VALENTINA_COMMAND")),
        "autodl_worker_url": bool(os.environ.get("GARMENTCAD_WORKER_URL")),
    }
    required = {
        "python_3_12",
        "cmake",
        "qmake_or_qtpaths",
        "qbs",
        "valentina_source",
        "garmentcode_source",
        "warp_source",
        "upstream_pins",
        "schemas_current",
    }
    return {"ok": all(checks[key] for key in required), "checks": checks}
