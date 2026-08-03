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
from market_regime_alpha.forecasting import PathForecast
from market_regime_alpha.signals import SignalSnapshot

from tests.position.test_assessments import _config, _position
from tests.position.test_thesis_health_builder import _bundle, _rebind
from tests.portfolio.risk_route_test_support import make_position
from tests.position.thesis_health_fixtures import (
    ASSESSED_AT,
    health_rule_set,
    make_h5_fixture,
)


def _authoritative_scope():
    position = make_position()
    fixture = make_h5_fixture()
    opportunity = replace(
        fixture.opportunity,
        opportunity_id=position.opportunity_id,
    )
    thesis = replace(
        fixture.thesis,
        thesis_id=position.thesis_id,
        opportunity_id=position.opportunity_id,
    )
    return (
        replace(
            fixture,
            opportunity=opportunity,
            thesis=thesis,
            rule_set=health_rule_set(thesis),
        ),
        position,
    )


def test_v2_adapter_consumes_derived_health_without_legacy_boolean_evaluation(
    monkeypatch,
) -> None:
    fixture, position = _authoritative_scope()
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
        position=position,
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
    fixture, position = _authoritative_scope()
    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, assessed_at=ASSESSED_AT + timedelta(minutes=2))
    )
    assert observation.effective_health_state is None

    result = OperationalPositionAssessmentServiceV2().assess(
        thesis=fixture.thesis,
        position=position,
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

    with pytest.raises(ValueError, match="stale or future"):
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


def test_v2_adapter_requires_t_plus_one_position_authority_and_exact_trace() -> None:
    fixture = make_h5_fixture()
    observation = ThesisHealthObservationBuilder().build(_bundle(fixture))
    service = OperationalPositionAssessmentServiceV2()

    with pytest.raises(ValueError, match=r"T\+1 authoritative"):
        service.assess(
            thesis=fixture.thesis,
            position=_position(),
            health_observation=observation,
            configuration=_config(),
            assessed_at=ASSESSED_AT,
            actor="reviewer-a",
            reason="legacy position authority rejected",
        )

    with pytest.raises(ValueError, match="Position trace mismatch"):
        service.assess(
            thesis=fixture.thesis,
            position=make_position(),
            health_observation=observation,
            configuration=_config(),
            assessed_at=ASSESSED_AT,
            actor="reviewer-a",
            reason="cross-Thesis position rejected",
        )


def test_v2_adapter_consumes_weakening_and_invalidated_effective_states() -> None:
    fixture, position = _authoritative_scope()
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        payload_changes={"volume_confirmation_state": "UNCONFIRMED"},
    )
    path = _rebind(
        fixture.path,
        PathForecast.from_canonical_dict,
        inputs=((signal.envelope.artifact_id, signal.envelope.content_hash),),
    )
    weakening = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal, path_forecast=path)
    )
    weakened = OperationalPositionAssessmentServiceV2().assess(
        thesis=fixture.thesis,
        position=position,
        health_observation=weakening,
        configuration=_config(),
        assessed_at=weakening.assessed_at,
        actor="reviewer-a",
        reason="derived weakening assessment",
    )
    assert weakened.holding_assessment.thesis_health is ThesisHealth.WEAKENING
    assert weakened.exit_assessment.thesis_health is ThesisHealth.WEAKENING

    invalidated = ThesisHealthObservationBuilder().build(
        _bundle(fixture, assessed_at=fixture.thesis.time_invalidation)
    )
    exited = OperationalPositionAssessmentServiceV2().assess(
        thesis=fixture.thesis,
        position=position,
        health_observation=invalidated,
        configuration=_config(),
        assessed_at=invalidated.assessed_at,
        actor="reviewer-a",
        reason="derived invalidation assessment",
    )
    assert exited.holding_assessment.thesis_health is ThesisHealth.INVALIDATED
    assert exited.exit_assessment.action is PositionLifecycleAction.EXIT


def test_v2_adapter_uses_preserved_effective_state_during_current_insufficiency() -> None:
    fixture, position = _authoritative_scope()
    signal = _rebind(
        fixture.signal,
        SignalSnapshot.from_canonical_dict,
        payload_changes={"volume_confirmation_state": "UNCONFIRMED"},
    )
    path = _rebind(
        fixture.path,
        PathForecast.from_canonical_dict,
        inputs=((signal.envelope.artifact_id, signal.envelope.content_hash),),
    )
    prior = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal, path_forecast=path)
    )
    current = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            prior_observation=prior,
            assessed_at=prior.assessed_at + timedelta(minutes=2),
        )
    )
    assert current.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert current.effective_health_state is ThesisHealth.WEAKENING

    result = OperationalPositionAssessmentServiceV2().assess(
        thesis=fixture.thesis,
        position=position,
        health_observation=current,
        configuration=_config(),
        assessed_at=current.assessed_at,
        actor="reviewer-a",
        reason="preserved effective health assessment",
    )
    assert result.holding_assessment.thesis_health is ThesisHealth.WEAKENING
    assert result.exit_assessment.thesis_health is ThesisHealth.WEAKENING
