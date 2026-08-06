from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.research.state_system.capital import (
    CapitalObservation,
    CapitalState,
    StatefulCapitalState,
    evaluate_capital_state,
)
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    CapitalStateConfiguration,
    MissingDataPolicy,
    TransitionThresholds,
)


NOW = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)


def config(*, confirmations: int = 1, dwell: int = 0) -> CapitalStateConfiguration:
    return CapitalStateConfiguration.create(
        model_id=ModelId("capital-proxy-state-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("capital-state-config-v1"),
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
    *,
    price: str,
    volume: str,
    amount: str,
    breadth: str,
    participation: str,
    concentration: str,
    etf: str,
    coverage: str = "0.90",
    counter: tuple[str, ...] = (),
    seconds: int = 0,
    suffix: str = "1",
) -> CapitalObservation:
    selected = config()
    at = NOW + timedelta(seconds=seconds)
    return CapitalObservation.create(
        scope_id="MARKET",
        price_change=Decimal(price),
        volume_change=Decimal(volume),
        amount_change=Decimal(amount),
        breadth_change=Decimal(breadth),
        participation_change=Decimal(participation),
        concentration=Decimal(concentration),
        etf_strength=Decimal(etf),
        data_coverage=Decimal(coverage),
        uncertainty=Decimal("1") - Decimal(coverage),
        missing_evidence=() if Decimal(coverage) >= Decimal("0.70") else ("ETF_FLOW_PROXY",),
        counter_evidence=counter,
        reason_codes=("OBSERVABLE_PROXY_INFERENCE",),
        lineage=StateLineage(
            continuous_operation_id=ArtifactId("operation-1"),
            runtime_tick_id=ArtifactId(f"tick-{suffix}"),
            provider_attempt_ids=(ArtifactId(f"provider-attempt-{suffix}"),),
            evidence_ids=(ArtifactId(f"evidence-{suffix}"),),
            dataset_id=DatasetId(f"dataset-{suffix}"),
            feature_id=ArtifactId(f"feature-{suffix}"),
            source_artifact_ids=(ArtifactId(f"capital-observable-{suffix}"),),
            model_id=selected.model_id,
            model_version=selected.model_version,
            configuration_id=selected.configuration_id,
            configuration_hash=selected.configuration_hash,
            as_of_time=at,
            available_at=at,
            created_at=at,
        ),
    )


def evaluate(
    obs: CapitalObservation,
    previous: StatefulCapitalState | None = None,
) -> StatefulCapitalState:
    return evaluate_capital_state(obs, previous=previous, configuration=config()).state


def test_accumulation_bias_uses_amount_without_claiming_owner() -> None:
    state = evaluate(
        observation(
            price="0.05",
            volume="0.70",
            amount="0.80",
            breadth="0.35",
            participation="0.40",
            concentration="0.75",
            etf="0.45",
        )
    )

    assert state.effective_state is CapitalState.ACCUMULATION_BIAS


def test_expansion_distribution_and_contraction_biases() -> None:
    expansion = evaluate(
        observation(
            price="0.80", volume="0.75", amount="0.80", breadth="0.80",
            participation="0.80", concentration="0.45", etf="0.80",
        )
    )
    distribution = evaluate(
        observation(
            price="0.35", volume="0.70", amount="0.70", breadth="-0.60",
            participation="-0.55", concentration="0.85", etf="-0.20", suffix="2",
        )
    )
    contraction = evaluate(
        observation(
            price="-0.70", volume="-0.60", amount="-0.70", breadth="-0.75",
            participation="-0.70", concentration="0.40", etf="-0.65", suffix="3",
        )
    )

    assert expansion.effective_state is CapitalState.EXPANSION_BIAS
    assert distribution.effective_state is CapitalState.DISTRIBUTION_BIAS
    assert contraction.effective_state is CapitalState.CONTRACTION_BIAS


def test_counter_evidence_retains_previous_effective_state() -> None:
    contraction = evaluate(
        observation(
            price="-0.70", volume="-0.60", amount="-0.70", breadth="-0.75",
            participation="-0.70", concentration="0.40", etf="-0.65",
        )
    )
    blocked = evaluate(
        observation(
            price="0.80", volume="0.80", amount="0.80", breadth="0.80",
            participation="0.80", concentration="0.45", etf="0.80",
            counter=("PRICE_AMOUNT_DIVERGENCE",), seconds=1, suffix="2",
        ),
        contraction,
    )

    assert blocked.effective_state is CapitalState.CONTRACTION_BIAS
    assert "CAPITAL_COUNTER_EVIDENCE_BLOCKED" in blocked.reason_codes


def test_coverage_insufficient_fails_closed_and_replay_is_identical() -> None:
    obs = observation(
        price="0.80", volume="0.80", amount="0.80", breadth="0.80",
        participation="0.80", concentration="0.45", etf="0.80", coverage="0.40",
    )

    first = evaluate(obs)
    replay = evaluate(obs)

    assert first.effective_state is CapitalState.DATA_INSUFFICIENT
    assert first.state_id == replay.state_id


def test_serialized_capital_state_contains_no_hidden_actor_claims() -> None:
    state = evaluate(
        observation(
            price="0.05", volume="0.70", amount="0.80", breadth="0.35",
            participation="0.40", concentration="0.75", etf="0.45",
        )
    )
    serialized = canonical_json(state.identity_payload()).lower()

    assert "institution" not in serialized
    assert "main_force" not in serialized
    assert "state_fund" not in serialized
    assert "owner" not in serialized
