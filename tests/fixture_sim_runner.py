from __future__ import annotations

import argparse
import base64
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
assert (args.input / "garmentcode.json").is_file()
args.output.mkdir(parents=True, exist_ok=True)
(args.output / "mesh.obj").write_text("o garment\nv 0 0 0\n", encoding="utf-8")
(args.output / "front.png").write_bytes(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
)
