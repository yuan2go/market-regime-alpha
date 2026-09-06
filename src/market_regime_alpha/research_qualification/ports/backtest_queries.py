"""Read-only generic Backtest projection contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    FrozenBacktestRun,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.backtest_execution import BacktestExecutionState


@dataclass(frozen=True, slots=True)
class BacktestAuthoritySnapshot:
    """Read-only projection; never an identity, FK target, or business Authority."""

    run: FrozenBacktestRun
    artifact_bindings: tuple[ArtifactBinding, ...]


@dataclass(frozen=True, slots=True)
class BacktestReplayVerification:
    exploratory_backtest_run_id: UUID
    matched: bool
    mismatch_codes: tuple[str, ...]
    source: str | None
    definition_sha256: str | None
    execution_state: BacktestExecutionState | None = None

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatch_codes)

    @property
    def integrity_mismatch_codes(self) -> tuple[str, ...]:
        """Incomplete execution is preserved evidence, not successful replay."""
        if self.execution_state in {
            BacktestExecutionState.PLANNED, BacktestExecutionState.RUNNING,
            BacktestExecutionState.FAILED,
        }:
            return tuple(code for code in self.mismatch_codes
                         if code != f"EXECUTION:{self.execution_state.value}")
        return self.mismatch_codes


class BacktestQueryPort(Protocol):
    def load(self, exploratory_backtest_run_id: UUID) -> FrozenBacktestRun: ...


class BacktestAuthorityQueryPort(Protocol):
    def load(self, exploratory_backtest_run_id: UUID) -> BacktestAuthoritySnapshot: ...


class BacktestArtifactByteReader(Protocol):
    def read_bytes(self, content_sha256: str, *, expected_size: int) -> bytes: ...


__all__ = [
    "BacktestArtifactByteReader",
    "BacktestAuthorityQueryPort",
    "BacktestAuthoritySnapshot",
    "BacktestQueryPort",
    "BacktestReplayVerification",
]
