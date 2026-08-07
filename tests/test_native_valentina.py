from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from garmentcad.models import Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.storage import read_json

NATIVE_COMMAND = os.environ.get("GARMENTCAD_VALENTINA_COMMAND")
pytestmark = pytest.mark.skipif(not NATIVE_COMMAND, reason="native Valentina host is not built")


def test_native_preview_commit_and_uuid_sidecar(tmp_path):
    project = Project.create(tmp_path / "native")
    fixture = (
        Path(__file__).parents[1]
        / "upstream/valentina/src/test/CollectionTest/tst_valentina/issue_372.val"
    )
    shutil.copy2(fixture, project.root / "pattern/main.val")

    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.line",
            arguments={
                "alias": "construction.guide",
                "first_point": {"alias": "A"},
                "second_point": {"alias": "A1"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.along_line",
            arguments={
                "alias": "B",
                "first_point": {"alias": "A"},
                "second_point": {"alias": "A1"},
                "length_mm": 15,
            },
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created] == ["construction.guide", "B"]
    candidate = project.root / f".garmentcad/changesets/{preview.token}/pattern/main.val"
    assert 'name="B"' in candidate.read_text(encoding="utf-8")
    assert 'name="B"' not in (project.root / "pattern/main.val").read_text(encoding="utf-8")

    committed = project.commit(preview.token)
    assert committed.revision == 1
    assert 'name="B"' in (project.root / "pattern/main.val").read_text(encoding="utf-8")
    records = read_json(project.root / ".garmentcad/aliases.json")["objects"]
    assert {record["alias"] for record in records.values()} == {"construction.guide", "B"}
    assert all(record["uuid"] == object_id for object_id, record in records.items())


def test_unsupported_native_action_fails_closed(tmp_path):
    project = Project.create(tmp_path / "unsupported")
    fixture = (
        Path(__file__).parents[1]
        / "upstream/valentina/src/test/CollectionTest/tst_valentina/empty.val"
    )
    shutil.copy2(fixture, project.root / "pattern/main.val")
    result = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.not_a_native_tool",
            )
        ]
    )
    assert not result.ok
    assert result.summary.issues[0].code == "unsupported_action"


