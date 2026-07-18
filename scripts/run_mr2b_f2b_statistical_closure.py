#!/usr/bin/env python3
"""Run frozen MR-2B F2B directional statistical closure from verified evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_regime_alpha.research.mr2b_f2b_artifacts import (  # noqa: E402
    DEFAULT_F2B_OUTPUT_ROOT,
    run_f2b_research,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mr1-run", type=Path, required=True)
    parser.add_argument("--f2a-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_F2B_OUTPUT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    final = run_f2b_research(
        dataset_path=args.dataset.resolve(), mr1_run_path=args.mr1_run.resolve(),
        f2a_run_path=args.f2a_run.resolve(), output_root=args.output_root.resolve(),
        runner_path=Path(__file__).resolve(),
    )
    print(f"MR-2B F2B completed: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
