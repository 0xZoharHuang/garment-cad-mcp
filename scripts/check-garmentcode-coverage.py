#!/usr/bin/env python3
from pathlib import Path

from garmentcad.catalog import GARMENTCODE_TOOLS
from garmentcad.garmentcode_coverage import coverage_report

root = Path(__file__).resolve().parents[1]
source = root / "upstream/garmentcode/pygarment/garmentcode"
report = coverage_report(source, {tool.action for tool in GARMENTCODE_TOOLS})
informational = {
    "upstream_unavailable",
    "valentina_owned_2d",
    "native_helpers_not_stable_commands",
}
failures = {key: value for key, value in report.items() if key not in informational and value}
if failures:
    raise SystemExit(f"GarmentCode facade coverage mismatch: {failures}")
print(report)
