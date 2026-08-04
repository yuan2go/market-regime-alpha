"""H4.5 content-addressed contracts for manual risk-reduction confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    ExitAssessmentId,
    ManualTradeId,
    OpportunityId,
    PositionBookId,
    PositionSnapshotId,
    ThesisId,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.execution.manual import ManualTradeRecord
from market_regime_alpha.position.assessment import PositionLifecycleAction
from market_regime_alpha.position.authority import (
    PositionSnapshot,
    SymbolTradingSessionStatus,
)
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
)

OPERATIONAL_EXIT_DIRECTIVE_V2_SCHEMA = "operational-exit-directive-v2"
RISK_REDUCTION_CONFIRMATION_POLICY_SCHEMA = (
    "risk-reduction-confirmation-policy-v1"
)
RISK_REDUCTION_CONFIRMATION_ATTEMPT_SCHEMA = (
    "risk-reduction-confirmation-attempt-v1"
)

FORMAL_PIT_NOT_ESTABLISHED = "FORMAL_PIT_NOT_ESTABLISHED"
FORMAL_OOS_ALPHA_NOT_ESTABLISHED = "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
TRADING_AUTHORITY_NOT_GRANTED = "TRADING_AUTHORITY_NOT_GRANTED"
OPERATOR_AUTHENTICATION_NOT_ESTABLISHED = (
    "OPERATOR_AUTHENTICATION_NOT_ESTABLISHED"
)


class RequiredExitAuthorityRoute(str, Enum):
    REDUCING_RISK_DECISION = "REDUCING_RISK_DECISION"


class OperatorAuthenticationRequirement(str, Enum):
    RECORDED_ACTOR_ONLY = "RECORDED_ACTOR_ONLY"


class RiskReductionConfirmationState(str, Enum):
    CONFIRMED_INTENT = "CONFIRMED_INTENT"
    EXPIRED = "EXPIRED"
    POSITION_CHANGED = "POSITION_CHANGED"
    BLOCKED_ON_RECHECK = "BLOCKED_ON_RECHECK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    ACTION_SEMANTICS_CONFLICT = "ACTION_SEMANTICS_CONFLICT"


@dataclass(frozen=True, slots=True)
class RiskReductionConfirmationCommand:
    risk_reducing_decision_id: ArtifactId
    risk_reducing_decision_hash: str
    exit_directive_id: ArtifactId
    exit_directive_hash: str
    thesis_health_observation_id: ArtifactId
    thesis_health_observation_hash: str
    composite_manifest_id: ArtifactId
    composite_manifest_hash: str
    trading_calendar: TradingCalendarArtifact
    symbol_trading_statuses: tuple[SymbolTradingSessionStatus, ...]
    execution_observation: ReducingExecutionObservation
    confirmation_policy: RiskReductionConfirmationPolicy
    expected_price_lower: float
    expected_price_upper: float
    confirmed_at: datetime
    actor: str
    reason: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for label, value in (
            ("risk_reducing_decision_hash", self.risk_reducing_decision_hash),
            ("exit_directive_hash", self.exit_directive_hash),
            (
                "thesis_health_observation_hash",
                self.thesis_health_observation_hash,
            ),
            ("composite_manifest_hash", self.composite_manifest_hash),
        ):
            require_sha256(label, value)
        if not self.symbol_trading_statuses:
            raise ValueError("symbol trading status evidence is required")
        if len({item.status_id for item in self.symbol_trading_statuses}) != len(
            self.symbol_trading_statuses
        ):
            raise ValueError("symbol trading status evidence must be unique")
        if (
            not isfinite(self.expected_price_lower)
            or not isfinite(self.expected_price_upper)
            or not 0.0 < self.expected_price_lower <= self.expected_price_upper
        ):
            raise ValueError("expected price range is invalid")
        _aware("confirmed_at", self.confirmed_at)
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        require_text("idempotency_key", self.idempotency_key)

    @property
    def command_hash(self) -> str:
        return canonical_hash(
            {
                "schema_version": "confirm-risk-reduction-command-v1",
                "risk_reducing_decision_id": str(
                    self.risk_reducing_decision_id
                ),
                "risk_reducing_decision_hash": (
                    self.risk_reducing_decision_hash
                ),
                "exit_directive_id": str(self.exit_directive_id),
                "exit_directive_hash": self.exit_directive_hash,
                "thesis_health_observation_id": str(
                    self.thesis_health_observation_id
                ),
                "thesis_health_observation_hash": (
                    self.thesis_health_observation_hash
                ),
                "composite_manifest_id": str(self.composite_manifest_id),
                "composite_manifest_hash": self.composite_manifest_hash,
                "trading_calendar": self.trading_calendar.to_canonical_dict(),
                "symbol_trading_statuses": [
                    item.to_canonical_dict()
                    for item in self.symbol_trading_statuses
                ],
                "execution_observation": (
                    self.execution_observation.to_canonical_dict()
                ),
                "confirmation_policy": (
                    self.confirmation_policy.to_canonical_dict()
                ),
                "expected_price_lower": self.expected_price_lower,
                "expected_price_upper": self.expected_price_upper,
                "confirmed_at": self.confirmed_at.isoformat(),
                "actor": self.actor,
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class RiskReductionConfirmationResult:
    attempt: RiskReductionConfirmationAttempt
    current_position: PositionSnapshot
    manual_trade: ManualTradeRecord | None
    outcome: str
    fill_boundary: str = "NO_FILL_CREATED"
    broker_boundary: str = "NO_BROKER_ORDER_CREATED"
    trading_authority: str = TRADING_AUTHORITY_NOT_GRANTED
    operator_authentication: str = OPERATOR_AUTHENTICATION_NOT_ESTABLISHED

    def __post_init__(self) -> None:
        expected_outcome = (
            "MANUAL_INTENT_CREATED"
            if self.attempt.state
            is RiskReductionConfirmationState.CONFIRMED_INTENT
            else self.attempt.state.value
        )
        if self.outcome != expected_outcome:
            raise ValueError("confirmation result outcome mismatch")
        if (
            (self.manual_trade is None)
            is (
                self.attempt.state
                is RiskReductionConfirmationState.CONFIRMED_INTENT
            )
            or self.fill_boundary != "NO_FILL_CREATED"
            or self.broker_boundary != "NO_BROKER_ORDER_CREATED"
            or self.trading_authority != TRADING_AUTHORITY_NOT_GRANTED
            or self.operator_authentication
            != OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
        ):
            raise ValueError("confirmation result authority boundary mismatch")


@dataclass(frozen=True, slots=True)
class OperationalExitDirectiveV2:
    schema_version: str
    directive_id: ArtifactId
    content_hash: str
    exit_assessment_id: ExitAssessmentId
    exit_assessment_hash: str
    action: PositionLifecycleAction
    required_authority_route: RequiredExitAuthorityRoute
    thesis_id: ThesisId
    thesis_version: int
    opportunity_id: OpportunityId
    position_book_id: PositionBookId
    symbol: str
    position_snapshot_id: PositionSnapshotId
    position_snapshot_hash: str
    position_snapshot_version: int
    thesis_health_observation_id: ArtifactId
    thesis_health_observation_hash: str
    composite_manifest_id: ArtifactId
    composite_manifest_hash: str
    created_at: datetime
    reason_codes: tuple[str, ...]
    formal_pit: str = FORMAL_PIT_NOT_ESTABLISHED
    formal_oos_alpha: str = FORMAL_OOS_ALPHA_NOT_ESTABLISHED
    trading_authority: str = TRADING_AUTHORITY_NOT_GRANTED

    def __post_init__(self) -> None:
        if self.schema_version != OPERATIONAL_EXIT_DIRECTIVE_V2_SCHEMA:
            raise ValueError("unsupported OperationalExitDirectiveV2 schema")
        if self.action not in {
            PositionLifecycleAction.REDUCE,
            PositionLifecycleAction.EXIT,
        }:
            raise ValueError("OperationalExitDirectiveV2 requires REDUCE or EXIT")
        if (
            self.required_authority_route
            is not RequiredExitAuthorityRoute.REDUCING_RISK_DECISION
        ):
            raise ValueError("OperationalExitDirectiveV2 route is invalid")
        _nonnegative("thesis_version", self.thesis_version)
        _nonnegative("position_snapshot_version", self.position_snapshot_version)
        require_text("symbol", self.symbol)
        _aware("created_at", self.created_at)
        _reason_codes(self.reason_codes)
        for label, value in (
            ("exit_assessment_hash", self.exit_assessment_hash),
            ("position_snapshot_hash", self.position_snapshot_hash),
            (
                "thesis_health_observation_hash",
                self.thesis_health_observation_hash,
            ),
            ("composite_manifest_hash", self.composite_manifest_hash),
            ("content_hash", self.content_hash),
        ):
            require_sha256(label, value)
        _authority_ceilings(
            formal_pit=self.formal_pit,
            formal_oos_alpha=self.formal_oos_alpha,
            trading_authority=self.trading_authority,
        )
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = _content_id("operational-exit-directive", expected_hash)
        if self.content_hash != expected_hash or self.directive_id != expected_id:
            raise ValueError("OperationalExitDirectiveV2 identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        exit_assessment_id: ExitAssessmentId,
        exit_assessment_hash: str,
        action: PositionLifecycleAction,
        thesis_id: ThesisId,
        thesis_version: int,
        opportunity_id: OpportunityId,
        position_book_id: PositionBookId,
        symbol: str,
        position_snapshot_id: PositionSnapshotId,
        position_snapshot_hash: str,
        position_snapshot_version: int,
        thesis_health_observation_id: ArtifactId,
        thesis_health_observation_hash: str,
        composite_manifest_id: ArtifactId,
        composite_manifest_hash: str,
        created_at: datetime,
        reason_codes: tuple[str, ...],
    ) -> OperationalExitDirectiveV2:
        semantic = cls.semantic_payload_for(
            exit_assessment_id=exit_assessment_id,
            exit_assessment_hash=exit_assessment_hash,
            action=action,
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            opportunity_id=opportunity_id,
            position_book_id=position_book_id,
            symbol=symbol,
            position_snapshot_id=position_snapshot_id,
            position_snapshot_hash=position_snapshot_hash,
            position_snapshot_version=position_snapshot_version,
            thesis_health_observation_id=thesis_health_observation_id,
            thesis_health_observation_hash=thesis_health_observation_hash,
            composite_manifest_id=composite_manifest_id,
            composite_manifest_hash=composite_manifest_hash,
            created_at=created_at,
            reason_codes=reason_codes,
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=OPERATIONAL_EXIT_DIRECTIVE_V2_SCHEMA,
            directive_id=_content_id("operational-exit-directive", digest),
            content_hash=digest,
            required_authority_route=(
                RequiredExitAuthorityRoute.REDUCING_RISK_DECISION
            ),
            formal_pit=FORMAL_PIT_NOT_ESTABLISHED,
            formal_oos_alpha=FORMAL_OOS_ALPHA_NOT_ESTABLISHED,
            trading_authority=TRADING_AUTHORITY_NOT_GRANTED,
            exit_assessment_id=exit_assessment_id,
            exit_assessment_hash=exit_assessment_hash,
            action=action,
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            opportunity_id=opportunity_id,
            position_book_id=position_book_id,
            symbol=symbol,
            position_snapshot_id=position_snapshot_id,
            position_snapshot_hash=position_snapshot_hash,
            position_snapshot_version=position_snapshot_version,
            thesis_health_observation_id=thesis_health_observation_id,
            thesis_health_observation_hash=thesis_health_observation_hash,
            composite_manifest_id=composite_manifest_id,
            composite_manifest_hash=composite_manifest_hash,
            created_at=created_at,
            reason_codes=reason_codes,
        )

    @staticmethod
    def semantic_payload_for(
        *,
        exit_assessment_id: ExitAssessmentId,
        exit_assessment_hash: str,
        action: PositionLifecycleAction,
        thesis_id: ThesisId,
        thesis_version: int,
        opportunity_id: OpportunityId,
        position_book_id: PositionBookId,
        symbol: str,
        position_snapshot_id: PositionSnapshotId,
        position_snapshot_hash: str,
        position_snapshot_version: int,
        thesis_health_observation_id: ArtifactId,
        thesis_health_observation_hash: str,
        composite_manifest_id: ArtifactId,
        composite_manifest_hash: str,
        created_at: datetime,
        reason_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "schema_version": OPERATIONAL_EXIT_DIRECTIVE_V2_SCHEMA,
            "exit_assessment_id": str(exit_assessment_id),
            "exit_assessment_hash": exit_assessment_hash,
            "action": action.value,
            "required_authority_route": (
                RequiredExitAuthorityRoute.REDUCING_RISK_DECISION.value
            ),
            "thesis_id": str(thesis_id),
            "thesis_version": thesis_version,
            "opportunity_id": str(opportunity_id),
            "position_book_id": str(position_book_id),
            "symbol": symbol,
            "position_snapshot_id": str(position_snapshot_id),
            "position_snapshot_hash": position_snapshot_hash,
            "position_snapshot_version": position_snapshot_version,
            "thesis_health_observation_id": str(thesis_health_observation_id),
            "thesis_health_observation_hash": thesis_health_observation_hash,
            "composite_manifest_id": str(composite_manifest_id),
            "composite_manifest_hash": composite_manifest_hash,
            "created_at": created_at.isoformat(),
            "reason_codes": list(reason_codes),
            "formal_pit": FORMAL_PIT_NOT_ESTABLISHED,
            "formal_oos_alpha": FORMAL_OOS_ALPHA_NOT_ESTABLISHED,
            "trading_authority": TRADING_AUTHORITY_NOT_GRANTED,
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            exit_assessment_id=self.exit_assessment_id,
            exit_assessment_hash=self.exit_assessment_hash,
            action=self.action,
            thesis_id=self.thesis_id,
            thesis_version=self.thesis_version,
            opportunity_id=self.opportunity_id,
            position_book_id=self.position_book_id,
            symbol=self.symbol,
            position_snapshot_id=self.position_snapshot_id,
            position_snapshot_hash=self.position_snapshot_hash,
            position_snapshot_version=self.position_snapshot_version,
            thesis_health_observation_id=self.thesis_health_observation_id,
            thesis_health_observation_hash=self.thesis_health_observation_hash,
            composite_manifest_id=self.composite_manifest_id,
            composite_manifest_hash=self.composite_manifest_hash,
            created_at=self.created_at,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "directive_id": str(self.directive_id),
            **self.semantic_payload(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> OperationalExitDirectiveV2:
        _fields(payload, _DIRECTIVE_FIELDS, "OperationalExitDirectiveV2")
        reasons = _string_tuple(payload["reason_codes"], "reason_codes")
        return cls(
            schema_version=str(payload["schema_version"]),
            directive_id=ArtifactId(str(payload["directive_id"])),
            content_hash=str(payload["content_hash"]),
            exit_assessment_id=ExitAssessmentId(
                str(payload["exit_assessment_id"])
            ),
            exit_assessment_hash=str(payload["exit_assessment_hash"]),
            action=PositionLifecycleAction(str(payload["action"])),
            required_authority_route=RequiredExitAuthorityRoute(
                str(payload["required_authority_route"])
            ),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            thesis_version=int(payload["thesis_version"]),
            opportunity_id=OpportunityId(str(payload["opportunity_id"])),
            position_book_id=PositionBookId(str(payload["position_book_id"])),
            symbol=str(payload["symbol"]),
            position_snapshot_id=PositionSnapshotId(
                str(payload["position_snapshot_id"])
            ),
            position_snapshot_hash=str(payload["position_snapshot_hash"]),
            position_snapshot_version=int(payload["position_snapshot_version"]),
            thesis_health_observation_id=ArtifactId(
                str(payload["thesis_health_observation_id"])
            ),
            thesis_health_observation_hash=str(
                payload["thesis_health_observation_hash"]
            ),
            composite_manifest_id=ArtifactId(
                str(payload["composite_manifest_id"])
            ),
            composite_manifest_hash=str(payload["composite_manifest_hash"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            reason_codes=reasons,
            formal_pit=str(payload["formal_pit"]),
            formal_oos_alpha=str(payload["formal_oos_alpha"]),
            trading_authority=str(payload["trading_authority"]),
        )


@dataclass(frozen=True, slots=True)
class RiskReductionConfirmationPolicy:
    schema_version: str
    policy_id: ArtifactId
    policy_hash: str
    profile_id: str
    builder_revision: str
    maximum_decision_age_seconds: float
    maximum_position_age_seconds: float
    maximum_execution_observation_age_seconds: float
    maximum_reference_price_deviation: float
    operator_authentication_requirement: OperatorAuthenticationRequirement
    operator_authentication_limitation: str = (
        OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
    )

    def __post_init__(self) -> None:
        if self.schema_version != RISK_REDUCTION_CONFIRMATION_POLICY_SCHEMA:
            raise ValueError("unsupported confirmation policy schema")
        require_text("profile_id", self.profile_id)
        require_text("builder_revision", self.builder_revision)
        thresholds = (
            self.maximum_decision_age_seconds,
            self.maximum_position_age_seconds,
            self.maximum_execution_observation_age_seconds,
        )
        if any(not isfinite(value) or value <= 0.0 for value in thresholds) or (
            not isfinite(self.maximum_reference_price_deviation)
            or not 0.0 < self.maximum_reference_price_deviation <= 1.0
        ):
            raise ValueError("confirmation policy thresholds are invalid")
        if (
            self.operator_authentication_requirement
            is not OperatorAuthenticationRequirement.RECORDED_ACTOR_ONLY
            or self.operator_authentication_limitation
            != OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
        ):
            raise ValueError("operator authentication authority is inflated")
        require_sha256("policy_hash", self.policy_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        if self.policy_hash != expected_hash or self.policy_id != _content_id(
            "risk-reduction-confirmation-policy", expected_hash
        ):
            raise ValueError("confirmation policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        profile_id: str,
        builder_revision: str,
        maximum_decision_age_seconds: float,
        maximum_position_age_seconds: float,
        maximum_execution_observation_age_seconds: float,
        maximum_reference_price_deviation: float,
        operator_authentication_requirement: OperatorAuthenticationRequirement,
    ) -> RiskReductionConfirmationPolicy:
        semantic = cls.semantic_payload_for(
            profile_id=profile_id,
            builder_revision=builder_revision,
            maximum_decision_age_seconds=maximum_decision_age_seconds,
            maximum_position_age_seconds=maximum_position_age_seconds,
            maximum_execution_observation_age_seconds=(
                maximum_execution_observation_age_seconds
            ),
            maximum_reference_price_deviation=maximum_reference_price_deviation,
            operator_authentication_requirement=(
                operator_authentication_requirement
            ),
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=RISK_REDUCTION_CONFIRMATION_POLICY_SCHEMA,
            policy_id=_content_id(
                "risk-reduction-confirmation-policy", digest
            ),
            policy_hash=digest,
            operator_authentication_limitation=(
                OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
            ),
            profile_id=profile_id,
            builder_revision=builder_revision,
            maximum_decision_age_seconds=maximum_decision_age_seconds,
            maximum_position_age_seconds=maximum_position_age_seconds,
            maximum_execution_observation_age_seconds=(
                maximum_execution_observation_age_seconds
            ),
            maximum_reference_price_deviation=maximum_reference_price_deviation,
            operator_authentication_requirement=(
                operator_authentication_requirement
            ),
        )

    @staticmethod
    def semantic_payload_for(
        *,
        profile_id: str,
        builder_revision: str,
        maximum_decision_age_seconds: float,
        maximum_position_age_seconds: float,
        maximum_execution_observation_age_seconds: float,
        maximum_reference_price_deviation: float,
        operator_authentication_requirement: OperatorAuthenticationRequirement,
    ) -> dict[str, Any]:
        return {
            "schema_version": RISK_REDUCTION_CONFIRMATION_POLICY_SCHEMA,
            "profile_id": profile_id,
            "builder_revision": builder_revision,
            "maximum_decision_age_seconds": float(maximum_decision_age_seconds),
            "maximum_position_age_seconds": float(maximum_position_age_seconds),
            "maximum_execution_observation_age_seconds": float(
                maximum_execution_observation_age_seconds
            ),
            "maximum_reference_price_deviation": float(
                maximum_reference_price_deviation
            ),
            "operator_authentication_requirement": (
                operator_authentication_requirement.value
            ),
            "operator_authentication_limitation": (
                OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
            ),
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            profile_id=self.profile_id,
            builder_revision=self.builder_revision,
            maximum_decision_age_seconds=self.maximum_decision_age_seconds,
            maximum_position_age_seconds=self.maximum_position_age_seconds,
            maximum_execution_observation_age_seconds=(
                self.maximum_execution_observation_age_seconds
            ),
            maximum_reference_price_deviation=(
                self.maximum_reference_price_deviation
            ),
            operator_authentication_requirement=(
                self.operator_authentication_requirement
            ),
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            **self.semantic_payload(),
            "policy_hash": self.policy_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RiskReductionConfirmationPolicy:
        _fields(payload, _POLICY_FIELDS, "RiskReductionConfirmationPolicy")
        return cls(
            schema_version=str(payload["schema_version"]),
            policy_id=ArtifactId(str(payload["policy_id"])),
            policy_hash=str(payload["policy_hash"]),
            profile_id=str(payload["profile_id"]),
            builder_revision=str(payload["builder_revision"]),
            maximum_decision_age_seconds=float(
                payload["maximum_decision_age_seconds"]
            ),
            maximum_position_age_seconds=float(
                payload["maximum_position_age_seconds"]
            ),
            maximum_execution_observation_age_seconds=float(
                payload["maximum_execution_observation_age_seconds"]
            ),
            maximum_reference_price_deviation=float(
                payload["maximum_reference_price_deviation"]
            ),
            operator_authentication_requirement=OperatorAuthenticationRequirement(
                str(payload["operator_authentication_requirement"])
            ),
            operator_authentication_limitation=str(
                payload["operator_authentication_limitation"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RiskReductionConfirmationAttempt:
    schema_version: str
    attempt_id: ArtifactId
    content_hash: str
    state: RiskReductionConfirmationState
    risk_reducing_decision_id: ArtifactId
    risk_reducing_decision_hash: str
    exit_directive_id: ArtifactId
    exit_directive_hash: str
    source_position_snapshot_id: PositionSnapshotId
    source_position_snapshot_hash: str
    current_position_snapshot_id: PositionSnapshotId
    current_position_snapshot_hash: str
    thesis_health_observation_id: ArtifactId
    thesis_health_observation_hash: str
    composite_manifest_id: ArtifactId
    composite_manifest_hash: str
    recheck_observation_id: ArtifactId
    recheck_observation_hash: str
    configuration_id: ArtifactId
    configuration_hash: str
    confirmation_policy_id: ArtifactId
    confirmation_policy_hash: str
    manual_trade_id: ManualTradeId | None
    actor: str
    reason: str
    confirmed_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RISK_REDUCTION_CONFIRMATION_ATTEMPT_SCHEMA:
            raise ValueError("unsupported confirmation attempt schema")
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        _aware("confirmed_at", self.confirmed_at)
        _reason_codes(self.reason_codes)
        for label, value in (
            ("risk_reducing_decision_hash", self.risk_reducing_decision_hash),
            ("exit_directive_hash", self.exit_directive_hash),
            ("source_position_snapshot_hash", self.source_position_snapshot_hash),
            (
                "current_position_snapshot_hash",
                self.current_position_snapshot_hash,
            ),
            (
                "thesis_health_observation_hash",
                self.thesis_health_observation_hash,
            ),
            ("composite_manifest_hash", self.composite_manifest_hash),
            ("recheck_observation_hash", self.recheck_observation_hash),
            ("configuration_hash", self.configuration_hash),
            ("confirmation_policy_hash", self.confirmation_policy_hash),
            ("content_hash", self.content_hash),
        ):
            require_sha256(label, value)
        if self.state is RiskReductionConfirmationState.CONFIRMED_INTENT:
            if self.manual_trade_id is None:
                raise ValueError("confirmed attempt requires a ManualTrade ID")
        elif self.manual_trade_id is not None:
            raise ValueError("failed attempt cannot bind a ManualTrade ID")
        expected_hash = canonical_hash(self.semantic_payload())
        if self.content_hash != expected_hash or self.attempt_id != _content_id(
            "risk-reduction-confirmation-attempt", expected_hash
        ):
            raise ValueError("confirmation attempt identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        state: RiskReductionConfirmationState,
        risk_reducing_decision_id: ArtifactId,
        risk_reducing_decision_hash: str,
        exit_directive_id: ArtifactId,
        exit_directive_hash: str,
        source_position_snapshot_id: PositionSnapshotId,
        source_position_snapshot_hash: str,
        current_position_snapshot_id: PositionSnapshotId,
        current_position_snapshot_hash: str,
        thesis_health_observation_id: ArtifactId,
        thesis_health_observation_hash: str,
        composite_manifest_id: ArtifactId,
        composite_manifest_hash: str,
        recheck_observation_id: ArtifactId,
        recheck_observation_hash: str,
        configuration_id: ArtifactId,
        configuration_hash: str,
        confirmation_policy_id: ArtifactId,
        confirmation_policy_hash: str,
        manual_trade_id: ManualTradeId | None,
        actor: str,
        reason: str,
        confirmed_at: datetime,
        reason_codes: tuple[str, ...],
    ) -> RiskReductionConfirmationAttempt:
        semantic = cls.semantic_payload_for(
            state=state,
            risk_reducing_decision_id=risk_reducing_decision_id,
            risk_reducing_decision_hash=risk_reducing_decision_hash,
            exit_directive_id=exit_directive_id,
            exit_directive_hash=exit_directive_hash,
            source_position_snapshot_id=source_position_snapshot_id,
            source_position_snapshot_hash=source_position_snapshot_hash,
            current_position_snapshot_id=current_position_snapshot_id,
            current_position_snapshot_hash=current_position_snapshot_hash,
            thesis_health_observation_id=thesis_health_observation_id,
            thesis_health_observation_hash=thesis_health_observation_hash,
            composite_manifest_id=composite_manifest_id,
            composite_manifest_hash=composite_manifest_hash,
            recheck_observation_id=recheck_observation_id,
            recheck_observation_hash=recheck_observation_hash,
            configuration_id=configuration_id,
            configuration_hash=configuration_hash,
            confirmation_policy_id=confirmation_policy_id,
            confirmation_policy_hash=confirmation_policy_hash,
            manual_trade_id=manual_trade_id,
            actor=actor,
            reason=reason,
            confirmed_at=confirmed_at,
            reason_codes=reason_codes,
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=RISK_REDUCTION_CONFIRMATION_ATTEMPT_SCHEMA,
            attempt_id=_content_id("risk-reduction-confirmation-attempt", digest),
            content_hash=digest,
            state=state,
            risk_reducing_decision_id=risk_reducing_decision_id,
            risk_reducing_decision_hash=risk_reducing_decision_hash,
            exit_directive_id=exit_directive_id,
            exit_directive_hash=exit_directive_hash,
            source_position_snapshot_id=source_position_snapshot_id,
            source_position_snapshot_hash=source_position_snapshot_hash,
            current_position_snapshot_id=current_position_snapshot_id,
            current_position_snapshot_hash=current_position_snapshot_hash,
            thesis_health_observation_id=thesis_health_observation_id,
            thesis_health_observation_hash=thesis_health_observation_hash,
            composite_manifest_id=composite_manifest_id,
            composite_manifest_hash=composite_manifest_hash,
            recheck_observation_id=recheck_observation_id,
            recheck_observation_hash=recheck_observation_hash,
            configuration_id=configuration_id,
            configuration_hash=configuration_hash,
            confirmation_policy_id=confirmation_policy_id,
            confirmation_policy_hash=confirmation_policy_hash,
            manual_trade_id=manual_trade_id,
            actor=actor,
            reason=reason,
            confirmed_at=confirmed_at,
            reason_codes=reason_codes,
        )

    @staticmethod
    def semantic_payload_for(
        *,
        state: RiskReductionConfirmationState,
        risk_reducing_decision_id: ArtifactId,
        risk_reducing_decision_hash: str,
        exit_directive_id: ArtifactId,
        exit_directive_hash: str,
        source_position_snapshot_id: PositionSnapshotId,
        source_position_snapshot_hash: str,
        current_position_snapshot_id: PositionSnapshotId,
        current_position_snapshot_hash: str,
        thesis_health_observation_id: ArtifactId,
        thesis_health_observation_hash: str,
        composite_manifest_id: ArtifactId,
        composite_manifest_hash: str,
        recheck_observation_id: ArtifactId,
        recheck_observation_hash: str,
        configuration_id: ArtifactId,
        configuration_hash: str,
        confirmation_policy_id: ArtifactId,
        confirmation_policy_hash: str,
        manual_trade_id: ManualTradeId | None,
        actor: str,
        reason: str,
        confirmed_at: datetime,
        reason_codes: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "schema_version": RISK_REDUCTION_CONFIRMATION_ATTEMPT_SCHEMA,
            "state": state.value,
            "risk_reducing_decision_id": str(risk_reducing_decision_id),
            "risk_reducing_decision_hash": risk_reducing_decision_hash,
            "exit_directive_id": str(exit_directive_id),
            "exit_directive_hash": exit_directive_hash,
            "source_position_snapshot_id": str(source_position_snapshot_id),
            "source_position_snapshot_hash": source_position_snapshot_hash,
            "current_position_snapshot_id": str(current_position_snapshot_id),
            "current_position_snapshot_hash": current_position_snapshot_hash,
            "thesis_health_observation_id": str(thesis_health_observation_id),
            "thesis_health_observation_hash": thesis_health_observation_hash,
            "composite_manifest_id": str(composite_manifest_id),
            "composite_manifest_hash": composite_manifest_hash,
            "recheck_observation_id": str(recheck_observation_id),
            "recheck_observation_hash": recheck_observation_hash,
            "configuration_id": str(configuration_id),
            "configuration_hash": configuration_hash,
            "confirmation_policy_id": str(confirmation_policy_id),
            "confirmation_policy_hash": confirmation_policy_hash,
            "manual_trade_id": (
                str(manual_trade_id) if manual_trade_id is not None else None
            ),
            "actor": actor,
            "reason": reason,
            "confirmed_at": confirmed_at.isoformat(),
            "reason_codes": list(reason_codes),
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            state=self.state,
            risk_reducing_decision_id=self.risk_reducing_decision_id,
            risk_reducing_decision_hash=self.risk_reducing_decision_hash,
            exit_directive_id=self.exit_directive_id,
            exit_directive_hash=self.exit_directive_hash,
            source_position_snapshot_id=self.source_position_snapshot_id,
            source_position_snapshot_hash=self.source_position_snapshot_hash,
            current_position_snapshot_id=self.current_position_snapshot_id,
            current_position_snapshot_hash=self.current_position_snapshot_hash,
            thesis_health_observation_id=self.thesis_health_observation_id,
            thesis_health_observation_hash=self.thesis_health_observation_hash,
            composite_manifest_id=self.composite_manifest_id,
            composite_manifest_hash=self.composite_manifest_hash,
            recheck_observation_id=self.recheck_observation_id,
            recheck_observation_hash=self.recheck_observation_hash,
            configuration_id=self.configuration_id,
            configuration_hash=self.configuration_hash,
            confirmation_policy_id=self.confirmation_policy_id,
            confirmation_policy_hash=self.confirmation_policy_hash,
            manual_trade_id=self.manual_trade_id,
            actor=self.actor,
            reason=self.reason,
            confirmed_at=self.confirmed_at,
            reason_codes=self.reason_codes,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": str(self.attempt_id),
            **self.semantic_payload(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> RiskReductionConfirmationAttempt:
        _fields(payload, _ATTEMPT_FIELDS, "RiskReductionConfirmationAttempt")
        manual_trade = payload["manual_trade_id"]
        return cls(
            schema_version=str(payload["schema_version"]),
            attempt_id=ArtifactId(str(payload["attempt_id"])),
            content_hash=str(payload["content_hash"]),
            state=RiskReductionConfirmationState(str(payload["state"])),
            risk_reducing_decision_id=ArtifactId(
                str(payload["risk_reducing_decision_id"])
            ),
            risk_reducing_decision_hash=str(
                payload["risk_reducing_decision_hash"]
            ),
            exit_directive_id=ArtifactId(str(payload["exit_directive_id"])),
            exit_directive_hash=str(payload["exit_directive_hash"]),
            source_position_snapshot_id=PositionSnapshotId(
                str(payload["source_position_snapshot_id"])
            ),
            source_position_snapshot_hash=str(
                payload["source_position_snapshot_hash"]
            ),
            current_position_snapshot_id=PositionSnapshotId(
                str(payload["current_position_snapshot_id"])
            ),
            current_position_snapshot_hash=str(
                payload["current_position_snapshot_hash"]
            ),
            thesis_health_observation_id=ArtifactId(
                str(payload["thesis_health_observation_id"])
            ),
            thesis_health_observation_hash=str(
                payload["thesis_health_observation_hash"]
            ),
            composite_manifest_id=ArtifactId(
                str(payload["composite_manifest_id"])
            ),
            composite_manifest_hash=str(payload["composite_manifest_hash"]),
            recheck_observation_id=ArtifactId(
                str(payload["recheck_observation_id"])
            ),
            recheck_observation_hash=str(payload["recheck_observation_hash"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            confirmation_policy_id=ArtifactId(
                str(payload["confirmation_policy_id"])
            ),
            confirmation_policy_hash=str(payload["confirmation_policy_hash"]),
            manual_trade_id=(
                ManualTradeId(str(manual_trade))
                if manual_trade is not None
                else None
            ),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            confirmed_at=datetime.fromisoformat(str(payload["confirmed_at"])),
            reason_codes=_string_tuple(payload["reason_codes"], "reason_codes"),
        )


_DIRECTIVE_FIELDS = {
    "schema_version",
    "directive_id",
    "content_hash",
    "exit_assessment_id",
    "exit_assessment_hash",
    "action",
    "required_authority_route",
    "thesis_id",
    "thesis_version",
    "opportunity_id",
    "position_book_id",
    "symbol",
    "position_snapshot_id",
    "position_snapshot_hash",
    "position_snapshot_version",
    "thesis_health_observation_id",
    "thesis_health_observation_hash",
    "composite_manifest_id",
    "composite_manifest_hash",
    "created_at",
    "reason_codes",
    "formal_pit",
    "formal_oos_alpha",
    "trading_authority",
}

_POLICY_FIELDS = {
    "schema_version",
    "policy_id",
    "policy_hash",
    "profile_id",
    "builder_revision",
    "maximum_decision_age_seconds",
    "maximum_position_age_seconds",
    "maximum_execution_observation_age_seconds",
    "maximum_reference_price_deviation",
    "operator_authentication_requirement",
    "operator_authentication_limitation",
}

_ATTEMPT_SEMANTIC_FIELDS = (
    "schema_version",
    "state",
    "risk_reducing_decision_id",
    "risk_reducing_decision_hash",
    "exit_directive_id",
    "exit_directive_hash",
    "source_position_snapshot_id",
    "source_position_snapshot_hash",
    "current_position_snapshot_id",
    "current_position_snapshot_hash",
    "thesis_health_observation_id",
    "thesis_health_observation_hash",
    "composite_manifest_id",
    "composite_manifest_hash",
    "recheck_observation_id",
    "recheck_observation_hash",
    "configuration_id",
    "configuration_hash",
    "confirmation_policy_id",
    "confirmation_policy_hash",
    "manual_trade_id",
    "actor",
    "reason",
    "confirmed_at",
    "reason_codes",
)
_ATTEMPT_FIELDS = {"attempt_id", "content_hash", *_ATTEMPT_SEMANTIC_FIELDS}


def _content_id(prefix: str, digest: str) -> ArtifactId:
    require_sha256("content_hash", digest)
    return ArtifactId(f"{prefix}-{digest.split(':', 1)[1][:24]}")


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _nonnegative(label: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _reason_codes(values: tuple[str, ...]) -> None:
    if not values or len(values) != len(set(values)):
        raise ValueError("reason_codes must be non-empty and unique")
    for value in values:
        require_text("reason_code", value)


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(str(item) for item in value)


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _authority_ceilings(
    *, formal_pit: str, formal_oos_alpha: str, trading_authority: str
) -> None:
    if (
        formal_pit != FORMAL_PIT_NOT_ESTABLISHED
        or formal_oos_alpha != FORMAL_OOS_ALPHA_NOT_ESTABLISHED
        or trading_authority != TRADING_AUTHORITY_NOT_GRANTED
    ):
        raise ValueError("OperationalExitDirectiveV2 authority is inflated")
