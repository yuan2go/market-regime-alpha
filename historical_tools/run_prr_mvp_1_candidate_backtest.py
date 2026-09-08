#!/usr/bin/env python3
"""Run the bounded EXPLORATORY PRR-MVP-1 Candidate replay without trading side effects."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.dividend_t.storage import DEFAULT_WATCHLIST_PATH, load_watchlist
from market_regime_alpha.dividend_t.trend_snapshot import DEFAULT_LOCAL_TIMING_CACHE_DIR
from market_regime_alpha.research.prr_mvp_1 import (
    ExploratoryExecutionCostConfig,
    acceptance_accounting,
    build_prr_candidate_data,
    replay_fixed_candidate_portfolios,
)
from market_regime_alpha.research.prr_mvp_1_artifacts import (
    load_prr_cached_acquisition,
    write_prr_dataset,
    write_prr_failure,
    write_prr_raw_evidence,
    write_prr_run,
)
from market_regime_alpha.research.tencent_composite_execution import (
    complete_tencent_composite_research,
    execute_tencent_composite_research,
)
from market_regime_alpha.data_sources.a_share_bars import (
    BaoStockADataProvider,
    TencentMinuteProvider,
    fetch_tencent_latest_quotes,
    read_local_5min_cache,
)
from market_regime_alpha.research.tencent_composite_acquisition import TencentCompositeAcquirer
from functools import partial


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_RUN_ROOT = PROJECT_ROOT / "data" / "processed" / "prr_mvp_1_runs"
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "data" / "processed" / "prr_mvp_1_datasets"
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "prr_mvp_1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("tencent",), default="tencent")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--cached", action="store_true")
    parser.add_argument("--cached-acquisition", type=Path)
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST_PATH)
    parser.add_argument("--local-cache-dir", type=Path, default=DEFAULT_LOCAL_TIMING_CACHE_DIR)
    parser.add_argument("--retrieved-at")
    parser.add_argument("--decision-count", type=int, default=60)
    parser.add_argument("--warmup-sessions", type=int, default=21)
    parser.add_argument("--minimum-accepted-symbols", type=int, default=16)
    parser.add_argument("--history-calendar-days", type=int, default=180)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--entry-slippage-bps", type=float, default=5.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=5.0)
    parser.add_argument("--buy-commission-bps", type=float, default=3.0)
    parser.add_argument("--sell-commission-bps", type=float, default=3.0)
    parser.add_argument("--minimum-commission", type=float, default=5.0)
    parser.add_argument("--sell-stamp-duty-bps", type=float, default=5.0)
    parser.add_argument("--transfer-fee-bps", type=float, default=0.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cached and args.cached_acquisition is None:
        raise SystemExit("--cached requires --cached-acquisition")
    retrieved_at = _parse_retrieved_at(args.retrieved_at)
    code_revision = _revision()
    config = _config_snapshot(args, code_revision)
    config_hash = f"sha256:{_canonical_hash(config)}"
    run_id = f"prr-mvp-1-{retrieved_at.strftime('%Y%m%dT%H%M%S%z')}-{_canonical_hash(config)[:10]}"
    try:
        watchlist_items = load_watchlist(args.watchlist)[:20]
        if len(watchlist_items) != 20:
            raise ValueError("PRR-MVP-1 requires exactly 20 watchlist symbols")
        watchlist = tuple(item.symbol for item in watchlist_items)
        if args.cached:
            acquisition = load_prr_cached_acquisition(args.cached_acquisition)
            execution = complete_tencent_composite_research(
                acquisition=acquisition,
                watchlist=watchlist,
                watchlist_hash=_file_hash(args.watchlist),
                decision_count=args.decision_count,
                warmup_sessions=args.warmup_sessions,
                minimum_accepted_symbols=args.minimum_accepted_symbols,
                code_revision=code_revision,
                config_hash=config_hash,
                acquisition_mode="CACHED",
            )
        else:
            acquirer = TencentCompositeAcquirer(
                tencent=TencentMinuteProvider(timeout_seconds=args.timeout_seconds),
                baostock=BaoStockADataProvider(),
                local_reader=partial(read_local_5min_cache, cache_dir=args.local_cache_dir),
                quote_fetcher=partial(fetch_tencent_latest_quotes, timeout_seconds=args.timeout_seconds),
                retry_count=args.retry_count,
            )
            execution = execute_tencent_composite_research(
                acquirer=acquirer,
                watchlist=watchlist,
                watchlist_hash=_file_hash(args.watchlist),
                retrieved_at=RetrievedAt(retrieved_at),
                history_calendar_days=args.history_calendar_days,
                decision_count=args.decision_count,
                warmup_sessions=args.warmup_sessions,
                minimum_accepted_symbols=args.minimum_accepted_symbols,
                code_revision=code_revision,
                config_hash=config_hash,
                acquisition_mode="MIXED",
            )
        acquisition_id, raw_path = write_prr_raw_evidence(
            root=args.raw_root,
            execution=execution,
            request=config,
        )
        candidate_data = build_prr_candidate_data(
            execution=execution,
            code_revision=code_revision,
            config_hash=config_hash,
        )
        dataset_identifier, dataset_path, dataset_manifest = write_prr_dataset(
            root=args.dataset_root,
            execution=execution,
            candidate_data=candidate_data,
            acquisition_id=acquisition_id,
            raw_path=raw_path,
            code_revision=code_revision,
            config_hash=config_hash,
        )
        costs = ExploratoryExecutionCostConfig(
            buy_commission_bps=args.buy_commission_bps,
            sell_commission_bps=args.sell_commission_bps,
            minimum_commission=args.minimum_commission,
            sell_stamp_duty_bps=args.sell_stamp_duty_bps,
            transfer_fee_bps=args.transfer_fee_bps,
            entry_slippage_bps=args.entry_slippage_bps,
            exit_slippage_bps=args.exit_slippage_bps,
        )
        replay = replay_fixed_candidate_portfolios(
            execution=execution,
            candidate_data=candidate_data,
            run_id=run_id,
            top_k=args.top_k,
            cost_config=costs,
        )
        acceptance = acceptance_accounting(
            replay=replay,
            model_count=len(replay.metrics["models"]),
            decision_date_count=len(candidate_data.decision_dates),
            top_k=args.top_k,
        )
        path = write_prr_run(
            root=args.output_root,
            run_id=run_id,
            dataset_identifier=dataset_identifier,
            dataset_path=dataset_path,
            dataset_manifest=dataset_manifest,
            execution=execution,
            candidate_data=candidate_data,
            replay=replay,
            acceptance=acceptance,
            cost_config=costs,
            config_snapshot=config,
        )
    except Exception as exc:  # noqa: BLE001 - a live failure must be published verbatim.
        try:
            failure_path = write_prr_failure(
                root=args.output_root,
                run_id=run_id,
                config_snapshot=config,
                error=exc,
            )
        except Exception:
            raise exc
        print(f"PRR-MVP-1 failed with retained evidence: {failure_path}", file=sys.stderr)
        return 2
    print(f"PRR-MVP-1 completed: {path}")
    return 0


def _parse_retrieved_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(SHANGHAI_TZ)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--retrieved-at must be timezone-aware ISO-8601")
    return parsed.astimezone(SHANGHAI_TZ)


def _config_snapshot(args: argparse.Namespace, code_revision: str) -> dict[str, object]:
    return {
        "schema_version": "prr-mvp-1-config-v1",
        "source": args.source,
        "mode": "LIVE" if args.live else "CACHED",
        "cached_acquisition": str(args.cached_acquisition) if args.cached_acquisition else None,
        "watchlist": str(args.watchlist),
        "watchlist_hash": _file_hash(args.watchlist) if args.watchlist.is_file() else None,
        "decision_count": args.decision_count,
        "warmup_sessions": args.warmup_sessions,
        "minimum_accepted_symbols": args.minimum_accepted_symbols,
        "history_calendar_days": args.history_calendar_days,
        "top_k": args.top_k,
        "costs": {
            "buy_commission_bps": args.buy_commission_bps,
            "sell_commission_bps": args.sell_commission_bps,
            "minimum_commission": args.minimum_commission,
            "sell_stamp_duty_bps": args.sell_stamp_duty_bps,
            "transfer_fee_bps": args.transfer_fee_bps,
            "entry_slippage_bps": args.entry_slippage_bps,
            "exit_slippage_bps": args.exit_slippage_bps,
        },
        "code_revision": code_revision,
        "data_eligibility": "EXPLORATORY",
    }


def _revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _canonical_hash(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


if __name__ == "__main__":
    raise SystemExit(main())
