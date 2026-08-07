from __future__ import annotations

import json

import pytest

from garmentcad.assembly import to_garmentcode
from garmentcad.errors import StaleRevisionError
from garmentcad.models import AliasRecord, AliasRegistry, ObjectRef, Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.sdk import GarmentSDK


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
