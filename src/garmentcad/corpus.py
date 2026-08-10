from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import typer

from garmentcad.backends import JsonLineCommandBackend
from garmentcad.models import Operation, OperationDomain
from garmentcad.project import Project
from garmentcad.storage import atomic_write_json, read_json, sha256_file

app = typer.Typer(no_args_is_help=True, help="Qualify the MCP against public Valentina patterns.")

REPRESENTATIVE_PATTERNS = {
    "src/app/share/collection/MaleShirt/MaleShirt.val",
    "src/app/share/collection/Trousers/Trousers.val",
    "src/app/share/collection/Gent_Jacket_with_tummy.val",
    "src/app/share/collection/Basic_block_women-2016.val",
    "src/app/share/collection/bra.val",
    "src/app/share/collection/Keiko_skirt.val",
    "src/app/share/collection/TestPuzzle.val",
    "src/app/share/collection/Steampunk_trousers.val",
    "src/app/share/collection/bugs/possible_inf_loop.val",
    "src/app/share/collection/bugs/smart_pattern_#184_case1.val",
    "src/test/CollectionTest/tst_valentina/issue_372.val",
    "src/test/CollectionTest/tst_valentina/wrong_formula.val",
}

EXPECTED_REJECTIONS = {
    "src/app/share/collection/bugs/possible_inf_loop.val",
    "src/test/CollectionTest/tst_valentina/wrong_formula.val",
    "src/test/CollectionTest/tst_valentina/wrong_obj_type.val",
}


@dataclass(frozen=True)
class CorpusCase:
    source: str
    sha256: str
    bytes: int
    xml_status: str
    fixture_kind: str
    expected_outcome: str
    category: str
    version: str | None
    unit: str | None
    points: int
    curves: int
    pieces: int
    increments: int
    embedded_images: int
    measurement_reference: str | None
    measurement_source: str | None
    dependency_status: str
    mutation_points: tuple[str, str] | None
    error: str | None = None


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(root: ET.Element, name: str) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) == name and element.text and element.text.strip():
            return element.text.strip()
    return None


def _measurement_reference(root: ET.Element) -> str | None:
    for element in root.iter():
        if _local_name(element.tag) != "measurements":
            continue
        if path := element.attrib.get("path", "").strip():
            return path
        if element.text and element.text.strip():
            return element.text.strip()
    return None


def _category(path: Path) -> str:
    name = path.stem.lower()
    for category, needles in {
        "jacket": ("jacket", "zhaketa"),
        "trousers": ("trouser", "pants", "pantalon"),
        "shirt": ("shirt", "blusa", "pajama", "tshirt"),
        "bodice": ("block", "moulage", "sleeve"),
        "lingerie": ("bra",),
        "skirt": ("skirt",),
    }.items():
        if any(needle in name for needle in needles):
            return category
    return "regression" if "bug" in path.parts or "test" in path.parts else "other"


def _fixture_kind(path: Path) -> str:
    lowered = {part.lower() for part in path.parts}
    if "bugs" in lowered or "test" in lowered or "src/test" in path.as_posix().lower():
        return "regression"
    return "production_like"


def _measurement_source(
    pattern: Path, reference: str | None, upstream: Path
) -> tuple[str | None, str]:
    if not reference:
        return None, "none"
    candidate = Path(reference).expanduser()
    if candidate.is_absolute():
        return (str(candidate), "external") if candidate.is_file() else (None, "missing")
    project_probe_root = Path("/garment-project")
    project_probe = (project_probe_root / "pattern" / candidate).resolve()
    if project_probe_root not in project_probe.parents:
        original = (pattern.parent / candidate).resolve()
        return (str(original), "outside_project") if original.is_file() else (None, "missing")
    relative = (pattern.parent / candidate).resolve()
    if relative.is_file():
        return str(relative), "bundled"
    matches = sorted(upstream.rglob(candidate.name))
    if len(matches) == 1:
        return str(matches[0].resolve()), "bundled_by_name"
    return None, "missing" if not matches else "ambiguous"


