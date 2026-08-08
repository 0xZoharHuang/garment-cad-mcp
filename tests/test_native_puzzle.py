from __future__ import annotations

import os
import struct
import subprocess
from pathlib import Path

import pytest

from garmentcad import Project
from garmentcad.artifacts import ArtifactStore
from garmentcad.backends import JsonLineCommandBackend
from garmentcad.models import Operation, OperationDomain

VALENTINA_COMMAND = os.environ.get("GARMENTCAD_VALENTINA_COMMAND")
PUZZLE_COMMAND = os.environ.get("GARMENTCAD_PUZZLE_COMMAND")
pytestmark = pytest.mark.skipif(
    not VALENTINA_COMMAND or not PUZZLE_COMMAND,
    reason="native Valentina and Puzzle command hosts are not configured",
)


def _operation(domain: OperationDomain, action: str, **arguments) -> Operation:
    return Operation(domain=domain, action=action, arguments=arguments)


def _raw_male_shirt(tmp_path: Path) -> Path:
    repository = Path(__file__).resolve().parents[1]
    collection = repository / "upstream/valentina/src/app/share/collection/MaleShirt"
    environment = os.environ.copy()
    environment.pop("GARMENTCAD_COMMAND_MODE", None)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    subprocess.run(
        [
            str(VALENTINA_COMMAND),
            "--basename",
            "shirt",
            "--destination",
            str(tmp_path),
            "--format",
            "35",
            "--exportOnlyDetails",
            "--mfile",
            str(collection / "MaleShirt.vit"),
            str(collection / "MaleShirt.val"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    result = tmp_path / "shirt.rld"
    assert result.stat().st_size > 10_000
    return result


def test_native_puzzle_service_info():
    info = JsonLineCommandBackend("GARMENTCAD_PUZZLE_COMMAND").service_info()
    assert info["application"] == "Puzzle"
    assert info["units"] == "mm"
    assert set(info["handlers"]) == {
        "layout.generate",
        "layout.sheet_add",
        "layout.sheet_update",
        "layout.move_piece",
        "layout.place",
        "layout.rotate_piece",
        "layout.flip_piece",
        "layout.settings_update",
        "layout.print",
        "export.layout",
    }


def test_native_puzzle_layout_nesting_transform_export_and_reopen(tmp_path):
    raw_layout = _raw_male_shirt(tmp_path)
    project = Project.create(tmp_path / "shirt-project")
    generated = project.preview(
        operations=[
            _operation(
                OperationDomain.LAYOUT,
                "layout.generate",
                raw_layout_path=str(raw_layout),
                sheet_width_mm=1600,
                sheet_height_mm=5000,
                piece_gap_mm=8,
                timeout_ms=10_000,
                allow_rotation=True,
            ),
            _operation(
                OperationDomain.LAYOUT,
                "layout.settings_update",
                title="Shirt marker",
                description="Native command replay",
                sticky_edges=True,
                piece_gap_mm=8,
            ),
        ]
    )
    assert generated.ok
    assert generated.summary.measurements["layout.efficiency"] > 0
    assert generated.summary.measurements["layout.sheets"] >= 1
    thumbnail = (
        project.root
        / f".garmentcad/changesets/{generated.token}/thumbnail.png"
    ).read_bytes()
    assert thumbnail.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", thumbnail[16:24]) == (512, 512)
    assert len(thumbnail) > 1_000
    assert generated.thumbnails
    candidate = (
        project.root
        / f".garmentcad/changesets/{generated.token}/layout/main.vlt"
    )
    assert "FrontPanel" in candidate.read_text(encoding="utf-8")
    assert not (project.root / "layout/main.vlt").exists()
    project.commit(generated.token)

    before = (project.root / "layout/main.vlt").read_text(encoding="utf-8")
    transformed = project.preview(
        operations=[
            _operation(
                OperationDomain.LAYOUT,
                "layout.move_piece",
                piece="FrontPanel",
                dx_mm=5,
                dy_mm=7,
            ),
            _operation(
                OperationDomain.LAYOUT,
                "layout.rotate_piece",
                piece="FrontPanel",
                angle_deg=5,
            ),
            _operation(
                OperationDomain.LAYOUT,
                "layout.flip_piece",
                piece="FrontPanel",
                axis="horizontal",
            ),
            _operation(
                OperationDomain.LAYOUT,
                "layout.place",
                piece="FrontPanel",
                sheet_index=0,
                x_mm=25,
                y_mm=30,
            ),
        ]
    )
    assert transformed.ok
    project.commit(transformed.token)
    after = (project.root / "layout/main.vlt").read_text(encoding="utf-8")
    assert after != before

    exports = project.preview(
        operations=[
            _operation(
                OperationDomain.EXPORT,
                "export.layout",
                format=format_name,
                output_path=f"artifacts/exports/{filename}",
            )
            for format_name, filename in (
                ("svg", "shirt.svg"),
                ("pdf", "shirt.pdf"),
                ("png", "shirt.png"),
                ("obj", "shirt.obj"),
                ("ps", "shirt.ps"),
                ("eps", "shirt.eps"),
                ("dxf_r10", "shirt-r10.dxf"),
                ("dxf_r12", "shirt-r12.dxf"),
                ("dxf_r13", "shirt-r13.dxf"),
                ("dxf_r14", "shirt-r14.dxf"),
                ("dxf_2000", "shirt-2000.dxf"),
                ("dxf_2004", "shirt-2004.dxf"),
                ("dxf_2007", "shirt-2007.dxf"),
                ("dxf_2010", "shirt-2010.dxf"),
                ("dxf_2013", "shirt-2013.dxf"),
                ("dxf_aama", "shirt-aama.dxf"),
                ("dxf_astm", "shirt-astm.dxf"),
                ("pdf_tiled", "shirt-tiled.pdf"),
                ("rld", "shirt.rld"),
                ("tif", "shirt.tif"),
                ("hpgl", "shirt.hpgl"),
                ("hpgl2", "shirt-hpgl2.hpgl"),
                ("plt", "shirt.plt"),
                ("hpgl2_plt", "shirt-hpgl2.plt"),
            )
        ]
    )
    assert exports.ok
    committed = project.commit(exports.token)
    # Every native LayoutExportFormats value except the reserved future NC
    # entry is exercised above. Alias spellings are covered by the static
    # mapping drift test.
    assert len(committed.resources) == 24
    payloads: dict[str, bytes] = {}
    store = ArtifactStore(project.root)
    for uri in committed.resources:
        blob, metadata = store.resolve(uri.rsplit("/", 1)[-1])
        content = blob.read_bytes()
        for filename in metadata["filenames"]:
            payloads[filename] = content
    assert payloads["shirt.svg"].lstrip().startswith(b"<?xml")
    assert payloads["shirt.pdf"].startswith(b"%PDF")
    assert payloads["shirt-tiled.pdf"].startswith(b"%PDF")
    assert payloads["shirt.png"].startswith(b"\x89PNG\r\n\x1a\n")
    assert payloads["shirt.tif"][:4] in {b"II*\x00", b"MM\x00*"}
    assert payloads["shirt.obj"].startswith(b"# Valentina OBJ File")
    assert payloads["shirt.ps"].startswith(b"%!PS")
    assert payloads["shirt.eps"].startswith(b"%!PS")
    for name in (
        "shirt-r10.dxf",
        "shirt-r12.dxf",
        "shirt-r13.dxf",
        "shirt-r14.dxf",
        "shirt-2000.dxf",
        "shirt-2004.dxf",
        "shirt-2007.dxf",
        "shirt-2010.dxf",
        "shirt-2013.dxf",
    ):
        assert b"SECTION" in payloads[name]
    assert b"SECTION" in payloads["shirt-aama.dxf"]
    assert b"SECTION" in payloads["shirt-astm.dxf"]
    assert len(payloads["shirt.rld"]) > 10_000
    assert len(payloads["shirt.hpgl"]) > 100
    assert len(payloads["shirt-hpgl2.hpgl"]) > 100
    assert len(payloads["shirt.plt"]) > 100
    assert len(payloads["shirt-hpgl2.plt"]) > 100

    reopened = Project.open(project.root).preview(
        operations=[
            _operation(
                OperationDomain.LAYOUT,
                "layout.settings_update",
                title="Reopened marker",
            ),
            _operation(
                OperationDomain.LAYOUT,
                "layout.sheet_add",
                name="Overflow",
                width_mm=600,
                height_mm=1000,
            ),
            _operation(
                OperationDomain.LAYOUT,
                "layout.sheet_update",
                sheet="Overflow",
                width_mm=620,
                margin_left_mm=10,
            ),
        ]
    )
    assert reopened.ok
    Project.open(project.root).commit(reopened.token)
    reopened_text = (project.root / "layout/main.vlt").read_text(encoding="utf-8")
    assert "Reopened marker" in reopened_text
    assert "Overflow" in reopened_text
