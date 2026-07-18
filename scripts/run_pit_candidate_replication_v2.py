#!/usr/bin/env python3
"""Run sealed PIT Candidate replication v2 or publish a truthful provider blocker."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from market_regime_alpha.research.pit_replication_success_v2_runner import (
    run_pit_replication_success_v2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "pit_candidate_replication"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xuntou-bundle", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--partition-id")
    parser.add_argument("--partition-start", type=date.fromisoformat)
    parser.add_argument("--partition-end", type=date.fromisoformat)
    args = parser.parse_args()
    final = run_pit_replication_success_v2(
        xuntou_bundle=args.xuntou_bundle,
        output_root=args.output_root,
        partition_id=args.partition_id,
        partition_start=args.partition_start,
        partition_end=args.partition_end,
    )
    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
