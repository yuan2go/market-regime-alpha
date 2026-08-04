#!/usr/bin/env python3
"""Compatibility entry point for the canonical H4.5 manual-only CLI."""

from market_regime_alpha.cli.create_manual_trade_from_risk_decision import (
    build_parser,
    main,
)


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
