from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from garmentcad.storage import atomic_write_bytes, atomic_write_json, read_json, sha256_bytes


class ArtifactStore:
    """Immutable, content-addressed project artifacts with small metadata sidecars."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root / "artifacts/sha256"

    def put(
        self,
        payload: bytes,
        *,
        filename: str,
        kind: str,
        revision: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        digest = sha256_bytes(payload)
        directory = self.root / digest[:2] / digest
        blob = directory / "blob"
        if blob.exists() and blob.read_bytes() != payload:
            raise RuntimeError("SHA-256 collision in artifact store")
        if not blob.exists():
            atomic_write_bytes(blob, payload)
        sidecar = directory / "metadata.json"
        current = read_json(sidecar, default={})
        names = sorted({*current.get("filenames", []), filename})
        record = {
            "schema_version": "1.0",
            "sha256": digest,
            "size": len(payload),
            "media_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "kind": kind,
            "revision": revision,
            "filenames": names,
            "metadata": metadata or {},
        }
        atomic_write_json(sidecar, record)
        return f"garment://artifact/sha256/{digest}"

    def resolve(self, digest: str) -> tuple[Path, dict[str, Any]]:
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Invalid artifact digest")
        directory = self.root / digest[:2] / digest
        blob = directory / "blob"
        metadata = read_json(directory / "metadata.json")
        if not blob.is_file() or metadata is None:
            raise FileNotFoundError(digest)
        return blob, metadata
