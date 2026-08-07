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
