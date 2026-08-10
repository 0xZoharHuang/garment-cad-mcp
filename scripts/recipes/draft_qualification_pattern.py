"""Create a complete multi-piece CAD qualification draft through native Valentina commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from garmentcad.project import Project
from garmentcad.recipes import DRAFTS, draft_qualification_pattern, qualification_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=sorted(DRAFTS))
    parser.add_argument("project", type=Path)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    if args.create:
        Project.create(args.project, name=DRAFTS[args.kind].name)
    results = draft_qualification_pattern(args.project, args.kind)
    snapshot = qualification_snapshot(args.project)
    print(
        json.dumps(
            {
                "kind": args.kind,
                "revision": results[-1].revision,
                "pieces": [piece["alias"] for piece in snapshot["pieces"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
