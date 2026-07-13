#!/usr/bin/env python3
"""Write a sealed-test-free non-empty MACD event rehearsal artifact."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.macd_event_rehearsal import write_controlled_event_rehearsal  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a controlled non-empty MACD REHEARSAL artifact.")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "macd_oos" / "rehearsal",
    )
    parser.add_argument("--run-id", help="Immutable run ID. Defaults to a timestamped rehearsal ID.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"event-rehearsal-{datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%z')}"
    artifact = write_controlled_event_rehearsal(args.artifact_root, run_id=run_id)
    print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
