from __future__ import annotations

import pytest

from garmentcad.assembly import apply_operations, empty_assembly, to_garmentcode
from garmentcad.catalog import GARMENTCODE_TOOLS
from garmentcad.models import Operation, OperationDomain
from garmentcad.valentina_bridge import snapshot_to_assembly


def operation(action: str, **arguments) -> Operation:
    return Operation(domain=OperationDomain.ASSEMBLY, action=action, arguments=arguments)


def test_edge_split_preserves_interface_and_garmentcode_stitches():
    state, summary = apply_operations(
        empty_assembly(),
        [
            operation("panel.create", alias="a", vertices_mm=[[0, 0], [100, 0], [0, 100]]),
            operation("panel.create", alias="b", vertices_mm=[[0, 0], [100, 0], [0, 100]]),
            operation("interface.define", alias="a_seam", panel={"alias": "a"}, edge_indices=[0]),
            operation("interface.define", alias="b_seam", panel={"alias": "b"}, edge_indices=[0]),
            operation("edge.split", panel="a", edge_index=0, fractions=[0.5]),
            operation("edge.split", panel="b", edge_index=0, fractions=[0.5]),
            operation(
                "stitch.create",
                alias="seam",
                interface_a={"alias": "a_seam"},
                interface_b={"alias": "b_seam"},
            ),
        ],
    )
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    assert len(to_garmentcode(state)["pattern"]["stitches"]) == 2


def test_valentina_snapshot_and_sidecar_preserve_semantics_and_units():
    snapshot = {
        "revision": 4,
        "pieces": [
            {
                "uuid": "front-id",
                "alias": "front",
                "contour": [
                    {"x_mm": 0, "y_mm": 0, "edge_uuid": "e1", "edge_alias": "front.waist"},
                    {"x_mm": 400, "y_mm": 0, "edge_uuid": "e2", "edge_alias": "front.side"},
                    {"x_mm": 0, "y_mm": 600, "edge_uuid": "e3", "edge_alias": "front.hem"},
                ],
            },
            {
                "uuid": "back-id",
                "alias": "back",
                "contour": [
                    {"x_mm": 0, "y_mm": 0, "edge_uuid": "e4", "edge_alias": "back.waist"},
                    {"x_mm": 400, "y_mm": 0, "edge_uuid": "e5", "edge_alias": "back.side"},
                    {"x_mm": 0, "y_mm": 600, "edge_uuid": "e6", "edge_alias": "back.hem"},
                ],
            },
        ],
    }
    sidecar = {
        "interfaces": [
            {"alias": "front_side", "edges": ["front.side"]},
            {"alias": "back_side", "edges": ["back.side"]},
        ],
        "stitches": [
            {
                "alias": "side",
                "interface_a": "front_side",
                "interface_b": "back_side",
            }
        ],
    }
    assembly = snapshot_to_assembly(snapshot, sidecar)
    assert assembly["source_revision"] == 4
    assert to_garmentcode(assembly)["pattern"]["panels"]["front"]["vertices"][1] == [
        40.0,
        0.0,
    ]


@pytest.mark.parametrize(
    ("action", "arguments", "expanded_count"),
    [
        ("edge.split", {"edge_index": 0, "fractions": [0.25, 0.75]}, 3),
        (
            "dart.insert",
            {"edge_index": 0, "intake_mm": 10, "depth_mm": 25, "position": 0.5},
            4,
        ),
    ],
)
def test_edge_replacement_preserves_unrelated_uuids_and_expands_interface(
    action, arguments, expanded_count
):
    state, summary = apply_operations(
        empty_assembly(),
        [
            operation(
                "panel.create",
                alias="front",
                vertices_mm=[[0, 0], [100, 0], [100, 100], [0, 100]],
            )
        ],
    )
    assert not summary.issues
    panel_id, panel = next(iter(state["panels"].items()))
    original_ids = [edge["id"] for edge in panel["edges"]]
    state, summary = apply_operations(
        state,
        [
            operation(
                "interface.define",
                alias="hem",
                panel={"uuid": panel_id},
                edge_indices=[0],
            ),
            operation(action, panel=panel_id, **arguments),
        ],
    )
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    updated_ids = {edge["id"] for edge in state["panels"][panel_id]["edges"]}
    assert set(original_ids) <= updated_ids
    interface = next(iter(state["interfaces"].values()))
    assert len(interface["edge_ids"]) == expanded_count
    assert set(interface["edge_ids"]) <= updated_ids


def test_chamfer_preserves_every_existing_edge_uuid_and_interface():
    state, _ = apply_operations(
        empty_assembly(),
        [
            operation(
                "panel.create",
                alias="front",
                vertices_mm=[[0, 0], [100, 0], [100, 100], [0, 100]],
            )
        ],
    )
    panel_id, panel = next(iter(state["panels"].items()))
    original_ids = {edge["id"] for edge in panel["edges"]}
    state, summary = apply_operations(
        state,
        [
            operation(
                "interface.define",
                alias="side",
                panel={"uuid": panel_id},
                edge_indices=[3],
            ),
            operation(
                "edge.chamfer",
                panel=panel_id,
                vertex_index=1,
                distance_before_mm=10,
                distance_after_mm=10,
            ),
        ],
    )
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    updated_ids = {edge["id"] for edge in state["panels"][panel_id]["edges"]}
    assert original_ids <= updated_ids
    assert set(next(iter(state["interfaces"].values()))["edge_ids"]) <= updated_ids


def test_all_public_garmentcode_transformations_compose_and_validate():
    state, summary = apply_operations(
        empty_assembly(),
        [
            operation(
                "panel.create",
                alias="front",
                vertices_mm=[[0, 0], [120, 0], [120, 180], [0, 180]],
            ),
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="panel.transform",
                target={"alias": "front"},
                arguments={"translation_mm": [10, 20, 30], "rotation_deg": [0, 15, 0]},
            ),
            Operation(
                domain=OperationDomain.ASSEMBLY,
                action="panel.mirror",
                target={"alias": "front"},
                arguments={"alias": "back", "axis": "x", "origin_mm": 0},
            ),
            operation(
                "edge.extend",
                panel="front",
                edge_index=0,
                start_delta_mm=5,
                end_delta_mm=5,
            ),
            operation(
                "edge.chamfer",
                panel="front",
                vertex_index=2,
                distance_before_mm=10,
                distance_after_mm=10,
            ),
            operation(
                "dart.insert",
                panel="back",
                edge_index=0,
                intake_mm=10,
                depth_mm=20,
                position=0.5,
            ),
            operation("component.define", alias="bodice", panels=["front", "back"]),
        ],
    )
    assert not [issue for issue in summary.issues if issue.severity == "error"]
    assert {panel["alias"] for panel in state["panels"].values()} == {"front", "back"}
    assert len(state["components"]["bodice"]) == 2
    native = to_garmentcode(state)
    assert set(native["pattern"]["panels"]) == {"front", "back"}


def test_garmentcode_catalog_exposes_every_mutating_facade_action():
    expected = {
        "panel.create",
        "panel.delete",
        "panel.transform",
        "panel.mirror",
        "edge.split",
        "edge.extend",
        "edge.chamfer",
        "dart.insert",
        "component.define",
        "valentina.import",
        "interface.define",
        "interface.delete",
        "stitch.create",
        "stitch.delete",
        "validate",
    }
    assert expected <= {tool.action for tool in GARMENTCODE_TOOLS}
