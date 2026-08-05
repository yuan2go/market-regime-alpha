"""Explicit network smoke for the 20-symbol Tencent free-data operation.

This script is intentionally outside ordinary CI. It delegates to the production
CLI and therefore preserves PostgreSQL authority, immutable raw archives, and
fail-closed status semantics.
"""

from __future__ import annotations

from typing import Sequence

from market_regime_alpha.cli.free_data_operation import run_main


def main(argv: Sequence[str] | None = None) -> int:
    return run_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
