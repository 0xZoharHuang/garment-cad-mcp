from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    action: str
    description: str


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# Kept in source-control deliberately: a Valentina upgrade must review the public API diff.
VALENTINA_CONSTRUCTION_TOOLS = (
    "BasePoint",
    "EndLine",
    "Line",
    "AlongLine",
    "ShoulderPoint",
    "Normal",
    "Bisector",
    "LineIntersect",
    "Spline",
    "CubicBezier",
    "CutSpline",
    "CutArc",
    "Arc",
    "ArcWithLength",
    "SplinePath",
    "CubicBezierPath",
    "CutSplinePath",
    "PointOfContact",
    "Piece",
    "PiecePath",
    "Height",
    "Triangle",
    "LineIntersectAxis",
    "PointOfIntersectionArcs",
    "PointOfIntersectionCircles",
    "PointOfIntersectionCurves",
    "CurveIntersectAxis",
    "ArcIntersectAxis",
    "PointOfIntersection",
    "PointFromCircleAndTangent",
    "PointFromArcAndTangent",
    "TrueDarts",
    "UnionDetails",
    "Group",
    "Rotation",
    "FlippingByLine",
    "FlippingByAxis",
    "Move",
    "Midpoint",
    "EllipticalArc",
    "Pin",
    "InsertNode",
    "PlaceLabel",
    "DuplicateDetail",
    "ArcStart",
    "ArcEnd",
    "EllipticalArcWithLength",
    "ParallelCurve",
    "GraduatedCurve",
)


VALENTINA_TOOLS = tuple(
    ToolSpec(
        name=f"pattern_{_snake(tool)}",
        action=f"pattern.{_snake(tool)}",
        description=f"Stage and preview Valentina {tool} as one atomic construction operation.",
    )
    for tool in VALENTINA_CONSTRUCTION_TOOLS
) + (
    ToolSpec("measurement_set", "measurement.set", "Set one Tape measurement in millimetres."),
    ToolSpec("measurement_remove", "measurement.remove", "Remove one Tape measurement."),
    ToolSpec("layout_generate", "layout.generate", "Generate a Puzzle marker layout."),
    ToolSpec("layout_move_piece", "layout.move_piece", "Move one piece in a marker layout."),
    ToolSpec("layout_rotate_piece", "layout.rotate_piece", "Rotate one piece in a marker layout."),
    ToolSpec(
        "export_pattern", "export.pattern", "Export the current pattern to a requested format."
    ),
    ToolSpec("export_layout", "export.layout", "Export the current marker layout."),
)


GARMENTCODE_TOOLS = (
    ToolSpec("panel_create", "panel.create", "Create one polygonal sewing panel in millimetres."),
    ToolSpec("panel_delete", "panel.delete", "Delete one panel and dependent sewing objects."),
    ToolSpec("panel_transform", "panel.transform", "Set a panel's 3D placement."),
    ToolSpec("interface_define", "interface.define", "Name an ordered set of panel edges."),
    ToolSpec("interface_delete", "interface.delete", "Delete one sewing interface."),
    ToolSpec("stitch_create", "stitch.create", "Sew two named interfaces together."),
    ToolSpec("stitch_delete", "stitch.delete", "Delete one stitch relation."),
    ToolSpec("assembly_validate", "validate", "Validate panels, interfaces, and stitches."),
)


def catalog_payload(kind: str) -> list[dict[str, str]]:
    source = VALENTINA_TOOLS if kind == "valentina" else GARMENTCODE_TOOLS
    return [spec.__dict__ for spec in source]
