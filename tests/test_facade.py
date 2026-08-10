from __future__ import annotations

from pathlib import Path

from garmentcad.catalog import GARMENTCODE_TOOLS
from garmentcad.garmentcode_coverage import FACADE_TRANSFORM_MAP, coverage_report


def test_public_garmentcode_surface_only_mutates_native_owned_semantics():
    actions = {tool.action for tool in GARMENTCODE_TOOLS}
    assert {
        "assembly.sync_from_pattern",
        "panel.transform",
        "component.define",
        "component.transform",
        "interface.define",
        "interface.update",
        "interface.delete",
        "stitch.create",
        "stitch.update",
        "stitch.delete",
        "validate",
    } <= actions
    assert not actions & {
        "panel.create",
        "panel.mirror",
        "panel.pivot",
        "edge.split",
        "edge.extend",
        "edge.chamfer",
        "dart.insert",
    }


def test_pinned_public_transformations_have_audited_facade_mapping():
    source = Path(__file__).resolve().parents[1] / "upstream/garmentcode/pygarment/garmentcode"
    report = coverage_report(source, {tool.action for tool in GARMENTCODE_TOOLS})
    assert report["missing_declarations"] == []
    assert report["stale_declarations"] == []
    assert report["upstream_unavailable"] == ["Component.rotate_to"]
    assert "Panel.add_dart" in report["valentina_owned_2d"]
    assert "Panel.autonorm" in report["native_helpers_not_stable_commands"]
    assert len(FACADE_TRANSFORM_MAP) >= 10
