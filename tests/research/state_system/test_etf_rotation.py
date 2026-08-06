from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    EtfRotationConfiguration,
    MissingDataPolicy,
    TransitionThresholds,
)
from market_regime_alpha.research.state_system.etf_rotation import (
    EtfRotationObservation,
    EtfRotationState,
    StatefulEtfRotation,
    evaluate_etf_rotation,
)


NOW = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)


def config(*, confirmations: int = 2, dwell: int = 120) -> EtfRotationConfiguration:
    return EtfRotationConfiguration.create(
        model_id=ModelId("etf-rotation-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("etf-rotation-config-v1"),
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


def observation(
    strength: str,
    *,
    seconds: int = 0,
    suffix: str = "1",
    diffusion: str = "0.80",
    amount_persistence: str = "0.80",
    liquidity: str = "0.90",
    coverage: str = "0.90",
    counter: tuple[str, ...] = (),
    selected: EtfRotationConfiguration | None = None,
) -> EtfRotationObservation:
    chosen = config() if selected is None else selected
    at = NOW + timedelta(seconds=seconds)
    metric = Decimal(strength)
    return EtfRotationObservation.create(
        etf_id="510300.SH",
        benchmark_id="000300.SH",
        relative_strength_1d=metric,
        relative_strength_3d=metric,
        relative_strength_5d=metric,
        relative_strength_10d=metric,
        benchmark_excess=metric,
        amount_change=metric,
        amount_persistence=Decimal(amount_persistence),
        volume_change=metric,
        drawdown=max(Decimal("0"), -metric),
        volatility=Decimal("0.20"),
        diffusion=Decimal(diffusion),
        liquidity=Decimal(liquidity),
        data_coverage=Decimal(coverage),
        missing_evidence=() if Decimal(coverage) >= Decimal("0.70") else ("RS_10D",),
        counter_evidence=counter,
        reason_codes=("ETF_OBSERVABLES_READY",),
        lineage=StateLineage(
            continuous_operation_id=ArtifactId("operation-1"),
            runtime_tick_id=ArtifactId(f"tick-{suffix}"),
            provider_attempt_ids=(ArtifactId(f"provider-attempt-{suffix}"),),
            evidence_ids=(ArtifactId(f"evidence-{suffix}"),),
            dataset_id=DatasetId(f"dataset-{suffix}"),
            feature_id=ArtifactId(f"feature-{suffix}"),
            source_artifact_ids=(ArtifactId(f"etf-observable-{suffix}"),),
            model_id=chosen.model_id,
            model_version=chosen.model_version,
            configuration_id=chosen.configuration_id,
            configuration_hash=chosen.configuration_hash,
            as_of_time=at,
            available_at=at,
            created_at=at,
        ),
    )


def evaluate(
    obs: EtfRotationObservation,
    previous: StatefulEtfRotation | None = None,
    selected: EtfRotationConfiguration | None = None,
) -> StatefulEtfRotation:
    return evaluate_etf_rotation(
        obs,
        previous=previous,
        configuration=config() if selected is None else selected,
    ).state


def test_single_etf_pulse_cannot_enter_leading() -> None:
    state = evaluate(observation("0.95"))

    assert state.proposed_state is EtfRotationState.STARTING
    assert state.effective_state is EtfRotationState.STARTING


def test_multi_observation_resonance_and_amount_persistence_reach_leading() -> None:
    selected = config(confirmations=1, dwell=0)
    starting = evaluate(observation("0.35", selected=selected), selected=selected)
    strengthening = evaluate(
        observation("0.60", seconds=1, suffix="2", selected=selected),
        starting,
        selected,
    )
    leading = evaluate(
        observation("0.85", seconds=2, suffix="3", selected=selected),
        strengthening,
        selected,
    )

    assert strengthening.effective_state is EtfRotationState.STRENGTHENING
    assert leading.effective_state is EtfRotationState.LEADING


def test_strength_without_liquidity_fails_closed() -> None:
    state = evaluate(observation("0.90", liquidity="0.30"))

    assert state.effective_state is EtfRotationState.DATA_INSUFFICIENT
    assert "ETF_LIQUIDITY_INSUFFICIENT" in state.reason_codes


def test_leading_can_diverge_weaken_and_fail_with_persisted_path() -> None:
    selected = config(confirmations=1, dwell=0)
    starting = evaluate(observation("0.35", selected=selected), selected=selected)
    strengthening = evaluate(
        observation("0.60", seconds=1, suffix="2", selected=selected), starting, selected
    )
    leading = evaluate(
        observation("0.85", seconds=2, suffix="3", selected=selected), strengthening, selected
    )
    diverging = evaluate(
        observation(
            "0.75",
            seconds=3,
            suffix="4",
            diffusion="0.20",
            counter=("ETF_BREADTH_DIVERGENCE",),
            selected=selected,
        ),
        leading,
        selected,
    )
    weakening = evaluate(
        observation("0.10", seconds=4, suffix="5", selected=selected), diverging, selected
    )
    failed = evaluate(
        observation("-0.70", seconds=5, suffix="6", selected=selected), weakening, selected
    )

    assert diverging.effective_state is EtfRotationState.DIVERGING
    assert weakening.effective_state is EtfRotationState.WEAKENING
    assert failed.effective_state is EtfRotationState.FAILED


def test_missing_data_and_restart_recovery_use_persisted_previous_state() -> None:
    first = evaluate(observation("0.35"))
    insufficient = evaluate(
        observation("0.40", seconds=130, suffix="2", coverage="0.40"), first
    )
    replay = evaluate(
        observation("0.40", seconds=130, suffix="2", coverage="0.40"), first
    )

    assert insufficient.effective_state is EtfRotationState.DATA_INSUFFICIENT
    assert insufficient.state_id == replay.state_id
    assert insufficient.previous_state_id == first.state_id
