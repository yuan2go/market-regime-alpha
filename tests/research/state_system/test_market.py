from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.authority import (
    StateAuthorityDomain,
    StateSeries,
    engineering_state_transition_policy,
)
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


def test_missing_data_after_effective_state_fails_closed_immediately() -> None:
    neutral = evaluate_market_state(
        observation("0.10"), previous=None, configuration=config()
    ).state

    insufficient = evaluate_market_state(
        observation(
            "0.10",
            at=NOW + timedelta(seconds=1),
            coverage="0.20",
            suffix="2",
        ),
        previous=neutral,
        configuration=config(),
    ).state

    assert insufficient.effective_state is MarketRegimeState.DATA_INSUFFICIENT
    assert insufficient.transitioned is True


def test_market_state_path_reaches_defensive_risk_off_risk_on_and_overheated() -> None:
    selected = config(confirmations=1, dwell=0)
    neutral = evaluate_market_state(
        observation("0.10", configuration=selected),
        previous=None,
        configuration=selected,
    ).state
    defensive = evaluate_market_state(
        observation("-0.80", at=NOW + timedelta(seconds=1), suffix="2", configuration=selected),
        previous=neutral,
        configuration=selected,
    ).state
    risk_off = evaluate_market_state(
        observation("-0.80", at=NOW + timedelta(seconds=2), suffix="3", configuration=selected),
        previous=defensive,
        configuration=selected,
    ).state
    defensive_again = evaluate_market_state(
        observation("0.10", at=NOW + timedelta(seconds=3), suffix="4", configuration=selected),
        previous=risk_off,
        configuration=selected,
    ).state
    neutral_again = evaluate_market_state(
        observation("0.10", at=NOW + timedelta(seconds=4), suffix="5", configuration=selected),
        previous=defensive_again,
        configuration=selected,
    ).state
    risk_on = evaluate_market_state(
        observation("0.80", at=NOW + timedelta(seconds=5), suffix="6", configuration=selected),
        previous=neutral_again,
        configuration=selected,
    ).state
    overheated = evaluate_market_state(
        observation("0.95", at=NOW + timedelta(seconds=6), suffix="7", configuration=selected),
        previous=risk_on,
        configuration=selected,
    ).state

    assert defensive.effective_state is MarketRegimeState.DEFENSIVE
    assert risk_off.effective_state is MarketRegimeState.RISK_OFF
    assert risk_on.effective_state is MarketRegimeState.RISK_ON
    assert overheated.effective_state is MarketRegimeState.OVERHEATED


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


def test_v2_previous_state_crosses_runs_only_within_the_same_series() -> None:
    policy = engineering_state_transition_policy(StateAuthorityDomain.MARKET_REGIME)
    selected = MarketStateConfiguration.create(
        model_id=ModelId("state-transition-evaluator-market-regime-v1"),
        model_version="v1",
        configuration_id=policy.policy_id,
        configuration_version=policy.policy_version,
        thresholds=policy.thresholds,
    )
    series = StateSeries.create(
        domain=StateAuthorityDomain.MARKET_REGIME,
        logical_scope="A_SHARE_MARKET",
        research_family="FREE_DATA_STATE_RESEARCH_V2",
        authority_mode="SHADOW",
        universe_policy_id=ArtifactId("universe-policy-v1"),
        universe_policy_hash="sha256:" + "a" * 64,
        model_id=ModelId("upstream-market-model-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("upstream-market-configuration-v1"),
        configuration_hash="sha256:" + "b" * 64,
        state_policy_id=policy.policy_id,
        state_policy_version=policy.policy_version,
        state_policy_hash=policy.policy_hash,
    )

    def v2_observation(
        at: datetime,
        run_id: str,
        suffix: str,
        bound_series: StateSeries,
    ) -> MarketRegimeObservation:
        bound_lineage = StateLineage(
            continuous_operation_id=ArtifactId(run_id),
            runtime_tick_id=ArtifactId(f"tick-{suffix}"),
            provider_attempt_ids=(ArtifactId(f"provider-{suffix}"),),
            evidence_ids=(ArtifactId(f"evidence-{suffix}"),),
            dataset_id=DatasetId(f"dataset-{suffix}"),
            feature_id=ArtifactId(f"feature-{suffix}"),
            source_artifact_ids=(ArtifactId(f"source-{suffix}"),),
            model_id=selected.model_id,
            model_version=selected.model_version,
            configuration_id=selected.configuration_id,
            configuration_hash=selected.configuration_hash,
            as_of_time=at,
            available_at=at,
            created_at=at,
            state_series_id=bound_series.series_id,
            state_series_hash=bound_series.series_hash,
            state_policy_id=policy.policy_id,
            state_policy_version=policy.policy_version,
            state_policy_hash=policy.policy_hash,
        )
        return MarketRegimeObservation.create(
            v0_snapshot_id=ArtifactId(f"v0-{suffix}"),
            regime_score=Decimal("0.10"),
            data_coverage=Decimal("0.90"),
            missing_evidence=(),
            counter_evidence=(),
            reason_codes=("V2_CROSS_SESSION_TEST",),
            lineage=bound_lineage,
        )

    d1 = evaluate_market_state(
        v2_observation(NOW, "run-d1", "d1", series),
        previous=None,
        configuration=selected,
        state_policy=policy,
    ).state
    d2 = evaluate_market_state(
        v2_observation(NOW + timedelta(days=1), "run-d2", "d2", series),
        previous=d1,
        configuration=selected,
        state_policy=policy,
    ).state

    assert d2.previous_state_id == d1.state_id
    assert d2.lineage.continuous_operation_id != d1.lineage.continuous_operation_id

    other_series = StateSeries.create(
        domain=StateAuthorityDomain.MARKET_REGIME,
        logical_scope="OTHER_MARKET_SCOPE",
        research_family=series.research_family,
        authority_mode=series.authority_mode,
        universe_policy_id=series.universe_policy_id,
        universe_policy_hash=series.universe_policy_hash,
        model_id=series.model_id,
        model_version=series.model_version,
        configuration_id=series.configuration_id,
        configuration_hash=series.configuration_hash,
        state_policy_id=series.state_policy_id,
        state_policy_version=series.state_policy_version,
        state_policy_hash=series.state_policy_hash,
    )
    with pytest.raises(ValueError, match="another State Series"):
        evaluate_market_state(
            v2_observation(NOW + timedelta(days=2), "run-d3", "d3", other_series),
            previous=d2,
            configuration=selected,
            state_policy=policy,
        )
