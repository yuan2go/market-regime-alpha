"""Holding/Exit validation protocol over Strategy Shadow outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    GOVERNED_NON_PRODUCTION_LIMITATIONS,
    GovernanceQualificationBinding,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.strategy_shadow.contracts import HoldingRuleKind, StrategyOutcome
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.platform.runtime_governance import QualificationEvidenceKind


@dataclass(frozen=True, slots=True)
class HoldingExitValidationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    minimum_samples: int
    minimum_net_return: Decimal
    maximum_mean_mae: Decimal
    required_exit_rule_coverage: tuple[HoldingRuleKind, ...]
    locked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        minimum_samples: int,
        minimum_net_return: Decimal,
        maximum_mean_mae: Decimal,
        required_exit_rule_coverage: tuple[HoldingRuleKind, ...],
        locked_at: datetime,
    ) -> HoldingExitValidationProtocol:
        if minimum_samples <= 0 or maximum_mean_mae > 0:
            raise ValueError("Holding/Exit validation floors are invalid")
        rules = tuple(sorted(set(required_exit_rule_coverage), key=lambda item: item.value))
        if not rules:
            raise ValueError("Holding/Exit validation requires rule coverage")
        payload = {
            "schema": "holding-exit-validation-protocol/v1",
            "protocol_version": protocol_version,
            "minimum_samples": minimum_samples,
            "minimum_net_return": str(minimum_net_return),
            "maximum_mean_mae": str(maximum_mean_mae),
            "required_exit_rule_coverage": [item.value for item in rules],
            "locked_at": timestamp(locked_at),
        }
        artifact_id, digest = content_identity("holding-exit-validation-protocol", payload)
        return cls(artifact_id, digest, protocol_version, minimum_samples, minimum_net_return, maximum_mean_mae, rules, locked_at)


@dataclass(frozen=True, slots=True)
class HoldingExitValidationEvidence:
    evidence_id: ArtifactId
    evidence_hash: str
    protocol_reference: ValidationArtifactReference
    outcome_references: tuple[ValidationArtifactReference, ...]
    formal_oos_reference: ValidationArtifactReference | None
    governance_approval_reference: ValidationArtifactReference | None
    sample_count: int
    observed_exit_rule_coverage: tuple[HoldingRuleKind, ...]
    mean_net_return: Decimal | None
    mean_mae: Decimal | None
    holding_exit_validated: bool
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("evidence_hash", self.evidence_hash)
        if self.holding_exit_validated and (self.formal_oos_reference is None or self.governance_approval_reference is None):
            raise ValueError("Holding/Exit validation requires Formal OOS and Governance evidence")
        if canonical_hash(self.identity_payload()) != self.evidence_hash:
            raise ValueError("Holding/Exit validation evidence hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _payload(
            self.protocol_reference,
            self.outcome_references,
            self.formal_oos_reference,
            self.governance_approval_reference,
            self.sample_count,
            self.observed_exit_rule_coverage,
            self.mean_net_return,
            self.mean_mae,
            self.holding_exit_validated,
            self.reason_codes,
            self.created_at,
            self.limitations,
        )


def evaluate_holding_exit(
    *,
    protocol: HoldingExitValidationProtocol,
    outcomes: tuple[StrategyOutcome, ...],
    formal_oos_reference: ValidationArtifactReference | None,
    created_at: datetime,
) -> HoldingExitValidationEvidence:
    if formal_oos_reference is not None and formal_oos_reference.artifact_kind != "FORMAL_OOS_EVIDENCE":
        raise ValueError("Holding/Exit validation requires Formal OOS evidence")
    references = tuple(
        sorted(
            (ValidationArtifactReference("STRATEGY_OUTCOME", item.outcome_id, item.outcome_hash) for item in outcomes),
            key=lambda item: str(item.artifact_id),
        )
    )
    mean_return = _mean([item.net_return for item in outcomes])
    mean_mae = _mean([item.mae for item in outcomes if item.mae is not None])
    observed_rule_coverage = tuple(sorted({rule for item in outcomes for rule in item.exit_rule_kinds}, key=lambda item: item.value))
    floors = (
        len(outcomes) >= protocol.minimum_samples
        and mean_return is not None
        and mean_return >= protocol.minimum_net_return
        and mean_mae is not None
        and mean_mae >= protocol.maximum_mean_mae
        and set(protocol.required_exit_rule_coverage).issubset(observed_rule_coverage)
    )
    validated = False
    reasons = tuple(
        sorted(
            {
                "GOVERNANCE_QUALIFICATION_REQUIRED",
                "HOLDING_EXIT_VALIDATED_FALSE",
                "HOLDING_EXIT_ENGINEERING_FLOORS_MET" if floors else "HOLDING_EXIT_ENGINEERING_FLOORS_NOT_MET",
            }
        )
    )
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "HOLDING_EXIT_VALIDATED_FALSE"}))
    protocol_ref = ValidationArtifactReference("HOLDING_EXIT_VALIDATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    payload = _payload(
        protocol_ref,
        references,
        formal_oos_reference,
        None,
        len(outcomes),
        observed_rule_coverage,
        mean_return,
        mean_mae,
        validated,
        reasons,
        created_at,
        limitations,
    )
    artifact_id, digest = content_identity("holding-exit-validation-evidence", payload)
    return HoldingExitValidationEvidence(
        artifact_id,
        digest,
        protocol_ref,
        references,
        formal_oos_reference,
        None,
        len(outcomes),
        observed_rule_coverage,
        mean_return,
        mean_mae,
        validated,
        reasons,
        created_at,
        limitations,
    )


def qualify_holding_exit(
    *,
    evidence: HoldingExitValidationEvidence,
    governance: GovernanceQualificationBinding,
    created_at: datetime,
) -> HoldingExitValidationEvidence:
    if evidence.holding_exit_validated:
        return evidence
    if evidence.formal_oos_reference is None:
        raise ValueError("Holding/Exit qualification requires Formal OOS evidence")
    if "HOLDING_EXIT_ENGINEERING_FLOORS_MET" not in evidence.reason_codes:
        raise ValueError("Holding/Exit engineering floors are not met")
    evidence_reference = ValidationArtifactReference("HOLDING_EXIT_EVIDENCE", evidence.evidence_id, evidence.evidence_hash)
    governance.require_artifact(evidence.formal_oos_reference, QualificationEvidenceKind.FORMAL_OOS)
    governance.require_artifact(evidence_reference, QualificationEvidenceKind.ECONOMIC_VALIDATION)
    approval = governance.decision_reference
    reasons = ("HOLDING_EXIT_VALIDATED_BY_GOVERNANCE",)
    payload = _payload(
        evidence.protocol_reference,
        evidence.outcome_references,
        evidence.formal_oos_reference,
        approval,
        evidence.sample_count,
        evidence.observed_exit_rule_coverage,
        evidence.mean_net_return,
        evidence.mean_mae,
        True,
        reasons,
        created_at,
        GOVERNED_NON_PRODUCTION_LIMITATIONS,
    )
    evidence_id, digest = content_identity("holding-exit-validation-evidence", payload)
    return HoldingExitValidationEvidence(
        evidence_id,
        digest,
        evidence.protocol_reference,
        evidence.outcome_references,
        evidence.formal_oos_reference,
        approval,
        evidence.sample_count,
        evidence.observed_exit_rule_coverage,
        evidence.mean_net_return,
        evidence.mean_mae,
        True,
        reasons,
        created_at,
        GOVERNED_NON_PRODUCTION_LIMITATIONS,
    )


def _mean(values: list[Decimal]) -> Decimal | None:
    return None if not values else sum(values, Decimal("0")) / Decimal(len(values))


def _payload(
    protocol: ValidationArtifactReference,
    outcomes: tuple[ValidationArtifactReference, ...],
    formal: ValidationArtifactReference | None,
    approval: ValidationArtifactReference | None,
    count: int,
    observed_rule_coverage: tuple[HoldingRuleKind, ...],
    mean_return: Decimal | None,
    mean_mae: Decimal | None,
    validated: bool,
    reasons: tuple[str, ...],
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema": "holding-exit-validation-evidence/v1",
        "protocol_reference": protocol.to_canonical_dict(),
        "outcome_references": [item.to_canonical_dict() for item in outcomes],
        "formal_oos_reference": None if formal is None else formal.to_canonical_dict(),
        "governance_approval_reference": None if approval is None else approval.to_canonical_dict(),
        "sample_count": count,
        "observed_exit_rule_coverage": [item.value for item in observed_rule_coverage],
        "mean_net_return": None if mean_return is None else str(mean_return),
        "mean_mae": None if mean_mae is None else str(mean_mae),
        "holding_exit_validated": validated,
        "reason_codes": list(reasons),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
