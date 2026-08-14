"""Simple cross-strategy Portfolio and Risk baseline over Strategy Proposals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    MultiStrategyCycle,
    StrategyProposal,
)


class CrossStrategyPortfolioStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    PARTIAL = "PARTIAL"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True, slots=True)
class CrossStrategyPortfolioPolicy:
    maximum_gross_weight: Decimal
    maximum_symbol_weight: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") < self.maximum_gross_weight <= Decimal("1"):
            raise ValueError("maximum gross weight must be within (0, 1]")
        if not Decimal("0") < self.maximum_symbol_weight <= self.maximum_gross_weight:
            raise ValueError("maximum symbol weight must be within gross weight")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "maximum_gross_weight": str(self.maximum_gross_weight),
            "maximum_symbol_weight": str(self.maximum_symbol_weight),
        }


@dataclass(frozen=True, slots=True)
class CrossStrategyPortfolioLine:
    strategy_version_reference: RuntimeArtifactReference
    proposal_reference: RuntimeArtifactReference
    symbol: str
    action: CanonicalStrategyAction
    requested_weight: Decimal
    accepted_weight: Decimal
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if abs(self.accepted_weight) > abs(self.requested_weight):
            raise ValueError("Portfolio cannot exceed requested Strategy weight")
        if self.requested_weight * self.accepted_weight < 0:
            raise ValueError("Portfolio cannot reverse a Strategy Proposal")
        if not self.reason_codes:
            raise ValueError("Portfolio line requires attribution")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "strategy_version_reference": self.strategy_version_reference.to_canonical_dict(),
            "proposal_reference": self.proposal_reference.to_canonical_dict(),
            "symbol": self.symbol,
            "action": self.action.value,
            "requested_weight": str(self.requested_weight),
            "accepted_weight": str(self.accepted_weight),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class CrossStrategyPortfolioDecision:
    decision_id: ArtifactId
    decision_hash: str
    cycle_reference: RuntimeArtifactReference
    policy: CrossStrategyPortfolioPolicy
    status: CrossStrategyPortfolioStatus
    gross_accepted_weight: Decimal
    lines: tuple[CrossStrategyPortfolioLine, ...]
    limitations: tuple[str, ...]
    schema_version: str = "cross-strategy-portfolio-decision/v1"

    def __post_init__(self) -> None:
        require_sha256("decision_hash", self.decision_hash)
        proposal_ids = tuple(str(item.proposal_reference.artifact_id) for item in self.lines)
        if proposal_ids != tuple(sorted(set(proposal_ids))):
            raise ValueError("Portfolio lines must be proposal-sorted and unique")
        actual_gross = sum(
            (max(Decimal("0"), item.accepted_weight) for item in self.lines),
            Decimal("0"),
        )
        if actual_gross != self.gross_accepted_weight:
            raise ValueError("Portfolio gross weight mismatch")
        if actual_gross > self.policy.maximum_gross_weight:
            raise ValueError("Portfolio gross risk limit exceeded")
        if not self.limitations:
            raise ValueError("Portfolio decision limitations cannot be empty")
        if canonical_hash(self.identity_payload()) != self.decision_hash:
            raise ValueError("Portfolio decision hash mismatch")
        if str(self.decision_id) != f"cross-strategy-portfolio:{self.decision_hash[7:]}":
            raise ValueError("Portfolio decision identity mismatch")

    @property
    def production_authorized(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cycle_reference": self.cycle_reference.to_canonical_dict(),
            "policy": self.policy.to_canonical_dict(),
            "status": self.status.value,
            "gross_accepted_weight": str(self.gross_accepted_weight),
            "lines": [item.to_canonical_dict() for item in self.lines],
            "limitations": list(self.limitations),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "decision_hash": self.decision_hash,
            **self.identity_payload(),
        }


def build_cross_strategy_portfolio(
    *,
    cycle: MultiStrategyCycle,
    policy: CrossStrategyPortfolioPolicy,
) -> CrossStrategyPortfolioDecision:
    proposals = tuple(proposal for run in cycle.runs for proposal in run.proposals)
    accepted: dict[ArtifactId, tuple[Decimal, tuple[str, ...]]] = {}
    gross_remaining = policy.maximum_gross_weight
    for symbol in sorted({item.symbol for item in proposals}):
        symbol_proposals = tuple(item for item in proposals if item.symbol == symbol)
        reductions = tuple(item for item in symbol_proposals if item.desired_weight < 0)
        increases = tuple(item for item in symbol_proposals if item.desired_weight > 0)
        for proposal in reductions:
            accepted[proposal.proposal_id] = (
                proposal.desired_weight,
                ("RISK_REDUCTION_ACCEPTED",),
            )
        if reductions and increases:
            for proposal in increases:
                accepted[proposal.proposal_id] = (
                    Decimal("0"),
                    ("OPPOSING_REDUCTION_PRIORITY",),
                )
            continue
        symbol_remaining = min(policy.maximum_symbol_weight, gross_remaining)
        ranked = tuple(
            sorted(
                increases,
                key=lambda item: (
                    -(item.utility_score or Decimal("0")),
                    str(item.strategy_version_reference.artifact_id),
                ),
            )
        )
        for proposal in ranked:
            weight = min(proposal.desired_weight, symbol_remaining)
            reasons = (
                ("ACCEPTED_WITHIN_BASELINE_RISK",)
                if weight == proposal.desired_weight
                else ("GROSS_WEIGHT_CAPPED" if gross_remaining <= symbol_remaining else "SYMBOL_WEIGHT_CAPPED",)
            )
            accepted[proposal.proposal_id] = (weight, reasons)
            symbol_remaining -= weight
            gross_remaining -= weight

    lines = tuple(
        sorted(
            (_line(proposal, *accepted[proposal.proposal_id]) for proposal in proposals),
            key=lambda item: str(item.proposal_reference.artifact_id),
        )
    )
    if not lines:
        status = CrossStrategyPortfolioStatus.NO_ACTION
    elif any(item.accepted_weight != item.requested_weight for item in lines):
        status = CrossStrategyPortfolioStatus.PARTIAL
    else:
        status = CrossStrategyPortfolioStatus.ACCEPTED
    cycle_reference = RuntimeArtifactReference("MULTI_STRATEGY_CYCLE", cycle.cycle_id, cycle.cycle_hash)
    gross = policy.maximum_gross_weight - gross_remaining
    limitations = (
        "ALPHA_NOT_ESTABLISHED",
        "ENGINEERING_BASELINE_ONLY",
        "NO_OPTIMIZER",
        "NO_ORDER_AUTHORITY",
        "PRODUCTION_AUTHORIZED_FALSE",
    )
    payload = {
        "schema_version": "cross-strategy-portfolio-decision/v1",
        "cycle_reference": cycle_reference.to_canonical_dict(),
        "policy": policy.to_canonical_dict(),
        "status": status.value,
        "gross_accepted_weight": str(gross),
        "lines": [item.to_canonical_dict() for item in lines],
        "limitations": list(limitations),
    }
    digest = canonical_hash(payload)
    return CrossStrategyPortfolioDecision(
        decision_id=ArtifactId(f"cross-strategy-portfolio:{digest[7:]}"),
        decision_hash=digest,
        cycle_reference=cycle_reference,
        policy=policy,
        status=status,
        gross_accepted_weight=gross,
        lines=lines,
        limitations=limitations,
    )


def _line(
    proposal: StrategyProposal,
    accepted_weight: Decimal,
    reason_codes: tuple[str, ...],
) -> CrossStrategyPortfolioLine:
    return CrossStrategyPortfolioLine(
        strategy_version_reference=proposal.strategy_version_reference,
        proposal_reference=RuntimeArtifactReference("STRATEGY_PROPOSAL", proposal.proposal_id, proposal.proposal_hash),
        symbol=proposal.symbol,
        action=proposal.action,
        requested_weight=proposal.desired_weight,
        accepted_weight=accepted_weight,
        reason_codes=reason_codes,
    )


__all__ = [
    "CrossStrategyPortfolioDecision",
    "CrossStrategyPortfolioLine",
    "CrossStrategyPortfolioPolicy",
    "CrossStrategyPortfolioStatus",
    "build_cross_strategy_portfolio",
]
