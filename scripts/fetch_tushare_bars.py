#!/usr/bin/env python3
"""Fetch Tushare A-share bars and save normalized CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.tushare_client import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    build_tushare_client,
    normalize_ts_code,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("daily", "minute"), help="bar type to fetch")
    parser.add_argument("symbol", help="A-share code, for example 600000.SH or 000001")
    parser.add_argument("--start", help="daily: YYYYMMDD; minute: YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--end", help="daily: YYYYMMDD; minute: YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--freq", default="1min", help="minute freq: 1min, 5min, 15min, 30min, 60min")
    parser.add_argument("--output", type=Path, help="output CSV path")
    parser.add_argument("--no-cache", action="store_true", help="force a fresh Tushare request")
    args = parser.parse_args()

    client = build_tushare_client()
    if args.kind == "daily":
        frame = client.daily_bars(args.symbol, start_date=args.start, end_date=args.end, use_cache=not args.no_cache)
    else:
        frame = client.minute_bars(
            args.symbol,
            freq=args.freq,
            start_date=args.start,
            end_date=args.end,
            use_cache=not args.no_cache,
        )

    output = args.output or _default_output(args.kind, args.symbol, args.start, args.end, args.freq)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(f"Saved {len(frame)} rows to {output}")
    print(frame.head(10).to_string(index=False))
    return 0


def _default_output(kind: str, symbol: str, start: str | None, end: str | None, freq: str) -> Path:
    code = normalize_ts_code(symbol).replace(".", "_")
    start_part = _clean_part(start or "start")
    end_part = _clean_part(end or "end")
    suffix = "daily" if kind == "daily" else freq
    return DEFAULT_CACHE_DIR / "manual" / f"{code}_{suffix}_{start_part}_{end_part}.csv"


def _clean_part(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum()) or "none"


if __name__ == "__main__":
    raise SystemExit(main())

