from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
import time
from pathlib import Path
from shlex import quote

import pytest
from fastapi.testclient import TestClient

from garmentcad.artifacts import ArtifactStore
from garmentcad.project import Project
from garmentcad.sdk import GarmentSDK
from garmentcad.simulation import SimulationClient, build_simulation_bundle
from garmentcad.worker import app as worker_app
from garmentcad.worker.app import JobStore

REPOSITORY = Path(__file__).resolve().parents[1]


def configured_project(tmp_path):
    project = Project.create(tmp_path / "project")
    files = {
        "simulation/bodies/test.obj": "o body\nv 0 0 0\n",
        "simulation/bodies/test.yaml": "body: {}\n",
        "simulation/bodies/test-segmentation.json": "{}\n",
        "simulation/fabrics/test.json": "{}\n",
        "simulation/config/test.json": "{}\n",
        "simulation/cameras/test.json": (
            '{"schema_version":"1.0","resolution":[64,64],'
            '"views":[{"name":"front","side":"front"},{"name":"back","side":"back"}]}\n'
        ),
    }
    for relative, contents in files.items():
        path = project.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    configured = GarmentSDK(project.root).configure_simulation(
        body_mesh="simulation/bodies/test.obj",
        body_measurements="simulation/bodies/test.yaml",
        body_segmentation="simulation/bodies/test-segmentation.json",
        fabric="simulation/fabrics/test.json",
        simulation_config="simulation/config/test.json",
        camera_config="simulation/cameras/test.json",
    )
    assert configured.ok
    project.commit(configured.preview_token)
    return project


def test_worker_runs_serial_job_and_reuses_content_cache(tmp_path, monkeypatch):
    project = configured_project(tmp_path)
    payload, content_hash = build_simulation_bundle(project)
    runner = Path(__file__).with_name("fixture_sim_runner.py")
    monkeypatch.setenv(
        "GARMENTCAD_SIM_COMMAND",
        f"{quote(sys.executable)} {quote(str(runner))} --input {{input}} --output {{output}}",
    )
    store = JobStore(tmp_path / "worker")
    job = store.submit(payload, content_hash)
    store.futures[job.id].result(timeout=10)
    completed = store.load(job.id)
    assert completed.status == "succeeded"
    assert any(path.endswith("renders/front.png") for path in completed.artifacts)
    assert any(path.endswith("renders/back.png") for path in completed.artifacts)
    assert completed.diagnostics == {"runner": "fixture", "views": ["front", "back"]}
    cached = store.submit(payload, content_hash)
    assert cached.id == job.id
    store.close()


def test_worker_runs_distinct_jobs_strictly_serial_and_cancels_queued(tmp_path, monkeypatch):
    first_project = configured_project(tmp_path / "first")
    second_project = configured_project(tmp_path / "second")
    first_payload, first_hash = build_simulation_bundle(first_project)
    second_payload, second_hash = build_simulation_bundle(second_project)
    assert first_hash != second_hash
    runner = Path(__file__).with_name("fixture_sim_runner.py")
    monkeypatch.setenv(
        "GARMENTCAD_SIM_COMMAND",
        f"{quote(sys.executable)} {quote(str(runner))} --input {{input}} --output {{output}}",
    )
    monkeypatch.setenv("GARMENTCAD_FIXTURE_SLEEP_SECONDS", "0.4")
    store = JobStore(tmp_path / "strictly-serial")
    first = store.submit(first_payload, first_hash)
    second = store.submit(second_payload, second_hash)
    deadline = time.monotonic() + 5
    while store.load(first.id).status != "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert store.load(first.id).status == "running"
    assert store.load(second.id).status == "queued"
    cancelled = store.cancel(second.id)
    assert cancelled.status == "cancelled"
    store.futures[first.id].result(timeout=10)
    assert store.load(first.id).status == "succeeded"
    assert store.load(second.id).status == "cancelled"
    store.close()


def test_bundle_is_self_contained_and_revisioned(tmp_path):
    project = configured_project(tmp_path)
    payload, content_hash = build_simulation_bundle(project)
    assert len(content_hash) == 64
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        names = {member.name for member in archive.getmembers() if member.isfile()}
        assert {
            "garmentcode.json",
            "assembly.json",
            "pattern_snapshot.json",
            "job.json",
            "simulation/bodies/test.obj",
            "simulation/bodies/test.yaml",
            "simulation/bodies/test-segmentation.json",
            "simulation/fabrics/test.json",
            "simulation/config/test.json",
            "simulation/cameras/test.json",
        } <= names
        task = json.load(archive.extractfile("job.json"))
    assert task["revision"] == 1
    assert task["units"] == "mm"
    assert task["body_mesh_units"] == "m"
    assert task["expected_views"] == ["front", "back"]
    assert not any(str(value).startswith("/") for value in task["inputs"].values())


