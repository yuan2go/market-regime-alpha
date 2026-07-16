from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data import ProviderReference, SourceArtifactReference
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionBar,
)
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.research.provider_candidate_runner import (
    ProviderCandidateRunOutcome,
    run_provider_candidate_experiment,
)
from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    ProviderRehearsalMarketArtifact,
    build_provider_rehearsal_market_artifact,
)
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.eligibility_policy import (
    DecisionBuyabilityStatus,
    RawTradingEligibilityObservation,
    r5_provider_rehearsal_trading_eligibility_policy_v2,
    r5_rehearsal_trading_eligibility_policy_v1,
)


TZ = ZoneInfo("Asia/Shanghai")
START = date(2026, 6, 20)
DECISION_DATES = (START + timedelta(days=25), START + timedelta(days=26))
SYMBOLS = ("000001.SZ", "600000.SH")
LIQUIDITY_MEASURE_ID = "TEST_MEDIAN_AMOUNT_20D"
PROVIDER_ID = ProviderId("provider-xuntou-fixture")


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)


def _market_artifact(
    *,
    buyability: DecisionBuyabilityStatus,
) -> ProviderRehearsalMarketArtifact:
    session_dates = tuple(START + timedelta(days=index) for index in range(28))
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("xuntou-test-calendar-source"),
        market="SH",
        calendar_version="xuntou-test-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(day, _at(day, 15))
            for day in session_dates
        ),
    )
    universe = build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId("xuntou-test-universe-source"),
        method_version="xuntou-test-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=tuple(
            HistoricalUniverseMembershipRecord(day, symbol, True)
            for day in DECISION_DATES
            for symbol in SYMBOLS
        ),
    )
    daily_bars = tuple(
        RehearsalDailyBar(
            symbol=symbol,
            session_date=day,
            close=10.0 + day_index / 10 + symbol_index / 20,
            amount=50_000_000.0 + day_index * 10_000 + symbol_index * 1_000,
            available_at=AvailabilityTime(_at(day, 15, 1)),
            finalized=True,
        )
        for day_index, day in enumerate(session_dates)
        for symbol_index, symbol in enumerate(SYMBOLS)
    )
    decision_snapshots = tuple(
        RehearsalDecisionSnapshot(
            symbol=symbol,
            decision_time=DecisionTime(_at(day, 14, 55)),
            reference_price=12.0 + day_index / 10 + symbol_index / 20,
            available_at=AvailabilityTime(_at(day, 14, 55)),
        )
        for day_index, day in enumerate(DECISION_DATES)
        for symbol_index, symbol in enumerate(SYMBOLS)
    )
    next_session_bars = tuple(
        RehearsalNextSessionBar(
            symbol=symbol,
            session_date=day + timedelta(days=1),
            open=12.1 + day_index / 10 + symbol_index / 20,
            high=12.8 + day_index / 10 + symbol_index / 20,
            low=11.8 + day_index / 10 + symbol_index / 20,
            close=12.5 + day_index / 10 + symbol_index / 20,
            available_at=AvailabilityTime(_at(day + timedelta(days=1), 15, 1)),
        )
        for day_index, day in enumerate(DECISION_DATES)
        for symbol_index, symbol in enumerate(SYMBOLS)
    )
    raw_eligibility = tuple(
        RawTradingEligibilityObservation(
            as_of=AsOfTime(_at(day, 14, 55)),
            available_at=AvailabilityTime(_at(day, 14, 55)),
            symbol=symbol,
            is_suspended=False,
            is_st=False,
            prev_close=11.9,
            limit_up_price=13.09,
            limit_down_price=10.71,
            limit_regime="TEST_EXPLICIT_LIMIT_REGIME",
            listing_age_calendar_days=365,
            liquidity_value=50_000_000.0,
            liquidity_measure_id=LIQUIDITY_MEASURE_ID,
            decision_buyability=buyability,
        )
        for day in DECISION_DATES
        for symbol in SYMBOLS
    )
    return build_provider_rehearsal_market_artifact(
        provider_references=(
            ProviderReference(PROVIDER_ID, "ThinkTrader / XtQuant normalized export", "v3"),
        ),
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=ArtifactId("xuntou-test-source-artifact"),
                provider_id=PROVIDER_ID,
                retrieved_at=RetrievedAt(_at(session_dates[-1], 18)),
                content_hash="sha256:test-xuntou-provider-bundle",
                locator="fixture://xuntou-provider-bundle.json",
            ),
        ),
        retrieval_convention="TEST_EXPLICIT_RETRIEVAL",
        market_availability_convention="TEST_EXPLICIT_AVAILABILITY",
        raw_eligibility_evidence_convention="TEST_EXPLICIT_RAW_ELIGIBILITY",
        bar_finality_convention="TEST_EXPLICIT_BAR_FINALITY",
        price_adjustment_basis="UNADJUSTED_RAW_TRADABLE_PRICE",
        trading_calendar=calendar,
        universe_artifact=universe,
        daily_bars=daily_bars,
        decision_snapshots=decision_snapshots,
        next_session_bars=next_session_bars,
        raw_eligibility_observations=raw_eligibility,
        pit_correct_for_scope=False,
        limitations=("TEST_HISTORICAL_PIT_UNVERIFIED",),
    )


