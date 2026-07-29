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


SMOKE_SYMBOLS = smoke_pool_policy_v1().symbols
