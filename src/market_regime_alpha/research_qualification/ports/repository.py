"""Research Definition aggregate persistence port."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain import (
    DatasetSource,
    DecisionInputDatasetDefinition,
    DecisionInputDatasetManifest,
    FeatureDefinition,
)


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    dataset_id: UUID
    version: int
    content_sha256: str
    row_count: int
    feature_count: int
    source_count: int
    cell_count: int
    available_cell_count: int
    missing_cell_count: int
    unknown_cell_count: int
    stale_cell_count: int
    conflict_cell_count: int


class ResearchDefinitionRepository(Protocol):
    def insert_feature_definition(self, definition: FeatureDefinition) -> int: ...

    def feature_definitions(
        self,
        feature_definition_ids: tuple[UUID, ...],
        *,
        lock: bool,
    ) -> tuple[FeatureDefinition, ...]: ...

    def insert_dataset(
        self,
        definition: DecisionInputDatasetDefinition,
        manifest: DecisionInputDatasetManifest,
    ) -> int: ...

    def dataset_record(self, dataset_id: UUID, *, lock: bool) -> DatasetRecord: ...

    def dataset_sources(
        self,
        dataset_id: UUID,
        *,
        lock: bool,
    ) -> tuple[DatasetSource, ...]: ...


__all__ = ["DatasetRecord", "ResearchDefinitionRepository"]
