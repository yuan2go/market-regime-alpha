"""Independent Holding and Exit assessments over Fill-derived Position state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import (
    ArtifactId,
    ExitAssessmentId,
    HoldingAssessmentId,
    PortfolioDecisionId,
    PositionSnapshotId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.decision.opportunity import DecisionEvidenceReference
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioDecision,
    RiskDecision,
    RiskDecisionState,
)
from market_regime_alpha.portfolio.services import IndependentRiskService
from market_regime_alpha.position.authority import PositionSnapshot, PositionState


POSITION_LIFECYCLE_CONFIG_SCHEMA = "position-lifecycle-config-v1"
HOLDING_ASSESSMENT_SCHEMA = "holding-assessment-v1"
EXIT_ASSESSMENT_SCHEMA = "exit-assessment-v1"


class ThesisHealth(str, Enum):
    HEALTHY = "HEALTHY"
    WEAKENING = "WEAKENING"
    INVALIDATED = "INVALIDATED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class PositionLifecycleAction(str, Enum):
    HOLD = "HOLD"
    ADD = "ADD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    WAIT = "WAIT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class PositionLifecycleConfig:
    profile_id: str
    configuration_id: ArtifactId
    configuration_hash: str
    add_minimum_return: float
    weakening_return_threshold: float
    exit_return_threshold: float
    enable_add_assessment: bool
    market_scope: str
    allowed_side: str
    schema_version: str

    def __post_init__(self) -> None:
        for label, value in (
            ("profile_id", self.profile_id),
            ("market_scope", self.market_scope),
            ("allowed_side", self.allowed_side),
        ):
            _text(label, value)
        if self.schema_version != POSITION_LIFECYCLE_CONFIG_SCHEMA:
            raise ValueError("unsupported PositionLifecycleConfig schema")
        if self.market_scope != "A_SHARE" or self.allowed_side != "LONG_ONLY":
            raise ValueError("PositionLifecycleConfig V1 is A_SHARE LONG_ONLY")
        values = (
            self.add_minimum_return,
            self.weakening_return_threshold,
            self.exit_return_threshold,
        )
        if any(not isfinite(value) or value <= -1.0 for value in values):
            raise ValueError("lifecycle return thresholds must be finite and above -1")
        if not (
            self.exit_return_threshold
            <= self.weakening_return_threshold
            < self.add_minimum_return
        ):
            raise ValueError("lifecycle return thresholds are not ordered")
        require_sha256("configuration_hash", self.configuration_hash)
        if canonical_hash(self.semantic_payload()) != self.configuration_hash:
            raise ValueError("PositionLifecycleConfig hash mismatch")
        digest = self.configuration_hash.split(":", 1)[1]
        if self.configuration_id != ArtifactId(
            f"position-lifecycle-config-{digest[:24]}"
        ):
            raise ValueError("PositionLifecycleConfig identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "add_minimum_return": self.add_minimum_return,
            "weakening_return_threshold": self.weakening_return_threshold,
            "exit_return_threshold": self.exit_return_threshold,
            "enable_add_assessment": self.enable_add_assessment,
            "market_scope": self.market_scope,
            "allowed_side": self.allowed_side,
            "schema_version": self.schema_version,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
        }

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        add_minimum_return: float,
        weakening_return_threshold: float,
        exit_return_threshold: float,
        enable_add_assessment: bool,
        market_scope: str,
        allowed_side: str,
        schema_version: str,
    ) -> PositionLifecycleConfig:
        semantic = {
            "profile_id": profile_id,
            "add_minimum_return": add_minimum_return,
            "weakening_return_threshold": weakening_return_threshold,
            "exit_return_threshold": exit_return_threshold,
            "enable_add_assessment": enable_add_assessment,
            "market_scope": market_scope,
            "allowed_side": allowed_side,
            "schema_version": schema_version,
        }
        digest = canonical_hash(semantic)
        return cls(
            profile_id=profile_id,
            configuration_id=ArtifactId(
                f"position-lifecycle-config-{digest.split(':', 1)[1][:24]}"
            ),
            configuration_hash=digest,
            add_minimum_return=add_minimum_return,
            weakening_return_threshold=weakening_return_threshold,
            exit_return_threshold=exit_return_threshold,
            enable_add_assessment=enable_add_assessment,
            market_scope=market_scope,
            allowed_side=allowed_side,
            schema_version=schema_version,
        )

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PositionLifecycleConfig:
        expected = {
            "profile_id",
            "configuration_id",
            "configuration_hash",
            "add_minimum_return",
            "weakening_return_threshold",
            "exit_return_threshold",
            "enable_add_assessment",
            "market_scope",
            "allowed_side",
            "schema_version",
        }
        if set(payload) != expected or not isinstance(
            payload["enable_add_assessment"], bool
        ):
            raise ValueError("PositionLifecycleConfig fields mismatch")
        return cls(
            profile_id=str(payload["profile_id"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            add_minimum_return=float(payload["add_minimum_return"]),
            weakening_return_threshold=float(
                payload["weakening_return_threshold"]
            ),
            exit_return_threshold=float(payload["exit_return_threshold"]),
            enable_add_assessment=payload["enable_add_assessment"],
            market_scope=str(payload["market_scope"]),
            allowed_side=str(payload["allowed_side"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ThesisHealthObservation:
    symbol: str
    market_price: float
    observed_at: datetime
    availability_time: datetime
    signal_support: bool | None
    theme_support: bool | None
    capital_support: bool | None
    triggered_condition_ids: tuple[str, ...]
    evidence: DecisionEvidenceReference
    missing_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        if not isfinite(self.market_price) or self.market_price <= 0.0:
            raise ValueError("health observation market price must be positive")
        for value in (self.observed_at, self.availability_time):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("health observation times must be timezone-aware")
        if self.availability_time < self.observed_at:
            raise ValueError("health evidence cannot be available before observation")
        if self.triggered_condition_ids != tuple(
            sorted(set(self.triggered_condition_ids))
        ):
            raise ValueError("triggered condition IDs must be sorted and unique")
        if self.missing_reason_codes != tuple(
            sorted(set(self.missing_reason_codes))
        ):
            raise ValueError("missing reason codes must be sorted and unique")
        if self.evidence.status not in {
            "AVAILABLE_FOR_RESEARCH",
            "RESEARCH_READY",
            "VERIFIED_EXPLORATORY",
        }:
            raise ValueError("health assessment requires verified research evidence")
        missing = any(
            value is None
            for value in (
                self.signal_support,
                self.theme_support,
                self.capital_support,
            )
        )
        if missing != bool(self.missing_reason_codes):
            raise ValueError("health missingness and reason codes must agree")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market_price": self.market_price,
            "observed_at": self.observed_at.isoformat(),
            "availability_time": self.availability_time.isoformat(),
            "signal_support": self.signal_support,
            "theme_support": self.theme_support,
            "capital_support": self.capital_support,
            "triggered_condition_ids": list(self.triggered_condition_ids),
            "evidence": self.evidence.to_canonical_dict(),
            "missing_reason_codes": list(self.missing_reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ThesisHealthObservation:
        expected = {
            "symbol",
            "market_price",
            "observed_at",
            "availability_time",
            "signal_support",
            "theme_support",
            "capital_support",
            "triggered_condition_ids",
            "evidence",
            "missing_reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("ThesisHealthObservation fields mismatch")
        triggered = payload["triggered_condition_ids"]
        reasons = payload["missing_reason_codes"]
        evidence = payload["evidence"]
        if not isinstance(triggered, list) or not isinstance(reasons, list):
            raise ValueError("ThesisHealthObservation array field mismatch")
        if not isinstance(evidence, dict):
            raise ValueError("ThesisHealthObservation evidence must be an object")
        return cls(
            symbol=str(payload["symbol"]),
            market_price=float(payload["market_price"]),
            observed_at=datetime.fromisoformat(str(payload["observed_at"])),
            availability_time=datetime.fromisoformat(
                str(payload["availability_time"])
            ),
            signal_support=_optional_bool(payload["signal_support"]),
            theme_support=_optional_bool(payload["theme_support"]),
            capital_support=_optional_bool(payload["capital_support"]),
            triggered_condition_ids=tuple(str(item) for item in triggered),
            evidence=DecisionEvidenceReference.from_canonical_dict(evidence),
            missing_reason_codes=tuple(str(item) for item in reasons),
        )


@dataclass(frozen=True, slots=True)
class HoldingAssessment:
    schema_version: str
    assessment_id: HoldingAssessmentId
    thesis_id: ThesisId
    thesis_version: int
    position_snapshot_id: PositionSnapshotId
    position_version: int
    configuration_id: ArtifactId
    configuration_hash: str
    evidence: DecisionEvidenceReference
    thesis_health: ThesisHealth
    action: PositionLifecycleAction
    unrealized_return: float
    add_portfolio_decision_id: PortfolioDecisionId | None
    add_risk_decision_id: RiskDecisionId | None
    assessed_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != HOLDING_ASSESSMENT_SCHEMA:
            raise ValueError("unsupported HoldingAssessment schema")
        if self.action not in {
            PositionLifecycleAction.HOLD,
            PositionLifecycleAction.ADD,
            PositionLifecycleAction.WAIT,
            PositionLifecycleAction.DATA_INSUFFICIENT,
        }:
            raise ValueError("Holding model emitted an Exit-only action")
        if self.action is PositionLifecycleAction.ADD:
            if self.thesis_health is not ThesisHealth.HEALTHY:
                raise ValueError("ADD requires a healthy Thesis")
            if self.add_portfolio_decision_id is None or self.add_risk_decision_id is None:
                raise ValueError("ADD requires independently approved risk authority")
        elif self.add_portfolio_decision_id is not None or self.add_risk_decision_id is not None:
            raise ValueError("non-ADD HoldingAssessment cannot bind add authority")
        _assessment_common(self)
        expected = _holding_id(self.semantic_payload())
        if self.assessment_id != expected:
            raise ValueError("HoldingAssessment content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thesis_id": str(self.thesis_id),
            "thesis_version": self.thesis_version,
            "position_snapshot_id": str(self.position_snapshot_id),
            "position_version": self.position_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "evidence": self.evidence.to_canonical_dict(),
            "thesis_health": self.thesis_health.value,
            "action": self.action.value,
            "unrealized_return": self.unrealized_return,
            "add_portfolio_decision_id": (
                str(self.add_portfolio_decision_id)
                if self.add_portfolio_decision_id is not None
                else None
            ),
            "add_risk_decision_id": (
                str(self.add_risk_decision_id)
                if self.add_risk_decision_id is not None
                else None
            ),
            "assessed_at": self.assessed_at.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"assessment_id": str(self.assessment_id), **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> HoldingAssessment:
        expected = {
            "assessment_id",
            "schema_version",
            "thesis_id",
            "thesis_version",
            "position_snapshot_id",
            "position_version",
            "configuration_id",
            "configuration_hash",
            "evidence",
            "thesis_health",
            "action",
            "unrealized_return",
            "add_portfolio_decision_id",
            "add_risk_decision_id",
            "assessed_at",
            "actor",
            "reason",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("HoldingAssessment fields mismatch")
        semantic = {key: value for key, value in payload.items() if key != "assessment_id"}
        return cls(
            assessment_id=HoldingAssessmentId(str(payload["assessment_id"])),
            **_holding_kwargs(semantic),
        )


@dataclass(frozen=True, slots=True)
class ExitAssessment:
    schema_version: str
    assessment_id: ExitAssessmentId
    thesis_id: ThesisId
    thesis_version: int
    position_snapshot_id: PositionSnapshotId
    position_version: int
    configuration_id: ArtifactId
    configuration_hash: str
    evidence: DecisionEvidenceReference
    thesis_health: ThesisHealth
    action: PositionLifecycleAction
    unrealized_return: float
    requires_portfolio_risk: bool
    assessed_at: datetime
    actor: str
    reason: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != EXIT_ASSESSMENT_SCHEMA:
            raise ValueError("unsupported ExitAssessment schema")
        if self.action not in {
            PositionLifecycleAction.REDUCE,
            PositionLifecycleAction.EXIT,
            PositionLifecycleAction.WAIT,
            PositionLifecycleAction.DATA_INSUFFICIENT,
        }:
            raise ValueError("Exit model emitted a Holding-only action")
        must_risk = self.action in {
            PositionLifecycleAction.REDUCE,
            PositionLifecycleAction.EXIT,
        }
        if self.requires_portfolio_risk is not must_risk:
            raise ValueError("Exit action risk requirement mismatch")
        _assessment_common(self)
        expected = _exit_id(self.semantic_payload())
        if self.assessment_id != expected:
            raise ValueError("ExitAssessment content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "thesis_id": str(self.thesis_id),
            "thesis_version": self.thesis_version,
            "position_snapshot_id": str(self.position_snapshot_id),
            "position_version": self.position_version,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
            "evidence": self.evidence.to_canonical_dict(),
            "thesis_health": self.thesis_health.value,
            "action": self.action.value,
            "unrealized_return": self.unrealized_return,
            "requires_portfolio_risk": self.requires_portfolio_risk,
            "assessed_at": self.assessed_at.isoformat(),
            "actor": self.actor,
            "reason": self.reason,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"assessment_id": str(self.assessment_id), **self.semantic_payload()}

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> ExitAssessment:
        expected = {
            "assessment_id",
            "schema_version",
            "thesis_id",
            "thesis_version",
            "position_snapshot_id",
            "position_version",
            "configuration_id",
            "configuration_hash",
            "evidence",
            "thesis_health",
            "action",
            "unrealized_return",
            "requires_portfolio_risk",
            "assessed_at",
            "actor",
            "reason",
            "reason_codes",
        }
        evidence = payload.get("evidence")
        reasons = payload.get("reason_codes")
        if (
            set(payload) != expected
            or not isinstance(evidence, dict)
            or not isinstance(reasons, list)
            or not isinstance(payload["requires_portfolio_risk"], bool)
        ):
            raise ValueError("ExitAssessment fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            assessment_id=ExitAssessmentId(str(payload["assessment_id"])),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            thesis_version=int(payload["thesis_version"]),
            position_snapshot_id=PositionSnapshotId(
                str(payload["position_snapshot_id"])
            ),
            position_version=int(payload["position_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            evidence=DecisionEvidenceReference.from_canonical_dict(evidence),
            thesis_health=ThesisHealth(str(payload["thesis_health"])),
            action=PositionLifecycleAction(str(payload["action"])),
            unrealized_return=float(payload["unrealized_return"]),
            requires_portfolio_risk=payload["requires_portfolio_risk"],
            assessed_at=datetime.fromisoformat(str(payload["assessed_at"])),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            reason_codes=tuple(str(item) for item in reasons),
        )


class ThesisHealthEvaluator:
    def evaluate(
        self,
        thesis: TradingThesis,
        position: PositionSnapshot,
        observation: ThesisHealthObservation,
        *,
        assessed_at: datetime,
    ) -> tuple[ThesisHealth, tuple[str, ...]]:
        _validate_inputs(thesis, position, observation, assessed_at)
        if position.state is PositionState.RECONCILIATION_REQUIRED:
            return ThesisHealth.DATA_INSUFFICIENT, (
                "POSITION_RECONCILIATION_REQUIRED",
            )
        if observation.missing_reason_codes:
            return ThesisHealth.DATA_INSUFFICIENT, observation.missing_reason_codes
        conditions = {item.condition_id for item in thesis.invalidation_conditions}
        unknown = set(observation.triggered_condition_ids) - conditions
        if unknown:
            raise ValueError("health observation references unknown invalidation condition")
        if (
            thesis.state is not ThesisState.APPROVED
            or assessed_at >= thesis.time_invalidation
            or observation.triggered_condition_ids
        ):
            return ThesisHealth.INVALIDATED, ("THESIS_INVALIDATION_TRIGGERED",)
        supports = (
            observation.signal_support,
            observation.theme_support,
            observation.capital_support,
        )
        if any(value is False for value in supports):
            return ThesisHealth.WEAKENING, ("THESIS_SUPPORT_WEAKENING",)
        return ThesisHealth.HEALTHY, ("THESIS_SUPPORT_CONFIRMED",)


@dataclass(frozen=True, slots=True)
class ResolvedThesisHealthContext:
    """Internal seam shared by legacy V1 and strict V2 assessment paths."""

    symbol: str
    health: ThesisHealth
    market_price: float
    evidence: DecisionEvidenceReference
    reason_codes: tuple[str, ...]
    observed_at: datetime
    availability_time: datetime

    def __post_init__(self) -> None:
        _text("resolved health symbol", self.symbol)
        if not isfinite(self.market_price) or self.market_price <= 0.0:
            raise ValueError("resolved health market price must be positive")
        for value in (self.observed_at, self.availability_time):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("resolved health times must be timezone-aware")
        if self.availability_time < self.observed_at:
            raise ValueError("resolved health availability cannot precede observation")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("resolved health reason codes must be sorted and unique")


class HoldingAssessmentModel:
    """Holding role; it cannot emit REDUCE or EXIT."""

    def assess(
        self,
        thesis: TradingThesis,
        position: PositionSnapshot,
        observation: ThesisHealthObservation,
        configuration: PositionLifecycleConfig,
        *,
        assessed_at: datetime,
        actor: str,
        reason: str,
        add_portfolio: PortfolioDecision | None = None,
        add_risk: RiskDecision | None = None,
    ) -> HoldingAssessment:
        health, health_reasons = ThesisHealthEvaluator().evaluate(
            thesis, position, observation, assessed_at=assessed_at
        )
        context = ResolvedThesisHealthContext(
            symbol=observation.symbol,
            health=health,
            market_price=observation.market_price,
            evidence=observation.evidence,
            reason_codes=tuple(sorted(set(health_reasons))),
            observed_at=observation.observed_at,
            availability_time=observation.availability_time,
        )
        return self.assess_resolved(
            thesis,
            position,
            context,
            configuration,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
            add_portfolio=add_portfolio,
            add_risk=add_risk,
        )

    def assess_resolved(
        self,
        thesis: TradingThesis,
        position: PositionSnapshot,
        health_context: ResolvedThesisHealthContext,
        configuration: PositionLifecycleConfig,
        *,
        assessed_at: datetime,
        actor: str,
        reason: str,
        add_portfolio: PortfolioDecision | None = None,
        add_risk: RiskDecision | None = None,
    ) -> HoldingAssessment:
        _validate_resolved_inputs(thesis, position, health_context, assessed_at)
        health = health_context.health
        health_reasons = health_context.reason_codes
        unrealized = _unrealized_return(position, health_context.market_price)
        portfolio_id: PortfolioDecisionId | None = None
        risk_id: RiskDecisionId | None = None
        if health is ThesisHealth.DATA_INSUFFICIENT:
            action = PositionLifecycleAction.DATA_INSUFFICIENT
            reasons = health_reasons
        elif health is ThesisHealth.INVALIDATED:
            action = PositionLifecycleAction.WAIT
            reasons = (*health_reasons, "EXIT_ROLE_MUST_ASSESS_INVALIDATED_THESIS")
        elif health is ThesisHealth.WEAKENING:
            action = PositionLifecycleAction.WAIT
            reasons = health_reasons
        elif (
            configuration.enable_add_assessment
            and unrealized >= configuration.add_minimum_return
        ):
            authority_reason = _validate_add_authority(
                thesis, position, add_portfolio, add_risk, assessed_at
            )
            if authority_reason is None:
                assert add_portfolio is not None and add_risk is not None
                action = PositionLifecycleAction.ADD
                portfolio_id = add_portfolio.decision_id
                risk_id = add_risk.risk_decision_id
                reasons = ("ADD_REAUTHORIZED_BY_INDEPENDENT_RISK",)
            else:
                action = PositionLifecycleAction.WAIT
                reasons = (authority_reason,)
        else:
            action = PositionLifecycleAction.HOLD
            reasons = ("HEALTHY_THESIS_WITHIN_EXPLICIT_HOLDING_PROFILE",)
        semantic = _holding_semantic(
            thesis=thesis,
            position=position,
            configuration=configuration,
            evidence=health_context.evidence,
            health=health,
            action=action,
            unrealized=unrealized,
            portfolio_id=portfolio_id,
            risk_id=risk_id,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
            reason_codes=tuple(sorted(set(reasons))),
        )
        return HoldingAssessment(
            assessment_id=_holding_id(semantic),
            **_holding_kwargs(semantic),
        )


class ExitAssessmentModel:
    """Exit role; it cannot emit HOLD or ADD."""

    def assess(
        self,
        thesis: TradingThesis,
        position: PositionSnapshot,
        observation: ThesisHealthObservation,
        configuration: PositionLifecycleConfig,
        *,
        assessed_at: datetime,
        actor: str,
        reason: str,
    ) -> ExitAssessment:
        health, health_reasons = ThesisHealthEvaluator().evaluate(
            thesis, position, observation, assessed_at=assessed_at
        )
        context = ResolvedThesisHealthContext(
            symbol=observation.symbol,
            health=health,
            market_price=observation.market_price,
            evidence=observation.evidence,
            reason_codes=tuple(sorted(set(health_reasons))),
            observed_at=observation.observed_at,
            availability_time=observation.availability_time,
        )
        return self.assess_resolved(
            thesis,
            position,
            context,
            configuration,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
        )

    def assess_resolved(
        self,
        thesis: TradingThesis,
        position: PositionSnapshot,
        health_context: ResolvedThesisHealthContext,
        configuration: PositionLifecycleConfig,
        *,
        assessed_at: datetime,
        actor: str,
        reason: str,
    ) -> ExitAssessment:
        _validate_resolved_inputs(thesis, position, health_context, assessed_at)
        health = health_context.health
        health_reasons = health_context.reason_codes
        unrealized = _unrealized_return(position, health_context.market_price)
        if health is ThesisHealth.DATA_INSUFFICIENT:
            action = PositionLifecycleAction.DATA_INSUFFICIENT
            reasons = health_reasons
        elif (
            health is ThesisHealth.INVALIDATED
            or unrealized <= configuration.exit_return_threshold
        ):
            action = PositionLifecycleAction.EXIT
            reasons = (
                *health_reasons,
                "EXIT_REQUIRES_NEW_PORTFOLIO_AND_RISK_DECISION",
            )
        elif (
            health is ThesisHealth.WEAKENING
            and unrealized <= configuration.weakening_return_threshold
        ):
            action = PositionLifecycleAction.REDUCE
            reasons = (
                *health_reasons,
                "REDUCE_REQUIRES_NEW_PORTFOLIO_AND_RISK_DECISION",
            )
        else:
            action = PositionLifecycleAction.WAIT
            reasons = ("NO_EXIT_CONDITION_UNDER_EXPLICIT_PROFILE",)
        reason_codes = tuple(sorted(set(reasons)))
        semantic = {
            "schema_version": EXIT_ASSESSMENT_SCHEMA,
            "thesis_id": str(thesis.thesis_id),
            "thesis_version": thesis.version,
            "position_snapshot_id": str(position.snapshot_id),
            "position_version": position.version,
            "configuration_id": str(configuration.configuration_id),
            "configuration_hash": configuration.configuration_hash,
            "evidence": health_context.evidence.to_canonical_dict(),
            "thesis_health": health.value,
            "action": action.value,
            "unrealized_return": unrealized,
            "requires_portfolio_risk": action
            in {PositionLifecycleAction.REDUCE, PositionLifecycleAction.EXIT},
            "assessed_at": assessed_at.isoformat(),
            "actor": actor,
            "reason": reason,
            "reason_codes": list(reason_codes),
        }
        return ExitAssessment(
            schema_version=EXIT_ASSESSMENT_SCHEMA,
            assessment_id=_exit_id(semantic),
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            position_snapshot_id=position.snapshot_id,
            position_version=position.version,
            configuration_id=configuration.configuration_id,
            configuration_hash=configuration.configuration_hash,
            evidence=health_context.evidence,
            thesis_health=health,
            action=action,
            unrealized_return=unrealized,
            requires_portfolio_risk=semantic["requires_portfolio_risk"] is True,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
            reason_codes=reason_codes,
        )


def _validate_add_authority(
    thesis: TradingThesis,
    position: PositionSnapshot,
    portfolio: PortfolioDecision | None,
    risk: RiskDecision | None,
    assessed_at: datetime,
) -> str | None:
    if portfolio is None or risk is None:
        return "ADD_RISK_AUTHORITY_MISSING"
    if risk.state is not RiskDecisionState.APPROVED:
        return "ADD_RISK_DECISION_NOT_APPROVED"
    if risk.portfolio_decision_id != portfolio.decision_id:
        return "ADD_RISK_PORTFOLIO_MISMATCH"
    if (
        portfolio.created_at < position.as_of
        or risk.completed_at < portfolio.created_at
        or risk.completed_at > assessed_at
    ):
        return "ADD_RISK_AUTHORITY_NOT_FRESH_FOR_POSITION"
    expected = IndependentRiskService().assess(
        portfolio,
        actor=risk.actor,
        reason=risk.reason,
        started_at=risk.started_at,
        completed_at=risk.completed_at,
    )
    if expected != risk:
        return "ADD_RISK_RECOMPUTATION_MISMATCH"
    targets = tuple(
        item
        for item in portfolio.target_positions
        if item.thesis_id == thesis.thesis_id and item.symbol == thesis.symbol
    )
    if len(targets) != 1:
        return "ADD_TARGET_POSITION_MISSING"
    target = targets[0]
    if (
        target.current_quantity != position.total_quantity
        or target.target_quantity <= position.total_quantity
        or target.trade_quantity <= 0
    ):
        return "ADD_TARGET_POSITION_NOT_INCREMENTAL"
    return None


def _validate_inputs(
    thesis: TradingThesis,
    position: PositionSnapshot,
    observation: ThesisHealthObservation,
    assessed_at: datetime,
) -> None:
    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("assessment time must be timezone-aware")
    if position.state is PositionState.CLOSED:
        raise ValueError("closed Position cannot receive Holding/Exit assessment")
    if not (
        thesis.symbol == position.symbol == observation.symbol
    ):
        raise ValueError("Thesis, Position and health observation symbol mismatch")
    if position.as_of > assessed_at or observation.availability_time > assessed_at:
        raise ValueError("assessment cannot consume future Position or evidence")


def _validate_resolved_inputs(
    thesis: TradingThesis,
    position: PositionSnapshot,
    context: ResolvedThesisHealthContext,
    assessed_at: datetime,
) -> None:
    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("assessment time must be timezone-aware")
    if position.state is PositionState.CLOSED:
        raise ValueError("closed Position cannot receive Holding/Exit assessment")
    if not isinstance(context, ResolvedThesisHealthContext):
        raise TypeError("health_context must be resolved")
    if not (thesis.symbol == position.symbol == context.symbol):
        raise ValueError("Thesis, Position and resolved health symbol mismatch")
    if position.as_of > assessed_at or context.availability_time > assessed_at:
        raise ValueError("assessment cannot consume future Position or health evidence")


def _assessment_common(value: HoldingAssessment | ExitAssessment) -> None:
    if value.assessed_at.tzinfo is None or value.assessed_at.utcoffset() is None:
        raise ValueError("assessment timestamp must be timezone-aware")
    _text("actor", value.actor)
    _text("reason", value.reason)
    require_sha256("configuration_hash", value.configuration_hash)
    if not isfinite(value.unrealized_return) or value.unrealized_return <= -1.0:
        raise ValueError("assessment return is invalid")
    if value.reason_codes != tuple(sorted(set(value.reason_codes))):
        raise ValueError("assessment reason codes must be sorted and unique")


def _unrealized_return(position: PositionSnapshot, market_price: float) -> float:
    if position.average_cost is None:
        raise ValueError("open Position requires average cost")
    return market_price / position.average_cost - 1.0


def _holding_semantic(
    *,
    thesis: TradingThesis,
    position: PositionSnapshot,
    configuration: PositionLifecycleConfig,
    evidence: DecisionEvidenceReference,
    health: ThesisHealth,
    action: PositionLifecycleAction,
    unrealized: float,
    portfolio_id: PortfolioDecisionId | None,
    risk_id: RiskDecisionId | None,
    assessed_at: datetime,
    actor: str,
    reason: str,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": HOLDING_ASSESSMENT_SCHEMA,
        "thesis_id": str(thesis.thesis_id),
        "thesis_version": thesis.version,
        "position_snapshot_id": str(position.snapshot_id),
        "position_version": position.version,
        "configuration_id": str(configuration.configuration_id),
        "configuration_hash": configuration.configuration_hash,
        "evidence": evidence.to_canonical_dict(),
        "thesis_health": health.value,
        "action": action.value,
        "unrealized_return": unrealized,
        "add_portfolio_decision_id": (
            str(portfolio_id) if portfolio_id is not None else None
        ),
        "add_risk_decision_id": str(risk_id) if risk_id is not None else None,
        "assessed_at": assessed_at.isoformat(),
        "actor": actor,
        "reason": reason,
        "reason_codes": list(reason_codes),
    }


def _holding_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    portfolio_id = payload["add_portfolio_decision_id"]
    risk_id = payload["add_risk_decision_id"]
    return {
        "schema_version": str(payload["schema_version"]),
        "thesis_id": ThesisId(str(payload["thesis_id"])),
        "thesis_version": int(payload["thesis_version"]),
        "position_snapshot_id": PositionSnapshotId(
            str(payload["position_snapshot_id"])
        ),
        "position_version": int(payload["position_version"]),
        "configuration_id": ArtifactId(str(payload["configuration_id"])),
        "configuration_hash": str(payload["configuration_hash"]),
        "evidence": DecisionEvidenceReference.from_canonical_dict(
            _object(payload["evidence"])
        ),
        "thesis_health": ThesisHealth(str(payload["thesis_health"])),
        "action": PositionLifecycleAction(str(payload["action"])),
        "unrealized_return": float(payload["unrealized_return"]),
        "add_portfolio_decision_id": (
            PortfolioDecisionId(str(portfolio_id)) if portfolio_id is not None else None
        ),
        "add_risk_decision_id": (
            RiskDecisionId(str(risk_id)) if risk_id is not None else None
        ),
        "assessed_at": datetime.fromisoformat(str(payload["assessed_at"])),
        "actor": str(payload["actor"]),
        "reason": str(payload["reason"]),
        "reason_codes": tuple(str(item) for item in _array(payload["reason_codes"])),
    }


def _holding_id(payload: dict[str, Any]) -> HoldingAssessmentId:
    digest = canonical_hash(payload).split(":", 1)[1]
    return HoldingAssessmentId(f"holding-assessment-{digest[:24]}")


def _exit_id(payload: dict[str, Any]) -> ExitAssessmentId:
    digest = canonical_hash(payload).split(":", 1)[1]
    return ExitAssessmentId(f"exit-assessment-{digest[:24]}")


def _text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _optional_bool(value: object) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError("health support value must be bool or null")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("assessment value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("assessment value must be an array")
    return value
