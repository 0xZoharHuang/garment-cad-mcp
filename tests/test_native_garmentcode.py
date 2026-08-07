from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from garmentcad.assembly import apply_operations, empty_assembly
from garmentcad.garmentcode_facade import GarmentCodeFacade
from garmentcad.models import ObjectRef, Operation, OperationDomain

REPOSITORY = Path(__file__).resolve().parents[1]
COMPAT_PYTHON = REPOSITORY / "build/garmentcode-venv/bin/python"
GARMENTCODE = REPOSITORY / "upstream/garmentcode"
WARP = REPOSITORY / "upstream/nvidia-warp-garmentcode"


def operation(action: str, **arguments) -> Operation:
    return Operation(domain=OperationDomain.ASSEMBLY, action=action, arguments=arguments)


@pytest.fixture(scope="module")
def facade() -> GarmentCodeFacade:
    if not COMPAT_PYTHON.is_file():
        pytest.skip("run scripts/bootstrap-macos.sh to create the GarmentCode environment")
    value = GarmentCodeFacade(str(REPOSITORY / "scripts/garmentcode-command-host.sh"))
    try:
        value.service_info()
    except Exception as error:
        pytest.skip(f"native GarmentCode host unavailable: {error}")
    return value


def test_pinned_native_classes_and_units(facade: GarmentCodeFacade):
    info = facade.service_info()
    assert info["application"] == "GarmentCode"
    assert info["units"] == {"public": "mm", "native": "cm"}
    assert set(info["native_classes"]) == {
        "Panel",
        "Edge",
        "EdgeSequence",
        "Interface",
        "Component",
    }


def test_native_conversion_preserves_units_placement_curve_and_roundtrip(
    facade: GarmentCodeFacade,
):
    state, summary = apply_operations(
        empty_assembly(),
        [
            operation(
                "panel.create",
                alias="front",
                vertices_mm=[[0, 0], [100, 0], [100, 200], [0, 200]],
            ),
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="panel.transform",
                target=ObjectRef(alias="front"),
                arguments={
                    "translation_mm": [10, 20, 30],
                    "rotation_deg": [1, 2, 3],
                },
            ),
        ],
    )
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    edge = next(iter(state["panels"].values()))["edges"][0]
    edge["curve"] = {
        "type": "cubic",
        "params": [[0.25, 0.10], [0.75, 0.10]],
    }
    converted, diagnostics = facade.convert(state)
    panel = converted["pattern"]["panels"]["front"]
    assert panel["vertices"][1] == [10.0, 0.0]
    assert panel["translation"] == [1.0, 2.0, 3.0]
    assert panel["edges"][0]["curvature"]["type"] == "cubic"
    assert diagnostics["roundtrip_ok"] is True
    assert converted["parameters"] == {}
    assert converted["parameter_order"] == []
    assert diagnostics["panels"]["front"] == {
        "edge_count": 4,
        "closed": True,
        "chained": True,
        "self_intersecting": False,
    }


def test_native_stitch_rule_matches_different_edge_partitions(facade: GarmentCodeFacade):
    state, summary = apply_operations(
        empty_assembly(),
        [
            operation(
                "panel.create",
                alias="left",
                vertices_mm=[[0, 0], [100, 0], [100, 50], [0, 50]],
            ),
            operation(
                "panel.create",
                alias="right",
                vertices_mm=[[0, 0], [50, 0], [100, 0], [100, 50], [0, 50]],
            ),
            operation(
                "interface.define",
                alias="left.seam",
                panel={"alias": "left"},
                edge_indices=[0],
                ruffle=1.0,
                right_wrong=False,
            ),
            operation(
                "interface.define",
                alias="right.seam",
                panel={"alias": "right"},
                edge_indices=[0, 1],
                reverse=True,
            ),
            operation(
                "stitch.create",
                alias="side",
                interface_a={"alias": "left.seam"},
                interface_b={"alias": "right.seam"},
                direction="opposed",
            ),
        ],
    )
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    converted, diagnostics = facade.convert(state)
    assert len(converted["pattern"]["stitches"]) == 2
    assert diagnostics["stitches"]["side"] == {
        "native_matching": True,
        "edge_pairs": 2,
        "direction": "opposed",
    }


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
document = {
    'pattern': pattern,
    'parameters': {},
    'parameter_order': [],
    'properties': {
        'units_in_meter': 100,
        'curvature_coords': 'relative',
        'normalize_panel_translation': False,
        'normalized_edge_loops': True,
    },
}
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / 'tshirt_specification.json'
    path.write_text(json.dumps(document))
    mesh = BoxMesh(path, 1.0)
    mesh.load()
print(json.dumps({
    'panels': len(pattern['panels']),
    'stitches': len(pattern['stitches']),
    'self_intersecting': garment.is_self_intersecting(),
    'mesh_vertices': len(mesh.vertices),
    'mesh_faces': len(mesh.faces),
}))
"""
    program = subprocess.run(
        [str(COMPAT_PYTHON), "-c", source],
        cwd=GARMENTCODE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert program.returncode == 0, program.stderr
    report = json.loads(program.stdout.splitlines()[-1])
    assert report["panels"] == 8
    assert report["stitches"] == 16
    assert report["self_intersecting"] is False
    assert report["mesh_vertices"] > 7_000
    assert report["mesh_faces"] > 14_000
    gui_import = subprocess.run(
        [str(COMPAT_PYTHON), "-c", "import gui.callbacks, gui.gui_pattern"],
        cwd=GARMENTCODE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert gui_import.returncode == 0, gui_import.stderr
