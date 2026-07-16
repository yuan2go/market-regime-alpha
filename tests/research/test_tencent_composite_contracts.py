from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
    PreparedCompositeSession,
    build_tencent_composite_dataset_contract,
)


TZ = ZoneInfo("Asia/Shanghai")


def _session(symbol: str, day: date) -> PreparedCompositeSession:
    return PreparedCompositeSession(
        symbol=symbol,
        session_date=day,
        open=10.0,
        high=10.5,
        low=9.8,
        close=10.2,
        amount=1_000_000.0,
        reference_price=10.1,
        reference_timestamp=datetime(day.year, day.month, day.day, 14, 50, tzinfo=TZ),
        source_kinds=(CompositeSourceKind.LOCAL,),
    )


def test_composite_contract_is_exploratory_and_not_pit() -> None:
    contract = build_tencent_composite_dataset_contract(
        watchlist_hash="sha256:watchlist",
        source_content_hashes=("sha256:local", "sha256:tencent"),
        code_revision="abc123",
        config_hash="sha256:config",
    )

    assert contract.eligibility is DataEligibility.EXPLORATORY
    assert contract.pit_correct_for_scope is False
    assert "CURRENT_WATCHLIST_BACKFILL_BIAS" in contract.limitations
    assert {reference.product for reference in contract.provider_references} == {
        "minute-and-quote",
        "dividend-t-5min-cache",
        "historical-5min-backfill",
    }


def test_composite_dataset_identity_is_order_independent_for_source_hashes() -> None:
    first = build_tencent_composite_dataset_contract(
        watchlist_hash="sha256:watchlist",
        source_content_hashes=("sha256:local", "sha256:tencent"),
        code_revision="abc123",
        config_hash="sha256:config",
    )
    second = build_tencent_composite_dataset_contract(
        watchlist_hash="sha256:watchlist",
        source_content_hashes=("sha256:tencent", "sha256:local"),
        code_revision="abc123",
        config_hash="sha256:config",
    )

    assert first.dataset_id == second.dataset_id
    assert first.manifest_artifact_id == second.manifest_artifact_id


def test_composite_bar_rejects_invalid_ohlc_and_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CompositeBar(
            "000001.SZ",
            datetime(2026, 7, 1, 9, 35),
            10.0,
            11.0,
            9.0,
            10.0,
            100.0,
            1_000.0,
            CompositeSourceKind.LOCAL,
        )
    with pytest.raises(ValueError, match="OHLC"):
        CompositeBar(
            "000001.SZ",
            datetime(2026, 7, 1, 9, 35, tzinfo=TZ),
            10.0,
            9.0,
            10.0,
            10.0,
            100.0,
            1_000.0,
            CompositeSourceKind.LOCAL,
        )


def test_quality_success_requires_minimum_symbols_and_sessions() -> None:
    accepted = tuple(f"{index:06d}.SZ" for index in range(16))
    requested = accepted + tuple(f"9{index:05d}.SZ" for index in range(4))
    days = tuple(date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + index) for index in range(82))
    dispositions = tuple(
        CompositeSymbolDisposition(
            symbol=symbol,
            code=(CompositeDispositionCode.ACCEPTED if symbol in accepted else CompositeDispositionCode.REJECTED_HISTORY_GAP),
            complete_session_count=(82 if symbol in accepted else 10),
            findings=(),
        )
        for symbol in requested
    )
    report = CompositeQualityReport(
        requested_symbols=requested,
        accepted_symbols=accepted,
        dispositions=dispositions,
        common_session_dates=days,
        required_session_count=82,
        minimum_accepted_symbols=16,
    )

    assert report.success is True


def test_prepared_data_requires_unique_session_keys() -> None:
    symbol = "000001.SZ"
    day = date(2026, 7, 1)
    report = CompositeQualityReport(
        requested_symbols=(symbol,),
        accepted_symbols=(symbol,),
        dispositions=(
            CompositeSymbolDisposition(symbol, CompositeDispositionCode.ACCEPTED, 82, ()),
        ),
        common_session_dates=(day,),
        required_session_count=1,
        minimum_accepted_symbols=1,
    )
    with pytest.raises(ValueError, match="unique"):
        PreparedCompositeData(
            accepted_symbols=(symbol,),
            common_session_dates=(day,),
            sessions=(_session(symbol, day), _session(symbol, day)),
            quality=report,
            limitations=("CURRENT_WATCHLIST_BACKFILL_BIAS",),
        )
