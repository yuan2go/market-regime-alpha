from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.daily_decision.recommendation import (
    CandidateDataQuality,
    CandidateRecommendation,
    project_candidate_recommendations,
)
from market_regime_alpha.data.daily_quality import DailyDataQualityStatus
from tests.daily_decision.conftest import DailyDecisionFixture


def test_projection_keeps_b0_and_b1_as_separate_top_five_lists(
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    fixture = daily_decision_fixture

    recommendations = project_candidate_recommendations(
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        data_quality_report=fixture.quality_report,
        top_k=5,
    )

    assert len(recommendations) == 10
    for run in fixture.prediction_runs:
        projected = tuple(
            item
            for item in recommendations
            if item.prediction_run_id == run.prediction_run_id
        )
        assert len(projected) == 5
        assert tuple(item.model_id for item in projected) == (run.model_id,) * 5
        assert tuple(item.rank for item in projected) == (1, 2, 3, 4, 5)
        assert tuple(item.symbol for item in projected) == tuple(
            item.symbol for item in run.predictions[:5]
        )
        assert tuple(item.score for item in projected) == tuple(
            item.model_score for item in run.predictions[:5]
        )
        assert all(
            item.target_id == run.target_id
            and item.data_quality is CandidateDataQuality.COMPLETE
            for item in projected
        )
    forbidden = {"BUY", "SELL", "ENTER", "order_size", "position_size"}
    assert all(
        forbidden.isdisjoint(item.to_canonical_dict())
        for item in recommendations
    )
    assert all(
        CandidateRecommendation.from_canonical_dict(item.to_canonical_dict())
        == item
        for item in recommendations
    )
    tampered = recommendations[0].to_canonical_dict()
    tampered["score_components"][0]["probability"] = 0.99
    with pytest.raises(ValueError, match="Score Component fields mismatch"):
        CandidateRecommendation.from_canonical_dict(tampered)


def test_data_blocked_never_publishes_partial_recommendations(
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    fixture = daily_decision_fixture
    blocked = replace(
        fixture.quality_report,
        status=DailyDataQualityStatus.DATA_BLOCKED,
        findings=(
            replace(
                fixture.quality_report.findings[0]
                if fixture.quality_report.findings
                else _blocking_finding(),
                blocking=True,
            ),
        ),
    )

    assert project_candidate_recommendations(
        prediction_runs=fixture.prediction_runs,
        decision_snapshot=fixture.decision_snapshot,
        data_quality_report=blocked,
    ) == ()


def _blocking_finding():
    from market_regime_alpha.data.daily_quality import DataQualityFinding

    return DataQualityFinding(
        symbol=None,
        field_id=None,
        critical_fact=None,
        reason_code="TEST_BLOCK",
        blocking=True,
    )