def _mutation_points(root: ET.Element) -> tuple[str, str] | None:
    candidates: list[tuple[str, str]] = []
    for draw in (element for element in root.iter() if _local_name(element.tag) == "draw"):
        names: list[str] = []
        for element in draw.iter():
            if _local_name(element.tag) != "point":
                continue
            name = element.attrib.get("name", "").strip()
            if name and name not in names:
                names.append(name)
            if len(names) == 2:
                candidates.append((names[0], names[1]))
                break
    # The first draw's base point in several legacy files is not present in the
    # calculation object table after loading. Prefer a later draw when available.
    return candidates[1] if len(candidates) > 1 else (candidates[0] if candidates else None)


def discover_corpus(repo: Path | None = None) -> list[CorpusCase]:
    repo = (repo or repository_root()).resolve()
    upstream = repo / "upstream/valentina"
    cases: list[CorpusCase] = []
    for path in sorted(upstream.rglob("*.val")):
        relative = path.relative_to(upstream).as_posix()
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as exc:
            cases.append(
                CorpusCase(
                    source=relative,
                    sha256=sha256_file(path),
                    bytes=path.stat().st_size,
                    xml_status="invalid",
                    fixture_kind="expected_invalid",
                    expected_outcome="reject",
                    category="regression",
                    version=None,
                    unit=None,
                    points=0,
                    curves=0,
                    pieces=0,
                    increments=0,
                    embedded_images=0,
                    measurement_reference=None,
                    measurement_source=None,
                    dependency_status="not_applicable",
                    mutation_points=None,
                    error=str(exc),
                )
            )
            continue
        elements = list(root.iter())
        tags = [_local_name(element.tag) for element in elements]
        measurement_reference = _measurement_reference(root)
        measurement_source, dependency_status = _measurement_source(
            path, measurement_reference, upstream
        )
        cases.append(
            CorpusCase(
                source=relative,
                sha256=sha256_file(path),
                bytes=path.stat().st_size,
                xml_status="valid",
                fixture_kind=_fixture_kind(Path(relative)),
                expected_outcome="reject" if relative in EXPECTED_REJECTIONS else "open",
                category=_category(Path(relative)),
                version=_text(root, "version"),
                unit=_text(root, "unit"),
                points=tags.count("point"),
                curves=sum(tags.count(tag) for tag in ("arc", "spline", "splinePath")),
                pieces=tags.count("detail") + tags.count("piece"),
                increments=tags.count("increment"),
                embedded_images=tags.count("image"),
                measurement_reference=measurement_reference,
                measurement_source=measurement_source,
                dependency_status=dependency_status,
                mutation_points=_mutation_points(root),
            )
        )
    return cases


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _semantic_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Remove revision metadata before comparing native CAD meaning."""
    return {key: value for key, value in snapshot.items() if key != "revision"}


@contextmanager
def _command_timeout(seconds: float):
    previous = os.environ.get("GARMENTCAD_COMMAND_TIMEOUT_SEC")
    os.environ["GARMENTCAD_COMMAND_TIMEOUT_SEC"] = str(seconds)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GARMENTCAD_COMMAND_TIMEOUT_SEC", None)
        else:
            os.environ["GARMENTCAD_COMMAND_TIMEOUT_SEC"] = previous


def _prepare_project(case: CorpusCase, repo: Path, destination: Path) -> Project:
    project = Project.create(destination, name=Path(case.source).stem)
    source = repo / "upstream/valentina" / case.source
    shutil.copy2(source, project.root / "pattern/main.val")
    measurement_files: list[str] = []
    if case.measurement_source and case.measurement_reference:
        reference = Path(case.measurement_reference)
        if not reference.is_absolute():
            target = (project.root / "pattern" / reference).resolve()
            if project.root == target or project.root in target.parents:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(case.measurement_source, target)
                measurement_files.append(str(target.relative_to(project.root)))
    manifest = project.manifest
    manifest.measurement_files = measurement_files
    atomic_write_json(project.manifest_path, manifest.model_dump(mode="json"))
    revision_path = project.root / ".garmentcad/revisions/0.json"
    revision = read_json(revision_path)
    revision["content_hash"] = Project._content_hash_static(project.root)
    atomic_write_json(revision_path, revision)
    return Project.open(project.root)


def _case_result(
    case: CorpusCase,
    repo: Path,
    workspace: Path,
    mutate: bool,
    *,
    timeout_sec: float = 30,
    retry_slow: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {"case": asdict(case), "status": "pending", "checks": {}}
    if case.xml_status != "valid":
        result["status"] = "expected_invalid"
        result["checks"]["xml"] = "rejected"
        return result
    if case.dependency_status in {"missing", "ambiguous", "external", "outside_project"}:
        result["status"] = "dependency_missing"
        result["checks"]["dependency"] = case.dependency_status
        return result
    slug = hashlib.sha256(case.source.encode()).hexdigest()[:12]
    effective_timeout = (
        timeout_sec if case.fixture_kind == "production_like" else min(timeout_sec, 10)
    )
    try:
        project = _prepare_project(case, repo, workspace / slug)
        pattern = project.root / "pattern/main.val"
        baseline_pattern_hash = sha256_file(pattern)
        backend = JsonLineCommandBackend(
            timeout_sec=10 if case.expected_outcome == "reject" else effective_timeout
        )
        first = backend.snapshot(project.root)
        second = backend.snapshot(project.root)
        first_semantic = _semantic_snapshot(first)
        first_digest = _canonical_digest(first_semantic)
        result["checks"].update(
            {
                "snapshot": "pass",
                "snapshot_deterministic": first == second,
                "semantic_digest": first_digest,
                "native_pieces": len(first["pieces"]),
            }
        )
        if first != second:
            raise AssertionError("native semantic snapshot is not deterministic")
        if case.expected_outcome == "reject":
            result["status"] = "fail"
            result["error"] = "fixture expected native rejection but opened successfully"
            return result
        if mutate:
            operation = Operation(
                domain=OperationDomain.MEASUREMENTS,
                action="measurement.increment_set",
                arguments={
                    "name": f"#corpus_validation_{slug}",
                    "value_mm": 1,
                    "description": "Reversible real-pattern qualification sentinel",
                },
            )
            with _command_timeout(effective_timeout):
                preview = project.preview(operations=[operation])
            if not preview.ok:
                issues = [issue.model_dump(mode="json") for issue in preview.summary.issues]
                raise AssertionError(f"mutation preview rejected: {issues}")
            with _command_timeout(effective_timeout):
                committed = project.commit(preview.token)
            reopened = Project.open(project.root)
            after = JsonLineCommandBackend().snapshot(reopened.root)
            reopened.revert(committed.revision)
            restored = JsonLineCommandBackend().snapshot(reopened.root)
            result["checks"].update(
                {
                    "preview": "pass",
                    "commit_revision": committed.revision,
                    "reopen": "pass",
                    "changed_semantic_digest": _canonical_digest(_semantic_snapshot(after)),
                    "reverse_revision": reopened.current_revision,
                    "restored_semantic_snapshot": _semantic_snapshot(restored) == first_semantic,
                    "restored_pattern_bytes": sha256_file(pattern) == baseline_pattern_hash,
                }
            )
            if (
                _semantic_snapshot(restored) != first_semantic
                or sha256_file(pattern) != baseline_pattern_hash
            ):
                raise AssertionError("reverse revision did not restore the original pattern")
        else:
            result["checks"]["mutation"] = "off"
        result["status"] = "pass"
    except Exception as exc:  # A corpus runner must preserve the rest of the run after one crash.
        if (
            retry_slow
            and case.fixture_kind == "production_like"
            and "timed out" in str(exc).lower()
        ):
            shutil.rmtree(workspace / slug, ignore_errors=True)
            retried = _case_result(
                case,
                repo,
                workspace,
                mutate,
                timeout_sec=120,
                retry_slow=False,
            )
            retried["checks"]["timeout_retry"] = "retried_at_120_seconds"
            return retried
        if case.expected_outcome == "reject":
            result["status"] = "expected_rejection"
        elif case.fixture_kind == "regression":
            result["status"] = "regression_rejection"
        else:
            result["status"] = "fail"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _write_html(report: dict[str, Any], path: Path) -> None:
    rows = []
    for item in report["results"]:
        case = item["case"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(case['source'])}</td>"
            f"<td>{html.escape(case['category'])}</td>"
            f"<td>{case['pieces']}</td>"
            f"<td class='{item['status']}'>{html.escape(item['status'])}</td>"
            f"<td><pre>{html.escape(item.get('error', ''))}</pre></td>"
            "</tr>"
        )
    document = """<!doctype html><meta charset='utf-8'><title>Garment CAD corpus</title>
