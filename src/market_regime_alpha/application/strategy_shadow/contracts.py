"""Strategy Shadow objects, intentionally separate from trading authorities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


class ShadowFillStatus(str, Enum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    UNFILLED = "UNFILLED"


class HoldingRuleKind(str, Enum):
    FIXED_TIME = "FIXED_TIME"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    MARKET_DETERIORATION = "MARKET_DETERIORATION"
    THEME_DETERIORATION = "THEME_DETERIORATION"
    CAPITAL_DETERIORATION = "CAPITAL_DETERIORATION"
    TRAILING_PROTECTION = "TRAILING_PROTECTION"
    LOSS_PROTECTION = "LOSS_PROTECTION"
    MULTI_HORIZON = "MULTI_HORIZON"


class ShadowHoldingDecision(str, Enum):
    CONTINUE = "CONTINUE"
    ASSESS_EXIT = "ASSESS_EXIT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ShadowExitDecision(str, Enum):
    SHADOW_EXIT = "SHADOW_EXIT"
    SHADOW_HOLD = "SHADOW_HOLD"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class StrategyShadowPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    rule_kinds: tuple[HoldingRuleKind, ...]
    fixed_horizon_sessions: int
    trailing_drawdown: Decimal
    protection_return: Decimal
    participation_rate: Decimal
    limitations: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        rule_kinds: tuple[HoldingRuleKind, ...],
        fixed_horizon_sessions: int,
        trailing_drawdown: Decimal,
        protection_return: Decimal,
        participation_rate: Decimal,
    ) -> StrategyShadowPolicy:
        ordered = tuple(sorted(set(rule_kinds), key=lambda item: item.value))
        if (
            not ordered
            or fixed_horizon_sessions <= 0
            or trailing_drawdown <= 0
            or protection_return >= 0
            or not Decimal("0") < participation_rate <= Decimal("1")
        ):
            raise ValueError("Strategy Shadow Policy configuration is invalid")
        limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "HOLDING_EXIT_VALIDATED_FALSE", "STRATEGY_SHADOW_PROVEN_FALSE"}))
        payload = {
            "schema": "strategy-shadow-policy/v1",
            "policy_version": policy_version,
            "rule_kinds": [item.value for item in ordered],
            "fixed_horizon_sessions": fixed_horizon_sessions,
            "trailing_drawdown": str(trailing_drawdown),
            "protection_return": str(protection_return),
            "participation_rate": str(participation_rate),
            "limitations": list(limitations),
        }
        artifact_id, digest = content_identity("strategy-shadow-policy", payload)
        return cls(
            artifact_id,
            digest,
            policy_version,
            ordered,
            fixed_horizon_sessions,
            trailing_drawdown,
            protection_return,
            participation_rate,
            limitations,
        )


@dataclass(frozen=True, slots=True)
class ShadowEntry:
    entry_id: ArtifactId
    entry_hash: str
    assessment_reference: ValidationArtifactReference
    policy_reference: ValidationArtifactReference
    symbol: str
    decision_time: datetime
    intended_quantity: Decimal
    intended_reference_price: Decimal
    source_references: tuple[ValidationArtifactReference, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowFill:
    fill_id: ArtifactId
    fill_hash: str
    entry_reference: ValidationArtifactReference
    status: ShadowFillStatus
    filled_quantity: Decimal
    fill_price: Decimal | None
    slippage_cost: Decimal
    market_impact_cost: Decimal
    commission_cost: Decimal
    observed_at: datetime
    liquidity_reference: ValidationArtifactReference
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowPosition:
    position_id: ArtifactId
    position_hash: str
    fill_reference: ValidationArtifactReference
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    opened_at: datetime
    peak_price: Decimal
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HoldingAssessment:
    assessment_id: ArtifactId
    assessment_hash: str
    position_reference: ValidationArtifactReference
    policy_reference: ValidationArtifactReference
    assessed_at: datetime
    sessions_held: int
    current_price: Decimal | None
    unrealized_return: Decimal | None
    peak_drawdown: Decimal | None
    triggered_rules: tuple[HoldingRuleKind, ...]
    decision: ShadowHoldingDecision
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExitAssessment:
    assessment_id: ArtifactId
    assessment_hash: str
    holding_reference: ValidationArtifactReference
    decision: ShadowExitDecision
    exit_price: Decimal | None
    exit_quantity: Decimal
    triggered_rules: tuple[HoldingRuleKind, ...]
    assessed_at: datetime
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    outcome_id: ArtifactId
    outcome_hash: str
    entry_reference: ValidationArtifactReference
    fill_reference: ValidationArtifactReference
    position_reference: ValidationArtifactReference
    exit_reference: ValidationArtifactReference
    symbol: str
    opened_at: datetime
    closed_at: datetime
    gross_return: Decimal
    total_cost: Decimal
    net_return: Decimal
    mfe: Decimal | None
    mae: Decimal | None
    settled: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("outcome_hash", self.outcome_hash)
        if not self.settled:
            raise ValueError("Strategy Outcome must be settled")
        if canonical_hash(self.identity_payload()) != self.outcome_hash:
            raise ValueError("Strategy Outcome hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _outcome_payload(
            self.entry_reference,
            self.fill_reference,
            self.position_reference,
            self.exit_reference,
            self.symbol,
            self.opened_at,
            self.closed_at,
            self.gross_return,
            self.total_cost,
            self.net_return,
            self.mfe,
            self.mae,
            self.limitations,
        )


def reference(kind: str, artifact_id: ArtifactId, digest: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, artifact_id, digest)


def make_shadow_entry(
    *,
    assessment_reference: ValidationArtifactReference,
    policy: StrategyShadowPolicy,
    symbol: str,
    decision_time: datetime,
    intended_quantity: Decimal,
    intended_reference_price: Decimal,
    source_references: tuple[ValidationArtifactReference, ...],
) -> ShadowEntry:
    if intended_quantity <= 0 or intended_reference_price <= 0:
        raise ValueError("Shadow Entry requires positive quantity and price")
    policy_ref = reference("STRATEGY_SHADOW_POLICY", policy.policy_id, policy.policy_hash)
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "NOT_ORDER", "NOT_BROKER_INTENT"}))
    ordered = tuple(sorted(set(source_references), key=lambda item: (item.artifact_kind, str(item.artifact_id))))
    payload = {
        "assessment_reference": assessment_reference.to_canonical_dict(),
        "policy_reference": policy_ref.to_canonical_dict(),
        "symbol": symbol,
        "decision_time": timestamp(decision_time),
        "intended_quantity": str(intended_quantity),
        "intended_reference_price": str(intended_reference_price),
        "source_references": [item.to_canonical_dict() for item in ordered],
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("shadow-entry", payload)
    return ShadowEntry(
        artifact_id,
        digest,
        assessment_reference,
        policy_ref,
        symbol,
        decision_time,
        intended_quantity,
        intended_reference_price,
        ordered,
        limitations,
    )


def make_shadow_fill(
    *,
    entry: ShadowEntry,
    observed_price: Decimal | None,
    fillability: Decimal,
    slippage_bps: Decimal,
    impact_bps: Decimal,
    commission_bps: Decimal,
    observed_at: datetime,
    liquidity_reference: ValidationArtifactReference,
) -> ShadowFill:
    if not Decimal("0") <= fillability <= Decimal("1"):
        raise ValueError("Shadow fillability must be within [0, 1]")
    quantity = entry.intended_quantity * fillability
    status = (
        ShadowFillStatus.UNFILLED
        if quantity == 0 or observed_price is None
        else ShadowFillStatus.FILLED
        if fillability == 1
        else ShadowFillStatus.PARTIAL
    )
    if status is ShadowFillStatus.UNFILLED:
        fill_price = None
    else:
        assert observed_price is not None
        fill_price = observed_price * (Decimal("1") + (slippage_bps + impact_bps) / Decimal("10000"))
    notional = Decimal("0") if fill_price is None else fill_price * quantity
    slippage = notional * slippage_bps / Decimal("10000")
    impact = notional * impact_bps / Decimal("10000")
    commission = notional * commission_bps / Decimal("10000")
    entry_ref = reference("SHADOW_ENTRY", entry.entry_id, entry.entry_hash)
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "NOT_REAL_FILL", "NO_POSITION_AUTHORITY"}))
    payload = {
        "entry_reference": entry_ref.to_canonical_dict(),
        "status": status.value,
        "filled_quantity": str(quantity),
        "fill_price": None if fill_price is None else str(fill_price),
        "slippage_cost": str(slippage),
        "market_impact_cost": str(impact),
        "commission_cost": str(commission),
        "observed_at": timestamp(observed_at),
        "liquidity_reference": liquidity_reference.to_canonical_dict(),
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("shadow-fill", payload)
    return ShadowFill(
        artifact_id,
        digest,
        entry_ref,
        status,
        quantity,
        fill_price,
        slippage,
        impact,
        commission,
        observed_at,
        liquidity_reference,
        limitations,
    )


def make_shadow_position(*, entry: ShadowEntry, fill: ShadowFill) -> ShadowPosition:
    if fill.status is ShadowFillStatus.UNFILLED or fill.fill_price is None:
        raise ValueError("unfilled Shadow Fill cannot create Shadow Position")
    fill_ref = reference("SHADOW_FILL", fill.fill_id, fill.fill_hash)
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "NOT_REAL_POSITION", "NO_POSITION_AUTHORITY"}))
    payload = {
        "fill_reference": fill_ref.to_canonical_dict(),
        "symbol": entry.symbol,
        "quantity": str(fill.filled_quantity),
        "average_cost": str(fill.fill_price),
        "opened_at": timestamp(fill.observed_at),
        "peak_price": str(fill.fill_price),
        "limitations": list(limitations),
    }
    artifact_id, digest = content_identity("shadow-position", payload)
    return ShadowPosition(
        artifact_id, digest, fill_ref, entry.symbol, fill.filled_quantity, fill.fill_price, fill.observed_at, fill.fill_price, limitations
    )


def assess_holding(
    *,
    position: ShadowPosition,
    policy: StrategyShadowPolicy,
    assessed_at: datetime,
    sessions_held: int,
    current_price: Decimal | None,
    signal_reversed: bool,
    market_deteriorated: bool,
    theme_deteriorated: bool,
    capital_deteriorated: bool,
) -> HoldingAssessment:
    position_ref = reference("SHADOW_POSITION", position.position_id, position.position_hash)
    policy_ref = reference("STRATEGY_SHADOW_POLICY", policy.policy_id, policy.policy_hash)
    triggered: set[HoldingRuleKind] = set()
    reasons: tuple[str, ...]
    if current_price is None:
        decision, reasons, unrealized, drawdown = ShadowHoldingDecision.DATA_INSUFFICIENT, ("CURRENT_PRICE_MISSING",), None, None
    else:
        unrealized = current_price / position.average_cost - Decimal("1")
        peak = max(position.peak_price, current_price)
        drawdown = current_price / peak - Decimal("1")
        checks = (
            (HoldingRuleKind.FIXED_TIME, sessions_held >= policy.fixed_horizon_sessions),
            (HoldingRuleKind.SIGNAL_REVERSAL, signal_reversed),
            (HoldingRuleKind.MARKET_DETERIORATION, market_deteriorated),
            (HoldingRuleKind.THEME_DETERIORATION, theme_deteriorated),
            (HoldingRuleKind.CAPITAL_DETERIORATION, capital_deteriorated),
            (HoldingRuleKind.TRAILING_PROTECTION, drawdown <= -policy.trailing_drawdown),
            (HoldingRuleKind.LOSS_PROTECTION, unrealized <= policy.protection_return),
            (HoldingRuleKind.MULTI_HORIZON, sessions_held in {1, policy.fixed_horizon_sessions}),
        )
        triggered = {kind for kind, result in checks if kind in policy.rule_kinds and result}
        decision = ShadowHoldingDecision.ASSESS_EXIT if triggered else ShadowHoldingDecision.CONTINUE
        reasons = tuple(sorted(kind.value for kind in triggered)) if triggered else ("NO_EXIT_RULE_TRIGGERED",)
    ordered = tuple(sorted(triggered, key=lambda item: item.value))
    payload = {
        "position_reference": position_ref.to_canonical_dict(),
        "policy_reference": policy_ref.to_canonical_dict(),
        "assessed_at": timestamp(assessed_at),
        "sessions_held": sessions_held,
        "current_price": None if current_price is None else str(current_price),
        "unrealized_return": None if unrealized is None else str(unrealized),
        "peak_drawdown": None if drawdown is None else str(drawdown),
        "triggered_rules": [item.value for item in ordered],
        "decision": decision.value,
        "reason_codes": list(reasons),
    }
    artifact_id, digest = content_identity("shadow-holding-assessment", payload)
    return HoldingAssessment(
        artifact_id,
        digest,
        position_ref,
        policy_ref,
        assessed_at,
        sessions_held,
        current_price,
        unrealized,
        drawdown,
        ordered,
        decision,
        tuple(reasons),
    )


def assess_exit(*, holding: HoldingAssessment, position: ShadowPosition, assessed_at: datetime) -> ExitAssessment:
    holding_ref = reference("HOLDING_ASSESSMENT", holding.assessment_id, holding.assessment_hash)
    if holding.decision is ShadowHoldingDecision.DATA_INSUFFICIENT:
        decision, price, quantity, reasons = ShadowExitDecision.DATA_INSUFFICIENT, None, Decimal("0"), holding.reason_codes
    elif holding.decision is ShadowHoldingDecision.ASSESS_EXIT:
        decision, price, quantity, reasons = ShadowExitDecision.SHADOW_EXIT, holding.current_price, position.quantity, holding.reason_codes
    else:
        decision, price, quantity, reasons = ShadowExitDecision.SHADOW_HOLD, None, Decimal("0"), ("HOLDING_CONTINUES",)
    payload = {
        "holding_reference": holding_ref.to_canonical_dict(),
        "decision": decision.value,
        "exit_price": None if price is None else str(price),
        "exit_quantity": str(quantity),
        "triggered_rules": [item.value for item in holding.triggered_rules],
        "assessed_at": timestamp(assessed_at),
        "reason_codes": list(reasons),
    }
    artifact_id, digest = content_identity("shadow-exit-assessment", payload)
    return ExitAssessment(artifact_id, digest, holding_ref, decision, price, quantity, holding.triggered_rules, assessed_at, tuple(reasons))


def settle_strategy_outcome(
    *,
    entry: ShadowEntry,
    fill: ShadowFill,
    position: ShadowPosition,
    exit_assessment: ExitAssessment,
    exit_cost: Decimal,
    mfe: Decimal | None,
    mae: Decimal | None,
) -> StrategyOutcome:
    if exit_assessment.decision is not ShadowExitDecision.SHADOW_EXIT or exit_assessment.exit_price is None:
        raise ValueError("Strategy Outcome requires completed Shadow Exit")
    gross = exit_assessment.exit_price / position.average_cost - Decimal("1")
    entry_cost = fill.slippage_cost + fill.market_impact_cost + fill.commission_cost
    notional = position.average_cost * position.quantity
    total_cost = Decimal("0") if notional == 0 else (entry_cost + exit_cost) / notional
    net = gross - total_cost
    entry_ref, fill_ref, position_ref, exit_ref = (
        reference("SHADOW_ENTRY", entry.entry_id, entry.entry_hash),
        reference("SHADOW_FILL", fill.fill_id, fill.fill_hash),
        reference("SHADOW_POSITION", position.position_id, position.position_hash),
        reference("EXIT_ASSESSMENT", exit_assessment.assessment_id, exit_assessment.assessment_hash),
    )
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "HOLDING_EXIT_VALIDATED_FALSE", "STRATEGY_SHADOW_PROVEN_FALSE"}))
    payload = _outcome_payload(
        entry_ref,
        fill_ref,
        position_ref,
        exit_ref,
        entry.symbol,
        position.opened_at,
        exit_assessment.assessed_at,
        gross,
        total_cost,
        net,
        mfe,
        mae,
        limitations,
    )
    artifact_id, digest = content_identity("strategy-shadow-outcome", payload)
    return StrategyOutcome(
        artifact_id,
        digest,
        entry_ref,
        fill_ref,
        position_ref,
        exit_ref,
        entry.symbol,
        position.opened_at,
        exit_assessment.assessed_at,
        gross,
        total_cost,
        net,
        mfe,
        mae,
        True,
        limitations,
    )


def _outcome_payload(
    entry: ValidationArtifactReference,
    fill: ValidationArtifactReference,
    position: ValidationArtifactReference,
    exit_assessment: ValidationArtifactReference,
    symbol: str,
    opened_at: datetime,
    closed_at: datetime,
    gross: Decimal,
    cost: Decimal,
    net: Decimal,
    mfe: Decimal | None,
    mae: Decimal | None,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema": "strategy-shadow-outcome/v1",
        "entry_reference": entry.to_canonical_dict(),
        "fill_reference": fill.to_canonical_dict(),
        "position_reference": position.to_canonical_dict(),
        "exit_reference": exit_assessment.to_canonical_dict(),
        "symbol": symbol,
        "opened_at": timestamp(opened_at),
        "closed_at": timestamp(closed_at),
        "gross_return": str(gross),
        "total_cost": str(cost),
        "net_return": str(net),
        "mfe": None if mfe is None else str(mfe),
        "mae": None if mae is None else str(mae),
        "settled": True,
        "limitations": list(limitations),
    }
