"""Pre-Strategy Risk composition and immutable Strategy Opportunity facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.strategies.contracts import (
    StrategyOpportunityInput,
    StrategyRegistry,
    strategy_reference,
)


@dataclass(frozen=True, slots=True)
class PreStrategyPositionFact:
    symbol: str
    total_quantity: int
    available_quantity: int
    observed_market_value: Decimal

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if min(self.total_quantity, self.available_quantity) < 0:
            raise ValueError("pre-Strategy position quantities cannot be negative")
        if self.available_quantity > self.total_quantity:
            raise ValueError("pre-Strategy available quantity exceeds total")
        if self.observed_market_value < 0:
            raise ValueError("pre-Strategy position value cannot be negative")


@dataclass(frozen=True, slots=True)
class PreStrategyMarketFact:
    symbol: str
    eligible: bool
    liquidity: Decimal
    is_st: bool
    suspended: bool

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if not Decimal("0") <= self.liquidity <= Decimal("1"):
            raise ValueError("pre-Strategy liquidity must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class PreStrategyRiskFacts:
    """Typed projection of existing Account/Position/Pool/Risk owners."""

    account_scope: str
    account_state_reference: RuntimeArtifactReference
    reconciliation_reference: RuntimeArtifactReference
    market_state_reference: RuntimeArtifactReference
    risk_limit_reference: RuntimeArtifactReference
    decision_time: datetime
    available_at: datetime
    total_equity: Decimal
    available_cash: Decimal
    positions: tuple[PreStrategyPositionFact, ...]
    market_facts: tuple[PreStrategyMarketFact, ...]
    maximum_single_symbol_weight: Decimal
    minimum_liquidity: Decimal
    daily_loss_limit: Decimal | None

    def __post_init__(self) -> None:
        require_text("account_scope", self.account_scope)
        canonical_datetime(self.decision_time)
        canonical_datetime(self.available_at)
        if self.available_at > self.decision_time:
            raise ValueError("pre-Strategy facts are unavailable at DecisionTime")
        if self.account_state_reference.reference_kind != "MANUAL_ACCOUNT_OBSERVATION":
            raise ValueError("pre-Strategy Account owner kind is invalid")
        if self.reconciliation_reference.reference_kind != "ACCOUNT_RECONCILIATION":
            raise ValueError("pre-Strategy reconciliation owner kind is invalid")
        if self.market_state_reference.reference_kind != "DYNAMIC_STOCK_POOL":
            raise ValueError("pre-Strategy market owner kind is invalid")
        if self.risk_limit_reference.reference_kind != "DECISION_RISK_CONFIGURATION":
            raise ValueError("pre-Strategy Risk configuration owner kind is invalid")
        if self.total_equity < 0 or self.available_cash < 0:
            raise ValueError("pre-Strategy Account amounts cannot be negative")
        if not Decimal("0") < self.maximum_single_symbol_weight <= Decimal("1"):
            raise ValueError("pre-Strategy symbol limit must be within (0, 1]")
        if not Decimal("0") <= self.minimum_liquidity <= Decimal("1"):
            raise ValueError("pre-Strategy liquidity limit must be within [0, 1]")
        position_symbols = tuple(item.symbol for item in self.positions)
        market_symbols = tuple(item.symbol for item in self.market_facts)
        if position_symbols != tuple(sorted(set(position_symbols))):
            raise ValueError("pre-Strategy positions must be unique and sorted")
        if market_symbols != tuple(sorted(set(market_symbols))):
            raise ValueError("pre-Strategy market facts must be unique and sorted")


@dataclass(frozen=True, slots=True)
class StrategyOpportunityMaterial:
    """Exact owner-resolved Signal/Forecast/Context/Model material."""

    symbol: str
    strategy_version_reference: RuntimeArtifactReference
    signal_reference: RuntimeArtifactReference
    forecast_reference: RuntimeArtifactReference
    context_reference: RuntimeArtifactReference
    model_reference: RuntimeArtifactReference
    signal_active: bool
    expected_return: Decimal | None
    prediction_uncertainty: Decimal | None
    calibration_status: str
    available_at: datetime

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        canonical_datetime(self.available_at)


class StrategyOpportunityWriteAuthority(Protocol):
    def record_risk_state(
        self,
        state: PreStrategyRiskState,
        *,
        created_at: datetime,
    ) -> PreStrategyRiskState: ...

    def record_opportunity(
        self,
        opportunity: StrategyOpportunityInput,
        *,
        created_at: datetime,
    ) -> StrategyOpportunityInput: ...


class StrategyOpportunityProducer:
    """The sole business producer for both pre-Strategy owner facts."""

    def __init__(self, authority: StrategyOpportunityWriteAuthority) -> None:
        self._authority = authority

    def produce(
        self,
        *,
        candidates: CandidateSet,
        facts: PreStrategyRiskFacts,
        registry: StrategyRegistry,
        materials: tuple[StrategyOpportunityMaterial, ...],
        created_at: datetime,
    ) -> tuple[PreStrategyRiskState, tuple[StrategyOpportunityInput, ...]]:
        risk = self._authority.record_risk_state(
            build_pre_strategy_risk_state(candidates=candidates, facts=facts),
            created_at=created_at,
        )
        active = {strategy_reference(item) for item in registry.active_versions}
        candidate_reference = RuntimeArtifactReference(
            "CANDIDATE_SET",
            candidates.envelope.artifact_id,
            candidates.envelope.content_hash,
        )
        opportunities: list[StrategyOpportunityInput] = []
        keys: set[tuple[RuntimeArtifactReference, str]] = set()
        for material in sorted(
            materials,
            key=lambda item: (str(item.strategy_version_reference.artifact_id), item.symbol),
        ):
            key = (material.strategy_version_reference, material.symbol)
            if key in keys:
                raise ValueError("Strategy Opportunity material is ambiguous")
            keys.add(key)
            if material.strategy_version_reference not in active:
                raise ValueError("Strategy Opportunity material uses an inactive version")
            decision = risk.decision_for(material.symbol)
            opportunity = StrategyOpportunityInput.create(
                symbol=material.symbol,
                strategy_version_reference=material.strategy_version_reference,
                candidate_reference=candidate_reference,
                decision_time=facts.decision_time,
                signal_reference=material.signal_reference,
                forecast_reference=material.forecast_reference,
                context_reference=material.context_reference,
                risk_state_reference=risk.reference,
                model_reference=material.model_reference,
                signal_active=material.signal_active,
                risk_allows_action=decision.allows_action,
                risk_reason_codes=decision.reason_codes,
                expected_return=material.expected_return,
                prediction_uncertainty=material.prediction_uncertainty,
                calibration_status=material.calibration_status,
                available_at=max(risk.available_at, material.available_at),
            )
            opportunities.append(
                self._authority.record_opportunity(opportunity, created_at=created_at)
            )
        return risk, tuple(opportunities)


def build_pre_strategy_risk_state(
    *,
    candidates: CandidateSet,
    facts: PreStrategyRiskFacts,
) -> PreStrategyRiskState:
    candidate_reference = RuntimeArtifactReference(
        "CANDIDATE_SET",
        candidates.envelope.artifact_id,
        candidates.envelope.content_hash,
    )
    positions = {item.symbol: item for item in facts.positions}
    market = {item.symbol: item for item in facts.market_facts}
    decisions: list[PreStrategySymbolRiskDecision] = []
    for candidate in candidates.records:
        if candidate.selection_status not in {
            CandidateSelectionStatus.SELECTED,
            CandidateSelectionStatus.WATCHLIST,
        }:
            continue
        reasons: set[str] = set()
        position = positions.get(candidate.symbol)
        market_fact = market.get(candidate.symbol)
        if facts.total_equity <= 0:
            reasons.add("ACCOUNT_EQUITY_UNAVAILABLE")
        if facts.available_cash <= 0:
            reasons.add("AVAILABLE_CASH_UNAVAILABLE")
        if position is not None:
            if position.total_quantity > 0 and position.available_quantity == 0:
                reasons.add("POSITION_AVAILABLE_QUANTITY_ZERO")
            if (
                facts.total_equity <= 0
                or position.observed_market_value / facts.total_equity
                > facts.maximum_single_symbol_weight
            ):
                reasons.add("SINGLE_SYMBOL_EXPOSURE_LIMIT")
        if market_fact is None:
            reasons.add("MARKET_ELIGIBILITY_DATA_INSUFFICIENT")
        else:
            if not market_fact.eligible:
                reasons.add("SYMBOL_NOT_ELIGIBLE")
            if market_fact.liquidity < facts.minimum_liquidity:
                reasons.add("LIQUIDITY_LIMIT")
            if market_fact.is_st:
                reasons.add("ST_TRADING_RESTRICTION")
            if market_fact.suspended:
                reasons.add("SUSPENSION_TRADING_RESTRICTION")
        if facts.daily_loss_limit is not None:
            reasons.add("DAILY_LOSS_EVIDENCE_UNAVAILABLE")
        decisions.append(
            PreStrategySymbolRiskDecision(
                candidate.symbol,
                not reasons,
                tuple(sorted(reasons)),
            )
        )
    return PreStrategyRiskState.create(
        account_scope=facts.account_scope,
        candidate_reference=candidate_reference,
        decision_time=facts.decision_time,
        available_at=facts.available_at,
        account_state_reference=facts.account_state_reference,
        position_state_references=(facts.account_state_reference,),
        liquidity_constraint_references=(facts.market_state_reference,),
        position_constraint_references=(facts.reconciliation_reference,),
        risk_limit_references=(facts.risk_limit_reference,),
        trading_restriction_references=(facts.market_state_reference,),
        symbol_decisions=tuple(decisions),
        limitations=(
            "PRE_STRATEGY_RISK_INCREASE_FILTER_ONLY",
            "RESEARCH_SHADOW_ONLY",
        ),
    )


@dataclass(frozen=True, slots=True)
class PreStrategySymbolRiskDecision:
    symbol: str
    allows_action: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("pre-Strategy Risk reason codes must be unique and sorted")
        if self.allows_action == bool(self.reason_codes):
            raise ValueError("pre-Strategy Risk decision and reason codes disagree")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "allows_action": self.allows_action,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PreStrategySymbolRiskDecision:
        return cls(
            symbol=str(payload["symbol"]),
            allows_action=bool(payload["allows_action"]),
            reason_codes=tuple(str(item) for item in payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class PreStrategyRiskState:
    risk_state_id: ArtifactId
    risk_state_hash: str
    account_scope: str
    candidate_reference: RuntimeArtifactReference
    decision_time: datetime
    available_at: datetime
    account_state_reference: RuntimeArtifactReference
    position_state_references: tuple[RuntimeArtifactReference, ...]
    liquidity_constraint_references: tuple[RuntimeArtifactReference, ...]
    position_constraint_references: tuple[RuntimeArtifactReference, ...]
    risk_limit_references: tuple[RuntimeArtifactReference, ...]
    trading_restriction_references: tuple[RuntimeArtifactReference, ...]
    symbol_decisions: tuple[PreStrategySymbolRiskDecision, ...]
    limitations: tuple[str, ...]
    schema_version: str = "pre-strategy-risk-state/v1"

    def __post_init__(self) -> None:
        require_text("account_scope", self.account_scope)
        require_sha256("risk_state_hash", self.risk_state_hash)
        canonical_datetime(self.decision_time)
        canonical_datetime(self.available_at)
        if self.available_at > self.decision_time:
            raise ValueError("pre-Strategy Risk state is unavailable at DecisionTime")
        if self.candidate_reference.reference_kind != "CANDIDATE_SET":
            raise ValueError("pre-Strategy Risk requires Candidate owner")
        if self.account_state_reference.reference_kind in {
            "COMPLETE_ACCOUNT_RISK_DECISION",
            "CROSS_STRATEGY_PORTFOLIO",
            "PORTFOLIO_DECISION",
        }:
            raise ValueError("post-Portfolio facts cannot own pre-Strategy Risk")
        for references in self.reference_groups:
            if references != _references(references):
                raise ValueError("pre-Strategy Risk owner references must be unique and sorted")
            if any(
                item.reference_kind == "COMPLETE_ACCOUNT_RISK_DECISION"
                for item in references
            ):
                raise ValueError("Complete Account Risk is post-Portfolio authority")
        symbols = tuple(item.symbol for item in self.symbol_decisions)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("pre-Strategy Risk symbol decisions must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("pre-Strategy Risk limitations must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.risk_state_hash:
            raise ValueError("pre-Strategy Risk state hash mismatch")
        if self.risk_state_id != ArtifactId(
            f"pre-strategy-risk-state:{self.risk_state_hash[7:]}"
        ):
            raise ValueError("pre-Strategy Risk state identity mismatch")

    @property
    def reference_groups(self) -> tuple[tuple[RuntimeArtifactReference, ...], ...]:
        return (
            self.position_state_references,
            self.liquidity_constraint_references,
            self.position_constraint_references,
            self.risk_limit_references,
            self.trading_restriction_references,
        )

    @property
    def source_references(self) -> tuple[RuntimeArtifactReference, ...]:
        return _references(
            (
                self.candidate_reference,
                self.account_state_reference,
                *(item for group in self.reference_groups for item in group),
            )
        )

    @property
    def reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            "PRE_STRATEGY_RISK_STATE",
            self.risk_state_id,
            self.risk_state_hash,
        )

    def decision_for(self, symbol: str) -> PreStrategySymbolRiskDecision:
        matches = tuple(item for item in self.symbol_decisions if item.symbol == symbol)
        if len(matches) != 1:
            raise KeyError(symbol)
        return matches[0]

    @classmethod
    def create(
        cls,
        *,
        account_scope: str,
        candidate_reference: RuntimeArtifactReference,
        decision_time: datetime,
        available_at: datetime,
        account_state_reference: RuntimeArtifactReference,
        position_state_references: tuple[RuntimeArtifactReference, ...],
        liquidity_constraint_references: tuple[RuntimeArtifactReference, ...],
        position_constraint_references: tuple[RuntimeArtifactReference, ...],
        risk_limit_references: tuple[RuntimeArtifactReference, ...],
        trading_restriction_references: tuple[RuntimeArtifactReference, ...],
        symbol_decisions: tuple[PreStrategySymbolRiskDecision, ...],
        limitations: tuple[str, ...] = (),
    ) -> PreStrategyRiskState:
        values = {
            "account_scope": account_scope,
            "candidate_reference": candidate_reference,
            "decision_time": decision_time,
            "available_at": available_at,
            "account_state_reference": account_state_reference,
            "position_state_references": _references(position_state_references),
            "liquidity_constraint_references": _references(
                liquidity_constraint_references
            ),
            "position_constraint_references": _references(
                position_constraint_references
            ),
            "risk_limit_references": _references(risk_limit_references),
            "trading_restriction_references": _references(
                trading_restriction_references
            ),
            "symbol_decisions": tuple(
                sorted(symbol_decisions, key=lambda item: item.symbol)
            ),
            "limitations": tuple(sorted(set(limitations))),
        }
        digest = canonical_hash(_risk_payload(**values))
        return cls(
            risk_state_id=ArtifactId(f"pre-strategy-risk-state:{digest[7:]}"),
            risk_state_hash=digest,
            account_scope=account_scope,
            candidate_reference=candidate_reference,
            decision_time=decision_time,
            available_at=available_at,
            account_state_reference=account_state_reference,
            position_state_references=_references(position_state_references),
            liquidity_constraint_references=_references(
                liquidity_constraint_references
            ),
            position_constraint_references=_references(
                position_constraint_references
            ),
            risk_limit_references=_references(risk_limit_references),
            trading_restriction_references=_references(
                trading_restriction_references
            ),
            symbol_decisions=tuple(
                sorted(symbol_decisions, key=lambda item: item.symbol)
            ),
            limitations=tuple(sorted(set(limitations))),
        )

    def identity_payload(self) -> dict[str, Any]:
        return _risk_payload(
            **{
                name: getattr(self, name)
                for name in (
                    "account_scope",
                    "candidate_reference",
                    "decision_time",
                    "available_at",
                    "account_state_reference",
                    "position_state_references",
                    "liquidity_constraint_references",
                    "position_constraint_references",
                    "risk_limit_references",
                    "trading_restriction_references",
                    "symbol_decisions",
                    "limitations",
                )
            }
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "risk_state_id": str(self.risk_state_id),
            "risk_state_hash": self.risk_state_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PreStrategyRiskState:
        def refs(name: str) -> tuple[RuntimeArtifactReference, ...]:
            return tuple(
                RuntimeArtifactReference.from_canonical_dict(item)
                for item in payload[name]
            )

        return cls(
            risk_state_id=ArtifactId(str(payload["risk_state_id"])),
            risk_state_hash=str(payload["risk_state_hash"]),
            account_scope=str(payload["account_scope"]),
            candidate_reference=RuntimeArtifactReference.from_canonical_dict(
                payload["candidate_reference"]
            ),
            decision_time=datetime.fromisoformat(str(payload["decision_time"])),
            available_at=datetime.fromisoformat(str(payload["available_at"])),
            account_state_reference=RuntimeArtifactReference.from_canonical_dict(
                payload["account_state_reference"]
            ),
            position_state_references=refs("position_state_references"),
            liquidity_constraint_references=refs(
                "liquidity_constraint_references"
            ),
            position_constraint_references=refs(
                "position_constraint_references"
            ),
            risk_limit_references=refs("risk_limit_references"),
            trading_restriction_references=refs(
                "trading_restriction_references"
            ),
            symbol_decisions=tuple(
                PreStrategySymbolRiskDecision.from_canonical_dict(item)
                for item in payload["symbol_decisions"]
            ),
            limitations=tuple(str(item) for item in payload["limitations"]),
            schema_version=str(payload["schema_version"]),
        )


def _risk_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "pre-strategy-risk-state/v1",
        "account_scope": values["account_scope"],
        "candidate_reference": values["candidate_reference"].to_canonical_dict(),
        "decision_time": canonical_datetime(values["decision_time"]),
        "available_at": canonical_datetime(values["available_at"]),
        "account_state_reference": values[
            "account_state_reference"
        ].to_canonical_dict(),
        **{
            name: [item.to_canonical_dict() for item in values[name]]
            for name in (
                "position_state_references",
                "liquidity_constraint_references",
                "position_constraint_references",
                "risk_limit_references",
                "trading_restriction_references",
            )
        },
        "symbol_decisions": [
            item.to_canonical_dict() for item in values["symbol_decisions"]
        ],
        "limitations": list(values["limitations"]),
    }


def _references(
    references: tuple[RuntimeArtifactReference, ...],
) -> tuple[RuntimeArtifactReference, ...]:
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


__all__ = [
    "PreStrategyMarketFact",
    "PreStrategyPositionFact",
    "PreStrategyRiskFacts",
    "PreStrategyRiskState",
    "PreStrategySymbolRiskDecision",
    "StrategyOpportunityMaterial",
    "StrategyOpportunityProducer",
    "build_pre_strategy_risk_state",
]
