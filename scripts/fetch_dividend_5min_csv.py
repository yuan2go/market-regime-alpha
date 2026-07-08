#!/usr/bin/env python3
"""Fetch normalized 5-minute A-share CSV files for dividend T backtests."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
import signal
import sys
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import fetch_a_share_5min_with_fallback  # noqa: E402
from market_regime_alpha.dividend_t.storage import load_watchlist  # noqa: E402


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch dividend watchlist 5-minute CSV data.")
    parser.add_argument("symbols", nargs="*", help="Symbols such as 601919.SH 600900.SH.")
    parser.add_argument("--watchlist", type=Path, help="Optional watchlist CSV path. Symbols from CLI and watchlist are merged.")
    parser.add_argument("--provider", default="strict", help="strict, fast, auto, tencent, eastmoney, akshare, baostock, yfinance, or tushare.")
    parser.add_argument("--days", type=int, default=100)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-rows", type=int, default=500)
    parser.add_argument("--limit", type=int, default=0, help="Limit symbol count after merging watchlist and CLI symbols. 0 means all.")
    parser.add_argument("--workers", type=int, default=1, help="Process workers for parallel fetch. 1 means serial.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per symbol after a failed provider fetch.")
    parser.add_argument("--retry-sleep", type=float, default=1.0, help="Seconds to wait between per-symbol retries.")
    parser.add_argument("--symbol-timeout-seconds", type=int, default=180, help="Hard timeout for one symbol fetch attempt.")
    parser.add_argument("--isolate-symbol-process", action="store_true", help="Run each symbol in a fresh child process when workers=1.")
    parser.add_argument("--hard-timeout-seconds", type=int, default=240, help="Terminate an isolated child process after this many seconds.")
    parser.add_argument("--force", action="store_true", help="Refetch symbols even when output CSV already exists.")
    parser.add_argument(
        "--min-existing-end-date",
        help="Skip an existing CSV only when its latest timestamp is on or after this YYYY-MM-DD date.",
    )
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]
    if args.watchlist:
        symbols.extend(item.symbol.upper() for item in load_watchlist(args.watchlist))
    symbols = list(dict.fromkeys(symbols))
    if args.limit > 0:
        symbols = symbols[: args.limit]
    if not symbols:
        parser.error("provide symbols or --watchlist")

    end = datetime.now()
    start = end - timedelta(days=args.days)
    start_text = start.strftime("%Y-%m-%d 09:00:00")
    end_text = end.strftime("%Y-%m-%d %H:%M:%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    if args.workers <= 1:
        for symbol in symbols:
            output = args.output_dir / f"{symbol.upper()}_5min.csv"
            if args.isolate_symbol_process and _should_skip_existing_output(
                output,
                force=args.force,
                min_existing_end_date=args.min_existing_end_date,
            ):
                print(f"{symbol} skipped: output exists at {output}", flush=True)
                continue
            fetch_kwargs = {
                "start_date": start_text,
                "end_date": end_text,
                "provider": args.provider,
                "min_rows": args.min_rows,
                "output_dir": args.output_dir,
                "force": args.force,
                "retries": args.retries,
                "retry_sleep": args.retry_sleep,
                "symbol_timeout_seconds": args.symbol_timeout_seconds,
                "min_existing_end_date": args.min_existing_end_date,
            }
            if args.isolate_symbol_process:
                ok, message = _fetch_one_isolated(symbol, fetch_kwargs=fetch_kwargs, hard_timeout_seconds=args.hard_timeout_seconds)
            else:
                ok, message = _fetch_one(symbol, **fetch_kwargs)
            print(message, flush=True)
            if not ok:
                failures += 1
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    _fetch_one,
                    symbol,
                    start_date=start_text,
                    end_date=end_text,
                    provider=args.provider,
                    min_rows=args.min_rows,
                    output_dir=args.output_dir,
                    force=args.force,
                    retries=args.retries,
                    retry_sleep=args.retry_sleep,
                    symbol_timeout_seconds=args.symbol_timeout_seconds,
                    min_existing_end_date=args.min_existing_end_date,
                ): symbol
                for symbol in symbols
            }
            for future in as_completed(futures):
                try:
                    ok, message = future.result()
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    message = f"{futures[future]} failed: {type(exc).__name__}: {exc}"
                print(message, flush=True)
                if not ok:
                    failures += 1
    return 1 if failures else 0


def _fetch_one_isolated(symbol: str, *, fetch_kwargs: dict[str, Any], hard_timeout_seconds: int) -> tuple[bool, str]:
    timeout = max(hard_timeout_seconds, 1)
    context = get_context("spawn")
    queue = context.Queue(maxsize=1)
    process = context.Process(target=_fetch_one_child, args=(queue, symbol, fetch_kwargs))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return False, f"{symbol} failed: isolated fetch timed out after {timeout}s"
    try:
        result = queue.get_nowait()
    except Empty:
        return False, f"{symbol} failed: isolated fetch exited without a result, exitcode={process.exitcode}"
    if not isinstance(result, tuple) or len(result) != 2:
        return False, f"{symbol} failed: isolated fetch returned an invalid result"
    ok, message = result
    return bool(ok), str(message)


def _fetch_one_child(queue: Any, symbol: str, fetch_kwargs: dict[str, Any]) -> None:
    queue.put(_fetch_one(symbol, **fetch_kwargs))


def _fetch_one(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    provider: str,
    min_rows: int,
    output_dir: Path,
    force: bool,
    retries: int,
    retry_sleep: float,
    symbol_timeout_seconds: int,
    min_existing_end_date: str | None,
) -> tuple[bool, str]:
    output = output_dir / f"{symbol.upper()}_5min.csv"
    if _should_skip_existing_output(output, force=force, min_existing_end_date=min_existing_end_date):
        return True, f"{symbol} skipped: output exists at {output}"
    failures: list[str] = []
    for attempt_index in range(max(retries, 0) + 1):
        try:
            with _symbol_timeout(symbol_timeout_seconds):
                result = fetch_a_share_5min_with_fallback(
                    symbol,
                    start_date=start_date,
                    end_date=end_date,
                    providers=None if provider in {"auto", "free", ""} else (provider,),
                    min_rows=min_rows,
                )
            result.bars.to_csv(output, index=False)
            attempts = ", ".join(
                f"{item.provider}:{'ok' if item.success else item.message}:{item.elapsed_seconds}s" for item in result.attempts
            )
            retry_note = f" retry={attempt_index}" if attempt_index else ""
            return (
                True,
                f"{symbol} rows={len(result.bars)} source={result.source} output={output}{retry_note} attempts=[{attempts}]",
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{type(exc).__name__}: {exc}")
            if attempt_index < retries:
                time.sleep(max(retry_sleep, 0.0))
    return False, f"{symbol} failed after {retries + 1} attempts: {' | '.join(failures)}"


def _should_skip_existing_output(output: Path, *, force: bool, min_existing_end_date: str | None) -> bool:
    if force or not output.exists():
        return False
    if not min_existing_end_date:
        return True
    try:
        import pandas as pd

        data = pd.read_csv(output, usecols=["timestamp"])
        if data.empty:
            return False
        latest = pd.to_datetime(data["timestamp"], errors="coerce").max()
        if pd.isna(latest):
            return False
        return latest.date() >= pd.Timestamp(min_existing_end_date).date()
    except Exception:
        return False


class _SymbolTimeout:
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        self.previous_handler: object | None = None

    def __enter__(self) -> None:
        if self.seconds <= 0 or not hasattr(signal, "SIGALRM"):
            return
        self.previous_handler = signal.signal(signal.SIGALRM, self._raise_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.seconds <= 0 or not hasattr(signal, "SIGALRM"):
            return
        signal.alarm(0)
        if self.previous_handler is not None:
            signal.signal(signal.SIGALRM, self.previous_handler)

    @staticmethod
    def _raise_timeout(signum: int, frame: object) -> None:
        raise TimeoutError("symbol fetch timed out")


def _symbol_timeout(seconds: int) -> _SymbolTimeout:
    return _SymbolTimeout(seconds)


if __name__ == "__main__":
    raise SystemExit(main())
