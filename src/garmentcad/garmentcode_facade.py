from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from garmentcad.errors import CommandBackendUnavailable
from garmentcad.models import ChangeSummary, Operation


class GarmentCodeFacade:
    """Stable process facade over the pinned upstream GarmentCode object model."""

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("GARMENTCAD_GARMENTCODE_COMMAND")
        if self.command is None:
            repository = Path(__file__).resolve().parents[2]
            bundled = repository / "scripts/garmentcode-command-host.sh"
            if bundled.is_file():
                self.command = str(bundled)

    @property
    def available(self) -> bool:
        if not self.command:
            return False
        executable = self.command if Path(self.command).is_file() else shlex.split(self.command)[0]
        return Path(executable).is_file()

    def _call(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.command:
            raise CommandBackendUnavailable(
                "GARMENTCAD_GARMENTCODE_COMMAND is not configured; run bootstrap-macos"
            )
        command = [self.command] if Path(self.command).is_file() else shlex.split(self.command)
        process = subprocess.run(
            command,
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        try:
            response = json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise CommandBackendUnavailable(
                process.stderr.strip() or "GarmentCode host returned invalid JSON"
            ) from error
        if process.returncode != 0 or not response.get("ok"):
            detail = response.get("error", {})
            raise CommandBackendUnavailable(
                f"{detail.get('code', 'garmentcode_error')}: "
                f"{detail.get('message', process.stderr.strip())}"
            )
        return response

    def service_info(self) -> dict[str, Any]:
        return self._call({"method": "service.info"})

    def create_document(self, output_path: Path, project_id: str) -> dict[str, Any]:
        """Ask the native GarmentCode model to author a new truth document."""
        return self._call(
            {
                "method": "document.create",
                "output_path": str(output_path),
                "project_id": project_id,
            }
        )

    def preview_document(
        self,
        source_path: Path,
        output_path: Path,
        operations: list[Operation],
    ) -> tuple[ChangeSummary, dict[str, Any]]:
        """Apply commands and save a candidate entirely inside the native host."""
        response = self._call(
            {
                "method": "document.preview",
                "source_path": str(source_path),
                "output_path": str(output_path),
                "operations": [operation.model_dump(mode="json") for operation in operations],
            }
        )
        return ChangeSummary.model_validate(response["summary"]), response

    def validate_document(self, source_path: Path) -> dict[str, Any]:
        return self._call(
            {"method": "document.validate", "source_path": str(source_path)}
        )["diagnostics"]

    def export_document(
        self, source_path: Path, output_directory: Path, formats: list[str]
    ) -> dict[str, Any]:
        """Export derivatives inside the pinned native GarmentCode environment."""
        return self._call(
            {
                "method": "document.export",
                "source_path": str(source_path),
                "output_directory": str(output_directory),
                "formats": formats,
            }
        )