def test_native_common_geometry_handlers_replay_in_order(tmp_path):
    project = Project.create(tmp_path / "geometry")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "B",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "C",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "D",
                "base_point": {"alias": "B"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.midpoint",
            arguments={"alias": "M", "first_point": {"alias": "A"}, "second_point": {"alias": "D"}},
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.line_intersect",
            arguments={
                "alias": "X",
                "line1_p1": {"alias": "A"},
                "line1_p2": {"alias": "D"},
                "line2_p1": {"alias": "B"},
                "line2_p2": {"alias": "C"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.arc",
            arguments={
                "alias": "neck.arc",
                "center": {"alias": "A"},
                "radius_mm": 20,
                "start_angle_deg": 0,
                "end_angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.spline",
            arguments={
                "alias": "neck.curve",
                "point1": {"alias": "B"},
                "point4": {"alias": "C"},
                "angle1_deg": 135,
                "angle2_deg": 315,
                "length1_mm": 30,
                "length2_mm": 30,
            },
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created] == [
        "B",
        "C",
        "D",
        "M",
        "X",
        "neck.arc",
        "neck.curve",
    ]
    committed = project.commit(preview.token)
    assert committed.revision == 1


def test_native_derived_point_handlers_replay_in_order(tmp_path):
    project = Project.create(tmp_path / "derived-points")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "B",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "C",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "D",
                "base_point": {"alias": "B"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.shoulder_point",
            arguments={
                "alias": "shoulder",
                "line_p1": {"alias": "B"},
                "line_p2": {"alias": "D"},
                "shoulder_point": {"alias": "A"},
                "length_mm": 120,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.normal",
            arguments={
                "alias": "normal",
                "first_point": {"alias": "A"},
                "second_point": {"alias": "B"},
                "length_mm": 30,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.bisector",
            arguments={
                "alias": "bisector",
                "first_point": {"alias": "B"},
                "vertex": {"alias": "A"},
                "third_point": {"alias": "C"},
                "length_mm": 40,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.height",
            arguments={
                "alias": "height",
                "base_point": {"alias": "D"},
                "line_p1": {"alias": "A"},
                "line_p2": {"alias": "C"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.triangle",
            arguments={
                "alias": "triangle",
                "axis_p1": {"alias": "A"},
                "axis_p2": {"alias": "D"},
                "first_point": {"alias": "B"},
                "second_point": {"alias": "C"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_of_intersection",
            arguments={
                "alias": "coordinate-intersection",
                "first_point": {"alias": "B"},
                "second_point": {"alias": "C"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_of_contact",
            arguments={
                "alias": "contact",
                "center": {"alias": "A"},
                "line_p1": {"alias": "A"},
                "line_p2": {"alias": "B"},
                "radius_mm": 50,
            },
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created] == [
        "B",
        "C",
        "D",
        "shoulder",
        "normal",
        "bisector",
        "height",
        "triangle",
        "coordinate-intersection",
        "contact",
    ]
    committed = project.commit(preview.token)
    assert committed.revision == 1

    reopened = Project.open(project.root)
    pattern = (reopened.root / "pattern/main.val").read_text(encoding="utf-8")
    for name in ("shoulder", "normal", "bisector", "height", "triangle", "contact"):
        assert f'name="{name}"' in pattern


def test_native_circle_arc_intersection_and_tangent_handlers(tmp_path):
    project = Project.create(tmp_path / "circle-intersections")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "B",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "D",
                "base_point": {"alias": "B"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.arc",
            arguments={
                "alias": "arc-a",
                "center": {"alias": "A"},
                "radius_mm": 100,
                "start_angle_deg": 0,
                "end_angle_deg": 180,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.arc",
            arguments={
                "alias": "arc-b",
                "center": {"alias": "B"},
                "radius_mm": 100,
                "start_angle_deg": 0,
                "end_angle_deg": 180,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_of_intersection_circles",
            arguments={
                "alias": "circle-cross",
                "first_center": {"alias": "A"},
                "second_center": {"alias": "B"},
                "first_radius_mm": 80,
                "second_radius_mm": 80,
                "solution": 1,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_of_intersection_arcs",
            arguments={
                "alias": "arc-cross",
                "first_arc": {"alias": "arc-a"},
                "second_arc": {"alias": "arc-b"},
                "solution": 1,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_from_circle_and_tangent",
            arguments={
                "alias": "circle-tangent",
                "center": {"alias": "A"},
                "tangent_point": {"alias": "B"},
                "radius_mm": 50,
                "solution": 2,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_from_arc_and_tangent",
            arguments={
                "alias": "arc-tangent",
                "arc": {"alias": "arc-a"},
                "tangent_point": {"alias": "D"},
                "solution": 2,
            },
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created[-4:]] == [
        "circle-cross",
        "arc-cross",
        "circle-tangent",
        "arc-tangent",
    ]
    project.commit(preview.token)
    pattern = (project.root / "pattern/main.val").read_text(encoding="utf-8")
    for name in ("circle-cross", "arc-cross", "circle-tangent", "arc-tangent"):
        assert f'name="{name}"' in pattern


def test_native_axis_intersection_handlers(tmp_path):
    project = Project.create(tmp_path / "axis-intersections")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "B",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "C",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.arc",
            arguments={
                "alias": "curve",
                "center": {"alias": "A"},
                "radius_mm": 100,
                "start_angle_deg": 0,
                "end_angle_deg": 180,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.line_intersect_axis",
            arguments={
                "alias": "line-axis",
                "base_point": {"alias": "A"},
                "line_p1": {"alias": "B"},
                "line_p2": {"alias": "C"},
                "angle_deg": 45,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.curve_intersect_axis",
            arguments={
                "alias": "curve-axis",
                "base_point": {"alias": "A"},
                "curve": {"alias": "curve"},
                "angle_deg": 45,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.arc_intersect_axis",
            arguments={
                "alias": "arc-axis",
                "base_point": {"alias": "A"},
                "curve": {"alias": "curve"},
                "angle_deg": 135,
            },
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created[-3:]] == [
        "line-axis",
        "curve-axis",
        "arc-axis",
    ]
    project.commit(preview.token)


def test_native_arc_variant_handlers(tmp_path):
    project = Project.create(tmp_path / "arc-variants")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action=action,
            arguments={
                "alias": alias,
                "center": {"alias": "A"},
                "radius_mm": 50,
                "start_angle_deg": start,
                "end_angle_deg": end,
            },
        )
        for action, alias, start, end in (
            ("pattern.arc_start", "arc-start", 0, 90),
            ("pattern.arc_end", "arc-end", 90, 180),
        )
    ]
    operations.extend(
        [
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.arc_with_length",
                arguments={
                    "alias": "arc-length",
                    "center": {"alias": "A"},
                    "radius_mm": 50,
                    "start_angle_deg": 0,
                    "length_mm": 50,
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.elliptical_arc",
                arguments={
                    "alias": "ellipse",
                    "center": {"alias": "A"},
                    "radius1_mm": 60,
                    "radius2_mm": 30,
                    "start_angle_deg": 0,
                    "end_angle_deg": 180,
                    "rotation_angle_deg": 15,
                },
            ),
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.elliptical_arc_with_length",
                arguments={
                    "alias": "ellipse-length",
                    "center": {"alias": "A"},
                    "radius1_mm": 60,
                    "radius2_mm": 30,
                    "start_angle_deg": 0,
                    "length_mm": 50,
                    "rotation_angle_deg": 15,
                },
            ),
        ]
    )
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created] == [
        "arc-start",
        "arc-end",
        "arc-length",
        "ellipse",
        "ellipse-length",
    ]
    project.commit(preview.token)
    pattern = (project.root / "pattern/main.val").read_text(encoding="utf-8")
    assert pattern.count('type="simple"') >= 3
    assert 'type="arcWithLength"' in pattern
    assert 'type="ellipticalArcWithLength"' in pattern
    records = read_json(project.root / ".garmentcad/aliases.json")["objects"]
    aliases = {record["alias"] for record in records.values()}
    assert aliases == {"arc-start", "arc-end", "arc-length", "ellipse", "ellipse-length"}


def test_native_cubic_bezier_and_curve_intersection(tmp_path):
    project = Project.create(tmp_path / "bezier-intersection")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "B",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "C",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "D",
                "base_point": {"alias": "B"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.cubic_bezier",
            arguments={
                "alias": "bezier-up",
                "point1": {"alias": "A"},
                "point2": {"alias": "B"},
                "point3": {"alias": "C"},
                "point4": {"alias": "D"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.cubic_bezier",
            arguments={
                "alias": "bezier-down",
                "point1": {"alias": "C"},
                "point2": {"alias": "D"},
                "point3": {"alias": "A"},
                "point4": {"alias": "B"},
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.cubic_bezier_path",
            arguments={
                "alias": "bezier-path",
                "points": [
                    {"alias": "A"},
                    {"alias": "B"},
                    {"alias": "D"},
                    {"alias": "C"},
                ],
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.point_of_intersection_curves",
            arguments={
                "alias": "bezier-cross",
                "first_curve": {"alias": "bezier-up"},
                "second_curve": {"alias": "bezier-down"},
                "vertical_solution": 1,
                "horizontal_solution": 1,
            },
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created[-4:]] == [
        "bezier-up",
        "bezier-down",
        "bezier-path",
        "bezier-cross",
    ]
    project.commit(preview.token)
    pattern = (project.root / "pattern/main.val").read_text(encoding="utf-8")
    assert pattern.count('type="cubicBezier"') == 2
    assert 'type="cubicBezierPath"' in pattern
    assert 'name="bezier-cross"' in pattern


def test_native_spline_path_and_cut_handlers(tmp_path):
    project = Project.create(tmp_path / "curve-cuts")
    operations = [
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "B",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 0,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "C",
                "base_point": {"alias": "A"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.end_line",
            arguments={
                "alias": "D",
                "base_point": {"alias": "B"},
                "length_mm": 100,
                "angle_deg": 90,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.arc",
            arguments={
                "alias": "arc",
                "center": {"alias": "A"},
                "radius_mm": 100,
                "start_angle_deg": 0,
                "end_angle_deg": 180,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.spline",
            arguments={
                "alias": "spline",
                "point1": {"alias": "B"},
                "point4": {"alias": "C"},
                "angle1_deg": 90,
                "angle2_deg": 0,
                "length1_mm": 40,
                "length2_mm": 40,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.spline_path",
            arguments={
                "alias": "path",
                "points": [
                    {
                        "point": {"alias": alias},
                        "angle1_deg": 180,
                        "angle2_deg": 0,
                        "length1_mm": 30,
                        "length2_mm": 30,
                    }
                    for alias in ("A", "B", "D", "C")
                ],
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.cut_arc",
            arguments={"alias": "arc-cut", "curve": {"alias": "arc"}, "length_mm": 50},
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.cut_spline",
            arguments={
                "alias": "spline-cut",
                "curve": {"alias": "spline"},
                "length_mm": 50,
            },
        ),
        Operation(
            domain=OperationDomain.PATTERN,
            action="pattern.cut_spline_path",
            arguments={"alias": "path-cut", "curve": {"alias": "path"}, "length_mm": 50},
        ),
    ]
    preview = project.preview(operations=operations)
    assert preview.ok
    assert [item.alias for item in preview.summary.created[-4:]] == [
        "path",
        "arc-cut",
        "spline-cut",
        "path-cut",
    ]
    project.commit(preview.token)
    pattern = (project.root / "pattern/main.val").read_text(encoding="utf-8")
    assert 'type="pathInteractive"' in pattern
    assert 'type="cutArc"' in pattern
    assert 'type="cutSpline"' in pattern
    assert 'type="cutSplinePath"' in pattern


def test_native_update_delete_and_alias_survive_reopen(tmp_path):
    project = Project.create(tmp_path / "lifecycle")
    created = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.end_line",
                arguments={
                    "alias": "B",
                    "base_point": {"alias": "A"},
                    "length_mm": 80,
                    "angle_deg": 0,
                },
            )
        ]
    )
    project.commit(created.token)

    updated = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.object_update",
                target={"alias": "B"},
                arguments={"alias": "front.shoulder", "name": "B2"},
            )
        ]
    )
    project.commit(updated.token)
    reopened = Project.open(project.root)
    records = read_json(reopened.root / ".garmentcad/aliases.json")["objects"]
    assert next(iter(records.values()))["alias"] == "front.shoulder"
    assert 'name="B2"' in (reopened.root / "pattern/main.val").read_text(encoding="utf-8")

    deleted = reopened.preview(
        operations=[
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.object_delete",
                target={"alias": "front.shoulder"},
            )
        ]
    )
    assert deleted.ok
    reopened.commit(deleted.token)
    assert 'name="B2"' not in (reopened.root / "pattern/main.val").read_text(encoding="utf-8")
    assert next(iter(read_json(reopened.root / ".garmentcad/aliases.json")["objects"].values()))[
        "deleted"
    ]


def test_native_formula_increments_and_final_measurements(tmp_path):
    project = Project.create(tmp_path / "formulas")
    preview = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.PATTERN,
                action="pattern.formula_evaluate",
                arguments={"formula": "2+3"},
            ),
            Operation(
                domain=OperationDomain.MEASUREMENTS,
                action="measurement.increment_set",
                arguments={"name": "#ease", "value_mm": 25, "description": "wearing ease"},
            ),
            Operation(
                domain=OperationDomain.MEASUREMENTS,
                action="measurement.final_measurement_set",
                arguments={
                    "name": "finished_width",
                    "formula": "#ease * 2",
                    "description": "finished width allowance",
                },
            ),
        ]
    )
    assert preview.ok
    assert preview.summary.measurements["formula.value_mm"] == pytest.approx(50)
    assert preview.summary.measurements["#ease"] == pytest.approx(25)
    project.commit(preview.token)
    pattern = (project.root / "pattern/main.val").read_text(encoding="utf-8")
    assert 'name="#ease"' in pattern
    assert 'name="finished_width"' in pattern

    removed = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.MEASUREMENTS,
                action="measurement.increment_remove",
                arguments={"name": "#ease"},
            )
        ]
    )
    assert removed.ok
