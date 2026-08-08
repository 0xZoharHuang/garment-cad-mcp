#!/usr/bin/env python3
from pathlib import Path

from garmentcad.catalog import GARMENTCODE_TOOLS
from garmentcad.garmentcode_coverage import coverage_report

root = Path(__file__).resolve().parents[1]
source = root / "upstream/garmentcode/pygarment/garmentcode"
report = coverage_report(source, {tool.action for tool in GARMENTCODE_TOOLS})
failures = {key: value for key, value in report.items() if key != "upstream_unavailable" and value}
if failures:
    raise SystemExit(f"GarmentCode facade coverage mismatch: {failures}")
print(report)
