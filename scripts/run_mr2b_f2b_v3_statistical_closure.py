#!/usr/bin/env python3
"""Run the immutable coverage-first MR-2B F2B v3 closure."""

from __future__ import annotations

import argparse
from pathlib import Path

from market_regime_alpha.research.mr2b_f2b_v3_artifacts import run_f2b_v3_research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mr1-run", type=Path, required=True)
    parser.add_argument("--f2a-run", type=Path, required=True)
    parser.add_argument("--f2b-v2-run", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/processed/mr2b_f2b_statistical_closure"),
    )
    args = parser.parse_args()
    final = run_f2b_v3_research(
        dataset_path=args.dataset,
        mr1_run_path=args.mr1_run,
        f2a_run_path=args.f2a_run,
        f2b_v2_run_path=args.f2b_v2_run,
        output_root=args.output_root,
        runner_path=Path(__file__).resolve(),
    )
    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
