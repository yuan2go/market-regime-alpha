from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.formal_dataset_builder import (
    FormalDatasetBuildError,
    FormalDatasetBuildRequest,
    FormalDatasetSidecars,
    build_rehearsal_dataset,
    write_rehearsal_dataset_artifact,
)
from market_regime_alpha.dividend_t.macd import PriceAdjustmentMode


def test_builder_accepts_only_a_complete_5_to_10_symbol_three_month_rehearsal_bundle(tmp_path: Path) -> None:
    request = _complete_request(tmp_path)

    result = build_rehearsal_dataset(request)

    assert result.manifest.classification.value == "REHEARSAL"
    assert result.manifest.symbols == ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ")
    assert result.manifest.quality.finalized_bar_count == result.manifest.total_bar_count
    assert result.quality.blocking_reasons == ()
    assert result.quality.calendar_span_days >= 90

    artifact = write_rehearsal_dataset_artifact(result, tmp_path / "artifact")
    assert (artifact / "manifest.json").is_file()
    assert (artifact / "quality.json").is_file()
    with pytest.raises(FileExistsError):
        write_rehearsal_dataset_artifact(result, artifact)


def test_builder_rejects_existing_raw_bars_without_explicit_finalization_or_sidecars(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "symbol,timestamp,open,high,low,close,volume,amount,source_freq\n"
        "600519.SH,2026-01-05 09:35:00,10,10,10,10,100,1000,5min\n",
        encoding="utf-8",
    )
    request = _complete_request(tmp_path / "sidecars", bars=(raw,))

    with pytest.raises(FormalDatasetBuildError, match="BAR_FINAL_REQUIRED"):
        build_rehearsal_dataset(request)


def _complete_request(tmp_path: Path, *, bars: tuple[Path, ...] | None = None) -> FormalDatasetBuildRequest:
    tmp_path.mkdir(parents=True, exist_ok=True)
    symbols = tuple(f"00000{index}.SZ" for index in range(1, 6))
    days = tuple(pd.bdate_range("2026-01-02", periods=65).strftime("%Y-%m-%d"))
    timestamps = [timestamp for day in days for timestamp in _session_times(day)]
    if bars is None:
        bars = tuple(tmp_path / f"{symbol}.csv" for symbol in symbols)
        for symbol, path in zip(symbols, bars, strict=True):
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "timestamp": timestamps,
                    "open": 10.0,
                    "high": 10.1,
                    "low": 9.9,
                    "close": 10.0,
                    "volume": 100.0,
                    "amount": 1000.0,
                    "vwap": 10.0,
                    "bar_final": True,
                    "source_freq": "5min",
                }
            ).to_csv(path, index=False)

    calendar = tmp_path / "calendar.json"
    calendar.write_text(json.dumps({"trading_dates": list(days), "sessions": [{"trade_date": day, "session_close": f"{day} 15:00:00"} for day in days]}), encoding="utf-8")
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"records": [{"as_of_date": day, "symbol": symbol, "universe_id": "fixture", "eligible": True, "listing_status": "L"} for day in days for symbol in symbols]}), encoding="utf-8")
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({"events": []}), encoding="utf-8")
    suspensions = tmp_path / "suspensions.json"
    suspensions.write_text(json.dumps({"suspension_times": [], "records": []}), encoding="utf-8")
    eligibility = tmp_path / "eligibility.json"
    eligibility.write_text(json.dumps({"records": [{"symbol": symbol, "timestamp": timestamp, "is_suspended": False, "is_st": False, "prev_close": 10.0, "limit_up_price": 11.0, "limit_down_price": 9.0, "limit_regime": "10pct"} for symbol in symbols for timestamp in timestamps]}), encoding="utf-8")
    market = tmp_path / "market.json"
    market.write_text(json.dumps({"records": [{"symbol": symbol, "timestamp": timestamp, "benchmark_symbol": "000300.SH", "index_close": 4000.0, "industry_id": "fixture-industry", "industry_as_of": timestamp, "industry_close": 2000.0, "theme_state": "NEUTRAL", "market_regime": "RANGE"} for symbol in symbols for timestamp in timestamps]}), encoding="utf-8")
    return FormalDatasetBuildRequest(
        bar_paths=bars,
        data_source="controlled-fixture-v1",
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=True,
        trading_calendar_version="fixture-calendar-v1",
        sidecars=FormalDatasetSidecars(calendar, universe, actions, suspensions, eligibility, market),
    )


def _session_times(day: str) -> list[str]:
    morning = pd.date_range(f"{day} 09:35:00", f"{day} 11:30:00", freq="5min")
    afternoon = pd.date_range(f"{day} 13:05:00", f"{day} 15:00:00", freq="5min")
    return [item.strftime("%Y-%m-%d %H:%M:%S") for item in (*morning, *afternoon)]
