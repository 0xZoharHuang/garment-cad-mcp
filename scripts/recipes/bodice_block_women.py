"""Draft a women's basic bodice block (Müller-style frame) through the native Valentina host.

The draft is parametric: every construction length is a formula over the `#`-increments
set in stage 1, so changing `#CG` / `#WG` / `#BWL` regrades the whole block.

Frame convention (Valentina angles are counter-clockwise, y grows downward):
  N  neck point at centre back, top of the frame
  the vertical N->Hem carries chest / waist / hip levels
  the chest level carries back width, scye width, chest width to the centre front

Run:  uv run python scripts/recipes/bodice_block_women.py <project-root>
"""

from __future__ import annotations

import sys
from pathlib import Path

from garmentcad.models import Operation, OperationDomain
from garmentcad.project import Project

PATTERN = OperationDomain.PATTERN
MEASUREMENT = OperationDomain.MEASUREMENTS


def _increment(name: str, formula: str, description: str = "") -> Operation:
    return Operation(
        domain=MEASUREMENT,
        action="measurement.increment_set",
        arguments={"name": name, "formula": formula, "description": description},
    )


def increments() -> list[Operation]:
    """Body measurements, derived values, ease and drafting parameters (centimetres)."""
    return [
        # --- primary body measurements, size 38 / 168 cm ---
        _increment("#BH", "168", "Body height"),
        _increment("#CG", "92", "Chest girth"),
        _increment("#WG", "74", "Waist girth"),
        _increment("#HG", "98", "Hip girth"),
        # --- derived vertical measurements ---
        _increment("#SD", "#CG/10+(#CG<116?11:10.5)", "Scye depth from neck"),
        _increment("#BWL", "#BH/4-1", "Back waist length"),
        _increment("#HD", "#SD+#BWL", "Hip depth from neck"),
        _increment("#L", "#BWL+20", "Block length below neck"),
        # --- derived horizontal measurements ---
        _increment("#NW", "#CG/20+2", "Neck width"),
        _increment("#BW", "#CG/8+5.5", "Back width"),
        _increment("#SW", "#CG/8-1.5", "Scye width"),
        _increment("#CW", "#CG/4-4", "Chest width"),
        _increment("#BL_II", "#CG/4+6-(#CG>96?1:0)-(#CG>116?1:0)", "Bust length from shoulder"),
        _increment(
            "#FWL_II",
            "#BWL+4+(#CG>90?0.5:0)+(#CG>100?(#CG-100)/10:0)+(#CG>110?0.5:0)",
            "Front waist length from shoulder",
        ),
        # --- ease ---
        _increment("#SD_ease", "1", "Scye depth ease"),
        _increment("#BW_ease", "0.5", "Back width ease"),
        _increment("#SW_ease", "1.5", "Scye width ease"),
        _increment("#CW_ease", "1.5", "Chest width ease"),
        _increment("#WG_ease", "2", "Waist girth ease"),
        # --- drafting parameters ---
        _increment("#BackCenterInTake", "2", "Centre back waist intake"),
        _increment("#NecklineToShoulder", "2", "Back neck rise"),
        _increment("#BackShoulderDrop", "1.5", "Back shoulder drop"),
        _increment("#BackDartLocation", "#BW/3+1", "Back waist dart from centre back"),
        _increment("#BackDartHight1", "14", "Back dart height above waist"),
        _increment("#WaistSideIntake", "1", "Side seam waist intake"),
    ]


def _point(action: str, alias: str, **arguments: object) -> Operation:
    return Operation(
        domain=PATTERN,
        action=f"pattern.{action}",
        arguments={"alias": alias, **arguments},
    )


# Centre-back neck point. This is the base point of the draw that the project template
# already contains, so the draft reuses it instead of creating a second draw.
NECK = "A"


def _ref(alias: str) -> dict[str, str]:
    return {"alias": NECK if alias == "N" else alias}


