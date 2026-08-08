from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import garmentcad.project as project_module
from garmentcad.assembly import to_garmentcode
from garmentcad.errors import ChangeSetIntegrityError, ProjectLockedError, StaleRevisionError
from garmentcad.locking import ProjectLock
from garmentcad.models import AliasRecord, AliasRegistry, ObjectRef, Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import GarmentSDK
from garmentcad.storage import read_json


def test_assembly_preview_commit_and_units(tmp_path):
    project = Project.create(tmp_path / "dress")
    assert (project.root / "pattern/main.val").is_file()
    sdk = GarmentSDK(project.root)
    preview = sdk.panel_create("front", [[0, 0], [400, 0], [350, 600], [0, 600]])
    assert preview.ok
    assert project.current_revision == 0
    assert json.loads((project.root / "assembly/assembly.json").read_text())["panels"] == {}

    committed = project.commit(preview.preview_token)
    assert committed.revision == 1
    assembly = json.loads((project.root / "assembly/assembly.json").read_text())
    converted = to_garmentcode(assembly)
    assert converted["pattern"]["panels"]["front"]["vertices"][1] == [40.0, 0.0]


def test_project_recipe_namespaces_stage_the_documented_atomic_contract(tmp_path):
    with Project.create(tmp_path / "recipe-contract") as project:
        project.measurements.set(name="@bust", value_mm=920)
        project.pattern.point.along_line(
            alias="front.armhole",
            first_point={"alias": "A"},
            second_point={"alias": "B"},
            length_mm=35,
        )
        project.pattern.curve.spline(alias="front.neckline")
        project.pattern.piece.create(alias="front", nodes=[])
        project.layout.place(piece="front", sheet_index=0, x_mm=0, y_mm=0)
        project.assembly.stitch(alias="side.seam")
        assert [operation.action for operation in project._pending] == [
            "measurement.set",
            "pattern.along_line",
            "pattern.spline",
            "pattern.piece",
            "layout.place",
            "stitch.create",
        ]


def test_interfaces_stitches_and_reverse_revision(tmp_path):
    project = Project.create(tmp_path / "shirt")
    operations = [
        Operation(
            domain=OperationDomain.ASSEMBLY,
            action="panel.create",
            arguments={"alias": alias, "vertices_mm": [[0, 0], [100, 0], [100, 200]]},
        )
        for alias in ("front", "back")
    ]
    first = project.preview(operations=operations)
    project.commit(first.preview_token)
    second = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="interface.define",
                arguments={
                    "alias": "front_side",
                    "panel": {"alias": "front"},
                    "edge_indices": [1],
                },
            ),
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="interface.define",
                arguments={
                    "alias": "back_side",
                    "panel": {"alias": "back"},
                    "edge_indices": [1],
                },
            ),
        ]
    )
    project.commit(second.preview_token)
    third = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="stitch.create",
                arguments={
                    "alias": "side_seam",
                    "interface_a": {"alias": "front_side"},
                    "interface_b": {"alias": "back_side"},
                },
            )
        ]
    )
    project.commit(third.preview_token)
    assembled = json.loads((project.root / "assembly/assembly.json").read_text())
    assert len(assembled["stitches"]) == 1
    assert to_garmentcode(assembled)["pattern"]["stitches"] == [
        [
            {"panel": "front", "edge": 1},
            {"panel": "back", "edge": 1},
        ]
    ]
    project.revert(3)
    assert len(json.loads((project.root / "assembly/assembly.json").read_text())["stitches"]) == 0


def test_stale_preview_is_rejected(tmp_path):
    project = Project.create(tmp_path / "coat")
    operation = Operation(
        domain=OperationDomain.ASSEMBLY,
        action="panel.create",
        arguments={"alias": "a", "vertices_mm": [[0, 0], [10, 0], [0, 10]]},
    )
    stale = project.preview(operations=[operation])
    fresh = project.preview(
        operations=[
            operation.model_copy(
                update={"id": "fresh", "arguments": {**operation.arguments, "alias": "b"}}
            )
        ]
    )
    project.commit(fresh.preview_token)
    with pytest.raises(StaleRevisionError):
        project.commit(stale.preview_token)


def test_gui_file_change_invalidates_preview_and_is_visible_on_refresh(tmp_path):
    project = Project.create(tmp_path / "gui-change")
    preview = GarmentSDK(project.root).panel_create("front", [[0, 0], [100, 0], [0, 100]])
    pattern = project.root / "pattern/main.val"
    pattern.write_bytes(pattern.read_bytes() + b"\n<!-- saved by GUI -->\n")
    refreshed = Project.open(project.root).status()
    assert refreshed["externally_modified"] is True
    with pytest.raises(StaleRevisionError, match="possibly through a GUI"):
        Project.open(project.root).commit(preview.token)


def test_invalid_interface_does_not_commit(tmp_path):
    project = Project.create(tmp_path / "bad")
    result = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="interface.define",
                arguments={
                    "alias": "missing",
                    "panel": ObjectRef(alias="none").model_dump(mode="json"),
                    "edge_indices": [0],
                },
            )
        ]
    )
    assert not result.ok


