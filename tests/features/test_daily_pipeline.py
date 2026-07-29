from __future__ import annotations

from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.features.daily_pipeline import (
    materialize_public_daily_baseline_features,
)
from market_regime_alpha.features.rehearsal_baselines import (
    LIQUIDITY_20S_ID,
    MOMENTUM_5S_ID,
    PRICE_VS_MA20_ID,
    VOLATILITY_20S_ID,
)
from market_regime_alpha.universe.daily_exploratory import (
    reconcile_daily_universe,
    smoke_pool_policy_v1,
)
from tests.application.daily_loop.public_fixture import public_fixture


def test_public_feature_adapter_reuses_all_frozen_r5_materializations() -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_fixture(policy=policy)
    reconciled = reconcile_daily_universe(
        policy=policy,
        source_manifest=manifest,
        provider_result=result,
    )

    feature_result = materialize_public_daily_baseline_features(
        reconciliation=reconciled,
        provider_result=result,
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
        config_hash="sha256:" + "2" * 64,
    )

    assert tuple(item.feature_id for item in feature_result.definitions) == (
        MOMENTUM_5S_ID,
        VOLATILITY_20S_ID,
        LIQUIDITY_20S_ID,
        PRICE_VS_MA20_ID,
    )
    assert tuple(
        item.definition_id for item in feature_result.materializations
    ) == tuple(item.feature_id for item in feature_result.definitions)
    assert all(
        len(item.observations) == len(SMOKE_SYMBOLS)
        for item in feature_result.materializations
    )
    assert all(
        observation.status is InputAvailabilityStatus.AVAILABLE
        for materialization in feature_result.materializations
        for observation in materialization.observations
    )
    assert feature_result.population.symbols == SMOKE_SYMBOLS


def test_public_daily_history_materializes_r5_features() -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_fixture(
        policy=policy,
        exploratory_daily_history=True,
    )
    reconciled = reconcile_daily_universe(
        policy=policy,
        source_manifest=manifest,
        provider_result=result,
    )

    feature_result = materialize_public_daily_baseline_features(
        reconciliation=reconciled,
        provider_result=result,
        code_revision="wp-d3-public-daily-history",
        config_hash="sha256:" + "3" * 64,
    )

    assert len(feature_result.materializations) == 4
    assert all(
        observation.status is InputAvailabilityStatus.AVAILABLE
        for materialization in feature_result.materializations
        for observation in materialization.observations
    )


def test_daily_history_and_decision_quote_are_temporally_separated() -> None:
    policy = smoke_pool_policy_v1()
    _, result, _ = public_fixture(
        policy=policy,
        exploratory_daily_history=True,
    )

    assert all(
        bar.event_time.date() < result.decision_time.value.date()
        for bar in result.bars
    )
    assert all(
        quote.event_time is not None
        and quote.event_time.date() == result.decision_time.value.date()
        for quote in result.quotes
    )


def test_feature_values_match_frozen_fixture_baseline() -> None:
    policy = smoke_pool_policy_v1()
    _, baseline_result, baseline_manifest = public_fixture(policy=policy)
    _, daily_result, daily_manifest = public_fixture(
        policy=policy,
        exploratory_daily_history=True,
    )
    baseline_reconciliation = reconcile_daily_universe(
        policy=policy,
        source_manifest=baseline_manifest,
        provider_result=baseline_result,
    )
    daily_reconciliation = reconcile_daily_universe(
        policy=policy,
        source_manifest=daily_manifest,
        provider_result=daily_result,
    )

    baseline = materialize_public_daily_baseline_features(
        reconciliation=baseline_reconciliation,
        provider_result=baseline_result,
        code_revision="same-code",
        config_hash="sha256:" + "4" * 64,
    )
    daily = materialize_public_daily_baseline_features(
        reconciliation=daily_reconciliation,
        provider_result=daily_result,
        code_revision="same-code",
        config_hash="sha256:" + "4" * 64,
    )

    assert tuple(
        tuple(
            (item.symbol, item.status, item.value)
            for item in materialization.observations
        )
        for materialization in daily.materializations
    ) == tuple(
        tuple(
            (item.symbol, item.status, item.value)
            for item in materialization.observations
        )
        for materialization in baseline.materializations
    )


SMOKE_SYMBOLS = smoke_pool_policy_v1().symbols
