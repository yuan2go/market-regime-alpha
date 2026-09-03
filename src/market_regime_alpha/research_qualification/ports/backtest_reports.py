"""Read-only canonical inputs and derived Artifact outputs for Backtest reports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestReportSource,
)


class BacktestReportSourcePort(Protocol):
    """Build a reconciled projection without reading raw Market bars."""

    def load(self, exploratory_backtest_run_id: UUID) -> BacktestReportSource: ...


__all__ = ["BacktestReportSourcePort"]
