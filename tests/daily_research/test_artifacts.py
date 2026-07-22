from __future__ import annotations

import json

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId, TargetId

from market_regime_alpha.daily_research.artifacts import (
    DAILY_QUANT_DECISION_FILES,
    daily_quant_decision_artifact_id,
    publish_daily_quant_decision_artifact,
)
from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyDataAuthority,
    DecisionDataQuality,
    EntryAssessment,
    EntryState,
    ScoreComponent,
)

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
    assert "feature-individual-strength-example-v1=0.8" in report
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


def test_package_identity_binds_snapshot_creation_provenance() -> None:
    first_snapshot = make_snapshot()
    second_snapshot = make_snapshot(created_at=first_snapshot.created_at.value.replace(minute=57))
    first_recommendation = make_recommendation(first_snapshot)
    second_recommendation = make_recommendation(second_snapshot)
    first_entry = make_entry(first_snapshot, first_recommendation)
    second_entry = make_entry(second_snapshot, second_recommendation)

    assert first_snapshot.snapshot_id == second_snapshot.snapshot_id
    assert daily_quant_decision_artifact_id(
        snapshot=first_snapshot,
        recommendations=(first_recommendation,),
        entry_assessments=(first_entry,),
    ) != daily_quant_decision_artifact_id(
        snapshot=second_snapshot,
        recommendations=(second_recommendation,),
        entry_assessments=(second_entry,),
    )


def test_publisher_reconstructs_rank_from_candidate_score(tmp_path) -> None:
    snapshot = make_snapshot()
    wrong_first = make_recommendation(snapshot, symbol="600001.SH", rank=1, score=0.5)
    wrong_second = make_recommendation(snapshot, symbol="600002.SH", rank=2, score=0.75)

    with pytest.raises(ValueError, match="score order"):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(wrong_first, wrong_second),
            entry_assessments=(
                make_entry(snapshot, wrong_first),
                make_entry(snapshot, wrong_second),
            ),
        )


def test_publisher_rejects_enter_for_insufficient_candidate(tmp_path) -> None:
    snapshot = make_snapshot()
    base = make_recommendation(snapshot)
    insufficient = CandidateRecommendation(
        **{**base.semantic_payload(), "data_quality": DecisionDataQuality.INSUFFICIENT}
    )
    enter = EntryAssessment(
        **{**make_entry(snapshot, insufficient).semantic_payload(), "entry_state": EntryState.ENTER}
    )

    with pytest.raises(ValueError, match="INSUFFICIENT Candidate must be REJECT"):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(insufficient,),
            entry_assessments=(enter,),
        )


def test_publisher_requires_registered_score_component_lineage(tmp_path) -> None:
    snapshot = make_snapshot()
    base = make_recommendation(snapshot)
    recommendation = CandidateRecommendation(
        **{
            **base.semantic_payload(),
            "score_components": (ScoreComponent(ArtifactId("invented-component-v1"), 0.75),),
        }
    )

    with pytest.raises(ValueError, match="registered component"):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(recommendation,),
            entry_assessments=(make_entry(snapshot, recommendation),),
        )


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ("target", "Target identity"),
        ("entry_model", "Entry model identity"),
        ("entry_configuration", "Entry configuration identity"),
    ],
)
def test_publisher_requires_result_identity_source_lineage(
    tmp_path,
    record: str,
    message: str,
) -> None:
    snapshot = make_snapshot()
    recommendation = make_recommendation(snapshot)
    if record == "target":
        recommendation = CandidateRecommendation(
            **{
                **recommendation.semantic_payload(),
                "target_definition": TargetId("unlinked-target-v1"),
            }
        )
    entry = make_entry(snapshot, recommendation)
    if record == "entry_model":
        entry = EntryAssessment(
            **{**entry.semantic_payload(), "model_identity": ModelId("unlinked-entry-model-v1")}
        )
    if record == "entry_configuration":
        entry = EntryAssessment(
            **{
                **entry.semantic_payload(),
                "configuration_identity": ArtifactId("unlinked-entry-config-v1"),
            }
        )

    with pytest.raises(ValueError, match=message):
        publish_daily_quant_decision_artifact(
            root=tmp_path,
            snapshot=snapshot,
            recommendations=(recommendation,),
            entry_assessments=(entry,),
        )
