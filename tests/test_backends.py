from __future__ import annotations

import json
import subprocess
import sys

import pytest

from garmentcad.backends import JsonLineCommandBackend
from garmentcad.errors import CommandBackendUnavailable


def test_native_backend_preserves_structured_error(monkeypatch):
    monkeypatch.setenv("GARMENTCAD_VALENTINA_COMMAND", sys.executable)
    response = {
        "ok": False,
        "error": {"code": "invalid_geometry", "message": "curves do not intersect"},
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout=json.dumps(response), stderr=""
        ),
    )

    with pytest.raises(
        CommandBackendUnavailable, match="invalid_geometry: curves do not intersect"
    ):
        JsonLineCommandBackend().service_info()


def test_native_backend_rejects_invalid_success_payload(monkeypatch):
    monkeypatch.setenv("GARMENTCAD_VALENTINA_COMMAND", sys.executable)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout="not-json", stderr=""
        ),
    )

    with pytest.raises(CommandBackendUnavailable, match="returned invalid JSON"):
        JsonLineCommandBackend().service_info()


def test_native_router_splits_valentina_and_puzzle_operations(monkeypatch, tmp_path):
    from garmentcad.backends import NativeCommandRouter
    from garmentcad.models import Operation, OperationDomain

    calls: list[tuple[str, list[str]]] = []
    router = NativeCommandRouter()

    def preview(name):
        def run(project_root, change_set_id, operations):
            del project_root, change_set_id
            calls.append((name, [operation.action for operation in operations]))
            from garmentcad.models import ChangeSummary

            return ChangeSummary()

        return run

    monkeypatch.setattr(router.valentina, "preview", preview("valentina"))
    monkeypatch.setattr(router.puzzle, "preview", preview("puzzle"))
    router.preview(
        tmp_path,
        "change",
        [
            Operation(domain=OperationDomain.PATTERN, action="pattern.base_point"),
            Operation(domain=OperationDomain.EXPORT, action="export.pattern"),
            Operation(domain=OperationDomain.LAYOUT, action="layout.generate"),
            Operation(domain=OperationDomain.EXPORT, action="export.layout"),
        ],
    )
    assert calls == [
        ("valentina", ["pattern.base_point", "export.pattern"]),
        ("puzzle", ["layout.generate", "export.layout"]),
    ]
