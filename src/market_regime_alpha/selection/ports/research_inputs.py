"""Selection-owned DTOs for the narrow Research Definition input seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from market_regime_alpha.runtime.ports import ByteVerification
from market_regime_alpha.selection.ports.candidate_artifacts import (
    CandidateArtifactBinding,
)
from market_regime_alpha.shared.time import DecisionTime

if TYPE_CHECKING:
    from market_regime_alpha.selection.domain.candidate_inputs import (
        CandidatePopulationRow,
    )


@dataclass(frozen=True, slots=True)
class CandidateFeatureDependency:
    feature_definition_id: UUID
    content_sha256: str
    value_type: str


@dataclass(frozen=True, slots=True)
class CandidateDatasetDependency:
    dataset_id: UUID
    content_sha256: str
    decision_time: DecisionTime
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    row_count: int
    feature_count: int
    source_count: int
    cell_count: int
    available_cell_count: int
    missing_cell_count: int
    unknown_cell_count: int
    stale_cell_count: int
    conflict_cell_count: int
    dataset_source_lineage_sha256: str
    manifest_artifact: CandidateArtifactBinding
    code_artifact: CandidateArtifactBinding
    config_artifact: CandidateArtifactBinding


@dataclass(frozen=True, slots=True)
class CandidatePopulationDependency:
    population_dataset_source_id: UUID
    instrument_id: UUID


@dataclass(frozen=True, slots=True)
class CandidateResearchDependencySnapshot:
    dataset: CandidateDatasetDependency
    features: tuple[CandidateFeatureDependency, ...]
    population: tuple[CandidatePopulationDependency, ...]
    dependency_sha256: str


@dataclass(frozen=True, slots=True)
class CandidatePreparedResearchInput:
    dataset: CandidateDatasetDependency
    features: tuple[CandidateFeatureDependency, ...]
    population: tuple[CandidatePopulationDependency, ...]
    rows: tuple[CandidatePopulationRow, ...]
    manifest_verification: ByteVerification
    dependency_sha256: str


class CandidateResearchInputLoader(Protocol):
    def prepare(
        self,
        *,
        dataset_id: UUID,
        required_features: tuple[CandidateFeatureDependency, ...],
    ) -> CandidatePreparedResearchInput: ...


class CandidateResearchDependencyQueries(Protocol):
    def feature_dependencies(
        self,
        required_features: tuple[CandidateFeatureDependency, ...],
        *,
        lock: bool,
    ) -> tuple[CandidateFeatureDependency, ...]: ...

    def snapshot(
        self,
        *,
        dataset_id: UUID,
        required_features: tuple[CandidateFeatureDependency, ...],
        lock: bool,
    ) -> CandidateResearchDependencySnapshot: ...


__all__ = [
    "CandidateDatasetDependency",
    "CandidateFeatureDependency",
    "CandidatePopulationDependency",
    "CandidatePreparedResearchInput",
    "CandidateResearchDependencyQueries",
    "CandidateResearchDependencySnapshot",
    "CandidateResearchInputLoader",
]
