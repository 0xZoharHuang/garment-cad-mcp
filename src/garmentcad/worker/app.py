from __future__ import annotations

import json
import os
import shlex
import subprocess
import tarfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from garmentcad.models import SimulationJob, SimulationStatus, utc_now
from garmentcad.storage import atomic_write_bytes, atomic_write_json, read_json, sha256_bytes


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="garment-sim")
        self.futures: dict[str, Future[None]] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.lock = threading.Lock()

    def path(self, job_id: str) -> Path:
        return self.root / job_id

    def load(self, job_id: str) -> SimulationJob:
        raw = read_json(self.path(job_id) / "status.json")
        if raw is None:
            raise KeyError(job_id)
        return SimulationJob.model_validate(raw)

    def save(self, job: SimulationJob) -> None:
        job.updated_at = utc_now()
        atomic_write_json(self.path(job.id) / "status.json", job.model_dump(mode="json"))

    def submit(self, payload: bytes, expected_hash: str) -> SimulationJob:
        if not expected_hash or len(expected_hash) != 64:
            raise ValueError("content_hash must be a SHA-256 hex digest")
        if _bundle_content_hash(payload) != expected_hash:
            raise ValueError("content_hash does not match bundle contents")
        for status_file in self.root.glob("*/status.json"):
            existing = SimulationJob.model_validate(read_json(status_file))
            if (
                existing.content_hash == expected_hash
                and existing.status == SimulationStatus.SUCCEEDED
            ):
                return existing
        metadata = _read_bundle_metadata(payload)
        job = SimulationJob(
            content_hash=expected_hash,
            project_id=metadata["project_id"],
            revision=int(metadata["revision"]),
        )
        directory = self.path(job.id)
        directory.mkdir(parents=True)
        atomic_write_bytes(directory / "bundle.tar.gz", payload)
        self.save(job)
        with self.lock:
            self.futures[job.id] = self.executor.submit(self._run, job.id)
        return job

    def _run(self, job_id: str) -> None:
        job = self.load(job_id)
        if job.status == SimulationStatus.CANCELLED:
            return
        job.status = SimulationStatus.RUNNING
        job.progress = 0.05
        self.save(job)
        directory = self.path(job_id)
        inputs = directory / "input"
        outputs = directory / "artifacts"
        inputs.mkdir()
        outputs.mkdir()
        try:
            with tarfile.open(directory / "bundle.tar.gz", "r:gz") as archive:
                for member in archive.getmembers():
                    destination = (inputs / member.name).resolve()
                    if (
                        inputs.resolve() not in destination.parents
                        and destination != inputs.resolve()
                    ):
                        raise ValueError("Unsafe path in simulation bundle")
                archive.extractall(inputs, filter="data")
            command_text = os.environ.get("GARMENTCAD_SIM_COMMAND")
            if not command_text:
                raise RuntimeError(
                    "GARMENTCAD_SIM_COMMAND is not configured. "
                    "Point it to the Warp/GarmentCode runner."
                )
            command = [
                part.format(input=str(inputs), output=str(outputs))
                for part in shlex.split(command_text)
            ]
            process = subprocess.Popen(
                command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            with self.lock:
                self.processes[job_id] = process
            timeout = float(os.environ.get("GARMENTCAD_JOB_TIMEOUT_SECONDS", "3600"))
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                process.kill()
                stdout, stderr = process.communicate()
                raise RuntimeError(f"Simulation exceeded {timeout:.0f}s timeout") from error
            finally:
                with self.lock:
                    self.processes.pop(job_id, None)
            (directory / "stdout.log").write_text(stdout, encoding="utf-8")
            (directory / "stderr.log").write_text(stderr, encoding="utf-8")
            if self.load(job_id).status == SimulationStatus.CANCELLED:
                return
            if process.returncode != 0:
                raise RuntimeError(stderr[-2000:] or f"Simulator exited {process.returncode}")
            artifacts = [
                str(path.relative_to(directory)) for path in outputs.rglob("*") if path.is_file()
            ]
            required_image = any(
                Path(path).suffix.lower() in {".png", ".jpg", ".jpeg"} for path in artifacts
            )
            if not required_image:
                raise RuntimeError("Simulation runner completed without a programmatic screenshot")
            job.status = SimulationStatus.SUCCEEDED
            job.progress = 1.0
            job.artifacts = artifacts
            job.message = "Simulation and render completed"
        except Exception as error:  # worker boundary records failures for polling clients
            job.status = SimulationStatus.FAILED
            job.message = str(error)
            job.diagnostics = {
                "type": type(error).__name__,
                "stdout": "stdout.log",
                "stderr": "stderr.log",
            }
        self.save(job)

    def cancel(self, job_id: str) -> SimulationJob:
        job = self.load(job_id)
        future = self.futures.get(job_id)
        if job.status == SimulationStatus.QUEUED and future and future.cancel():
            job.status = SimulationStatus.CANCELLED
            job.message = "Cancelled before execution"
            self.save(job)
        elif job.status == SimulationStatus.RUNNING:
            process = self.processes.get(job_id)
            if process is None:
                raise RuntimeError("Runner process is changing state; retry cancellation")
            job.status = SimulationStatus.CANCELLED
            job.message = "Cancellation requested"
            self.save(job)
            process.terminate()
        return job


def _read_bundle_metadata(payload: bytes) -> dict:
    import io

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        member = archive.getmember("job.json")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError("Bundle has no job.json")
        return json.loads(stream.read())


def _bundle_content_hash(payload: bytes) -> str:
    import io

    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is not None:
                files[member.name] = stream.read()
    return sha256_bytes(b"".join(name.encode() + b"\0" + files[name] for name in sorted(files)))


worker_root = Path(os.environ.get("GARMENTCAD_WORKER_ROOT", "./.garment-worker")).resolve()
store = JobStore(worker_root)
app = FastAPI(title="Garment CAD simulation worker", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "queue": "serial",
        "runner_configured": bool(os.environ.get("GARMENTCAD_SIM_COMMAND")),
    }


@app.post("/v1/jobs")
async def create_job(
    bundle: Annotated[UploadFile, File()], content_hash: Annotated[str, Form()]
) -> dict:
    payload = await bundle.read()
    if len(payload) > 256 * 1024 * 1024:
        raise HTTPException(413, "Bundle exceeds 256 MiB")
    try:
        return store.submit(payload, content_hash).model_dump(mode="json")
    except (KeyError, tarfile.TarError, ValueError) as error:
        raise HTTPException(400, str(error)) from error


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return store.load(job_id).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(404, "Job not found") from error


@app.delete("/v1/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    try:
        return store.cancel(job_id).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(404, "Job not found") from error
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/v1/jobs/{job_id}/artifacts/{artifact_path:path}")
def artifact(job_id: str, artifact_path: str) -> FileResponse:
    directory = (store.path(job_id) / "artifacts").resolve()
    target = (directory / artifact_path).resolve()
    if directory not in target.parents or not target.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(target)


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("GARMENTCAD_WORKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("GARMENTCAD_WORKER_PORT", "8765")),
    )
