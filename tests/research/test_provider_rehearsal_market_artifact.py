from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import (
    DataEligibility,
    ProviderReference,
    SourceArtifactReference,
)
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
    RehearsalNextSessionBar,
)
from market_regime_alpha.data.trading_calendar import TradingSession, build_trading_calendar_artifact
from market_regime_alpha.research.provider_rehearsal_market_artifact import (
    build_provider_rehearsal_market_artifact,
)
from market_regime_alpha.universe.artifacts import (
    HistoricalUniverseMembershipRecord,
    build_historical_pit_universe_artifact,
)
from market_regime_alpha.universe.contracts import TradingEligibilityStatus
from market_regime_alpha.universe.eligibility_policy import (
    DecisionBuyabilityStatus,
    RawTradingEligibilityObservation,
    r5_provider_rehearsal_trading_eligibility_policy_v2,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION_AT = datetime(2026, 7, 15, 14, 55, tzinfo=TZ)
NEXT_SESSION_DATE = date(2026, 7, 16)
PROVIDER_ID = ProviderId("provider-fixture")
LIQUIDITY_MEASURE = "AVG_AMOUNT_20D_CNY"


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("dataset-calendar-v1"),
        market="CN_A_SHARE",
        calendar_version="fixture-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=(
            TradingSession(date(2026, 7, 14), datetime(2026, 7, 14, 15, 0, tzinfo=TZ)),
            TradingSession(date(2026, 7, 15), datetime(2026, 7, 15, 15, 0, tzinfo=TZ)),
            TradingSession(date(2026, 7, 16), datetime(2026, 7, 16, 15, 0, tzinfo=TZ)),
        ),
    )


def _universe():
    return build_historical_pit_universe_artifact(
        source_dataset_id=DatasetId("dataset-universe-v1"),
        method_version="fixture-a-share-universe-v1",
        timezone_name="Asia/Shanghai",
        effective_time_convention="AS_OF_DATE_EFFECTIVE_FROM_LOCAL_DAY_START",
        records=(
            HistoricalUniverseMembershipRecord(date(2026, 7, 15), "000001.SZ", True),
        ),
    )


def _source_artifacts():
    return (
        SourceArtifactReference(
            artifact_id=ArtifactId("source-export-bars-v1"),
            provider_id=PROVIDER_ID,
            retrieved_at=RetrievedAt(datetime(2026, 7, 17, 9, 0, tzinfo=TZ)),
            content_hash="sha256:bars",
            locator="fixture://bars.csv",
        ),
        SourceArtifactReference(
            artifact_id=ArtifactId("source-export-eligibility-v1"),
            provider_id=PROVIDER_ID,
            retrieved_at=RetrievedAt(datetime(2026, 7, 17, 9, 5, tzinfo=TZ)),
            content_hash="sha256:eligibility",
            locator="fixture://eligibility.csv",
        ),
    )


def _raw_eligibility(*, include_v2: bool = True):
    return RawTradingEligibilityObservation(
        as_of=AsOfTime(DECISION_AT),
        available_at=AvailabilityTime(DECISION_AT),
        symbol="000001.SZ",
        is_suspended=False,
        is_st=False,
        prev_close=10.0,
        limit_up_price=11.0,
        limit_down_price=9.0,
        limit_regime="MAIN_BOARD_10PCT",
        listing_age_calendar_days=120 if include_v2 else None,
        liquidity_value=80_000_000.0 if include_v2 else None,
        liquidity_measure_id=LIQUIDITY_MEASURE if include_v2 else None,
        decision_buyability=(DecisionBuyabilityStatus.BUYABLE if include_v2 else None),
    )


def _build(*, source_artifacts=None, availability_convention: str = "PROVIDER_DECLARED_AVAILABLE_AT"):
    return build_provider_rehearsal_market_artifact(
        provider_references=(
            ProviderReference(
                provider_id=PROVIDER_ID,
                product="fixture-export",
                contract_version="v1",
            ),
        ),
        source_artifacts=source_artifacts or _source_artifacts(),
        retrieval_convention="SOURCE_EXPORT_RETRIEVED_AFTER_SAMPLE_WINDOW",
        market_availability_convention=availability_convention,
        raw_eligibility_evidence_convention="PROVIDER_EXPLICIT_AVAILABLE_AT",
        bar_finality_convention="DAILY_BAR_FINAL_AFTER_IDENTIFIED_SESSION_CLOSE",
        price_adjustment_basis="RAW_TRADABLE_PRICE_FOR_REHEARSAL_BASELINE",
        trading_calendar=_calendar(),
        universe_artifact=_universe(),
        daily_bars=(
            RehearsalDailyBar(
                symbol="000001.SZ",
                session_date=date(2026, 7, 14),
                close=9.8,
                amount=100_000_000.0,
                available_at=AvailabilityTime(datetime(2026, 7, 14, 15, 1, tzinfo=TZ)),
                finalized=True,
            ),
        ),
        decision_snapshots=(
            RehearsalDecisionSnapshot(
                symbol="000001.SZ",
                decision_time=DecisionTime(DECISION_AT),
                reference_price=10.2,
                available_at=AvailabilityTime(DECISION_AT),
            ),
        ),
        next_session_bars=(
            RehearsalNextSessionBar(
                symbol="000001.SZ",
                session_date=NEXT_SESSION_DATE,
                open=10.3,
                high=10.8,
                low=10.0,
                close=10.6,
                available_at=AvailabilityTime(datetime(2026, 7, 16, 15, 1, tzinfo=TZ)),
            ),
        ),
        raw_eligibility_observations=(_raw_eligibility(),),
        pit_correct_for_scope=False,
        limitations=("fixture only",),
    )


