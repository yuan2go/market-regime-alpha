"""Read-only canonical reconciliation input for Backtest execution planning."""

from __future__ import annotations

from typing import Protocol

from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestRun,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionObservation,
    BacktestExpectedAction,
)


class BacktestExecutionObservationPort(Protocol):
    def observe(
        self,
        run: FrozenBacktestRun,
        expected_actions: tuple[BacktestExpectedAction, ...],
    ) -> tuple[BacktestActionObservation, ...]: ...


__all__ = ["BacktestExecutionObservationPort"]
