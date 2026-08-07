from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from garmentcad.errors import CommandBackendUnavailable
from garmentcad.models import ChangeSummary, Operation, ValidationIssue


class CommandBackend(Protocol):
    def preview(
        self, project_root: Path, change_set_id: str, operations: list[Operation]
    ) -> ChangeSummary: ...

    def commit(self, project_root: Path, change_set_id: str) -> None: ...


class JsonLineCommandBackend:
    """Adapter for the C++ Valentina command host.

    The host receives one JSON request on stdin and returns one JSON response on
    stdout. Keeping this protocol below MCP makes the CAD core usable by the GUI,
    SDK, tests, and other agent runtimes without depending on MCP.
    """

    def __init__(self, executable_env: str = "GARMENTCAD_VALENTINA_COMMAND") -> None:
        self.executable_env = executable_env

    def _call(self, request: dict) -> dict:
        executable = os.environ.get(self.executable_env)
        if not executable:
            raise CommandBackendUnavailable(
                f"{self.executable_env} is not set; build the Valentina command host first"
            )
        command = [executable] if Path(executable).is_file() else shlex.split(executable)
        if not command:
            raise CommandBackendUnavailable(f"{self.executable_env} is empty")
        environment = os.environ.copy()
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        environment["GARMENTCAD_COMMAND_MODE"] = "1"
        process = subprocess.run(
            command,
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        if process.returncode != 0:
            raise CommandBackendUnavailable(process.stderr.strip() or "Valentina command failed")
        return json.loads(process.stdout)

    def preview(
        self, project_root: Path, change_set_id: str, operations: list[Operation]
    ) -> ChangeSummary:
        response = self._call(
            {
                "method": "commands.preview",
                "project_root": str(project_root),
                "change_set_id": change_set_id,
                "operations": [operation.model_dump(mode="json") for operation in operations],
            }
        )
        return ChangeSummary.model_validate(response.get("summary", {}))

    def service_info(self) -> dict:
        return self._call({"method": "service.info"})

    def commit(self, project_root: Path, change_set_id: str) -> None:
        self._call(
            {
                "method": "commands.commit",
                "project_root": str(project_root),
                "change_set_id": change_set_id,
            }
        )


class ProjectMetadataBackend:
    """Validator for project-owned metadata operations."""

    def preview(
        self, project_root: Path, change_set_id: str, operations: list[Operation]
    ) -> ChangeSummary:
        del project_root, change_set_id
        summary = ChangeSummary()
        for operation in operations:
            if not operation.action:
                summary.issues.append(
                    ValidationIssue(
                        severity="error", code="empty_action", message="Action is required"
                    )
                )
            elif operation.target:
                summary.changed.append(operation.target)
        return summary

    def commit(self, project_root: Path, change_set_id: str) -> None:
        return None


def merge_summaries(summaries: Iterable[ChangeSummary]) -> ChangeSummary:
    result = ChangeSummary()
    for summary in summaries:
        result.created.extend(summary.created)
        result.changed.extend(summary.changed)
        result.deleted.extend(summary.deleted)
        result.measurements.update(summary.measurements)
        result.issues.extend(summary.issues)
    return result
