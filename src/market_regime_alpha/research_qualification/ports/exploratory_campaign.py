"""Read-only exact completion projection for an exploratory campaign."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CompletedExploratoryCampaign:
    exploratory_backtest_run_id: UUID
    fit_dataset_id: UUID
    fit_decision_run_id: UUID
    fit_evaluation_run_id: UUID
    model_version_id: UUID
    validation_dataset_ids: tuple[UUID, ...]
    validation_decision_run_ids: tuple[UUID, ...]
    validation_evaluation_run_id: UUID


class ExploratoryCampaignReadPort(Protocol):
    def completed(
        self,
        exploratory_backtest_run_id: UUID,
        *,
        expected_definition_sha256: str,
    ) -> CompletedExploratoryCampaign | None: ...


__all__ = ["CompletedExploratoryCampaign", "ExploratoryCampaignReadPort"]
