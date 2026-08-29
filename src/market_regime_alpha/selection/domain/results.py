"""Immutable Selection command results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from market_regime_alpha.selection.domain.evidence import MarketLineage
from market_regime_alpha.selection.domain.model import EligibilityRule
from market_regime_alpha.selection.domain.vocabulary import (
    CriterionResult,
    CriterionValueKind,
    EligibilityStatus,
    MarketEvidenceStatus,
    UniverseMembershipStatus,
)
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime


@dataclass(frozen=True, slots=True)
class UniverseMemberDecision:
    universe_member_id: UUID
    instrument_id: InstrumentId
    membership_status: UniverseMembershipStatus
    evidence_status: MarketEvidenceStatus
    observed_membership_status: str | None
    classification_id: UUID | None
    membership_revision_id: UUID | None
    source_gap_id: UUID | None
    market_capture_id: UUID | None
    market_decision_visible_at: datetime | None
    reason_code: str
    lineage_hash: str


@dataclass(frozen=True, slots=True)
class FrozenUniverse:
    universe_revision_id: UUID
    universe_id: UUID
    revision: int
    decision_time: DecisionTime
    members: tuple[UniverseMemberDecision, ...]
    total_count: int
    included_count: int
    excluded_count: int
    unknown_count: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


@dataclass(frozen=True, slots=True)
class EligibilityReasonDecision:
    eligibility_reason_id: UUID
    rule: EligibilityRule
    criterion_result: CriterionResult
    observed_value_kind: CriterionValueKind
    observed_decimal: Decimal | None
    observed_status: str | None
    observed_count: int | None
    reason_code: str
    lineage: MarketLineage


@dataclass(frozen=True, slots=True)
class EligibilityAssessmentDecision:
    eligibility_assessment_id: UUID
    universe_member_id: UUID
    instrument_id: InstrumentId
    result: EligibilityStatus
    reasons: tuple[EligibilityReasonDecision, ...]


@dataclass(frozen=True, slots=True)
class EligibilityBatch:
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    decision_time: DecisionTime
    assessments: tuple[EligibilityAssessmentDecision, ...]
    total_count: int
    eligible_count: int
    ineligible_count: int
    unknown_count: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


__all__ = [
    "EligibilityAssessmentDecision",
    "EligibilityBatch",
    "EligibilityReasonDecision",
    "FrozenUniverse",
    "UniverseMemberDecision",
]