def test_provider_rehearsal_artifact_is_deterministic_and_rehearsal_only() -> None:
    first = _build()
    second = _build(source_artifacts=tuple(reversed(_source_artifacts())))

    assert first.artifact_id == second.artifact_id
    assert first.dataset_contract.dataset_id == second.dataset_contract.dataset_id
    assert first.dataset_contract.eligibility is DataEligibility.REHEARSAL
    assert first.dataset_contract.manifest_artifact_id == first.artifact_id


def test_result_affecting_availability_convention_changes_artifact_identity() -> None:
    baseline = _build()
    changed = _build(availability_convention="DIFFERENT_PROVIDER_AVAILABILITY_CONVENTION")

    assert baseline.artifact_id != changed.artifact_id
    assert baseline.dataset_contract.dataset_id != changed.dataset_contract.dataset_id


def test_provider_rehearsal_artifact_materializes_v2_eligibility() -> None:
    artifact = _build()
    policy = r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=50_000_000.0,
        liquidity_measure_id=LIQUIDITY_MEASURE,
    )

    eligibility = artifact.materialize_trading_eligibility(policy=policy)
    snapshot = eligibility.snapshot_for_decision_time(DecisionTime(DECISION_AT))

    assert eligibility.source_dataset_id == artifact.dataset_contract.dataset_id
    assert eligibility.raw_evidence_convention == artifact.raw_eligibility_evidence_convention
    assert snapshot.status_for("000001.SZ") is TradingEligibilityStatus.ELIGIBLE


def test_missing_provider_v2_evidence_remains_unknown() -> None:
    artifact = build_provider_rehearsal_market_artifact(
        provider_references=(ProviderReference(PROVIDER_ID, "fixture-export", "v1"),),
        source_artifacts=_source_artifacts(),
        retrieval_convention="SOURCE_EXPORT_RETRIEVED_AFTER_SAMPLE_WINDOW",
        market_availability_convention="PROVIDER_DECLARED_AVAILABLE_AT",
        raw_eligibility_evidence_convention="PROVIDER_EXPLICIT_AVAILABLE_AT",
        bar_finality_convention="DAILY_BAR_FINAL_AFTER_IDENTIFIED_SESSION_CLOSE",
        price_adjustment_basis="RAW_TRADABLE_PRICE_FOR_REHEARSAL_BASELINE",
        trading_calendar=_calendar(),
        universe_artifact=_universe(),
        daily_bars=(
            RehearsalDailyBar(
                "000001.SZ",
                date(2026, 7, 14),
                9.8,
                100_000_000.0,
                AvailabilityTime(datetime(2026, 7, 14, 15, 1, tzinfo=TZ)),
            ),
        ),
        decision_snapshots=(
            RehearsalDecisionSnapshot(
                "000001.SZ",
                DecisionTime(DECISION_AT),
                10.2,
                AvailabilityTime(DECISION_AT),
            ),
        ),
        next_session_bars=(
            RehearsalNextSessionBar(
                "000001.SZ",
                NEXT_SESSION_DATE,
                10.3,
                10.8,
                10.0,
                10.6,
                AvailabilityTime(datetime(2026, 7, 16, 15, 1, tzinfo=TZ)),
            ),
        ),
        raw_eligibility_observations=(_raw_eligibility(include_v2=False),),
        pit_correct_for_scope=False,
    )
    policy = r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=50_000_000.0,
        liquidity_measure_id=LIQUIDITY_MEASURE,
    )

    eligibility = artifact.materialize_trading_eligibility(policy=policy)
    snapshot = eligibility.snapshot_for_decision_time(DecisionTime(DECISION_AT))

    assert snapshot.status_for("000001.SZ") is TradingEligibilityStatus.UNKNOWN


def test_source_artifact_provider_must_be_declared() -> None:
    undeclared = SourceArtifactReference(
        artifact_id=ArtifactId("source-undeclared-v1"),
        provider_id=ProviderId("other-provider"),
        retrieved_at=RetrievedAt(datetime(2026, 7, 17, 9, 0, tzinfo=TZ)),
        content_hash="sha256:other",
        locator="fixture://other.csv",
    )

    with pytest.raises(ValueError, match="source artifact provider must be declared"):
        _build(source_artifacts=(undeclared,))
