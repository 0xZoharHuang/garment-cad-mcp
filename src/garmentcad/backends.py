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
            message = process.stderr.strip()
            if process.stdout.strip():
                try:
                    response = json.loads(process.stdout)
                    error = response.get("error", {})
                    message = error.get("message") or message
                    if error.get("code") and message:
                        message = f"{error['code']}: {message}"
                except json.JSONDecodeError:
                    message = message or process.stdout.strip()
            raise CommandBackendUnavailable(message or "Native CAD command failed")
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise CommandBackendUnavailable("Native CAD host returned invalid JSON") from exc

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

    def snapshot(self, project_root: Path) -> dict:
        """Ask Valentina to expand the current native pattern without parsing XML here."""
        from garmentcad.models import PatternSnapshot

        response = self._call(
            {
                "method": "pattern.snapshot",
                "project_root": str(project_root),
            }
        )
        return PatternSnapshot.model_validate(response).model_dump(mode="json")

    def commit(self, project_root: Path, change_set_id: str) -> None:
        self._call(
            {
                "method": "commands.commit",
                "project_root": str(project_root),
                "change_set_id": change_set_id,
            }
        )


class NativeCommandRouter:
    """Route one project transaction across the native Valentina and Puzzle hosts."""

    def __init__(self) -> None:
        self.valentina = JsonLineCommandBackend("GARMENTCAD_VALENTINA_COMMAND")
        self.puzzle = JsonLineCommandBackend("GARMENTCAD_PUZZLE_COMMAND")

    @staticmethod
    def _is_puzzle(operation: Operation) -> bool:
        return operation.domain.value == "layout" or operation.action == "export.layout"

    def preview(
        self, project_root: Path, change_set_id: str, operations: list[Operation]
    ) -> ChangeSummary:
        valentina = [operation for operation in operations if not self._is_puzzle(operation)]
        puzzle = [operation for operation in operations if self._is_puzzle(operation)]
        summaries: list[ChangeSummary] = []
        if valentina:
            summaries.append(self.valentina.preview(project_root, change_set_id, valentina))
        if puzzle:
            summaries.append(self.puzzle.preview(project_root, change_set_id, puzzle))
        return merge_summaries(summaries)

    def commit(self, project_root: Path, change_set_id: str, operations: list[Operation]) -> None:
        if any(not self._is_puzzle(operation) for operation in operations):
            self.valentina.commit(project_root, change_set_id)
        if any(self._is_puzzle(operation) for operation in operations):
            self.puzzle.commit(project_root, change_set_id)


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
