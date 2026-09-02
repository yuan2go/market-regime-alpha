"""Deterministic complete PortfolioProposal Authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import DecisionArtifactBinding
from market_regime_alpha.decision_support.domain.opportunity import OpportunityStatus
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class PortfolioAllocationMethod(StrEnum):
    EQUAL_WEIGHT_ACTIONABLE = "EQUAL_WEIGHT_ACTIONABLE"


class PortfolioProposalStatus(StrEnum):
    PROPOSED = "PROPOSED"
    NO_ACTION = "NO_ACTION"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class PortfolioLineStatus(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


def _sha(value: str, label: str) -> str:
    try:
        return str(ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256") from exc


def _ratio(value: Decimal, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be a finite ratio")
    return value


@dataclass(frozen=True, slots=True)
class PortfolioPolicyPlan:
    portfolio_policy_id: UUID
    policy_code: str
    version: int
    supersedes_policy_id: UUID | None
    allocation_method: PortfolioAllocationMethod
    minimum_estimable_count: int
    maximum_line_count: int
    maximum_single_weight: Decimal
    maximum_gross_weight: Decimal
    maximum_net_weight: Decimal
    minimum_cash_weight: Decimal
    maximum_turnover: Decimal
    decimal_places: int
    code_artifact: DecisionArtifactBinding
    config_artifact: DecisionArtifactBinding
    provenance_sha256: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.policy_code) or self.version < 1:
            raise ValueError("PortfolioPolicy identity is invalid")
        if (self.version == 1) != (self.supersedes_policy_id is None):
            raise ValueError("PortfolioPolicy supersession shape is invalid")
        if self.minimum_estimable_count < 1 or self.maximum_line_count < 1:
            raise ValueError("PortfolioPolicy counts must be positive")
        if not 1 <= self.decimal_places <= 12:
            raise ValueError("Portfolio decimal places are invalid")
        for name in (
            "maximum_single_weight", "maximum_gross_weight", "maximum_net_weight",
            "minimum_cash_weight", "maximum_turnover",
        ):
            _ratio(getattr(self, name), name)
        if self.maximum_net_weight > self.maximum_gross_weight:
            raise ValueError("Portfolio net cap cannot exceed gross cap")
        object.__setattr__(self, "provenance_sha256", _sha(self.provenance_sha256, "Portfolio provenance"))
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "allocation_method": self.allocation_method,
            "code_artifact": self.code_artifact,
            "config_artifact": self.config_artifact,
            "decimal_places": self.decimal_places,
            "maximum_gross_weight": self.maximum_gross_weight,
            "maximum_line_count": self.maximum_line_count,
            "maximum_net_weight": self.maximum_net_weight,
            "maximum_single_weight": self.maximum_single_weight,
            "maximum_turnover": self.maximum_turnover,
            "minimum_cash_weight": self.minimum_cash_weight,
            "minimum_estimable_count": self.minimum_estimable_count,
            "policy_code": self.policy_code,
            "portfolio_policy_id": self.portfolio_policy_id,
            "provenance_sha256": self.provenance_sha256,
            "supersedes_policy_id": self.supersedes_policy_id,
            "version": self.version,
        }))


@dataclass(frozen=True, slots=True)
class PreparedPortfolioOpportunity:
    opportunity_id: UUID
    ordinal: int
    candidate_id: UUID
    instrument_id: UUID
    target_definition_id: UUID
    status: OpportunityStatus
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", _sha(self.content_sha256, "Opportunity hash"))


@dataclass(frozen=True, slots=True)
class PreparedPortfolioInputs:
    decision_run_id: UUID
    strategy_version_id: UUID
    opportunity_set_id: UUID
    opportunity_set_sha256: str
    opportunity_set_recorded_at: datetime
    opportunities: tuple[PreparedPortfolioOpportunity, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "opportunity_set_sha256", _sha(self.opportunity_set_sha256, "OpportunitySet hash"))
        object.__setattr__(
            self,
            "opportunity_set_recorded_at",
            require_utc(
                self.opportunity_set_recorded_at,
                field="OpportunitySet recorded_at",
            ),
        )
        if tuple(item.ordinal for item in self.opportunities) != tuple(range(1, len(self.opportunities) + 1)):
            raise ValueError("Portfolio Opportunity roster must be contiguous")


@dataclass(frozen=True, slots=True)
class PortfolioLinePlan:
    portfolio_line_id: UUID
    ordinal: int
    source: PreparedPortfolioOpportunity
    status: PortfolioLineStatus
    proposed_weight: Decimal
    reason_code: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _ratio(self.proposed_weight, "Portfolio line weight")
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "opportunity_id": self.source.opportunity_id,
            "ordinal": self.ordinal,
            "portfolio_line_id": self.portfolio_line_id,
            "proposed_weight": self.proposed_weight,
            "reason_code": self.reason_code,
            "status": self.status,
        }))


@dataclass(frozen=True, slots=True)
class PortfolioProposalAuthority:
    portfolio_proposal_id: UUID
    prepared: PreparedPortfolioInputs
    policy: PortfolioPolicyPlan
    status: PortfolioProposalStatus
    lines: tuple[PortfolioLinePlan, ...]
    line_roster_sha256: str
    included_count: int
    excluded_count: int
    not_estimable_count: int
    gross_weight: Decimal
    net_weight: Decimal
    cash_weight: Decimal
    turnover_weight: Decimal
    request_identity: str
    request_sha256: str
    command_receipt_id: UUID
    recorded_at: datetime
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "line_roster_sha256", _sha(self.line_roster_sha256, "Portfolio line roster hash"))
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at, field="Portfolio recorded_at"))
        if self.recorded_at < self.prepared.opportunity_set_recorded_at:
            raise ValueError("PortfolioProposal cannot precede OpportunitySet")
        if self.included_count + self.excluded_count + self.not_estimable_count != len(self.lines):
            raise ValueError("Portfolio line states do not reconcile")
        for name in ("gross_weight", "net_weight", "cash_weight", "turnover_weight"):
            _ratio(getattr(self, name), name)
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "cash_weight": self.cash_weight,
            "decision_run_id": self.prepared.decision_run_id,
            "excluded_count": self.excluded_count,
            "gross_weight": self.gross_weight,
            "included_count": self.included_count,
            "line_count": len(self.lines),
            "line_roster_sha256": self.line_roster_sha256,
            "net_weight": self.net_weight,
            "not_estimable_count": self.not_estimable_count,
            "portfolio_policy_id": self.policy.portfolio_policy_id,
            "portfolio_proposal_id": self.portfolio_proposal_id,
            "request_identity": self.request_identity,
            "request_sha256": self.request_sha256,
            "status": self.status,
            "turnover_weight": self.turnover_weight,
        }))


def build_portfolio_proposal(
    *,
    portfolio_proposal_id: UUID,
    prepared: PreparedPortfolioInputs,
    policy: PortfolioPolicyPlan,
    request_identity: str,
    request_sha256: str,
    command_receipt_id: UUID,
    recorded_at: datetime,
    line_id_factory: Callable[[PreparedPortfolioOpportunity], UUID],
) -> PortfolioProposalAuthority:
    request_sha256 = _sha(request_sha256, "Portfolio request hash")
    actionable = tuple(item for item in prepared.opportunities if item.status is OpportunityStatus.ACTIONABLE)
    estimable_count = sum(item.status is not OpportunityStatus.NOT_ESTIMABLE for item in prepared.opportunities)
    selected = actionable[: policy.maximum_line_count] if estimable_count >= policy.minimum_estimable_count else ()
    if estimable_count < policy.minimum_estimable_count:
        proposal_status = PortfolioProposalStatus.NOT_ESTIMABLE
    elif not selected:
        proposal_status = PortfolioProposalStatus.NO_ACTION
    else:
        proposal_status = PortfolioProposalStatus.PROPOSED
    quantum = Decimal(1).scaleb(-policy.decimal_places)
    gross_cap = min(
        policy.maximum_gross_weight,
        policy.maximum_net_weight,
        policy.maximum_turnover,
        Decimal("1") - policy.minimum_cash_weight,
    )
    raw_weight = min(policy.maximum_single_weight, gross_cap / len(selected)) if selected else Decimal("0")
    base_weight = raw_weight.quantize(quantum, rounding=ROUND_DOWN)
    selected_ids = {item.opportunity_id for item in selected}
    lines: list[PortfolioLinePlan] = []
    remaining = gross_cap - base_weight * len(selected)
    for ordinal, item in enumerate(prepared.opportunities, start=1):
        if proposal_status is PortfolioProposalStatus.NOT_ESTIMABLE:
            status, weight, reason = PortfolioLineStatus.NOT_ESTIMABLE, Decimal("0"), "PROPOSAL_NOT_ESTIMABLE"
        elif item.opportunity_id not in selected_ids:
            status, weight, reason = PortfolioLineStatus.EXCLUDED, Decimal("0"), "OPPORTUNITY_NOT_INCLUDED"
        else:
            extra = min(quantum, remaining, policy.maximum_single_weight - base_weight)
            weight = base_weight + extra
            remaining -= extra
            status, reason = PortfolioLineStatus.INCLUDED, "EQUAL_WEIGHT_ACTIONABLE"
        lines.append(PortfolioLinePlan(
            portfolio_line_id=line_id_factory(item), ordinal=ordinal, source=item,
            status=status, proposed_weight=weight, reason_code=reason,
        ))
    line_tuple = tuple(lines)
    gross = sum((item.proposed_weight for item in line_tuple), Decimal("0"))
    roster_hash = canonical_json_sha256(tuple({
        "content_sha256": item.content_sha256,
        "ordinal": item.ordinal,
        "portfolio_line_id": item.portfolio_line_id,
    } for item in line_tuple))
    return PortfolioProposalAuthority(
        portfolio_proposal_id=portfolio_proposal_id,
        prepared=prepared,
        policy=policy,
        status=proposal_status,
        lines=line_tuple,
        line_roster_sha256=roster_hash,
        included_count=sum(item.status is PortfolioLineStatus.INCLUDED for item in line_tuple),
        excluded_count=sum(item.status is PortfolioLineStatus.EXCLUDED for item in line_tuple),
        not_estimable_count=sum(item.status is PortfolioLineStatus.NOT_ESTIMABLE for item in line_tuple),
        gross_weight=gross,
        net_weight=gross,
        cash_weight=Decimal("1") - gross,
        turnover_weight=gross,
        request_identity=request_identity,
        request_sha256=request_sha256,
        command_receipt_id=command_receipt_id,
        recorded_at=recorded_at,
    )


__all__ = [
    "PortfolioAllocationMethod", "PortfolioLinePlan", "PortfolioLineStatus",
    "PortfolioPolicyPlan", "PortfolioProposalAuthority",
    "PortfolioProposalStatus", "PreparedPortfolioInputs",
    "PreparedPortfolioOpportunity", "build_portfolio_proposal",
]
