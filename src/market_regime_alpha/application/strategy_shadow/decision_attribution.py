"""Structured non-causal decision attribution and manual research feedback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ResearchExperimentDefinition,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


class AttributionDimension(str, Enum):
    MARKET_REGIME = "MARKET_REGIME"
    ETF_CONTEXT = "ETF_CONTEXT"
    THEME = "THEME"
    CAPITAL_PROXY = "CAPITAL_PROXY"
    CANDIDATE_RANK = "CANDIDATE_RANK"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"
    ENTRY = "ENTRY"
    HOLDING = "HOLDING"
    EXIT = "EXIT"
    COST = "COST"
    LIQUIDITY = "LIQUIDITY"
    CAPACITY = "CAPACITY"


class AttributionValueStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class DiagnosisOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class AttributionObservation:
    dimension: AttributionDimension
    key: str
    status: AttributionValueStatus
    diagnostic_value: Decimal | None
    source_references: tuple[ValidationArtifactReference, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("attribution key", self.key)
        if (self.status is AttributionValueStatus.AVAILABLE) != (
            self.diagnostic_value is not None
        ):
            raise ValueError("Attribution status/value mismatch")
        if self.source_references != tuple(
            sorted(
                set(self.source_references),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ):
            raise ValueError("Attribution lineage must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Attribution reasons must be unique and sorted")
        if self.status is AttributionValueStatus.NOT_ESTIMABLE and not self.reason_codes:
            raise ValueError("NOT_ESTIMABLE attribution requires a reason")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "key": self.key,
            "status": self.status.value,
            "diagnostic_value": decimal_text(self.diagnostic_value),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class DecisionChainAttribution:
    attribution_id: ArtifactId
    attribution_hash: str
    outcome_reference: ValidationArtifactReference
    observations: tuple[AttributionObservation, ...]
    created_at: datetime
    causal_claim: bool
    authority: ResearchEvidenceAuthority
    limitations: tuple[str, ...]
    schema_version: str = "decision-chain-attribution/v1"

    def __post_init__(self) -> None:
        require_sha256("attribution_hash", self.attribution_hash)
        if self.causal_claim:
            raise ValueError("Decision-chain attribution cannot claim causality")
        if self.authority is not ResearchEvidenceAuthority.EXPLORATORY:
            raise ValueError("Decision-chain attribution is exploratory only")
        if {item.dimension for item in self.observations} != set(
            AttributionDimension
        ):
            raise ValueError("Attribution must cover every decision-chain dimension")
        if canonical_hash(self.identity_payload()) != self.attribution_hash:
            raise ValueError("Decision-chain Attribution hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome_reference": self.outcome_reference.to_canonical_dict(),
            "observations": [
                item.to_canonical_dict() for item in self.observations
            ],
            "created_at": timestamp(self.created_at),
            "causal_claim": self.causal_claim,
            "authority": self.authority.value,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ResearchDiagnosis:
    diagnosis_id: ArtifactId
    diagnosis_hash: str
    attribution_reference: ValidationArtifactReference
    outcome: DiagnosisOutcome
    selected_slices: tuple[tuple[str, str], ...]
    diagnosis: str
    proposed_research_question: str
    proposed_hypothesis: str
    primary_research_change: str
    diagnosed_at: datetime
    next_experiment_reference: ValidationArtifactReference | None
    experiment_frozen_at: datetime | None
    ready_for_experiment: bool
    limitations: tuple[str, ...]
    schema_version: str = "research-diagnosis/v1"

    def __post_init__(self) -> None:
        require_sha256("diagnosis_hash", self.diagnosis_hash)
        for label, value in (
            ("diagnosis", self.diagnosis),
            ("proposed_research_question", self.proposed_research_question),
            ("proposed_hypothesis", self.proposed_hypothesis),
            ("primary_research_change", self.primary_research_change),
        ):
            require_text(label, value)
        if self.selected_slices != tuple(sorted(set(self.selected_slices))):
            raise ValueError("Research Diagnosis slices must be unique and sorted")
        if self.ready_for_experiment != (
            self.next_experiment_reference is not None
            and self.experiment_frozen_at is not None
        ):
            raise ValueError("Research Diagnosis experiment readiness mismatch")
        if canonical_hash(self.identity_payload()) != self.diagnosis_hash:
            raise ValueError("Research Diagnosis hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _diagnosis_payload(
            self.attribution_reference,
            self.outcome,
            self.selected_slices,
            self.diagnosis,
            self.proposed_research_question,
            self.proposed_hypothesis,
            self.primary_research_change,
            self.diagnosed_at,
            self.next_experiment_reference,
            self.experiment_frozen_at,
            self.ready_for_experiment,
            self.limitations,
        )


def build_decision_chain_attribution(
    *,
    outcome_reference: ValidationArtifactReference,
    observations: tuple[AttributionObservation, ...],
    created_at: datetime,
) -> DecisionChainAttribution:
    ordered = tuple(
        sorted(observations, key=lambda item: (item.dimension.value, item.key))
    )
    if len(ordered) != len(AttributionDimension) or {
        item.dimension for item in ordered
    } != set(AttributionDimension):
        raise ValueError("Attribution requires every decision-chain dimension exactly once")
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "STRUCTURED_DIAGNOSTIC_NOT_CAUSAL",
                "EXPLORATORY_NOT_FORMAL_ALPHA_EVIDENCE",
            }
        )
    )
    values = {
        "schema_version": "decision-chain-attribution/v1",
        "outcome_reference": outcome_reference.to_canonical_dict(),
        "observations": [item.to_canonical_dict() for item in ordered],
        "created_at": timestamp(created_at),
        "causal_claim": False,
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": list(limitations),
    }
    attribution_id, digest = content_identity("decision-chain-attribution", values)
    return DecisionChainAttribution(
        attribution_id,
        digest,
        outcome_reference,
        ordered,
        created_at,
        False,
        ResearchEvidenceAuthority.EXPLORATORY,
        limitations,
    )


def diagnose_research_outcome(
    *,
    attribution: DecisionChainAttribution,
    outcome: DiagnosisOutcome,
    selected_slices: tuple[tuple[str, str], ...],
    diagnosis: str,
    proposed_research_question: str,
    proposed_hypothesis: str,
    primary_research_change: str,
    diagnosed_at: datetime,
) -> ResearchDiagnosis:
    available_slices = {
        (item.dimension.value, item.key) for item in attribution.observations
    }
    ordered_slices = tuple(sorted(set(selected_slices)))
    if not ordered_slices or not set(ordered_slices).issubset(available_slices):
        raise ValueError("Research Diagnosis must select observed attribution slices")
    attribution_reference = ValidationArtifactReference(
        "DECISION_CHAIN_ATTRIBUTION",
        attribution.attribution_id,
        attribution.attribution_hash,
    )
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "MANUAL_RESEARCH_DIAGNOSIS",
                "NEW_FROZEN_EXPERIMENT_REQUIRED",
                "NO_AUTOMATIC_STRATEGY_MUTATION",
            }
        )
    )
    return _make_diagnosis(
        attribution_reference,
        outcome,
        ordered_slices,
        diagnosis,
        proposed_research_question,
        proposed_hypothesis,
        primary_research_change,
        diagnosed_at,
        None,
        None,
        False,
        limitations,
    )


def freeze_diagnosis_with_experiment(
    *,
    diagnosis: ResearchDiagnosis,
    experiment_definition: ResearchExperimentDefinition,
    frozen_at: datetime,
) -> ResearchDiagnosis:
    if diagnosis.ready_for_experiment:
        raise ValueError("Research Diagnosis is already bound to a frozen experiment")
    if (
        experiment_definition.research_question
        != diagnosis.proposed_research_question
        or experiment_definition.hypothesis != diagnosis.proposed_hypothesis
    ):
        raise ValueError("Frozen Experiment question/hypothesis differs from Diagnosis")
    if frozen_at < diagnosis.diagnosed_at:
        raise ValueError("Experiment cannot be frozen before Research Diagnosis")
    experiment_reference = ValidationArtifactReference(
        "RESEARCH_EXPERIMENT_DEFINITION",
        experiment_definition.definition_id,
        experiment_definition.definition_hash,
    )
    limitations = tuple(
        item
        for item in diagnosis.limitations
        if item != "NEW_FROZEN_EXPERIMENT_REQUIRED"
    )
    return _make_diagnosis(
        diagnosis.attribution_reference,
        diagnosis.outcome,
        diagnosis.selected_slices,
        diagnosis.diagnosis,
        diagnosis.proposed_research_question,
        diagnosis.proposed_hypothesis,
        diagnosis.primary_research_change,
        diagnosis.diagnosed_at,
        experiment_reference,
        frozen_at,
        True,
        limitations,
    )


def _make_diagnosis(
    attribution_reference: ValidationArtifactReference,
    outcome: DiagnosisOutcome,
    selected_slices: tuple[tuple[str, str], ...],
    diagnosis: str,
    proposed_research_question: str,
    proposed_hypothesis: str,
    primary_research_change: str,
    diagnosed_at: datetime,
    next_experiment_reference: ValidationArtifactReference | None,
    experiment_frozen_at: datetime | None,
    ready_for_experiment: bool,
    limitations: tuple[str, ...],
) -> ResearchDiagnosis:
    values = _diagnosis_payload(
        attribution_reference,
        outcome,
        selected_slices,
        diagnosis,
        proposed_research_question,
        proposed_hypothesis,
        primary_research_change,
        diagnosed_at,
        next_experiment_reference,
        experiment_frozen_at,
        ready_for_experiment,
        limitations,
    )
    diagnosis_id, digest = content_identity("research-diagnosis", values)
    return ResearchDiagnosis(
        diagnosis_id,
        digest,
        attribution_reference,
        outcome,
        selected_slices,
        diagnosis,
        proposed_research_question,
        proposed_hypothesis,
        primary_research_change,
        diagnosed_at,
        next_experiment_reference,
        experiment_frozen_at,
        ready_for_experiment,
        limitations,
    )


def _diagnosis_payload(
    attribution_reference: ValidationArtifactReference,
    outcome: DiagnosisOutcome,
    selected_slices: tuple[tuple[str, str], ...],
    diagnosis: str,
    proposed_research_question: str,
    proposed_hypothesis: str,
    primary_research_change: str,
    diagnosed_at: datetime,
    next_experiment_reference: ValidationArtifactReference | None,
    experiment_frozen_at: datetime | None,
    ready_for_experiment: bool,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "research-diagnosis/v1",
        "attribution_reference": attribution_reference.to_canonical_dict(),
        "outcome": outcome.value,
        "selected_slices": [list(item) for item in selected_slices],
        "diagnosis": diagnosis,
        "proposed_research_question": proposed_research_question,
        "proposed_hypothesis": proposed_hypothesis,
        "primary_research_change": primary_research_change,
        "diagnosed_at": timestamp(diagnosed_at),
        "next_experiment_reference": (
            None
            if next_experiment_reference is None
            else next_experiment_reference.to_canonical_dict()
        ),
        "experiment_frozen_at": (
            None if experiment_frozen_at is None else timestamp(experiment_frozen_at)
        ),
        "ready_for_experiment": ready_for_experiment,
        "limitations": list(limitations),
    }


__all__ = [
    "AttributionDimension",
    "AttributionObservation",
    "AttributionValueStatus",
    "DecisionChainAttribution",
    "DiagnosisOutcome",
    "ResearchDiagnosis",
    "build_decision_chain_attribution",
    "diagnose_research_outcome",
    "freeze_diagnosis_with_experiment",
]
