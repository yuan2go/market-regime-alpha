#!/usr/bin/env python3
"""Local scheduler for dividend-watchlist data refresh, trend scan, and GitHub Pages publishing."""

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
    fetch_tencent_1min_frame,
    is_a_share_market_session,
    write_tencent_1min_cache,
)
from market_regime_alpha.dividend_t.git_publish import publish_paths  # noqa: E402
from market_regime_alpha.dividend_t.storage import DEFAULT_WATCHLIST_PATH, load_watchlist  # noqa: E402
from market_regime_alpha.dividend_t.trend_snapshot import (  # noqa: E402
    DEFAULT_TREND_OUTPUT,
    build_dividend_trend_snapshot,
    write_dividend_trend_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local dividend trend scheduler and publish Pages JSON.")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST_PATH)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_TENCENT_CACHE_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_TREND_OUTPUT)
    parser.add_argument("--data-interval-seconds", type=int, default=300)
    parser.add_argument("--trend-interval-seconds", type=int, default=600)
    parser.add_argument("--timeout-seconds", type=float, default=4.0)
    parser.add_argument("--include-off-session", action="store_true", help="Run jobs outside A-share trading hours.")
    parser.add_argument("--no-push", action="store_true", help="Write JSON and commit nothing.")
    parser.add_argument("--git-remote", default="origin")
    parser.add_argument("--git-branch", default=None)
    parser.add_argument("--once", nargs="?", choices=["cache", "trend", "both"], const="both", help="Run one job and exit.")
    args = parser.parse_args()

    runner = DividendTrendScheduler(
        watchlist_path=args.watchlist,
        limit=args.limit,
        db_path=args.db_path,
        output_path=args.output,
        timeout_seconds=args.timeout_seconds,
        include_off_session=args.include_off_session,
        push=not args.no_push,
        git_remote=args.git_remote,
        git_branch=args.git_branch,
    )

    if args.once:
        if args.once in {"cache", "both"}:
            runner.cache_latest_data()
        if args.once in {"trend", "both"}:
            runner.publish_trend_snapshot()
        return 0

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError as exc:
        raise SystemExit("Install APScheduler with `pip install -r requirements.txt`.") from exc

    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        runner.cache_latest_data,
        "interval",
        seconds=args.data_interval_seconds,
        id="dividend_watchlist_data_cache",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    scheduler.add_job(
        runner.publish_trend_snapshot,
        "interval",
        seconds=args.trend_interval_seconds,
        id="dividend_watchlist_trend_publish",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    print("红利观察池本地定时任务已启动。", flush=True)
    print(f"行情采集间隔：{args.data_interval_seconds} 秒；趋势发布间隔：{args.trend_interval_seconds} 秒。", flush=True)
    print(f"观察池：{args.watchlist}；输出：{args.output}", flush=True)
    print("说明：只生成研究快照并推送 GitHub Pages JSON，不自动下单。", flush=True)
    scheduler.start()
    return 0


class DividendTrendScheduler:
    def __init__(
        self,
        *,
        watchlist_path: Path,
        limit: int,
        db_path: Path,
        output_path: Path,
        timeout_seconds: float,
        include_off_session: bool,
        push: bool,
        git_remote: str,
        git_branch: str | None,
    ) -> None:
        self.watchlist_path = watchlist_path
        self.limit = limit
        self.db_path = db_path
        self.output_path = output_path
        self.timeout_seconds = timeout_seconds
        self.include_off_session = include_off_session
        self.push = push
        self.git_remote = git_remote
        self.git_branch = git_branch

    def cache_latest_data(self) -> None:
        now = _now_text()
        if self._should_skip_session():
            print(f"[{now}] 非交易时段，跳过 5 分钟行情采集。", flush=True)
            return

        symbols = [item.symbol for item in load_watchlist(self.watchlist_path)[: self.limit]]
        if not symbols:
            print(f"[{now}] 观察池为空，跳过行情采集。", flush=True)
            return

        ok_count = 0
        fail_count = 0
        for symbol in symbols:
            try:
                frame = fetch_tencent_1min_frame(symbol, timeout_seconds=self.timeout_seconds)
                result = write_tencent_1min_cache(frame, database_path=self.db_path)
                ok_count += 1
                print(
                    f"[{now}] cache {result.symbol} fetched={result.fetched_rows} "
                    f"inserted={result.inserted_rows} latest={result.latest_timestamp}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - continue other symbols.
                fail_count += 1
                print(f"[{now}] cache {symbol} failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        print(f"[{now}] 行情采集完成：success={ok_count} failed={fail_count} db={self.db_path}", flush=True)

    def publish_trend_snapshot(self) -> None:
        now = _now_text()
        if self._should_skip_session():
            print(f"[{now}] 非交易时段，跳过 10 分钟趋势计算。", flush=True)
            return

        snapshot = build_dividend_trend_snapshot(
            watchlist_path=self.watchlist_path,
            limit=self.limit,
            timeout_seconds=self.timeout_seconds,
        )
        output = write_dividend_trend_snapshot(snapshot, output_path=self.output_path)
        print(
            f"[{now}] 趋势快照已写入 {output}：rows={snapshot['row_count']} "
            f"success={snapshot['successful_count']} failed={snapshot['failed_count']}",
            flush=True,
        )

        if not self.push:
            print(f"[{now}] --no-push 已启用，跳过 git commit/push。", flush=True)
            return

        try:
            result = publish_paths(
                repo_root=PROJECT_ROOT,
                paths=[output],
                commit_message=f"Update dividend trend snapshot {datetime.now().strftime('%Y-%m-%d %H:%M')} [skip ci]",
                remote=self.git_remote,
                branch=self.git_branch,
                push=True,
            )
        except Exception as exc:  # noqa: BLE001 - keep scheduler alive after git failures.
            print(f"[{now}] git 发布失败：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return
        print(
            f"[{now}] git 发布完成：changed={result.changed} committed={result.committed} "
            f"pushed={result.pushed} commit={result.commit_hash} message={result.message}",
            flush=True,
        )

    def _should_skip_session(self) -> bool:
        return not self.include_off_session and not is_a_share_market_session()


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    raise SystemExit(main())
