from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path
from typing import Any

import httpx

from garmentcad.artifacts import ArtifactStore
from garmentcad.assembly import to_garmentcode
from garmentcad.errors import StaleRevisionError
from garmentcad.project import Project
from garmentcad.storage import canonical_json, read_json, sha256_bytes


def build_simulation_bundle(project: Project) -> tuple[bytes, str]:
    assembly = read_json(project.root / "assembly/assembly.json")
    garmentcode = to_garmentcode(assembly)
    metadata = {
        "project_id": project.manifest.project_id,
        "revision": project.current_revision,
        "units": "mm",
        "active_body": project.manifest.active_body,
        "active_fabric": project.manifest.active_fabric,
        "active_simulation_config": project.manifest.active_simulation_config,
        "active_camera_config": project.manifest.active_camera_config,
    }
    files = {
        "assembly.json": canonical_json(assembly),
        "garmentcode.json": canonical_json(garmentcode),
        "job.json": canonical_json(metadata),
    }
    if not project.manifest.active_body:
        raise ValueError("Project has no active_body; simulation bundles must be self-contained")
    included = {
        project.manifest.active_body,
        project.manifest.active_fabric,
        project.manifest.active_simulation_config,
        project.manifest.active_camera_config,
        *project.manifest.measurement_files,
    }
    for base in (project.root / "simulation").rglob("*"):
        if base.is_file():
            included.add(str(base.relative_to(project.root)))
    for relative in sorted(value for value in included if value):
        path = (project.root / relative).resolve()
        if project.root not in path.parents or not path.is_file():
            raise FileNotFoundError(f"Required simulation input is missing: {relative}")
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


class SimulationClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0) -> None:
        self.base_url = (base_url or os.environ.get("GARMENTCAD_WORKER_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError("Set GARMENTCAD_WORKER_URL or pass base_url")
        self.timeout = timeout

    def submit(self, project: Project) -> dict[str, Any]:
        bundle, content_hash = build_simulation_bundle(project)
        response = httpx.post(
            f"{self.base_url}/v1/jobs",
            files={"bundle": ("project.tar.gz", bundle, "application/gzip")},
            data={"content_hash": content_hash},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def status(self, job_id: str) -> dict[str, Any]:
        response = httpx.get(f"{self.base_url}/v1/jobs/{job_id}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def cancel(self, job_id: str) -> dict[str, Any]:
        response = httpx.delete(f"{self.base_url}/v1/jobs/{job_id}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def download(self, project: Project, job_id: str) -> list[str]:
        job = self.status(job_id)
        if job["status"] != "succeeded":
            raise ValueError(f"Simulation job is not complete: {job['status']}")
        if int(job["revision"]) != project.current_revision:
            raise StaleRevisionError(
                f"Job targets revision {job['revision']}; project is at {project.current_revision}"
            )
        store = ArtifactStore(project.root)
        resources = []
        for relative in job["artifacts"]:
            response = httpx.get(
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
