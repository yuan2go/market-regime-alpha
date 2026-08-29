"""Selection-owned immutable inputs to Candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


class CandidateCellStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class CandidateArtifactBinding:
    artifact_id: UUID
    content_sha256: ContentHash | str
    size_bytes: int

    def __post_init__(self) -> None:
        content_hash = (
            self.content_sha256
            if isinstance(self.content_sha256, ContentHash)
            else ContentHash(self.content_sha256)
        )
        object.__setattr__(self, "content_sha256", content_hash)
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("Artifact size_bytes must be non-negative")


@dataclass(frozen=True, slots=True)
class CandidatePopulationCell:
    feature_definition_id: UUID
    status: CandidateCellStatus
    value: Decimal | int | None
    reason_code: str
    cell_source_lineage_hash: ContentHash | str

    def __post_init__(self) -> None:
        if not isinstance(self.status, CandidateCellStatus):
            raise TypeError("status must be CandidateCellStatus")
        lineage_hash = (
            self.cell_source_lineage_hash
            if isinstance(self.cell_source_lineage_hash, ContentHash)
            else ContentHash(self.cell_source_lineage_hash)
        )
        object.__setattr__(self, "cell_source_lineage_hash", lineage_hash)
        if not self.reason_code:
            raise ValueError("Candidate cell reason_code is required")
        if self.status is CandidateCellStatus.AVAILABLE:
            if isinstance(self.value, bool) or not isinstance(
                self.value,
                (Decimal, int),
            ):
                raise TypeError(
                    "AVAILABLE Candidate cells require Decimal or integer values"
                )
            if isinstance(self.value, Decimal) and not self.value.is_finite():
                raise ValueError("AVAILABLE Candidate Decimal values must be finite")
        elif self.value is not None:
            raise ValueError("unavailable Candidate cells cannot carry a value")


@dataclass(frozen=True, slots=True)
class CandidatePopulationRow:
    instrument_id: UUID
    dataset_population_source_id: UUID
    cells: tuple[CandidatePopulationCell, ...]

    def __post_init__(self) -> None:
        feature_ids = [item.feature_definition_id for item in self.cells]
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("Candidate row Feature cells must be unique")

    @property
    def population_source_id(self) -> UUID:
        return self.dataset_population_source_id


@dataclass(frozen=True, slots=True)
class CandidateDatasetPopulation:
    dataset_id: UUID
    dataset_content_sha256: ContentHash | str
    decision_time: DecisionTime
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    rows: tuple[CandidatePopulationRow, ...]
    dependency_sha256: ContentHash | str | None = None

    def __post_init__(self) -> None:
        dataset_hash = (
            self.dataset_content_sha256
            if isinstance(self.dataset_content_sha256, ContentHash)
            else ContentHash(self.dataset_content_sha256)
        )
        object.__setattr__(self, "dataset_content_sha256", dataset_hash)
        if not isinstance(self.decision_time, DecisionTime):
            raise TypeError("decision_time must be DecisionTime")
        dependency_hash = self.dependency_sha256
        if dependency_hash is None:
            dependency_hash = dataset_hash
        elif not isinstance(dependency_hash, ContentHash):
            dependency_hash = ContentHash(dependency_hash)
        object.__setattr__(self, "dependency_sha256", dependency_hash)
        instruments = [item.instrument_id for item in self.rows]
        population_sources = [
            item.dataset_population_source_id for item in self.rows
        ]
        if len(set(instruments)) != len(instruments):
            raise ValueError("Candidate population instruments must be unique")
        if len(set(population_sources)) != len(population_sources):
            raise ValueError("Candidate population sources must be unique")

    @property
    def row_count(self) -> int:
        return len(self.rows)


__all__ = [
    "CandidateArtifactBinding",
    "CandidateCellStatus",
    "CandidateDatasetPopulation",
    "CandidatePopulationCell",
    "CandidatePopulationRow",
]
