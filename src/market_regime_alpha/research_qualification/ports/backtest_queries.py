"""Read-only generic Backtest projection contract."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestRun,
)


class BacktestQueryPort(Protocol):
    def load(self, exploratory_backtest_run_id: UUID) -> FrozenBacktestRun: ...


__all__ = ["BacktestQueryPort"]
