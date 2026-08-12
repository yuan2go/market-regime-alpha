"""Deterministic Portfolio Risk V1 for Strategy Shadow research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
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


class PortfolioRiskMode(str, Enum):
    EXPLORATORY = "EXPLORATORY"
    FORMAL = "FORMAL"


class MembershipEvidenceStatus(str, Enum):
    PIT_QUALIFIED = "PIT_QUALIFIED"
    EXPLORATORY = "EXPLORATORY"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PortfolioRiskCandidate:
    symbol: str
    score: Decimal
    volatility: Decimal
    adv20: Decimal
    theme: str
    industry: str
    correlation_cluster: str
    membership_evidence: MembershipEvidenceStatus

    def __post_init__(self) -> None:
        require_text("Portfolio Risk symbol", self.symbol)
        require_text("Portfolio Risk theme", self.theme)
        require_text("Portfolio Risk industry", self.industry)
        require_text("Portfolio Risk correlation cluster", self.correlation_cluster)
        if not self.score.is_finite():
            raise ValueError("Portfolio Risk score must be finite")
        if not self.volatility.is_finite() or self.volatility <= 0:
            raise ValueError("Portfolio Risk volatility must be positive")
        if not self.adv20.is_finite() or self.adv20 < 0:
            raise ValueError("Portfolio Risk ADV20 must be non-negative")


@dataclass(frozen=True, slots=True)
class PortfolioRiskResearchPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    single_name_max_weight: Decimal
    theme_max_weight: Decimal
    industry_max_weight: Decimal
    correlation_cluster_max_weight: Decimal
    minimum_adv20: Decimal
    maximum_participation_rate: Decimal
    volatility_budget: Decimal
    cash_reserve: Decimal
    drawdown_reduction_threshold: Decimal
    drawdown_exposure_multiplier: Decimal
    created_at: datetime
    schema_version: str = "portfolio-risk-research-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        for label, value in (
            ("single_name_max_weight", self.single_name_max_weight),
            ("theme_max_weight", self.theme_max_weight),
            ("industry_max_weight", self.industry_max_weight),
            ("correlation_cluster_max_weight", self.correlation_cluster_max_weight),
            ("maximum_participation_rate", self.maximum_participation_rate),
            ("volatility_budget", self.volatility_budget),
            ("drawdown_exposure_multiplier", self.drawdown_exposure_multiplier),
        ):
            if not Decimal("0") < value <= Decimal("1"):
                raise ValueError(f"{label} must be within (0, 1]")
        if not Decimal("0") <= self.cash_reserve < Decimal("1"):
            raise ValueError("cash_reserve must be within [0, 1)")
        if self.minimum_adv20 < 0:
            raise ValueError("minimum_adv20 cannot be negative")
        if not Decimal("-1") < self.drawdown_reduction_threshold < Decimal("0"):
            raise ValueError("drawdown reduction threshold must be within (-1, 0)")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Portfolio Risk Research Policy hash mismatch")

    @classmethod
    def create(cls, **values: Any) -> PortfolioRiskResearchPolicy:
        require_text("policy_version", str(values["policy_version"]))
        payload = {
            "schema_version": "portfolio-risk-research-policy/v1",
            **{
                key: (
                    timestamp(value)
                    if key == "created_at"
                    else str(value)
                )
                for key, value in values.items()
            },
        }
        policy_id, digest = content_identity("portfolio-risk-research-policy", payload)
        return cls(policy_id=policy_id, policy_hash=digest, **values)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "single_name_max_weight": str(self.single_name_max_weight),
            "theme_max_weight": str(self.theme_max_weight),
            "industry_max_weight": str(self.industry_max_weight),
            "correlation_cluster_max_weight": str(
                self.correlation_cluster_max_weight
            ),
            "minimum_adv20": str(self.minimum_adv20),
            "maximum_participation_rate": str(self.maximum_participation_rate),
            "volatility_budget": str(self.volatility_budget),
            "cash_reserve": str(self.cash_reserve),
            "drawdown_reduction_threshold": str(
                self.drawdown_reduction_threshold
            ),
            "drawdown_exposure_multiplier": str(
                self.drawdown_exposure_multiplier
            ),
            "created_at": timestamp(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class PortfolioRiskAllocation:
    symbol: str
    weight: Decimal
    notional: Decimal
    capacity_notional: Decimal
    theme: str
    industry: str
    correlation_cluster: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "weight": str(self.weight),
            "notional": str(self.notional),
            "capacity_notional": str(self.capacity_notional),
            "theme": self.theme,
            "industry": self.industry,
            "correlation_cluster": self.correlation_cluster,
        }


@dataclass(frozen=True, slots=True)
class PortfolioRiskResearchResult:
    result_id: ArtifactId
    result_hash: str
    policy_reference: ValidationArtifactReference
    source_policy_reference: ValidationArtifactReference
    mode: PortfolioRiskMode
    portfolio_nav: Decimal
    current_drawdown: Decimal
    allocations: tuple[PortfolioRiskAllocation, ...]
    invested_weight: Decimal
    cash_weight: Decimal
    portfolio_adv_capacity: Decimal
    formal_membership_qualified: bool
    rejected_symbols: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]
    constructed_at: datetime
    authority: ResearchEvidenceAuthority
    limitations: tuple[str, ...]
    schema_version: str = "portfolio-risk-research-result/v1"

    def __post_init__(self) -> None:
        require_sha256("result_hash", self.result_hash)
        if self.invested_weight + self.cash_weight != Decimal("1"):
            raise ValueError("Portfolio Risk weights must reconcile to one")
        if self.authority is not ResearchEvidenceAuthority.EXPLORATORY:
            raise ValueError("Portfolio Risk Research result is exploratory only")
        if self.mode is PortfolioRiskMode.FORMAL and not self.formal_membership_qualified:
            raise ValueError("Formal Portfolio Risk requires PIT-qualified membership")
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Portfolio Risk Research Result hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _result_payload(
            self.policy_reference,
            self.source_policy_reference,
            self.mode,
            self.portfolio_nav,
            self.current_drawdown,
            self.allocations,
            self.invested_weight,
            self.cash_weight,
            self.portfolio_adv_capacity,
            self.formal_membership_qualified,
            self.rejected_symbols,
            self.reason_codes,
            self.constructed_at,
            self.limitations,
        )


def construct_risk_constrained_portfolio(
    *,
    policy: PortfolioRiskResearchPolicy,
    source_policy_reference: ValidationArtifactReference,
    candidates: tuple[PortfolioRiskCandidate, ...],
    portfolio_nav: Decimal,
    current_drawdown: Decimal,
    mode: PortfolioRiskMode,
    constructed_at: datetime,
) -> PortfolioRiskResearchResult:
    if portfolio_nav <= 0:
        raise ValueError("Portfolio NAV must be positive")
    if not Decimal("-1") < current_drawdown <= Decimal("0"):
        raise ValueError("Portfolio drawdown must be within (-1, 0]")
    if tuple(item.symbol for item in candidates) != tuple(
        sorted({item.symbol for item in candidates})
    ):
        raise ValueError("Portfolio Risk candidates must be unique and sorted")
    membership_qualified = all(
        item.membership_evidence is MembershipEvidenceStatus.PIT_QUALIFIED
        for item in candidates
    )
    if mode is PortfolioRiskMode.FORMAL and not membership_qualified:
        raise ValueError("Formal Portfolio Risk requires PIT-qualified membership")
    target_invested = Decimal("1") - policy.cash_reserve
    reasons: set[str] = set()
    if current_drawdown <= policy.drawdown_reduction_threshold:
        target_invested *= policy.drawdown_exposure_multiplier
        reasons.add("DRAWDOWN_EXPOSURE_REDUCED")
    ordered = sorted(candidates, key=lambda item: (-item.score, item.symbol))
    theme_weights: dict[str, Decimal] = {}
    industry_weights: dict[str, Decimal] = {}
    cluster_weights: dict[str, Decimal] = {}
    allocations: list[PortfolioRiskAllocation] = []
    rejected: list[tuple[str, str]] = []
    invested = Decimal("0")
    volatility_used = Decimal("0")
    for candidate in ordered:
        if candidate.adv20 < policy.minimum_adv20:
            rejected.append((candidate.symbol, "ADV20_BELOW_MINIMUM"))
            continue
        capacity_notional = candidate.adv20 * policy.maximum_participation_rate
        capacity_weight = capacity_notional / portfolio_nav
        available_weight = min(
            policy.single_name_max_weight,
            target_invested - invested,
            policy.theme_max_weight - theme_weights.get(candidate.theme, Decimal("0")),
            policy.industry_max_weight
            - industry_weights.get(candidate.industry, Decimal("0")),
            policy.correlation_cluster_max_weight
            - cluster_weights.get(candidate.correlation_cluster, Decimal("0")),
            capacity_weight,
            (policy.volatility_budget - volatility_used) / candidate.volatility,
        )
        if available_weight <= 0:
            rejected.append((candidate.symbol, "RISK_OR_CAPACITY_BUDGET_EXHAUSTED"))
            continue
        allocations.append(
            PortfolioRiskAllocation(
                candidate.symbol,
                available_weight,
                available_weight * portfolio_nav,
                capacity_notional,
                candidate.theme,
                candidate.industry,
                candidate.correlation_cluster,
            )
        )
        invested += available_weight
        volatility_used += available_weight * candidate.volatility
        theme_weights[candidate.theme] = (
            theme_weights.get(candidate.theme, Decimal("0")) + available_weight
        )
        industry_weights[candidate.industry] = (
            industry_weights.get(candidate.industry, Decimal("0"))
            + available_weight
        )
        cluster_weights[candidate.correlation_cluster] = (
            cluster_weights.get(candidate.correlation_cluster, Decimal("0"))
            + available_weight
        )
        if invested >= target_invested:
            break
    if not membership_qualified:
        reasons.add("MEMBERSHIP_EXPLORATORY_NOT_FORMAL")
    if invested < target_invested:
        reasons.add("TARGET_EXPOSURE_CONSTRAINED")
    limitations = tuple(
        sorted(
            {
                *ENGINEERING_LIMITATIONS,
                "EXPLORATORY_PORTFOLIO_RESEARCH",
                "NO_OPTIMIZER",
                "NO_REAL_POSITION",
                "SECTOR_MEMBERSHIP_FORMALITY_RECORDED_EXPLICITLY",
            }
        )
    )
    policy_reference = ValidationArtifactReference(
        "PORTFOLIO_RISK_RESEARCH_POLICY", policy.policy_id, policy.policy_hash
    )
    portfolio_capacity = sum(
        (item.adv20 * policy.maximum_participation_rate for item in candidates),
        Decimal("0"),
    )
    values = _result_payload(
        policy_reference,
        source_policy_reference,
        mode,
        portfolio_nav,
        current_drawdown,
        tuple(allocations),
        invested,
        Decimal("1") - invested,
        portfolio_capacity,
        membership_qualified,
        tuple(sorted(rejected)),
        tuple(sorted(reasons)),
        constructed_at,
        limitations,
    )
    result_id, digest = content_identity("portfolio-risk-research-result", values)
    return PortfolioRiskResearchResult(
        result_id,
        digest,
        policy_reference,
        source_policy_reference,
        mode,
        portfolio_nav,
        current_drawdown,
        tuple(allocations),
        invested,
        Decimal("1") - invested,
        portfolio_capacity,
        membership_qualified,
        tuple(sorted(rejected)),
        tuple(sorted(reasons)),
        constructed_at,
        ResearchEvidenceAuthority.EXPLORATORY,
        limitations,
    )


def _result_payload(
    policy_reference: ValidationArtifactReference,
    source_policy_reference: ValidationArtifactReference,
    mode: PortfolioRiskMode,
    portfolio_nav: Decimal,
    current_drawdown: Decimal,
    allocations: tuple[PortfolioRiskAllocation, ...],
    invested_weight: Decimal,
    cash_weight: Decimal,
    portfolio_adv_capacity: Decimal,
    formal_membership_qualified: bool,
    rejected_symbols: tuple[tuple[str, str], ...],
    reason_codes: tuple[str, ...],
    constructed_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "portfolio-risk-research-result/v1",
        "policy_reference": policy_reference.to_canonical_dict(),
        "source_policy_reference": source_policy_reference.to_canonical_dict(),
        "mode": mode.value,
        "portfolio_nav": str(portfolio_nav),
        "current_drawdown": str(current_drawdown),
        "allocations": [item.to_canonical_dict() for item in allocations],
        "invested_weight": str(invested_weight),
        "cash_weight": str(cash_weight),
        "portfolio_adv_capacity": str(portfolio_adv_capacity),
        "formal_membership_qualified": formal_membership_qualified,
        "rejected_symbols": [list(item) for item in rejected_symbols],
        "reason_codes": list(reason_codes),
        "constructed_at": timestamp(constructed_at),
        "authority": ResearchEvidenceAuthority.EXPLORATORY.value,
        "limitations": list(limitations),
    }


__all__ = [
    "MembershipEvidenceStatus",
    "PortfolioRiskAllocation",
    "PortfolioRiskCandidate",
    "PortfolioRiskMode",
    "PortfolioRiskResearchPolicy",
    "PortfolioRiskResearchResult",
    "construct_risk_constrained_portfolio",
]
