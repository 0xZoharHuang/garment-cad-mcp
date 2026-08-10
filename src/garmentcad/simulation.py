from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path
from typing import Any

import httpx

from garmentcad.artifacts import ArtifactStore
from garmentcad.errors import StaleRevisionError
from garmentcad.models import SimulationCameraConfig, SimulationTask
from garmentcad.project import Project
from garmentcad.storage import canonical_json, read_json, sha256_bytes


def build_simulation_bundle(project: Project) -> tuple[bytes, str]:
    project.assert_assembly_current()
    manifest = project.manifest
    assembly_path = project.root / manifest.assembly_file
    assembly = read_json(assembly_path)
    if not assembly or assembly.get("engine") != "GarmentCode":
        raise ValueError("Native GarmentCode document is missing or invalid")
    garmentcode = assembly.get("native_pattern")
    if not garmentcode:
        raise ValueError("Native GarmentCode document has no compiled pattern")
    required_inputs = {
        "body_mesh": manifest.active_body,
        "body_measurements": manifest.active_body_measurements,
        "body_segmentation": manifest.active_body_segmentation,
        "fabric": manifest.active_fabric,
        "simulation_config": manifest.active_simulation_config,
        "camera_config": manifest.active_camera_config,
    }
    missing = sorted(name for name, relative in required_inputs.items() if not relative)
    if missing:
        raise ValueError(f"Project simulation inputs are not configured: {missing}")
    camera_path = _project_input(project, required_inputs["camera_config"] or "")
    camera_config = SimulationCameraConfig.model_validate(read_json(camera_path))
    input_paths = {name: str(relative) for name, relative in required_inputs.items() if relative}
    task = SimulationTask(
        project_id=manifest.project_id,
        revision=project.current_revision,
        inputs=input_paths,
        expected_views=[view.name for view in camera_config.views],
    )
    files = {
        "assembly/main.garmentcode.json": assembly_path.read_bytes(),
        "garmentcode.json": canonical_json(garmentcode),
        "pattern_snapshot.json": canonical_json(garmentcode),
        "job.json": canonical_json(task.model_dump(mode="json")),
    }
    included = {
        *input_paths.values(),
        *manifest.measurement_files,
    }
    for base in (project.root / "simulation").rglob("*"):
        if base.is_file():
            included.add(str(base.relative_to(project.root)))
    for relative in sorted(value for value in included if value):
        path = _project_input(project, relative)
        files[relative] = path.read_bytes()
    content_hash = sha256_bytes(
        b"".join(name.encode() + b"\0" + files[name] for name in sorted(files))
    )
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))
    return stream.getvalue(), content_hash


def _project_input(project: Project, relative: str) -> Path:
    path = (project.root / relative).resolve()
    if project.root not in path.parents or not path.is_file():
        raise FileNotFoundError(f"Required simulation input is missing: {relative}")
    return path


class SimulationClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("GARMENTCAD_WORKER_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError("Set GARMENTCAD_WORKER_URL or pass base_url")
        self.timeout = timeout
        self.client = client or httpx.Client(timeout=timeout)

    def health(self) -> dict[str, Any]:
        response = self.client.get(f"{self.base_url}/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def submit(self, project: Project) -> dict[str, Any]:
        bundle, content_hash = build_simulation_bundle(project)
        response = self.client.post(
            f"{self.base_url}/v1/jobs",
            files={"bundle": ("project.tar.gz", bundle, "application/gzip")},
            data={"content_hash": content_hash},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def status(self, job_id: str) -> dict[str, Any]:
        response = self.client.get(f"{self.base_url}/v1/jobs/{job_id}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def cancel(self, job_id: str) -> dict[str, Any]:
        response = self.client.delete(f"{self.base_url}/v1/jobs/{job_id}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def download(self, project: Project, job_id: str) -> list[str]:
        job = self.status(job_id)
        if job["status"] not in {"succeeded", "failed"}:
            raise ValueError(f"Simulation job is not complete: {job['status']}")
        if int(job["revision"]) != project.current_revision:
            raise StaleRevisionError(
                f"Job targets revision {job['revision']}; project is at {project.current_revision}"
            )
        store = ArtifactStore(project.root)
        resources = []
        artifact_paths = job["artifacts"]
        if job["status"] == "failed":
            artifact_paths = [
                relative
                for relative in artifact_paths
                if relative.startswith("artifacts/diagnostics")
                or relative == "artifacts/diagnostics.json"
            ]
        for relative in artifact_paths:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("artifacts",):
                raise ValueError(f"Worker returned an unsafe artifact path: {relative}")
            response = self.client.get(
                f"{self.base_url}/v1/jobs/{job_id}/artifacts/{relative.removeprefix('artifacts/')}",
                timeout=self.timeout,
            )
            response.raise_for_status()
            resources.append(
                store.put(
                    response.content,
                    filename=Path(relative).name,
                    kind="simulation",
                    revision=project.current_revision,
                    metadata={"job_id": job_id},
                )
            )
        return resources
