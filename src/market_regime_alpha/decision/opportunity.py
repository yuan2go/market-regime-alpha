"""TradingOpportunity aggregate between research evidence and human approval."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, ModelId, OpportunityId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.evidence.canonical import require_sha256


TRADING_OPPORTUNITY_SCHEMA = "trading-opportunity-v1"


class OpportunityState(str, Enum):
    OPEN = "OPEN"
    CONFIRMED_TO_THESIS = "CONFIRMED_TO_THESIS"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class DecisionEvidenceReference:
    artifact_type: str
    artifact_id: ArtifactId
    content_hash: str
    status: str

    def __post_init__(self) -> None:
        for label, text_value in (
            ("artifact_type", self.artifact_type),
            ("status", self.status),
        ):
            if not text_value or text_value != text_value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        require_sha256("content_hash", self.content_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.content_hash,
            "status": self.status,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> DecisionEvidenceReference:
        if set(payload) != {"artifact_type", "artifact_id", "content_hash", "status"}:
            raise ValueError("DecisionEvidenceReference fields mismatch")
        return cls(
            artifact_type=str(payload["artifact_type"]),
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            content_hash=str(payload["content_hash"]),
            status=str(payload["status"]),
        )


@dataclass(frozen=True, slots=True)
class DecisionModelReference:
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_hash: str

    def __post_init__(self) -> None:
        if not self.model_version or self.model_version != self.model_version.strip():
            raise ValueError("model_version must be a non-empty trimmed string")
        require_sha256("configuration_hash", self.configuration_hash)

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> DecisionModelReference:
        if set(payload) != {
            "model_id",
            "model_version",
            "configuration_id",
            "configuration_hash",
        }:
            raise ValueError("DecisionModelReference fields mismatch")
        return cls(
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
        )


@dataclass(frozen=True, slots=True)
class TradingOpportunity:
    schema_version: str
    opportunity_id: OpportunityId
    symbol: str
    candidate_set: DecisionEvidenceReference
    signal_snapshot: DecisionEvidenceReference
    path_forecast: DecisionEvidenceReference
    decision_time: DecisionTime
    signal_model: DecisionModelReference
    forecast_model: DecisionModelReference
    valid_until: datetime
    state: OpportunityState
    version: int
    created_at: datetime
    created_by: str
    creation_reason: str
    updated_at: datetime
    last_actor: str
    last_reason: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != TRADING_OPPORTUNITY_SCHEMA:
            raise ValueError("unsupported TradingOpportunity schema")
        for label, text_value in (
            ("symbol", self.symbol),
            ("created_by", self.created_by),
            ("creation_reason", self.creation_reason),
            ("last_actor", self.last_actor),
            ("last_reason", self.last_reason),
        ):
            if not text_value or text_value != text_value.strip():
                raise ValueError(f"{label} must be a non-empty trimmed string")
        for label, datetime_value in (
            ("valid_until", self.valid_until),
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
        ):
            if (
                datetime_value.tzinfo is None
                or datetime_value.utcoffset() is None
            ):
                raise ValueError(f"{label} must be timezone-aware")
        if self.valid_until <= self.decision_time.value:
            raise ValueError("Opportunity valid_until must follow DecisionTime")
        if self.created_at < self.decision_time.value:
            raise ValueError("Opportunity creation cannot precede DecisionTime")
        if self.updated_at < self.created_at:
            raise ValueError("Opportunity updated_at cannot precede creation")
        if self.version < 0:
            raise ValueError("Opportunity version cannot be negative")
        if self.state is OpportunityState.OPEN and self.version != 0:
            raise ValueError("OPEN Opportunity must be initial version 0")
        if self.state is not OpportunityState.OPEN and self.version <= 0:
            raise ValueError("terminal Opportunity requires a transition version")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("Opportunity reason_codes must be unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "opportunity_id": str(self.opportunity_id),
            "symbol": self.symbol,
            "candidate_set": self.candidate_set.to_canonical_dict(),
            "signal_snapshot": self.signal_snapshot.to_canonical_dict(),
            "path_forecast": self.path_forecast.to_canonical_dict(),
            "decision_time": self.decision_time.isoformat(),
            "signal_model": self.signal_model.to_canonical_dict(),
            "forecast_model": self.forecast_model.to_canonical_dict(),
            "valid_until": self.valid_until.isoformat(),
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "creation_reason": self.creation_reason,
            "updated_at": self.updated_at.isoformat(),
            "last_actor": self.last_actor,
            "last_reason": self.last_reason,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> TradingOpportunity:
        expected = {
            "schema_version",
            "opportunity_id",
            "symbol",
            "candidate_set",
            "signal_snapshot",
            "path_forecast",
            "decision_time",
            "signal_model",
            "forecast_model",
            "valid_until",
            "state",
            "version",
            "created_at",
            "created_by",
            "creation_reason",
            "updated_at",
            "last_actor",
            "last_reason",
            "reason_codes",
        }
        if set(payload) != expected or not isinstance(payload["reason_codes"], list):
            raise ValueError("TradingOpportunity fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            opportunity_id=OpportunityId(str(payload["opportunity_id"])),
            symbol=str(payload["symbol"]),
            candidate_set=DecisionEvidenceReference.from_canonical_dict(
                _object(payload["candidate_set"])
            ),
            signal_snapshot=DecisionEvidenceReference.from_canonical_dict(
                _object(payload["signal_snapshot"])
            ),
            path_forecast=DecisionEvidenceReference.from_canonical_dict(
                _object(payload["path_forecast"])
            ),
            decision_time=DecisionTime(
                datetime.fromisoformat(str(payload["decision_time"]))
            ),
            signal_model=DecisionModelReference.from_canonical_dict(
                _object(payload["signal_model"])
            ),
            forecast_model=DecisionModelReference.from_canonical_dict(
                _object(payload["forecast_model"])
            ),
            valid_until=datetime.fromisoformat(str(payload["valid_until"])),
            state=OpportunityState(str(payload["state"])),
            version=int(payload["version"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            created_by=str(payload["created_by"]),
            creation_reason=str(payload["creation_reason"]),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])),
            last_actor=str(payload["last_actor"]),
            last_reason=str(payload["last_reason"]),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        )


def transition_opportunity(
    opportunity: TradingOpportunity,
    *,
    to_state: OpportunityState,
    actor: str,
    reason: str,
    changed_at: datetime,
) -> TradingOpportunity:
    if opportunity.state is not OpportunityState.OPEN:
        raise ValueError("only OPEN Opportunity can transition")
    if to_state is OpportunityState.OPEN:
        raise ValueError("Opportunity transition must leave OPEN")
    if to_state is OpportunityState.EXPIRED and changed_at < opportunity.valid_until:
        raise ValueError("Opportunity cannot expire before valid_until")
    return replace(
        opportunity,
        state=to_state,
        version=opportunity.version + 1,
        updated_at=changed_at,
        last_actor=actor,
        last_reason=reason,
        reason_codes=tuple(
            sorted({*opportunity.reason_codes, f"OPPORTUNITY_{to_state.value}"})
        ),
    )


def validate_opportunity_transition(
    before: TradingOpportunity, after: TradingOpportunity
) -> None:
    expected = transition_opportunity(
        before,
        to_state=after.state,
        actor=after.last_actor,
        reason=after.last_reason,
        changed_at=after.updated_at,
    )
    if expected != after:
        raise ValueError("invalid TradingOpportunity transition")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Opportunity value must be an object")
    return value
