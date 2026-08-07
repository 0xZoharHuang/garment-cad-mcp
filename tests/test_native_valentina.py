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
