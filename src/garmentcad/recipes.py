from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from garmentcad.backends import JsonLineCommandBackend
from garmentcad.models import Operation, OperationDomain, ToolResult
from garmentcad.project import Project


@dataclass(frozen=True)
class PanelRecipe:
    alias: str
    name: str
    width_formula: str
    height_formula: str
    offset_mm: float


@dataclass(frozen=True)
class DraftRecipe:
    name: str
    driving_increment: str
    changed_formula: str
    increments: tuple[tuple[str, str, str], ...]
    panels: tuple[PanelRecipe, ...]


DRAFTS: dict[str, DraftRecipe] = {
    "bodice": DraftRecipe(
        name="Women's bodice qualification block",
        driving_increment="#Bust",
        changed_formula="96",
        increments=(
            ("#Bust", "92", "Bust girth"),
            ("#Waist", "74", "Waist girth"),
            ("#BackLength", "42", "Back waist length"),
            ("#SleeveLength", "58", "Sleeve length"),
            ("#Ease", "4", "Bodice ease"),
        ),
        panels=(
            PanelRecipe("bodice.front", "Bodice front", "#Bust/4+#Ease/4", "#BackLength+20", 0),
            PanelRecipe("bodice.back", "Bodice back", "#Bust/4+#Ease/4", "#BackLength+20", 400),
            PanelRecipe("bodice.sleeve", "Set-in sleeve", "#Bust/6+4", "#SleeveLength", 800),
        ),
    ),
    "shirt": DraftRecipe(
        name="Men's shirt qualification pattern",
        driving_increment="#Chest",
        changed_formula="104",
        increments=(
            ("#Chest", "100", "Chest girth"),
            ("#Neck", "40", "Neck girth"),
            ("#Wrist", "18", "Wrist girth"),
            ("#ShirtLength", "76", "Finished shirt length"),
            ("#SleeveLength", "64", "Sleeve length"),
            ("#ShirtEase", "12", "Shirt chest ease"),
        ),
        panels=(
            PanelRecipe(
                "shirt.front_left", "Left front", "#Chest/4+#ShirtEase/4", "#ShirtLength", 0
            ),
            PanelRecipe(
                "shirt.front_right", "Right front", "#Chest/4+#ShirtEase/4", "#ShirtLength", 400
            ),
            PanelRecipe("shirt.back", "Back", "#Chest/4+#ShirtEase/4", "#ShirtLength", 800),
            PanelRecipe("shirt.sleeve", "Sleeve", "#Chest/5+8", "#SleeveLength", 1200),
            PanelRecipe("shirt.collar", "Collar", "#Neck/2+2", "8", 1600),
            PanelRecipe("shirt.cuff", "Cuff", "#Wrist+6", "8", 1900),
        ),
    ),
    "trousers": DraftRecipe(
        name="Straight trouser qualification pattern",
        driving_increment="#Hip",
        changed_formula="104",
        increments=(
            ("#Waist", "82", "Waist girth"),
            ("#Hip", "100", "Hip girth"),
            ("#Outseam", "106", "Waist to floor"),
            ("#TrouserEase", "4", "Hip ease"),
        ),
        panels=(
            PanelRecipe("trouser.front", "Trouser front", "#Hip/4+#TrouserEase/4", "#Outseam", 0),
            PanelRecipe("trouser.back", "Trouser back", "#Hip/4+#TrouserEase/4+3", "#Outseam", 400),
            PanelRecipe("trouser.waistband", "Waistband", "#Waist/2+4", "8", 850),
            PanelRecipe("trouser.pocket", "Pocket facing", "#Hip/8", "18", 1400),
        ),
    ),
}


def _ref(alias: str) -> dict[str, str]:
    return {"alias": alias}


def _increment(name: str, formula: str, description: str) -> Operation:
    return Operation(
        domain=OperationDomain.MEASUREMENTS,
        action="measurement.increment_set",
        arguments={"name": name, "formula": formula, "description": description},
    )


