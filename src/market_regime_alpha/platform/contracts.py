"""Canonical research-platform domain contracts.

These contracts extend the existing V2 identities instead of creating a competing
Candidate, Feature, Target, or Experiment ontology. They define platform-level
objects needed to register theories and models, control lifecycle authority, and
bind model implementations to explicit research scopes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, ClassVar

from market_regime_alpha.core.identity import (
    FeatureDefinitionId,
    ModelId,
    StableId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.data.contracts import DataEligibility


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_unique(label: str, values: tuple[object, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicate values")


@dataclass(frozen=True, slots=True)
class TheoryId(StableId):
    """Identity of a versioned investment or market-behaviour theory."""


@dataclass(frozen=True, slots=True)
class ObservableId(StableId):
    """Identity of a theory-derived observable market phenomenon."""


@dataclass(frozen=True, slots=True)
class EvaluationProtocolId(StableId):
    """Identity of a versioned model evaluation protocol."""


@dataclass(frozen=True, slots=True)
class ResearchHypothesisId(StableId):
    """Identity of a falsifiable research hypothesis."""


@dataclass(frozen=True, slots=True)
class MetricId(StableId):
    """Identity of a versioned evaluation metric."""


class DefinitionStatus(str, Enum):
    """Maturity of a theory or observable definition."""

    CONCEPTUAL = "CONCEPTUAL"
    FORMALIZED = "FORMALIZED"
    IMPLEMENTED = "IMPLEMENTED"
    UNIT_VALIDATED = "UNIT_VALIDATED"
    EMPIRICALLY_TESTED = "EMPIRICALLY_TESTED"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class ModelRole(str, Enum):
    """Exclusive research responsibility owned by a model."""

    CONTEXT = "CONTEXT"
    CANDIDATE = "CANDIDATE"
    ENTRY = "ENTRY"
    HOLDING = "HOLDING"
    EXIT = "EXIT"
    PORTFOLIO = "PORTFOLIO"


class ModelLifecycleStatus(str, Enum):
    """Lifecycle state of a registered model version."""

    DRAFT = "DRAFT"
    RESEARCH = "RESEARCH"
    BACKTESTED = "BACKTESTED"
    OOS_VALIDATED = "OOS_VALIDATED"
    SHADOW = "SHADOW"
    PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class EvidenceLevel(str, Enum):
    """Highest class of claim supported by the evidence bound to a model."""

    UNQUALIFIED = "UNQUALIFIED"
    EXPLORATORY = "EXPLORATORY"
    REHEARSAL = "REHEARSAL"
    FORMAL_RESEARCH = "FORMAL_RESEARCH"
    SHADOW_EVIDENCE = "SHADOW_EVIDENCE"
    LIVE_OBSERVED = "LIVE_OBSERVED"


class PredictionDisposition(str, Enum):
    """Explicit outcome when a prediction scope cannot or should not emit a trade idea."""

    PREDICTION_AVAILABLE = "PREDICTION_AVAILABLE"
    NO_PREDICTION = "NO_PREDICTION"
    NO_TRADE = "NO_TRADE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DATA_BLOCKED = "DATA_BLOCKED"
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"


@dataclass(frozen=True, slots=True)
class TheoryDefinition:
    """Versioned formalization boundary for one investment theory."""

    SCHEMA_VERSION: ClassVar[str] = "theory-definition-v1"

    theory_id: TheoryId
    name: str
    version: str
    status: DefinitionStatus
    summary: str
    observable_ids: tuple[ObservableId, ...]
    source_references: tuple[str, ...]
    invalidation_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("version", self.version),
            ("summary", self.summary),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.status, DefinitionStatus):
            raise TypeError("status must be a DefinitionStatus")
        _require_unique("observable_ids", self.observable_ids)
        _require_unique("source_references", self.source_references)
        if not self.source_references:
            raise ValueError("source_references must not be empty")


@dataclass(frozen=True, slots=True)
class ObservableDefinition:
    """Quantifiable market phenomenon derived from one theory."""

    SCHEMA_VERSION: ClassVar[str] = "observable-definition-v1"

    observable_id: ObservableId
    theory_id: TheoryId
    name: str
    version: str
    status: DefinitionStatus
    observable_rule: str
    boundary_cases: tuple[str, ...]
    feature_ids: tuple[FeatureDefinitionId, ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("version", self.version),
            ("observable_rule", self.observable_rule),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.status, DefinitionStatus):
            raise TypeError("status must be a DefinitionStatus")
        _require_unique("boundary_cases", self.boundary_cases)
        _require_unique("feature_ids", self.feature_ids)
        if not self.boundary_cases:
            raise ValueError("boundary_cases must not be empty")
        if not self.feature_ids:
            raise ValueError("feature_ids must not be empty")


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """Immutable semantic definition of one model version.

    A model predicts or scores one declared role. It does not own final account
    allocation or execution. ``implementation_ref`` and ``parameter_hash`` bind the
    result-affecting implementation without embedding mutable code or parameters.
    """

    SCHEMA_VERSION: ClassVar[str] = "model-definition-v2"

    model_id: ModelId
    name: str
    version: str
    family: str
    role: ModelRole
    target_id: TargetId
    universe_id: UniverseId
    feature_ids: tuple[FeatureDefinitionId, ...]
    implementation_ref: str
    parameter_hash: str
    decision_time_convention: str
    horizon: str
    theory_ids: tuple[TheoryId, ...] = ()
    parent_model_id: ModelId | None = None
    supported_data_eligibilities: tuple[DataEligibility, ...] = (
        DataEligibility.EXPLORATORY,
    )
    compatibility_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("name", self.name),
            ("version", self.version),
            ("family", self.family),
            ("implementation_ref", self.implementation_ref),
            ("parameter_hash", self.parameter_hash),
            ("decision_time_convention", self.decision_time_convention),
            ("horizon", self.horizon),
        ):
            _require_non_empty(label, value)
        if not isinstance(self.role, ModelRole):
            raise TypeError("role must be a ModelRole")
        _require_unique("feature_ids", self.feature_ids)
        _require_unique("theory_ids", self.theory_ids)
        _require_unique(
            "supported_data_eligibilities",
            self.supported_data_eligibilities,
        )
        _require_unique("compatibility_refs", self.compatibility_refs)
        if not self.feature_ids and self.role is not ModelRole.CONTEXT:
            raise ValueError("non-context model requires at least one feature")
        if not self.supported_data_eligibilities:
            raise ValueError("supported_data_eligibilities must not be empty")
        for eligibility in self.supported_data_eligibilities:
            if not isinstance(eligibility, DataEligibility):
                raise TypeError(
                    "supported_data_eligibilities must contain DataEligibility values"
                )
        if self.parent_model_id == self.model_id:
            raise ValueError("model cannot be its own parent")

    def supports_data_eligibility(self, eligibility: DataEligibility) -> bool:
        """Return whether one input-data authority is declared compatible."""

        if not isinstance(eligibility, DataEligibility):
            raise TypeError("eligibility must be a DataEligibility")
        return eligibility in self.supported_data_eligibilities

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "model_id": str(self.model_id),
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "role": self.role.value,
            "target_id": str(self.target_id),
            "universe_id": str(self.universe_id),
            "feature_ids": [str(item) for item in self.feature_ids],
            "implementation_ref": self.implementation_ref,
            "parameter_hash": self.parameter_hash,
            "decision_time_convention": self.decision_time_convention,
            "horizon": self.horizon,
            "theory_ids": [str(item) for item in self.theory_ids],
            "parent_model_id": str(self.parent_model_id) if self.parent_model_id else None,
            "supported_data_eligibilities": [
                item.value for item in self.supported_data_eligibilities
            ],
            "compatibility_refs": list(self.compatibility_refs),
        }

    @property
    def definition_hash(self) -> str:
        canonical = json.dumps(self.canonical_payload(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()
