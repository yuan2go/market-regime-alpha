from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from market_regime_alpha.core.identity import ThesisId
import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.application.trading_lifecycle import (
    OperationalPositionAssessmentServiceV2,
)
from market_regime_alpha.position import (
    PositionLifecycleAction,
    ThesisHealth,
    ThesisHealthEvaluator,
    ThesisHealthObservationBuilder,
)

from tests.position.test_assessments import _config, _position
from tests.position.test_thesis_health_builder import _bundle
from tests.position.thesis_health_fixtures import ASSESSED_AT, make_h5_fixture


def test_v2_adapter_consumes_derived_health_without_legacy_boolean_evaluation(
    monkeypatch,
) -> None:
    fixture = make_h5_fixture()
    observation = ThesisHealthObservationBuilder().build(_bundle(fixture))
    monkeypatch.setattr(
        ThesisHealthEvaluator,
        "evaluate",
        lambda *_args, **_kwargs: pytest.fail(
            "V2 must not construct or evaluate a V1 support-boolean Observation"
        ),
    )

    result = OperationalPositionAssessmentServiceV2().assess(
        thesis=fixture.thesis,
        position=_position(),
        health_observation=observation,
        configuration=_config(),
        assessed_at=ASSESSED_AT,
        actor="reviewer-a",
        reason="strict V2 operational assessment",
    )

    assert result.holding_assessment.thesis_health is ThesisHealth.HEALTHY
    assert result.holding_assessment.action is PositionLifecycleAction.WAIT
    assert result.exit_assessment.action is PositionLifecycleAction.WAIT
    assert result.holding_assessment.evidence.artifact_id == observation.observation_id
    assert result.mode == "ASSESSMENT_ONLY"
    assert result.execution_boundary == "NO_TRADE_ACTION_CREATED"
    assert result.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"


def test_v2_adapter_preserves_not_established_effective_health_as_insufficient() -> None:
    fixture = make_h5_fixture()
    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, assessed_at=ASSESSED_AT + timedelta(minutes=2))
    )
    assert observation.effective_health_state is None

    result = OperationalPositionAssessmentServiceV2().assess(
        thesis=fixture.thesis,
        position=_position(),
        health_observation=observation,
        configuration=_config(),
        assessed_at=observation.assessed_at,
        actor="reviewer-a",
        reason="insufficient V2 operational assessment",
    )

    assert result.holding_assessment.action is PositionLifecycleAction.DATA_INSUFFICIENT
    assert result.exit_assessment.action is PositionLifecycleAction.DATA_INSUFFICIENT


def test_v2_adapter_rejects_future_health_or_thesis_scope_mismatch() -> None:
    fixture = make_h5_fixture()
    observation = ThesisHealthObservationBuilder().build(_bundle(fixture))

    with pytest.raises(ValueError, match="future"):
        OperationalPositionAssessmentServiceV2().assess(
            thesis=fixture.thesis,
            position=_position(),
            health_observation=observation,
            configuration=_config(),
            assessed_at=ASSESSED_AT - timedelta(seconds=1),
            actor="reviewer-a",
            reason="future evidence must fail",
        )

    other = replace(
        make_h5_fixture().thesis,
        thesis_id=ThesisId("different-thesis"),
    )
    with pytest.raises(ValueError, match="Thesis scope"):
        OperationalPositionAssessmentServiceV2().assess(
            thesis=other,
            position=_position(),
            health_observation=observation,
            configuration=_config(),
            assessed_at=ASSESSED_AT,
            actor="reviewer-a",
            reason="scope mismatch must fail",
        )


def test_v2_adapter_rejects_assessment_when_market_price_is_not_established() -> None:
    fixture = make_h5_fixture()
    from market_regime_alpha.daily_decision import DecisionPriceSnapshot

    empty_price = DecisionPriceSnapshot(
        source_manifest_id=fixture.price.source_manifest_id,
        decision_time=fixture.price.decision_time,
        observations=(),
        data_eligibility=fixture.price.data_eligibility,
    )
    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, price_snapshot=empty_price)
    )

    with pytest.raises(ValueError, match="requires established market price"):
        OperationalPositionAssessmentServiceV2().assess(
            thesis=fixture.thesis,
            position=_position(),
            health_observation=observation,
            configuration=_config(),
            assessed_at=ASSESSED_AT,
            actor="reviewer-a",
            reason="assessment requires an actual price",
        )
