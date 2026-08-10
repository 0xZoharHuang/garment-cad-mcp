from __future__ import annotations

import json

import pytest
from v2_helpers import commit_sync

from garmentcad.artifacts import ArtifactStore
from garmentcad.exports import export_garmentcode
from garmentcad.garmentcode_facade import GarmentCodeFacade
from garmentcad.models import ObjectRef, Operation, OperationDomain
from garmentcad.project import Project


@pytest.fixture(autouse=True, scope="module")
def native_garmentcode():
    try:
        GarmentCodeFacade().service_info()
    except Exception as error:
        pytest.skip(f"native GarmentCode host unavailable: {error}")


def test_json_obj_usd_exports_are_native_and_content_addressed(tmp_path):
    project = Project.create(tmp_path / "exports")
    commit_sync(project, "front")
    placement = project.preview(
        operations=[
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="panel.transform",
                target=ObjectRef(alias="front"),
                arguments={"translation_mm": [10, 20, 30], "rotation_deg": [0, 90, 0]},
            )
        ]
    )
    project.commit(placement.token)

    first = export_garmentcode(project, ["json", "obj", "usd"])
    second = export_garmentcode(project, ["json", "obj", "usd"])
    assert first["resources"] == second["resources"]
    assert first["provenance"]["engine"] == "GarmentCode"

    store = ArtifactStore(project.root)
    payloads = {}
    for format_name, uri in first["resources"].items():
        path, metadata = store.resolve(uri.rsplit("/", 1)[-1])
        payloads[format_name] = path.read_bytes()
        assert metadata["revision"] == 2
        assert metadata["metadata"]["native_engine"] == "GarmentCode"

    document = json.loads(payloads["json"])
    assert document["pattern"]["panels"]["front"]["translation"] == [1.0, 2.0, 3.0]
    assert payloads["obj"].decode().count("\nf ") == 2
    assert "v 10 20 30" in payloads["obj"].decode()
    usd = payloads["usd"].decode()
    assert usd.startswith("#usda 1.0")
    assert "metersPerUnit = 0.001" in usd


def test_exports_refuse_stale_valentina_projection(tmp_path):
    project = Project.create(tmp_path / "stale-export")
    commit_sync(project, "front")
    pattern = project.root / project.manifest.pattern_file
    pattern.write_bytes(pattern.read_bytes() + b"\n<!-- GUI edit -->\n")
    with pytest.raises(Exception, match="not bound to the current native Valentina pattern"):
        export_garmentcode(project, ["json"])
