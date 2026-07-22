from __future__ import annotations

import json

import pytest

from market_regime_alpha.daily_research.artifacts import (
    DAILY_QUANT_DECISION_FILES,
    daily_quant_decision_artifact_id,
    publish_daily_quant_decision_artifact,
)
from market_regime_alpha.daily_research.contracts import DailyDataAuthority

from .conftest import make_entry, make_recommendation, make_snapshot


def test_publisher_writes_exact_hashed_non_overwriting_artifact(tmp_path) -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    entry = make_entry(snapshot, recommendation)

    output = publish_daily_quant_decision_artifact(
        root=tmp_path,
        snapshot=snapshot,
        recommendations=(recommendation,),
        entry_assessments=(entry,),
    )

    assert {path.name for path in output.iterdir()} == set(DAILY_QUANT_DECISION_FILES)
    checksums = json.loads((output / "SHA256SUMS.json").read_text())
    assert set(checksums) == set(DAILY_QUANT_DECISION_FILES) - {"SHA256SUMS.json"}
    manifest = json.loads((output / "manifest.json").read_text())
    assert output.name == manifest["artifact_id"]
    assert manifest["snapshot_id"] == str(snapshot.snapshot_id)
    assert manifest["recommendation_ids"] == [str(recommendation.recommendation_id)]
    assert manifest["entry_assessment_ids"] == [str(entry.entry_assessment_id)]
    assert manifest["evidence_authority"] == "NOT_FORMAL_OOS"

    with pytest.raises(FileExistsError):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(recommendation,),
            entry_assessments=(entry,),
        )


def test_publisher_requires_contiguous_ranks_without_silent_replacement(tmp_path) -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot, rank=2)
    entry = make_entry(snapshot, recommendation)

    with pytest.raises(ValueError, match="contiguous"):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(recommendation,),
            entry_assessments=(entry,),
        )


def test_publisher_requires_exact_entry_recommendation_coverage(tmp_path) -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)

    with pytest.raises(ValueError, match="Entry Assessment coverage"):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(recommendation,),
            entry_assessments=(),
        )


def test_test_fixture_never_receives_research_authority(tmp_path) -> None:
    snapshot = make_snapshot(authority=DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE)
    recommendation = make_recommendation(snapshot)
    entry = make_entry(snapshot, recommendation)

    output = publish_daily_quant_decision_artifact(
        root=tmp_path,
        snapshot=snapshot,
        recommendations=(recommendation,),
        entry_assessments=(entry,),
    )
    manifest = json.loads((output / "manifest.json").read_text())

    assert str(snapshot.snapshot_id).startswith("test-only-daily-snapshot-")
    assert output.name.startswith("test-only-daily-quant-decision-")
    assert manifest["data_authority"] == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"
    assert manifest["evidence_authority"] == "TEST_ONLY_NOT_RESEARCH_EVIDENCE"


def test_report_is_derived_from_structured_reasons(published_artifact) -> None:
    report = (published_artifact / "report.md").read_text()
    assert "B1_BASELINE_RANK" in report
    assert "STRUCTURE_INVALIDATED" in report
    assert "PRICE_STRUCTURE_VALID" in report
    assert "No Alpha or trading authority" in report
    assert "individual_strength=0.8" in report
    assert "9.8..10.1" in report


def test_package_identity_changes_when_recommendation_semantics_change() -> None:
    snapshot = make_snapshot()
    first_recommendation = make_recommendation(snapshot, score=0.75)
    second_recommendation = make_recommendation(snapshot, score=0.76)
    first_entry = make_entry(snapshot, first_recommendation)
    second_entry = make_entry(snapshot, second_recommendation)

    first = daily_quant_decision_artifact_id(
        snapshot=snapshot,
        recommendations=(first_recommendation,),
        entry_assessments=(first_entry,),
    )
    second = daily_quant_decision_artifact_id(
        snapshot=snapshot,
        recommendations=(second_recommendation,),
        entry_assessments=(second_entry,),
    )

    assert first != second
