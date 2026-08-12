"""A-share Portfolio Shadow ledger isolated from real execution authorities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data import PriceLimitState, TradingStatus


class ShadowParameterProvenance(str, Enum):
    OBSERVED_FACT = "OBSERVED_FACT"
    ENGINEERING_ASSUMPTION = "ENGINEERING_ASSUMPTION"
    CALIBRATED_PARAMETER = "CALIBRATED_PARAMETER"
    OPERATOR_INPUT = "OPERATOR_INPUT"


class PortfolioWeightingMethod(str, Enum):
    EQUAL_WEIGHT = "EQUAL_WEIGHT"
    SCORE_WEIGHT = "SCORE_WEIGHT"
    RISK_WEIGHT = "RISK_WEIGHT"


class ShadowPortfolioTradeSession(str, Enum):
    OPEN_CALL_AUCTION = "OPEN_CALL_AUCTION"
    CONTINUOUS_AM = "CONTINUOUS_AM"
    CONTINUOUS_PM = "CONTINUOUS_PM"
    CLOSE_CALL_AUCTION = "CLOSE_CALL_AUCTION"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class ShadowTradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ShadowPortfolioFillStatus(str, Enum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    UNFILLED = "UNFILLED"


_REQUIRED_PARAMETERS = frozenset(
    {
        "commission_bps",
        "slippage_bps",
        "impact_bps",
        "exit_cost_bps",
        "max_participation_rate",
    }
)


@dataclass(frozen=True, slots=True)
class ShadowPortfolioParameter:
    name: str
    value: Decimal
    provenance: ShadowParameterProvenance

    def __post_init__(self) -> None:
        require_text("Shadow Portfolio parameter name", self.name)
        if not self.value.is_finite() or self.value < 0:
            raise ValueError("Shadow Portfolio parameter must be non-negative")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "value": str(self.value),
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True, slots=True)
class ShadowPortfolioPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    top_k: int
    weighting_method: PortfolioWeightingMethod
    lot_size: int
    t_plus_one: bool
    parameters: tuple[ShadowPortfolioParameter, ...]
    allowed_trade_sessions: tuple[ShadowPortfolioTradeSession, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "shadow-portfolio-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        if self.top_k not in {1, 3, 5}:
            raise ValueError("Shadow Portfolio top_k must be one of 1, 3, or 5")
        if self.lot_size != 100:
            raise ValueError("A-share Shadow Portfolio lot size must be 100")
        if not self.t_plus_one:
            raise ValueError("A-share Shadow Portfolio must enforce T+1")
        if {item.name for item in self.parameters} != _REQUIRED_PARAMETERS:
            raise ValueError("Shadow Portfolio requires exact cost/capacity parameter set")
        if self.parameters != tuple(sorted(self.parameters, key=lambda item: item.name)):
            raise ValueError("Shadow Portfolio parameters must be sorted")
        participation = self.parameter("max_participation_rate")
        if not Decimal("0") < participation <= Decimal("1"):
            raise ValueError("Shadow Portfolio participation rate must be within (0, 1]")
        if self.allowed_trade_sessions != (
            ShadowPortfolioTradeSession.CONTINUOUS_AM,
            ShadowPortfolioTradeSession.CONTINUOUS_PM,
        ):
            raise ValueError("Shadow Portfolio currently permits continuous auction only")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Shadow Portfolio Policy hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        top_k: int,
        weighting_method: PortfolioWeightingMethod,
        lot_size: int,
        t_plus_one: bool,
        parameters: Mapping[
            str, tuple[Decimal, ShadowParameterProvenance]
        ],
        created_at: datetime,
    ) -> ShadowPortfolioPolicy:
        if set(parameters) != _REQUIRED_PARAMETERS:
            raise ValueError("Shadow Portfolio requires exact cost/capacity parameter set")
        ordered = tuple(
            ShadowPortfolioParameter(name, value, provenance)
            for name, (value, provenance) in sorted(parameters.items())
        )
        limitations = tuple(
            sorted(
                {
                    *ENGINEERING_LIMITATIONS,
                    "A_SHARE_T_PLUS_ONE",
                    "NO_BROKER",
                    "NO_ORDER_AUTHORITY",
                    "NOT_REAL_FILL",
                    "NOT_REAL_POSITION",
                    *(
                        ("ENGINEERING_ASSUMPTION",)
                        if any(
                            item.provenance
                            is ShadowParameterProvenance.ENGINEERING_ASSUMPTION
                            for item in ordered
                        )
                        else ()
                    ),
                }
            )
        )
        allowed = (
            ShadowPortfolioTradeSession.CONTINUOUS_AM,
            ShadowPortfolioTradeSession.CONTINUOUS_PM,
        )
        values = {
            "schema_version": "shadow-portfolio-policy/v1",
            "policy_version": policy_version,
            "top_k": top_k,
            "weighting_method": weighting_method.value,
            "lot_size": lot_size,
            "t_plus_one": t_plus_one,
            "parameters": [item.to_canonical_dict() for item in ordered],
            "allowed_trade_sessions": [item.value for item in allowed],
            "created_at": timestamp(created_at),
            "limitations": list(limitations),
        }
        policy_id, digest = content_identity("shadow-portfolio-policy", values)
        return cls(
            policy_id,
            digest,
            policy_version,
            top_k,
            weighting_method,
            lot_size,
            t_plus_one,
            ordered,
            allowed,
            created_at,
            limitations,
        )

    def parameter(self, name: str) -> Decimal:
        return next(item.value for item in self.parameters if item.name == name)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "top_k": self.top_k,
            "weighting_method": self.weighting_method.value,
            "lot_size": self.lot_size,
            "t_plus_one": self.t_plus_one,
            "parameters": [item.to_canonical_dict() for item in self.parameters],
            "allowed_trade_sessions": [
                item.value for item in self.allowed_trade_sessions
            ],
            "created_at": timestamp(self.created_at),
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ShadowPortfolioPolicy:
        parameters = tuple(
            ShadowPortfolioParameter(
                name=str(_mapping(item)["name"]),
                value=Decimal(str(_mapping(item)["value"])),
                provenance=ShadowParameterProvenance(
                    str(_mapping(item)["provenance"])
                ),
            )
            for item in _sequence(value["parameters"])
        )
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            top_k=int(value["top_k"]),
            weighting_method=PortfolioWeightingMethod(
                str(value["weighting_method"])
            ),
            lot_size=int(value["lot_size"]),
            t_plus_one=_required_boolean(value["t_plus_one"]),
            parameters=parameters,
            allowed_trade_sessions=tuple(
                ShadowPortfolioTradeSession(str(item))
                for item in _sequence(value["allowed_trade_sessions"])
            ),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ShadowPortfolio:
    portfolio_id: ArtifactId
    portfolio_hash: str
    policy_reference: ValidationArtifactReference
    research_reference: ValidationArtifactReference
    candidate_reference: ValidationArtifactReference
    initial_cash: Decimal
    created_at: datetime
    limitations: tuple[str, ...]
    strategy_reference: ValidationArtifactReference | None = None
    schema_version: str = "shadow-portfolio/v1"

    def __post_init__(self) -> None:
        require_sha256("portfolio_hash", self.portfolio_hash)
        if self.initial_cash <= 0:
            raise ValueError("Shadow Portfolio initial cash must be positive")
        if self.schema_version not in {
            "shadow-portfolio/v1",
            "shadow-portfolio/v2",
        }:
            raise ValueError("Shadow Portfolio schema version is unsupported")
        if (self.schema_version == "shadow-portfolio/v2") != (
            self.strategy_reference is not None
        ):
            raise ValueError("Shadow Portfolio v2 requires exact Strategy lineage")
        if canonical_hash(self.identity_payload()) != self.portfolio_hash:
            raise ValueError("Shadow Portfolio hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "policy_reference": self.policy_reference.to_canonical_dict(),
            "research_reference": self.research_reference.to_canonical_dict(),
            "candidate_reference": self.candidate_reference.to_canonical_dict(),
            "initial_cash": str(self.initial_cash),
            "created_at": timestamp(self.created_at),
            "limitations": list(self.limitations),
        }
        if self.schema_version == "shadow-portfolio/v2":
            assert self.strategy_reference is not None
            payload["strategy_reference"] = (
                self.strategy_reference.to_canonical_dict()
            )
        return payload

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": str(self.portfolio_id),
            "portfolio_hash": self.portfolio_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ShadowPortfolio:
        return cls(
            portfolio_id=ArtifactId(str(value["portfolio_id"])),
            portfolio_hash=str(value["portfolio_hash"]),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["policy_reference"])
            ),
            research_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["research_reference"])
            ),
            candidate_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["candidate_reference"])
            ),
            initial_cash=Decimal(str(value["initial_cash"])),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            strategy_reference=(
                None
                if value.get("strategy_reference") is None
                else ValidationArtifactReference.from_canonical_dict(
                    _mapping(value["strategy_reference"])
                )
            ),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ShadowPortfolioMarketObservation:
    symbol: str
    score: Decimal | None
    risk_weight: Decimal | None
    risk_weight_provenance: ShadowParameterProvenance | None
    reference_price: Decimal | None
    mark_price: Decimal | None
    average_daily_amount: Decimal | None
    trading_status: TradingStatus
    price_limit_state: PriceLimitState
    trade_session: ShadowPortfolioTradeSession
    value_provenance: tuple[tuple[str, ShadowParameterProvenance], ...]
    observed_at: datetime
    source_references: tuple[ValidationArtifactReference, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("Shadow Portfolio symbol", self.symbol)
        for value in (
            self.reference_price,
            self.mark_price,
            self.average_daily_amount,
        ):
            if value is not None and value <= 0:
                raise ValueError("Shadow Portfolio market values must be positive")
        if self.risk_weight is not None and self.risk_weight <= 0:
            raise ValueError("Shadow Portfolio risk weight must be positive")
        if (self.risk_weight is None) != (self.risk_weight_provenance is None):
            raise ValueError("Shadow Portfolio risk weight requires explicit provenance")
        _validate_market_value_provenance(
            self.value_provenance,
            reference_price=self.reference_price,
            mark_price=self.mark_price,
            average_daily_amount=self.average_daily_amount,
        )
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Shadow Portfolio observation must be timezone-aware")
        if self.source_references != tuple(
            sorted(
                set(self.source_references),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ):
            raise ValueError("Shadow Portfolio observation lineage must be sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Shadow Portfolio observation reasons must be sorted")

    def to_init_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "risk_weight": self.risk_weight,
            "risk_weight_provenance": self.risk_weight_provenance,
            "reference_price": self.reference_price,
            "mark_price": self.mark_price,
            "average_daily_amount": self.average_daily_amount,
            "trading_status": self.trading_status,
            "price_limit_state": self.price_limit_state,
            "trade_session": self.trade_session,
            "value_provenance": self.value_provenance,
            "observed_at": self.observed_at,
            "source_references": self.source_references,
            "reason_codes": self.reason_codes,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.to_init_dict(),
            "score": _decimal(self.score),
            "risk_weight": _decimal(self.risk_weight),
            "risk_weight_provenance": (
                None
                if self.risk_weight_provenance is None
                else self.risk_weight_provenance.value
            ),
            "reference_price": _decimal(self.reference_price),
            "mark_price": _decimal(self.mark_price),
            "average_daily_amount": _decimal(self.average_daily_amount),
            "trading_status": self.trading_status.value,
            "price_limit_state": self.price_limit_state.value,
            "trade_session": self.trade_session.value,
            "value_provenance": {
                name: provenance.value
                for name, provenance in self.value_provenance
            },
            "observed_at": timestamp(self.observed_at),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "reason_codes": list(self.reason_codes),
        }


def _validate_market_value_provenance(
    value_provenance: tuple[tuple[str, ShadowParameterProvenance], ...],
    *,
    reference_price: Decimal | None,
    mark_price: Decimal | None,
    average_daily_amount: Decimal | None,
) -> None:
    if value_provenance != tuple(sorted(value_provenance)) or len(
        {name for name, _ in value_provenance}
    ) != len(value_provenance):
        raise ValueError("Shadow Portfolio value provenance must be unique and sorted")
    required = {"trading_status", "price_limit_state", "trade_session"}
    for name, value in (
        ("reference_price", reference_price),
        ("mark_price", mark_price),
        ("average_daily_amount", average_daily_amount),
    ):
        if value is not None:
            required.add(name)
    supplied = {name for name, _ in value_provenance}
    if supplied != required:
        raise ValueError(
            "Shadow Portfolio value provenance must exactly cover result inputs"
        )


@dataclass(frozen=True, slots=True)
class ShadowPortfolioOrderIntent:
    intent_id: ArtifactId
    symbol: str
    side: ShadowTradeSide
    requested_quantity: Decimal
    reference_price: Decimal | None
    reason_codes: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "intent_id": str(self.intent_id),
            "symbol": self.symbol,
            "side": self.side.value,
            "requested_quantity": str(self.requested_quantity),
            "reference_price": _decimal(self.reference_price),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class ShadowPortfolioFill:
    fill_id: ArtifactId
    intent_id: ArtifactId
    symbol: str
    side: ShadowTradeSide
    status: ShadowPortfolioFillStatus
    filled_quantity: Decimal
    fill_price: Decimal | None
    notional: Decimal
    total_cost: Decimal
    parameter_provenance: tuple[tuple[str, ShadowParameterProvenance], ...]
    limitations: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "fill_id": str(self.fill_id),
            "intent_id": str(self.intent_id),
            "symbol": self.symbol,
            "side": self.side.value,
            "status": self.status.value,
            "filled_quantity": str(self.filled_quantity),
            "fill_price": _decimal(self.fill_price),
            "notional": str(self.notional),
            "total_cost": str(self.total_cost),
            "parameter_provenance": [
                [name, provenance.value]
                for name, provenance in self.parameter_provenance
            ],
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class ShadowPortfolioPosition:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    opened_on: date
    mark_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": str(self.quantity),
            "average_cost": str(self.average_cost),
            "opened_on": self.opened_on.isoformat(),
            "mark_price": str(self.mark_price),
            "market_value": str(self.market_value),
            "unrealized_pnl": str(self.unrealized_pnl),
        }


@dataclass(frozen=True, slots=True)
class ShadowPortfolioAttribution:
    symbol: str
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    cost: Decimal

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "market_value": str(self.market_value),
            "unrealized_pnl": str(self.unrealized_pnl),
            "realized_pnl": str(self.realized_pnl),
            "cost": str(self.cost),
        }


@dataclass(frozen=True, slots=True)
class ShadowPortfolioDayState:
    state_id: ArtifactId
    state_hash: str
    portfolio_reference: ValidationArtifactReference
    policy_reference: ValidationArtifactReference
    previous_state_reference: ValidationArtifactReference | None
    sequence: int
    trading_date: date
    cash: Decimal
    positions: tuple[ShadowPortfolioPosition, ...]
    order_intents: tuple[ShadowPortfolioOrderIntent, ...]
    fills: tuple[ShadowPortfolioFill, ...]
    nav: Decimal
    peak_nav: Decimal
    gross_exposure: Decimal
    turnover: Decimal
    drawdown: Decimal
    total_cost: Decimal
    attribution: tuple[ShadowPortfolioAttribution, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    recorded_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "shadow-portfolio-day-state/v1"

    def __post_init__(self) -> None:
        require_sha256("state_hash", self.state_hash)
        if self.sequence <= 0 or self.cash < 0 or self.nav < 0:
            raise ValueError("Shadow Portfolio state sequence/cash/NAV is invalid")
        if any(item.quantity % Decimal("100") != 0 for item in self.positions):
            raise ValueError("Shadow Portfolio Positions must use 100-share lots")
        if canonical_hash(self.identity_payload()) != self.state_hash:
            raise ValueError("Shadow Portfolio state hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "portfolio_reference": self.portfolio_reference.to_canonical_dict(),
            "policy_reference": self.policy_reference.to_canonical_dict(),
            "previous_state_reference": (
                None
                if self.previous_state_reference is None
                else self.previous_state_reference.to_canonical_dict()
            ),
            "sequence": self.sequence,
            "trading_date": self.trading_date.isoformat(),
            "cash": str(self.cash),
            "positions": [item.to_canonical_dict() for item in self.positions],
            "order_intents": [item.to_canonical_dict() for item in self.order_intents],
            "fills": [item.to_canonical_dict() for item in self.fills],
            "nav": str(self.nav),
            "peak_nav": str(self.peak_nav),
            "gross_exposure": str(self.gross_exposure),
            "turnover": str(self.turnover),
            "drawdown": str(self.drawdown),
            "total_cost": str(self.total_cost),
            "attribution": [item.to_canonical_dict() for item in self.attribution],
            "source_references": [item.to_canonical_dict() for item in self.source_references],
            "recorded_at": timestamp(self.recorded_at),
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "state_id": str(self.state_id),
            "state_hash": self.state_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ShadowPortfolioDayState:
        previous_value = value["previous_state_reference"]
        return cls(
            state_id=ArtifactId(str(value["state_id"])),
            state_hash=str(value["state_hash"]),
            portfolio_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["portfolio_reference"])
            ),
            policy_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["policy_reference"])
            ),
            previous_state_reference=(
                None
                if previous_value is None
                else ValidationArtifactReference.from_canonical_dict(
                    _mapping(previous_value)
                )
            ),
            sequence=int(value["sequence"]),
            trading_date=date.fromisoformat(str(value["trading_date"])),
            cash=Decimal(str(value["cash"])),
            positions=tuple(
                _position_from_dict(_mapping(item))
                for item in _sequence(value["positions"])
            ),
            order_intents=tuple(
                _intent_from_dict(_mapping(item))
                for item in _sequence(value["order_intents"])
            ),
            fills=tuple(
                _fill_from_dict(_mapping(item))
                for item in _sequence(value["fills"])
            ),
            nav=Decimal(str(value["nav"])),
            peak_nav=Decimal(str(value["peak_nav"])),
            gross_exposure=Decimal(str(value["gross_exposure"])),
            turnover=Decimal(str(value["turnover"])),
            drawdown=Decimal(str(value["drawdown"])),
            total_cost=Decimal(str(value["total_cost"])),
            attribution=tuple(
                _attribution_from_dict(_mapping(item))
                for item in _sequence(value["attribution"])
            ),
            source_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["source_references"])
            ),
            recorded_at=datetime.fromisoformat(str(value["recorded_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )


def build_shadow_portfolio(
    *,
    policy: ShadowPortfolioPolicy,
    research_reference: ValidationArtifactReference,
    candidate_reference: ValidationArtifactReference,
    strategy_reference: ValidationArtifactReference | None = None,
    initial_cash: Decimal,
    created_at: datetime,
) -> ShadowPortfolio:
    policy_reference = ValidationArtifactReference(
        "SHADOW_PORTFOLIO_POLICY", policy.policy_id, policy.policy_hash
    )
    limitations = tuple(
        sorted(
            {
                *policy.limitations,
                "STRATEGY_SHADOW_PROVEN_FALSE",
                "PORTFOLIO_SHADOW_ONLY",
            }
        )
    )
    schema_version = (
        "shadow-portfolio/v1"
        if strategy_reference is None
        else "shadow-portfolio/v2"
    )
    values = {
        "schema_version": schema_version,
        "policy_reference": policy_reference.to_canonical_dict(),
        "research_reference": research_reference.to_canonical_dict(),
        "candidate_reference": candidate_reference.to_canonical_dict(),
        "initial_cash": str(initial_cash),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
    if strategy_reference is not None:
        values["strategy_reference"] = strategy_reference.to_canonical_dict()
    portfolio_id, digest = content_identity("shadow-portfolio", values)
    return ShadowPortfolio(
        portfolio_id,
        digest,
        policy_reference,
        research_reference,
        candidate_reference,
        initial_cash,
        created_at,
        limitations,
        strategy_reference,
        schema_version,
    )


def run_shadow_portfolio_day(
    *,
    portfolio: ShadowPortfolio,
    policy: ShadowPortfolioPolicy,
    trading_date: date,
    observations: tuple[ShadowPortfolioMarketObservation, ...],
    previous: ShadowPortfolioDayState | None,
    recorded_at: datetime,
) -> ShadowPortfolioDayState:
    if (
        portfolio.policy_reference.artifact_id != policy.policy_id
        or portfolio.policy_reference.content_hash != policy.policy_hash
    ):
        raise ValueError("Shadow Portfolio Policy identity mismatch")
    if not observations or tuple(item.symbol for item in observations) != tuple(
        sorted({item.symbol for item in observations})
    ):
        raise ValueError("Shadow Portfolio observations must be non-empty, unique, and sorted")
    if previous is not None:
        if previous.portfolio_reference.artifact_id != portfolio.portfolio_id:
            raise ValueError("previous Portfolio Shadow state belongs to another Portfolio")
        if trading_date <= previous.trading_date:
            raise ValueError("Portfolio Shadow trading dates must increase")
    observation_by_symbol = {item.symbol: item for item in observations}
    ranked = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.score is None,
                -(item.score or Decimal("0")),
                item.symbol,
            ),
        )
    )
    selected = tuple(item for item in ranked if item.score is not None)[: policy.top_k]
    weights = _weights(selected, policy.weighting_method)
    cash = portfolio.initial_cash if previous is None else previous.cash
    positions = {
        item.symbol: item for item in (() if previous is None else previous.positions)
    }
    intents: list[ShadowPortfolioOrderIntent] = []
    fills: list[ShadowPortfolioFill] = []
    realized: dict[str, Decimal] = {}
    costs: dict[str, Decimal] = {}
    traded_notional = Decimal("0")
    selected_symbols = {item.symbol for item in selected}

    for symbol, position in tuple(sorted(positions.items())):
        if symbol in selected_symbols:
            continue
        observation = observation_by_symbol.get(symbol)
        reasons = _sell_rejections(
            observation=observation,
            position=position,
            trading_date=trading_date,
            policy=policy,
        )
        sell_capacity = (
            Decimal("0")
            if observation is None
            or observation.average_daily_amount is None
            or observation.reference_price is None
            else _lot_floor(
                observation.average_daily_amount
                * policy.parameter("max_participation_rate")
                / observation.reference_price,
                policy.lot_size,
            )
        )
        if sell_capacity == 0:
            reasons = tuple(sorted({*reasons, "ZERO_EXECUTABLE_LOT"}))
        intent = _intent(
            portfolio.portfolio_id,
            trading_date,
            symbol,
            ShadowTradeSide.SELL,
            position.quantity,
            None if observation is None else observation.reference_price,
            reasons,
        )
        intents.append(intent)
        fill = _fill(
            intent=intent,
            observation=observation,
            policy=policy,
            maximum_quantity=sell_capacity,
        )
        fills.append(fill)
        costs[symbol] = costs.get(symbol, Decimal("0")) + fill.total_cost
        if fill.status is not ShadowPortfolioFillStatus.UNFILLED:
            assert fill.fill_price is not None
            proceeds = fill.notional - _explicit_cash_cost(
                fill.notional, policy, selling=True
            )
            cash += proceeds
            explicit_exit_cost = _explicit_cash_cost(
                fill.notional,
                policy,
                selling=True,
            )
            realized[symbol] = (
                (fill.fill_price - position.average_cost) * fill.filled_quantity
                - explicit_exit_cost
            )
            traded_notional += fill.notional
            remaining_quantity = position.quantity - fill.filled_quantity
            if remaining_quantity == 0:
                del positions[symbol]
            else:
                assert observation is not None
                mark = observation.mark_price or fill.fill_price
                positions[symbol] = ShadowPortfolioPosition(
                    symbol,
                    remaining_quantity,
                    position.average_cost,
                    position.opened_on,
                    mark,
                    mark * remaining_quantity,
                    (mark - position.average_cost) * remaining_quantity,
                )

    pretrade_market_value = Decimal("0")
    for item in positions.values():
        position_observation = observation_by_symbol.get(item.symbol)
        mark = (
            position_observation.mark_price
            if position_observation is not None
            and position_observation.mark_price is not None
            else item.mark_price
        )
        pretrade_market_value += item.quantity * mark
    pretrade_nav = cash + pretrade_market_value
    for observation in selected:
        if observation.symbol in positions:
            continue
        target_value = pretrade_nav * weights[observation.symbol]
        reference_price = observation.reference_price
        intended_quantity = (
            Decimal("0")
            if reference_price is None
            else _lot_floor(target_value / reference_price, policy.lot_size)
        )
        reasons = _buy_rejections(observation=observation, policy=policy)
        capacity_quantity = (
            Decimal("0")
            if observation.average_daily_amount is None
            or reference_price is None
            else _lot_floor(
                observation.average_daily_amount
                * policy.parameter("max_participation_rate")
                / reference_price,
                policy.lot_size,
            )
        )
        affordable_quantity = (
            Decimal("0")
            if reference_price is None
            else _lot_floor(
                cash
                / (
                    reference_price
                    * (
                        Decimal("1")
                        + (
                            policy.parameter("slippage_bps")
                            + policy.parameter("impact_bps")
                            + policy.parameter("commission_bps")
                        )
                        / Decimal("10000")
                    )
                ),
                policy.lot_size,
            )
        )
        executable_quantity = min(
            intended_quantity, capacity_quantity, affordable_quantity
        )
        if intended_quantity > 0 and capacity_quantity == 0:
            reasons = tuple(sorted({*reasons, "CAPACITY_ZERO"}))
        if executable_quantity == 0:
            reasons = tuple(sorted({*reasons, "ZERO_EXECUTABLE_LOT"}))
        intent = _intent(
            portfolio.portfolio_id,
            trading_date,
            observation.symbol,
            ShadowTradeSide.BUY,
            intended_quantity,
            reference_price,
            reasons,
        )
        intents.append(intent)
        fill = _fill(
            intent=intent,
            observation=observation,
            policy=policy,
            maximum_quantity=executable_quantity,
        )
        fills.append(fill)
        costs[observation.symbol] = costs.get(
            observation.symbol, Decimal("0")
        ) + fill.total_cost
        if fill.status is not ShadowPortfolioFillStatus.UNFILLED:
            assert fill.fill_price is not None
            cash_cost = _explicit_cash_cost(fill.notional, policy, selling=False)
            cash -= fill.notional + cash_cost
            if cash < 0:
                raise ValueError("Shadow Portfolio fill exceeded available Cash")
            mark = observation.mark_price or fill.fill_price
            average_cost = (
                fill.notional + cash_cost
            ) / fill.filled_quantity
            positions[observation.symbol] = ShadowPortfolioPosition(
                observation.symbol,
                fill.filled_quantity,
                average_cost,
                trading_date,
                mark,
                mark * fill.filled_quantity,
                (mark - average_cost) * fill.filled_quantity,
            )
            traded_notional += fill.notional

    marked: list[ShadowPortfolioPosition] = []
    for symbol, position in sorted(positions.items()):
        observation = observation_by_symbol.get(symbol)
        mark = (
            observation.mark_price
            if observation is not None and observation.mark_price is not None
            else position.mark_price
        )
        marked.append(
            ShadowPortfolioPosition(
                symbol,
                position.quantity,
                position.average_cost,
                position.opened_on,
                mark,
                mark * position.quantity,
                (mark - position.average_cost) * position.quantity,
            )
        )
    nav = cash + sum((item.market_value for item in marked), Decimal("0"))
    peak_nav = max(nav, portfolio.initial_cash if previous is None else previous.peak_nav)
    exposure = (
        Decimal("0")
        if nav == 0
        else sum((item.market_value for item in marked), Decimal("0")) / nav
    )
    turnover = Decimal("0") if pretrade_nav == 0 else traded_notional / pretrade_nav
    total_cost = sum((item.total_cost for item in fills), Decimal("0"))
    attribution = tuple(
        ShadowPortfolioAttribution(
            symbol,
            next(
                (item.market_value for item in marked if item.symbol == symbol),
                Decimal("0"),
            ),
            next(
                (item.unrealized_pnl for item in marked if item.symbol == symbol),
                Decimal("0"),
            ),
            realized.get(symbol, Decimal("0")),
            costs.get(symbol, Decimal("0")),
        )
        for symbol in sorted(set(costs) | set(realized) | {item.symbol for item in marked})
    )
    portfolio_reference = ValidationArtifactReference(
        "SHADOW_PORTFOLIO", portfolio.portfolio_id, portfolio.portfolio_hash
    )
    previous_reference = (
        None
        if previous is None
        else ValidationArtifactReference(
            "SHADOW_PORTFOLIO_DAY_STATE", previous.state_id, previous.state_hash
        )
    )
    sequence = 1 if previous is None else previous.sequence + 1
    source_references = tuple(
        sorted(
            {
                portfolio.research_reference,
                portfolio.candidate_reference,
                *(reference for item in observations for reference in item.source_references),
            },
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )
    limitations = tuple(
        sorted(
            {
                *portfolio.limitations,
                "SHADOW_ORDER_INTENT_NOT_ORDER",
                "NOT_REAL_FILL",
                "NOT_REAL_POSITION",
                "NO_BROKER",
            }
        )
    )
    state_values = (
        portfolio_reference,
        portfolio.policy_reference,
        previous_reference,
        sequence,
        trading_date,
        cash,
        tuple(marked),
        tuple(intents),
        tuple(fills),
        nav,
        peak_nav,
        exposure,
        turnover,
        nav / peak_nav - Decimal("1") if peak_nav else Decimal("0"),
        total_cost,
        attribution,
        source_references,
        recorded_at,
        limitations,
    )
    payload = _state_payload(*state_values)
    state_id, digest = content_identity("shadow-portfolio-day", payload)
    return ShadowPortfolioDayState(state_id, digest, *state_values)


def _weights(
    selected: tuple[ShadowPortfolioMarketObservation, ...],
    method: PortfolioWeightingMethod,
) -> dict[str, Decimal]:
    if not selected:
        return {}
    if method is PortfolioWeightingMethod.EQUAL_WEIGHT:
        return {item.symbol: Decimal("1") / Decimal(len(selected)) for item in selected}
    values = {
        item.symbol: (
            item.score
            if method is PortfolioWeightingMethod.SCORE_WEIGHT
            else item.risk_weight
        )
        for item in selected
    }
    if any(value is None or value <= 0 for value in values.values()):
        raise ValueError(f"{method.value} requires positive explicit weights")
    total = sum((value for value in values.values() if value is not None), Decimal("0"))
    output: dict[str, Decimal] = {}
    for symbol, value in values.items():
        if value is not None:
            output[symbol] = value / total
    return output


def _buy_rejections(
    *, observation: ShadowPortfolioMarketObservation, policy: ShadowPortfolioPolicy
) -> tuple[str, ...]:
    reasons = set(observation.reason_codes)
    if observation.trading_status is TradingStatus.UNKNOWN:
        reasons.add("TRADING_STATUS_UNKNOWN")
    elif observation.trading_status is TradingStatus.SUSPENDED:
        reasons.add("SECURITY_SUSPENDED")
    if observation.price_limit_state is PriceLimitState.UNKNOWN:
        reasons.add("PRICE_LIMIT_STATE_UNKNOWN")
    elif observation.price_limit_state is PriceLimitState.LIMIT_UP:
        reasons.add("BUY_LIMIT_UP")
    if observation.trade_session not in policy.allowed_trade_sessions:
        reasons.add(f"TRADE_SESSION_NOT_ALLOWED:{observation.trade_session.value}")
    if observation.reference_price is None or observation.mark_price is None:
        reasons.add("PRICE_EVIDENCE_MISSING")
    if observation.average_daily_amount is None:
        reasons.add("CAPACITY_EVIDENCE_MISSING")
    return tuple(sorted(reasons))


def _sell_rejections(
    *,
    observation: ShadowPortfolioMarketObservation | None,
    position: ShadowPortfolioPosition,
    trading_date: date,
    policy: ShadowPortfolioPolicy,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if policy.t_plus_one and trading_date <= position.opened_on:
        reasons.add("T_PLUS_ONE_NOT_SELLABLE")
    if observation is None:
        reasons.add("MARKET_OBSERVATION_MISSING")
        return tuple(sorted(reasons))
    reasons.update(observation.reason_codes)
    if observation.trading_status is TradingStatus.UNKNOWN:
        reasons.add("TRADING_STATUS_UNKNOWN")
    elif observation.trading_status is TradingStatus.SUSPENDED:
        reasons.add("SECURITY_SUSPENDED")
    if observation.price_limit_state is PriceLimitState.UNKNOWN:
        reasons.add("PRICE_LIMIT_STATE_UNKNOWN")
    elif observation.price_limit_state is PriceLimitState.LIMIT_DOWN:
        reasons.add("SELL_LIMIT_DOWN")
    if observation.trade_session not in policy.allowed_trade_sessions:
        reasons.add(f"TRADE_SESSION_NOT_ALLOWED:{observation.trade_session.value}")
    if observation.reference_price is None:
        reasons.add("PRICE_EVIDENCE_MISSING")
    if observation.average_daily_amount is None:
        reasons.add("CAPACITY_EVIDENCE_MISSING")
    return tuple(sorted(reasons))


def _intent(
    portfolio_id: ArtifactId,
    trading_date: date,
    symbol: str,
    side: ShadowTradeSide,
    quantity: Decimal,
    reference_price: Decimal | None,
    reason_codes: tuple[str, ...],
) -> ShadowPortfolioOrderIntent:
    payload = {
        "portfolio_id": str(portfolio_id),
        "trading_date": trading_date.isoformat(),
        "symbol": symbol,
        "side": side.value,
        "requested_quantity": str(quantity),
        "reference_price": _decimal(reference_price),
        "reason_codes": list(reason_codes),
    }
    intent_id, _digest = content_identity("shadow-portfolio-intent", payload)
    return ShadowPortfolioOrderIntent(
        intent_id, symbol, side, quantity, reference_price, reason_codes
    )


def _fill(
    *,
    intent: ShadowPortfolioOrderIntent,
    observation: ShadowPortfolioMarketObservation | None,
    policy: ShadowPortfolioPolicy,
    maximum_quantity: Decimal | None = None,
) -> ShadowPortfolioFill:
    blocked = bool(intent.reason_codes) or intent.requested_quantity <= 0
    reference_price = None if observation is None else observation.reference_price
    if blocked or reference_price is None:
        status = ShadowPortfolioFillStatus.UNFILLED
        quantity = notional = cost = Decimal("0")
        fill_price = None
    else:
        quantity = min(
            intent.requested_quantity,
            intent.requested_quantity
            if maximum_quantity is None
            else maximum_quantity,
        )
        if quantity <= 0:
            status = ShadowPortfolioFillStatus.UNFILLED
            quantity = notional = cost = Decimal("0")
            fill_price = None
            return _build_fill(
                intent=intent,
                policy=policy,
                status=status,
                quantity=quantity,
                fill_price=fill_price,
                notional=notional,
                cost=cost,
            )
        status = (
            ShadowPortfolioFillStatus.FILLED
            if quantity == intent.requested_quantity
            else ShadowPortfolioFillStatus.PARTIAL
        )
        direction = Decimal("1") if intent.side is ShadowTradeSide.BUY else Decimal("-1")
        fill_price = reference_price * (
            Decimal("1")
            + direction
            * (
                policy.parameter("slippage_bps")
                + policy.parameter("impact_bps")
            )
            / Decimal("10000")
        )
        notional = fill_price * quantity
        reference_notional = reference_price * quantity
        cost = abs(notional - reference_notional) + _explicit_cash_cost(
            notional, policy, selling=intent.side is ShadowTradeSide.SELL
        )
    return _build_fill(
        intent=intent,
        policy=policy,
        status=status,
        quantity=quantity,
        fill_price=fill_price,
        notional=notional,
        cost=cost,
    )


def _build_fill(
    *,
    intent: ShadowPortfolioOrderIntent,
    policy: ShadowPortfolioPolicy,
    status: ShadowPortfolioFillStatus,
    quantity: Decimal,
    fill_price: Decimal | None,
    notional: Decimal,
    cost: Decimal,
) -> ShadowPortfolioFill:
    provenance = tuple((item.name, item.provenance) for item in policy.parameters)
    limitations = tuple(sorted({*policy.limitations, "NOT_REAL_FILL"}))
    payload = {
        "intent_id": str(intent.intent_id),
        "symbol": intent.symbol,
        "side": intent.side.value,
        "status": status.value,
        "filled_quantity": str(quantity),
        "fill_price": _decimal(fill_price),
        "notional": str(notional),
        "total_cost": str(cost),
        "parameter_provenance": [
            [name, item.value] for name, item in provenance
        ],
        "limitations": list(limitations),
    }
    fill_id, _digest = content_identity("shadow-portfolio-fill", payload)
    return ShadowPortfolioFill(
        fill_id,
        intent.intent_id,
        intent.symbol,
        intent.side,
        status,
        quantity,
        fill_price,
        notional,
        cost,
        provenance,
        limitations,
    )


def _explicit_cash_cost(
    notional: Decimal, policy: ShadowPortfolioPolicy, *, selling: bool
) -> Decimal:
    bps = policy.parameter("commission_bps")
    if selling:
        bps += policy.parameter("exit_cost_bps")
    return notional * bps / Decimal("10000")


def _lot_floor(quantity: Decimal, lot_size: int) -> Decimal:
    lots = (quantity / Decimal(lot_size)).to_integral_value(rounding=ROUND_DOWN)
    return lots * Decimal(lot_size)


def _state_payload(
    portfolio_reference: ValidationArtifactReference,
    policy_reference: ValidationArtifactReference,
    previous_state_reference: ValidationArtifactReference | None,
    sequence: int,
    trading_date: date,
    cash: Decimal,
    positions: tuple[ShadowPortfolioPosition, ...],
    order_intents: tuple[ShadowPortfolioOrderIntent, ...],
    fills: tuple[ShadowPortfolioFill, ...],
    nav: Decimal,
    peak_nav: Decimal,
    gross_exposure: Decimal,
    turnover: Decimal,
    drawdown: Decimal,
    total_cost: Decimal,
    attribution: tuple[ShadowPortfolioAttribution, ...],
    source_references: tuple[ValidationArtifactReference, ...],
    recorded_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "shadow-portfolio-day-state/v1",
        "portfolio_reference": portfolio_reference.to_canonical_dict(),
        "policy_reference": policy_reference.to_canonical_dict(),
        "previous_state_reference": None if previous_state_reference is None else previous_state_reference.to_canonical_dict(),
        "sequence": sequence,
        "trading_date": trading_date.isoformat(),
        "cash": str(cash),
        "positions": [item.to_canonical_dict() for item in positions],
        "order_intents": [item.to_canonical_dict() for item in order_intents],
        "fills": [item.to_canonical_dict() for item in fills],
        "nav": str(nav),
        "peak_nav": str(peak_nav),
        "gross_exposure": str(gross_exposure),
        "turnover": str(turnover),
        "drawdown": str(drawdown),
        "total_cost": str(total_cost),
        "attribution": [item.to_canonical_dict() for item in attribution],
        "source_references": [item.to_canonical_dict() for item in source_references],
        "recorded_at": timestamp(recorded_at),
        "limitations": list(limitations),
    }


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _position_from_dict(value: Mapping[str, Any]) -> ShadowPortfolioPosition:
    return ShadowPortfolioPosition(
        symbol=str(value["symbol"]),
        quantity=Decimal(str(value["quantity"])),
        average_cost=Decimal(str(value["average_cost"])),
        opened_on=date.fromisoformat(str(value["opened_on"])),
        mark_price=Decimal(str(value["mark_price"])),
        market_value=Decimal(str(value["market_value"])),
        unrealized_pnl=Decimal(str(value["unrealized_pnl"])),
    )


def _intent_from_dict(value: Mapping[str, Any]) -> ShadowPortfolioOrderIntent:
    reference_price = value["reference_price"]
    return ShadowPortfolioOrderIntent(
        intent_id=ArtifactId(str(value["intent_id"])),
        symbol=str(value["symbol"]),
        side=ShadowTradeSide(str(value["side"])),
        requested_quantity=Decimal(str(value["requested_quantity"])),
        reference_price=(
            None if reference_price is None else Decimal(str(reference_price))
        ),
        reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
    )


def _fill_from_dict(value: Mapping[str, Any]) -> ShadowPortfolioFill:
    fill_price = value["fill_price"]
    return ShadowPortfolioFill(
        fill_id=ArtifactId(str(value["fill_id"])),
        intent_id=ArtifactId(str(value["intent_id"])),
        symbol=str(value["symbol"]),
        side=ShadowTradeSide(str(value["side"])),
        status=ShadowPortfolioFillStatus(str(value["status"])),
        filled_quantity=Decimal(str(value["filled_quantity"])),
        fill_price=None if fill_price is None else Decimal(str(fill_price)),
        notional=Decimal(str(value["notional"])),
        total_cost=Decimal(str(value["total_cost"])),
        parameter_provenance=tuple(
            (str(_sequence(item)[0]), ShadowParameterProvenance(str(_sequence(item)[1])))
            for item in _sequence(value["parameter_provenance"])
        ),
        limitations=tuple(str(item) for item in _sequence(value["limitations"])),
    )


def _attribution_from_dict(value: Mapping[str, Any]) -> ShadowPortfolioAttribution:
    return ShadowPortfolioAttribution(
        symbol=str(value["symbol"]),
        market_value=Decimal(str(value["market_value"])),
        unrealized_pnl=Decimal(str(value["unrealized_pnl"])),
        realized_pnl=Decimal(str(value["realized_pnl"])),
        cost=Decimal(str(value["cost"])),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Shadow Portfolio payload entry must be an object")
    return value


def _sequence(value: Any) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Shadow Portfolio payload entry must be a sequence")
    return tuple(value)


def _required_boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Shadow Portfolio payload boolean is invalid")
    return value


__all__ = [
    "PortfolioWeightingMethod",
    "ShadowParameterProvenance",
    "ShadowPortfolio",
    "ShadowPortfolioDayState",
    "ShadowPortfolioMarketObservation",
    "ShadowPortfolioPolicy",
    "ShadowPortfolioTradeSession",
    "ShadowTradeSide",
    "build_shadow_portfolio",
    "run_shadow_portfolio_day",
]