def frame() -> list[Operation]:
    """Balance line, horizontal levels, and the chest-level width divisions."""
    return [
        # The project template already ships one draw whose base point is named "A";
        # a second pattern.base_point would create a second draw and collide with the
        # schema's uniqueDrawName constraint, so reuse "A" as the centre-back neck point.
        # Centre-back vertical: neck -> hem. 270 deg is downward.
        _point("end_line", "Hem", base_point=_ref("N"), formula_length="#L", angle_deg=270),
        # Horizontal levels measured down the centre back.
        _point(
            "along_line",
            "Chest",
            first_point=_ref("N"),
            second_point=_ref("Hem"),
            formula="#SD+#SD_ease",
        ),
        _point(
            "along_line",
            "Waist",
            first_point=_ref("N"),
            second_point=_ref("Hem"),
            formula="#BWL",
        ),
        _point(
            "along_line",
            "Hip",
            first_point=_ref("N"),
            second_point=_ref("Hem"),
            formula="#HD",
        ),
        # Chest level runs to the right (centre front). Normal of Waist->N at 90 deg.
        _point(
            "normal",
            "ChestCF",
            first_point=_ref("Chest"),
            second_point=_ref("N"),
            formula="#BW+#BW_ease+#SW+#SW_ease+#CW+#CW_ease",
            angle_deg=90,
        ),
        # Width divisions along the chest level: back width, then scye, then chest.
        _point(
            "along_line",
            "BackW",
            first_point=_ref("Chest"),
            second_point=_ref("ChestCF"),
            formula="#BW+#BW_ease",
        ),
        _point(
            "along_line",
            "ChestW",
            first_point=_ref("ChestCF"),
            second_point=_ref("Chest"),
            formula="#CW+#CW_ease",
        ),
        # Side seam sits one third into the scye from the front.
        _point(
            "along_line",
            "SideChest",
            first_point=_ref("ChestW"),
            second_point=_ref("BackW"),
            formula="(#SW+#SW_ease)/3",
        ),
    ]


def verticals() -> list[Operation]:
    """Drop the side seam and centre front from chest level to waist and hip."""
    return [
        # pointOfIntersection takes x from the first point and y from the second.
        _point(
            "point_of_intersection",
            "SideWaist",
            first_point=_ref("SideChest"),
            second_point=_ref("Waist"),
        ),
        _point(
            "point_of_intersection",
            "SideHip",
            first_point=_ref("SideChest"),
            second_point=_ref("Hip"),
        ),
        _point(
            "point_of_intersection",
            "CFWaist",
            first_point=_ref("ChestCF"),
            second_point=_ref("Waist"),
        ),
        _point(
            "point_of_intersection", "CFHip", first_point=_ref("ChestCF"), second_point=_ref("Hip")
        ),
        _point(
            "point_of_intersection",
            "BackWWaist",
            first_point=_ref("BackW"),
            second_point=_ref("Waist"),
        ),
        # Back width line carried up to neck level for the shoulder construction.
        _point(
            "point_of_intersection", "BackWNeck", first_point=_ref("BackW"), second_point=_ref("N")
        ),
    ]


def back_neck_and_shoulder() -> list[Operation]:
    """Back neckline and shoulder slope."""
    return [
        # Neck width along the top level, then rise to the neck point.
        _point(
            "along_line",
            "BNeckSide",
            first_point=_ref("N"),
            second_point=_ref("BackWNeck"),
            formula="#NW",
        ),
        _point(
            "normal",
            "BNeckTop",
            first_point=_ref("BNeckSide"),
            second_point=_ref("N"),
            formula="#NecklineToShoulder",
            angle_deg=0,
        ),
        # Shoulder tip: drop from the back width line at neck level.
        _point(
            "along_line",
            "BShoulderDrop",
            first_point=_ref("BackWNeck"),
            second_point=_ref("BackW"),
            formula="#BackShoulderDrop",
        ),
        # Extend the shoulder line past the drop point to reach the armhole.
        _point(
            "along_line",
            "BShoulder",
            first_point=_ref("BNeckTop"),
            second_point=_ref("BShoulderDrop"),
            formula="CurrentLength+1.5",
        ),
    ]


