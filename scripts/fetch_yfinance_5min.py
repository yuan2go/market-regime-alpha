#!/usr/bin/env python3
"""Fetch one symbol's recent 5-minute bars from yfinance and write CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import YFinanceADataProvider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch yfinance 5-minute bars for one A-share symbol.")
    parser.add_argument("symbol")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--period", default="60d")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()

    bars = YFinanceADataProvider(period=args.period, timeout_seconds=args.timeout_seconds).minute_bars(args.symbol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(args.output, index=False)
    print(f"{args.symbol} rows={len(bars)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
