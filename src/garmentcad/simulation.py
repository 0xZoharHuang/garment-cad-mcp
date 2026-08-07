from __future__ import annotations

import io
import os
import tarfile
from typing import Any

import httpx

from garmentcad.assembly import to_garmentcode
from garmentcad.project import Project
from garmentcad.storage import canonical_json, read_json, sha256_bytes


def build_simulation_bundle(project: Project) -> tuple[bytes, str]:
    assembly = read_json(project.root / "assembly/assembly.json")
    garmentcode = to_garmentcode(assembly)
    metadata = {
        "project_id": project.manifest.project_id,
        "revision": project.current_revision,
        "units": "mm",
    }
    files = {
        "assembly.json": canonical_json(assembly),
        "garmentcode.json": canonical_json(garmentcode),
        "job.json": canonical_json(metadata),
    }
    for relative in (project.manifest.active_body, project.manifest.active_fabric):
        if relative:
            path = project.root / relative
            if path.is_file():
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
