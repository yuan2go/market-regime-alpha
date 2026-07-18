#!/usr/bin/env python3
"""Run MR-1 from one immutable EXPLORATORY PRR Dataset without provider access."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_regime_alpha.research.mr1_research_runner import (  # noqa: E402
    DEFAULT_MR1_OUTPUT_ROOT,
    run_mr1_research,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_MR1_OUTPUT_ROOT)
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    final = run_mr1_research(
        dataset_path=args.dataset.resolve(),
        output_root=args.output_root.resolve(),
        top_k=args.top_k,
    )
    print(f"MR-1 completed: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
