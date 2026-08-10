from __future__ import annotations

import os
from pathlib import Path

import pytest

from garmentcad.corpus import _case_result, discover_corpus


def test_public_corpus_manifest_classifies_every_valentina_pattern():
    cases = discover_corpus()
    assert len(cases) == 85
    assert sum(case.xml_status == "valid" for case in cases) == 83
    assert sum(case.fixture_kind == "expected_invalid" for case in cases) == 2
    assert any(case.category == "jacket" and case.pieces >= 30 for case in cases)
    assert any(case.category == "shirt" and case.measurement_source for case in cases)
    assert all(len(case.sha256) == 64 for case in cases)


def test_manifest_finds_complex_and_historical_formats():
    cases = discover_corpus()
    valid = [case for case in cases if case.xml_status == "valid"]
    assert len({case.version for case in valid}) >= 5
    assert max(case.bytes for case in valid) > 1_000_000
    assert any(case.embedded_images for case in valid)
    assert any(case.dependency_status == "missing" for case in valid)


@pytest.mark.skipif(
    not os.environ.get("GARMENTCAD_VALENTINA_COMMAND"), reason="native Valentina host is not built"
)
def test_native_corpus_case_snapshots_mutates_reopens_and_reverses(tmp_path):
    repo = Path(__file__).parents[1]
    case = next(
        case
        for case in discover_corpus(repo)
        if case.source == "src/test/CollectionTest/tst_valentina/issue_372.val"
    )
    result = _case_result(case, repo, tmp_path, mutate=True)
    assert result["status"] == "pass", result.get("error")
    assert result["checks"]["snapshot_deterministic"] is True
    assert result["checks"]["restored_semantic_snapshot"] is True
    assert result["checks"]["restored_pattern_bytes"] is True
