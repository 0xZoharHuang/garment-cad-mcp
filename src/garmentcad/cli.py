from __future__ import annotations

import json
from pathlib import Path

import typer

from garmentcad.project import Project
from garmentcad.simulation import SimulationClient

app = typer.Typer(no_args_is_help=True)


@app.command("create")
def create_project(path: Path, name: str | None = None) -> None:
    project = Project.create(path, name=name)
    typer.echo(json.dumps(project.status(), ensure_ascii=False, indent=2))


@app.command("status")
def project_status(path: Path | None = None) -> None:
    project = Project.open(path or Path.cwd())
    typer.echo(json.dumps(project.status(), ensure_ascii=False, indent=2))


@app.command("doctor")
def doctor() -> None:
    from garmentcad.doctor import run_doctor

    report = run_doctor()
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise typer.Exit(1)


@app.command("commit")
def commit_preview(preview_token: str, path: Path | None = None) -> None:
    result = Project.open(path or Path.cwd()).commit(preview_token)
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("simulate")
def simulate(path: Path | None = None, worker_url: str | None = None) -> None:
    result = SimulationClient(worker_url).submit(Project.open(path or Path.cwd()))
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("simulation-status")
def simulation_status(job_id: str, worker_url: str | None = None) -> None:
    result = SimulationClient(worker_url).status(job_id)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("simulation-download")
def simulation_download(
    job_id: str, path: Path | None = None, worker_url: str | None = None
) -> None:
    project = Project.open(path or Path.cwd())
    result = SimulationClient(worker_url).download(project, job_id)
    typer.echo(json.dumps({"resources": result}, ensure_ascii=False, indent=2))


@app.command("revert")
def revert_revision(revision: int, path: Path | None = None) -> None:
    result = Project.open(path or Path.cwd()).revert(revision)
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
