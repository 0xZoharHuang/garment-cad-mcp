from __future__ import annotations

import os

import pytest

from garmentcad.project import Project
from garmentcad.recipes import (
    DRAFTS,
    draft_qualification_pattern,
    export_qualification_pattern,
    qualification_snapshot,
    redraft_driving_measurement,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("GARMENTCAD_VALENTINA_COMMAND"), reason="native Valentina host is not built"
)


def _piece_width(snapshot, alias: str) -> float:
    piece = next(piece for piece in snapshot["pieces"] if piece["alias"] == alias)
    xs = [node["x_mm"] for node in piece["contour"]]
    return max(xs) - min(xs)


@pytest.mark.parametrize("kind", sorted(DRAFTS))
def test_from_scratch_recipe_redrafts_reopens_and_exports(tmp_path, kind):
    project = Project.create(tmp_path / kind, name=DRAFTS[kind].name)
    draft_qualification_pattern(project.root, kind)
    before = qualification_snapshot(project.root)
    assert len(before["pieces"]) == len(DRAFTS[kind].panels)
    assert all(piece["seam_allowance"] for piece in before["pieces"])
    first_alias = DRAFTS[kind].panels[0].alias
    before_width = _piece_width(before, first_alias)

    redraft_driving_measurement(project.root, kind)
    reopened = Project.open(project.root)
    after = qualification_snapshot(reopened.root)
    assert _piece_width(after, first_alias) != pytest.approx(before_width, abs=0.1)

    exported = export_qualification_pattern(reopened.root, kind)
    assert len(exported.resources) == 3
    assert Project.open(project.root).status()["externally_modified"] is False
