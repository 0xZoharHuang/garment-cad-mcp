from __future__ import annotations

import sys
from pathlib import Path
from shlex import quote

from garmentcad.project import Project
from garmentcad.simulation import build_simulation_bundle
from garmentcad.worker.app import JobStore


def test_worker_runs_serial_job_and_reuses_content_cache(tmp_path, monkeypatch):
    project = Project.create(tmp_path / "project")
    body = project.root / "simulation/bodies/test.obj"
    body.write_text("o body\nv 0 0 0\n", encoding="utf-8")
    body.with_suffix(".yaml").write_text("body: {}\n", encoding="utf-8")
    manifest = project.manifest
    manifest.active_body = "simulation/bodies/test.obj"
    from garmentcad.storage import atomic_write_json

    atomic_write_json(project.manifest_path, manifest.model_dump(mode="json"))
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
    assert any(path.endswith("front.png") for path in completed.artifacts)
    cached = store.submit(payload, content_hash)
    assert cached.id == job.id
