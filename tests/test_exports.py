from __future__ import annotations

import json
from pathlib import Path

import pytest

from garmentcad.artifacts import ArtifactStore
from garmentcad.exports import export_garmentcode, triangulate_polygon
from garmentcad.garmentcode_facade import GarmentCodeFacade
from garmentcad.project import Project
from garmentcad.sdk import GarmentSDK

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True, scope="module")
def native_garmentcode():
    try:
        GarmentCodeFacade().service_info()
    except Exception as error:
        pytest.skip(f"native GarmentCode host unavailable: {error}")


def test_ear_clipping_handles_concave_panels():
    points = [[0, 0], [100, 0], [100, 100], [50, 40], [0, 100]]
    faces = triangulate_polygon(points)
    assert len(faces) == len(points) - 2
    assert {index for face in faces for index in face} == set(range(len(points)))


def test_json_obj_usd_exports_are_native_placed_and_content_addressed(tmp_path):
    project = Project.create(tmp_path / "exports")
    sdk = GarmentSDK(project.root)
    preview = sdk.panel_create(
        "front",
        [[0, 0], [100, 0], [100, 100], [50, 40], [0, 100]],
        translation_mm=[10, 20, 30],
        rotation_deg=[0, 90, 0],
    )
    project.commit(preview.preview_token)

    first = sdk.export_garmentcode()
    second = export_garmentcode(project, ["json", "obj", "usd"])
    assert first["revision"] == 1
    assert first["resources"] == second["resources"]
    assert first["diagnostics"]["roundtrip_ok"] is True

    store = ArtifactStore(project.root)
    payloads = {}
    for format_name, uri in first["resources"].items():
        path, metadata = store.resolve(uri.rsplit("/", 1)[-1])
        payloads[format_name] = path.read_bytes()
        assert metadata["revision"] == 1
        assert metadata["kind"] == "garmentcode_export"
        assert metadata["metadata"]["format"] == format_name

    document = json.loads(payloads["json"])
    assert document["pattern"]["panels"]["front"]["translation"] == [1.0, 2.0, 3.0]
    obj = payloads["obj"].decode()
    assert obj.count("\nv ") == 5
    assert obj.count("\nf ") == 3
    assert "v 10 20 30" in obj
    usd = payloads["usd"].decode()
    assert usd.startswith("#usda 1.0")
    assert "metersPerUnit = 0.001" in usd
    assert "faceVertexCounts = [3, 3, 3]" in usd


def test_native_mesh_samples_curved_edges():
    assembly = {
        "schema_version": "1.0",
        "units": "mm",
        "panels": {
            "curved": {
                "id": "curved",
                "alias": "curved",
                "vertices_mm": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "edges": [
                    {
                        "id": "curve",
                        "start": 0,
                        "end": 1,
                        "curve": {
                            "type": "cubic",
                            "params": [[0.25, -0.2], [0.75, -0.2]],
                        },
                    },
                    {"id": "b", "start": 1, "end": 2},
                    {"id": "c", "start": 2, "end": 3},
                    {"id": "d", "start": 3, "end": 0},
                ],
                "translation_mm": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
            }
        },
        "interfaces": {},
        "stitches": {},
        "components": {},
    }
    panels, diagnostics = GarmentCodeFacade().mesh(assembly)
    assert diagnostics["mesh_panels"] == 1
    assert len(panels[0]["boundary_2d_mm"]) == 13
    assert min(point[1] for point in panels[0]["boundary_2d_mm"]) < 0
