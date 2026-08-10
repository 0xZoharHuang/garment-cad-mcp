from __future__ import annotations

from garmentcad.models import Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.storage import sha256_file


def snapshot(*aliases: str, revision: int = 0) -> dict:
    pieces = []
    for panel_index, alias in enumerate(aliases):
        offset = panel_index * 150.0
        pieces.append(
            {
                "uuid": f"{alias}-panel-id",
                "alias": alias,
                "contour": [
                    {
                        "x_mm": offset,
                        "y_mm": 0,
                        "edge_uuid": f"{alias}-edge-0",
                        "edge_alias": f"{alias}.edge.0",
                    },
                    {
                        "x_mm": offset + 100,
                        "y_mm": 0,
                        "edge_uuid": f"{alias}-edge-1",
                        "edge_alias": f"{alias}.edge.1",
                    },
                    {
                        "x_mm": offset + 100,
                        "y_mm": 200,
                        "edge_uuid": f"{alias}-edge-2",
                        "edge_alias": f"{alias}.edge.2",
                    },
                    {
                        "x_mm": offset,
                        "y_mm": 200,
                        "edge_uuid": f"{alias}-edge-3",
                        "edge_alias": f"{alias}.edge.3",
                    },
                ],
            }
        )
    return {"revision": revision, "units": "mm", "pieces": pieces}


def sync_operation(project: Project, *aliases: str, bindings: dict | None = None) -> Operation:
    return Operation(
        domain=OperationDomain.ASSEMBLY,
        action="assembly.sync_from_pattern",
        arguments={
            "snapshot": snapshot(*aliases, revision=project.current_revision),
            "bindings": bindings or {},
            "source_project_id": project.manifest.project_id,
            "source_pattern_hash": sha256_file(project.root / project.manifest.pattern_file),
        },
    )


def commit_sync(project: Project, *aliases: str, bindings: dict | None = None):
    preview = project.preview(operations=[sync_operation(project, *aliases, bindings=bindings)])
    project.commit(preview.token)
    return preview
