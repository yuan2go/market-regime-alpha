"""Private transactional Outcome acquisition contract for Evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutcomeAcquisitionResult:
    evaluation_run_id: UUID
    access_count: int
    observation_count: int
    input_roster_sha256: str


class TransactionalOutcomeAcquisition(Protocol):
    """Never exposes Outcome values; acquisition is valid only after UoW commit."""

    def acquire(self, evaluation_run_id: UUID) -> OutcomeAcquisitionResult: ...


__all__ = ["OutcomeAcquisitionResult", "TransactionalOutcomeAcquisition"]
