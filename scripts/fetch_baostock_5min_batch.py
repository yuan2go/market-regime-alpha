#!/usr/bin/env python3
"""Fetch A-share 5-minute bars from BaoStock with resumable batch semantics."""

from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
import signal
import socket
import sys
import threading
import time
from typing import Any, Callable, TypeVar

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import (  # noqa: E402
    baostock_credentials,
    normalize_baostock_minute_frame,
    to_baostock_code,
)
from market_regime_alpha.dividend_t.storage import load_watchlist  # noqa: E402


FIELDS = "date,time,code,open,high,low,close,volume,amount"
OUTPUT_COLUMNS = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "amount", "source_freq"]
CHECKPOINT_COLUMNS = ["updated_at", "symbol", "status", "mode", "rows", "start", "end", "fetch_start", "fetch_end", "message", "output"]
FAILURE_COLUMNS = ["symbol", "message"]
DEFAULT_LOGIN_TIMEOUT_SECONDS = 30.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 45.0
DEFAULT_SOCKET_TIMEOUT_SECONDS = 45.0
SESSION_CLOSE_TIME = "15:00:00"
T = TypeVar("T")


class BaoStockTimeoutError(TimeoutError):
    """Raised when a BaoStock socket call exceeds the configured timeout."""


@dataclass(frozen=True)
class FetchOutcome:
    status: str
    mode: str
    rows: int = 0
    start: str = "-"
    end: str = "-"
    fetch_start: str = "-"
    fetch_end: str = "-"
    message: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="*", help="Symbols such as 601939.SH.")
    parser.add_argument("--watchlist", type=Path)
    parser.add_argument("--days", type=int, default=735)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-rows", type=int, default=18_000)
    parser.add_argument("--chunk-days", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--mode", choices=["full", "incremental"], default="full", help="full rewrites each CSV; incremental only fetches missing dates.")
    parser.add_argument("--incremental", action="store_true", help="Alias for --mode incremental.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-existing-end-date")
    parser.add_argument("--failures", type=Path)
    parser.add_argument("--append-failures", action="store_true", help="Append to --failures instead of replacing it at startup.")
    parser.add_argument("--checkpoint", type=Path, help="CSV event log used for resumable batch runs. Defaults inside --output-dir.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint-based resume skips. Existing CSV skip checks still apply.")
    parser.add_argument("--login-timeout", type=float, default=DEFAULT_LOGIN_TIMEOUT_SECONDS, help="Seconds before a BaoStock login attempt is interrupted. 0 disables.")
    parser.add_argument("--request-timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS, help="Seconds before one BaoStock query/iteration is interrupted. 0 disables.")
    parser.add_argument("--socket-timeout", type=float, default=DEFAULT_SOCKET_TIMEOUT_SECONDS, help="Default socket timeout for BaoStock connections. 0 disables.")
    parser.add_argument("--max-consecutive-failures", type=int, default=20, help="Abort after this many consecutive symbol/login failures. 0 disables.")
    parser.add_argument(
        "--relogin-after-failure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reset the BaoStock session after a failed symbol fetch.",
    )
    args = parser.parse_args()
    if args.incremental:
        args.mode = "incremental"

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
    start_date = start.date().isoformat()
    end_date = end.date().isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.checkpoint or args.output_dir / ".fetch_baostock_5min_batch_checkpoint.csv"
    checkpoint = {} if args.no_resume else _load_checkpoint(checkpoint_path)
    if args.failures and not args.append_failures:
        _initialize_csv(args.failures, FAILURE_COLUMNS)
    if args.socket_timeout > 0:
        socket.setdefaulttimeout(args.socket_timeout)

    try:
        import baostock as bs
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install baostock.") from exc

    user_id, password = baostock_credentials()
    failures: list[tuple[str, str]] = []
    success = 0
    skipped = 0
    consecutive_failures = 0
    aborted = False
    session_active = False

    def ensure_login() -> None:
        nonlocal session_active
        if session_active:
            return
        login = _call_with_timeout(
            "BaoStock login",
            args.login_timeout,
            _silent_call,
            bs.login,
            user_id=user_id,
            password=password,
        )
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
        session_active = True

    def reset_session() -> None:
        nonlocal session_active
        if session_active:
            _safe_logout(bs, timeout_seconds=args.login_timeout)
        session_active = False

    try:
        for index, symbol in enumerate(symbols, start=1):
            output = args.output_dir / f"{symbol}_5min.csv"
            target_resume_date = args.min_existing_end_date or (end_date if args.mode == "incremental" else None)
            existing = _read_existing_bars(output)
            if _should_skip_existing_frame(
                existing,
                force=args.force,
                min_existing_end_date=args.min_existing_end_date,
                mode=args.mode,
                target_end_date=end_date,
            ):
                skipped += 1
                outcome = _existing_skip_outcome(output, existing=existing, mode=args.mode, message="existing output is current")
                _append_checkpoint(checkpoint_path, symbol=symbol, outcome=outcome, output=output)
                print(f"[{index}/{len(symbols)}] {symbol} skipped rows={outcome.rows} end={outcome.end}", flush=True)
                continue
            if not args.no_resume and _checkpoint_can_skip(checkpoint.get(symbol), output, target_end_date=target_resume_date):
                skipped += 1
                outcome = _existing_skip_outcome(output, mode=args.mode, message="checkpoint resume skip")
                _append_checkpoint(checkpoint_path, symbol=symbol, outcome=outcome, output=output)
                print(f"[{index}/{len(symbols)}] {symbol} skipped checkpoint rows={outcome.rows} end={outcome.end}", flush=True)
                continue
            try:
                ensure_login()
                outcome = _fetch_symbol(
                    bs=bs,
                    symbol=symbol,
                    output=output,
                    start_date=start_date,
                    end_date=end_date,
                    min_existing_end_date=args.min_existing_end_date,
                    mode=args.mode,
                    force=args.force,
                    min_rows=args.min_rows,
                    chunk_days=args.chunk_days,
                    request_timeout=args.request_timeout,
                )
                _append_checkpoint(checkpoint_path, symbol=symbol, outcome=outcome, output=output)
                if outcome.status == "skipped":
                    skipped += 1
                    print(f"[{index}/{len(symbols)}] {symbol} skipped rows={outcome.rows} end={outcome.end}", flush=True)
                else:
                    success += 1
                    print(
                        f"[{index}/{len(symbols)}] {symbol} rows={outcome.rows} end={outcome.end} "
                        f"mode={outcome.mode} fetch={outcome.fetch_start}..{outcome.fetch_end} output={output}",
                        flush=True,
                    )
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                message = f"{type(exc).__name__}: {exc}"
                failures.append((symbol, message))
                _append_failure(args.failures, symbol=symbol, message=message)
                _append_checkpoint(
                    checkpoint_path,
                    symbol=symbol,
                    outcome=FetchOutcome(status="failed", mode=args.mode, message=message),
                    output=output,
                )
                print(f"[{index}/{len(symbols)}] {symbol} failed: {message}", flush=True)
                consecutive_failures += 1
                if args.relogin_after_failure:
                    reset_session()
                if args.max_consecutive_failures > 0 and consecutive_failures >= args.max_consecutive_failures:
                    aborted = True
                    print(f"aborting after {consecutive_failures} consecutive failures", flush=True)
                    break
            if args.sleep > 0:
                time.sleep(args.sleep)
    finally:
        reset_session()

    print(
        f"done success={success} skipped={skipped} failed={len(failures)} aborted={aborted} "
        f"mode={args.mode} output_dir={args.output_dir} checkpoint={checkpoint_path}"
    )
    return 2 if aborted else (1 if failures else 0)


def _fetch_symbol(
    bs: object,
    symbol: str,
    *,
    output: Path,
    start_date: str,
    end_date: str,
    min_existing_end_date: str | None,
    mode: str,
    force: bool,
    min_rows: int,
    chunk_days: int,
    request_timeout: float,
) -> FetchOutcome:
    existing = _read_existing_bars(output)
    if _should_skip_existing_frame(
        existing,
        force=force,
        min_existing_end_date=min_existing_end_date,
        mode=mode,
        target_end_date=end_date,
    ):
        return _existing_skip_outcome(output, existing=existing, mode=mode, message="existing output is current")

    fetch_start = start_date
    write_mode = "full"
    if mode == "incremental" and existing is not None and not existing.empty and not force:
        latest = _latest_timestamp(existing)
        if latest is not None:
            fetch_start = _incremental_fetch_start_date(latest, end_date)
            write_mode = "incremental"

    frame = _query_symbol(
        bs,
        symbol,
        start_date=fetch_start,
        end_date=end_date,
        chunk_days=chunk_days,
        request_timeout=request_timeout,
    )
    if frame.empty and write_mode == "incremental" and existing is not None and len(existing) >= min_rows:
        return _existing_skip_outcome(output, existing=existing, mode=write_mode, message="incremental query returned no new rows")

    normalized = normalize_baostock_minute_frame(frame, symbol=symbol, source_freq="5min")
    output_frame = _merge_incremental_bars(existing, normalized) if write_mode == "incremental" and existing is not None else normalized
    if len(output_frame) < min_rows:
        raise RuntimeError(f"only {len(output_frame)} rows returned; need at least {min_rows}")
    output_frame.to_csv(output, index=False)
    return FetchOutcome(
        status="success",
        mode=write_mode,
        rows=len(output_frame),
        start=str(output_frame["timestamp"].iloc[0]),
        end=str(output_frame["timestamp"].iloc[-1]),
        fetch_start=fetch_start,
        fetch_end=end_date,
    )


def _query_symbol(
    bs: object,
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    chunk_days: int,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _date_chunks(start_date, end_date, chunk_days=chunk_days):
        rs = _call_with_timeout(
            f"{symbol} query {chunk_start}..{chunk_end}",
            request_timeout,
            bs.query_history_k_data_plus,
            to_baostock_code(symbol),
            FIELDS,
            start_date=chunk_start,
            end_date=chunk_end,
            frequency="5",
            adjustflag="3",
        )
        if getattr(rs, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock minute query failed: {rs.error_msg}")
        rows: list[list[str]] = []
        while rs.next():
            row = _call_with_timeout(f"{symbol} read row {chunk_start}..{chunk_end}", request_timeout, rs.get_row_data)
            rows.append(row)
        frames.append(pd.DataFrame(rows, columns=rs.fields))
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["date", "time", "code"], keep="last")
    return frame


def _date_chunks(start_date: str, end_date: str, *, chunk_days: int) -> list[tuple[str, str]]:
    start = pd.Timestamp(start_date).date()
    end = pd.Timestamp(end_date).date()
    step = timedelta(days=max(1, chunk_days) - 1)
    ranges: list[tuple[str, str]] = []
    current = start
    while current <= end:
        chunk_end = min(current + step, end)
        ranges.append((current.isoformat(), chunk_end.isoformat()))
        current = chunk_end + timedelta(days=1)
    return ranges


def _should_skip_existing_output(output: Path, *, force: bool, min_existing_end_date: str | None) -> bool:
    existing = _read_existing_bars(output)
    return _should_skip_existing_frame(existing, force=force, min_existing_end_date=min_existing_end_date, mode="full", target_end_date=None)


def _should_skip_existing_frame(
    existing: pd.DataFrame | None,
    *,
    force: bool,
    min_existing_end_date: str | None,
    mode: str,
    target_end_date: str | None,
) -> bool:
    if force or existing is None or existing.empty:
        return False
    if not min_existing_end_date:
        if mode == "incremental" and target_end_date:
            min_existing_end_date = target_end_date
        else:
            return True
    try:
        latest = _latest_timestamp(existing)
        if latest is None:
            return False
        return latest.date() >= pd.Timestamp(min_existing_end_date).date()
    except Exception:
        return False


def _read_existing_bars(output: Path) -> pd.DataFrame | None:
    if not output.exists():
        return None
    try:
        data = pd.read_csv(output)
    except Exception:
        return None
    if data.empty or "timestamp" not in data.columns:
        return None
    return data


def _existing_skip_outcome(
    output: Path,
    *,
    existing: pd.DataFrame | None = None,
    mode: str,
    message: str,
) -> FetchOutcome:
    data = existing if existing is not None else _read_existing_bars(output)
    if data is None or data.empty:
        return FetchOutcome(status="skipped", mode=mode, message=message)
    return FetchOutcome(
        status="skipped",
        mode=mode,
        rows=len(data),
        start=str(data["timestamp"].iloc[0]),
        end=str(data["timestamp"].iloc[-1]),
        message=message,
    )


def _latest_timestamp(data: pd.DataFrame) -> pd.Timestamp | None:
    times = pd.to_datetime(data["timestamp"], errors="coerce")
    latest = times.max()
    if pd.isna(latest):
        return None
    return pd.Timestamp(latest)


def _incremental_fetch_start_date(latest: pd.Timestamp, end_date: str) -> str:
    end = pd.Timestamp(end_date).date()
    latest_date = latest.date()
    if latest_date >= end:
        return latest_date.isoformat()
    if latest.strftime("%H:%M:%S") >= SESSION_CLOSE_TIME:
        return (latest_date + timedelta(days=1)).isoformat()
    return latest_date.isoformat()


def _merge_incremental_bars(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([existing.loc[:, OUTPUT_COLUMNS], incoming.loc[:, OUTPUT_COLUMNS]], ignore_index=True)
    merged["timestamp"] = merged["timestamp"].astype(str)
    merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
    return merged.sort_values("timestamp").reset_index(drop=True).loc[:, OUTPUT_COLUMNS]


def _load_checkpoint(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return {}
    if frame.empty or "symbol" not in frame.columns:
        return {}
    latest: dict[str, dict[str, str]] = {}
    for row in frame.to_dict("records"):
        symbol = str(row.get("symbol", "")).upper()
        if symbol:
            latest[symbol] = {str(key): str(value) for key, value in row.items()}
    return latest


def _checkpoint_can_skip(row: dict[str, str] | None, output: Path, *, target_end_date: str | None) -> bool:
    if not row or row.get("status") != "success" or not target_end_date:
        return False
    existing = _read_existing_bars(output)
    if existing is None or existing.empty:
        return False
    latest = _latest_timestamp(existing)
    if latest is None:
        return False
    return latest.date() >= pd.Timestamp(target_end_date).date()


def _append_checkpoint(path: Path, *, symbol: str, outcome: FetchOutcome, output: Path) -> None:
    _append_csv_row(
        path,
        CHECKPOINT_COLUMNS,
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "status": outcome.status,
            "mode": outcome.mode,
            "rows": outcome.rows,
            "start": outcome.start,
            "end": outcome.end,
            "fetch_start": outcome.fetch_start,
            "fetch_end": outcome.fetch_end,
            "message": outcome.message,
            "output": str(output),
        },
    )


def _append_failure(path: Path | None, *, symbol: str, message: str) -> None:
    if path is None:
        return
    _append_csv_row(path, FAILURE_COLUMNS, {"symbol": symbol, "message": message})


def _initialize_csv(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()


def _append_csv_row(path: Path, columns: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if write_header:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in columns})


def _safe_logout(bs: object, *, timeout_seconds: float) -> None:
    try:
        _call_with_timeout("BaoStock logout", timeout_seconds, _silent_call, bs.logout)
    except Exception:
        pass


def _silent_call(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    with redirect_stdout(StringIO()):
        return func(*args, **kwargs)


def _call_with_timeout(label: str, timeout_seconds: float, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    with _timeout_guard(label, timeout_seconds):
        return func(*args, **kwargs)


@contextmanager
def _timeout_guard(label: str, timeout_seconds: float):
    if timeout_seconds <= 0 or threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        yield
        return

    def _raise_timeout(_signum: int, _frame: object) -> None:
        raise BaoStockTimeoutError(f"{label} timed out after {timeout_seconds:g}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
