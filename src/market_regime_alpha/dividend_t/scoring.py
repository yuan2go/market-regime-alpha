"""Scoring functions for the long-term dividend T-trading model."""

from __future__ import annotations

from market_regime_alpha.dividend_t.models import (
    FundamentalInputs,
    RetreatInputs,
    ScoreBreakdown,
    TechnicalInputs,
)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def fundamental_score(inputs: FundamentalInputs) -> float:
    return clamp(
        0.25 * inputs.dividend_sustainability
        + 0.20 * inputs.valuation_margin
        + 0.20 * inputs.cycle_prosperity
        + 0.20 * inputs.financial_quality
        + 0.15 * inputs.catalyst_stability,
        0.0,
        100.0,
    )


def base_position_limit(f_score: float) -> float:
    if f_score >= 60:
        return 0.10
    if f_score >= 50:
        return 0.05
    return 0.0


def fundamental_grade(f_score: float) -> str:
    if f_score >= 80:
        return "优质底仓"
    if f_score >= 70:
        return "合格底仓"
    if f_score >= 60:
        return "观察底仓"
    if f_score >= 50:
        return "弱底仓"
    return "不合格"


def risk_reward_score(ratio: float) -> float:
    if ratio >= 3.0:
        return 5.0
    if ratio >= 2.5:
        return 4.5
    if ratio >= 2.0:
        return 4.0
    if ratio >= 1.5:
        return 3.0
    if ratio >= 1.0:
        return 2.0
    if ratio > 0:
        return 1.0
    return 0.0


def retreat_score(inputs: RetreatInputs) -> tuple[float, float]:
    g_score = clamp(inputs.market_attention, 0.0, 5.0)
    z_score = clamp(inputs.upside_certainty, 0.0, 5.0)
    k_score = risk_reward_score(inputs.risk_reward_ratio)
    s_score = clamp(inputs.sell_pressure, 0.0, 5.0)
    raw_score = 0.25 * g_score + 0.30 * z_score + 0.25 * k_score + 0.20 * (5.0 - s_score)
    return clamp(raw_score * 20.0, 0.0, 100.0), k_score


def technical_score(inputs: TechnicalInputs) -> float:
    return clamp(
        0.28 * inputs.position_quality
        + 0.20 * inputs.volume_structure
        + 0.17 * inputs.trend_quality
        + 0.15 * inputs.intraday_support
        + 0.20 * inputs.chan_score,
        0.0,
        100.0,
    )


def build_score_breakdown(
    fundamental: FundamentalInputs,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
) -> ScoreBreakdown:
    f_score = fundamental_score(fundamental)
    r_score, k_score = retreat_score(retreat)
    t_score = technical_score(technical)
    total_score = clamp(0.35 * f_score + 0.35 * r_score + 0.30 * t_score, 0.0, 100.0)
    return ScoreBreakdown(
        F_score=round(f_score, 2),
        G_score=round(clamp(retreat.market_attention, 0.0, 5.0), 2),
        Z_score=round(clamp(retreat.upside_certainty, 0.0, 5.0), 2),
        K_score=round(k_score, 2),
        S_score=round(clamp(retreat.sell_pressure, 0.0, 5.0), 2),
        R_score=round(r_score, 2),
        T_score=round(t_score, 2),
        total_score=round(total_score, 2),
        C_score=round(clamp(technical.chan_score, 0.0, 100.0), 2),
    )
