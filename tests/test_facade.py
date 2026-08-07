from __future__ import annotations

from garmentcad.assembly import apply_operations, empty_assembly, to_garmentcode
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
