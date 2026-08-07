#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from garmentcad.valentina_coverage import coverage

root = Path(__file__).resolve().parents[1]
header = root / "upstream/valentina/src/libs/vmisc/def.h"
result = coverage(header)
unmapped = {name: record for name, record in result.items() if record["status"] == "unmapped"}
print(json.dumps(result, indent=2, sort_keys=True))
if unmapped:
    raise SystemExit(f"Unmapped Valentina Tool enum values: {', '.join(unmapped)}")
