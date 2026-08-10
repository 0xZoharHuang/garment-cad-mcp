from __future__ import annotations

import ast
from pathlib import Path

# Public mutators in the pinned GarmentCode object model. Several upstream methods
# intentionally share one more stable, parameterized garmentcad action.
FACADE_TRANSFORM_MAP: dict[str, str] = {
    "Component.rotate_by": "component.transform",
    "Component.translate_by": "component.transform",
    "Component.translate_to": "component.transform",
    "Interface.flip_edges": "interface.update",
    "Interface.reorder": "interface.update",
    "Interface.reverse": "interface.update",
    "Interface.set_right_wrong": "interface.update",
    "Interface.substitute": "interface.update",
    "Panel.center_x": "panel.transform",
    "Panel.rotate_by": "panel.transform",
    "Panel.rotate_to": "panel.transform",
    "Panel.translate_by": "panel.transform",
    "Panel.translate_to": "panel.transform",
}

# These are real upstream methods, but exposing them here would recreate a second 2D drafting
# surface beside Valentina. Keeping the disposition executable makes an upstream diff fail closed.
VALENTINA_OWNED_2D_TRANSFORMS = {
    "Component.mirror",
    "Edge.reflect_features",
    "Edge.reverse",
    "Edge.rotate",
    "Edge.snap_to",
    "Edge.subdivide_len",
    "Edge.subdivide_param",
    "EdgeSequence.close_loop",
    "EdgeSequence.extend",
    "EdgeSequence.reflect",
    "EdgeSequence.reverse",
    "EdgeSequence.rotate",
    "EdgeSequence.snap_to",
    "EdgeSequence.substitute",
    "EdgeSequence.translate_by",
    "Panel.add_dart",
    "Panel.mirror",
    "Panel.set_pivot",
    "Panel.top_center_pivot",
}

NATIVE_HELPERS_NOT_STABLE_COMMANDS = {"Panel.autonorm", "Panel.rotate_align"}

# Upstream advertises this method but raises NotImplementedError unconditionally.
UPSTREAM_UNAVAILABLE = {"Component.rotate_to"}

MUTATOR_NAMES = {
    name.split(".", 1)[1]
    for name in (
        set(FACADE_TRANSFORM_MAP)
        | VALENTINA_OWNED_2D_TRANSFORMS
        | NATIVE_HELPERS_NOT_STABLE_COMMANDS
        | UPSTREAM_UNAVAILABLE
    )
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
    declared = (
        set(FACADE_TRANSFORM_MAP)
        | VALENTINA_OWNED_2D_TRANSFORMS
        | NATIVE_HELPERS_NOT_STABLE_COMMANDS
        | UPSTREAM_UNAVAILABLE
    )
    return {
        "missing_declarations": sorted(discovered - declared),
        "stale_declarations": sorted(declared - discovered),
        "missing_actions": sorted(set(FACADE_TRANSFORM_MAP.values()) - facade_actions),
        "valentina_owned_2d": sorted(VALENTINA_OWNED_2D_TRANSFORMS),
        "native_helpers_not_stable_commands": sorted(NATIVE_HELPERS_NOT_STABLE_COMMANDS),
        "upstream_unavailable": sorted(UPSTREAM_UNAVAILABLE),
    }
