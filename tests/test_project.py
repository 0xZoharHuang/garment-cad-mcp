from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from v2_helpers import commit_sync, sync_operation

import garmentcad.project as project_module
from garmentcad.errors import ChangeSetIntegrityError, ProjectLockedError, StaleRevisionError
from garmentcad.locking import ProjectLock
from garmentcad.models import AliasRecord, AliasRegistry, ObjectRef, Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.storage import read_json


def test_native_truth_preview_commit_units_and_binding(tmp_path):
    project = Project.create(tmp_path / "dress")
    assembly_path = project.root / project.manifest.assembly_file
    initial = json.loads(assembly_path.read_text())
    assert initial["engine"] == "GarmentCode" and initial["panels"] == {}
    preview = project.preview(operations=[sync_operation(project, "front")])
    assert preview.ok and project.current_revision == 0
    assert json.loads(assembly_path.read_text())["panels"] == {}
    project.commit(preview.token)
    native = json.loads(assembly_path.read_text())
    assert native["native_pattern"]["pattern"]["panels"]["front"]["vertices"][1] == [10, 0]
    assert project.status()["assembly_binding"]["current"] is True


def test_import_existing_valentina_files_preserves_native_bytes(tmp_path):
    source = Path("upstream/valentina/src/app/share/collection/MaleShirt/MaleShirt.val")
    measurement = source.with_suffix(".vit")
    project = Project.import_valentina(source, tmp_path / "imported")
    assert (project.root / project.manifest.pattern_file).read_bytes() == source.read_bytes()
    imported = project.root / f"measurements/{measurement.name}"
    assert imported.read_bytes() == measurement.read_bytes()
    assert project.status()["externally_modified"] is False


def test_interfaces_stitches_and_reverse_revision(tmp_path):
    project = Project.create(tmp_path / "shirt")
    commit_sync(project, "front", "back")
    interfaces = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="interface.define",
                arguments={"alias": f"{name}.side", "panel": {"alias": name}, "edge_indices": [1]},
            )
            for name in ("front", "back")
        ]
    )
    project.commit(interfaces.token)
    seam = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="stitch.create",
                arguments={
                    "alias": "side",
                    "interface_a": {"alias": "front.side"},
                    "interface_b": {"alias": "back.side"},
                },
            )
        ]
    )
    project.commit(seam.token)
    assert len(read_json(project.root / project.manifest.assembly_file)["stitches"]) == 1
    project.revert(3)
    assert len(read_json(project.root / project.manifest.assembly_file)["stitches"]) == 0


def test_invalid_native_operation_is_a_structured_noncommittable_preview(tmp_path):
    project = Project.create(tmp_path / "bad")
    result = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="interface.define",
                arguments={"alias": "missing", "panel": {"alias": "none"}, "edge_indices": [0]},
            )
        ]
    )
    assert not result.ok
    assert result.summary.issues[0].code == "invalid_garmentcode_operation"
    with pytest.raises(ValueError, match="validation errors"):
        project.commit(result.token)


def test_stale_revision_and_external_gui_edits_reject_preview(tmp_path):
    project = Project.create(tmp_path / "stale")
    stale = project.preview(operations=[sync_operation(project, "front")])
    fresh = project.preview(operations=[sync_operation(project, "back")])
    project.commit(fresh.token)
    with pytest.raises(StaleRevisionError):
        project.commit(stale.token)

    preview = project.preview(operations=[sync_operation(project, "front")])
    pattern = project.root / project.manifest.pattern_file
    pattern.write_bytes(pattern.read_bytes() + b"\n<!-- GUI save -->\n")
    assert Project.open(project.root).status()["externally_modified"] is True
    with pytest.raises(StaleRevisionError, match="possibly through a GUI"):
        Project.open(project.root).commit(preview.token)


def test_preview_candidate_integrity_discard_and_writer_lock(tmp_path):
    project = Project.create(tmp_path / "integrity")
    preview = project.preview(operations=[sync_operation(project, "front")])
    candidate = (
        project.root
        / f".garmentcad/changesets/{preview.token}/assembly/main.garmentcode.json"
    )
    candidate.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ChangeSetIntegrityError, match="changed after validation"):
        project.commit(preview.token)

    clean = project.preview(operations=[sync_operation(project, "back")])
    project.discard(clean.token)
    with pytest.raises(ChangeSetIntegrityError, match="already discarded"):
        project.commit(clean.token)

    locked = project.preview(operations=[sync_operation(project, "front")])
    with ProjectLock(project.root / ".garmentcad/project.lock"):
        with pytest.raises(ProjectLockedError):
            project.commit(locked.token)


def test_alias_registry_is_strict_and_revision_content(tmp_path):
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


def test_gui_session_records_native_file_change_as_reversible_revision(tmp_path):
    project = Project.create(tmp_path / "gui-session")
    repository = Path(__file__).resolve().parents[1]
    pattern = project.root / project.manifest.pattern_file
    original = pattern.read_bytes()
    script = (
        f"from pathlib import Path; p=Path({str(pattern)!r}); "
        "p.write_bytes(p.read_bytes()+b'\\n<!-- GUI -->\\n')"
    )
    process = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts/gui-session.py"),
            "--project",
            str(project.root),
            "--",
            sys.executable,
            "-c",
            script,
        ],
        cwd=repository, capture_output=True, text=True, check=False,
    )
    assert process.returncode == 0, process.stderr
    reopened = Project.open(project.root)
    assert reopened.current_revision == 1
    reopened.revert(1)
    assert pattern.read_bytes() == original


def test_commit_failure_restores_both_native_truth_files(tmp_path, monkeypatch):
    project = Project.create(tmp_path / "rollback")
    preview = project.preview(operations=[sync_operation(project, "front")])
    manifest_before = (project.root / "garment.json").read_bytes()
    assembly = project.root / project.manifest.assembly_file
    assembly_before = assembly.read_bytes()
    original_write = project_module.atomic_write_json

    def fail_manifest(path, value):
        if path == project.root / "garment.json" and value.get("current_revision") == 1:
            raise OSError("injected manifest failure")
        return original_write(path, value)

    monkeypatch.setattr(project_module, "atomic_write_json", fail_manifest)
    with pytest.raises(OSError, match="injected"):
        project.commit(preview.token)
    assert (project.root / "garment.json").read_bytes() == manifest_before
    assert assembly.read_bytes() == assembly_before
    change = read_json(project.root / f".garmentcad/changesets/{preview.token}.json")
    assert change["status"] == "preview"