def test_alias_registry_rejects_ambiguity_and_is_revision_content(tmp_path):
    project = Project.create(tmp_path / "aliases")
    initial_hash = project.status()["content_hash"]
    registry = AliasRegistry(
        objects={
            "one": AliasRecord(uuid="one", alias="front.armhole", kind="point"),
            "two": AliasRecord(uuid="two", alias="front.armhole", kind="curve"),
        }
    )
    with pytest.raises(ValueError, match="ambiguous"):
        registry.resolve(ObjectRef(alias="front.armhole"))
    (project.root / ".garmentcad/aliases.json").write_text(
        registry.model_dump_json(indent=2), encoding="utf-8"
    )
    assert project.status()["content_hash"] != initial_hash


def test_preview_candidate_is_immutable_and_discard_is_terminal(tmp_path):
    project = Project.create(tmp_path / "immutable-preview")
    preview = GarmentSDK(project.root).panel_create(
        "front", [[0, 0], [100, 0], [100, 100], [0, 100]]
    )
    candidate = project.root / f".garmentcad/changesets/{preview.token}/assembly.json"
    candidate.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ChangeSetIntegrityError, match="changed after validation"):
        project.commit(preview.token)
    assert project.current_revision == 0

    clean = GarmentSDK(project.root).panel_create("back", [[0, 0], [80, 0], [80, 100], [0, 100]])
    project.discard(clean.token)
    with pytest.raises(ChangeSetIntegrityError, match="already discarded"):
        project.commit(clean.token)


def test_project_lock_rejects_a_second_writer(tmp_path):
    project = Project.create(tmp_path / "locked-project")
    preview = GarmentSDK(project.root).panel_create("front", [[0, 0], [100, 0], [0, 100]])
    with ProjectLock(project.root / ".garmentcad/project.lock"):
        with pytest.raises(ProjectLockedError):
            project.commit(preview.token)
    assert project.current_revision == 0


def test_gui_session_holds_project_lock_for_child_process(tmp_path):
    project = Project.create(tmp_path / "gui-session-project")
    repository = Path(__file__).resolve().parents[1]
    probe = f"""
from pathlib import Path
from garmentcad.errors import ProjectLockedError
from garmentcad.locking import ProjectLock
try:
    ProjectLock(Path({str(project.root / ".garmentcad/project.lock")!r})).acquire()
except ProjectLockedError:
    raise SystemExit(0)
raise SystemExit(1)
"""
    process = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts/gui-session.py"),
            "--project",
            str(project.root),
            "--",
            sys.executable,
            "-c",
            probe,
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert Project.open(project.root).current_revision == 0


def test_gui_session_records_changed_truth_as_reversible_revision(tmp_path):
    project = Project.create(tmp_path / "gui-save-project")
    repository = Path(__file__).resolve().parents[1]
    pattern = project.root / "pattern/main.val"
    original = pattern.read_bytes()
    save = f"""
from pathlib import Path
path = Path({str(pattern)!r})
path.write_bytes(path.read_bytes() + b'\\n<!-- GUI save -->\\n')
"""
    process = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts/gui-session.py"),
            "--project",
            str(project.root),
            "--",
            sys.executable,
            "-c",
            save,
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    reopened = Project.open(project.root)
    assert reopened.current_revision == 1
    assert reopened.status()["externally_modified"] is False
    revision = read_json(project.root / ".garmentcad/revisions/1.json")
    change = read_json(project.root / f".garmentcad/changesets/{revision['change_set_id']}.json")
    assert change["operations"][0]["action"] == "project.gui_save"
    reopened.revert(1)
    assert pattern.read_bytes() == original


def test_commit_failure_restores_truth_and_leaves_preview_retryable(tmp_path, monkeypatch):
    project = Project.create(tmp_path / "rollback-project")
    preview = GarmentSDK(project.root).panel_create("front", [[0, 0], [100, 0], [0, 100]])
    original_manifest = (project.root / "garment.json").read_bytes()
    original_assembly = (project.root / "assembly/assembly.json").read_bytes()
    original_write = project_module.atomic_write_json

    def fail_manifest(path, value):
        if path == project.root / "garment.json" and value.get("current_revision") == 1:
            raise OSError("injected manifest failure")
        return original_write(path, value)

    monkeypatch.setattr(project_module, "atomic_write_json", fail_manifest)
    with pytest.raises(OSError, match="injected manifest failure"):
        project.commit(preview.token)
    assert (project.root / "garment.json").read_bytes() == original_manifest
    assert (project.root / "assembly/assembly.json").read_bytes() == original_assembly
    assert not (project.root / ".garmentcad/revisions/1.json").exists()
    assert not (project.root / ".garmentcad/snapshots/1").exists()
    assert (
        read_json(project.root / f".garmentcad/changesets/{preview.token}.json")["status"]
        == "preview"
    )


def test_reverse_revision_is_appended_to_event_log(tmp_path):
    project = Project.create(tmp_path / "reverse-events")
    preview = GarmentSDK(project.root).panel_create("front", [[0, 0], [100, 0], [0, 100]])
    project.commit(preview.token)
    project.revert(1)
    events = [
        json.loads(line)
        for line in (project.root / ".garmentcad/events.jsonl").read_text().splitlines()
    ]
    assert [event["number"] for event in events] == [1, 2]
    assert events[-1]["reverse_of"] == 1
