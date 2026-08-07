#!/usr/bin/env python3
"""Hold the Garment Project writer lock for the lifetime of a GUI process."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from garmentcad.locking import ProjectLock
from garmentcad.project import Project


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    if options.command[:1] == ["--"]:
        options.command = options.command[1:]
    if not options.command:
        parser.error("a GUI command is required after --")
    project = Project.open(options.project)
    status_before = project.status()
    if status_before["externally_modified"]:
        raise RuntimeError(
            "Project already contains unrecorded external changes; "
            "commit a validated revision first"
        )
    with ProjectLock(project.root / ".garmentcad/project.lock"):
        base_revision = project.current_revision
        base_hash = project.status()["content_hash"]
        preimage = project._snapshot(base_revision + 1)
        try:
            status = subprocess.run(options.command, check=False).returncode
        except Exception:
            shutil.rmtree(preimage)
            raise
        result = project.record_gui_revision(
            preimage=preimage,
            base_revision=base_revision,
            base_content_hash=base_hash,
            application=Path(options.command[0]).name,
        )
    print(result.message)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
