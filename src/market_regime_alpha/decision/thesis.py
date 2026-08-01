"""Human-approved TradingThesis aggregate and invalidation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import OpportunityId, ThesisId
from market_regime_alpha.decision.opportunity import DecisionEvidenceReference


TRADING_THESIS_SCHEMA = "trading-thesis-v1"


class ThesisState(str, Enum):
    APPROVED = "APPROVED"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


class InvalidationKind(str, Enum):
    PRICE = "PRICE"
    MARKET_REGIME = "MARKET_REGIME"
    THEME = "THEME"
    CAPITAL = "CAPITAL"
    SIGNAL = "SIGNAL"
    TIME = "TIME"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True)
class InvalidationCondition:
    condition_id: str
    kind: InvalidationKind
    description: str
    reason_code: str

    def __post_init__(self) -> None:
        for label, value in (
            ("condition_id", self.condition_id),
            ("description", self.description),
            ("reason_code", self.reason_code),
        ):
            if not value or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "condition_id": self.condition_id,
            "kind": self.kind.value,
            "description": self.description,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> InvalidationCondition:
        if set(payload) != {"condition_id", "kind", "description", "reason_code"}:
            raise ValueError("InvalidationCondition fields mismatch")
        return cls(
            condition_id=str(payload["condition_id"]),
            kind=InvalidationKind(str(payload["kind"])),
            description=str(payload["description"]),
            reason_code=str(payload["reason_code"]),
        )


@dataclass(frozen=True, slots=True)
class TradingThesis:
    schema_version: str
    thesis_id: ThesisId
    opportunity_id: OpportunityId
    source_opportunity_version: int
    symbol: str
    supporting_evidence: tuple[DecisionEvidenceReference, ...]
    invalidation_conditions: tuple[InvalidationCondition, ...]
    time_invalidation: datetime
    state: ThesisState
    version: int
    approved_by: str
    approval_reason: str
    created_at: datetime
    updated_at: datetime
    last_actor: str
    last_reason: str

    def __post_init__(self) -> None:
        if self.schema_version != TRADING_THESIS_SCHEMA:
            raise ValueError("unsupported TradingThesis schema")
        if self.source_opportunity_version != 0:
            raise ValueError("Thesis V1 must bind the OPEN Opportunity version")
        for label, value in (
            ("symbol", self.symbol),
            ("approved_by", self.approved_by),
            ("approval_reason", self.approval_reason),
            ("last_actor", self.last_actor),
            ("last_reason", self.last_reason),
        ):
            if not value or value != value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        if self.time_invalidation.tzinfo is None or self.time_invalidation.utcoffset() is None:
            raise ValueError("Thesis time invalidation must be timezone-aware")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Thesis created_at must be timezone-aware")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("Thesis updated_at must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("Thesis updated_at cannot precede creation")
        if self.time_invalidation <= self.created_at:
            raise ValueError("Thesis time invalidation must follow approval")
        evidence_keys = tuple(
            (item.artifact_id, item.content_hash) for item in self.supporting_evidence
        )
        if not evidence_keys or evidence_keys != tuple(sorted(set(evidence_keys), key=lambda item: str(item[0]))):
            raise ValueError("Thesis supporting evidence must be sorted and unique")
        condition_ids = tuple(item.condition_id for item in self.invalidation_conditions)
        if not condition_ids or condition_ids != tuple(sorted(set(condition_ids))):
            raise ValueError("Thesis invalidation conditions must be sorted and unique")
        if self.version < 0:
            raise ValueError("Thesis version cannot be negative")
        if self.state is ThesisState.APPROVED and self.version != 0:
            raise ValueError("APPROVED Thesis must be initial version 0")
        if self.state is not ThesisState.APPROVED and self.version <= 0:
            raise ValueError("terminal Thesis requires a transition version")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thesis_id": str(self.thesis_id),
            "opportunity_id": str(self.opportunity_id),
            "source_opportunity_version": self.source_opportunity_version,
            "symbol": self.symbol,
            "supporting_evidence": [
                item.to_canonical_dict() for item in self.supporting_evidence
            ],
            "invalidation_conditions": [
                item.to_canonical_dict() for item in self.invalidation_conditions
            ],
            "time_invalidation": self.time_invalidation.isoformat(),
            "state": self.state.value,
            "version": self.version,
            "approved_by": self.approved_by,
            "approval_reason": self.approval_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_actor": self.last_actor,
            "last_reason": self.last_reason,
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> TradingThesis:
        expected = {
            "schema_version",
            "thesis_id",
            "opportunity_id",
            "source_opportunity_version",
            "symbol",
            "supporting_evidence",
            "invalidation_conditions",
            "time_invalidation",
            "state",
            "version",
            "approved_by",
            "approval_reason",
            "created_at",
            "updated_at",
            "last_actor",
            "last_reason",
        }
        evidence = payload.get("supporting_evidence")
        conditions = payload.get("invalidation_conditions")
        if set(payload) != expected or not isinstance(evidence, list) or not isinstance(conditions, list):
            raise ValueError("TradingThesis fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            opportunity_id=OpportunityId(str(payload["opportunity_id"])),
            source_opportunity_version=int(payload["source_opportunity_version"]),
            symbol=str(payload["symbol"]),
            supporting_evidence=tuple(
                DecisionEvidenceReference.from_canonical_dict(_object(item))
                for item in evidence
            ),
            invalidation_conditions=tuple(
                InvalidationCondition.from_canonical_dict(_object(item))
                for item in conditions
            ),
            time_invalidation=datetime.fromisoformat(str(payload["time_invalidation"])),
            state=ThesisState(str(payload["state"])),
            version=int(payload["version"]),
            approved_by=str(payload["approved_by"]),
            approval_reason=str(payload["approval_reason"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])),
            last_actor=str(payload["last_actor"]),
            last_reason=str(payload["last_reason"]),
        )


def transition_thesis(
    thesis: TradingThesis,
    *,
    to_state: ThesisState,
    actor: str,
    reason: str,
    changed_at: datetime,
) -> TradingThesis:
    if thesis.state is not ThesisState.APPROVED:
        raise ValueError("only APPROVED Thesis can transition")
    if to_state is ThesisState.APPROVED:
        raise ValueError("Thesis transition must leave APPROVED")
    return replace(
        thesis,
        state=to_state,
        version=thesis.version + 1,
        updated_at=changed_at,
        last_actor=actor,
        last_reason=reason,
    )


def validate_thesis_transition(before: TradingThesis, after: TradingThesis) -> None:
    expected = transition_thesis(
        before,
        to_state=after.state,
        actor=after.last_actor,
        reason=after.last_reason,
        changed_at=after.updated_at,
    )
    if expected != after:
        raise ValueError("invalid TradingThesis transition")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Thesis value must be an object")
    return value