def _policy():
    return r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=1.0,
        liquidity_measure_id=LIQUIDITY_MEASURE_ID,
    )


def test_provider_candidate_run_evaluates_three_targets() -> None:
    artifact = _market_artifact(buyability=DecisionBuyabilityStatus.BUYABLE)
    materialized_at = AsOfTime(_at(DECISION_DATES[-1] + timedelta(days=1), 16))

    run = run_provider_candidate_experiment(
        market_artifact=artifact,
        eligibility_policy=_policy(),
        materialized_at=materialized_at,
        code_revision="abc123",
        config_hash="sha256:config",
        decision_count=2,
    )

    assert run.outcome is ProviderCandidateRunOutcome.EVALUATED
    assert run.data_eligibility.value == "REHEARSAL"
    assert run.market_artifact_id == artifact.artifact_id
    assert run.source_dataset_id == artifact.dataset_contract.dataset_id
    assert len(run.target_runs) == 3
    assert all(target.panel.slice_count == 2 for target in run.target_runs)
    assert all(len(target.b0_evaluations) == 4 for target in run.target_runs)
    assert all(len(target.b1_evaluations) == 5 for target in run.target_runs)
    assert all(item.eligible_count == 2 for item in run.decision_diagnostics)


def test_unknown_buyability_preserves_truthful_empty_population() -> None:
    artifact = _market_artifact(buyability=DecisionBuyabilityStatus.UNKNOWN)

    run = run_provider_candidate_experiment(
        market_artifact=artifact,
        eligibility_policy=_policy(),
        materialized_at=AsOfTime(_at(DECISION_DATES[-1] + timedelta(days=1), 16)),
        code_revision="abc123",
        config_hash="sha256:config",
        decision_count=2,
    )

    assert run.outcome is ProviderCandidateRunOutcome.NO_CANDIDATES_AFTER_ELIGIBILITY
    assert run.target_runs == ()
    assert all(item.eligible_count == 0 for item in run.decision_diagnostics)
    assert all(item.unknown_count == 2 for item in run.decision_diagnostics)
    assert "NO_CANDIDATES_AFTER_ELIGIBILITY" in run.limitations


def test_provider_candidate_runner_rejects_weaker_v1_policy() -> None:
    with pytest.raises(ValueError, match="provider-rehearsal eligibility policy v2"):
        run_provider_candidate_experiment(
            market_artifact=_market_artifact(
                buyability=DecisionBuyabilityStatus.BUYABLE
            ),
            eligibility_policy=r5_rehearsal_trading_eligibility_policy_v1(),
            materialized_at=AsOfTime(
                _at(DECISION_DATES[-1] + timedelta(days=1), 16)
            ),
            code_revision="abc123",
            config_hash="sha256:config",
            decision_count=2,
        )
