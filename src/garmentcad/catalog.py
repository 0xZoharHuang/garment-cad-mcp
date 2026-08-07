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
    ToolSpec("object_get", "pattern.object_get", "Read one object and its semantic/UUID identity."),
    ToolSpec("object_update", "pattern.object_update", "Update editable properties of one object."),
    ToolSpec("object_delete", "pattern.object_delete", "Delete one object through native undo."),
    ToolSpec("object_duplicate", "pattern.object_duplicate", "Duplicate one construction object."),
    ToolSpec(
        "dependency_query", "pattern.dependency_query", "Read formula and geometry dependencies."
    ),
    ToolSpec(
        "formula_evaluate", "pattern.formula_evaluate", "Evaluate a native Valentina formula."
    ),
    ToolSpec("increment_set", "measurement.increment_set", "Set a pattern increment formula."),
    ToolSpec("increment_remove", "measurement.increment_remove", "Remove a pattern increment."),
    ToolSpec(
        "final_measurement_set",
        "measurement.final_measurement_set",
        "Set a final-measurement formula.",
    ),
    ToolSpec("measurement_file_create", "measurement.file_create", "Create a Tape .vit/.vst file."),
    ToolSpec("measurement_file_open", "measurement.file_open", "Attach an existing Tape file."),
    ToolSpec("measurement_file_save", "measurement.file_save", "Save the active Tape file."),
    ToolSpec("measurement_set", "measurement.set", "Set one Tape measurement in millimetres."),
    ToolSpec("measurement_rename", "measurement.rename", "Rename a custom Tape measurement."),
    ToolSpec("measurement_remove", "measurement.remove", "Remove one Tape measurement."),
    ToolSpec("measurement_dimension_set", "measurement.dimension_set", "Set multisize dimensions."),
    ToolSpec("measurement_export_csv", "measurement.export_csv", "Export measurements as CSV."),
    ToolSpec("layout_generate", "layout.generate", "Generate a Puzzle marker layout."),
    ToolSpec("layout_sheet_add", "layout.sheet_add", "Add a Puzzle layout sheet."),
    ToolSpec("layout_sheet_update", "layout.sheet_update", "Update sheet size and margins."),
    ToolSpec("layout_move_piece", "layout.move_piece", "Move one piece in a marker layout."),
    ToolSpec("layout_place", "layout.place", "Place one piece on a Puzzle sheet."),
    ToolSpec("layout_rotate_piece", "layout.rotate_piece", "Rotate one piece in a marker layout."),
    ToolSpec("layout_flip_piece", "layout.flip_piece", "Flip one piece in a marker layout."),
    ToolSpec("layout_settings_update", "layout.settings_update", "Update nesting/layout settings."),
    ToolSpec("layout_print", "layout.print", "Print or create a tiled Puzzle layout."),
    ToolSpec(
        "export_pattern", "export.pattern", "Export the current pattern to a requested format."
    ),
    ToolSpec("export_layout", "export.layout", "Export the current marker layout."),
)


GARMENTCODE_TOOLS = (
    ToolSpec("project_create", "project.create", "Create an empty Garment Project directory."),
    ToolSpec("changeset_discard", "changeset.discard", "Discard one immutable preview."),
    ToolSpec("revision_revert", "revision.revert", "Append a reverse revision."),
    ToolSpec("simulation_submit", "simulation.submit", "Submit a self-contained GPU job bundle."),
    ToolSpec("simulation_status", "simulation.status", "Poll structured GPU job status."),
    ToolSpec("simulation_cancel", "simulation.cancel", "Cancel a queued or running GPU job."),
    ToolSpec(
        "simulation_download", "simulation.download", "Store job results as project artifacts."
    ),
    ToolSpec("panel_create", "panel.create", "Create one polygonal sewing panel in millimetres."),
    ToolSpec("panel_delete", "panel.delete", "Delete one panel and dependent sewing objects."),
    ToolSpec("panel_transform", "panel.transform", "Set a panel's 3D placement."),
    ToolSpec("panel_mirror", "panel.mirror", "Create a reflected copy of one panel."),
    ToolSpec("edge_split", "edge.split", "Split one panel edge at fractional positions."),
    ToolSpec("edge_extend", "edge.extend", "Extend or shorten a straight panel edge."),
    ToolSpec("edge_chamfer", "edge.chamfer", "Chamfer one panel corner by millimetres."),
    ToolSpec("dart_insert", "dart.insert", "Insert a cut dart into one straight edge."),
    ToolSpec("component_define", "component.define", "Group panels as a named component."),
    ToolSpec(
        "valentina_import_revision",
        "valentina.import",
        "Import a native Valentina snapshot plus explicit sewing sidecar.",
    ),
    ToolSpec("interface_define", "interface.define", "Name an ordered set of panel edges."),
    ToolSpec("interface_delete", "interface.delete", "Delete one sewing interface."),
    ToolSpec("stitch_create", "stitch.create", "Sew two named interfaces together."),
    ToolSpec("stitch_delete", "stitch.delete", "Delete one stitch relation."),
    ToolSpec("assembly_validate", "validate", "Validate panels, interfaces, and stitches."),
)


def catalog_payload(kind: str) -> list[dict[str, str]]:
    source = VALENTINA_TOOLS if kind == "valentina" else GARMENTCODE_TOOLS
    return [spec.__dict__ for spec in source]
