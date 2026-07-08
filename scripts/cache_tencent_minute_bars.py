#!/usr/bin/env python3
"""Cache Tencent 1-minute A-share intraday data into DuckDB."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.tencent_minute_cache import (  # noqa: E402
    DEFAULT_TENCENT_CACHE_DB,
    cache_tencent_1min,
    is_a_share_market_session,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache Tencent 1-minute bars into DuckDB.")
    parser.add_argument("symbols", nargs="*", default=["601919.SH"], help="Symbols such as 601919.SH.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_TENCENT_CACHE_DB)
    parser.add_argument("--interval-seconds", type=int, default=60, help="Polling interval for scheduler mode.")
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--once", action="store_true", help="Run one cache update and exit.")
    parser.add_argument("--include-off-session", action="store_true", help="Also poll outside A-share market sessions.")
    args = parser.parse_args()

    def job() -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not args.include_off_session and not is_a_share_market_session():
            print(f"[{now}] 非交易时段，跳过腾讯分钟缓存。", flush=True)
            return
        try:
            results = cache_tencent_1min(args.symbols, database_path=args.db_path, timeout_seconds=args.timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            print(f"[{now}] 缓存失败：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return
        for result in results:
            print(
                f"[{now}] {result.symbol} fetched={result.fetched_rows} "
                f"inserted={result.inserted_rows} latest={result.latest_timestamp} "
                f"db={result.database_path}",
                flush=True,
            )

    if args.once:
        job()
        return 0

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError as exc:
        raise SystemExit("Install APScheduler with `pip install -r requirements.txt`.") from exc

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        job,
        "interval",
        seconds=args.interval_seconds,
        id="tencent_1min_cache",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    print("腾讯 1 分钟行情缓存任务已启动。", flush=True)
    print(f"标的：{', '.join(args.symbols)}", flush=True)
    print(f"间隔：{args.interval_seconds} 秒；数据库：{args.db_path}", flush=True)
    print("说明：只缓存行情，不生成交易指令，不自动下单。", flush=True)
    scheduler.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
