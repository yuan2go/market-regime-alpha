#!/usr/bin/env python3
"""Offline deterministic benchmark for canonical Feature materialization."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import time as wall_time
import tracemalloc
from typing import Sequence

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.features import FeatureMaterializationRunner
from market_regime_alpha.features.technical.catalog import (
    canonical_technical_feature_set,
)
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
    load_verified_market_data_dataset,
    publish_market_data_dataset,
)


UTC = timezone.utc
SOURCE_HASH = "sha256:" + "7" * 64
MANIFEST_HASH = "sha256:" + "8" * 64


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", type=int, default=100)
    parser.add_argument("--daily-sessions", type=int, default=250)
    parser.add_argument("--minute-bars-per-symbol", type=int, default=48)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.symbols <= 300:
        raise SystemExit("--symbols must be between 1 and 300")
    if args.daily_sessions < 60:
        raise SystemExit("--daily-sessions must be at least 60")
    if not 0 <= args.minute_bars_per_symbol <= 72:
        raise SystemExit("--minute-bars-per-symbol must be between 0 and 72")
    if args.output_dir is None:
        with tempfile.TemporaryDirectory(prefix="feature-benchmark-") as temporary:
            payload = _benchmark(args=args, root=Path(temporary))
    else:
        payload = _benchmark(args=args, root=args.output_dir.resolve())
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


def _benchmark(*, args: argparse.Namespace, root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    decision_time = datetime(2026, 8, 4, 7, 30, tzinfo=UTC)
    created_at = decision_time + timedelta(minutes=1)
    symbols = tuple(f"{600000 + index:06d}.SH" for index in range(args.symbols))
    bars = _bars(
        symbols=symbols,
        sessions=args.daily_sessions,
        minute_count=args.minute_bars_per_symbol,
        decision_time=decision_time,
    )
    expected_timeframes = (
        (Timeframe.DAILY, Timeframe.MINUTE_5)
        if args.minute_bars_per_symbol
        else (Timeframe.DAILY,)
    )
    dataset = MarketDataDatasetArtifact.create(
        decision_time=decision_time,
        created_at=created_at,
        bars=bars,
        expected_symbols=symbols,
        expected_timeframes=expected_timeframes,
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="benchmark-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (ArtifactId("benchmark-source-manifest"), MANIFEST_HASH),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("OFFLINE_SYNTHETIC_PERFORMANCE_FIXTURE",),
    )
    dataset_path = publish_market_data_dataset(
        root=root / "market-data", artifact=dataset
    )
    verified = load_verified_market_data_dataset(dataset_path)
    feature_set = canonical_technical_feature_set(
        effective_from=decision_time - timedelta(days=365)
    )
    runner = FeatureMaterializationRunner(max_workers=args.max_workers)
    tracemalloc.start()
    started = wall_time.perf_counter()
    receipt = runner.run(
        verified_dataset=verified,
        feature_set=feature_set,
        decision_time=decision_time,
        created_at=created_at,
        selected_symbols=symbols,
        code_revision="benchmark-feature-spine-v1",
        output_root=root / "features",
        idempotency_key="benchmark-feature-materialization-v1",
        resume=True,
    )
    cold_seconds = wall_time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    cached_started = wall_time.perf_counter()
    replayed_receipt = runner.run(
        verified_dataset=verified,
        feature_set=feature_set,
        decision_time=decision_time,
        created_at=created_at,
        selected_symbols=symbols,
        code_revision="benchmark-feature-spine-v1",
        output_root=root / "features",
        idempotency_key="benchmark-feature-materialization-v1",
        resume=True,
    )
    cached_seconds = wall_time.perf_counter() - cached_started
    if replayed_receipt != receipt:
        raise RuntimeError("cached benchmark receipt is not deterministic")
    return {
        "status": receipt.status.value,
        "symbols": len(symbols),
        "daily_sessions": args.daily_sessions,
        "minute_bars": args.minute_bars_per_symbol * len(symbols),
        "market_bar_count": len(bars),
        "feature_family_count": len(feature_set.definitions),
        "feature_artifact_count": receipt.artifact_count,
        "available_value_count": receipt.available_value_count,
        "missing_value_count": receipt.missing_value_count,
        "cold_run_seconds": round(cold_seconds, 6),
        "cached_run_seconds": round(cached_seconds, 6),
        "peak_traced_memory_bytes": peak_bytes,
        "output_bytes": _tree_size(root),
        "feature_bundle_id": str(receipt.bundle_id),
        "feature_bundle_hash": receipt.bundle_hash,
        "deterministic_cached_receipt": True,
        "network_used": False,
        "limitations": [
            "OFFLINE_SYNTHETIC_PERFORMANCE_FIXTURE",
            "NOT_A_MODEL_QUALITY_BENCHMARK",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
        ],
    }


def _bars(
    *,
    symbols: tuple[str, ...],
    sessions: int,
    minute_count: int,
    decision_time: datetime,
) -> tuple[CanonicalMarketBar, ...]:
    first_date = decision_time.date() - timedelta(days=sessions - 1)
    result: list[CanonicalMarketBar] = []
    for symbol_index, symbol in enumerate(symbols):
        base = Decimal("8") + Decimal(symbol_index) / Decimal("100")
        previous: Decimal | None = None
        for session in range(sessions):
            market_date = first_date + timedelta(days=session)
            close = base + Decimal(session) / Decimal("1000")
            event_start = datetime.combine(market_date, time(1, 30), tzinfo=UTC)
            event_end = datetime.combine(market_date, time(7), tzinfo=UTC)
            volume = Decimal(100000 + session * 100 + symbol_index)
            result.append(
                _bar(
                    symbol=symbol,
                    timeframe=Timeframe.DAILY,
                    market_date=market_date,
                    event_start=event_start,
                    event_end=event_end,
                    close=close,
                    previous_close=previous,
                    volume=volume,
                    source_id=f"benchmark-d-{symbol_index}-{session}",
                )
            )
            previous = close
        minute_start = datetime.combine(
            decision_time.date(), time(1, 30), tzinfo=UTC
        )
        for minute_index in range(minute_count):
            event_start = minute_start + timedelta(minutes=5 * minute_index)
            event_end = event_start + timedelta(minutes=5)
            close = base + Decimal(minute_index) / Decimal("10000")
            volume = Decimal(1000 + minute_index * 10 + symbol_index)
            result.append(
                _bar(
                    symbol=symbol,
                    timeframe=Timeframe.MINUTE_5,
                    market_date=decision_time.date(),
                    event_start=event_start,
                    event_end=event_end,
                    close=close,
                    previous_close=(base if minute_index == 0 else None),
                    volume=volume,
                    source_id=f"benchmark-m-{symbol_index}-{minute_index}",
                )
            )
    return tuple(result)


def _bar(
    *,
    symbol: str,
    timeframe: Timeframe,
    market_date: date,
    event_start: datetime,
    event_end: datetime,
    close: Decimal,
    previous_close: Decimal | None,
    volume: Decimal,
    source_id: str,
) -> CanonicalMarketBar:
    return CanonicalMarketBar.create(
        symbol=symbol,
        exchange=Exchange.SH,
        asset_type=AssetType.A_SHARE,
        timeframe=timeframe,
        market_date=market_date,
        event_start=event_start,
        event_end=event_end,
        available_at=event_end,
        open=close - Decimal("0.01"),
        high=close + Decimal("0.02"),
        low=close - Decimal("0.02"),
        close=close,
        previous_close=previous_close,
        volume=volume,
        volume_unit=VolumeUnit.SHARES,
        amount=close * volume,
        turnover_rate=Decimal("0.01"),
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=Decimal("1"),
        trading_status=TradingStatus.TRADING,
        price_limit_state=PriceLimitState.NORMAL,
        source_artifact_id=ArtifactId(source_id),
        source_content_hash=SOURCE_HASH,
    )


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


if __name__ == "__main__":
    raise SystemExit(main())
