"""Scoring functions for the long-term dividend T-trading model."""

from __future__ import annotations

from dataclasses import dataclass
import math

from market_regime_alpha.dividend_t.models import (
    FundamentalInputs,
    RetreatInputs,
    ScoreBreakdown,
    TechnicalInputs,
)


TECHNICAL_SCORE_VERSION = "technical-score-macd-v1"
LEGACY_TECHNICAL_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("position_quality", 0.28),
    ("volume_structure", 0.20),
    ("trend_quality", 0.17),
    ("intraday_support", 0.15),
    ("chan_score", 0.20),
)


@dataclass(frozen=True)
class TechnicalScoreDiagnostics:
    technical_score_without_macd: float
    technical_score_with_macd: float
    effective_weights: tuple[tuple[str, float], ...]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def normalize_score(value: float) -> float:
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("technical score components must be finite")
    return clamp(normalized, 0.0, 100.0)


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
    return clamp(sum(normalize_score(getattr(inputs, name)) * weight for name, weight in LEGACY_TECHNICAL_WEIGHTS), 0.0, 100.0)


def technical_score_diagnostics(inputs: TechnicalInputs, *, macd_weight: float) -> TechnicalScoreDiagnostics:
    weight = float(macd_weight)
    if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
        raise ValueError("macd_weight must be finite and in [0, 1]")
    legacy = technical_score(inputs)
    if not inputs.macd_data_ready or weight == 0.0:
        return TechnicalScoreDiagnostics(legacy, legacy, LEGACY_TECHNICAL_WEIGHTS)
    scaled = tuple((name, component_weight * (1.0 - weight)) for name, component_weight in LEGACY_TECHNICAL_WEIGHTS)
    effective = (*scaled, ("macd_score", weight))
    if not math.isclose(sum(component_weight for _, component_weight in effective), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("technical score weights must sum to 1")
    weighted = sum(normalize_score(getattr(inputs, name)) * component_weight for name, component_weight in effective)
    return TechnicalScoreDiagnostics(legacy, clamp(weighted, 0.0, 100.0), effective)


def build_score_breakdown(
    fundamental: FundamentalInputs,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
    *,
    macd_weight: float = 0.0,
) -> ScoreBreakdown:
    diagnostics = technical_score_diagnostics(technical, macd_weight=macd_weight)
    return build_score_breakdown_with_t_score(
        fundamental,
        retreat,
        technical,
        t_score=diagnostics.technical_score_with_macd,
    )


def build_score_breakdown_with_t_score(
    fundamental: FundamentalInputs,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
    *,
    t_score: float,
) -> ScoreBreakdown:
    f_score = fundamental_score(fundamental)
    r_score, k_score = retreat_score(retreat)
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
