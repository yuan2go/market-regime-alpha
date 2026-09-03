"""Machine-derived exploratory Alpha funnel diagnosis read model.

The result is intentionally diagnostic rather than Authority.  Every rate keeps
its denominator so an empty downstream layer cannot masquerade as zero return.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class AlphaLossStage(StrEnum):
    DATA = "DATA"
    FEATURE = "FEATURE"
    CANDIDATE = "CANDIDATE"
    CONTEXT = "CONTEXT"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"
    PORTFOLIO = "PORTFOLIO"
    RISK = "RISK"
    ECONOMICS = "ECONOMICS"
    NOT_DETERMINED = "NOT_DETERMINED"


@dataclass(frozen=True, slots=True)
class FunnelRate:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("funnel counts cannot be negative")
        if self.numerator > self.denominator:
            raise ValueError("funnel numerator cannot exceed its denominator")

    @property
    def value(self) -> Decimal | None:
        if self.denominator == 0:
            return None
        return Decimal(self.numerator) / Decimal(self.denominator)


@dataclass(frozen=True, slots=True)
class AlphaFunnelDiagnosisInputs:
    dataset: FunnelRate
    feature: FunnelRate
    candidate_score: FunnelRate
    candidate_selected: FunnelRate
    candidate_rank_ic: Decimal | None
    context_pass: FunnelRate
    signal_current: FunnelRate
    signal_observational: FunnelRate
    forecast: FunnelRate
    opportunity: FunnelRate
    portfolio_exposed: FunnelRate
    risk_rejected: FunnelRate
    assumed_cost_net_return: Decimal | None


def diagnose_alpha_loss(inputs: AlphaFunnelDiagnosisInputs) -> AlphaLossStage:
    """Return the first empirically non-estimable or closed funnel layer."""

    if inputs.dataset.value in {None, Decimal(0)}:
        return AlphaLossStage.DATA
    if inputs.feature.value in {None, Decimal(0)}:
        return AlphaLossStage.FEATURE
    if (
        inputs.candidate_score.value in {None, Decimal(0)}
        or inputs.candidate_selected.value in {None, Decimal(0)}
        or inputs.candidate_rank_ic is None
    ):
        return AlphaLossStage.CANDIDATE
    if (
        inputs.context_pass.value == 0
        and inputs.signal_current.value == 0
        and inputs.signal_observational.value not in {None, Decimal(0)}
    ):
        return AlphaLossStage.CONTEXT
    if inputs.signal_current.value in {None, Decimal(0)}:
        return AlphaLossStage.SIGNAL
    if inputs.forecast.value in {None, Decimal(0)}:
        return AlphaLossStage.FORECAST
    if inputs.opportunity.value not in {None, Decimal(0)} and inputs.portfolio_exposed.value == 0:
        return AlphaLossStage.PORTFOLIO
    if (
        inputs.portfolio_exposed.value not in {None, Decimal(0)}
        and inputs.risk_rejected.value == 1
    ):
        return AlphaLossStage.RISK
    if (
        inputs.portfolio_exposed.value not in {None, Decimal(0)}
        and inputs.assumed_cost_net_return is not None
        and inputs.assumed_cost_net_return <= 0
    ):
        return AlphaLossStage.ECONOMICS
    return AlphaLossStage.NOT_DETERMINED
