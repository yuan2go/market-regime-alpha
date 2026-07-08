"""COSCO Shipping Holdings A-share profile for the first single-stock monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


COSCO_A_SYMBOL = "601919.SH"


@dataclass(frozen=True)
class CoscoProfile:
    symbol: str = COSCO_A_SYMBOL
    name: str = "中远海控"
    industry: str = "航运"
    is_cycle_stock: bool = True
    base_fundamental_score: float = 72.0
    dividend_sustainability_score: float = 72.0
    valuation_margin_score: float = 70.0
    cycle_prosperity_score: float = 68.0
    financial_quality_score: float = 74.0
    catalyst_stability_score: float = 66.0
    max_single_trade_pct: float = 0.10
    preferred_interval_minutes: int = 5
    default_base_position_pct: float = 0.10
    default_t_trade_pct: float = 0.10
    defensive_base_position_pct: float = 0.05
    range_base_position_pct: float = 0.10
    strong_trend_base_position_pct: float = 0.10
    strong_trend_t_trade_pct: float = 0.80
    buy_force_threshold: float = 0.98
    early_buy_force_threshold: float = 1.08
    buy_certainty_threshold: float = 50.0
    buy_sell_pressure_max: float = 78.0
    early_buy_sell_pressure_max: float = 70.0
    support_atr_width: float = 1.10
    sell_force_threshold: float = 0.78
    sell_pressure_threshold: float = 78.0
    strong_trend_sell_pressure_threshold: float = 80.0
    reverse_buyback_atr_offset: float = 0.25
    probe_buy_strength_threshold: float = 66.0
    fundamental_position_weight: float = 0.35
    fundamental_source: str = "industry_profile"
    fundamental_as_of: str | None = None
    fundamental_notes: tuple[str, ...] = field(default_factory=tuple)
    fundamental_metrics: dict[str, float | str | None] = field(default_factory=dict)

    @property
    def range_max_total_position_pct(self) -> float:
        return self.default_t_trade_pct

    @property
    def strong_trend_max_total_position_pct(self) -> float:
        return self.strong_trend_t_trade_pct


@dataclass(frozen=True)
class IndustryProfileDefaults:
    base_fundamental_score: float
    dividend_sustainability_score: float
    valuation_margin_score: float
    cycle_prosperity_score: float
    financial_quality_score: float
    catalyst_stability_score: float
    default_base_position_pct: float
    default_t_trade_pct: float
    buy_force_threshold: float
    early_buy_force_threshold: float
    buy_certainty_threshold: float
    buy_sell_pressure_max: float
    early_buy_sell_pressure_max: float
    support_atr_width: float
    sell_pressure_threshold: float
    strong_trend_sell_pressure_threshold: float
    reverse_buyback_atr_offset: float


INDUSTRY_DEFAULTS: dict[str, IndustryProfileDefaults] = {
    "航运": IndustryProfileDefaults(70, 68, 72, 64, 74, 66, 0.10, 0.12, 0.98, 1.08, 50, 78, 70, 1.25, 78, 80, 0.35),
    "煤炭": IndustryProfileDefaults(76, 82, 74, 70, 78, 72, 0.10, 0.10, 0.99, 1.10, 51, 77, 69, 1.15, 78, 80, 0.30),
    "电力": IndustryProfileDefaults(80, 82, 76, 78, 80, 76, 0.10, 0.07, 0.96, 1.06, 50, 78, 70, 1.05, 76, 78, 0.22),
    "银行": IndustryProfileDefaults(78, 80, 78, 72, 80, 72, 0.10, 0.07, 0.96, 1.06, 50, 78, 70, 1.05, 76, 78, 0.20),
    "运营商": IndustryProfileDefaults(79, 80, 76, 76, 80, 74, 0.10, 0.08, 0.96, 1.06, 50, 78, 70, 1.05, 76, 78, 0.22),
    "港口": IndustryProfileDefaults(73, 76, 72, 70, 76, 70, 0.10, 0.10, 0.98, 1.09, 51, 77, 69, 1.15, 78, 80, 0.28),
    "高速公路": IndustryProfileDefaults(80, 82, 76, 78, 82, 74, 0.10, 0.06, 0.96, 1.05, 50, 78, 70, 1.00, 76, 78, 0.20),
    "铁路运输": IndustryProfileDefaults(74, 76, 72, 68, 76, 70, 0.10, 0.08, 0.98, 1.08, 51, 77, 69, 1.10, 78, 80, 0.25),
    "石油石化": IndustryProfileDefaults(70, 72, 74, 62, 74, 68, 0.10, 0.10, 1.00, 1.12, 52, 76, 68, 1.20, 78, 80, 0.32),
    "消费": IndustryProfileDefaults(82, 78, 66, 78, 88, 80, 0.10, 0.05, 0.96, 1.05, 50, 78, 70, 1.00, 76, 78, 0.18),
}


def build_stock_profile(
    *,
    symbol: str,
    name: str,
    industry: str,
    is_cycle_stock: bool,
) -> CoscoProfile:
    defaults = INDUSTRY_DEFAULTS.get(industry, INDUSTRY_DEFAULTS["航运"])
    return CoscoProfile(
        symbol=symbol,
        name=name,
        industry=industry,
        is_cycle_stock=is_cycle_stock,
        base_fundamental_score=defaults.base_fundamental_score,
        dividend_sustainability_score=defaults.dividend_sustainability_score,
        valuation_margin_score=defaults.valuation_margin_score,
        cycle_prosperity_score=defaults.cycle_prosperity_score,
        financial_quality_score=defaults.financial_quality_score,
        catalyst_stability_score=defaults.catalyst_stability_score,
        max_single_trade_pct=defaults.default_t_trade_pct,
        default_base_position_pct=defaults.default_base_position_pct,
        default_t_trade_pct=defaults.default_t_trade_pct,
        buy_force_threshold=defaults.buy_force_threshold,
        early_buy_force_threshold=defaults.early_buy_force_threshold,
        buy_certainty_threshold=defaults.buy_certainty_threshold,
        buy_sell_pressure_max=defaults.buy_sell_pressure_max,
        early_buy_sell_pressure_max=defaults.early_buy_sell_pressure_max,
        support_atr_width=defaults.support_atr_width,
        sell_pressure_threshold=defaults.sell_pressure_threshold,
        strong_trend_sell_pressure_threshold=defaults.strong_trend_sell_pressure_threshold,
        reverse_buyback_atr_offset=defaults.reverse_buyback_atr_offset,
    )


def profile_for_watchlist_item(item: Any) -> CoscoProfile:
    return build_stock_profile(
        symbol=item.symbol,
        name=item.name,
        industry=item.industry,
        is_cycle_stock=item.is_cycle_stock,
    )
