from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


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
    schema_version: str = "1.0"
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    units: Literal["mm"] = "mm"
    current_revision: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    pattern_file: str = "pattern/main.val"
    assembly_file: str = "assembly/assembly.json"
    measurement_files: list[str] = Field(default_factory=list)
    active_body: str | None = None
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
    edge_indices: list[int]
    edge_ids: list[str] = Field(default_factory=list)
    reverse: bool = False


class AssemblyStitch(BaseModel):
    id: str
    alias: str
    interface_a: str
    interface_b: str
    direction: Literal["same", "opposed", "auto"] = "auto"


class AssemblyDocument(BaseModel):
    schema_version: str = "1.0"
    units: Literal["mm"] = "mm"
    source_revision: int | None = None
    panels: dict[str, AssemblyPanel] = Field(default_factory=dict)
    interfaces: dict[str, AssemblyInterface] = Field(default_factory=dict)
    stitches: dict[str, AssemblyStitch] = Field(default_factory=dict)
    components: dict[str, list[str]] = Field(default_factory=dict)
