from __future__ import annotations

from datetime import timedelta

import pytest

import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.forecasting import PathForecast
from market_regime_alpha.position import (
    ThesisHealth,
    ThesisHealthObservationBuilder,
    ThesisHealthObservationV2,
)
from market_regime_alpha.signals import SignalSnapshot

from tests.position.test_thesis_health_builder import _bundle, _rebind
from tests.position.thesis_health_fixtures import ASSESSED_AT, make_h5_fixture


def _weakening_observation():
    fixture = make_h5_fixture()
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
    observation = ThesisHealthObservationBuilder().build(
        _bundle(fixture, signal_snapshot=signal, path_forecast=path)
    )
    return fixture, observation


def test_weakening_does_not_recover_when_current_artifacts_observe_healthy() -> None:
    fixture, prior = _weakening_observation()

    current = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            prior_observation=prior,
            assessed_at=ASSESSED_AT + timedelta(minutes=1),
        )
    )
    assert current.observed_health_state is ThesisHealth.HEALTHY
    assert current.prior_observation_id == prior.observation_id
    assert current.prior_observation_hash == prior.content_hash
    assert current.prior_observed_health_state is ThesisHealth.WEAKENING
    assert current.prior_effective_health_state is ThesisHealth.WEAKENING
    assert current.effective_health_state is ThesisHealth.WEAKENING
    assert "THESIS_HEALTH_RECOVERY_NOT_AUTHORIZED" in current.reason_codes


def test_first_data_insufficient_does_not_forge_effective_healthy() -> None:
    fixture = make_h5_fixture()
    current = ThesisHealthObservationBuilder().build(
        _bundle(fixture, assessed_at=ASSESSED_AT + timedelta(minutes=2))
    )

    assert current.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert current.prior_effective_health_state is None
    assert current.effective_health_state is None
    assert "EFFECTIVE_THESIS_HEALTH_NOT_ESTABLISHED" in current.reason_codes


def test_data_insufficient_preserves_prior_effective_state() -> None:
    fixture, prior = _weakening_observation()
    current = ThesisHealthObservationBuilder().build(
        _bundle(
            fixture,
            prior_observation=prior,
            assessed_at=ASSESSED_AT + timedelta(minutes=2),
        )
    )

    assert current.observed_health_state is ThesisHealth.DATA_INSUFFICIENT
    assert current.effective_health_state is ThesisHealth.WEAKENING


def test_prior_must_precede_current_assessment() -> None:
    fixture, prior = _weakening_observation()
    with pytest.raises(ValueError, match="must precede"):
        ThesisHealthObservationBuilder().build(
            _bundle(fixture, prior_observation=prior, assessed_at=ASSESSED_AT)
        )


def test_prior_hash_tamper_is_rejected_by_canonical_reader() -> None:
    _, prior = _weakening_observation()
    payload = prior.to_canonical_dict()
    payload["content_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="identity mismatch"):
        ThesisHealthObservationV2.from_canonical_dict(payload)


def test_invalidated_prior_is_terminal() -> None:
    fixture = make_h5_fixture()
    prior = ThesisHealthObservationBuilder().build(
        _bundle(fixture, assessed_at=fixture.thesis.time_invalidation)
    )
    with pytest.raises(ValueError, match="must precede"):
        ThesisHealthObservationBuilder().build(
            _bundle(
                fixture,
                prior_observation=prior,
                assessed_at=fixture.thesis.time_invalidation - timedelta(seconds=1),
            )
        )
