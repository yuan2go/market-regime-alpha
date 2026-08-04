#!/usr/bin/env python3
"""Offline deterministic benchmark for canonical Feature materialization."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import resource
import sys
import tempfile
import time as wall_time
from typing import Sequence, cast

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.features import (
    FEATURE_ARTIFACT_ENCODING_V2,
    FEATURE_BUNDLE_ENCODING_V2,
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunner,
    load_verified_feature_bundle_v2,
    read_feature_values_v2,
)
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
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.signals import (
    CandidateFeatureView,
    SignalInputAssemblerV3,
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
    run_signal_model_v3,
)
import tracemalloc


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
    parser.add_argument("--reuse-json-v1-root", type=Path)
    parser.add_argument("--reuse-json-v1-metrics", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.symbols <= 300:
        raise SystemExit("--symbols must be between 1 and 300")
    if args.daily_sessions < 60:
        raise SystemExit("--daily-sessions must be at least 60")
    if not 0 <= args.minute_bars_per_symbol <= 72:
        raise SystemExit("--minute-bars-per-symbol must be between 0 and 72")
    if (args.reuse_json_v1_root is None) != (args.reuse_json_v1_metrics is None):
        raise SystemExit("--reuse-json-v1-root and --reuse-json-v1-metrics must be supplied together")
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
    expected_timeframes = (Timeframe.DAILY, Timeframe.MINUTE_5) if args.minute_bars_per_symbol else (Timeframe.DAILY,)
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
        source_manifest_references=((ArtifactId("benchmark-source-manifest"), MANIFEST_HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("OFFLINE_SYNTHETIC_PERFORMANCE_FIXTURE",),
    )
    feature_set = canonical_technical_feature_set(effective_from=decision_time - timedelta(days=365))
    if args.reuse_json_v1_root is not None:
        v1 = _reuse_json_v1_baseline(
            root=args.reuse_json_v1_root.resolve(),
            metrics_path=args.reuse_json_v1_metrics.resolve(),
            expected_dataset=dataset,
            expected_feature_count=len(feature_set.definitions) * len(symbols),
        )
    else:
        v1 = _benchmark_encoding(
            root=root / "json-v1",
            dataset=dataset,
            feature_set=feature_set,
            symbols=symbols,
            decision_time=decision_time,
            created_at=created_at,
            max_workers=args.max_workers,
            market_encoding="market-data-package-json-v1",
            artifact_encoding="feature-artifact-package-json-v1",
            bundle_encoding="feature-bundle-package-json-v1",
        )
    v2 = _benchmark_encoding(
        root=root / "columnar-v2",
        dataset=dataset,
        feature_set=feature_set,
        symbols=symbols,
        decision_time=decision_time,
        created_at=created_at,
        max_workers=args.max_workers,
        market_encoding="market-data-package-encoding-v2",
        artifact_encoding=FEATURE_ARTIFACT_ENCODING_V2,
        bundle_encoding=FEATURE_BUNDLE_ENCODING_V2,
    )
    if v1["feature_bundle_hash"] != v2["feature_bundle_hash"]:
        raise RuntimeError("Feature logical hash differs between physical encodings")
    signal_hash_v1 = _signal_hash(
        verified_bundle=v1.pop("_verified_bundle"),
        verified_dataset=v1.pop("_verified_dataset"),
        decision_time=decision_time,
        created_at=created_at,
        symbols=symbols,
    )
    signal_hash_v2 = _signal_hash(
        verified_bundle=v2.pop("_verified_bundle"),
        verified_dataset=v2.pop("_verified_dataset"),
        decision_time=decision_time,
        created_at=created_at,
        symbols=symbols,
    )
    output_reduction = 1 - cast(int, v2["output_bytes"]) / cast(int, v1["output_bytes"])
    selective_reduction = 1 - cast(float, v2["selective_read_seconds"]) / cast(float, v1["selective_read_seconds"])
    cold_materialization_ratio = cast(float, v2["cold_materialization_seconds"]) / cast(float, v1["cold_materialization_seconds"])
    signal_hash_equal = signal_hash_v1 == signal_hash_v2
    cold_target_met = cold_materialization_ratio <= 1.2
    benchmark_passed = output_reduction >= 0.7 and selective_reduction >= 0.5 and cold_target_met and signal_hash_equal
    peak_value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    process_peak_bytes = peak_value if sys.platform == "darwin" else peak_value * 1024
    return {
        "status": "PASS" if benchmark_passed else "TARGET_NOT_MET",
        "symbols": len(symbols),
        "daily_sessions": args.daily_sessions,
        "minute_bars": args.minute_bars_per_symbol * len(symbols),
        "market_bar_count": len(bars),
        "feature_family_count": len(feature_set.definitions),
        # Backward-compatible summary fields describe the new default V2
        # production encoding.  Detailed comparisons remain grouped below.
        "feature_artifact_count": v2["feature_artifact_count"],
        "cold_run_seconds": v2["cold_materialization_seconds"],
        "cached_run_seconds": v2["cached_receipt_seconds"],
        "peak_memory_bytes": v2["peak_memory_bytes"],
        "output_bytes": v2["output_bytes"],
        "deterministic_cached_receipt": v2["deterministic_cached_receipt"],
        "json_v1": v1,
        "columnar_v2": v2,
        "output_size_reduction_ratio": round(output_reduction, 6),
        "selective_read_reduction_ratio": round(selective_reduction, 6),
        "cold_materialization_v2_to_v1_ratio": round(cold_materialization_ratio, 6),
        "storage_reduction_target_met": output_reduction >= 0.7,
        "selective_read_target_met": selective_reduction >= 0.5,
        "cold_materialization_target_met": cold_target_met,
        "semantic_feature_bundle_hash_equal": True,
        "signal_artifact_hash_v1": signal_hash_v1,
        "signal_artifact_hash_v2": signal_hash_v2,
        "signal_artifact_hash_equal": signal_hash_equal,
        "replay_equal": (bool(v1["deterministic_cached_receipt"]) and bool(v2["deterministic_cached_receipt"]) and signal_hash_equal),
        "process_peak_memory_bytes": process_peak_bytes,
        "network_used": False,
        "limitations": [
            "OFFLINE_SYNTHETIC_PERFORMANCE_FIXTURE",
            "NOT_A_MODEL_QUALITY_BENCHMARK",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
        ],
    }


def _reuse_json_v1_baseline(
    *,
    root: Path,
    metrics_path: Path,
    expected_dataset: MarketDataDatasetArtifact,
    expected_feature_count: int,
) -> dict[str, object]:
    """Reuse a verified same-fixture V1 run while rerunning only an optimized V2."""

    metrics_raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(metrics_raw, dict):
        raise ValueError("reused JSON V1 metrics must be an object")
    metrics: dict[str, object] = dict(metrics_raw)
    dataset_paths = tuple(item for item in (root / "market-data").iterdir() if item.is_dir())
    bundle_paths = tuple(item for item in (root / "features" / "feature-bundles").iterdir() if item.is_dir())
    if len(dataset_paths) != 1 or len(bundle_paths) != 1:
        raise ValueError("reused JSON V1 baseline package scope is ambiguous")
    verified_dataset = load_verified_market_data_dataset(dataset_paths[0])
    if verified_dataset.artifact.to_canonical_dict() != expected_dataset.to_canonical_dict():
        raise ValueError("reused JSON V1 Dataset differs from current fixture")
    verified_bundle = load_verified_feature_bundle_v2(
        bundle_paths[0],
        artifact_root=root / "features" / "feature-artifacts",
    )
    if len(verified_bundle.artifacts) != expected_feature_count:
        raise ValueError("reused JSON V1 Feature scope differs from current fixture")
    required_metrics = {
        "output_bytes",
        "cold_materialization_seconds",
        "cached_receipt_seconds",
        "full_read_seconds",
        "selective_read_seconds",
        "peak_memory_bytes",
        "artifact_file_count",
        "feature_artifact_count",
        "available_value_count",
        "missing_value_count",
        "feature_bundle_id",
        "feature_bundle_hash",
        "deterministic_cached_receipt",
    }
    if not required_metrics.issubset(metrics):
        raise ValueError("reused JSON V1 metrics are incomplete")
    if metrics["feature_bundle_hash"] != verified_bundle.artifact.content_hash:
        raise ValueError("reused JSON V1 metric hash disagrees with verified Bundle")
    metrics["reused_verified_baseline"] = True
    metrics["_verified_bundle"] = verified_bundle
    metrics["_verified_dataset"] = verified_dataset
    return metrics


def _benchmark_encoding(
    *,
    root: Path,
    dataset: MarketDataDatasetArtifact,
    feature_set,
    symbols: tuple[str, ...],
    decision_time: datetime,
    created_at: datetime,
    max_workers: int,
    market_encoding: str,
    artifact_encoding: str,
    bundle_encoding: str,
) -> dict[str, object]:
    dataset_path = publish_market_data_dataset(
        root=root / "market-data",
        artifact=dataset,
        encoding_version=market_encoding,
    )
    verified = load_verified_market_data_dataset(dataset_path)
    runner = FeatureMaterializationRunner(max_workers=max_workers)
    tracemalloc.start()
    started = wall_time.perf_counter()
    receipt = runner.run(
        verified_dataset=verified,
        feature_set=feature_set,
        decision_time=decision_time,
        created_at=created_at,
        selected_symbols=symbols,
        code_revision="benchmark-feature-spine-v2",
        output_root=root / "features",
        idempotency_key="benchmark-feature-materialization-v2",
        execution_mode=FeatureMaterializationExecutionMode.START_NEW,
        artifact_encoding_version=artifact_encoding,
        bundle_encoding_version=bundle_encoding,
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
        code_revision="benchmark-feature-spine-v2",
        output_root=root / "features",
        idempotency_key="benchmark-feature-materialization-v2",
        execution_mode=FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE,
        artifact_encoding_version=artifact_encoding,
        bundle_encoding_version=bundle_encoding,
    )
    cached_seconds = wall_time.perf_counter() - cached_started
    if replayed_receipt != receipt:
        raise RuntimeError("cached benchmark receipt is not deterministic")
    bundle_path = root / "features" / receipt.bundle_locator
    artifact_root = root / "features" / "feature-artifacts"
    full_read_started = wall_time.perf_counter()
    bundle = load_verified_feature_bundle_v2(bundle_path, artifact_root=artifact_root)
    full_read_seconds = wall_time.perf_counter() - full_read_started
    selective_started = wall_time.perf_counter()
    if bundle_encoding == FEATURE_BUNDLE_ENCODING_V2:
        selected_count = len(
            read_feature_values_v2(
                bundle_path,
                symbols=(symbols[0],),
                output_ids=("price_vs_vwap_return",),
                timeframes=(Timeframe.MINUTE_5,),
            ).rows
        )
    else:
        selected_count = sum(
            item.artifact.symbol == symbols[0]
            and item.artifact.timeframe is Timeframe.MINUTE_5
            and any(value.output_id == "price_vs_vwap_return" for value in item.artifact.values)
            for item in load_verified_feature_bundle_v2(bundle_path, artifact_root=artifact_root).artifacts
        )
    selective_seconds = wall_time.perf_counter() - selective_started
    if selected_count != 1:
        raise RuntimeError("selective benchmark projection mismatch")
    return {
        "physical_encoding": bundle_encoding,
        "status": receipt.status.value,
        "output_bytes": _tree_size(root),
        "cold_materialization_seconds": round(cold_seconds, 6),
        "cached_receipt_seconds": round(cached_seconds, 6),
        "full_read_seconds": round(full_read_seconds, 6),
        "selective_read_seconds": round(selective_seconds, 6),
        "peak_memory_bytes": peak_bytes,
        "artifact_file_count": sum(1 for item in root.rglob("*") if item.is_file()),
        "feature_artifact_count": receipt.artifact_count,
        "available_value_count": receipt.available_value_count,
        "missing_value_count": receipt.missing_value_count,
        "feature_bundle_id": str(receipt.bundle_id),
        "feature_bundle_hash": receipt.bundle_hash,
        "deterministic_cached_receipt": True,
        "_verified_bundle": bundle,
        "_verified_dataset": verified,
    }


def _signal_hash(
    *,
    verified_bundle,
    verified_dataset,
    decision_time: datetime,
    created_at: datetime,
    symbols: tuple[str, ...],
) -> str:
    selected_symbols = symbols[: min(5, len(symbols))]
    records = tuple(
        CandidateRecord(
            symbol=symbol,
            primary_theme_id=None,
            supporting_theme_ids=(),
            market_regime_status=MarketState.RISK_NEUTRAL,
            theme_rotation_state=RotationState.DATA_INSUFFICIENT,
            capital_evolution_state=CapitalEvolutionState.DATA_INSUFFICIENT,
            market_regime_score=0.0,
            theme_score=None,
            capital_evolution_score=None,
            candidate_discovery_score=0.5,
            rank=index,
            selection_status=CandidateSelectionStatus.SELECTED,
            reason_codes=("BENCHMARK_CONTROLLED_SUBSET",),
            source_feature_ids=(),
            input_artifact_ids=(),
        )
        for index, symbol in enumerate(selected_symbols, start=1)
    )
    candidate_payload = {
        "records": [item.to_canonical_dict() for item in records],
        "minimum_candidate_population": 1,
        "reason_codes": ["BENCHMARK_CONTROLLED_SUBSET"],
    }
    source_manifest_id, source_manifest_hash = verified_dataset.artifact.source_manifest_references[0]
    candidate_set = CandidateSet(
        envelope=ArtifactEnvelope.create(
            artifact_type="CANDIDATE_SET",
            artifact_payload=candidate_payload,
            decision_date=decision_time.date(),
            decision_time=DecisionTime(decision_time),
            created_at=created_at,
            code_revision="benchmark-feature-spine-v2",
            configuration_id=verified_bundle.artifact.feature_set.feature_set_id,
            configuration_hash=verified_bundle.artifact.feature_set.content_hash,
            source_manifest_id=source_manifest_id,
            source_manifest_hash=source_manifest_hash,
            input_artifact_ids=(ArtifactId(str(verified_dataset.artifact.dataset_id)),),
            input_content_hashes=(verified_dataset.artifact.content_hash,),
            model_id=None,
            model_version=None,
            data_eligibility=DataEligibility.EXPLORATORY,
            evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
            status="RESEARCH_ONLY",
            reason_codes=("BENCHMARK_CONTROLLED_SUBSET",),
            limitations=("OFFLINE_SYNTHETIC_PERFORMANCE_FIXTURE",),
        ),
        records=records,
        minimum_candidate_population=1,
        reason_codes=("BENCHMARK_CONTROLLED_SUBSET",),
    )
    view = CandidateFeatureView.create(
        candidate_set=candidate_set,
        feature_bundle=verified_bundle,
        verified_dataset=verified_dataset,
        minimum_data_eligibility=DataEligibility.EXPLORATORY,
    )
    market_dates = tuple(sorted({item.market_date for item in verified_dataset.bars if item.timeframe is Timeframe.DAILY}))
    shanghai = timezone(timedelta(hours=8))
    calendar = build_trading_calendar_artifact(
        source_dataset_id=verified_dataset.artifact.dataset_id,
        market="A_SHARE",
        calendar_version="benchmark-explicit-calendar-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=value,
                session_close=datetime.combine(value, time(15), tzinfo=shanghai),
            )
            for value in market_dates
        ),
    )
    mapping = canonical_signal_input_mapping_v2(effective_from=decision_time - timedelta(days=365))
    requirement = canonical_all_factors_required_policy()
    freshness = canonical_signal_freshness_policy(trading_calendar=calendar)
    observations = SignalInputAssemblerV3().assemble(
        candidate_set=candidate_set,
        candidate_feature_view=view,
        feature_bundle=verified_bundle,
        verified_dataset=verified_dataset,
        mapping_configuration=mapping,
        requirement_policy=requirement,
        freshness_policy=freshness,
        trading_calendar=calendar,
        decision_time=DecisionTime(decision_time),
    )
    signal = run_signal_model_v3(
        candidate_set=candidate_set,
        candidate_feature_view=view,
        feature_bundle=verified_bundle,
        verified_dataset=verified_dataset,
        mapping_configuration=mapping,
        requirement_policy=requirement,
        freshness_policy=freshness,
        trading_calendar=calendar,
        signal_configuration=canonical_signal_model_configuration_v2(),
        observations=observations,
        decision_time=DecisionTime(decision_time),
        created_at=created_at,
        code_revision="benchmark-feature-spine-v2",
    )
    return signal.envelope.content_hash


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
        minute_start = datetime.combine(decision_time.date(), time(1, 30), tzinfo=UTC)
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
