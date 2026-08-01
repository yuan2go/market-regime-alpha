"""Complete-account Portfolio construction and independent Risk Authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    PortfolioDecisionId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
)
from market_regime_alpha.portfolio.lifecycle import (
    PortfolioConstraint,
    PortfolioConstraintType,
    PortfolioOutputMode,
    RiskBudget,
    RiskDecisionState,
    ThesisAllocationRequest,
)


ACCOUNT_PORTFOLIO_SNAPSHOT_SCHEMA = "authoritative-account-portfolio-snapshot-v1"
COMPLETE_ACCOUNT_RISK_CONFIGURATION_SCHEMA = (
    "complete-account-risk-configuration-v1"
)
POST_TRADE_PORTFOLIO_SCHEMA = "post-trade-portfolio-snapshot-v1"
COMPLETE_ACCOUNT_PORTFOLIO_DECISION_SCHEMA = "complete-account-portfolio-decision-v1"
COMPLETE_ACCOUNT_RISK_DECISION_SCHEMA = "complete-account-risk-decision-v1"


class AccountPortfolioCompleteness(str, Enum):
    COMPLETE_ACCOUNT = "COMPLETE_ACCOUNT"
    PARTIAL = "PARTIAL"


class AccountReconciliationState(str, Enum):
    RECONCILED = "RECONCILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AccountPosition:
    symbol: str
    theme_id: str
    total_quantity: int
    available_quantity: int
    market_price: float
    loss_per_share: float
    source_position_snapshot_id: ArtifactId
    source_position_snapshot_hash: str

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        _text("theme_id", self.theme_id)
        if self.total_quantity <= 0:
            raise ValueError("account position quantity must be positive")
        if not 0 <= self.available_quantity <= self.total_quantity:
            raise ValueError("account available quantity is invalid")
        _positive("market_price", self.market_price)
        _positive("loss_per_share", self.loss_per_share)
        require_sha256(
            "source_position_snapshot_hash",
            self.source_position_snapshot_hash,
        )

    @property
    def market_value(self) -> float:
        return self.total_quantity * self.market_price

    @property
    def maximum_loss(self) -> float:
        return self.total_quantity * self.loss_per_share

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "theme_id": self.theme_id,
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "market_price": self.market_price,
            "loss_per_share": self.loss_per_share,
            "source_position_snapshot_id": str(
                self.source_position_snapshot_id
            ),
            "source_position_snapshot_hash": self.source_position_snapshot_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> AccountPosition:
        _fields(
            payload,
            {
                "symbol",
                "theme_id",
                "total_quantity",
                "available_quantity",
                "market_price",
                "loss_per_share",
                "source_position_snapshot_id",
                "source_position_snapshot_hash",
            },
            "AccountPosition",
        )
        return cls(
            symbol=str(payload["symbol"]),
            theme_id=str(payload["theme_id"]),
            total_quantity=int(payload["total_quantity"]),
            available_quantity=int(payload["available_quantity"]),
            market_price=float(payload["market_price"]),
            loss_per_share=float(payload["loss_per_share"]),
            source_position_snapshot_id=ArtifactId(
                str(payload["source_position_snapshot_id"])
            ),
            source_position_snapshot_hash=str(
                payload["source_position_snapshot_hash"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AuthoritativeAccountPortfolioSnapshot:
    schema_version: str
    snapshot_id: ArtifactId
    account_id: str
    as_of: datetime
    source_reference: str
    net_asset_value: float
    available_cash: float
    all_positions: tuple[AccountPosition, ...]
    completeness: AccountPortfolioCompleteness
    reconciliation_state: AccountReconciliationState
    version: int
    content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != ACCOUNT_PORTFOLIO_SNAPSHOT_SCHEMA:
            raise ValueError("unsupported account Portfolio snapshot schema")
        _text("account_id", self.account_id)
        _text("source_reference", self.source_reference)
        _aware("account snapshot as_of", self.as_of)
        _positive("net_asset_value", self.net_asset_value)
        if not isfinite(self.available_cash) or self.available_cash < 0.0:
            raise ValueError("available cash must be non-negative and finite")
        if self.version < 0:
            raise ValueError("account snapshot version cannot be negative")
        symbols = tuple(item.symbol for item in self.all_positions)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("account positions must be symbol-sorted and unique")
        require_sha256("content_hash", self.content_hash)
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("account Portfolio snapshot content hash mismatch")
        digest = self.content_hash.split(":", 1)[1]
        if self.snapshot_id != ArtifactId(
            f"account-portfolio-snapshot-{digest[:24]}"
        ):
            raise ValueError("account Portfolio snapshot identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "account_id": self.account_id,
            "as_of": self.as_of.isoformat(),
            "source_reference": self.source_reference,
            "net_asset_value": self.net_asset_value,
            "available_cash": self.available_cash,
            "all_positions": [
                item.to_canonical_dict() for item in self.all_positions
            ],
            "completeness": self.completeness.value,
            "reconciliation_state": self.reconciliation_state.value,
            "version": self.version,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "snapshot_id": str(self.snapshot_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        as_of: datetime,
        source_reference: str,
        net_asset_value: float,
        available_cash: float,
        all_positions: tuple[AccountPosition, ...],
        completeness: AccountPortfolioCompleteness,
        reconciliation_state: AccountReconciliationState,
        version: int,
    ) -> AuthoritativeAccountPortfolioSnapshot:
        ordered = tuple(sorted(all_positions, key=lambda item: item.symbol))
        semantic = {
            "schema_version": ACCOUNT_PORTFOLIO_SNAPSHOT_SCHEMA,
            "account_id": account_id,
            "as_of": as_of.isoformat(),
            "source_reference": source_reference,
            "net_asset_value": net_asset_value,
            "available_cash": available_cash,
            "all_positions": [item.to_canonical_dict() for item in ordered],
            "completeness": completeness.value,
            "reconciliation_state": reconciliation_state.value,
            "version": version,
        }
        digest = canonical_hash(semantic)
        return cls(
            schema_version=ACCOUNT_PORTFOLIO_SNAPSHOT_SCHEMA,
            snapshot_id=ArtifactId(
                f"account-portfolio-snapshot-{digest.split(':', 1)[1][:24]}"
            ),
            account_id=account_id,
            as_of=as_of,
            source_reference=source_reference,
            net_asset_value=net_asset_value,
            available_cash=available_cash,
            all_positions=ordered,
            completeness=completeness,
            reconciliation_state=reconciliation_state,
            version=version,
            content_hash=digest,
        )

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> AuthoritativeAccountPortfolioSnapshot:
        expected = {
            "schema_version",
            "snapshot_id",
            "account_id",
            "as_of",
            "source_reference",
            "net_asset_value",
            "available_cash",
            "all_positions",
            "completeness",
            "reconciliation_state",
            "version",
            "content_hash",
        }
        _fields(payload, expected, "AuthoritativeAccountPortfolioSnapshot")
        return cls(
            schema_version=str(payload["schema_version"]),
            snapshot_id=ArtifactId(str(payload["snapshot_id"])),
            account_id=str(payload["account_id"]),
            as_of=datetime.fromisoformat(str(payload["as_of"])),
            source_reference=str(payload["source_reference"]),
            net_asset_value=float(payload["net_asset_value"]),
            available_cash=float(payload["available_cash"]),
            all_positions=tuple(
                AccountPosition.from_canonical_dict(_mapping(item))
                for item in _array(payload["all_positions"])
            ),
            completeness=AccountPortfolioCompleteness(
                str(payload["completeness"])
            ),
            reconciliation_state=AccountReconciliationState(
                str(payload["reconciliation_state"])
            ),
            version=int(payload["version"]),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class CompleteAccountRiskConfiguration:
    profile_id: str
    risk_budget: RiskBudget
    maximum_account_snapshot_age_seconds: float
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != COMPLETE_ACCOUNT_RISK_CONFIGURATION_SCHEMA:
            raise ValueError("unsupported complete-account Risk configuration")
        _text("profile_id", self.profile_id)
        _positive(
            "maximum_account_snapshot_age_seconds",
            self.maximum_account_snapshot_age_seconds,
        )
        require_sha256("configuration_hash", self.configuration_hash)
        if canonical_hash(self.semantic_payload()) != self.configuration_hash:
            raise ValueError("complete-account Risk configuration hash mismatch")
        digest = self.configuration_hash.split(":", 1)[1]
        if self.configuration_id != ArtifactId(
            f"complete-account-risk-config-{digest[:24]}"
        ):
            raise ValueError("complete-account Risk configuration identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "risk_budget": self.risk_budget.to_canonical_dict(),
            "maximum_account_snapshot_age_seconds": (
                self.maximum_account_snapshot_age_seconds
            ),
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
        risk_budget: RiskBudget,
        maximum_account_snapshot_age_seconds: float,
        schema_version: str,
    ) -> CompleteAccountRiskConfiguration:
        semantic = {
            "profile_id": profile_id,
            "risk_budget": risk_budget.to_canonical_dict(),
            "maximum_account_snapshot_age_seconds": (
                maximum_account_snapshot_age_seconds
            ),
            "schema_version": schema_version,
        }
        digest = canonical_hash(semantic)
        return cls(
            profile_id=profile_id,
            risk_budget=risk_budget,
            maximum_account_snapshot_age_seconds=(
                maximum_account_snapshot_age_seconds
            ),
            schema_version=schema_version,
            configuration_id=ArtifactId(
                f"complete-account-risk-config-{digest.split(':', 1)[1][:24]}"
            ),
            configuration_hash=digest,
        )

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompleteAccountRiskConfiguration:
        _fields(
            payload,
            {
                "profile_id",
                "risk_budget",
                "maximum_account_snapshot_age_seconds",
                "schema_version",
                "configuration_id",
                "configuration_hash",
            },
            "CompleteAccountRiskConfiguration",
        )
        return cls(
            profile_id=str(payload["profile_id"]),
            risk_budget=RiskBudget.from_canonical_dict(
                dict(_mapping(payload["risk_budget"]))
            ),
            maximum_account_snapshot_age_seconds=float(
                payload["maximum_account_snapshot_age_seconds"]
            ),
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
        )


@dataclass(frozen=True, slots=True)
class ProposedTradeDelta:
    thesis_id: ThesisId
    symbol: str
    theme_id: str
    current_quantity: int
    current_available_quantity: int
    target_quantity: int
    trade_quantity: int
    reference_price: float
    average_daily_trade_value: float
    loss_per_share: float

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        _text("theme_id", self.theme_id)
        if min(
            self.current_quantity,
            self.current_available_quantity,
            self.target_quantity,
        ) < 0:
            raise ValueError("complete-account trade quantities cannot be negative")
        if self.current_available_quantity > self.current_quantity:
            raise ValueError("current available quantity exceeds current quantity")
        if self.trade_quantity != self.target_quantity - self.current_quantity:
            raise ValueError("complete-account trade delta mismatch")
        _positive("reference_price", self.reference_price)
        _positive("average_daily_trade_value", self.average_daily_trade_value)
        _positive("loss_per_share", self.loss_per_share)

    @property
    def trade_value(self) -> float:
        return self.trade_quantity * self.reference_price

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "thesis_id": str(self.thesis_id),
            "symbol": self.symbol,
            "theme_id": self.theme_id,
            "current_quantity": self.current_quantity,
            "current_available_quantity": self.current_available_quantity,
            "target_quantity": self.target_quantity,
            "trade_quantity": self.trade_quantity,
            "reference_price": self.reference_price,
            "average_daily_trade_value": self.average_daily_trade_value,
            "loss_per_share": self.loss_per_share,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ProposedTradeDelta:
        _fields(
            payload,
            {
                "thesis_id",
                "symbol",
                "theme_id",
                "current_quantity",
                "current_available_quantity",
                "target_quantity",
                "trade_quantity",
                "reference_price",
                "average_daily_trade_value",
                "loss_per_share",
            },
            "ProposedTradeDelta",
        )
        return cls(
            thesis_id=ThesisId(str(payload["thesis_id"])),
            symbol=str(payload["symbol"]),
            theme_id=str(payload["theme_id"]),
            current_quantity=int(payload["current_quantity"]),
            current_available_quantity=int(
                payload["current_available_quantity"]
            ),
            target_quantity=int(payload["target_quantity"]),
            trade_quantity=int(payload["trade_quantity"]),
            reference_price=float(payload["reference_price"]),
            average_daily_trade_value=float(
                payload["average_daily_trade_value"]
            ),
            loss_per_share=float(payload["loss_per_share"]),
        )


@dataclass(frozen=True, slots=True)
class PostTradePosition:
    symbol: str
    theme_id: str
    total_quantity: int
    available_quantity: int
    market_price: float
    loss_per_share: float

    def __post_init__(self) -> None:
        _text("symbol", self.symbol)
        _text("theme_id", self.theme_id)
        if self.total_quantity <= 0:
            raise ValueError("post-trade position quantity must be positive")
        if not 0 <= self.available_quantity <= self.total_quantity:
            raise ValueError("post-trade available quantity is invalid")
        _positive("market_price", self.market_price)
        _positive("loss_per_share", self.loss_per_share)

    @property
    def market_value(self) -> float:
        return self.total_quantity * self.market_price

    @property
    def maximum_loss(self) -> float:
        return self.total_quantity * self.loss_per_share

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "theme_id": self.theme_id,
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "market_price": self.market_price,
            "loss_per_share": self.loss_per_share,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PostTradePosition:
        _fields(
            payload,
            {
                "symbol",
                "theme_id",
                "total_quantity",
                "available_quantity",
                "market_price",
                "loss_per_share",
            },
            "PostTradePosition",
        )
        return cls(
            symbol=str(payload["symbol"]),
            theme_id=str(payload["theme_id"]),
            total_quantity=int(payload["total_quantity"]),
            available_quantity=int(payload["available_quantity"]),
            market_price=float(payload["market_price"]),
            loss_per_share=float(payload["loss_per_share"]),
        )


@dataclass(frozen=True, slots=True)
class PostTradePortfolioSnapshot:
    schema_version: str
    snapshot_id: ArtifactId
    account_snapshot_id: ArtifactId
    account_snapshot_hash: str
    account_id: str
    as_of: datetime
    available_cash: float
    positions: tuple[PostTradePosition, ...]
    proposed_deltas: tuple[ProposedTradeDelta, ...]
    configuration_id: ArtifactId
    configuration_hash: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_TRADE_PORTFOLIO_SCHEMA:
            raise ValueError("unsupported post-trade Portfolio schema")
        _text("account_id", self.account_id)
        _aware("post-trade as_of", self.as_of)
        if not isfinite(self.available_cash):
            raise ValueError("post-trade available cash must be finite")
        for label, value in (
            ("account_snapshot_hash", self.account_snapshot_hash),
            ("configuration_hash", self.configuration_hash),
            ("content_hash", self.content_hash),
        ):
            require_sha256(label, value)
        symbols = tuple(item.symbol for item in self.positions)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("post-trade positions must be sorted and unique")
        delta_symbols = tuple(item.symbol for item in self.proposed_deltas)
        if delta_symbols != tuple(sorted(set(delta_symbols))):
            raise ValueError("proposed deltas must be sorted and unique")
        if canonical_hash(self.semantic_payload()) != self.content_hash:
            raise ValueError("post-trade Portfolio hash mismatch")
        digest = self.content_hash.split(":", 1)[1]
        if self.snapshot_id != ArtifactId(
            f"post-trade-portfolio-{digest[:24]}"
        ):
            raise ValueError("post-trade Portfolio identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "account_snapshot_id": str(self.account_snapshot_id),
            "account_snapshot_hash": self.account_snapshot_hash,
            "account_id": self.account_id,
            "as_of": self.as_of.isoformat(),
            "available_cash": self.available_cash,
            "positions": [item.to_canonical_dict() for item in self.positions],
            "proposed_deltas": [
                item.to_canonical_dict() for item in self.proposed_deltas
            ],
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "snapshot_id": str(self.snapshot_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> PostTradePortfolioSnapshot:
        expected = {
            "schema_version",
            "snapshot_id",
            "account_snapshot_id",
            "account_snapshot_hash",
            "account_id",
            "as_of",
            "available_cash",
            "positions",
            "proposed_deltas",
            "configuration_id",
            "configuration_hash",
            "content_hash",
        }
        _fields(payload, expected, "PostTradePortfolioSnapshot")
        return cls(
            schema_version=str(payload["schema_version"]),
            snapshot_id=ArtifactId(str(payload["snapshot_id"])),
            account_snapshot_id=ArtifactId(str(payload["account_snapshot_id"])),
            account_snapshot_hash=str(payload["account_snapshot_hash"]),
            account_id=str(payload["account_id"]),
            as_of=datetime.fromisoformat(str(payload["as_of"])),
            available_cash=float(payload["available_cash"]),
            positions=tuple(
                PostTradePosition.from_canonical_dict(_mapping(item))
                for item in _array(payload["positions"])
            ),
            proposed_deltas=tuple(
                ProposedTradeDelta.from_canonical_dict(_mapping(item))
                for item in _array(payload["proposed_deltas"])
            ),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            content_hash=str(payload["content_hash"]),
        )


@dataclass(frozen=True, slots=True)
class CompleteAccountPortfolioDecision:
    schema_version: str
    decision_id: PortfolioDecisionId
    mode: PortfolioOutputMode
    configuration: CompleteAccountRiskConfiguration
    account_snapshot: AuthoritativeAccountPortfolioSnapshot
    post_trade: PostTradePortfolioSnapshot
    thesis_ids: tuple[ThesisId, ...]
    version: int
    actor: str
    reason: str
    created_at: datetime
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != COMPLETE_ACCOUNT_PORTFOLIO_DECISION_SCHEMA:
            raise ValueError("unsupported complete-account PortfolioDecision")
        if self.version != 0:
            raise ValueError("complete-account PortfolioDecision must be version 0")
        _text("actor", self.actor)
        _text("reason", self.reason)
        _aware("PortfolioDecision created_at", self.created_at)
        if self.post_trade.account_snapshot_id != self.account_snapshot.snapshot_id:
            raise ValueError("post-trade Portfolio account identity mismatch")
        if self.post_trade.account_snapshot_hash != self.account_snapshot.content_hash:
            raise ValueError("post-trade Portfolio account hash mismatch")
        if self.post_trade.configuration_id != self.configuration.configuration_id:
            raise ValueError("post-trade Portfolio configuration mismatch")
        if self.post_trade.configuration_hash != self.configuration.configuration_hash:
            raise ValueError("post-trade Portfolio configuration hash mismatch")
        expected_theses = tuple(
            sorted(
                (item.thesis_id for item in self.post_trade.proposed_deltas),
                key=str,
            )
        )
        if self.thesis_ids != expected_theses:
            raise ValueError("complete-account Portfolio thesis scope mismatch")
        if self.decision_id != _portfolio_decision_id(self.semantic_payload()):
            raise ValueError("complete-account PortfolioDecision identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "configuration": self.configuration.to_canonical_dict(),
            "account_snapshot": self.account_snapshot.to_canonical_dict(),
            "post_trade": self.post_trade.to_canonical_dict(),
            "thesis_ids": [str(item) for item in self.thesis_ids],
            "version": self.version,
            "actor": self.actor,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompleteAccountPortfolioDecision:
        expected = {
            "decision_id",
            "schema_version",
            "mode",
            "configuration",
            "account_snapshot",
            "post_trade",
            "thesis_ids",
            "version",
            "actor",
            "reason",
            "created_at",
            "reason_codes",
        }
        _fields(payload, expected, "CompleteAccountPortfolioDecision")
        return cls(
            schema_version=str(payload["schema_version"]),
            decision_id=PortfolioDecisionId(str(payload["decision_id"])),
            mode=PortfolioOutputMode(str(payload["mode"])),
            configuration=CompleteAccountRiskConfiguration.from_canonical_dict(
                _mapping(payload["configuration"])
            ),
            account_snapshot=(
                AuthoritativeAccountPortfolioSnapshot.from_canonical_dict(
                    _mapping(payload["account_snapshot"])
                )
            ),
            post_trade=PostTradePortfolioSnapshot.from_canonical_dict(
                _mapping(payload["post_trade"])
            ),
            thesis_ids=tuple(
                ThesisId(str(item)) for item in _array(payload["thesis_ids"])
            ),
            version=int(payload["version"]),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            reason_codes=tuple(
                str(item) for item in _array(payload["reason_codes"])
            ),
        )


@dataclass(frozen=True, slots=True)
class CompleteAccountRiskDecision:
    schema_version: str
    risk_decision_id: RiskDecisionId
    portfolio_decision_id: PortfolioDecisionId
    portfolio_decision_version: int
    post_trade_snapshot_id: ArtifactId
    post_trade_content_hash: str
    configuration_id: ArtifactId
    configuration_hash: str
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
        if self.schema_version != COMPLETE_ACCOUNT_RISK_DECISION_SCHEMA:
            raise ValueError("unsupported complete-account RiskDecision")
        if self.portfolio_decision_version != 0 or self.version != 0:
            raise ValueError("complete-account RiskDecision versions must be zero")
        for label, value in (
            ("post_trade_content_hash", self.post_trade_content_hash),
            ("configuration_hash", self.configuration_hash),
        ):
            require_sha256(label, value)
        _text("actor", self.actor)
        _text("reason", self.reason)
        _aware("RiskDecision started_at", self.started_at)
        _aware("RiskDecision completed_at", self.completed_at)
        if self.completed_at < self.started_at:
            raise ValueError("RiskDecision completion precedes start")
        if self.state is RiskDecisionState.APPROVED and any(
            not item.passed for item in self.constraints
        ):
            raise ValueError("approved complete-account Risk has failed constraints")
        if self.state is not RiskDecisionState.APPROVED and not self.reason_codes:
            raise ValueError("non-approved complete-account Risk requires reasons")
        if self.risk_decision_id != _risk_decision_id(self.semantic_payload()):
            raise ValueError("complete-account RiskDecision identity mismatch")

    @property
    def approved_for_manual_intent(self) -> bool:
        return self.state is RiskDecisionState.APPROVED

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "portfolio_decision_id": str(self.portfolio_decision_id),
            "portfolio_decision_version": self.portfolio_decision_version,
            "post_trade_snapshot_id": str(self.post_trade_snapshot_id),
            "post_trade_content_hash": self.post_trade_content_hash,
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
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

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "risk_decision_id": str(self.risk_decision_id),
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> CompleteAccountRiskDecision:
        expected = {
            "risk_decision_id",
            "schema_version",
            "portfolio_decision_id",
            "portfolio_decision_version",
            "post_trade_snapshot_id",
            "post_trade_content_hash",
            "configuration_id",
            "configuration_hash",
            "mode",
            "state",
            "constraints",
            "version",
            "actor",
            "reason",
            "started_at",
            "completed_at",
            "reason_codes",
        }
        _fields(payload, expected, "CompleteAccountRiskDecision")
        return cls(
            schema_version=str(payload["schema_version"]),
            risk_decision_id=RiskDecisionId(str(payload["risk_decision_id"])),
            portfolio_decision_id=PortfolioDecisionId(
                str(payload["portfolio_decision_id"])
            ),
            portfolio_decision_version=int(
                payload["portfolio_decision_version"]
            ),
            post_trade_snapshot_id=ArtifactId(
                str(payload["post_trade_snapshot_id"])
            ),
            post_trade_content_hash=str(payload["post_trade_content_hash"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            mode=PortfolioOutputMode(str(payload["mode"])),
            state=RiskDecisionState(str(payload["state"])),
            constraints=tuple(
                _constraint_from_dict(_mapping(item))
                for item in _array(payload["constraints"])
            ),
            version=int(payload["version"]),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            started_at=datetime.fromisoformat(str(payload["started_at"])),
            completed_at=datetime.fromisoformat(str(payload["completed_at"])),
            reason_codes=tuple(
                str(item) for item in _array(payload["reason_codes"])
            ),
        )


class CompleteAccountPortfolioConstructionService:
    """Build a proposal from one explicitly complete account snapshot."""

    def construct(
        self,
        *,
        theses: tuple[TradingThesis, ...],
        allocations: tuple[ThesisAllocationRequest, ...],
        account_snapshot: AuthoritativeAccountPortfolioSnapshot,
        configuration: CompleteAccountRiskConfiguration,
        mode: PortfolioOutputMode,
        actor: str,
        reason: str,
        created_at: datetime,
    ) -> CompleteAccountPortfolioDecision:
        if account_snapshot.as_of > created_at:
            raise ValueError("future account Portfolio snapshot is unavailable")
        thesis_by_id = {item.thesis_id: item for item in theses}
        allocation_by_id = {item.thesis_id: item for item in allocations}
        if len(thesis_by_id) != len(theses) or len(allocation_by_id) != len(allocations):
            raise ValueError("complete-account inputs require unique Thesis identities")
        if set(thesis_by_id) != set(allocation_by_id):
            raise ValueError("every complete-account Thesis requires one allocation")
        current = {item.symbol: item for item in account_snapshot.all_positions}
        allocation_symbols = tuple(item.symbol for item in allocations)
        if len(allocation_symbols) != len(set(allocation_symbols)):
            raise ValueError("one account cannot allocate multiple Thesis to one symbol")
        deltas: list[ProposedTradeDelta] = []
        for thesis_id, thesis in thesis_by_id.items():
            allocation = allocation_by_id[thesis_id]
            if thesis.state is not ThesisState.APPROVED:
                raise ValueError("only APPROVED Thesis can enter complete-account Portfolio")
            if created_at >= thesis.time_invalidation:
                raise ValueError("time-invalidated Thesis cannot enter Portfolio")
            if thesis.symbol != allocation.symbol:
                raise ValueError("Thesis and allocation symbol mismatch")
            position = current.get(allocation.symbol)
            if position is not None and position.theme_id != allocation.theme_id:
                raise ValueError("allocation theme conflicts with account Position")
            current_quantity = position.total_quantity if position else 0
            available_quantity = position.available_quantity if position else 0
            deltas.append(
                ProposedTradeDelta(
                    thesis_id=thesis_id,
                    symbol=allocation.symbol,
                    theme_id=allocation.theme_id,
                    current_quantity=current_quantity,
                    current_available_quantity=available_quantity,
                    target_quantity=allocation.target_quantity,
                    trade_quantity=allocation.target_quantity - current_quantity,
                    reference_price=allocation.reference_price,
                    average_daily_trade_value=allocation.average_daily_trade_value,
                    loss_per_share=allocation.loss_per_share,
                )
            )
        ordered_deltas = tuple(sorted(deltas, key=lambda item: item.symbol))
        post_trade = _apply_deltas(
            account_snapshot,
            ordered_deltas,
            configuration=configuration,
            as_of=created_at,
        )
        thesis_ids = tuple(sorted(thesis_by_id, key=str))
        semantic = {
            "schema_version": COMPLETE_ACCOUNT_PORTFOLIO_DECISION_SCHEMA,
            "mode": mode.value,
            "configuration": configuration.to_canonical_dict(),
            "account_snapshot": account_snapshot.to_canonical_dict(),
            "post_trade": post_trade.to_canonical_dict(),
            "thesis_ids": [str(item) for item in thesis_ids],
            "version": 0,
            "actor": actor,
            "reason": reason,
            "created_at": created_at.isoformat(),
            "reason_codes": ["COMPLETE_ACCOUNT_POST_TRADE_PORTFOLIO_PROPOSED"],
        }
        return CompleteAccountPortfolioDecision(
            schema_version=COMPLETE_ACCOUNT_PORTFOLIO_DECISION_SCHEMA,
            decision_id=_portfolio_decision_id(semantic),
            mode=mode,
            configuration=configuration,
            account_snapshot=account_snapshot,
            post_trade=post_trade,
            thesis_ids=thesis_ids,
            version=0,
            actor=actor,
            reason=reason,
            created_at=created_at,
            reason_codes=("COMPLETE_ACCOUNT_POST_TRADE_PORTFOLIO_PROPOSED",),
        )


class CompleteAccountRiskService:
    """Recomputable hard Risk over the complete resulting account."""

    def assess(
        self,
        portfolio: CompleteAccountPortfolioDecision,
        *,
        actor: str,
        reason: str,
        started_at: datetime,
        completed_at: datetime,
    ) -> CompleteAccountRiskDecision:
        configuration = portfolio.configuration
        budget = configuration.risk_budget
        elapsed = (completed_at - started_at).total_seconds()
        age = (started_at - portfolio.account_snapshot.as_of).total_seconds()
        reasons: tuple[str, ...]
        if elapsed > budget.risk_service_timeout_seconds:
            state = RiskDecisionState.TIMEOUT
            constraints: tuple[PortfolioConstraint, ...] = ()
            reasons = ("RISK_SERVICE_TIMEOUT_FAIL_CLOSED",)
        elif age < 0.0:
            state = RiskDecisionState.DATA_INSUFFICIENT
            constraints = ()
            reasons = ("ACCOUNT_SNAPSHOT_NOT_AVAILABLE_AT_RISK_TIME",)
        elif age > configuration.maximum_account_snapshot_age_seconds:
            state = RiskDecisionState.DATA_INSUFFICIENT
            constraints = ()
            reasons = ("ACCOUNT_SNAPSHOT_STALE",)
        elif portfolio.account_snapshot.completeness is not AccountPortfolioCompleteness.COMPLETE_ACCOUNT:
            state = RiskDecisionState.DATA_INSUFFICIENT
            constraints = ()
            reasons = ("ACCOUNT_PORTFOLIO_INCOMPLETE",)
        elif portfolio.account_snapshot.reconciliation_state is not AccountReconciliationState.RECONCILED:
            state = RiskDecisionState.DATA_INSUFFICIENT
            constraints = ()
            reasons = ("ACCOUNT_RECONCILIATION_REQUIRED",)
        else:
            constraints = _complete_account_constraints(portfolio)
            failed = tuple(item for item in constraints if not item.passed)
            state = RiskDecisionState.APPROVED if not failed else RiskDecisionState.REJECTED
            reasons = (
                ("ALL_COMPLETE_ACCOUNT_HARD_RISK_CONSTRAINTS_PASSED",)
                if not failed
                else tuple(sorted({item.reason_code for item in failed}))
            )
        semantic = {
            "schema_version": COMPLETE_ACCOUNT_RISK_DECISION_SCHEMA,
            "portfolio_decision_id": str(portfolio.decision_id),
            "portfolio_decision_version": portfolio.version,
            "post_trade_snapshot_id": str(portfolio.post_trade.snapshot_id),
            "post_trade_content_hash": portfolio.post_trade.content_hash,
            "configuration_id": str(configuration.configuration_id),
            "configuration_hash": configuration.configuration_hash,
            "mode": portfolio.mode.value,
            "state": state.value,
            "constraints": [item.to_canonical_dict() for item in constraints],
            "version": 0,
            "actor": actor,
            "reason": reason,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "reason_codes": list(reasons),
        }
        return CompleteAccountRiskDecision(
            schema_version=COMPLETE_ACCOUNT_RISK_DECISION_SCHEMA,
            risk_decision_id=_risk_decision_id(semantic),
            portfolio_decision_id=portfolio.decision_id,
            portfolio_decision_version=portfolio.version,
            post_trade_snapshot_id=portfolio.post_trade.snapshot_id,
            post_trade_content_hash=portfolio.post_trade.content_hash,
            configuration_id=configuration.configuration_id,
            configuration_hash=configuration.configuration_hash,
            mode=portfolio.mode,
            state=state,
            constraints=constraints,
            version=0,
            actor=actor,
            reason=reason,
            started_at=started_at,
            completed_at=completed_at,
            reason_codes=reasons,
        )


def _apply_deltas(
    account: AuthoritativeAccountPortfolioSnapshot,
    deltas: tuple[ProposedTradeDelta, ...],
    *,
    configuration: CompleteAccountRiskConfiguration,
    as_of: datetime,
) -> PostTradePortfolioSnapshot:
    positions = {
        item.symbol: PostTradePosition(
            symbol=item.symbol,
            theme_id=item.theme_id,
            total_quantity=item.total_quantity,
            available_quantity=item.available_quantity,
            market_price=item.market_price,
            loss_per_share=item.loss_per_share,
        )
        for item in account.all_positions
    }
    for delta in deltas:
        existing = positions.get(delta.symbol)
        observed_current = existing.total_quantity if existing else 0
        observed_available = existing.available_quantity if existing else 0
        if (
            observed_current != delta.current_quantity
            or observed_available != delta.current_available_quantity
        ):
            raise ValueError("trade delta current Position differs from account authority")
        if delta.target_quantity == 0:
            positions.pop(delta.symbol, None)
            continue
        available_after = (
            observed_available
            if delta.trade_quantity > 0
            else min(observed_available + delta.trade_quantity, delta.target_quantity)
        )
        positions[delta.symbol] = PostTradePosition(
            symbol=delta.symbol,
            theme_id=delta.theme_id,
            total_quantity=delta.target_quantity,
            available_quantity=max(0, available_after),
            market_price=delta.reference_price,
            loss_per_share=delta.loss_per_share,
        )
    ordered = tuple(sorted(positions.values(), key=lambda item: item.symbol))
    cash = account.available_cash - sum(item.trade_value for item in deltas)
    semantic = {
        "schema_version": POST_TRADE_PORTFOLIO_SCHEMA,
        "account_snapshot_id": str(account.snapshot_id),
        "account_snapshot_hash": account.content_hash,
        "account_id": account.account_id,
        "as_of": as_of.isoformat(),
        "available_cash": cash,
        "positions": [item.to_canonical_dict() for item in ordered],
        "proposed_deltas": [item.to_canonical_dict() for item in deltas],
        "configuration_id": str(configuration.configuration_id),
        "configuration_hash": configuration.configuration_hash,
    }
    digest = canonical_hash(semantic)
    return PostTradePortfolioSnapshot(
        schema_version=POST_TRADE_PORTFOLIO_SCHEMA,
        snapshot_id=ArtifactId(
            f"post-trade-portfolio-{digest.split(':', 1)[1][:24]}"
        ),
        account_snapshot_id=account.snapshot_id,
        account_snapshot_hash=account.content_hash,
        account_id=account.account_id,
        as_of=as_of,
        available_cash=cash,
        positions=ordered,
        proposed_deltas=deltas,
        configuration_id=configuration.configuration_id,
        configuration_hash=configuration.configuration_hash,
        content_hash=digest,
    )


def _complete_account_constraints(
    portfolio: CompleteAccountPortfolioDecision,
) -> tuple[PortfolioConstraint, ...]:
    budget = portfolio.configuration.risk_budget
    nav = portfolio.account_snapshot.net_asset_value
    positions = portfolio.post_trade.positions
    deltas = portfolio.post_trade.proposed_deltas
    constraints: list[PortfolioConstraint] = []
    gross = sum(item.market_value for item in positions) / nav
    constraints.append(
        _constraint(
            PortfolioConstraintType.MAXIMUM_GROSS_EXPOSURE,
            gross,
            budget.maximum_gross_exposure,
            "MAXIMUM_GROSS_EXPOSURE_EXCEEDED",
            tuple(item.symbol for item in positions),
        )
    )
    symbol_exposure = max(
        (item.market_value / nav for item in positions), default=0.0
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.SINGLE_SYMBOL_LIMIT,
            symbol_exposure,
            budget.single_symbol_limit,
            "SINGLE_SYMBOL_LIMIT_EXCEEDED",
            tuple(
                item.symbol
                for item in positions
                if item.market_value / nav > budget.single_symbol_limit
            ),
        )
    )
    theme_values: dict[str, float] = {}
    for item in positions:
        theme_values[item.theme_id] = (
            theme_values.get(item.theme_id, 0.0) + item.market_value
        )
    theme_exposure = max(
        (value / nav for value in theme_values.values()), default=0.0
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.THEME_LIMIT,
            theme_exposure,
            budget.theme_limit,
            "THEME_LIMIT_EXCEEDED",
            tuple(
                item.symbol
                for item in positions
                if theme_values[item.theme_id] / nav > budget.theme_limit
            ),
        )
    )
    liquidity = max(
        (
            abs(item.trade_value) / item.average_daily_trade_value
            for item in deltas
        ),
        default=0.0,
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.LIQUIDITY_LIMIT,
            liquidity,
            budget.liquidity_max_participation,
            "LIQUIDITY_LIMIT_EXCEEDED",
            tuple(
                item.symbol
                for item in deltas
                if abs(item.trade_value) / item.average_daily_trade_value
                > budget.liquidity_max_participation
            ),
        )
    )
    reserve = nav * budget.minimum_cash_reserve
    cash_shortfall = max(0.0, reserve - portfolio.post_trade.available_cash)
    constraints.append(
        _constraint(
            PortfolioConstraintType.AVAILABLE_CASH,
            cash_shortfall,
            0.0,
            "AVAILABLE_CASH_INSUFFICIENT",
            tuple(item.symbol for item in deltas if item.trade_quantity > 0),
        )
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.CURRENT_POSITION,
            0.0,
            0.0,
            "LONG_ONLY_POSITION_CONSTRAINT_FAILED",
            (),
        )
    )
    unavailable_sell = max(
        (
            float(
                max(
                    0,
                    -item.trade_quantity - item.current_available_quantity,
                )
            )
            for item in deltas
        ),
        default=0.0,
    )
    constraints.append(
        _constraint(
            PortfolioConstraintType.T_PLUS_ONE,
            unavailable_sell,
            0.0 if budget.t_plus_one_enforced else unavailable_sell,
            "T_PLUS_ONE_AVAILABLE_QUANTITY_EXCEEDED",
            tuple(
                item.symbol
                for item in deltas
                if -item.trade_quantity > item.current_available_quantity
            ),
        )
    )
    maximum_loss = sum(item.maximum_loss for item in positions) / nav
    constraints.append(
        _constraint(
            PortfolioConstraintType.MAXIMUM_LOSS_BUDGET,
            maximum_loss,
            budget.maximum_loss_budget,
            "MAXIMUM_LOSS_BUDGET_EXCEEDED",
            tuple(item.symbol for item in positions),
        )
    )
    return tuple(constraints)


def _constraint(
    kind: PortfolioConstraintType,
    observed: float,
    limit: float,
    failed_reason: str,
    symbols: tuple[str, ...],
) -> PortfolioConstraint:
    passed = observed <= limit
    return PortfolioConstraint(
        constraint_type=kind,
        passed=passed,
        observed_value=observed,
        limit_value=limit,
        reason_code="CONSTRAINT_PASSED" if passed else failed_reason,
        symbols=tuple(sorted(set(symbols))),
    )


def _constraint_from_dict(payload: Mapping[str, Any]) -> PortfolioConstraint:
    _fields(
        payload,
        {
            "constraint_type",
            "passed",
            "observed_value",
            "limit_value",
            "reason_code",
            "symbols",
        },
        "PortfolioConstraint",
    )
    passed = payload["passed"]
    if not isinstance(passed, bool):
        raise ValueError("PortfolioConstraint passed must be boolean")
    return PortfolioConstraint(
        constraint_type=PortfolioConstraintType(str(payload["constraint_type"])),
        passed=passed,
        observed_value=float(payload["observed_value"]),
        limit_value=float(payload["limit_value"]),
        reason_code=str(payload["reason_code"]),
        symbols=tuple(str(item) for item in _array(payload["symbols"])),
    )


def _portfolio_decision_id(payload: Mapping[str, Any]) -> PortfolioDecisionId:
    digest = canonical_hash(dict(payload)).split(":", 1)[1]
    return PortfolioDecisionId(f"complete-account-portfolio-{digest[:24]}")


def _risk_decision_id(payload: Mapping[str, Any]) -> RiskDecisionId:
    digest = canonical_hash(dict(payload)).split(":", 1)[1]
    return RiskDecisionId(f"complete-account-risk-{digest[:24]}")


def _text(label: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _positive(label: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be positive and finite")


def _aware(label: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _fields(
    payload: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("complete-account value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("complete-account value must be an array")
    return value
