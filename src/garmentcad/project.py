from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from garmentcad.artifacts import ArtifactStore
from garmentcad.assembly import preview_assembly, thumbnail_svg
from garmentcad.backends import NativeCommandRouter, ProjectMetadataBackend, merge_summaries
from garmentcad.errors import (
    ChangeSetIntegrityError,
    ChangeSetNotFoundError,
    ProjectNotFoundError,
    StaleRevisionError,
)
from garmentcad.locking import ProjectLock
from garmentcad.models import (
    ChangeSet,
    ObjectRef,
    Operation,
    OperationDomain,
    ProjectManifest,
    Revision,
    ToolResult,
    utc_now,
)
from garmentcad.storage import (
    atomic_write_bytes,
    atomic_write_json,
    canonical_json,
    read_json,
    sha256_bytes,
    sha256_file,
)

DIRECTORIES = (
    "pattern",
    "measurements",
    "layout",
    "assembly",
    "simulation/bodies",
    "simulation/fabrics",
    "simulation/config",
    "simulation/cameras",
    "artifacts",
    ".garmentcad/changesets",
    ".garmentcad/revisions",
    ".garmentcad/snapshots",
)

NATIVE_VALENTINA_DOMAINS = {
    OperationDomain.PATTERN,
    OperationDomain.MEASUREMENTS,
    OperationDomain.LAYOUT,
    OperationDomain.EXPORT,
}


class CommandNamespace:
    def __init__(self, project: Project, domain: OperationDomain, prefix: str = "") -> None:
        self.project = project
        self.domain = domain
        self.prefix = prefix

    def __getattr__(self, name: str) -> CommandNamespace:
        prefix = f"{self.prefix}.{name}" if self.prefix else name
        return CommandNamespace(self.project, self.domain, prefix)

    def __call__(
        self,
        *,
        target: ObjectRef | str | None = None,
        **arguments: Any,
    ) -> Operation:
        if not self.prefix:
            raise ValueError("A command name is required")
        reference = target
        if isinstance(target, str):
            reference = ObjectRef(alias=target)
        operation = Operation(
            domain=self.domain,
            action=self._contract_action(),
            target=reference,
            arguments=arguments,
        )
        self.project.stage(operation)
        return operation

    def _contract_action(self) -> str:
        parts = self.prefix.split(".")
        if self.domain == OperationDomain.PATTERN:
            leaf = parts[-1]
            aliases = {"create": parts[-2] if len(parts) > 1 else "create"}
            return f"pattern.{aliases.get(leaf, leaf)}"
        if self.domain == OperationDomain.MEASUREMENTS:
            return f"measurement.{parts[-1]}"
        if self.domain == OperationDomain.LAYOUT:
            return f"layout.{parts[-1]}"
        if self.domain == OperationDomain.ASSEMBLY:
            assembly_aliases = {"stitch": "stitch.create", "panel": "panel.create"}
            return assembly_aliases.get(parts[-1], self.prefix)
        return f"{self.domain.value}.{self.prefix}"


