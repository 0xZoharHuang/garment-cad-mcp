from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from garmentcad.artifacts import ArtifactStore
from garmentcad.garmentcode_facade import GarmentCodeFacade
from garmentcad.project import Project

SUPPORTED_GARMENTCODE_EXPORTS = {"json", "obj", "usd"}


def export_garmentcode(
    project: Project | str | Path, formats: list[str] | None = None
) -> dict[str, Any]:
    """Store native GarmentCode exports as content-addressed project derivatives."""
    project = project if isinstance(project, Project) else Project.open(project)
    project.assert_assembly_current()
    requested = list(dict.fromkeys(formats or ["json", "obj", "usd"]))
    unsupported = sorted(set(requested) - SUPPORTED_GARMENTCODE_EXPORTS)
    if unsupported:
        raise ValueError(f"Unsupported GarmentCode export formats: {unsupported}")
    source = project.root / project.manifest.assembly_file
    with tempfile.TemporaryDirectory(prefix="garmentcode-export-") as temporary:
        native = GarmentCodeFacade().export_document(source, Path(temporary), requested)
        store = ArtifactStore(project.root)
        resources = {
            format_name: store.put(
                Path(record["path"]).read_bytes(),
                filename=Path(record["path"]).name,
                kind="garmentcode_export",
                revision=project.current_revision,
                metadata={
                    "project_id": project.manifest.project_id,
                    "format": format_name,
                    "native_sha256": record["sha256"],
                    "native_engine": native["provenance"]["engine"],
                },
            )
            for format_name, record in native["files"].items()
        }
    return {
        "ok": True,
        "revision": project.current_revision,
        "resources": resources,
        "diagnostics": native["diagnostics"],
        "provenance": native["provenance"],
    }
