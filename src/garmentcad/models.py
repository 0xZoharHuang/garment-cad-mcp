from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class OperationDomain(StrEnum):
    PROJECT = "project"
    PATTERN = "pattern"
    MEASUREMENTS = "measurements"
    LAYOUT = "layout"
    ASSEMBLY = "assembly"
    SIMULATION = "simulation"
    EXPORT = "export"


class ObjectRef(BaseModel):
    uuid: str | None = None
    alias: str | None = None

    def display(self) -> str:
        return self.alias or self.uuid or "<unresolved>"


class AliasRecord(BaseModel):
    uuid: str
    alias: str
    domain: OperationDomain | None = None
    kind: str
    native_id: int | str | None = None
    deleted: bool = False


class AliasRegistry(BaseModel):
    schema_version: str = "1.0"
    objects: dict[str, AliasRecord] = Field(default_factory=dict)

    def resolve(self, reference: ObjectRef) -> AliasRecord:
        if reference.uuid:
            record = self.objects.get(reference.uuid)
            if record is None or record.deleted:
                raise KeyError(f"Unknown object UUID: {reference.uuid}")
            return record
        matches = [
            record
            for record in self.objects.values()
            if not record.deleted and record.alias == reference.alias
        ]
        if not matches:
            raise KeyError(f"Unknown object alias: {reference.alias}")
        if len(matches) > 1:
            raise ValueError(f"Alias is ambiguous: {reference.alias}")
        return matches[0]


class Operation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    domain: OperationDomain
    action: str
    target: ObjectRef | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    objects: list[ObjectRef] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ChangeSummary(BaseModel):
    created: list[ObjectRef] = Field(default_factory=list)
    changed: list[ObjectRef] = Field(default_factory=list)
    deleted: list[ObjectRef] = Field(default_factory=list)
    measurements: dict[str, float] = Field(default_factory=dict)
    issues: list[ValidationIssue] = Field(default_factory=list)


class ChangeSet(BaseModel):
    schema_version: str = "1.0"
    id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    base_revision: int
    base_content_hash: str
    preview_content_hash: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    author: str = "agent"
    message: str = ""
    operations: list[Operation]
    summary: ChangeSummary = Field(default_factory=ChangeSummary)
    preview_resources: list[str] = Field(default_factory=list)
    status: Literal["preview", "committed", "discarded"] = "preview"


class Revision(BaseModel):
    schema_version: str = "1.0"
    number: int
    parent: int | None
    change_set_id: str
    committed_at: datetime = Field(default_factory=utc_now)
    author: str
    message: str
    content_hash: str
    reverse_of: int | None = None


class ProjectManifest(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    units: Literal["mm"] = "mm"
    current_revision: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    pattern_file: str = "pattern/main.val"
    assembly_file: str = "assembly/main.garmentcode.json"
    measurement_files: list[str] = Field(default_factory=list)
    active_body: str | None = None
    active_body_measurements: str | None = None
    active_body_segmentation: str | None = None
    active_fabric: str | None = None
    active_simulation_config: str | None = None
    active_camera_config: str | None = None


class ToolResult(BaseModel):
    ok: bool
    project_id: str | None = None
    revision: int | None = None
    preview_token: str | None = None
    summary: ChangeSummary = Field(default_factory=ChangeSummary)
    resources: list[str] = Field(default_factory=list)
    thumbnails: list[str] = Field(default_factory=list)
    message: str = ""

    @property
    def token(self) -> str | None:
        """Recipe-friendly alias used by ``g.commit(preview.token)``."""
        return self.preview_token


class SimulationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SimulationCameraView(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    side: Literal["front", "back"] | None = None
    azimuth_deg: float | None = None
    elevation_deg: float | None = None
    camera_location_mm: tuple[float, float, float] | None = None
    distance_scale: float = Field(default=1.6, gt=0)


class SimulationCameraConfig(BaseModel):
    schema_version: str = "1.0"
    resolution: tuple[int, int] = (800, 800)
    views: list[SimulationCameraView] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_camera_contract(self) -> Self:
        if any(value <= 0 for value in self.resolution):
            raise ValueError("Camera resolution must be positive")
        names = [view.name for view in self.views]
        if len(names) != len(set(names)):
            raise ValueError("Camera view names must be unique")
        return self


class SimulationTask(BaseModel):
    schema_version: str = "1.0"
    project_id: str
    revision: int = Field(ge=0)
    units: Literal["mm"] = "mm"
    body_mesh_units: Literal["m"] = "m"
    pattern_snapshot_format: Literal["garmentcode"] = "garmentcode"
    inputs: dict[str, str]
    expected_views: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_required_inputs(self) -> Self:
        required = {
            "body_mesh",
            "body_measurements",
            "body_segmentation",
            "fabric",
            "simulation_config",
            "camera_config",
        }
        if missing := sorted(required - set(self.inputs)):
            raise ValueError(f"Simulation task inputs are missing: {missing}")
        if len(self.expected_views) != len(set(self.expected_views)):
            raise ValueError("Simulation task views must be unique")
        if any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name) is None
            for name in self.expected_views
        ):
            raise ValueError("Simulation task contains an unsafe view name")
        return self


class SimulationJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    content_hash: str
    project_id: str
    revision: int
    status: SimulationStatus = SimulationStatus.QUEUED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    progress: float = 0.0
    message: str = ""
    artifacts: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class AssemblyEdge(BaseModel):
    id: str
    start: int
    end: int
    curve: dict[str, Any] | None = None
    alias: str | None = None
    label: str | None = None


class PatternSnapshotNode(BaseModel):
    x_mm: float
    y_mm: float
    edge_uuid: str
    edge_alias: str
    curve_point: bool = False
    turn_point: bool = False


class PatternSnapshotPiece(BaseModel):
    uuid: str
    alias: str
    native_id: int
    name: str = ""
    contour: list[PatternSnapshotNode]
    seam_allowance: bool = False
    seam_allowance_mm: float = 0.0


class PatternSnapshot(BaseModel):
    schema_version: str = "1.0"
    units: Literal["mm"] = "mm"
    revision: int
    pieces: list[PatternSnapshotPiece]


class SewingSidecarInterface(BaseModel):
    uuid: str | None = None
    alias: str
    edges: list[str] = Field(min_length=1)
    reverse: bool = False
    ruffle: float = Field(default=1.0, gt=0)
    right_wrong: bool = False


class SewingSidecarStitch(BaseModel):
    uuid: str | None = None
    alias: str
    interface_a: str
    interface_b: str
    direction: Literal["same", "opposed", "auto"] = "auto"


class SewingSidecar(BaseModel):
    schema_version: str = "1.0"
    interfaces: list[SewingSidecarInterface] = Field(default_factory=list)
    stitches: list[SewingSidecarStitch] = Field(default_factory=list)


class AssemblyPanel(BaseModel):
    id: str
    alias: str
    vertices_mm: list[tuple[float, float]]
    edges: list[AssemblyEdge]
    translation_mm: tuple[float, float, float] = (0, 0, 0)
    rotation_deg: tuple[float, float, float] = (0, 0, 0)
    grainline_deg: float | None = None
    seam_allowance_mm: float | None = None
    component: str | None = None


class AssemblyInterface(BaseModel):
    id: str
    alias: str
    panel_id: str
    edge_indices: list[int] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    reverse_order: bool = False
    flip_edges: bool = False
    ruffle: float = Field(default=1.0, gt=0)
    right_wrong: bool = False


class AssemblyStitch(BaseModel):
    id: str
    alias: str
    interface_a: str
    interface_b: str
    direction: Literal["same", "opposed", "auto"] = "auto"


class AssemblyDocument(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    engine: Literal["GarmentCode"] = "GarmentCode"
    units: Literal["mm"] = "mm"
    source_project_id: str | None = None
    source_revision: int | None = None
    source_pattern_hash: str | None = None
    panels: dict[str, AssemblyPanel] = Field(default_factory=dict)
    interfaces: dict[str, AssemblyInterface] = Field(default_factory=dict)
    stitches: dict[str, AssemblyStitch] = Field(default_factory=dict)
    components: dict[str, list[str]] = Field(default_factory=dict)
    native_pattern: dict[str, Any] | None = None
