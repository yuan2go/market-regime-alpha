"""Read-only canonical inputs and derived Artifact outputs for Backtest reports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest_report import (
    BacktestReportArtifactBinding,
    BacktestReportSource,
)
from market_regime_alpha.runtime.application import CommandContext
from market_regime_alpha.runtime.ports import ArtifactRecord


class BacktestReportSourcePort(Protocol):
    """Build a reconciled projection without reading raw Market bars."""

    def load(self, exploratory_backtest_run_id: UUID) -> BacktestReportSource: ...


class BacktestReportArtifactPublisher(Protocol):
    def publish(
        self,
        content: bytes,
        *,
        media_type: str,
        context: CommandContext,
    ) -> ArtifactRecord: ...


class BacktestReportBindingWriter(Protocol):
    def bind_report(
        self,
        binding: BacktestReportArtifactBinding,
        context: CommandContext,
    ) -> object: ...


__all__ = [
    "BacktestReportArtifactPublisher",
    "BacktestReportBindingWriter",
    "BacktestReportSourcePort",
]
