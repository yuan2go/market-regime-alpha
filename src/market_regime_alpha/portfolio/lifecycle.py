"""Explicit-config portfolio construction and independent hard-risk contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import (
    ArtifactId,
    PortfolioDecisionId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


RISK_BUDGET_SCHEMA = "risk-budget-v1"
PORTFOLIO_DECISION_SCHEMA = "portfolio-decision-v1"
RISK_DECISION_SCHEMA = "risk-decision-v1"


class PortfolioOutputMode(str, Enum):
    SIMULATION = "SIMULATION"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"


class PortfolioDecisionState(str, Enum):
    PROPOSED_FOR_RISK = "PROPOSED_FOR_RISK"
    CONFLICTED = "CONFLICTED"


class RiskDecisionState(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class PortfolioConstraintType(str, Enum):
    MAXIMUM_GROSS_EXPOSURE = "MAXIMUM_GROSS_EXPOSURE"
    SINGLE_SYMBOL_LIMIT = "SINGLE_SYMBOL_LIMIT"
    THEME_LIMIT = "THEME_LIMIT"
    LIQUIDITY_LIMIT = "LIQUIDITY_LIMIT"
    AVAILABLE_CASH = "AVAILABLE_CASH"
    CURRENT_POSITION = "CURRENT_POSITION"
    T_PLUS_ONE = "T_PLUS_ONE"
    MAXIMUM_LOSS_BUDGET = "MAXIMUM_LOSS_BUDGET"


@dataclass(frozen=True, slots=True)
class RiskBudget:
    profile_id: str
    configuration_id: ArtifactId
    configuration_hash: str
    maximum_gross_exposure: float
    single_symbol_limit: float
    theme_limit: float
    liquidity_max_participation: float
    minimum_cash_reserve: float
    maximum_loss_budget: float
    t_plus_one_enforced: bool
    risk_service_timeout_seconds: float
    market_scope: str
    allowed_side: str
    schema_version: str

    def __post_init__(self) -> None:
        for label, text_value in (
            ("profile_id", self.profile_id),
            ("market_scope", self.market_scope),
            ("allowed_side", self.allowed_side),
            ("schema_version", self.schema_version),
        ):
            _text(label, text_value)
        if self.schema_version != RISK_BUDGET_SCHEMA:
            raise ValueError("unsupported RiskBudget schema")
        if self.market_scope != "A_SHARE" or self.allowed_side != "LONG_ONLY":
            raise ValueError("RiskBudget V1 is restricted to A_SHARE LONG_ONLY")
        for label, numeric_value in (
            ("maximum_gross_exposure", self.maximum_gross_exposure),
            ("single_symbol_limit", self.single_symbol_limit),
            ("theme_limit", self.theme_limit),
            ("liquidity_max_participation", self.liquidity_max_participation),
            ("minimum_cash_reserve", self.minimum_cash_reserve),
            ("maximum_loss_budget", self.maximum_loss_budget),
        ):
            if not isfinite(numeric_value) or not 0.0 <= numeric_value <= 1.0:
                raise ValueError(f"{label} must be within [0, 1]")
        if (
            not isfinite(self.risk_service_timeout_seconds)
            or self.risk_service_timeout_seconds <= 0.0
        ):
            raise ValueError("risk service timeout must be positive and finite")
        require_sha256("configuration_hash", self.configuration_hash)
        semantic = self.semantic_payload()
        if canonical_hash(semantic) != self.configuration_hash:
            raise ValueError("RiskBudget configuration hash mismatch")
        digest = self.configuration_hash.split(":", 1)[1]
        if self.configuration_id != ArtifactId(f"risk-budget-{digest[:24]}"):
            raise ValueError("RiskBudget configuration identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "maximum_gross_exposure": self.maximum_gross_exposure,
            "single_symbol_limit": self.single_symbol_limit,
            "theme_limit": self.theme_limit,
            "liquidity_max_participation": self.liquidity_max_participation,
            "minimum_cash_reserve": self.minimum_cash_reserve,
            "maximum_loss_budget": self.maximum_loss_budget,
            "t_plus_one_enforced": self.t_plus_one_enforced,
            "risk_service_timeout_seconds": self.risk_service_timeout_seconds,
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
        maximum_gross_exposure: float,
        single_symbol_limit: float,
        theme_limit: float,
        liquidity_max_participation: float,
        minimum_cash_reserve: float,
        maximum_loss_budget: float,
        t_plus_one_enforced: bool,
        risk_service_timeout_seconds: float,
        market_scope: str,
        allowed_side: str,
        schema_version: str,
    ) -> RiskBudget:
        semantic = {
            "profile_id": profile_id,
            "maximum_gross_exposure": maximum_gross_exposure,
            "single_symbol_limit": single_symbol_limit,
            "theme_limit": theme_limit,
            "liquidity_max_participation": liquidity_max_participation,
            "minimum_cash_reserve": minimum_cash_reserve,
            "maximum_loss_budget": maximum_loss_budget,
            "t_plus_one_enforced": t_plus_one_enforced,
            "risk_service_timeout_seconds": risk_service_timeout_seconds,
            "market_scope": market_scope,
            "allowed_side": allowed_side,
            "schema_version": schema_version,
        }
        digest = canonical_hash(semantic)
        return cls(
            profile_id=profile_id,
            configuration_id=ArtifactId(
                f"risk-budget-{digest.split(':', 1)[1][:24]}"
            ),
            configuration_hash=digest,
            maximum_gross_exposure=maximum_gross_exposure,
            single_symbol_limit=single_symbol_limit,
            theme_limit=theme_limit,
            liquidity_max_participation=liquidity_max_participation,
            minimum_cash_reserve=minimum_cash_reserve,
            maximum_loss_budget=maximum_loss_budget,
            t_plus_one_enforced=t_plus_one_enforced,
            risk_service_timeout_seconds=risk_service_timeout_seconds,
            market_scope=market_scope,
            allowed_side=allowed_side,
            schema_version=schema_version,
        )

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> RiskBudget:
        expected = {
            "profile_id",
            "configuration_id",
            "configuration_hash",
            "maximum_gross_exposure",
            "single_symbol_limit",
            "theme_limit",
            "liquidity_max_participation",
            "minimum_cash_reserve",
            "maximum_loss_budget",
            "t_plus_one_enforced",
            "risk_service_timeout_seconds",
            "market_scope",
            "allowed_side",
            "schema_version",
        }
        if set(payload) != expected or not isinstance(payload["t_plus_one_enforced"], bool):
            raise ValueError("RiskBudget fields mismatch")
        return cls(
            profile_id=str(payload["profile_id"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            maximum_gross_exposure=float(payload["maximum_gross_exposure"]),
            single_symbol_limit=float(payload["single_symbol_limit"]),
            theme_limit=float(payload["theme_limit"]),
            liquidity_max_participation=float(payload["liquidity_max_participation"]),
            minimum_cash_reserve=float(payload["minimum_cash_reserve"]),
            maximum_loss_budget=float(payload["maximum_loss_budget"]),
            t_plus_one_enforced=payload["t_plus_one_enforced"],
            risk_service_timeout_seconds=float(payload["risk_service_timeout_seconds"]),
            market_scope=str(payload["market_scope"]),
            allowed_side=str(payload["allowed_side"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class PortfolioAccountSnapshot:
    net_asset_value: float
    available_cash: float
    observed_at: datetime
    source_reference: str

    def __post_init__(self) -> None:
        if not isfinite(self.net_asset_value) or self.net_asset_value <= 0.0:
            raise ValueError("net asset value must be positive and finite")
        if not isfinite(self.available_cash) or self.available_cash < 0.0:
            raise ValueError("available cash must be non-negative and finite")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("account snapshot time must be timezone-aware")
        _text("source_reference", self.source_reference)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "net_asset_value": self.net_asset_value,
            "available_cash": self.available_cash,
            "observed_at": self.observed_at.isoformat(),
            "source_reference": self.source_reference,
        }


@dataclass(frozen=True, slots=True)
class CurrentPositionInput:
    symbol: str
    total_quantity: int
    available_quantity: int
    market_price: float

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        if self.total_quantity < 0 or self.available_quantity < 0:
            raise ValueError("position quantities cannot be negative")
        if self.available_quantity > self.total_quantity:
            raise ValueError("available quantity cannot exceed total quantity")
        if not isfinite(self.market_price) or self.market_price <= 0.0:
            raise ValueError("position market price must be positive and finite")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "market_price": self.market_price,
        }


@dataclass(frozen=True, slots=True)
class ThesisAllocationRequest:
    thesis_id: ThesisId
    symbol: str
    theme_id: str
    target_quantity: int
    reference_price: float
    average_daily_trade_value: float
    loss_per_share: float

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        _text("theme_id", self.theme_id)
        if self.target_quantity < 0:
            raise ValueError("long-only target quantity cannot be negative")
        for label, value in (
            ("reference_price", self.reference_price),
            ("average_daily_trade_value", self.average_daily_trade_value),
            ("loss_per_share", self.loss_per_share),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{label} must be positive and finite")


@dataclass(frozen=True, slots=True)
class TargetPosition:
    thesis_id: ThesisId
    symbol: str
    theme_id: str
    current_quantity: int
    available_quantity: int
    target_quantity: int
    trade_quantity: int
    reference_price: float
    average_daily_trade_value: float
    loss_per_share: float

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        _text("theme_id", self.theme_id)
        if self.trade_quantity != self.target_quantity - self.current_quantity:
            raise ValueError("TargetPosition trade quantity mismatch")
        if min(self.current_quantity, self.available_quantity, self.target_quantity) < 0:
            raise ValueError("TargetPosition quantities cannot be negative")
        if self.available_quantity > self.current_quantity:
            raise ValueError("TargetPosition available quantity exceeds current")
        for label, value in (
            ("reference_price", self.reference_price),
            ("average_daily_trade_value", self.average_daily_trade_value),
            ("loss_per_share", self.loss_per_share),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{label} must be positive and finite")

    @property
    def target_value(self) -> float:
        return self.target_quantity * self.reference_price

    @property
    def trade_value(self) -> float:
        return self.trade_quantity * self.reference_price

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "thesis_id": str(self.thesis_id),
            "symbol": self.symbol,
            "theme_id": self.theme_id,
            "current_quantity": self.current_quantity,
            "available_quantity": self.available_quantity,
            "target_quantity": self.target_quantity,
            "trade_quantity": self.trade_quantity,
            "reference_price": self.reference_price,
            "average_daily_trade_value": self.average_daily_trade_value,
            "loss_per_share": self.loss_per_share,
        }


@dataclass(frozen=True, slots=True)
class PortfolioConstraint:
    constraint_type: PortfolioConstraintType
    passed: bool
    observed_value: float
    limit_value: float
    reason_code: str
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isfinite(self.observed_value) or not isfinite(self.limit_value):
            raise ValueError("constraint values must be finite")
        _text("reason_code", self.reason_code)
        if self.symbols != tuple(sorted(set(self.symbols))):
            raise ValueError("constraint symbols must be sorted and unique")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "constraint_type": self.constraint_type.value,
            "passed": self.passed,
            "observed_value": self.observed_value,
            "limit_value": self.limit_value,
            "reason_code": self.reason_code,
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True, slots=True)
class PortfolioDecision:
    schema_version: str
    decision_id: PortfolioDecisionId
    mode: PortfolioOutputMode
    state: PortfolioDecisionState
    risk_budget_id: ArtifactId
    risk_budget_hash: str
    risk_budget: RiskBudget
    account_snapshot: PortfolioAccountSnapshot
    target_positions: tuple[TargetPosition, ...]
    thesis_ids: tuple[ThesisId, ...]
    version: int
    actor: str
    reason: str
    created_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PORTFOLIO_DECISION_SCHEMA or self.version != 0:
            raise ValueError("unsupported or non-initial PortfolioDecision")
        require_sha256("risk_budget_hash", self.risk_budget_hash)
        if (
            self.risk_budget_id != self.risk_budget.configuration_id
            or self.risk_budget_hash != self.risk_budget.configuration_hash
        ):
            raise ValueError("PortfolioDecision RiskBudget snapshot mismatch")
        _text("actor", self.actor)
        _text("reason", self.reason)
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("PortfolioDecision created_at must be timezone-aware")
        symbols = tuple(item.symbol for item in self.target_positions)
        if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
            raise ValueError("TargetPositions must be symbol-sorted and unique")
        if self.thesis_ids != tuple(sorted(set(self.thesis_ids), key=str)):
            raise ValueError("Portfolio thesis IDs must be sorted and unique")
        if self.state is PortfolioDecisionState.CONFLICTED and self.target_positions:
            raise ValueError("conflicted PortfolioDecision cannot carry targets")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": str(self.decision_id),
            "mode": self.mode.value,
            "state": self.state.value,
            "risk_budget_id": str(self.risk_budget_id),
            "risk_budget_hash": self.risk_budget_hash,
            "risk_budget": self.risk_budget.to_canonical_dict(),
            "account_snapshot": self.account_snapshot.to_canonical_dict(),
            "target_positions": [item.to_canonical_dict() for item in self.target_positions],
            "thesis_ids": [str(item) for item in self.thesis_ids],
            "version": self.version,
            "actor": self.actor,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class RiskDecision:
    schema_version: str
    risk_decision_id: RiskDecisionId
    portfolio_decision_id: PortfolioDecisionId
    portfolio_decision_version: int
    risk_budget_id: ArtifactId
    risk_budget_hash: str
    risk_budget: RiskBudget
    mode: PortfolioOutputMode
    state: RiskDecisionState
    constraints: tuple[PortfolioConstraint, ...]
    version: int
    actor: str
    reason: str
    started_at: datetime
    completed_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RISK_DECISION_SCHEMA or self.version != 0:
            raise ValueError("unsupported or non-initial RiskDecision")
        require_sha256("risk_budget_hash", self.risk_budget_hash)
        if (
            self.risk_budget_id != self.risk_budget.configuration_id
            or self.risk_budget_hash != self.risk_budget.configuration_hash
        ):
            raise ValueError("RiskDecision RiskBudget snapshot mismatch")
        if self.completed_at < self.started_at:
            raise ValueError("RiskDecision completion cannot precede start")
        for label, text_value in (("actor", self.actor), ("reason", self.reason)):
            _text(label, text_value)
        for label, datetime_value in (
            ("started_at", self.started_at),
            ("completed_at", self.completed_at),
        ):
            if datetime_value.tzinfo is None or datetime_value.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware")
        if self.state is RiskDecisionState.APPROVED and any(
            not item.passed for item in self.constraints
        ):
            raise ValueError("approved RiskDecision cannot contain failed constraint")
        if self.state is not RiskDecisionState.APPROVED and not self.reason_codes:
            raise ValueError("non-approved RiskDecision requires reason_codes")

    @property
    def approved_for_manual_intent(self) -> bool:
        return self.state is RiskDecisionState.APPROVED

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "risk_decision_id": str(self.risk_decision_id),
            "portfolio_decision_id": str(self.portfolio_decision_id),
            "portfolio_decision_version": self.portfolio_decision_version,
            "risk_budget_id": str(self.risk_budget_id),
            "risk_budget_hash": self.risk_budget_hash,
            "risk_budget": self.risk_budget.to_canonical_dict(),
            "mode": self.mode.value,
            "state": self.state.value,
            "constraints": [item.to_canonical_dict() for item in self.constraints],
            "version": self.version,
            "actor": self.actor,
            "reason": self.reason,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "reason_codes": list(self.reason_codes),
        }


def _text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
