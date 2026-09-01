"""Narrow read-only verifier port owned by Research & Qualification."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.verification import (
    ResearchVerificationMismatch,
)


class ResearchEvaluationVerificationProvider(Protocol):
    def inspect_partition(
        self, research_partition_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...

    def inspect_experiment(
        self, experiment_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...

    def inspect_evaluation_run(
        self, evaluation_run_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...


__all__ = ["ResearchEvaluationVerificationProvider"]
