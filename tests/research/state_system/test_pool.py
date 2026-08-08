from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ModelId
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import DynamicPoolConfiguration
from market_regime_alpha.research.state_system.pool import (
    DynamicPoolEvaluationStatus,
    DynamicPoolStateContext,
    PoolEligibilityObservation,
    evaluate_dynamic_pool,
)


NOW = datetime(2026, 8, 6, 6, 30, tzinfo=timezone.utc)


def config(*, material: str = "0.20") -> DynamicPoolConfiguration:
    return DynamicPoolConfiguration.create(
        configuration_id=ArtifactId("dynamic-pool-config-v1"),
        configuration_version="1.0.0",
        allowed_etf_states=("LEADING", "STRENGTHENING"),
        allowed_theme_states=("LEADING", "STRENGTHENING"),
        minimum_state_dwell_seconds=120,
        minimum_evidence_coverage=Decimal("0.70"),
        material_change_threshold=Decimal(material),
    )


def lineage(
    *,
    seconds: int = 0,
    suffix: str = "1",
    selected: DynamicPoolConfiguration | None = None,
) -> StateLineage:
    at = NOW + timedelta(seconds=seconds)
    chosen = config() if selected is None else selected
    return StateLineage(
        continuous_operation_id=ArtifactId("operation-1"),
        runtime_tick_id=ArtifactId(f"tick-{suffix}"),
        provider_attempt_ids=(ArtifactId(f"provider-attempt-{suffix}"),),
        evidence_ids=(ArtifactId(f"evidence-{suffix}"),),
        dataset_id=DatasetId(f"dataset-{suffix}"),
        feature_id=ArtifactId(f"feature-{suffix}"),
        source_artifact_ids=(ArtifactId(f"eligibility-{suffix}"),),
        model_id=ModelId("dynamic-pool-policy"),
        model_version="1.0.0",
        configuration_id=chosen.configuration_id,
        configuration_hash=chosen.configuration_hash,
        as_of_time=at,
        available_at=at,
        created_at=at,
    )


def context(
    *,
    seconds: int = 0,
    suffix: str = "1",
    etf_state: str = "STRENGTHENING",
    theme_state: str = "STRENGTHENING",
    available_offset: int = 0,
) -> DynamicPoolStateContext:
    at = NOW + timedelta(seconds=seconds + available_offset)
    return DynamicPoolStateContext(
        market_regime_state_id=ArtifactId(f"market-state-{suffix}"),
        market_regime_state="NEUTRAL",
        etf_rotation_states=((ArtifactId(f"etf-state-{suffix}"), etf_state, 300),),
        theme_rotation_states=((ArtifactId(f"theme-state-{suffix}"), theme_state, 300),),
        capital_state_id=ArtifactId(f"capital-state-{suffix}"),
        capital_state="EXPANSION_BIAS",
        data_coverage=Decimal("0.90"),
        available_at=at,
    )


def member(symbol: str, *, eligible: bool = True, coverage: str = "0.90") -> PoolEligibilityObservation:
    return PoolEligibilityObservation(
        symbol=symbol,
        eligible=eligible,
        eligibility_reason="ELIGIBLE" if eligible else "SUSPENDED",
        liquidity=Decimal("0.90"),
        board="MAIN",
        is_st=False,
        suspended=not eligible,
        listing_age_days=1000,
        theme_overlap=("AI_COMPUTE",),
        data_coverage=Decimal(coverage),
        missing_evidence=(),
    )


def test_initial_pool_preserves_full_included_and_excluded_cross_section() -> None:
    result = evaluate_dynamic_pool(
        state_context=context(),
        eligibility=(member("600000.SH"), member("600001.SH", eligible=False)),
        previous=None,
        configuration=config(),
        lineage=lineage(),
    )

    assert result.status is DynamicPoolEvaluationStatus.CREATED
    assert result.pool is not None
    assert result.pool.included_symbols == ("600000.SH",)
    assert result.pool.excluded_symbols == ("600001.SH",)
    assert len(result.pool.members) == 2


def test_add_remove_and_eligibility_change_create_immutable_new_version() -> None:
    first = evaluate_dynamic_pool(
        state_context=context(), eligibility=(member("600000.SH"), member("600001.SH")),
        previous=None, configuration=config(), lineage=lineage(),
    ).pool
    assert first is not None
    second = evaluate_dynamic_pool(
        state_context=context(seconds=60, suffix="2"),
        eligibility=(member("600000.SH", eligible=False), member("600001.SH"), member("600002.SH")),
        previous=first,
        configuration=config(),
        lineage=lineage(seconds=60, suffix="2"),
    ).pool
    assert second is not None

    assert second.previous_pool_id == first.pool_id
    assert second.added_symbols == ("600002.SH",)
    assert second.removed_symbols == ("600000.SH",)
    assert first.included_symbols == ("600000.SH", "600001.SH")


def test_identical_or_immaterial_input_reuses_previous_identity() -> None:
    selected = config(material="0.40")
    first = evaluate_dynamic_pool(
        state_context=context(), eligibility=tuple(member(f"60000{i}.SH") for i in range(5)),
        previous=None, configuration=selected, lineage=lineage(selected=selected),
    ).pool
    assert first is not None
    result = evaluate_dynamic_pool(
        state_context=context(seconds=60, suffix="2"),
        eligibility=tuple(member(f"60000{i}.SH", eligible=i != 4) for i in range(5)),
        previous=first,
        configuration=selected,
        lineage=lineage(seconds=60, suffix="2", selected=selected),
    )

    assert result.status is DynamicPoolEvaluationStatus.NO_MATERIAL_POOL_CHANGE
    assert result.pool is first


def test_rotation_state_change_is_material_but_gate_and_dwell_apply() -> None:
    first = evaluate_dynamic_pool(
        state_context=context(), eligibility=(member("600000.SH"),), previous=None,
        configuration=config(), lineage=lineage(),
    ).pool
    assert first is not None
    changed = evaluate_dynamic_pool(
        state_context=context(seconds=60, suffix="2", etf_state="LEADING"),
        eligibility=(member("600000.SH"),), previous=first,
        configuration=config(), lineage=lineage(seconds=60, suffix="2"),
    )
    closed = evaluate_dynamic_pool(
        state_context=replace(
            context(seconds=120, suffix="3"),
            etf_rotation_states=((ArtifactId("etf-state-3"), "LEADING", 30),),
        ),
        eligibility=(member("600000.SH"),), previous=changed.pool,
        configuration=config(), lineage=lineage(seconds=120, suffix="3"),
    )

    assert changed.status is DynamicPoolEvaluationStatus.CREATED
    assert changed.pool is not None
    assert closed.pool is not None
    assert closed.pool.included_symbols == ()
    assert "ROTATION_MINIMUM_DWELL_NOT_MET" in closed.pool.reason_codes


def test_future_state_is_rejected_and_replay_is_identical() -> None:
    with pytest.raises(ValueError, match="future State"):
        evaluate_dynamic_pool(
            state_context=context(available_offset=1), eligibility=(member("600000.SH"),),
            previous=None, configuration=config(), lineage=lineage(),
        )
    kwargs = {
        "state_context": context(),
        "eligibility": (member("600000.SH"),),
        "previous": None,
        "configuration": config(),
        "lineage": lineage(),
    }
    assert evaluate_dynamic_pool(**kwargs).pool_id == evaluate_dynamic_pool(**kwargs).pool_id