def test_official_autodl_smoke_bundle_satisfies_worker_contract(tmp_path, monkeypatch):
    script = REPOSITORY / "scripts/smoke-autodl.py"
    spec = importlib.util.spec_from_file_location("smoke_autodl", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload, content_hash = module.official_bundle()
    runner = Path(__file__).with_name("fixture_sim_runner.py")
    monkeypatch.setenv(
        "GARMENTCAD_SIM_COMMAND",
        f"{quote(sys.executable)} {quote(str(runner))} --input {{input}} --output {{output}}",
    )
    store = JobStore(tmp_path / "official-smoke-contract")
    job = store.submit(payload, content_hash)
    store.futures[job.id].result(timeout=10)
    completed = store.load(job.id)
    assert completed.status == "succeeded"
    assert {
        "artifacts/renders/front.png",
        "artifacts/renders/back.png",
        "artifacts/renders/left.png",
        "artifacts/renders/right.png",
    } <= set(completed.artifacts)
    with pytest.raises(RuntimeError, match="pinned production runner"):
        module.verify_completed_job(completed.model_dump(mode="json"))
    store.close()


def test_simulation_configuration_rejects_missing_input_as_preview_issue(tmp_path):
    project = Project.create(tmp_path / "invalid-config")
    result = GarmentSDK(project.root).configure_simulation(
        body_mesh="simulation/missing.obj",
        body_measurements="simulation/missing.yaml",
        body_segmentation="simulation/missing-segmentation.json",
        fabric="simulation/missing-fabric.json",
        simulation_config="simulation/missing-config.json",
        camera_config="simulation/missing-camera.json",
    )
    assert not result.ok
    assert {issue.code for issue in result.summary.issues} == {"invalid_simulation_input"}


def test_external_simulation_inputs_are_previewed_committed_and_reverted(tmp_path):
    project = Project.create(tmp_path / "external-input-project")
    sources = tmp_path / "external-assets"
    sources.mkdir()
    files = {
        "body.obj": "o body\nv 0 0 0\n",
        "body.yaml": "body: {}\n",
        "segmentation.json": "{}\n",
        "fabric.json": "{}\n",
        "simulation.json": "{}\n",
        "camera.json": (
            '{"schema_version":"1.0","resolution":[64,64],'
            '"views":[{"name":"front","side":"front"}]}\n'
        ),
    }
    for name, contents in files.items():
        (sources / name).write_text(contents, encoding="utf-8")
    result = GarmentSDK(project.root).configure_simulation(
        body_mesh=str(sources / "body.obj"),
        body_measurements=str(sources / "body.yaml"),
        body_segmentation=str(sources / "segmentation.json"),
        fabric=str(sources / "fabric.json"),
        simulation_config=str(sources / "simulation.json"),
        camera_config=str(sources / "camera.json"),
    )
    assert result.ok
    assert not (project.root / "simulation/bodies/body.obj").exists()
    assert (
        project.root
        / f".garmentcad/changesets/{result.token}/simulation/bodies/body.obj"
    ).exists()
    project.commit(result.token)
    assert (project.root / "simulation/bodies/body.obj").exists()
    assert project.manifest.active_body == "simulation/bodies/body.obj"
    project.revert(1)
    assert not (project.root / "simulation/bodies/body.obj").exists()
    assert (project.root / "simulation/bodies").is_dir()
    assert project.manifest.active_body is None


def test_worker_records_failure_timeout_and_missing_views(tmp_path, monkeypatch):
    project = configured_project(tmp_path)
    payload, content_hash = build_simulation_bundle(project)
    runner = Path(__file__).with_name("fixture_sim_runner.py")
    monkeypatch.setenv(
        "GARMENTCAD_SIM_COMMAND",
        f"{quote(sys.executable)} {quote(str(runner))} --input {{input}} --output {{output}}",
    )

    monkeypatch.setenv("GARMENTCAD_FIXTURE_MODE", "fail")
    failed_store = JobStore(tmp_path / "failed")
    failed = failed_store.submit(payload, content_hash)
    failed_store.futures[failed.id].result(timeout=10)
    failed = failed_store.load(failed.id)
    assert failed.status == "failed"
    assert failed.diagnostics["code"] == "runner_failed"
    assert failed.diagnostics["returncode"] == 23
    failed_store.close()

    monkeypatch.setenv("GARMENTCAD_FIXTURE_MODE", "no-images")
    missing_store = JobStore(tmp_path / "missing")
    missing = missing_store.submit(payload, content_hash)
    missing_store.futures[missing.id].result(timeout=10)
    missing = missing_store.load(missing.id)
    assert missing.status == "failed"
    assert missing.diagnostics["code"] == "missing_render_views"
    assert missing.diagnostics["missing_views"] == ["front", "back"]
    missing_store.close()

    monkeypatch.setenv("GARMENTCAD_FIXTURE_MODE", "success")
    monkeypatch.setenv("GARMENTCAD_FIXTURE_SLEEP_SECONDS", "2")
    monkeypatch.setenv("GARMENTCAD_JOB_TIMEOUT_SECONDS", "0.05")
    timeout_store = JobStore(tmp_path / "timeout")
    timed_out = timeout_store.submit(payload, content_hash)
    timeout_store.futures[timed_out.id].result(timeout=10)
    timed_out = timeout_store.load(timed_out.id)
    assert timed_out.status == "failed"
    assert timed_out.diagnostics["code"] == "runner_timeout"
    assert timed_out.diagnostics["retryable"] is True
    timeout_store.close()


def test_worker_cancels_running_process_group_and_recovers_state(tmp_path, monkeypatch):
    project = configured_project(tmp_path)
    payload, content_hash = build_simulation_bundle(project)
    runner = Path(__file__).with_name("fixture_sim_runner.py")
    monkeypatch.setenv(
        "GARMENTCAD_SIM_COMMAND",
        f"{quote(sys.executable)} {quote(str(runner))} --input {{input}} --output {{output}}",
    )
    monkeypatch.setenv("GARMENTCAD_FIXTURE_SLEEP_SECONDS", "10")
    worker_root = tmp_path / "cancel"
    store = JobStore(worker_root)
    job = store.submit(payload, content_hash)
    deadline = time.monotonic() + 5
    while store.load(job.id).status != "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    cancelled = store.cancel(job.id)
    assert cancelled.status == "cancelled"
    store.futures[job.id].result(timeout=5)
    assert store.load(job.id).status == "cancelled"
    store.close()

    status_path = worker_root / job.id / "status.json"
    raw = json.loads(status_path.read_text(encoding="utf-8"))
    raw["status"] = "running"
    status_path.write_text(json.dumps(raw), encoding="utf-8")
    recovered = JobStore(worker_root)
    state = recovered.load(job.id)
    assert state.status == "failed"
    assert state.diagnostics["code"] == "worker_restarted"
    recovered.close()


def test_http_job_api_upload_poll_cache_and_artifact(tmp_path, monkeypatch):
    project = configured_project(tmp_path)
    payload, content_hash = build_simulation_bundle(project)
    runner = Path(__file__).with_name("fixture_sim_runner.py")
    monkeypatch.setenv(
        "GARMENTCAD_SIM_COMMAND",
        f"{quote(sys.executable)} {quote(str(runner))} --input {{input}} --output {{output}}",
    )
    test_store = JobStore(tmp_path / "api-worker")
    monkeypatch.setattr(worker_app, "store", test_store)
    client = TestClient(worker_app.app)
    response = client.post(
        "/v1/jobs",
        files={"bundle": ("project.tar.gz", payload, "application/gzip")},
        data={"content_hash": content_hash},
    )
    assert response.status_code == 200
    job_id = response.json()["id"]
    test_store.futures[job_id].result(timeout=10)
    status = client.get(f"/v1/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded"
    image = client.get(f"/v1/jobs/{job_id}/artifacts/renders/front.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    cached = client.post(
        "/v1/jobs",
        files={"bundle": ("project.tar.gz", payload, "application/gzip")},
        data={"content_hash": content_hash},
    )
    assert cached.json()["id"] == job_id

    simulation = SimulationClient("http://testserver", client=client)
    assert simulation.health()["queue"] == "serial"
    assert simulation.health()["runner_id"] == "unidentified"
    submitted = simulation.submit(project)
    assert submitted["id"] == job_id
    resources = simulation.download(project, job_id)
    assert len(resources) >= 4
    image_uri = next(
        uri
        for uri in resources
        if ArtifactStore(project.root).resolve(uri.rsplit("/", 1)[-1])[1]["media_type"]
        == "image/png"
    )
    image, metadata = ArtifactStore(project.root).resolve(image_uri.rsplit("/", 1)[-1])
    assert image.read_bytes().startswith(b"\x89PNG")
    assert metadata["revision"] == project.current_revision
    test_store.close()
