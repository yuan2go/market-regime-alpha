"""Holding/Exit validation protocol over Strategy Shadow outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    GOVERNED_NON_PRODUCTION_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.strategy_shadow.contracts import StrategyOutcome
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


@dataclass(frozen=True, slots=True)
class HoldingExitValidationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    minimum_samples: int
    minimum_net_return: Decimal
    maximum_mean_mae: Decimal
    required_exit_rule_coverage: tuple[str, ...]
    locked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        minimum_samples: int,
        minimum_net_return: Decimal,
        maximum_mean_mae: Decimal,
        required_exit_rule_coverage: tuple[str, ...],
        locked_at: datetime,
    ) -> HoldingExitValidationProtocol:
        if minimum_samples <= 0 or maximum_mean_mae > 0:
            raise ValueError("Holding/Exit validation floors are invalid")
        rules = tuple(sorted(set(required_exit_rule_coverage)))
        if not rules:
            raise ValueError("Holding/Exit validation requires rule coverage")
        payload = {
            "schema": "holding-exit-validation-protocol/v1",
            "protocol_version": protocol_version,
            "minimum_samples": minimum_samples,
            "minimum_net_return": str(minimum_net_return),
            "maximum_mean_mae": str(maximum_mean_mae),
            "required_exit_rule_coverage": list(rules),
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
    governance_approval_reference: ValidationArtifactReference | None,
    created_at: datetime,
) -> HoldingExitValidationEvidence:
    references = tuple(
        sorted(
            (ValidationArtifactReference("STRATEGY_OUTCOME", item.outcome_id, item.outcome_hash) for item in outcomes),
            key=lambda item: str(item.artifact_id),
        )
    )
    mean_return = _mean([item.net_return for item in outcomes])
    mean_mae = _mean([item.mae for item in outcomes if item.mae is not None])
    floors = (
        len(outcomes) >= protocol.minimum_samples
        and mean_return is not None
        and mean_return >= protocol.minimum_net_return
        and mean_mae is not None
        and mean_mae >= protocol.maximum_mean_mae
    )
    validated = floors and formal_oos_reference is not None and governance_approval_reference is not None
    reasons = ("HOLDING_EXIT_VALIDATED_BY_GOVERNANCE",) if validated else ("HOLDING_EXIT_VALIDATED_FALSE",)
    limitations = (
        GOVERNED_NON_PRODUCTION_LIMITATIONS if validated else tuple(sorted({*ENGINEERING_LIMITATIONS, "HOLDING_EXIT_VALIDATED_FALSE"}))
    )
    protocol_ref = ValidationArtifactReference("HOLDING_EXIT_VALIDATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    payload = _payload(
        protocol_ref,
        references,
        formal_oos_reference,
        governance_approval_reference,
        len(outcomes),
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
        governance_approval_reference,
        len(outcomes),
        mean_return,
        mean_mae,
        validated,
        reasons,
        created_at,
        limitations,
    )


def _mean(values: list[Decimal]) -> Decimal | None:
    return None if not values else sum(values, Decimal("0")) / Decimal(len(values))


def _payload(
    protocol: ValidationArtifactReference,
    outcomes: tuple[ValidationArtifactReference, ...],
    formal: ValidationArtifactReference | None,
    approval: ValidationArtifactReference | None,
    count: int,
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
        "mean_net_return": None if mean_return is None else str(mean_return),
        "mean_mae": None if mean_mae is None else str(mean_mae),
        "holding_exit_validated": validated,
        "reason_codes": list(reasons),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
