from __future__ import annotations

from dataclasses import replace

from market_regime_alpha.daily_decision.entry import (
    ENTRY_PLUMBING_GATE_V0,
    EntryAssessment,
    EntryAssessmentState,
    assess_entry_plumbing,
)
from market_regime_alpha.daily_decision.recommendation import (
    CandidateDataQuality,
    project_candidate_recommendations,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def test_qualified_candidates_can_only_wait_for_a_validated_entry_model(
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    fixture = daily_decision_fixture
    recommendations = project_candidate_recommendations(
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        data_quality_report=fixture.quality_report,
    )

    assessments = assess_entry_plumbing(
        recommendations=recommendations,
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        source_manifest=fixture.source_manifest,
        data_quality_report=fixture.quality_report,
        eligibility_snapshot=fixture.reconciliation.eligibility_snapshot,
    )

    assert len(assessments) == len(recommendations)
    assert {item.entry_state for item in assessments} == {
        EntryAssessmentState.WAIT_CONFIRMATION
    }
    assert all(item.gate_id == ENTRY_PLUMBING_GATE_V0 for item in assessments)
    assert all(
        item.blocking_reasons == ("ENTRY_MODEL_NOT_YET_VALIDATED",)
        for item in assessments
    )
    assert all(
        item.prediction_run_id
        == next(
            recommendation.prediction_run_id
            for recommendation in recommendations
            if recommendation.recommendation_id == item.recommendation_id
        )
        for item in assessments
    )
    forbidden = {
        "ENTER",
        "entry_price",
        "reference_price",
        "position_size",
        "order",
        "order_size",
    }
    assert "ENTER" not in {state.value for state in EntryAssessmentState}
    assert all(
        forbidden.isdisjoint(item.to_canonical_dict()) for item in assessments
    )
    assert all(
        EntryAssessment.from_canonical_dict(item.to_canonical_dict()) == item
        for item in assessments
    )


def test_insufficient_candidate_quality_is_rejected(
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    fixture = daily_decision_fixture
    recommendations = project_candidate_recommendations(
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        data_quality_report=fixture.quality_report,
    )
    insufficient = (
        replace(
            recommendations[0],
            data_quality=CandidateDataQuality.INSUFFICIENT,
        ),
        *recommendations[1:],
    )

    assessments = assess_entry_plumbing(
        recommendations=insufficient,
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        source_manifest=fixture.source_manifest,
        data_quality_report=fixture.quality_report,
        eligibility_snapshot=fixture.reconciliation.eligibility_snapshot,
    )

    assert assessments[0].entry_state is EntryAssessmentState.REJECT
    assert assessments[0].blocking_reasons == (
        "CANDIDATE_DATA_QUALITY_INSUFFICIENT",
    )
    assert all(
        item.entry_state is EntryAssessmentState.WAIT_CONFIRMATION
        for item in assessments[1:]
    )
