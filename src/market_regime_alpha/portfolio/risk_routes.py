"""Explicit separation of increasing Risk authority and reducing execution gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    PortfolioDecisionId,
    PositionBookId,
    PositionSnapshotId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
    ProposedTradeDelta,
)
from market_regime_alpha.portfolio.lifecycle import RiskDecisionState
from market_regime_alpha.position.authority import (
    T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA,
    PositionSellabilityState,
    PositionSnapshot,
    PositionState,
)


RISK_REDUCING_GATE_CONFIG_SCHEMA = "risk-reducing-gate-configuration-v1"
REDUCING_EXECUTION_OBSERVATION_SCHEMA = "reducing-execution-observation-v1"
RISK_REDUCING_DECISION_SCHEMA = "risk-reducing-decision-v1"
RISK_INCREASING_DECISION_SCHEMA = "risk-increasing-decision-reference-v1"


class RiskChangeKind(str, Enum):
    OPEN = "OPEN"
    ADD = "ADD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class ExecutionConstraintState(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    SUSPENDED = "SUSPENDED"
    PRICE_LIMIT_BLOCKED = "PRICE_LIMIT_BLOCKED"
    UNKNOWN = "UNKNOWN"


class RiskReducingDecisionState(str, Enum):
    PERMITTED_FOR_MANUAL_CONFIRMATION = "PERMITTED_FOR_MANUAL_CONFIRMATION"
    BLOCKED = "BLOCKED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class RiskReducingGateConfiguration:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    profile_id: str
    maximum_position_age_seconds: float
    maximum_liquidity_participation: float

    def __post_init__(self) -> None:
        if self.schema_version != RISK_REDUCING_GATE_CONFIG_SCHEMA:
            raise ValueError("unsupported Risk reducing configuration")
        _text("profile_id", self.profile_id)
        if (
            not isfinite(self.maximum_position_age_seconds)
            or self.maximum_position_age_seconds <= 0.0
            or not isfinite(self.maximum_liquidity_participation)
            or not 0.0 < self.maximum_liquidity_participation <= 1.0
        ):
            raise ValueError("Risk reducing configuration values are invalid")
        require_sha256("configuration_hash", self.configuration_hash)
        if canonical_hash(self.semantic_payload()) != self.configuration_hash:
            raise ValueError("Risk reducing configuration hash mismatch")
        if self.configuration_id != _content_id(
            "risk-reducing-config", self.configuration_hash
        ):
            raise ValueError("Risk reducing configuration identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "maximum_position_age_seconds": self.maximum_position_age_seconds,
            "maximum_liquidity_participation": (
                self.maximum_liquidity_participation
            ),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "configuration_id": str(self.configuration_id),
            **self.semantic_payload(),
            "configuration_hash": self.configuration_hash,
        }

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        maximum_position_age_seconds: float,
        maximum_liquidity_participation: float,
    ) -> RiskReducingGateConfiguration:
        semantic = {
            "schema_version": RISK_REDUCING_GATE_CONFIG_SCHEMA,
            "profile_id": profile_id,
            "maximum_position_age_seconds": maximum_position_age_seconds,
            "maximum_liquidity_participation": maximum_liquidity_participation,
        }
        digest = canonical_hash(semantic)
        return cls(
            schema_version=RISK_REDUCING_GATE_CONFIG_SCHEMA,
            configuration_id=_content_id("risk-reducing-config", digest),
            configuration_hash=digest,
            profile_id=profile_id,
            maximum_position_age_seconds=maximum_position_age_seconds,
            maximum_liquidity_participation=maximum_liquidity_participation,
        )

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RiskReducingGateConfiguration:
        _fields(
            payload,
            {
                "schema_version",
                "configuration_id",
                "configuration_hash",
                "profile_id",
                "maximum_position_age_seconds",
                "maximum_liquidity_participation",
            },
            "RiskReducingGateConfiguration",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            profile_id=str(payload["profile_id"]),
            maximum_position_age_seconds=float(
                payload["maximum_position_age_seconds"]
            ),
            maximum_liquidity_participation=float(
                payload["maximum_liquidity_participation"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ReducingExecutionObservation:
    schema_version: str
    observation_id: ArtifactId
    content_hash: str
    symbol: str
    session_date: date
    state: ExecutionConstraintState
    reference_price: float
    average_daily_volume: int
    source_artifact_id: ArtifactId
    source_artifact_hash: str
    availability_time: datetime
    reason_code: str

    def __post_init__(self) -> None:
        if self.schema_version != REDUCING_EXECUTION_OBSERVATION_SCHEMA:
            raise ValueError("unsupported reducing execution observation")
        _text("symbol", self.symbol)
        _text("reason_code", self.reason_code)
        if (
            not isfinite(self.reference_price)
            or self.reference_price <= 0.0
            or self.average_daily_volume <= 0
        ):
            raise ValueError("reducing execution observation values are invalid")
        if self.availability_time.tzinfo is None:
            raise ValueError("execution observation availability must be aware")
        require_sha256("source_artifact_hash", self.source_artifact_hash)
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("reducing execution observation hash mismatch")
        if self.observation_id != _content_id(
            "reducing-execution-observation", self.content_hash
        ):
            raise ValueError("reducing execution observation identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "state": self.state.value,
            "reference_price": self.reference_price,
            "average_daily_volume": self.average_daily_volume,
            "source_artifact_id": str(self.source_artifact_id),
            "source_artifact_hash": self.source_artifact_hash,
            "availability_time": self.availability_time.isoformat(),
            "reason_code": self.reason_code,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            **self.semantic_payload(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        session_date: date,
        state: ExecutionConstraintState,
        reference_price: float,
        average_daily_volume: int,
        source_artifact_id: ArtifactId,
        source_artifact_hash: str,
        availability_time: datetime,
        reason_code: str,
    ) -> ReducingExecutionObservation:
        semantic = {
            "schema_version": REDUCING_EXECUTION_OBSERVATION_SCHEMA,
            "symbol": symbol,
            "session_date": session_date.isoformat(),
            "state": state.value,
            "reference_price": reference_price,
            "average_daily_volume": average_daily_volume,
            "source_artifact_id": str(source_artifact_id),
            "source_artifact_hash": source_artifact_hash,
            "availability_time": availability_time.isoformat(),
            "reason_code": reason_code,
        }
        digest = canonical_hash(semantic)
        return cls(
            schema_version=REDUCING_EXECUTION_OBSERVATION_SCHEMA,
            observation_id=_content_id("reducing-execution-observation", digest),
            content_hash=digest,
            symbol=symbol,
            session_date=session_date,
            state=state,
            reference_price=reference_price,
            average_daily_volume=average_daily_volume,
            source_artifact_id=source_artifact_id,
            source_artifact_hash=source_artifact_hash,
            availability_time=availability_time,
            reason_code=reason_code,
        )

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ReducingExecutionObservation:
        _fields(
            payload,
            {
                "schema_version",
                "observation_id",
                "content_hash",
                "symbol",
                "session_date",
                "state",
                "reference_price",
                "average_daily_volume",
                "source_artifact_id",
                "source_artifact_hash",
                "availability_time",
                "reason_code",
            },
            "ReducingExecutionObservation",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            observation_id=ArtifactId(str(payload["observation_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            session_date=date.fromisoformat(str(payload["session_date"])),
            state=ExecutionConstraintState(str(payload["state"])),
            reference_price=float(payload["reference_price"]),
            average_daily_volume=int(payload["average_daily_volume"]),
            source_artifact_id=ArtifactId(str(payload["source_artifact_id"])),
            source_artifact_hash=str(payload["source_artifact_hash"]),
            availability_time=datetime.fromisoformat(
                str(payload["availability_time"])
            ),
            reason_code=str(payload["reason_code"]),
        )


@dataclass(frozen=True, slots=True)
class RiskReducingDecision:
    schema_version: str
    decision_id: ArtifactId
    content_hash: str
    action: RiskChangeKind
    position_snapshot_id: PositionSnapshotId
    position_snapshot_hash: str
    position_snapshot_version: int
    position_book_id: PositionBookId
    thesis_id: ThesisId
    symbol: str
    current_quantity: int
    available_quantity: int
    target_quantity: int
    order_quantity: int
    observation_id: ArtifactId
    observation_hash: str
    configuration_id: ArtifactId
    configuration_hash: str
    state: RiskReducingDecisionState
    reason_codes: tuple[str, ...]
    actor: str
    reason: str
    assessed_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != RISK_REDUCING_DECISION_SCHEMA:
            raise ValueError("unsupported RiskReducingDecision schema")
        if self.action not in {RiskChangeKind.REDUCE, RiskChangeKind.EXIT}:
            raise ValueError("RiskReducingDecision action must reduce risk")
        for label, value in (("symbol", self.symbol), ("actor", self.actor), ("reason", self.reason)):
            _text(label, value)
        if min(
            self.current_quantity,
            self.available_quantity,
            self.target_quantity,
            self.order_quantity,
            self.position_snapshot_version,
        ) < 0:
            raise ValueError("RiskReducingDecision quantities are invalid")
        if self.assessed_at.tzinfo is None:
            raise ValueError("RiskReducingDecision assessed_at must be aware")
        for label, value in (
            ("position_snapshot_hash", self.position_snapshot_hash),
            ("observation_hash", self.observation_hash),
            ("configuration_hash", self.configuration_hash),
            ("content_hash", self.content_hash),
        ):
            require_sha256(label, value)
        if not self.reason_codes:
            raise ValueError("RiskReducingDecision requires reason codes")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("RiskReducingDecision hash mismatch")
        if self.decision_id != _content_id("risk-reducing-decision", self.content_hash):
            raise ValueError("RiskReducingDecision identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action.value,
            "position_snapshot_id": str(self.position_snapshot_id),
            "position_snapshot_hash": self.position_snapshot_hash,
            "position_snapshot_version": self.position_snapshot_version,
            "position_book_id": str(self.position_book_id),
            "thesis_id": str(self.thesis_id),
            "symbol": self.symbol,
            "current_quantity": self.current_quantity,
            "available_quantity": self.available_quantity,
            "target_quantity": self.target_quantity,
            "order_quantity": self.order_quantity,
            "observation_id": str(self.observation_id),
            "observation_hash": self.observation_hash,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "state": self.state.value,
            "reason_codes": list(self.reason_codes),
            "actor": self.actor,
            "reason": self.reason,
            "assessed_at": self.assessed_at.isoformat(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            **self.semantic_payload(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RiskReducingDecision:
        expected = {
            "decision_id",
            "schema_version",
            "content_hash",
            "action",
            "position_snapshot_id",
            "position_snapshot_hash",
            "position_snapshot_version",
            "position_book_id",
            "thesis_id",
            "symbol",
            "current_quantity",
            "available_quantity",
            "target_quantity",
            "order_quantity",
            "observation_id",
            "observation_hash",
            "configuration_id",
            "configuration_hash",
            "state",
            "reason_codes",
            "actor",
            "reason",
            "assessed_at",
        }
        _fields(payload, expected, "RiskReducingDecision")
        reasons = payload["reason_codes"]
        if not isinstance(reasons, list):
            raise ValueError("RiskReducingDecision reason codes must be an array")
        return cls(
            schema_version=str(payload["schema_version"]),
            decision_id=ArtifactId(str(payload["decision_id"])),
            content_hash=str(payload["content_hash"]),
            action=RiskChangeKind(str(payload["action"])),
            position_snapshot_id=PositionSnapshotId(
                str(payload["position_snapshot_id"])
            ),
            position_snapshot_hash=str(payload["position_snapshot_hash"]),
            position_snapshot_version=int(payload["position_snapshot_version"]),
            position_book_id=PositionBookId(str(payload["position_book_id"])),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            symbol=str(payload["symbol"]),
            current_quantity=int(payload["current_quantity"]),
            available_quantity=int(payload["available_quantity"]),
            target_quantity=int(payload["target_quantity"]),
            order_quantity=int(payload["order_quantity"]),
            observation_id=ArtifactId(str(payload["observation_id"])),
            observation_hash=str(payload["observation_hash"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            state=RiskReducingDecisionState(str(payload["state"])),
            reason_codes=tuple(str(item) for item in reasons),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            assessed_at=datetime.fromisoformat(str(payload["assessed_at"])),
        )


@dataclass(frozen=True, slots=True)
class RiskIncreasingDecision:
    schema_version: str
    decision_id: ArtifactId
    action: RiskChangeKind
    thesis_id: ThesisId
    portfolio_decision_id: PortfolioDecisionId
    risk_decision_id: RiskDecisionId
    risk_decision_hash: str
    trade_delta_hash: str
    created_at: datetime
    content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != RISK_INCREASING_DECISION_SCHEMA:
            raise ValueError("unsupported RiskIncreasingDecision schema")
        if self.action not in {RiskChangeKind.OPEN, RiskChangeKind.ADD}:
            raise ValueError("RiskIncreasingDecision action must increase risk")
        require_sha256("risk_decision_hash", self.risk_decision_hash)
        require_sha256("trade_delta_hash", self.trade_delta_hash)
        require_sha256("content_hash", self.content_hash)
        if self.created_at.tzinfo is None:
            raise ValueError("RiskIncreasingDecision created_at must be aware")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("RiskIncreasingDecision hash mismatch")
        if self.decision_id != _content_id("risk-increasing-reference", self.content_hash):
            raise ValueError("RiskIncreasingDecision identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action.value,
            "thesis_id": str(self.thesis_id),
            "portfolio_decision_id": str(self.portfolio_decision_id),
            "risk_decision_id": str(self.risk_decision_id),
            "risk_decision_hash": self.risk_decision_hash,
            "trade_delta_hash": self.trade_delta_hash,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def create(
        cls,
        *,
        portfolio: CompleteAccountPortfolioDecision,
        risk: CompleteAccountRiskDecision,
        delta: ProposedTradeDelta,
        created_at: datetime,
    ) -> RiskIncreasingDecision:
        if (
            delta.trade_quantity <= 0
            or delta not in portfolio.post_trade.proposed_deltas
            or risk.state is not RiskDecisionState.APPROVED
            or risk.portfolio_decision_id != portfolio.decision_id
            or risk.post_trade_content_hash != portfolio.post_trade.content_hash
        ):
            raise ValueError("increasing risk requires approved complete-account Risk")
        action = RiskChangeKind.OPEN if delta.current_quantity == 0 else RiskChangeKind.ADD
        semantic = {
            "schema_version": RISK_INCREASING_DECISION_SCHEMA,
            "action": action.value,
            "thesis_id": str(delta.thesis_id),
            "portfolio_decision_id": str(portfolio.decision_id),
            "risk_decision_id": str(risk.risk_decision_id),
            "risk_decision_hash": canonical_hash(risk.to_canonical_dict()),
            "trade_delta_hash": canonical_hash(delta.to_canonical_dict()),
            "created_at": created_at.isoformat(),
        }
        digest = canonical_hash(semantic)
        return cls(
            schema_version=RISK_INCREASING_DECISION_SCHEMA,
            decision_id=_content_id("risk-increasing-reference", digest),
            action=action,
            thesis_id=delta.thesis_id,
            portfolio_decision_id=portfolio.decision_id,
            risk_decision_id=risk.risk_decision_id,
            risk_decision_hash=canonical_hash(risk.to_canonical_dict()),
            trade_delta_hash=canonical_hash(delta.to_canonical_dict()),
            created_at=created_at,
            content_hash=digest,
        )


class RiskReducingExecutionGate:
    def assess(
        self,
        *,
        action: RiskChangeKind,
        position: PositionSnapshot,
        target_quantity: int,
        order_quantity: int,
        execution_observation: ReducingExecutionObservation | None,
        configuration: RiskReducingGateConfiguration,
        actor: str,
        reason: str,
        assessed_at: datetime,
    ) -> RiskReducingDecision:
        if action not in {RiskChangeKind.REDUCE, RiskChangeKind.EXIT}:
            raise ValueError("increasing Risk cannot use RiskReducingExecutionGate")
        _text("actor", actor)
        _text("reason", reason)
        if execution_observation is None:
            raise ValueError("reducing execution observation is required")
        if position.position_book_id is None or position.thesis_id is None:
            raise ValueError("risk reduction requires Thesis-scoped Position")
        reasons: set[str] = set()
        insufficient: set[str] = set()
        age = (assessed_at - position.as_of).total_seconds()
        if position.schema_version != T_PLUS_ONE_POSITION_SNAPSHOT_SCHEMA:
            insufficient.add("POSITION_T_PLUS_ONE_AUTHORITY_REQUIRED")
        if age < 0.0:
            insufficient.add("POSITION_NOT_AVAILABLE_AT_ASSESSMENT_TIME")
        elif age > configuration.maximum_position_age_seconds:
            insufficient.add("POSITION_SNAPSHOT_STALE")
        if position.state is PositionState.RECONCILIATION_REQUIRED:
            reasons.add("POSITION_RECONCILIATION_REQUIRED")
        current = position.total_quantity
        available = position.available_quantity or 0
        if target_quantity > current:
            reasons.add("RISK_REDUCTION_WOULD_INCREASE_POSITION")
        if target_quantity < 0:
            reasons.add("NEGATIVE_TARGET_QUANTITY_FORBIDDEN")
        expected_order = current - target_quantity
        if order_quantity > current:
            reasons.add("ORDER_QUANTITY_EXCEEDS_POSITION")
        if order_quantity != expected_order:
            reasons.add("REDUCING_ORDER_QUANTITY_MISMATCH")
        if action is RiskChangeKind.EXIT and target_quantity != 0:
            reasons.add("EXIT_REQUIRES_ZERO_TARGET")
        if action is RiskChangeKind.REDUCE and not 0 < target_quantity < current:
            reasons.add("REDUCE_REQUIRES_STRICTLY_LOWER_POSITIVE_TARGET")
        if order_quantity <= 0:
            reasons.add("REDUCING_ORDER_QUANTITY_MUST_BE_POSITIVE")
        if order_quantity > available:
            reasons.add("T_PLUS_ONE_NOT_SELLABLE")
        if position.sellability_state is PositionSellabilityState.SUSPENDED:
            reasons.add("EXIT_BLOCKED_BY_MARKET_CONSTRAINT")
        elif position.sellability_state is PositionSellabilityState.DATA_INSUFFICIENT:
            insufficient.add("EXECUTION_STATE_UNKNOWN")
        if (
            execution_observation.symbol != position.symbol
            or execution_observation.session_date != position.as_of_session_date
        ):
            insufficient.add("EXECUTION_OBSERVATION_SCOPE_MISMATCH")
        if execution_observation.availability_time > assessed_at:
            insufficient.add("EXECUTION_OBSERVATION_UNAVAILABLE")
        if execution_observation.state in {
            ExecutionConstraintState.SUSPENDED,
            ExecutionConstraintState.PRICE_LIMIT_BLOCKED,
        }:
            reasons.add("EXIT_BLOCKED_BY_MARKET_CONSTRAINT")
        elif execution_observation.state is ExecutionConstraintState.UNKNOWN:
            insufficient.add("EXECUTION_STATE_UNKNOWN")
        participation = order_quantity / execution_observation.average_daily_volume
        if participation > configuration.maximum_liquidity_participation:
            reasons.add("LIQUIDITY_PARTICIPATION_EXCEEDED")
        if insufficient:
            state = RiskReducingDecisionState.DATA_INSUFFICIENT
            reason_codes = tuple(sorted(insufficient | reasons))
        elif reasons:
            state = RiskReducingDecisionState.BLOCKED
            reason_codes = tuple(sorted(reasons))
        else:
            state = RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION
            reason_codes = ("STRICT_RISK_REDUCTION_PERMITTED",)
        position_hash = canonical_hash(position.to_canonical_dict())
        semantic = {
            "schema_version": RISK_REDUCING_DECISION_SCHEMA,
            "action": action.value,
            "position_snapshot_id": str(position.snapshot_id),
            "position_snapshot_hash": position_hash,
            "position_snapshot_version": position.version,
            "position_book_id": str(position.position_book_id),
            "thesis_id": str(position.thesis_id),
            "symbol": position.symbol,
            "current_quantity": current,
            "available_quantity": available,
            "target_quantity": target_quantity,
            "order_quantity": order_quantity,
            "observation_id": str(execution_observation.observation_id),
            "observation_hash": execution_observation.content_hash,
            "configuration_id": str(configuration.configuration_id),
            "configuration_hash": configuration.configuration_hash,
            "state": state.value,
            "reason_codes": list(reason_codes),
            "actor": actor,
            "reason": reason,
            "assessed_at": assessed_at.isoformat(),
        }
        digest = canonical_hash(semantic)
        return RiskReducingDecision(
            schema_version=RISK_REDUCING_DECISION_SCHEMA,
            decision_id=_content_id("risk-reducing-decision", digest),
            content_hash=digest,
            action=action,
            position_snapshot_id=position.snapshot_id,
            position_snapshot_hash=position_hash,
            position_snapshot_version=position.version,
            position_book_id=position.position_book_id,
            thesis_id=position.thesis_id,
            symbol=position.symbol,
            current_quantity=current,
            available_quantity=available,
            target_quantity=target_quantity,
            order_quantity=order_quantity,
            observation_id=execution_observation.observation_id,
            observation_hash=execution_observation.content_hash,
            configuration_id=configuration.configuration_id,
            configuration_hash=configuration.configuration_hash,
            state=state,
            reason_codes=reason_codes,
            actor=actor,
            reason=reason,
            assessed_at=assessed_at,
        )


def _content_id(prefix: str, digest: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")
