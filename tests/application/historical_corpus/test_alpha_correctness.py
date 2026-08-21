from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.historical_corpus.alpha_correctness import (
    AlphaCorrectnessStatus,
    PersistedFeatureObservation,
    PersistedTargetObservation,
    reproduce_intraday_features,
    reproduce_t_plus_one_1030_target,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Timeframe


SHANGHAI = ZoneInfo("Asia/Shanghai")
SESSION = date(2025, 1, 2)
NEXT_SESSION = date(2025, 1, 3)
DECISION_TIME = datetime.combine(SESSION, time(14, 55), SHANGHAI).astimezone(UTC)


def test_independent_intraday_recomputation_matches_persisted_values() -> None:
    bars = (
        _bar(SESSION, time(14, 45), open_price="10", close="10", volume="100"),
        _bar(SESSION, time(14, 50), open_price="10", close="12", volume="100"),
    )
    persisted = tuple(
        PersistedFeatureObservation.create(
            factor_id=factor_id,
            value=value,
            source_bars=bars,
        )
        for factor_id, value in (
            ("intraday_return_to_decision_time", Decimal("0.200000000000")),
            ("price_vs_vwap_return", Decimal("0.090909090909")),
            ("vwap_slope", Decimal("0.100000000000")),
        )
    )

    result = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=bars,
        persisted=persisted,
        physical_source_available=True,
    )

    assert result.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    assert result.discrepancies == ()
    assert {item.factor_id: item.recomputed_value for item in result.comparisons} == {
        "intraday_return_to_decision_time": Decimal("0.200000000000"),
        "price_vs_vwap_return": Decimal("0.090909090909"),
        "vwap_slope": Decimal("0.100000000000"),
    }
    assert all(item.event_end <= DECISION_TIME for item in result.comparisons)


def test_intraday_recomputation_mismatch_fails_closed() -> None:
    bars = (
        _bar(SESSION, time(14, 45), open_price="10", close="10", volume="100"),
        _bar(SESSION, time(14, 50), open_price="10", close="12", volume="100"),
    )
    persisted = (
        PersistedFeatureObservation.create(
            factor_id="intraday_return_to_decision_time",
            value=Decimal("0.199999999999"),
            source_bars=bars,
        ),
    )

    result = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=bars,
        persisted=persisted,
        physical_source_available=True,
    )

    assert result.status is AlphaCorrectnessStatus.CORRECTNESS_FAILED
    assert result.discrepancies == (
        "VALUE_MISMATCH:intraday_return_to_decision_time",
    )


def test_owner_replay_cannot_claim_physical_reproduction() -> None:
    bars = (
        _bar(SESSION, time(14, 45), open_price="10", close="10", volume="100"),
        _bar(SESSION, time(14, 50), open_price="10", close="12", volume="100"),
    )
    persisted = (
        PersistedFeatureObservation.create(
            factor_id="intraday_return_to_decision_time",
            value=Decimal("0.200000000000"),
            source_bars=bars,
        ),
    )

    result = reproduce_intraday_features(
        session=SESSION,
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        source_bars=bars,
        persisted=persisted,
        physical_source_available=False,
    )

    assert (
        result.status
        is AlphaCorrectnessStatus.PHYSICAL_REPRODUCTION_NOT_ESTABLISHED
    )
    assert result.discrepancies == ()


def test_t_plus_one_target_is_recomputed_from_a_later_session_checkpoint() -> None:
    decision_bar = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )
    target_bars = tuple(
        _bar(
            NEXT_SESSION,
            (datetime.combine(NEXT_SESSION, time(9, 30)) + timedelta(minutes=5 * index)).time(),
            open_price=str(Decimal("12") + Decimal(index) / Decimal("10")),
            close=str(Decimal("12.1") + Decimal(index) / Decimal("10")),
            volume="100",
            row=100 + index,
        )
        for index in range(12)
    )
    persisted = PersistedTargetObservation.create(
        decision_reference_price=Decimal("12"),
        target_price=Decimal("13.2"),
        target_return=Decimal("0.1"),
        decision_source_bars=(decision_bar,),
        target_source_bars=target_bars,
        target_session=NEXT_SESSION,
    )

    result = reproduce_t_plus_one_1030_target(
        symbol="600000.SH",
        decision_time=DECISION_TIME,
        next_session=NEXT_SESSION,
        source_bars=(decision_bar, *target_bars),
        persisted=persisted,
        physical_source_available=True,
    )

    assert result.status is AlphaCorrectnessStatus.CORRECTNESS_SUPPORTED
    assert result.decision_reference_price == Decimal("12")
    assert result.target_price == Decimal("13.2")
    assert result.target_return == Decimal("0.1")
    assert result.target_session > SESSION
    assert result.target_event_end == datetime.combine(
        NEXT_SESSION, time(10, 30), SHANGHAI
    ).astimezone(UTC)
    assert set(result.decision_source_ids).isdisjoint(result.target_source_ids)


def test_t_plus_one_target_rejects_same_session_and_future_feature_lineage() -> None:
    decision_bar = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )

    with pytest.raises(ValueError, match="later trading session"):
        reproduce_t_plus_one_1030_target(
            symbol="600000.SH",
            decision_time=DECISION_TIME,
            next_session=SESSION,
            source_bars=(decision_bar,),
            persisted=None,
            physical_source_available=True,
        )


def test_t_plus_one_target_requires_complete_open_to_checkpoint_window() -> None:
    decision_bar = _bar(
        SESSION,
        time(14, 50),
        open_price="11.9",
        close="12",
        volume="100",
    )
    incomplete = tuple(
        _bar(
            NEXT_SESSION,
            (
                datetime.combine(NEXT_SESSION, time(9, 35))
                + timedelta(minutes=5 * index)
            ).time(),
            open_price="13",
            close="13",
            volume="100",
            row=200 + index,
        )
        for index in range(11)
    )

    with pytest.raises(ValueError, match="checkpoint is incomplete"):
        reproduce_t_plus_one_1030_target(
            symbol="600000.SH",
            decision_time=DECISION_TIME,
            next_session=NEXT_SESSION,
            source_bars=(decision_bar, *incomplete),
            persisted=None,
            physical_source_available=True,
        )


def _bar(
    market_date: date,
    start_time: time,
    *,
    open_price: str,
    close: str,
    volume: str,
    row: int = 1,
) -> HistoricalNormalizedBar:
    event_start = datetime.combine(market_date, start_time, SHANGHAI).astimezone(UTC)
    close_value = Decimal(close)
    volume_value = Decimal(volume)
    return HistoricalNormalizedBar.create(
        symbol="600000.SH",
        timeframe=Timeframe.MINUTE_5,
        market_date=market_date,
        event_start=event_start,
        event_end=event_start + timedelta(minutes=5),
        retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
        open=Decimal(open_price),
        high=max(Decimal(open_price), close_value),
        low=min(Decimal(open_price), close_value),
        close=close_value,
        volume=volume_value,
        amount=volume_value * close_value,
        adjustment_basis="RAW_UNADJUSTED",
        trading_status=HistoricalTradingStatus.TRADING,
        st_status=None,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST",
            ArtifactId("raw-request-correctness"),
            canonical_hash({"request": "correctness"}),
        ),
        raw_row_number=row,
        missing_fields=("listing_status", "st_status"),
        limitations=("PIT_INCOMPLETE",),
    )
