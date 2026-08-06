from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    MissingDataPolicy,
    ThemeRotationConfiguration,
    TransitionThresholds,
)
from market_regime_alpha.research.state_system.theme_rotation import (
    StatefulThemeRotation,
    ThemeRotationObservation,
    ThemeRotationState,
    evaluate_theme_rotation,
)


NOW = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)


def config(*, confirmations: int = 2, dwell: int = 120) -> ThemeRotationConfiguration:
    return ThemeRotationConfiguration.create(
        model_id=ModelId("theme-rotation-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("theme-rotation-config-v1"),
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
    etf_strength: str = "0.70",
    breadth: str = "0.70",
    participation: str = "0.70",
    leader: str = "0.70",
    concentration: str = "0.50",
    mapping_complete: bool = True,
    coverage: str = "0.90",
    seconds: int = 0,
    suffix: str = "1",
    theme_id: str = "AI_COMPUTE",
    proxy_etfs: tuple[str, ...] = ("510300.SH", "512760.SH"),
    selected: ThemeRotationConfiguration | None = None,
) -> ThemeRotationObservation:
    chosen = config() if selected is None else selected
    at = NOW + timedelta(seconds=seconds)
    return ThemeRotationObservation.create(
        theme_id=theme_id,
        theme_mapping_id=ArtifactId("theme-map-20260806"),
        theme_mapping_version="2026-08-06",
        mapping_complete=mapping_complete,
        proxy_etf_ids=proxy_etfs,
        etf_rotation_state_ids=(ArtifactId(f"etf-state-{suffix}"),),
        verified_etf_strength=Decimal(etf_strength),
        stock_breadth=Decimal(breadth),
        participation_rate=Decimal(participation),
        leader_resonance=Decimal(leader),
        internal_concentration=Decimal(concentration),
        amount_persistence=Decimal("0.75"),
        data_coverage=Decimal(coverage),
        missing_evidence=() if mapping_complete else ("THEME_MAPPING",),
        counter_evidence=(),
        reason_codes=("THEME_OBSERVABLES_READY",),
        lineage=StateLineage(
            continuous_operation_id=ArtifactId("operation-1"),
            runtime_tick_id=ArtifactId(f"tick-{suffix}"),
            provider_attempt_ids=(ArtifactId(f"provider-attempt-{suffix}"),),
            evidence_ids=(ArtifactId(f"evidence-{suffix}"),),
            dataset_id=DatasetId(f"dataset-{suffix}"),
            feature_id=ArtifactId(f"feature-{suffix}"),
            source_artifact_ids=(ArtifactId(f"theme-observable-{suffix}"),),
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
    obs: ThemeRotationObservation,
    previous: StatefulThemeRotation | None = None,
    selected: ThemeRotationConfiguration | None = None,
) -> StatefulThemeRotation:
    return evaluate_theme_rotation(
        obs,
        previous=previous,
        configuration=config() if selected is None else selected,
    ).state


def test_many_to_many_mapping_is_explicit_and_not_guessed() -> None:
    ai = observation(proxy_etfs=("510300.SH", "512760.SH"))
    chips = observation(theme_id="CHIPS", proxy_etfs=("512760.SH",), suffix="2")

    assert "512760.SH" in ai.proxy_etf_ids
    assert "512760.SH" in chips.proxy_etf_ids
    assert ai.theme_mapping_version == chips.theme_mapping_version


def test_etf_strength_without_stock_breadth_or_participation_cannot_lead() -> None:
    state = evaluate(observation(etf_strength="0.95", breadth="0.20", participation="0.20"))

    assert state.effective_state in {ThemeRotationState.STARTING, ThemeRotationState.DIVERGING}
    assert state.effective_state is not ThemeRotationState.LEADING
    assert "ETF_STOCK_EVIDENCE_CONFLICT" in state.reason_codes


def test_leader_without_participation_is_counter_evidence() -> None:
    state = evaluate(observation(leader="0.95", participation="0.15"))

    assert "LEADER_PARTICIPATION_CONFLICT" in state.counter_evidence
    assert state.effective_state is not ThemeRotationState.LEADING


def test_incomplete_mapping_and_low_coverage_fail_closed() -> None:
    incomplete = evaluate(observation(mapping_complete=False))
    low_coverage = evaluate(observation(coverage="0.40"))

    assert incomplete.effective_state is ThemeRotationState.DATA_INSUFFICIENT
    assert "THEME_MAPPING_INCOMPLETE" in incomplete.reason_codes
    assert low_coverage.effective_state is ThemeRotationState.DATA_INSUFFICIENT


def test_theme_transition_has_confirmation_hysteresis_and_replay() -> None:
    selected = config(confirmations=2, dwell=120)
    starting = evaluate(observation(selected=selected), selected=selected)
    first = evaluate(
        observation(
            etf_strength="0.90",
            breadth="0.90",
            participation="0.90",
            leader="0.90",
            seconds=130,
            suffix="2",
            selected=selected,
        ),
        starting,
        selected,
    )
    second_obs = observation(
        etf_strength="0.90",
        breadth="0.90",
        participation="0.90",
        leader="0.90",
        seconds=140,
        suffix="3",
        selected=selected,
    )
    second = evaluate(second_obs, first, selected)
    replay = evaluate(second_obs, first, selected)

    assert first.effective_state is starting.effective_state
    assert second.effective_state is ThemeRotationState.STRENGTHENING
    assert second.state_id == replay.state_id