def _panel_operations(panel: PanelRecipe, *, first: bool) -> list[Operation]:
    stem = panel.alias
    top_left = "A" if first else f"{stem}.top_left"
    operations: list[Operation] = []
    if not first:
        operations.append(
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.end_line",
                arguments={
                    "alias": top_left,
                    "base_point": _ref("A"),
                    "length_mm": panel.offset_mm,
                    "angle_deg": 0,
                },
            )
        )
    operations.extend(
        [
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.end_line",
                arguments={
                    "alias": f"{stem}.top_right",
                    "base_point": _ref(top_left),
                    "formula_length": panel.width_formula,
                    "angle_deg": 0,
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.end_line",
                arguments={
                    "alias": f"{stem}.bottom_left",
                    "base_point": _ref(top_left),
                    "formula_length": panel.height_formula,
                    "angle_deg": 90,
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.end_line",
                arguments={
                    "alias": f"{stem}.bottom_right",
                    "base_point": _ref(f"{stem}.top_right"),
                    "formula_length": panel.height_formula,
                    "angle_deg": 90,
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.midpoint",
                arguments={
                    "alias": f"{stem}.right_notch",
                    "first_point": _ref(f"{stem}.top_right"),
                    "second_point": _ref(f"{stem}.bottom_right"),
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.midpoint",
                arguments={
                    "alias": f"{stem}.top_mid",
                    "first_point": _ref(top_left),
                    "second_point": _ref(f"{stem}.top_right"),
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.midpoint",
                arguments={
                    "alias": f"{stem}.bottom_mid",
                    "first_point": _ref(f"{stem}.bottom_left"),
                    "second_point": _ref(f"{stem}.bottom_right"),
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.midpoint",
                arguments={
                    "alias": f"{stem}.label_center",
                    "first_point": _ref(top_left),
                    "second_point": _ref(f"{stem}.bottom_right"),
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.piece",
                arguments={
                    "alias": panel.alias,
                    "name": panel.name,
                    "short_name": re.sub(r"[^\w]", "_", panel.name)[:16],
                    "seam_allowance": True,
                    "seam_allowance_mm": 10,
                    "follow_grainline": True,
                    "nodes": [
                        {"object": _ref(top_left), "type": "point"},
                        {"object": _ref(f"{stem}.top_right"), "type": "point"},
                        {
                            "object": _ref(f"{stem}.right_notch"),
                            "type": "point",
                            "passmark": True,
                        },
                        {"object": _ref(f"{stem}.bottom_right"), "type": "point"},
                        {"object": _ref(f"{stem}.bottom_left"), "type": "point"},
                    ],
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.piece_path",
                arguments={
                    "alias": f"{stem}.grain_guide",
                    "piece": _ref(panel.alias),
                    "name": "Grain guide",
                    "type": "internal",
                    "line_type": "dashLine",
                    "nodes": [
                        {"object": _ref(f"{stem}.top_mid"), "type": "point"},
                        {"object": _ref(f"{stem}.bottom_mid"), "type": "point"},
                    ],
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.pin",
                arguments={
                    "alias": f"{stem}.label_pin",
                    "piece": _ref(panel.alias),
                    "point": _ref(f"{stem}.label_center"),
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.place_label",
                arguments={
                    "alias": f"{stem}.match_mark",
                    "piece": _ref(panel.alias),
                    "center_point": _ref(f"{stem}.right_notch"),
                    "type": "button",
                    "width_mm": 5,
                    "height_mm": 5,
                },
            ),
        ]
    )
    return operations


def draft_qualification_pattern(project_path: str | Path, kind: str) -> list[ToolResult]:
    if kind not in DRAFTS:
        raise ValueError(f"Unknown qualification draft {kind!r}; choose from {sorted(DRAFTS)}")
    recipe = DRAFTS[kind]
    project = Project.open(project_path)
    stages = [
        (
            "measurements",
            [
                _increment(name, formula, description)
                for name, formula, description in recipe.increments
            ],
        )
    ]
    stages.extend(
        (panel.alias, _panel_operations(panel, first=index == 0))
        for index, panel in enumerate(recipe.panels)
    )
    results: list[ToolResult] = []
    for label, operations in stages:
        preview = project.preview(operations=operations, message=f"Draft {kind}: {label}")
        if not preview.ok:
            issues = [issue.model_dump(mode="json") for issue in preview.summary.issues]
            raise ValueError(f"Draft stage {label!r} failed: {issues}")
        results.append(project.commit(preview.token))
    return results


def qualification_snapshot(project_path: str | Path) -> dict[str, Any]:
    return JsonLineCommandBackend().snapshot(Path(project_path))


def redraft_driving_measurement(project_path: str | Path, kind: str) -> ToolResult:
    recipe = DRAFTS[kind]
    project = Project.open(project_path)
    preview = project.preview(
        operations=[
            _increment(
                recipe.driving_increment,
                recipe.changed_formula,
                "Qualification redraft value",
            )
        ],
        message=f"Redraft {kind} after measurement change",
    )
    if not preview.ok:
        issues = [issue.model_dump(mode="json") for issue in preview.summary.issues]
        raise ValueError(f"Measurement redraft failed: {issues}")
    return project.commit(preview.token)


def export_qualification_pattern(project_path: str | Path, kind: str) -> ToolResult:
    project = Project.open(project_path)
    preview = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.EXPORT,
                action="export.pattern",
                arguments={
                    "format": format_name,
                    "output_path": f"artifacts/exports/{kind}.{extension}",
                    "details_only": True,
                },
            )
            for format_name, extension in (
                ("pdf", "pdf"),
                ("dxf_aama", "aama.dxf"),
                ("dxf_astm", "astm.dxf"),
            )
        ],
        message=f"Export {kind} qualification pattern",
    )
    if not preview.ok:
        issues = [issue.model_dump(mode="json") for issue in preview.summary.issues]
        raise ValueError(f"Qualification export failed: {issues}")
    return project.commit(preview.token)
