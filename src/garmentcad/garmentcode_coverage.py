from __future__ import annotations

import ast
from pathlib import Path

# Public mutators in the pinned GarmentCode object model. Several upstream methods
# intentionally share one more stable, parameterized garmentcad action.
FACADE_TRANSFORM_MAP: dict[str, str] = {
    "Component.mirror": "component.mirror",
    "Component.rotate_by": "component.transform",
    "Component.translate_by": "component.transform",
    "Component.translate_to": "component.transform",
    "Edge.reflect_features": "edge_sequence.transform",
    "Edge.reverse": "edge_sequence.transform",
    "Edge.rotate": "edge_sequence.transform",
    "Edge.snap_to": "edge_sequence.transform",
    "Edge.subdivide_len": "edge.split",
    "Edge.subdivide_param": "edge.split",
    "EdgeSequence.close_loop": "panel.create",
    "EdgeSequence.extend": "edge.extend",
    "EdgeSequence.reflect": "edge_sequence.transform",
    "EdgeSequence.reverse": "edge_sequence.transform",
    "EdgeSequence.rotate": "edge_sequence.transform",
    "EdgeSequence.snap_to": "edge_sequence.transform",
    "EdgeSequence.substitute": "edge.split",
    "EdgeSequence.translate_by": "edge_sequence.transform",
    "Interface.flip_edges": "interface.update",
    "Interface.reorder": "interface.update",
    "Interface.reverse": "interface.update",
    "Interface.set_right_wrong": "interface.update",
    "Interface.substitute": "interface.update",
    "Panel.add_dart": "dart.insert",
    "Panel.autonorm": "panel.transform",
    "Panel.center_x": "panel.transform",
    "Panel.mirror": "panel.mirror",
    "Panel.rotate_align": "panel.transform",
    "Panel.rotate_by": "panel.transform",
    "Panel.rotate_to": "panel.transform",
    "Panel.set_pivot": "panel.pivot",
    "Panel.top_center_pivot": "panel.pivot",
    "Panel.translate_by": "panel.transform",
    "Panel.translate_to": "panel.transform",
}

# Upstream advertises this method but raises NotImplementedError unconditionally.
UPSTREAM_UNAVAILABLE = {"Component.rotate_to"}

MUTATOR_NAMES = {name.split(".", 1)[1] for name in FACADE_TRANSFORM_MAP} | {
    name.split(".", 1)[1] for name in UPSTREAM_UNAVAILABLE
}


def discover_public_transforms(source_root: Path) -> set[str]:
    files = {
        "Component": source_root / "component.py",
        "Panel": source_root / "panel.py",
        "Interface": source_root / "interface.py",
        "Edge": source_root / "edge.py",
        "EdgeSequence": source_root / "edge.py",
    }
    discovered: set[str] = set()
    for class_name, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if member.name in MUTATOR_NAMES:
                        discovered.add(f"{class_name}.{member.name}")
    return discovered


def coverage_report(source_root: Path, facade_actions: set[str]) -> dict[str, list[str]]:
    discovered = discover_public_transforms(source_root)
    declared = set(FACADE_TRANSFORM_MAP) | UPSTREAM_UNAVAILABLE
    return {
        "missing_declarations": sorted(discovered - declared),
        "stale_declarations": sorted(declared - discovered),
        "missing_actions": sorted(set(FACADE_TRANSFORM_MAP.values()) - facade_actions),
        "upstream_unavailable": sorted(UPSTREAM_UNAVAILABLE),
    }
