#!/usr/bin/env python3
"""Publish PIT Candidate replication evidence or an explicit provider blocker."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from market_regime_alpha.research.pit_replication_runner import run_pit_replication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "processed" / "pit_candidate_replication"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xuntou-bundle", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    final = run_pit_replication(
        xuntou_bundle=args.xuntou_bundle,
        output_root=args.output_root,
        code_revision=_revision(),
    )
    print(final)
    return 0


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
