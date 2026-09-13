"""Read-only inputs for bounded source sensitivity, without new Forecast facts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain import DecisionInputDatasetManifest
from market_regime_alpha.research_qualification.ports.model_execution import FrozenModelVersionPayload


@dataclass(frozen=True, slots=True)
class SourceComparisonModel:
    model_version_id: UUID
    content_sha256: str
    target_id: UUID
    last_fit_decision: datetime
    last_fit_label_cutoff: datetime
    payload: FrozenModelVersionPayload


class SourceComparisonInputs(Protocol):
    def dataset(self, dataset_id: UUID) -> DecisionInputDatasetManifest: ...

    def model(self, model_version_id: UUID) -> SourceComparisonModel: ...

    def bars(self, dataset_ids: tuple[UUID, ...], outcome_ids: tuple[UUID, ...]) -> tuple[dict, ...]: ...
