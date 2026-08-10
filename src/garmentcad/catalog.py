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
    ToolSpec(
        "background_image_add",
        "pattern.background_image_add",
        "Embed or link a native Valentina drafting background image.",
    ),
    ToolSpec(
        "background_image_get",
        "pattern.background_image_get",
        "Read native Valentina background-image properties.",
    ),
    ToolSpec(
        "background_image_update",
        "pattern.background_image_update",
        "Transform or update a native Valentina background image.",
    ),
    ToolSpec(
        "background_image_delete",
        "pattern.background_image_delete",
        "Delete a native Valentina background image.",
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
    ToolSpec(
        "measurement_file_metadata_set",
        "measurement.file_metadata_set",
        "Set Tape personal, system, and file metadata.",
    ),
    ToolSpec(
        "measurement_dimension_labels_set",
        "measurement.dimension_labels_set",
        "Set display labels for one multisize dimension.",
    ),
    ToolSpec(
        "measurement_restriction_set",
        "measurement.restriction_set",
        "Set a multisize dimension restriction.",
    ),
    ToolSpec(
        "measurement_restriction_remove",
        "measurement.restriction_remove",
        "Remove a multisize dimension restriction.",
    ),
    ToolSpec(
        "measurement_correction_set",
        "measurement.correction_set",
        "Set a measurement correction at one size coordinate.",
    ),
    ToolSpec(
        "measurement_value_alias_set",
        "measurement.value_alias_set",
        "Set an individual or multisize measurement value alias.",
    ),
    ToolSpec(
        "measurement_image_set",
        "measurement.image_set",
        "Embed an image in a Tape measurement.",
    ),
    ToolSpec(
        "measurement_image_remove",
        "measurement.image_remove",
        "Remove an embedded Tape measurement image.",
    ),
    ToolSpec(
        "measurement_import_csv",
        "measurement.import_csv",
        "Import standard columns from CSV into a Tape file.",
    ),
    ToolSpec("measurement_export_csv", "measurement.export_csv", "Export measurements as CSV."),
    ToolSpec("layout_generate", "layout.generate", "Generate a Puzzle marker layout."),
    ToolSpec("layout_sheet_add", "layout.sheet_add", "Add a Puzzle layout sheet."),
    ToolSpec("layout_sheet_update", "layout.sheet_update", "Update sheet size and margins."),
    ToolSpec("layout_sheet_remove", "layout.sheet_remove", "Remove one Puzzle sheet."),
    ToolSpec("layout_sheet_crop", "layout.sheet_crop", "Crop unused Puzzle sheet length."),
    ToolSpec("layout_move_piece", "layout.move_piece", "Move one piece in a marker layout."),
    ToolSpec("layout_place", "layout.place", "Place one piece on a Puzzle sheet."),
    ToolSpec("layout_rotate_piece", "layout.rotate_piece", "Rotate one piece in a marker layout."),
    ToolSpec("layout_flip_piece", "layout.flip_piece", "Flip one piece in a marker layout."),
    ToolSpec("layout_piece_reset", "layout.piece_reset", "Reset one piece transformation."),
    ToolSpec("layout_piece_z_order", "layout.piece_z_order", "Change one piece stacking order."),
    ToolSpec(
        "layout_rotate_to_grainline",
        "layout.rotate_to_grainline",
        "Rotate one piece to its grainline.",
    ),
    ToolSpec("layout_trash_piece", "layout.trash_piece", "Move one piece to Puzzle trash."),
    ToolSpec("layout_settings_update", "layout.settings_update", "Update nesting/layout settings."),
    ToolSpec("layout_validate", "layout.validate", "Validate all placed Puzzle pieces."),
    ToolSpec("layout_print", "layout.print", "Print or create a tiled Puzzle layout."),
    ToolSpec(
        "export_pattern", "export.pattern", "Export the current pattern to a requested format."
    ),
    ToolSpec("export_layout", "export.layout", "Export the current marker layout."),
)


GARMENTCODE_TOOLS = (
    ToolSpec("simulation_submit", "simulation.submit", "Submit a self-contained GPU job bundle."),
    ToolSpec(
        "simulation_configure",
        "simulation.configure",
        "Select revisioned body, measurements, fabric, simulation, and camera inputs.",
    ),
    ToolSpec("simulation_status", "simulation.status", "Poll structured GPU job status."),
    ToolSpec("simulation_cancel", "simulation.cancel", "Cancel a queued or running GPU job."),
    ToolSpec(
        "simulation_download", "simulation.download", "Store job results as project artifacts."
    ),
    ToolSpec(
        "garmentcode_export",
        "garmentcode.export",
        "Export native JSON and placed OBJ/USD as content-addressed artifacts.",
    ),
    ToolSpec(
        "panel_place_3d",
        "panel.transform",
        "Set a Valentina-derived panel's native GarmentCode 3D placement.",
    ),
    ToolSpec("component_define", "component.define", "Group panels as a named component."),
    ToolSpec(
        "component_place_3d",
        "component.transform",
        "Place a component in 3D through native GarmentCode transforms.",
    ),
    ToolSpec(
        "assembly_sync_from_pattern",
        "assembly.sync_from_pattern",
        "Rebuild the read-only 2D projection from the current native Valentina revision.",
    ),
    ToolSpec("interface_define", "interface.define", "Name an ordered set of panel edges."),
    ToolSpec("interface_update", "interface.update", "Reorder or orient a sewing interface."),
    ToolSpec("interface_delete", "interface.delete", "Delete one sewing interface."),
    ToolSpec("stitch_create", "stitch.create", "Sew two named interfaces together."),
    ToolSpec("stitch_update", "stitch.update", "Update native stitch interfaces or direction."),
    ToolSpec("stitch_delete", "stitch.delete", "Delete one stitch relation."),
    ToolSpec("assembly_validate", "validate", "Validate panels, interfaces, and stitches."),
)


def catalog_payload(kind: str) -> list[dict[str, str]]:
    source = VALENTINA_TOOLS if kind == "valentina" else GARMENTCODE_TOOLS
    return [spec.__dict__ for spec in source]
