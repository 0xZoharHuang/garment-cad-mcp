from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
assert (args.input / "garmentcode.json").is_file()
mode = os.environ.get("GARMENTCAD_FIXTURE_MODE", "success")
if sleep_seconds := float(os.environ.get("GARMENTCAD_FIXTURE_SLEEP_SECONDS", "0")):
    time.sleep(sleep_seconds)
if mode == "fail":
    print("fixture runner failed deliberately", file=sys.stderr)
    raise SystemExit(23)
args.output.mkdir(parents=True, exist_ok=True)
(args.output / "mesh.obj").write_text("o garment\nv 0 0 0\n", encoding="utf-8")
task = json.loads((args.input / "job.json").read_text(encoding="utf-8"))
if mode != "no-images":
    renders = args.output / "renders"
    renders.mkdir()
    for view in task["expected_views"]:
        (renders / f"{view}.png").write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )
(args.output / "diagnostics.json").write_text(
    json.dumps({"runner": "fixture", "views": task["expected_views"]}), encoding="utf-8"
)
