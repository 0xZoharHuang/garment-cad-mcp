#!/usr/bin/env python3
"""JSON command host for the pinned, native GarmentCode compatibility environment."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from pygarment.garmentcode.document import GarmentDocument


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_create(request: dict[str, Any]) -> dict[str, Any]:
    output = Path(request["output_path"]).resolve()
    document = GarmentDocument()
    document.state["source_project_id"] = request.get("project_id")
    document.save(output)
    return {
        "document_path": str(output),
        "document_hash": _sha256(output),
        "diagnostics": document.diagnostics(),
        "provenance": {
            "engine": "GarmentCode",
            "protocol_version": "2.0",
            "operation": "document.create",
        },
    }


def _append_validation(summary: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    for alias, panel in diagnostics.get("panels", {}).items():
        if not panel.get("closed") or not panel.get("chained"):
            summary["issues"].append(
                {
                    "severity": "error",
                    "code": "garmentcode_open_panel",
                    "message": f"Native GarmentCode panel {alias} is not a closed chain",
                    "details": panel,
                }
            )
        if panel.get("self_intersecting"):
            summary["issues"].append(
                {
                    "severity": "error",
                    "code": "garmentcode_self_intersection",
                    "message": f"Native GarmentCode panel {alias} self-intersects",
                    "details": panel,
                }
            )
    for alias, stitch in diagnostics.get("stitches", {}).items():
        summary["measurements"][f"stitch.{alias}.length_difference_mm"] = float(
            stitch.get("length_difference_mm", 0.0)
        )
        if not stitch.get("native_matching"):
            summary["issues"].append(
                {
                    "severity": "error",
                    "code": "garmentcode_incompatible_stitch",
                    "message": f"Native GarmentCode cannot match stitch {alias}",
                    "details": stitch,
                }
            )


def _document_preview(request: dict[str, Any]) -> dict[str, Any]:
    source = Path(request["source_path"]).resolve()
    output = Path(request["output_path"]).resolve()
    document = GarmentDocument.load(source)
    summary: dict[str, Any] = {
        "created": [],
        "changed": [],
        "deleted": [],
        "measurements": {},
        "issues": [],
    }
    for operation in request.get("operations", []):
        try:
            if operation.get("action") == "assembly.sync_from_pattern":
                arguments = operation.get("arguments") or {}
                document.sync_from_valentina(
                    arguments["snapshot"],
                    source_project_id=str(arguments["source_project_id"]),
                    source_pattern_hash=str(arguments["source_pattern_hash"]),
                    bindings=arguments.get("bindings") or {},
                )
                summary["changed"].append({"alias": "assembly"})
            else:
                change = document.apply(operation)
                for key in ("created", "changed", "deleted"):
                    summary[key].extend(change[key])
        except (IndexError, KeyError, TypeError, ValueError) as error:
            summary["issues"].append(
                {
                    "severity": "error",
                    "code": "invalid_garmentcode_operation",
                    "message": f"{operation.get('action')}: {error}",
                    "objects": [operation["target"]] if operation.get("target") else [],
                }
            )
    diagnostics = document.diagnostics()
    _append_validation(summary, diagnostics)
    document.save(output)
    return {
        "summary": summary,
        "diagnostics": diagnostics,
        "document_path": str(output),
        "document_hash": _sha256(output),
        "provenance": {
            "engine": "GarmentCode",
            "protocol_version": "2.0",
            "operation": "document.preview",
            "source_hash": _sha256(source),
        },
    }


def _document_export(request: dict[str, Any]) -> dict[str, Any]:
    source = Path(request["source_path"]).resolve()
    output = Path(request["output_directory"]).resolve()
    document = GarmentDocument.load(source)
    paths = document.export(output, list(request.get("formats") or ["json", "obj", "usd"]))
    return {
        "files": {
            name: {"path": str(path), "sha256": _sha256(path), "size": path.stat().st_size}
            for name, path in paths.items()
        },
        "diagnostics": document.diagnostics(),
        "provenance": {
            "engine": "GarmentCode",
            "protocol_version": "2.0",
            "operation": "document.export",
            "source_hash": _sha256(source),
        },
    }


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    if method == "service.info":
        return {
            "protocol_version": "2.0",
            "application": "GarmentCode",
            "units": {"public": "mm", "native": "cm"},
            "handlers": [
                "document.create",
                "document.preview",
                "document.validate",
                "document.export",
            ],
            "native_classes": [
                "GarmentDocument",
                "Panel",
                "Edge",
                "EdgeSequence",
                "Interface",
                "Component",
            ],
        }
    if method == "document.create":
        return _document_create(request)
    if method == "document.preview":
        return _document_preview(request)
    if method == "document.validate":
        document = GarmentDocument.load(request["source_path"])
        return {"diagnostics": document.diagnostics()}
    if method == "document.export":
        return _document_export(request)
    raise ValueError(f"Unknown method: {method}")


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            response = dispatch(request)
        response["native_log"] = captured.getvalue()
        response["ok"] = True
        status = 0
    except Exception as error:
        response = {
            "ok": False,
            "error": {
                "code": "garmentcode_native_error",
                "message": str(error),
                "type": type(error).__name__,
            },
        }
        status = 1
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
