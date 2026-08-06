from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    MarketStateConfiguration,
    MissingDataPolicy,
    TransitionThresholds,
)
from market_regime_alpha.research.state_system.market import (
    MarketRegimeObservation,
    MarketRegimeState,
    StatefulMarketRegime,
    evaluate_market_state,
)


NOW = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)


def config(*, confirmations: int = 2, dwell: int = 300) -> MarketStateConfiguration:
    return MarketStateConfiguration.create(
        model_id=ModelId("stateful-market-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("market-state-config-v1"),
        configuration_version="1.0.0",
        thresholds=TransitionThresholds(
            enter_threshold=Decimal("0.65"),
            exit_threshold=Decimal("0.45"),
            hysteresis=Decimal("0.20"),
            confirmation_count=confirmations,
            minimum_dwell_seconds=dwell,
            minimum_coverage=Decimal("0.70"),
            missing_data_policy=MissingDataPolicy.FAIL_CLOSED,
        ),
    )


def lineage(
    at: datetime = NOW,
    *,
    suffix: str = "1",
    configuration: MarketStateConfiguration | None = None,
) -> StateLineage:
    selected = config() if configuration is None else configuration
    return StateLineage(
        continuous_operation_id=ArtifactId("operation-1"),
        runtime_tick_id=ArtifactId(f"tick-{suffix}"),
        provider_attempt_ids=(ArtifactId(f"provider-attempt-{suffix}"),),
        evidence_ids=(ArtifactId(f"evidence-{suffix}"),),
        dataset_id=DatasetId(f"dataset-{suffix}"),
        feature_id=ArtifactId(f"feature-{suffix}"),
        source_artifact_ids=(ArtifactId(f"v0-market-{suffix}"),),
        model_id=ModelId("stateful-market-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("market-state-config-v1"),
        configuration_hash=selected.configuration_hash,
        as_of_time=at,
        available_at=at,
        created_at=at,
    )


def observation(
    score: str,
    *,
    at: datetime = NOW,
    coverage: str = "0.90",
    counter: tuple[str, ...] = (),
    suffix: str = "1",
    configuration: MarketStateConfiguration | None = None,
) -> MarketRegimeObservation:
    return MarketRegimeObservation.create(
        v0_snapshot_id=ArtifactId(f"v0-market-{suffix}"),
        regime_score=Decimal(score),
        data_coverage=Decimal(coverage),
        missing_evidence=() if Decimal(coverage) >= Decimal("0.70") else ("BREADTH",),
        counter_evidence=counter,
        reason_codes=("V0_OBSERVATION_ADAPTED",),
        lineage=lineage(at, suffix=suffix, configuration=configuration),
    )


def advance(
    previous: StatefulMarketRegime,
    score: str,
    *,
    seconds: int,
    suffix: str,
    counter: tuple[str, ...] = (),
) -> StatefulMarketRegime:
    result = evaluate_market_state(
        observation(
            score,
            at=NOW + timedelta(seconds=seconds),
            suffix=suffix,
            counter=counter,
        ),
        previous=previous,
        configuration=config(),
    )
    return result.state


def test_initial_state_is_deterministic_and_has_no_trading_authority() -> None:
    first = evaluate_market_state(observation("0.10"), previous=None, configuration=config())
    replay = evaluate_market_state(observation("0.10"), previous=None, configuration=config())

    assert first.state.effective_state is MarketRegimeState.NEUTRAL
    assert first.state.state_id == replay.state.state_id
    assert first.transition.transition_id == replay.transition.transition_id
    assert first.state.entry_authority_granted is False
    assert first.state.broker_authority_granted is False


def test_single_risk_on_pulse_does_not_replace_effective_state() -> None:
    neutral = evaluate_market_state(
        observation("0.10"), previous=None, configuration=config()
    ).state

    pulse = advance(neutral, "0.80", seconds=600, suffix="2")

    assert pulse.proposed_state is MarketRegimeState.RISK_ON
    assert pulse.effective_state is MarketRegimeState.NEUTRAL
    assert pulse.confirmation_count == 1


def test_continuous_confirmation_after_minimum_dwell_transitions() -> None:
    neutral = evaluate_market_state(
        observation("0.10"), previous=None, configuration=config()
    ).state
    first = advance(neutral, "0.80", seconds=200, suffix="2")
    second = advance(first, "0.82", seconds=400, suffix="3")

    assert first.effective_state is MarketRegimeState.NEUTRAL
    assert second.effective_state is MarketRegimeState.RISK_ON
    assert second.state_entered_at == NOW + timedelta(seconds=400)
    assert second.transitioned is True


def test_minimum_dwell_blocks_even_when_confirmation_is_met() -> None:
    neutral = evaluate_market_state(
        observation("0.10"), previous=None, configuration=config()
    ).state
    first = advance(neutral, "0.80", seconds=100, suffix="2")
    second = advance(first, "0.82", seconds=200, suffix="3")

    assert second.confirmation_count == 2
    assert second.effective_state is MarketRegimeState.NEUTRAL
    assert "MINIMUM_DWELL_NOT_MET" in second.reason_codes


def test_exit_threshold_and_hysteresis_retain_risk_on_until_exit_crosses() -> None:
    selected = config(confirmations=1, dwell=0)
    neutral = evaluate_market_state(
        observation("0.10", configuration=selected), previous=None, configuration=selected
    ).state
    risk_on = evaluate_market_state(
        observation("0.80", at=NOW + timedelta(seconds=1), suffix="2", configuration=selected),
        previous=neutral,
        configuration=selected,
    ).state

    retained = evaluate_market_state(
        observation("0.50", at=NOW + timedelta(seconds=2), suffix="3", configuration=selected),
        previous=risk_on,
        configuration=selected,
    ).state
    exited = evaluate_market_state(
        observation("0.40", at=NOW + timedelta(seconds=3), suffix="4", configuration=selected),
        previous=retained,
        configuration=selected,
    ).state

    assert retained.effective_state is MarketRegimeState.RISK_ON
    assert exited.effective_state is MarketRegimeState.NEUTRAL


def test_counter_evidence_prevents_advancing_state() -> None:
    selected = config(confirmations=1, dwell=0)
    neutral = evaluate_market_state(
        observation("0.10", configuration=selected), previous=None, configuration=selected
    ).state

    result = evaluate_market_state(
        observation(
            "0.90",
            at=NOW + timedelta(seconds=1),
            suffix="2",
            counter=("BREADTH_DIVERGENCE",),
            configuration=selected,
        ),
        previous=neutral,
        configuration=selected,
    )

    assert result.state.effective_state is MarketRegimeState.NEUTRAL
    assert "COUNTER_EVIDENCE_BLOCKED_ADVANCE" in result.state.reason_codes


def test_insufficient_coverage_fails_closed_and_late_evidence_is_new_version() -> None:
    selected = config(confirmations=1, dwell=0)
    insufficient = evaluate_market_state(
        observation("0.80", coverage="0.50"),
        previous=None,
        configuration=config(),
    ).state
    corrected = evaluate_market_state(
        observation(
            "0.80",
            at=NOW + timedelta(seconds=60),
            suffix="2",
            configuration=selected,
        ),
        previous=insufficient,
        configuration=selected,
    ).state

    assert insufficient.effective_state is MarketRegimeState.DATA_INSUFFICIENT
    assert corrected.state_id != insufficient.state_id
    assert corrected.previous_state_id == insufficient.state_id


def test_observation_rejects_lineage_configuration_mismatch() -> None:
    with pytest.raises(ValueError, match="configuration"):
        evaluate_market_state(
            observation("0.10"),
            previous=None,
            configuration=replace(
                config(),
                configuration_hash="sha256:" + "f" * 64,
            ),
        )