class Project:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.manifest_path = self.root / "garment.json"
        if not self.manifest_path.exists():
            raise ProjectNotFoundError(f"Not a garment project: {self.root}")
        self._pending: list[Operation] = []
        self.pattern = CommandNamespace(self, OperationDomain.PATTERN)
        self.measurements = CommandNamespace(self, OperationDomain.MEASUREMENTS)
        self.layout = CommandNamespace(self, OperationDomain.LAYOUT)
        self.assembly = CommandNamespace(self, OperationDomain.ASSEMBLY)
        self.simulation = CommandNamespace(self, OperationDomain.SIMULATION)
        self.export = CommandNamespace(self, OperationDomain.EXPORT)

    @classmethod
    def create(cls, root: str | Path, name: str | None = None) -> Project:
        root_path = Path(root).resolve()
        root_path.mkdir(parents=True, exist_ok=False)
        for directory in DIRECTORIES:
            (root_path / directory).mkdir(parents=True, exist_ok=True)
        template = Path(__file__).with_name("templates") / "empty.val"
        shutil.copy2(template, root_path / "pattern/main.val")
        manifest = ProjectManifest(name=name or root_path.name)
        atomic_write_json(root_path / "garment.json", manifest.model_dump(mode="json"))
        atomic_write_json(
            root_path / "assembly/assembly.json",
            {
                "schema_version": "1.0",
                "units": "mm",
                "panels": {},
                "interfaces": {},
                "stitches": {},
            },
        )
        atomic_write_json(
            root_path / ".garmentcad/aliases.json", {"schema_version": "1.0", "objects": {}}
        )
        atomic_write_json(
            root_path / ".garmentcad/revisions/0.json",
            {
                "schema_version": "1.0",
                "number": 0,
                "parent": None,
                "change_set_id": "initial",
                "committed_at": manifest.created_at.isoformat(),
                "author": "system",
                "message": "Initial project",
                "content_hash": cls._content_hash_static(root_path),
                "reverse_of": None,
            },
        )
        return cls(root_path)

    @classmethod
    def open(cls, root: str | Path) -> Project:
        return cls(Path(root))

    @staticmethod
    def _content_hash_static(root: Path) -> str:
        tracked: list[tuple[str, str]] = []
        roots = [root / "garment.json", root / ".garmentcad/aliases.json"]
        for directory in ("pattern", "measurements", "layout", "assembly", "simulation"):
            base = root / directory
            if base.exists():
                roots.extend(path for path in base.rglob("*") if path.is_file())
        for path in roots:
            if path.is_file():
                tracked.append((str(path.relative_to(root)), sha256_file(path)))
        tracked.sort()
        return sha256_bytes(canonical_json(tracked))

    @property
    def manifest(self) -> ProjectManifest:
        return ProjectManifest.model_validate(read_json(self.manifest_path))

    @property
    def current_revision(self) -> int:
        return self.manifest.current_revision

    def stage(self, operation: Operation) -> None:
        self._pending.append(operation)

    def clear(self) -> None:
        self._pending.clear()

    def preview(
        self,
        *,
        message: str = "",
        author: str = "agent",
        operations: list[Operation] | None = None,
        validate_backends: bool = True,
    ) -> ToolResult:
        selected = list(operations if operations is not None else self._pending)
        if not selected:
            raise ValueError("No operations staged")
        summaries = []
        by_domain: dict[OperationDomain, list[Operation]] = defaultdict(list)
        for operation in selected:
            by_domain[operation.domain].append(operation)
        change_set = ChangeSet(
            project_id=self.manifest.project_id,
            base_revision=self.current_revision,
            base_content_hash=self._content_hash_static(self.root),
            author=author,
            message=message,
            operations=selected,
        )
        preview_directory = self.root / f".garmentcad/changesets/{change_set.id}"
        preview_directory.mkdir(parents=True, exist_ok=False)
        for domain, domain_operations in by_domain.items():
            if domain == OperationDomain.ASSEMBLY:
                assembly, summary = preview_assembly(self.root, domain_operations)
                atomic_write_json(preview_directory / "assembly.json", assembly)
                (preview_directory / "thumbnail.svg").write_text(
                    thumbnail_svg(assembly), encoding="utf-8"
                )
                change_set.preview_resources.append(
                    f"garment://project/{change_set.project_id}/changeset/{change_set.id}/assembly"
                )
                summaries.append(summary)
            elif domain == OperationDomain.SIMULATION:
                from garmentcad.simulation_inputs import preview_simulation_configuration

                staged_manifest, summary = preview_simulation_configuration(
                    self.root, preview_directory, domain_operations
                )
                atomic_write_json(
                    preview_directory / "garment.json",
                    staged_manifest.model_dump(mode="json"),
                )
                summaries.append(summary)
            elif validate_backends and domain not in NATIVE_VALENTINA_DOMAINS:
                summaries.append(
                    ProjectMetadataBackend().preview(
                        self.root, change_set.id, domain_operations
                    )
                )
        native_operations = [
            operation for operation in selected if operation.domain in NATIVE_VALENTINA_DOMAINS
        ]
        if validate_backends and native_operations:
            summaries.append(
                NativeCommandRouter().preview(self.root, change_set.id, native_operations)
            )
        thumbnail_uri = (
            f"garment://project/{change_set.project_id}/changeset/{change_set.id}/thumbnail"
        )
        if any(
            (preview_directory / filename).exists()
            for filename in ("thumbnail.png", "thumbnail.svg")
        ):
            change_set.preview_resources.append(thumbnail_uri)
        change_set.summary = merge_summaries(summaries)
        self._externalize_summary_details(change_set, preview_directory)
        change_set.preview_content_hash = self._tree_content_hash(preview_directory)
        atomic_write_json(
            self.root / f".garmentcad/changesets/{change_set.id}.json",
            change_set.model_dump(mode="json"),
        )
        return ToolResult(
            ok=not any(issue.severity == "error" for issue in change_set.summary.issues),
            project_id=change_set.project_id,
            revision=change_set.base_revision,
            preview_token=change_set.id,
            summary=change_set.summary,
            resources=[f"garment://project/{change_set.project_id}/changeset/{change_set.id}"],
            thumbnails=[thumbnail_uri] if thumbnail_uri in change_set.preview_resources else [],
            message="Preview created",
        )

    def commit(self, preview_token: str) -> ToolResult:
        change_path = self.root / f".garmentcad/changesets/{preview_token}.json"
        raw = read_json(change_path)
        if raw is None:
            raise ChangeSetNotFoundError(preview_token)
        change_set = ChangeSet.model_validate(raw)
        if change_set.status != "preview":
            raise ChangeSetIntegrityError(
                f"Change-set {preview_token} is already {change_set.status}"
            )
        if any(issue.severity == "error" for issue in change_set.summary.issues):
            raise ValueError("Cannot commit a preview with validation errors")
        with ProjectLock(self.root / ".garmentcad/project.lock"):
            preview_directory = self.root / f".garmentcad/changesets/{change_set.id}"
            if self._tree_content_hash(preview_directory) != change_set.preview_content_hash:
                raise ChangeSetIntegrityError(
                    "Preview candidate changed after validation; create a new preview"
                )
            manifest = self.manifest
            if manifest.current_revision != change_set.base_revision:
                raise StaleRevisionError(
                    f"Preview is based on revision {change_set.base_revision}; "
                    f"current revision is {manifest.current_revision}"
                )
            current_hash = self._content_hash_static(self.root)
            if current_hash != change_set.base_content_hash:
                raise StaleRevisionError(
                    "Project files changed after preview (possibly through a GUI); "
                    "refresh and preview again"
                )
            next_revision = manifest.current_revision + 1
            snapshot = self._snapshot(next_revision)
            artifact_resources: list[str] = []
            revision_path = self.root / f".garmentcad/revisions/{next_revision}.json"
            event_path = self.root / ".garmentcad/events.jsonl"
            event_size = event_path.stat().st_size if event_path.exists() else 0
            try:
                domains = {operation.domain for operation in change_set.operations}
                for domain in domains:
                    if domain == OperationDomain.ASSEMBLY:
                        staged = self.root / f".garmentcad/changesets/{change_set.id}/assembly.json"
                        if not staged.exists():
                            raise ChangeSetNotFoundError(
                                f"Missing staged assembly for {change_set.id}"
                            )
                        atomic_write_json(
                            self.root / "assembly/assembly.json",
                            read_json(staged),
                        )
                    elif domain == OperationDomain.SIMULATION:
                        staged = self.root / f".garmentcad/changesets/{change_set.id}/garment.json"
                        if not staged.exists():
                            raise ChangeSetNotFoundError(
                                f"Missing staged manifest for {change_set.id}"
                            )
                        configured = ProjectManifest.model_validate(read_json(staged))
                        staged_simulation = (
                            self.root / f".garmentcad/changesets/{change_set.id}/simulation"
                        )
                        if staged_simulation.is_dir():
                            candidate_root = (
                                self.root / f".garmentcad/changesets/{change_set.id}"
                            )
                            for source in sorted(staged_simulation.rglob("*")):
                                if source.is_file():
                                    destination = self.root / source.relative_to(candidate_root)
                                    atomic_write_bytes(destination, source.read_bytes())
                        for field_name in (
                            "active_body",
                            "active_body_measurements",
                            "active_body_segmentation",
                            "active_fabric",
                            "active_simulation_config",
                            "active_camera_config",
                        ):
                            setattr(manifest, field_name, getattr(configured, field_name))
                if domains & NATIVE_VALENTINA_DOMAINS:
                    native_operations = [
                        operation
                        for operation in change_set.operations
                        if operation.domain in NATIVE_VALENTINA_DOMAINS
                    ]
                    NativeCommandRouter().commit(
                        self.root, change_set.id, native_operations
                    )
                staged_exports = (
                    self.root
                    / f".garmentcad/changesets/{change_set.id}/artifacts/exports"
                )
                if staged_exports.is_dir():
                    store = ArtifactStore(self.root)
                    for exported in sorted(staged_exports.rglob("*")):
                        if exported.is_file():
                            artifact_resources.append(
                                store.put(
                                    exported.read_bytes(),
                                    filename=exported.name,
                                    kind="cad_export",
                                    revision=next_revision,
                                    metadata={
                                        "change_set_id": change_set.id,
                                        "relative_path": str(
                                            exported.relative_to(staged_exports)
                                        ),
                                    },
                                )
                            )
                change_set.status = "committed"
                manifest.current_revision = next_revision
                manifest.updated_at = utc_now()
                atomic_write_json(self.manifest_path, manifest.model_dump(mode="json"))
                revision = Revision(
                    number=next_revision,
                    parent=next_revision - 1,
                    change_set_id=change_set.id,
                    author=change_set.author,
                    message=change_set.message,
                    content_hash=self._content_hash_static(self.root),
                )
                atomic_write_json(revision_path, revision.model_dump(mode="json"))
                atomic_write_json(change_path, change_set.model_dump(mode="json"))
                with event_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(revision.model_dump(mode="json"), ensure_ascii=False) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                self._restore_snapshot(snapshot)
                revision_path.unlink(missing_ok=True)
                if event_path.exists():
                    with event_path.open("r+b") as stream:
                        stream.truncate(event_size)
                atomic_write_json(change_path, raw)
                shutil.rmtree(snapshot)
                raise
        self.clear()
        return ToolResult(
            ok=True,
            project_id=manifest.project_id,
            revision=next_revision,
            summary=change_set.summary,
            resources=artifact_resources,
            message="Change-set committed",
        )

    def _snapshot(self, revision: int) -> Path:
        snapshot = self.root / f".garmentcad/snapshots/{revision}"
        snapshot.mkdir(parents=True, exist_ok=False)
        for relative in ("garment.json", ".garmentcad/aliases.json"):
            source = self.root / relative
            if source.exists():
                destination = snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        for relative in ("pattern", "measurements", "layout", "assembly", "simulation"):
            source = self.root / relative
            if source.exists():
                shutil.copytree(source, snapshot / relative)
        return snapshot

    @staticmethod
    def _tree_content_hash(root: Path) -> str:
        files = []
        if root.is_dir():
            files = [
                (str(path.relative_to(root)), sha256_file(path))
                for path in root.rglob("*")
                if path.is_file()
            ]
        return sha256_bytes(canonical_json(sorted(files)))

    @staticmethod
    def _externalize_summary_details(change_set: ChangeSet, preview_directory: Path) -> None:
        for index, issue in enumerate(change_set.summary.issues):
            payload = canonical_json(issue.details)
            if not issue.details or (
                issue.code != "dependency_query" and len(payload) <= 4096
            ):
                continue
            relative = f"details/issue-{index:04d}.json"
            atomic_write_json(preview_directory / relative, issue.details)
            uri = (
                f"garment://project/{change_set.project_id}/changeset/"
                f"{change_set.id}/{relative}"
            )
            issue.details = {"resource_uri": uri, "byte_length": len(payload)}
            change_set.preview_resources.append(uri)

    def _restore_snapshot(self, snapshot: Path) -> None:
        for relative in ("pattern", "measurements", "layout", "assembly", "simulation"):
            destination = self.root / relative
            source = snapshot / relative
            if source.exists() and destination.exists():
                shutil.rmtree(destination)
        for source in sorted(path for path in snapshot.rglob("*") if path.is_dir()):
            (self.root / source.relative_to(snapshot)).mkdir(parents=True, exist_ok=True)
        for source in snapshot.rglob("*"):
            if source.is_file():
                destination = self.root / source.relative_to(snapshot)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def record_gui_revision(
        self,
        *,
        preimage: Path,
        base_revision: int,
        base_content_hash: str,
        application: str,
    ) -> ToolResult:
        """Record files saved by a repository-launched GUI while its writer lock is held."""
        manifest = self.manifest
        if manifest.current_revision != base_revision:
            raise StaleRevisionError("Project revision changed during the GUI session")
        current_hash = self._content_hash_static(self.root)
        if current_hash == base_content_hash:
            shutil.rmtree(preimage)
            return ToolResult(
                ok=True,
                project_id=manifest.project_id,
                revision=base_revision,
                message="GUI session made no project changes",
            )
        next_revision = base_revision + 1
        if preimage != self.root / f".garmentcad/snapshots/{next_revision}":
            raise ValueError("GUI preimage does not match the next revision")
        change_set = ChangeSet(
            id=f"gui-{uuid4()}",
            project_id=manifest.project_id,
            base_revision=base_revision,
            base_content_hash=base_content_hash,
            author="gui",
            message=f"{application} GUI save",
            operations=[
                Operation(
                    domain=OperationDomain.PROJECT,
                    action="project.gui_save",
                    arguments={"application": application},
                )
            ],
            status="committed",
        )
        change_path = self.root / f".garmentcad/changesets/{change_set.id}.json"
        revision_path = self.root / f".garmentcad/revisions/{next_revision}.json"
        event_path = self.root / ".garmentcad/events.jsonl"
        event_size = event_path.stat().st_size if event_path.exists() else 0
        old_manifest = manifest.model_dump(mode="json")
        try:
            manifest.current_revision = next_revision
            manifest.updated_at = utc_now()
            atomic_write_json(self.manifest_path, manifest.model_dump(mode="json"))
            revision = Revision(
                number=next_revision,
                parent=base_revision,
                change_set_id=change_set.id,
                author="gui",
                message=change_set.message,
                content_hash=self._content_hash_static(self.root),
            )
            atomic_write_json(change_path, change_set.model_dump(mode="json"))
            atomic_write_json(revision_path, revision.model_dump(mode="json"))
            with event_path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(revision.model_dump(mode="json"), ensure_ascii=False) + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            # Roll back only metadata. GUI-authored pattern/layout/measurement files are preserved.
            atomic_write_json(self.manifest_path, old_manifest)
            change_path.unlink(missing_ok=True)
            revision_path.unlink(missing_ok=True)
            if event_path.exists():
                with event_path.open("r+b") as stream:
                    stream.truncate(event_size)
            raise
        return ToolResult(
            ok=True,
            project_id=manifest.project_id,
            revision=next_revision,
            summary=change_set.summary,
            message=f"{application} GUI save recorded as revision {next_revision}",
        )

    def revert(self, revision: int, *, author: str = "agent", message: str = "") -> ToolResult:
        snapshot = self.root / f".garmentcad/snapshots/{revision}"
        if not snapshot.exists():
            raise ChangeSetNotFoundError(f"No reverse snapshot for revision {revision}")
        with ProjectLock(self.root / ".garmentcad/project.lock"):
            current = self.manifest.current_revision
            safety_snapshot = self._snapshot(current + 1)
            revision_path = self.root / f".garmentcad/revisions/{current + 1}.json"
            event_path = self.root / ".garmentcad/events.jsonl"
            event_size = event_path.stat().st_size if event_path.exists() else 0
            try:
                self._restore_snapshot(snapshot)
                manifest = self.manifest
                manifest.current_revision = current + 1
                manifest.updated_at = utc_now()
                atomic_write_json(self.manifest_path, manifest.model_dump(mode="json"))
                record = Revision(
                    number=current + 1,
                    parent=current,
                    change_set_id=f"revert-{revision}",
                    author=author,
                    message=message or f"Revert revision {revision}",
                    content_hash=self._content_hash_static(self.root),
                    reverse_of=revision,
                )
                atomic_write_json(revision_path, record.model_dump(mode="json"))
                with event_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                self._restore_snapshot(safety_snapshot)
                revision_path.unlink(missing_ok=True)
                if event_path.exists():
                    with event_path.open("r+b") as stream:
                        stream.truncate(event_size)
                shutil.rmtree(safety_snapshot)
                raise
        return ToolResult(
            ok=True,
            project_id=manifest.project_id,
            revision=current + 1,
            message=f"Revision {revision} reverted as revision {current + 1}",
        )

    def discard(self, preview_token: str) -> None:
        change_path = self.root / f".garmentcad/changesets/{preview_token}.json"
        raw = read_json(change_path)
        if raw is None:
            raise ChangeSetNotFoundError(preview_token)
        change_set = ChangeSet.model_validate(raw)
        change_set.status = "discarded"
        atomic_write_json(change_path, change_set.model_dump(mode="json"))

    def attach_file(self, source: str | Path, relative_destination: str) -> Path:
        source_path = Path(source).resolve()
        destination = (self.root / relative_destination).resolve()
        if self.root not in destination.parents:
            raise ValueError("Destination must be inside the garment project")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return destination

    def status(self) -> dict[str, Any]:
        manifest = self.manifest
        current_hash = self._content_hash_static(self.root)
        revision = read_json(self.root / f".garmentcad/revisions/{manifest.current_revision}.json")
        return {
            "root": str(self.root),
            "project": manifest.model_dump(mode="json"),
            "pending_operations": len(self._pending),
            "content_hash": current_hash,
            "externally_modified": bool(revision and revision.get("content_hash") != current_hash),
        }

    def __enter__(self) -> Project:
        return self

    def __exit__(self, *args: Any) -> None:
        self.clear()
