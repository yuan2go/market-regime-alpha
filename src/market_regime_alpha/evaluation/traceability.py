"""Full authority-chain validation for closed trade outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    ManualTradeId,
    OpportunityId,
    PortfolioDecisionId,
    PositionBookId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.decision.opportunity import TradingOpportunity
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.evaluation.lifecycle import (
    TradeEvaluationConfig,
    TradeOutcome,
    TradeOutcomeEvaluator,
    TradePathObservation,
)
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.execution.manual import (
    ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    TRACEABLE_MANUAL_TRADE_SCHEMA,
    ExecutionDeviation,
    Fill,
    ManualTradeRecord,
    ManualTradeAuthorityRoute,
)
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
    CompleteAccountRiskService,
)
from market_regime_alpha.position.authority import (
    TRACEABLE_POSITION_SNAPSHOT_SCHEMA,
    PositionSnapshot,
)


TRACEABLE_TRADE_OUTCOME_SCHEMA = "traceable-trade-outcome-v1"


@dataclass(frozen=True, slots=True)
class TraceableTradeOutcome:
    schema_version: str
    traceable_outcome_id: ArtifactId
    outcome: TradeOutcome
    position_book_id: PositionBookId
    opportunity_id: OpportunityId
    thesis_id: ThesisId
    source_manual_trade_ids: tuple[ManualTradeId, ...]
    portfolio_decision_ids: tuple[PortfolioDecisionId, ...]
    risk_decision_ids: tuple[RiskDecisionId, ...]
    source_fill_ids: tuple[FillId, ...]
    authority_chain_hash: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != TRACEABLE_TRADE_OUTCOME_SCHEMA:
            raise ValueError("unsupported TraceableTradeOutcome schema")
        require_sha256("authority_chain_hash", self.authority_chain_hash)
        for label, values in (
            ("ManualTrade", self.source_manual_trade_ids),
            ("PortfolioDecision", self.portfolio_decision_ids),
            ("RiskDecision", self.risk_decision_ids),
            ("Fill", self.source_fill_ids),
        ):
            if not values or values != tuple(sorted(set(values), key=str)):
                raise ValueError(f"traceable outcome {label} IDs must be sorted and unique")
        if self.thesis_id != self.outcome.thesis_id:
            raise ValueError("traceable outcome Thesis differs from TradeOutcome")
        if self.source_fill_ids != self.outcome.source_fill_ids:
            raise ValueError("traceable outcome Fill scope differs from TradeOutcome")
        expected = _traceable_outcome_id(self.semantic_payload())
        if self.traceable_outcome_id != expected:
            raise ValueError("TraceableTradeOutcome content identity mismatch")

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome.to_canonical_dict(),
            "position_book_id": str(self.position_book_id),
            "opportunity_id": str(self.opportunity_id),
            "thesis_id": str(self.thesis_id),
            "source_manual_trade_ids": [
                str(item) for item in self.source_manual_trade_ids
            ],
            "portfolio_decision_ids": [
                str(item) for item in self.portfolio_decision_ids
            ],
            "risk_decision_ids": [str(item) for item in self.risk_decision_ids],
            "source_fill_ids": [str(item) for item in self.source_fill_ids],
            "authority_chain_hash": self.authority_chain_hash,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "traceable_outcome_id": str(self.traceable_outcome_id),
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TraceableTradeOutcome:
        expected = {
            "traceable_outcome_id",
            "schema_version",
            "outcome",
            "position_book_id",
            "opportunity_id",
            "thesis_id",
            "source_manual_trade_ids",
            "portfolio_decision_ids",
            "risk_decision_ids",
            "source_fill_ids",
            "authority_chain_hash",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("TraceableTradeOutcome fields mismatch")
        return cls(
            schema_version=str(payload["schema_version"]),
            traceable_outcome_id=ArtifactId(str(payload["traceable_outcome_id"])),
            outcome=TradeOutcome.from_canonical_dict(_object(payload["outcome"])),
            position_book_id=PositionBookId(str(payload["position_book_id"])),
            opportunity_id=OpportunityId(str(payload["opportunity_id"])),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            source_manual_trade_ids=tuple(
                ManualTradeId(str(item))
                for item in _array(payload["source_manual_trade_ids"])
            ),
            portfolio_decision_ids=tuple(
                PortfolioDecisionId(str(item))
                for item in _array(payload["portfolio_decision_ids"])
            ),
            risk_decision_ids=tuple(
                RiskDecisionId(str(item))
                for item in _array(payload["risk_decision_ids"])
            ),
            source_fill_ids=tuple(
                FillId(str(item)) for item in _array(payload["source_fill_ids"])
            ),
            authority_chain_hash=str(payload["authority_chain_hash"]),
            reason_codes=tuple(str(item) for item in _array(payload["reason_codes"])),
        )


class TraceableTradeOutcomeEvaluator:
    """Reject outcomes unless every Fill resolves through the approved chain."""

    def evaluate(
        self,
        *,
        opportunity: TradingOpportunity,
        thesis: TradingThesis,
        portfolio_decisions: tuple[CompleteAccountPortfolioDecision, ...],
        risk_decisions: tuple[CompleteAccountRiskDecision, ...],
        manual_trades: tuple[ManualTradeRecord, ...],
        final_position: PositionSnapshot,
        fills: tuple[Fill, ...],
        path: TradePathObservation,
        execution_deviations: tuple[ExecutionDeviation, ...],
        configuration: TradeEvaluationConfig,
        evaluated_at: datetime,
    ) -> TraceableTradeOutcome:
        if final_position.schema_version != TRACEABLE_POSITION_SNAPSHOT_SCHEMA:
            raise ValueError("traceable outcome requires traceable Position authority")
        if (
            final_position.position_book_id is None
            or final_position.thesis_id != thesis.thesis_id
            or final_position.opportunity_id != opportunity.opportunity_id
            or thesis.opportunity_id != opportunity.opportunity_id
        ):
            raise ValueError("traceable outcome Opportunity/Thesis/Position mismatch")
        trades = tuple(sorted(manual_trades, key=lambda item: str(item.manual_trade_id)))
        trade_ids = tuple(item.manual_trade_id for item in trades)
        if trade_ids != final_position.source_manual_trade_ids:
            raise ValueError("traceable outcome ManualTrade scope differs from Position")
        fill_trade_ids = {item.manual_trade_id for item in fills}
        if fill_trade_ids != set(trade_ids):
            raise ValueError("traceable outcome Fill ownership differs from ManualTrades")

        portfolios = {item.decision_id: item for item in portfolio_decisions}
        risks = {item.risk_decision_id: item for item in risk_decisions}
        if len(portfolios) != len(portfolio_decisions) or len(risks) != len(
            risk_decisions
        ):
            raise ValueError("traceable outcome authority identities must be unique")
        for trade in trades:
            if (
                trade.risk_decision_id is None
                or trade.portfolio_decision_id is None
            ):
                raise ValueError("traceable outcome omits Portfolio/Risk authority")
            risk = risks.get(trade.risk_decision_id)
            portfolio = portfolios.get(trade.portfolio_decision_id)
            if risk is None or portfolio is None:
                raise ValueError("traceable outcome omits Portfolio/Risk authority")
            expected_risk = CompleteAccountRiskService().assess(
                portfolio,
                actor=risk.actor,
                reason=risk.reason,
                started_at=risk.started_at,
                completed_at=risk.completed_at,
            )
            deltas = tuple(
                delta
                for delta in portfolio.post_trade.proposed_deltas
                if canonical_hash(delta.to_canonical_dict())
                == trade.target_position_hash
            )
            if (
                (
                    trade.schema_version != TRACEABLE_MANUAL_TRADE_SCHEMA
                    and not (
                        trade.schema_version
                        == ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA
                        and trade.authority_route
                        is ManualTradeAuthorityRoute.INCREASING
                    )
                )
                or trade.position_book_id != final_position.position_book_id
                or trade.thesis_id != thesis.thesis_id
                or trade.opportunity_id != opportunity.opportunity_id
                or risk != expected_risk
                or risk.portfolio_decision_id != portfolio.decision_id
                or trade.risk_decision_hash
                != canonical_hash(risk.to_canonical_dict())
                or trade.post_trade_snapshot_id != portfolio.post_trade.snapshot_id
                or trade.post_trade_snapshot_hash
                != portfolio.post_trade.content_hash
                or len(deltas) != 1
                or deltas[0].thesis_id != thesis.thesis_id
                or deltas[0].symbol != thesis.symbol
            ):
                raise ValueError("traceable outcome authority chain mismatch")

        outcome = TradeOutcomeEvaluator().evaluate(
            thesis=thesis,
            final_position=final_position,
            fills=fills,
            path=path,
            execution_deviations=execution_deviations,
            configuration=configuration,
            evaluated_at=evaluated_at,
        )
        ordered_portfolios = tuple(
            sorted(portfolio_decisions, key=lambda item: str(item.decision_id))
        )
        ordered_risks = tuple(
            sorted(risk_decisions, key=lambda item: str(item.risk_decision_id))
        )
        ordered_fills = tuple(sorted(fills, key=lambda item: str(item.fill_id)))
        authority_payload = {
            "opportunity": opportunity.to_canonical_dict(),
            "thesis": thesis.to_canonical_dict(),
            "portfolios": [item.to_canonical_dict() for item in ordered_portfolios],
            "risks": [item.to_canonical_dict() for item in ordered_risks],
            "manual_trades": [item.to_canonical_dict() for item in trades],
            "position": final_position.to_canonical_dict(),
            "fills": [item.to_canonical_dict() for item in ordered_fills],
        }
        chain_hash = canonical_hash(authority_payload)
        semantic = {
            "schema_version": TRACEABLE_TRADE_OUTCOME_SCHEMA,
            "outcome": outcome.to_canonical_dict(),
            "position_book_id": str(final_position.position_book_id),
            "opportunity_id": str(opportunity.opportunity_id),
            "thesis_id": str(thesis.thesis_id),
            "source_manual_trade_ids": [str(item) for item in trade_ids],
            "portfolio_decision_ids": [
                str(item) for item in sorted(portfolios, key=str)
            ],
            "risk_decision_ids": [str(item) for item in sorted(risks, key=str)],
            "source_fill_ids": [str(item) for item in outcome.source_fill_ids],
            "authority_chain_hash": chain_hash,
            "reason_codes": ["FULL_AUTHORITY_CHAIN_VERIFIED"],
        }
        return TraceableTradeOutcome(
            schema_version=TRACEABLE_TRADE_OUTCOME_SCHEMA,
            traceable_outcome_id=_traceable_outcome_id(semantic),
            outcome=outcome,
            position_book_id=final_position.position_book_id,
            opportunity_id=opportunity.opportunity_id,
            thesis_id=thesis.thesis_id,
            source_manual_trade_ids=trade_ids,
            portfolio_decision_ids=tuple(sorted(portfolios, key=str)),
            risk_decision_ids=tuple(sorted(risks, key=str)),
            source_fill_ids=outcome.source_fill_ids,
            authority_chain_hash=chain_hash,
            reason_codes=("FULL_AUTHORITY_CHAIN_VERIFIED",),
        )


def _traceable_outcome_id(payload: Mapping[str, Any]) -> ArtifactId:
    digest = canonical_hash(payload).split(":", 1)[1]
    return ArtifactId(f"traceable-trade-outcome-{digest[:24]}")


def _array(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("TraceableTradeOutcome array field mismatch")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("TraceableTradeOutcome object field mismatch")
    return value