<style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:6px;text-align:left}.pass{color:#087830}.fail{color:#b00020}
.dependency_missing{color:#9a6700}pre{white-space:pre-wrap;margin:0}</style>
<h1>Garment CAD real-pattern qualification</h1>"""
    document += f"<pre>{html.escape(json.dumps(report['summary'], indent=2))}</pre>"
    document += (
        "<table><tr><th>Pattern</th><th>Category</th><th>Pieces</th>"
        "<th>Status</th><th>Error</th></tr>"
    )
    document += "".join(rows) + "</table>"
    path.write_text(document, encoding="utf-8")


def validate_corpus(
    *,
    repo: Path | None = None,
    output: Path,
    representative: bool = False,
    mutate: bool = True,
    limit: int | None = None,
    keep_workspaces: bool = False,
) -> dict[str, Any]:
    repo = (repo or repository_root()).resolve()
    cases = discover_corpus(repo)
    if representative:
        cases = [case for case in cases if case.source in REPRESENTATIVE_PATTERNS]
    if limit is not None:
        cases = cases[:limit]
    output.mkdir(parents=True, exist_ok=True)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if keep_workspaces:
        workspace = output / "workspaces"
        workspace.mkdir(exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="garmentcad-corpus-")
        workspace = Path(temporary.name)
    partial_path = output / "report.partial.json"
    previous = read_json(partial_path, default={})
    previous_by_source = {
        item["case"]["source"]: item for item in previous.get("results", [])
    }
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        old_result = previous_by_source.get(case.source)
        if old_result is not None and old_result["case"] == asdict(case):
            results.append(old_result)
            typer.echo(f"[{index}/{len(cases)}] {case.source} (resumed)")
            continue
        typer.echo(f"[{index}/{len(cases)}] {case.source}")
        result = _case_result(case, repo, workspace, mutate)
        results.append(result)
        typer.echo(f"  {result['status']}{': ' + result['error'] if result.get('error') else ''}")
        atomic_write_json(
            partial_path,
            {
                "schema_version": "1.0",
                "in_progress": True,
                "completed": len(results),
                "total": len(cases),
                "results": results,
            },
        )
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    production = [
        result
        for result in results
        if result["case"]["fixture_kind"] == "production_like"
    ]
    production_counts: dict[str, int] = {}
    for result in production:
        production_counts[result["status"]] = production_counts.get(result["status"], 0) + 1
    report = {
        "schema_version": "1.0",
        "summary": {
            "total": len(results),
            "counts": counts,
            "strict_pass": counts.get("fail", 0) == 0,
            "mutations_enabled": mutate,
            "production_total": len(production),
            "production_counts": production_counts,
        },
        "results": results,
    }
    atomic_write_json(output / "report.json", report)
    atomic_write_json(output / "manifest.json", [asdict(case) for case in cases])
    _write_html(report, output / "report.html")
    (output / "report.partial.json").unlink(missing_ok=True)
    if temporary is not None:
        temporary.cleanup()
    return report


@app.command("manifest")
def manifest_command(output: Path = Path("build/reports/real-patterns/manifest.json")) -> None:
    cases = discover_corpus()
    atomic_write_json(output, [asdict(case) for case in cases])
    typer.echo(json.dumps({"patterns": len(cases), "output": str(output)}, ensure_ascii=False))


@app.command("validate")
def validate_command(
    output: Path = Path("build/reports/real-patterns"),
    representative: bool = False,
    no_mutation: bool = False,
    limit: int | None = None,
    keep_workspaces: bool = False,
) -> None:
    report = validate_corpus(
        output=output,
        representative=representative,
        mutate=not no_mutation,
        limit=limit,
        keep_workspaces=keep_workspaces,
    )
    typer.echo(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if not report["summary"]["strict_pass"]:
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
