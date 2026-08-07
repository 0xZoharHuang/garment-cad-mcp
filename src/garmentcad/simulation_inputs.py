from __future__ import annotations

from pathlib import Path

from garmentcad.models import (
    ChangeSummary,
    ObjectRef,
    Operation,
    ProjectManifest,
    SimulationCameraConfig,
    ValidationIssue,
)
from garmentcad.storage import atomic_write_bytes, read_json

SIMULATION_MANIFEST_FIELDS = {
    "body_mesh": "active_body",
    "body_measurements": "active_body_measurements",
    "body_segmentation": "active_body_segmentation",
    "fabric": "active_fabric",
    "simulation_config": "active_simulation_config",
    "camera_config": "active_camera_config",
}

SIMULATION_DESTINATIONS = {
    "body_mesh": "simulation/bodies",
    "body_measurements": "simulation/bodies",
    "body_segmentation": "simulation/bodies",
    "fabric": "simulation/fabrics",
    "simulation_config": "simulation/config",
    "camera_config": "simulation/cameras",
}


def preview_simulation_configuration(
    project_root: Path, preview_root: Path, operations: list[Operation]
) -> tuple[ProjectManifest, ChangeSummary]:
    manifest = ProjectManifest.model_validate(read_json(project_root / "garment.json"))
    summary = ChangeSummary()
    for operation in operations:
        if operation.action != "simulation.configure":
            summary.issues.append(
                ValidationIssue(
                    severity="error",
                    code="unsupported_simulation_action",
                    message=f"Unsupported simulation action: {operation.action}",
                )
            )
            continue
        for argument, field_name in SIMULATION_MANIFEST_FIELDS.items():
            if argument not in operation.arguments:
                continue
            relative = operation.arguments[argument]
            try:
                if relative is not None:
                    relative = _stage_project_file(
                        project_root,
                        preview_root,
                        argument,
                        str(relative),
                    )
                setattr(manifest, field_name, relative)
            except Exception as error:
                summary.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="invalid_simulation_input",
                        message=str(error),
                        details={"input": argument},
                    )
                )
        summary.changed.append(ObjectRef(uuid=manifest.project_id, alias=manifest.name))
    if manifest.active_camera_config:
        try:
            staged_camera = preview_root / manifest.active_camera_config
            camera = (
                staged_camera
                if staged_camera.is_file()
                else project_root / manifest.active_camera_config
            )
            SimulationCameraConfig.model_validate(read_json(camera))
        except Exception as error:
            summary.issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_camera_config",
                    message=str(error),
                )
            )
    return manifest, summary


def _validate_project_file(project_root: Path, relative: str) -> str:
    if Path(relative).is_absolute():
        raise ValueError("Simulation inputs must use project-relative paths")
    path = (project_root / relative).resolve()
    if project_root not in path.parents or not path.is_file():
        raise FileNotFoundError(f"Simulation input is missing: {relative}")
    return str(path.relative_to(project_root))


def _stage_project_file(
    project_root: Path,
    preview_root: Path,
    input_name: str,
    value: str,
) -> str:
    source_value = Path(value)
    if not source_value.is_absolute():
        return _validate_project_file(project_root, value)
    source = source_value.resolve()
    if project_root in source.parents:
        return _validate_project_file(project_root, str(source.relative_to(project_root)))
    if not source.is_file():
        raise FileNotFoundError(f"Simulation input is missing: {value}")
    destination = Path(SIMULATION_DESTINATIONS[input_name]) / source.name
    target = preview_root / destination
    payload = source.read_bytes()
    if target.exists() and target.read_bytes() != payload:
        destination = destination.with_name(f"{input_name}-{source.name}")
        target = preview_root / destination
    atomic_write_bytes(target, payload)
    return str(destination)
