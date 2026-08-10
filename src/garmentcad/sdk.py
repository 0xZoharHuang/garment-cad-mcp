from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from garmentcad.models import ObjectRef, Operation, OperationDomain, ToolResult
from garmentcad.project import Project

if TYPE_CHECKING:
    from garmentcad.generated.assembly_commands import AssemblyCommands
    from garmentcad.generated.atomic_commands import AtomicCommands


def reference(value: str | None) -> ObjectRef | None:
    if value is None:
        return None
    return ObjectRef(uuid=value) if _looks_like_uuid(value) else ObjectRef(alias=value)


def _looks_like_uuid(value: str) -> bool:
    return len(value) == 36 and value.count("-") == 4


DEFAULT_ARGUMENTS: dict[str, dict[str, Any]] = {
    "panel.transform": {"center_x": False},
    "component.transform": {
        "translation_delta_mm": [0, 0, 0],
        "rotation_delta_deg": [0, 0, 0],
    },
    "interface.define": {"reverse": False, "ruffle": 1.0, "right_wrong": False},
    "interface.update": {"reverse_order": False, "flip_edges": False},
    "stitch.create": {"direction": "auto"},
}


def canonical_arguments(action: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove wrapper defaults so SDK and MCP persist the same minimal command DTO."""
    canonical = dict(arguments)
    for name, default in DEFAULT_ARGUMENTS.get(action, {}).items():
        if canonical.get(name) == default:
            canonical.pop(name, None)
    return canonical


def execute_atomic(
    project_path: str | Path,
    *,
    domain: OperationDomain,
    action: str,
    arguments: dict[str, Any] | None = None,
    target: str | None = None,
    message: str = "",
    author: str = "agent",
) -> ToolResult:
    project = Project.open(project_path)
    operation = Operation(
        domain=domain,
        action=action,
        target=reference(target),
        arguments=canonical_arguments(action, arguments or {}),
    )
    return project.preview(message=message, author=author, operations=[operation])


class GarmentSDK:
    """Stable typed facade used by Python recipes; MCP delegates to the same functions."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)
        from garmentcad.generated.assembly_commands import AssemblyCommands
        from garmentcad.generated.atomic_commands import AtomicCommands

        self.commands: AtomicCommands = AtomicCommands(self.project_path)
        self.assembly_commands: AssemblyCommands = AssemblyCommands(self.project_path)

    def sync_assembly_from_pattern(
        self,
        *,
        bindings: dict[str, Any] | None = None,
        message: str = "",
        author: str = "agent",
    ) -> ToolResult:
        """Preview a native GarmentCode projection of the current Valentina truth."""
        from garmentcad.backends import JsonLineCommandBackend
        from garmentcad.storage import sha256_file

        project = Project.open(self.project_path)
        snapshot = JsonLineCommandBackend().snapshot(project.root)
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="assembly.sync_from_pattern",
            arguments={
                "snapshot": snapshot,
                "bindings": bindings or {},
                "source_project_id": project.manifest.project_id,
                "source_pattern_hash": sha256_file(project.root / project.manifest.pattern_file),
            },
            message=message,
            author=author,
        )

    def export_garmentcode(self, formats: list[str] | None = None) -> dict[str, Any]:
        """Create immutable JSON/OBJ/USD artifacts for the current assembly revision."""
        from garmentcad.exports import export_garmentcode

        return export_garmentcode(self.project_path, formats)

    def configure_simulation(
        self,
        *,
        body_mesh: str,
        body_measurements: str,
        body_segmentation: str,
        fabric: str,
        simulation_config: str,
        camera_config: str,
    ) -> ToolResult:
        """Select a complete revisioned simulation input set."""
        arguments = {
            "body_mesh": body_mesh,
            "body_measurements": body_measurements,
            "body_segmentation": body_segmentation,
            "fabric": fabric,
            "simulation_config": simulation_config,
            "camera_config": camera_config,
        }
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.SIMULATION,
            action="simulation.configure",
            arguments=arguments,
        )

    def valentina(
        self,
        action: str,
        arguments: dict[str, Any],
        *,
        target: str | None = None,
    ) -> ToolResult:
        """Call a reviewed Valentina catalog action through the native host."""
        from garmentcad.catalog import VALENTINA_TOOLS

        spec = next((item for item in VALENTINA_TOOLS if item.action == action), None)
        if spec is None:
            raise ValueError(f"Action is not in the Valentina catalog: {action}")
        prefix = action.split(".", 1)[0]
        domain = {
            "pattern": OperationDomain.PATTERN,
            "measurement": OperationDomain.MEASUREMENTS,
            "layout": OperationDomain.LAYOUT,
            "export": OperationDomain.EXPORT,
        }[prefix]
        return execute_atomic(
            self.project_path,
            domain=domain,
            action=action,
            arguments=arguments,
            target=target,
        )
