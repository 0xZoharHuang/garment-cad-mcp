from __future__ import annotations

from pathlib import Path
from typing import Any

from garmentcad.models import ObjectRef, Operation, OperationDomain, ToolResult
from garmentcad.project import Project


def reference(value: str | None) -> ObjectRef | None:
    if value is None:
        return None
    return ObjectRef(uuid=value) if _looks_like_uuid(value) else ObjectRef(alias=value)


def _looks_like_uuid(value: str) -> bool:
    return len(value) == 36 and value.count("-") == 4


def execute_atomic(
    project_path: str | Path,
    *,
    domain: OperationDomain,
    action: str,
    arguments: dict[str, Any] | None = None,
    target: str | None = None,
    message: str = "",
    author: str = "agent",
    commit: bool = False,
) -> ToolResult:
    project = Project.open(project_path)
    operation = Operation(
        domain=domain,
        action=action,
        target=reference(target),
        arguments=arguments or {},
    )
    result = project.preview(message=message, author=author, operations=[operation])
    if commit and result.ok and result.preview_token:
        return project.commit(result.preview_token)
    return result


class GarmentSDK:
    """Stable typed facade used by Python recipes; MCP delegates to the same functions."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)

    def panel_create(
        self,
        alias: str,
        vertices_mm: list[list[float]],
        *,
        translation_mm: list[float] | None = None,
        rotation_deg: list[float] | None = None,
        commit: bool = False,
    ) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="panel.create",
            arguments={
                "alias": alias,
                "vertices_mm": vertices_mm,
                "translation_mm": translation_mm or [0, 0, 0],
                "rotation_deg": rotation_deg or [0, 0, 0],
            },
            commit=commit,
        )

    def panel_delete(self, panel: str, *, commit: bool = False) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="panel.delete",
            target=panel,
            commit=commit,
        )

    def panel_transform(
        self,
        panel: str,
        *,
        translation_mm: list[float] | None = None,
        rotation_deg: list[float] | None = None,
        commit: bool = False,
    ) -> ToolResult:
        arguments: dict[str, Any] = {}
        if translation_mm is not None:
            arguments["translation_mm"] = translation_mm
        if rotation_deg is not None:
            arguments["rotation_deg"] = rotation_deg
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="panel.transform",
            arguments=arguments,
            target=panel,
            commit=commit,
        )

    def interface_define(
        self, alias: str, panel: str, edge_indices: list[int], *, commit: bool = False
    ) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="interface.define",
            arguments={
                "alias": alias,
                "panel": reference(panel).model_dump(exclude_none=True),
                "edge_indices": edge_indices,
            },
            commit=commit,
        )

    def stitch_create(
        self, alias: str, interface_a: str, interface_b: str, *, commit: bool = False
    ) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="stitch.create",
            arguments={
                "alias": alias,
                "interface_a": reference(interface_a).model_dump(exclude_none=True),
                "interface_b": reference(interface_b).model_dump(exclude_none=True),
            },
            commit=commit,
        )

    def interface_delete(self, interface: str, *, commit: bool = False) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="interface.delete",
            target=interface,
            commit=commit,
        )

    def stitch_delete(self, stitch: str, *, commit: bool = False) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="stitch.delete",
            target=stitch,
            commit=commit,
        )

    def validate(self) -> ToolResult:
        return execute_atomic(
            self.project_path,
            domain=OperationDomain.ASSEMBLY,
            action="validate",
        )

    def valentina(
        self,
        action: str,
        arguments: dict[str, Any],
        *,
        target: str | None = None,
        commit: bool = False,
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
            commit=commit,
        )