def armhole() -> list[Operation]:
    """Back armhole guide points and the curve through them."""
    return [
        # Scye base at the side seam, and the front armhole point.
        _point(
            "along_line",
            "ScyeFront",
            first_point=_ref("ChestW"),
            second_point=_ref("SideChest"),
            formula="0",
        ),
        # Bisector into the back scye corner gives the armhole hollow.
        _point(
            "bisector",
            "BArmholeGuide",
            first_point=_ref("BackWNeck"),
            vertex=_ref("BackW"),
            third_point=_ref("SideChest"),
            formula="2.5",
        ),
        # Back armhole: shoulder tip -> hollow -> side seam at chest level.
        Operation(
            domain=PATTERN,
            action="pattern.spline_path",
            arguments={
                "alias": "BArmholeCurve",
                "points": [
                    {"point": _ref("BShoulder"), "angle2_deg": 250, "length2_mm": 60},
                    {
                        "point": _ref("BArmholeGuide"),
                        "angle1_deg": 70,
                        "length1_mm": 40,
                        "angle2_deg": 250,
                        "length2_mm": 40,
                    },
                    {"point": _ref("SideChest"), "angle1_deg": 90, "length1_mm": 45},
                ],
            },
        ),
    ]


def waist_shaping() -> list[Operation]:
    """Centre back intake, side seam intake, and the back waist dart."""
    return [
        # Centre back is taken in at the waist and returns to the chest level.
        _point(
            "normal",
            "CBWaist",
            first_point=_ref("Waist"),
            second_point=_ref("N"),
            formula="#BackCenterInTake",
            angle_deg=0,
        ),
        # Side seam intake, both directions from the side waist point.
        _point(
            "along_line",
            "SideWaistBack",
            first_point=_ref("SideWaist"),
            second_point=_ref("BackWWaist"),
            formula="#WaistSideIntake",
        ),
        _point(
            "along_line",
            "SideWaistFront",
            first_point=_ref("SideWaist"),
            second_point=_ref("CFWaist"),
            formula="#WaistSideIntake",
        ),
        # Back waist dart: centre on the waist, apex above it.
        _point(
            "along_line",
            "BDartCentre",
            first_point=_ref("Waist"),
            second_point=_ref("SideWaist"),
            formula="#BackDartLocation",
        ),
        _point(
            "normal",
            "BDartApex",
            first_point=_ref("BDartCentre"),
            second_point=_ref("Waist"),
            formula="#BackDartHight1",
            angle_deg=0,
        ),
        _point(
            "along_line",
            "BDartLeft",
            first_point=_ref("BDartCentre"),
            second_point=_ref("Waist"),
            formula="1.5",
        ),
        _point(
            "along_line",
            "BDartRight",
            first_point=_ref("BDartCentre"),
            second_point=_ref("SideWaist"),
            formula="1.5",
        ),
    ]


def outline() -> list[Operation]:
    """Structural lines that make the block readable in the GUI."""
    edges = [
        (NECK, "BNeckSide"),
        ("BNeckTop", "BShoulder"),
        (NECK, "Waist"),
        ("Waist", "CBWaist"),
        ("CBWaist", "BDartLeft"),
        ("BDartLeft", "BDartApex"),
        ("BDartApex", "BDartRight"),
        ("BDartRight", "SideWaistBack"),
        ("SideWaistBack", "SideChest"),
        ("Chest", "ChestCF"),
        ("SideWaistFront", "CFWaist"),
        ("CFWaist", "ChestCF"),
    ]
    return [
        Operation(
            domain=PATTERN,
            action="pattern.line",
            arguments={
                "alias": f"seam.{first}_{second}",
                "first_point": _ref(first),
                "second_point": _ref(second),
            },
        )
        for first, second in edges
    ]


STAGES: list[tuple[str, list[Operation]]] = []


def build_stages() -> list[tuple[str, list[Operation]]]:
    return [
        ("increments", increments()),
        ("frame", frame()),
        ("verticals", verticals()),
        ("back neck and shoulder", back_neck_and_shoulder()),
        ("armhole", armhole()),
        ("waist shaping", waist_shaping()),
        ("outline", outline()),
    ]


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("projects/bodice-block-women")
    project = Project.open(root)
    for label, operations in build_stages():
        preview = project.preview(operations=operations)
        if not preview.ok:
            print(f"FAILED at stage {label!r}")
            for issue in preview.summary.issues:
                print(f"  {issue.code}: {getattr(issue, 'message', '')}")
            return 1
        committed = project.commit(preview.token)
        created = [item.alias for item in preview.summary.created]
        print(f"r{committed.revision:<3} {label:<24} +{len(created)}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
