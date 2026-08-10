"""Independent Entry research and qualification pipeline.

This module cannot mutate or unlock the current Canonical Entry version.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    GOVERNED_NON_PRODUCTION_LIMITATIONS,
    GovernanceQualificationBinding,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.platform.runtime_governance import QualificationEvidenceKind


class EntryResearchVariant(str, Enum):
    CANDIDATE_ONLY = "CANDIDATE_ONLY"
    CANDIDATE_SIGNAL = "CANDIDATE_SIGNAL"
    CANDIDATE_FORECAST = "CANDIDATE_FORECAST"
    CANDIDATE_INTRADAY = "CANDIDATE_INTRADAY"


class EntryResearchDecision(str, Enum):
    SHADOW_ENTER = "SHADOW_ENTER"
    SHADOW_WAIT = "SHADOW_WAIT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class EntryResearchModel:
    model_id: ModelId
    model_hash: str
    model_version: str
    variant: EntryResearchVariant
    score_threshold: Decimal
    required_inputs: tuple[str, ...]
    limitations: tuple[str, ...]

    @classmethod
    def create(cls, *, model_version: str, variant: EntryResearchVariant, score_threshold: Decimal) -> EntryResearchModel:
        if not Decimal("0") <= score_threshold <= Decimal("1"):
            raise ValueError("Entry research threshold must be within [0, 1]")
        required = {
            EntryResearchVariant.CANDIDATE_ONLY: ("candidate_score",),
            EntryResearchVariant.CANDIDATE_SIGNAL: ("candidate_score", "signal_score"),
            EntryResearchVariant.CANDIDATE_FORECAST: ("candidate_score", "forecast_score"),
            EntryResearchVariant.CANDIDATE_INTRADAY: ("candidate_score", "intraday_score"),
        }[variant]
        limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "ENTRY_QUALIFIED_FALSE", "SHADOW_DECISION_ONLY"}))
        payload = {
            "schema": "entry-research-model/v1",
            "model_version": model_version,
            "variant": variant.value,
            "score_threshold": str(score_threshold),
            "required_inputs": list(required),
            "limitations": list(limitations),
        }
        artifact_id, digest = content_identity("entry-research-model", payload)
        return cls(ModelId(str(artifact_id)), digest, model_version, variant, score_threshold, required, limitations)


@dataclass(frozen=True, slots=True)
class EntryResearchAssessment:
    assessment_id: ArtifactId
    assessment_hash: str
    model_reference: ValidationArtifactReference
    symbol: str
    decision_time: datetime
    inputs: tuple[tuple[str, Decimal | None], ...]
    aggregate_score: Decimal | None
    decision: EntryResearchDecision
    reason_codes: tuple[str, ...]
    source_references: tuple[ValidationArtifactReference, ...]

    def __post_init__(self) -> None:
        require_sha256("assessment_hash", self.assessment_hash)
        require_text("symbol", self.symbol)
        if self.inputs != tuple(sorted(self.inputs)):
            raise ValueError("Entry research inputs must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.assessment_hash:
            raise ValueError("Entry assessment hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _assessment_payload(
            self.model_reference,
            self.symbol,
            self.decision_time,
            self.inputs,
            self.aggregate_score,
            self.decision,
            self.reason_codes,
            self.source_references,
        )


@dataclass(frozen=True, slots=True)
class EntryEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    model_reference: ValidationArtifactReference
    assessment_references: tuple[ValidationArtifactReference, ...]
    sample_count: int
    enter_count: int
    hit_rate: Decimal | None
    mean_return: Decimal | None
    mean_mfe: Decimal | None
    mean_mae: Decimal | None
    cost_adjusted_return: Decimal | None
    created_at: datetime
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntryQualificationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    minimum_samples: int
    minimum_hit_rate: Decimal
    minimum_cost_adjusted_return: Decimal
    required_formal_oos: bool
    required_calibration: bool
    locked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        minimum_samples: int,
        minimum_hit_rate: Decimal,
        minimum_cost_adjusted_return: Decimal,
        locked_at: datetime,
    ) -> EntryQualificationProtocol:
        if minimum_samples <= 0 or not Decimal("0") <= minimum_hit_rate <= Decimal("1"):
            raise ValueError("Entry Qualification floor is invalid")
        payload = {
            "schema": "entry-qualification-protocol/v1",
            "protocol_version": protocol_version,
            "minimum_samples": minimum_samples,
            "minimum_hit_rate": str(minimum_hit_rate),
            "minimum_cost_adjusted_return": str(minimum_cost_adjusted_return),
            "required_formal_oos": True,
            "required_calibration": True,
            "locked_at": timestamp(locked_at),
        }
        artifact_id, digest = content_identity("entry-qualification-protocol", payload)
        return cls(
            artifact_id, digest, protocol_version, minimum_samples, minimum_hit_rate, minimum_cost_adjusted_return, True, True, locked_at
        )


@dataclass(frozen=True, slots=True)
class EntryQualificationEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    protocol_reference: ValidationArtifactReference
    evaluation_reference: ValidationArtifactReference
    formal_oos_reference: ValidationArtifactReference | None
    calibration_reference: ValidationArtifactReference | None
    governance_approval_reference: ValidationArtifactReference | None
    entry_qualified: bool
    canonical_entry_unlock_permitted: bool
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        if self.entry_qualified and (
            self.formal_oos_reference is None or self.calibration_reference is None or self.governance_approval_reference is None
        ):
            raise ValueError("Entry qualification requires Formal OOS, Calibration and Governance evidence")
        if self.canonical_entry_unlock_permitted != self.entry_qualified:
            raise ValueError("Canonical Entry unlock permission must match qualified evidence")
        if canonical_hash(self.identity_payload()) != self.evidence_hash:
            raise ValueError("Entry qualification evidence hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _qualification_payload(
            self.protocol_reference,
            self.evaluation_reference,
            self.formal_oos_reference,
            self.calibration_reference,
            self.governance_approval_reference,
            self.entry_qualified,
            self.canonical_entry_unlock_permitted,
            self.reason_codes,
            self.created_at,
            self.limitations,
        )


def assess_entry(
    *,
    model: EntryResearchModel,
    symbol: str,
    decision_time: datetime,
    inputs: tuple[tuple[str, Decimal | None], ...],
    source_references: tuple[ValidationArtifactReference, ...],
) -> EntryResearchAssessment:
    values = dict(inputs)
    if tuple(sorted(values)) != model.required_inputs:
        raise ValueError("Entry research inputs do not match model variant")
    missing = tuple(sorted(name for name, value in values.items() if value is None))
    score = None if missing else sum((value for value in values.values() if value is not None), Decimal("0")) / Decimal(len(values))
    decision = (
        EntryResearchDecision.DATA_INSUFFICIENT
        if missing
        else EntryResearchDecision.SHADOW_ENTER
        if score is not None and score >= model.score_threshold
        else EntryResearchDecision.SHADOW_WAIT
    )
    reasons = (
        missing
        if missing
        else ("RESEARCH_THRESHOLD_MET",)
        if decision is EntryResearchDecision.SHADOW_ENTER
        else ("RESEARCH_THRESHOLD_NOT_MET",)
    )
    model_ref = ValidationArtifactReference("ENTRY_RESEARCH_MODEL", ArtifactId(str(model.model_id)), model.model_hash)
    ordered_inputs = tuple(sorted(inputs))
    ordered_sources = tuple(sorted(set(source_references), key=lambda item: (item.artifact_kind, str(item.artifact_id))))
    payload = _assessment_payload(
        model_ref, symbol, decision_time, ordered_inputs, score, decision, tuple(sorted(reasons)), ordered_sources
    )
    artifact_id, digest = content_identity("entry-research-assessment", payload)
    return EntryResearchAssessment(
        artifact_id, digest, model_ref, symbol, decision_time, ordered_inputs, score, decision, tuple(sorted(reasons)), ordered_sources
    )


def evaluate_entries(
    *,
    model: EntryResearchModel,
    observations: tuple[tuple[EntryResearchAssessment, Decimal | None, Decimal | None, Decimal | None, Decimal | None], ...],
    created_at: datetime,
) -> EntryEvaluation:
    entered = [item for item in observations if item[0].decision is EntryResearchDecision.SHADOW_ENTER and item[1] is not None]
    returns = [item[1] for item in entered if item[1] is not None]
    mfes = [item[2] for item in entered if item[2] is not None]
    maes = [item[3] for item in entered if item[3] is not None]
    costs = [item[4] or Decimal("0") for item in entered]
    model_ref = ValidationArtifactReference("ENTRY_RESEARCH_MODEL", ArtifactId(str(model.model_id)), model.model_hash)
    references = tuple(
        sorted(
            (
                ValidationArtifactReference("ENTRY_RESEARCH_ASSESSMENT", item[0].assessment_id, item[0].assessment_hash)
                for item in observations
            ),
            key=lambda item: str(item.artifact_id),
        )
    )
    hit_rate = None if not returns else Decimal(sum(value > 0 for value in returns)) / Decimal(len(returns))
    mean_return = _mean(returns)
    cost_return = None if not returns else _mean([value - cost for value, cost in zip(returns, costs, strict=True)])
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "ENTRY_QUALIFIED_FALSE"}))
    payload = {
        "model_reference": model_ref.to_canonical_dict(),
        "assessment_references": [item.to_canonical_dict() for item in references],
        "sample_count": len(observations),
        "enter_count": len(entered),
        "hit_rate": None if hit_rate is None else str(hit_rate),
        "mean_return": None if mean_return is None else str(mean_return),
        "mean_mfe": None if not mfes else str(_mean(mfes)),
        "mean_mae": None if not maes else str(_mean(maes)),
        "cost_adjusted_return": None if cost_return is None else str(cost_return),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("entry-evaluation", payload)
    return EntryEvaluation(
        artifact_id,
        digest,
        model_ref,
        references,
        len(observations),
        len(entered),
        hit_rate,
        mean_return,
        _mean(mfes),
        _mean(maes),
        cost_return,
        created_at,
        limitations,
    )


def build_unqualified_entry_evidence(
    *,
    protocol: EntryQualificationProtocol,
    evaluation: EntryEvaluation,
    formal_oos_reference: ValidationArtifactReference | None,
    calibration_reference: ValidationArtifactReference | None,
    created_at: datetime,
) -> EntryQualificationEvidence:
    protocol_ref = ValidationArtifactReference("ENTRY_QUALIFICATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    evaluation_ref = ValidationArtifactReference("ENTRY_EVALUATION", evaluation.evaluation_id, evaluation.evaluation_hash)
    reasons = {"ENTRY_QUALIFIED_FALSE", "CANONICAL_ENTRY_UNLOCK_BLOCKED"}
    if formal_oos_reference is None:
        reasons.add("FORMAL_OOS_REQUIRED")
    if calibration_reference is None:
        reasons.add("CALIBRATION_QUALIFICATION_REQUIRED")
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "ENTRY_QUALIFIED_FALSE"}))
    payload = _qualification_payload(
        protocol_ref,
        evaluation_ref,
        formal_oos_reference,
        calibration_reference,
        None,
        False,
        False,
        tuple(sorted(reasons)),
        created_at,
        limitations,
    )
    artifact_id, digest = content_identity("entry-qualification-evidence", payload)
    return EntryQualificationEvidence(
        artifact_id,
        digest,
        protocol_ref,
        evaluation_ref,
        formal_oos_reference,
        calibration_reference,
        None,
        False,
        False,
        tuple(sorted(reasons)),
        created_at,
        limitations,
    )


def qualify_entry(
    *,
    protocol: EntryQualificationProtocol,
    evaluation: EntryEvaluation,
    formal_oos_reference: ValidationArtifactReference,
    calibration_reference: ValidationArtifactReference,
    governance: GovernanceQualificationBinding,
    created_at: datetime,
) -> EntryQualificationEvidence:
    expected_kinds = (
        (formal_oos_reference, "FORMAL_OOS_EVIDENCE"),
        (calibration_reference, "CALIBRATION_ARTIFACT"),
    )
    for reference, expected_kind in expected_kinds:
        if reference.artifact_kind != expected_kind:
            raise ValueError(f"Entry qualification requires {expected_kind}")
    evaluation_ref = ValidationArtifactReference("ENTRY_EVALUATION", evaluation.evaluation_id, evaluation.evaluation_hash)
    governance.require_artifact(formal_oos_reference, QualificationEvidenceKind.FORMAL_OOS)
    governance.require_artifact(calibration_reference, QualificationEvidenceKind.BACKTEST_VALIDATION)
    governance.require_artifact(evaluation_ref, QualificationEvidenceKind.ECONOMIC_VALIDATION)
    governance_approval_reference = governance.decision_reference
    if evaluation.sample_count < protocol.minimum_samples:
        raise ValueError("Entry qualification sample floor not met")
    if evaluation.hit_rate is None or evaluation.hit_rate < protocol.minimum_hit_rate:
        raise ValueError("Entry qualification hit-rate floor not met")
    if evaluation.cost_adjusted_return is None or evaluation.cost_adjusted_return < protocol.minimum_cost_adjusted_return:
        raise ValueError("Entry qualification economic floor not met")
    protocol_ref = ValidationArtifactReference("ENTRY_QUALIFICATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    reasons = ("ENTRY_QUALIFIED_BY_GOVERNANCE",)
    limitations = GOVERNED_NON_PRODUCTION_LIMITATIONS
    payload = _qualification_payload(
        protocol_ref,
        evaluation_ref,
        formal_oos_reference,
        calibration_reference,
        governance_approval_reference,
        True,
        True,
        reasons,
        created_at,
        limitations,
    )
    artifact_id, digest = content_identity("entry-qualification-evidence", payload)
    return EntryQualificationEvidence(
        artifact_id,
        digest,
        protocol_ref,
        evaluation_ref,
        formal_oos_reference,
        calibration_reference,
        governance_approval_reference,
        True,
        True,
        reasons,
        created_at,
        limitations,
    )


def _mean(values: list[Decimal]) -> Decimal | None:
    return None if not values else sum(values, Decimal("0")) / Decimal(len(values))


def _assessment_payload(
    model: ValidationArtifactReference,
    symbol: str,
    decision_time: datetime,
    inputs: tuple[tuple[str, Decimal | None], ...],
    score: Decimal | None,
    decision: EntryResearchDecision,
    reasons: tuple[str, ...],
    sources: tuple[ValidationArtifactReference, ...],
) -> dict[str, Any]:
    return {
        "schema": "entry-research-assessment/v1",
        "model_reference": model.to_canonical_dict(),
        "symbol": symbol,
        "decision_time": timestamp(decision_time),
        "inputs": [[name, None if value is None else str(value)] for name, value in inputs],
        "aggregate_score": None if score is None else str(score),
        "decision": decision.value,
        "reason_codes": list(reasons),
        "source_references": [item.to_canonical_dict() for item in sources],
    }


def _qualification_payload(
    protocol: ValidationArtifactReference,
    evaluation: ValidationArtifactReference,
    formal: ValidationArtifactReference | None,
    calibration: ValidationArtifactReference | None,
    governance_approval: ValidationArtifactReference | None,
    entry_qualified: bool,
    canonical_entry_unlock_permitted: bool,
    reasons: tuple[str, ...],
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema": "entry-qualification-evidence/v1",
        "protocol_reference": protocol.to_canonical_dict(),
        "evaluation_reference": evaluation.to_canonical_dict(),
        "formal_oos_reference": None if formal is None else formal.to_canonical_dict(),
        "calibration_reference": None if calibration is None else calibration.to_canonical_dict(),
        "governance_approval_reference": (None if governance_approval is None else governance_approval.to_canonical_dict()),
        "entry_qualified": entry_qualified,
        "canonical_entry_unlock_permitted": canonical_entry_unlock_permitted,
        "reason_codes": list(reasons),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
