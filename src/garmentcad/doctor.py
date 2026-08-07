from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path


def run_doctor() -> dict:
    repository = Path(__file__).resolve().parents[2]
    checks = {
        "python_3_12": sys.version_info[:2] == (3, 12),
        "macos_arm64": platform.system() == "Darwin" and platform.machine() == "arm64",
        "cmake": shutil.which("cmake") is not None,
        "qmake_or_qtpaths": bool(shutil.which("qmake") or shutil.which("qtpaths")),
        "valentina_source": (repository / "upstream/valentina").exists(),
        "garmentcode_source": (repository / "upstream/garmentcode").exists(),
        "valentina_command": bool(os.environ.get("GARMENTCAD_VALENTINA_COMMAND")),
        "autodl_worker_url": bool(os.environ.get("GARMENTCAD_WORKER_URL")),
    }
    required = {
        "python_3_12",
        "cmake",
        "qmake_or_qtpaths",
        "valentina_source",
        "garmentcode_source",
    }
    return {"ok": all(checks[key] for key in required), "checks": checks}
