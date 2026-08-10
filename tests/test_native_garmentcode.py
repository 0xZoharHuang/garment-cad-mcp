from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from v2_helpers import snapshot

from garmentcad.garmentcode_facade import GarmentCodeFacade
from garmentcad.models import ObjectRef, Operation, OperationDomain

REPOSITORY = Path(__file__).resolve().parents[1]
COMPAT_PYTHON = REPOSITORY / "build/garmentcode-venv/bin/python"
GARMENTCODE = REPOSITORY / "upstream/garmentcode"
WARP = REPOSITORY / "upstream/nvidia-warp-garmentcode"


@pytest.fixture(scope="module")
def facade() -> GarmentCodeFacade:
    if not COMPAT_PYTHON.is_file():
        pytest.skip("run scripts/bootstrap-macos.sh to create the GarmentCode environment")
    value = GarmentCodeFacade(str(REPOSITORY / "scripts/garmentcode-command-host.sh"))
    value.service_info()
    return value


def test_pinned_native_classes_units_and_v2_document(facade: GarmentCodeFacade, tmp_path):
    info = facade.service_info()
    assert info["protocol_version"] == "2.0"
    assert info["units"] == {"public": "mm", "native": "cm"}
    assert "GarmentDocument" in info["native_classes"]
    created = facade.create_document(tmp_path / "native.json", "project")
    assert created["provenance"]["engine"] == "GarmentCode"
    facade.create_document(tmp_path / "seed.json", "")
    generated = json.loads((tmp_path / "seed.json").read_text())
    generated["source_project_id"] = None
    template = json.loads(
        (REPOSITORY / "src/garmentcad/templates/empty.garmentcode.json").read_text()
    )
    assert generated == template


def test_native_document_sync_transform_stitch_and_roundtrip(facade: GarmentCodeFacade, tmp_path):
    source = tmp_path / "source.json"
    candidate = tmp_path / "candidate.json"
    facade.create_document(source, "project")
    bindings = {
        "interfaces": [
            {"alias": "front.side", "edges": ["front.edge.1"]},
            {"alias": "back.side", "edges": ["back.edge.1"], "reverse": True},
        ],
        "stitches": [
            {
                "alias": "side",
                "interface_a": "front.side",
                "interface_b": "back.side",
                "direction": "opposed",
            }
        ],
    }
    operations = [
        Operation(
            domain=OperationDomain.ASSEMBLY,
            action="assembly.sync_from_pattern",
            arguments={
                "snapshot": snapshot("front", "back"),
                "bindings": bindings,
                "source_project_id": "project",
                "source_pattern_hash": "a" * 64,
            },
        ),
        Operation(
            domain=OperationDomain.ASSEMBLY,
            action="panel.transform",
            target=ObjectRef(alias="front"),
            arguments={"translation_mm": [10, 20, 30], "rotation_deg": [1, 2, 3]},
        ),
    ]
    summary, result = facade.preview_document(source, candidate, operations)
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    state = json.loads(candidate.read_text())
    assert state["engine"] == "GarmentCode"
    assert state["native_pattern"]["pattern"]["panels"]["front"]["translation"] == [1, 2, 3]
    assert len(state["native_pattern"]["pattern"]["stitches"]) == 1
    assert result["diagnostics"]["stitches"]["side"]["native_matching"] is True


def test_resync_preserves_sewing_semantics_by_valentina_edge_alias(
    facade: GarmentCodeFacade, tmp_path
):
    source = tmp_path / "source.json"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    facade.create_document(source, "project")
    bindings = {
        "interfaces": [
            {"alias": "a", "edges": ["front.edge.0"]},
            {"alias": "b", "edges": ["back.edge.0"]},
        ],
        "stitches": [{"alias": "seam", "interface_a": "a", "interface_b": "b"}],
    }
    sync = Operation(
        domain=OperationDomain.ASSEMBLY,
        action="assembly.sync_from_pattern",
        arguments={
            "snapshot": snapshot("front", "back"),
            "bindings": bindings,
            "source_project_id": "project",
            "source_pattern_hash": "1" * 64,
        },
    )
    facade.preview_document(source, first, [sync])
    resync = sync.model_copy(
        update={
            "arguments": {
                **sync.arguments,
                "bindings": {},
                "source_pattern_hash": "2" * 64,
            }
        }
    )
    facade.preview_document(first, second, [resync])
    state = json.loads(second.read_text())
    assert len(state["interfaces"]) == 2
    assert len(state["stitches"]) == 1


def test_official_tshirt_program_and_gui_import_remain_compatible():
    if not COMPAT_PYTHON.is_file():
        pytest.skip("run scripts/bootstrap-macos.sh to create the GarmentCode environment")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(GARMENTCODE), str(WARP)])
    source = """
import json, tempfile, yaml
from pathlib import Path
from assets.bodies.body_params import BodyParameters
from assets.garment_programs.meta_garment import MetaGarment
from pygarment.meshgen.boxmeshgen import BoxMesh
body = BodyParameters('assets/bodies/mean_all.yaml')
with open('assets/design_params/t-shirt.yaml') as stream:
    design = yaml.safe_load(stream)['design']
garment = MetaGarment('t-shirt', body, design)
pattern = garment.assembly().pattern
document = {'pattern': pattern, 'parameters': {}, 'parameter_order': [], 'properties': {
    'units_in_meter': 100, 'curvature_coords': 'relative',
    'normalize_panel_translation': False, 'normalized_edge_loops': True}}
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / 'tshirt.json'; path.write_text(json.dumps(document))
    mesh = BoxMesh(path, 1.0); mesh.load()
print(json.dumps({'panels': len(pattern['panels']), 'stitches': len(pattern['stitches']),
                  'mesh_vertices': len(mesh.vertices), 'mesh_faces': len(mesh.faces)}))
"""
    program = subprocess.run(
        [str(COMPAT_PYTHON), "-c", source], cwd=GARMENTCODE, env=environment,
        capture_output=True, text=True, timeout=60, check=False
    )
    assert program.returncode == 0, program.stderr
    report = json.loads(program.stdout.splitlines()[-1])
    assert report["panels"] == 8 and report["stitches"] == 16
    assert report["mesh_vertices"] > 7_000 and report["mesh_faces"] > 14_000
    gui = subprocess.run(
        [str(COMPAT_PYTHON), "-c", "import gui.callbacks, gui.gui_pattern"],
        cwd=GARMENTCODE, env=environment, capture_output=True, text=True, timeout=60,
        check=False,
    )
    assert gui.returncode == 0, gui.stderr
