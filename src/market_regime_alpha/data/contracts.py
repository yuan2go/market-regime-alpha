"""Canonical provider, source-artifact, and dataset contracts.

These contracts deliberately separate Provider, Source Artifact, Dataset, and Data
Eligibility. They do not fetch data or promote an existing adapter to formal authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId, DatasetId, ProviderId
from market_regime_alpha.core.time import RetrievedAt


class DataEligibility(str, Enum):
    """Canonical qualification of whether data may support a class of claim."""

    UNQUALIFIED = "UNQUALIFIED"
    EXPLORATORY = "EXPLORATORY"
    REHEARSAL = "REHEARSAL"
    FORMAL_RESEARCH = "FORMAL_RESEARCH"


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


@dataclass(frozen=True, slots=True)
class ProviderReference:
    """Reference to an identified provider product under a declared contract version."""

    provider_id: ProviderId
    product: str
    contract_version: str

    def __post_init__(self) -> None:
        _require_non_empty("product", self.product)
        _require_non_empty("contract_version", self.contract_version)


@dataclass(frozen=True, slots=True)
class SourceArtifactReference:
    """Reference to one exact retrieved source artifact."""

    artifact_id: ArtifactId
    provider_id: ProviderId
    retrieved_at: RetrievedAt
    content_hash: str
    locator: str

    def __post_init__(self) -> None:
        _require_non_empty("content_hash", self.content_hash)
        _require_non_empty("locator", self.locator)


@dataclass(frozen=True, slots=True)
class DatasetContract:
    """Canonical identity and eligibility declaration for a controlled dataset.

    This is intentionally not a replacement for every existing manifest schema. A
    concrete dataset builder or compatibility adapter may preserve richer local fields
    while exposing this canonical project boundary.
    """

    dataset_id: DatasetId
    schema_version: str
    eligibility: DataEligibility
    manifest_artifact_id: ArtifactId
    provider_references: tuple[ProviderReference, ...]
    pit_correct_for_scope: bool
    scope: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("schema_version", self.schema_version)
        _require_non_empty("scope", self.scope)
        if not isinstance(self.eligibility, DataEligibility):
            raise TypeError("eligibility must be a DataEligibility")
        if not isinstance(self.pit_correct_for_scope, bool):
            raise TypeError("pit_correct_for_scope must be boolean")
        if not self.provider_references:
            raise ValueError("provider_references must not be empty")
        keys = [
            (item.provider_id, item.product, item.contract_version)
            for item in self.provider_references
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("provider_references must not contain duplicates")
        if self.eligibility is DataEligibility.FORMAL_RESEARCH and not self.pit_correct_for_scope:
            raise ValueError("FORMAL_RESEARCH requires pit_correct_for_scope")
