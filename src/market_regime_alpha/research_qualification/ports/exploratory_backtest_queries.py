"""Read-only exploratory backtest reconciliation port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExploratoryBacktestVerification:
    exploratory_backtest_run_id: UUID
    matched: bool
    mismatch_codes: tuple[str, ...]

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatch_codes)


class ExploratoryBacktestVerificationPort(Protocol):
    def verify(
        self,
        exploratory_backtest_run_id: UUID,
    ) -> ExploratoryBacktestVerification: ...


__all__ = [
    "ExploratoryBacktestVerification",
    "ExploratoryBacktestVerificationPort",
]
