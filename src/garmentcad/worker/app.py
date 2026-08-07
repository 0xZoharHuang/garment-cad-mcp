from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import tarfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from garmentcad.models import SimulationJob, SimulationStatus, SimulationTask, utc_now
from garmentcad.storage import atomic_write_bytes, atomic_write_json, read_json, sha256_bytes


class WorkerJobError(RuntimeError):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class JobStore:
    def __init__(self, root: Path, *, recover: bool = True) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="garment-sim")
        self.futures: dict[str, Future[None]] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.lock = threading.Lock()
        if recover:
            self._recover()

    def _recover(self) -> None:
        for status_file in sorted(self.root.glob("*/status.json")):
            job = SimulationJob.model_validate(read_json(status_file))
            if job.status == SimulationStatus.RUNNING:
                job.status = SimulationStatus.FAILED
                job.message = "Worker restarted while the runner was active"
                job.diagnostics = {
                    "code": "worker_restarted",
                    "type": "WorkerRestart",
                    "retryable": True,
                }
                self.save(job)
            elif job.status == SimulationStatus.QUEUED:
                self.futures[job.id] = self.executor.submit(self._run, job.id)

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
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError("content_hash must be a SHA-256 hex digest")
        if _bundle_content_hash(payload) != expected_hash:
            raise ValueError("content_hash does not match bundle contents")
        with self.lock:
            for status_file in self.root.glob("*/status.json"):
                existing = SimulationJob.model_validate(read_json(status_file))
                if existing.content_hash == expected_hash and existing.status in {
                    SimulationStatus.QUEUED,
                    SimulationStatus.RUNNING,
                    SimulationStatus.SUCCEEDED,
                }:
                    return existing
            task = _read_bundle_task(payload)
            job = SimulationJob(
                content_hash=expected_hash,
                project_id=task.project_id,
                revision=task.revision,
            )
            directory = self.path(job.id)
            directory.mkdir(parents=True)
            atomic_write_bytes(directory / "bundle.tar.gz", payload)
            self.save(job)
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
        inputs.mkdir(exist_ok=True)
        outputs.mkdir(exist_ok=True)
        diagnostics_dir = outputs / "diagnostics"
        diagnostics_dir.mkdir(exist_ok=True)
        (diagnostics_dir / "stdout.log").touch()
        (diagnostics_dir / "stderr.log").touch()
        try:
            _extract_bundle(directory / "bundle.tar.gz", inputs)
            task = SimulationTask.model_validate(read_json(inputs / "job.json"))
            if self.load(job_id).status == SimulationStatus.CANCELLED:
                return
            command_text = os.environ.get("GARMENTCAD_SIM_COMMAND")
            if not command_text:
                raise WorkerJobError(
                    "runner_not_configured",
                    "GARMENTCAD_SIM_COMMAND is not configured. "
                    "Point it to the Warp/GarmentCode runner.",
                )
            command = [
                part.format(input=str(inputs), output=str(outputs))
                for part in shlex.split(command_text)
            ]
            process = subprocess.Popen(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            with self.lock:
                self.processes[job_id] = process
            timeout = float(os.environ.get("GARMENTCAD_JOB_TIMEOUT_SECONDS", "3600"))
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                _terminate_process_group(process, signal.SIGKILL)
                stdout, stderr = process.communicate()
                raise WorkerJobError(
                    "runner_timeout",
                    f"Simulation exceeded {timeout:.0f}s timeout",
                    timeout_seconds=timeout,
                ) from error
            finally:
                with self.lock:
                    self.processes.pop(job_id, None)
            (diagnostics_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (diagnostics_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            if self.load(job_id).status == SimulationStatus.CANCELLED:
                return
            if process.returncode != 0:
                raise WorkerJobError(
                    "runner_failed",
                    stderr[-2000:] or f"Simulator exited {process.returncode}",
                    returncode=process.returncode,
                )
            missing_views = [
                view
                for view in task.expected_views
                if not (outputs / f"renders/{view}.png").is_file()
            ]
            if missing_views:
                raise WorkerJobError(
                    "missing_render_views",
                    f"Simulation runner omitted required views: {missing_views}",
                    missing_views=missing_views,
                )
            artifacts = sorted(
                str(path.relative_to(directory)) for path in outputs.rglob("*") if path.is_file()
            )
            job.status = SimulationStatus.SUCCEEDED
            job.progress = 1.0
            job.artifacts = artifacts
            job.message = "Simulation and render completed"
            runner_diagnostics = read_json(outputs / "diagnostics.json", default={})
            if isinstance(runner_diagnostics, dict):
                job.diagnostics = runner_diagnostics
        except Exception as error:  # worker boundary records failures for polling clients
            job.status = SimulationStatus.FAILED
            job.message = str(error)
            job.artifacts = sorted(
                str(path.relative_to(directory)) for path in outputs.rglob("*") if path.is_file()
            )
            runner_diagnostics = read_json(outputs / "diagnostics.json", default={})
            job.diagnostics = {
                "code": getattr(error, "code", "worker_internal_error"),
                "type": type(error).__name__,
                "retryable": getattr(error, "code", "") in {"runner_timeout", "worker_restarted"},
                "stdout": "artifacts/diagnostics/stdout.log",
                "stderr": "artifacts/diagnostics/stderr.log",
                **getattr(error, "details", {}),
                **(
                    {"runner_diagnostics": runner_diagnostics}
                    if isinstance(runner_diagnostics, dict) and runner_diagnostics
                    else {}
                ),
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
            job.status = SimulationStatus.CANCELLED
            job.message = "Cancellation requested"
            self.save(job)
            if process is not None:
                _terminate_process_group(process, signal.SIGTERM)
        return job

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)


def _read_bundle_task(payload: bytes) -> SimulationTask:
    import io

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        file_names = [member.name for member in archive.getmembers() if member.isfile()]
        if len(file_names) != len(set(file_names)):
            raise ValueError("Simulation bundle contains duplicate file names")
        names = set(file_names)
        required = {"job.json", "garmentcode.json", "assembly.json", "pattern_snapshot.json"}
        if missing := sorted(required - names):
            raise ValueError(f"Simulation bundle is missing: {missing}")
        member = archive.getmember("job.json")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError("Bundle has no job.json")
        task = SimulationTask.model_validate_json(stream.read())
        if missing_inputs := sorted(set(task.inputs.values()) - names):
            raise ValueError(f"Simulation bundle omits declared inputs: {missing_inputs}")
        return task


def _extract_bundle(archive_path: Path, destination_root: Path) -> None:
    expanded_size = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 10_000:
            raise WorkerJobError("unsafe_bundle", "Simulation bundle contains too many files")
        for member in members:
            destination = (destination_root / member.name).resolve()
            if destination_root.resolve() not in destination.parents:
                raise WorkerJobError("unsafe_bundle", "Unsafe path in simulation bundle")
            if member.issym() or member.islnk() or member.isdev():
                raise WorkerJobError("unsafe_bundle", "Links and devices are forbidden in bundles")
            expanded_size += member.size
            if expanded_size > 2 * 1024 * 1024 * 1024:
                raise WorkerJobError("unsafe_bundle", "Expanded bundle exceeds 2 GiB")
        archive.extractall(destination_root, members=members, filter="data")


def _terminate_process_group(process: subprocess.Popen[str], signal_number: signal.Signals) -> None:
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        return


def _bundle_content_hash(payload: bytes) -> str:
    import io

    files: dict[str, bytes] = {}
    expanded_size = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 10_000:
            raise ValueError("Simulation bundle contains too many files")
        for member in members:
            if not member.isfile():
                continue
            if member.name in files:
                raise ValueError("Simulation bundle contains duplicate file names")
            if member.size > 256 * 1024 * 1024:
                raise ValueError(f"Simulation bundle member is too large: {member.name}")
            expanded_size += member.size
            if expanded_size > 512 * 1024 * 1024:
                raise ValueError("Expanded simulation bundle exceeds 512 MiB")
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
