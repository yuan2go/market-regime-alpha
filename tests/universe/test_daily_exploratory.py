from __future__ import annotations

from market_regime_alpha.candidates.contracts import build_candidate_population
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.daily_exploratory import (
    DailyEligibilityReason,
    SMOKE_POOL_SYMBOLS,
    reconcile_daily_universe,
    smoke_pool_policy_v1,
)
from tests.application.daily_loop.public_fixture import public_fixture


def test_smoke_policy_reuses_the_fixed_twenty_a_share_symbols() -> None:
    first = smoke_pool_policy_v1()
    second = smoke_pool_policy_v1()

    assert len(first.symbols) == 20
    assert first.symbols == SMOKE_POOL_SYMBOLS
    assert first.instrument_scope == "A_SHARE_STOCK"
    assert first.policy_id == second.policy_id
    assert first.content_hash == second.content_hash
    assert first.data_eligibility is DataEligibility.EXPLORATORY


def test_reconciliation_accounts_for_every_symbol_without_silent_deletion() -> None:
    policy = smoke_pool_policy_v1()
    _, result, manifest = public_fixture(
        policy=policy,
        missing_price_symbol=SMOKE_POOL_SYMBOLS[0],
        suspended_symbol=SMOKE_POOL_SYMBOLS[1],
        include_outsider=True,
    )

    reconciled = reconcile_daily_universe(
        policy=policy,
        source_manifest=manifest,
        provider_result=result,
    )
    decisions = {item.symbol: item for item in reconciled.decisions}

    assert len(decisions) == 21
    assert decisions[SMOKE_POOL_SYMBOLS[0]].status is TradingEligibilityStatus.INELIGIBLE
    assert decisions[SMOKE_POOL_SYMBOLS[0]].reasons == (
        DailyEligibilityReason.PRICE_UNAVAILABLE.value,
    )
    assert decisions[SMOKE_POOL_SYMBOLS[1]].reasons == (
        DailyEligibilityReason.SUSPENDED.value,
    )
    assert decisions["000001.SZ"].member is False
    assert decisions["000001.SZ"].reasons == (
        DailyEligibilityReason.NOT_IN_FIXED_UNIVERSE.value,
    )
    assert len(reconciled.universe_snapshot.records) == 21
    assert len(reconciled.eligibility_snapshot.records) == 21

    population = build_candidate_population(
        reconciled.universe_snapshot,
        reconciled.eligibility_snapshot,
        decision_time=result.decision_time,
    )
    assert len(population.symbols) == 18
    assert SMOKE_POOL_SYMBOLS[0] not in population.symbols
    assert SMOKE_POOL_SYMBOLS[1] not in population.symbols
    assert "000001.SZ" not in population.symbols


def test_daily_eligibility_reason_vocabulary_covers_fail_closed_cases() -> None:
    assert {item.value for item in DailyEligibilityReason} >= {
        "NOT_IN_FIXED_UNIVERSE",
        "SUSPENDED",
        "ST_STATUS_UNKNOWN",
        "INSUFFICIENT_HISTORY",
        "INSUFFICIENT_LIQUIDITY",
        "QUOTE_STALE",
        "PRICE_UNAVAILABLE",
        "MAPPING_UNKNOWN",
    }
