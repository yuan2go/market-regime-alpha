#!/usr/bin/env python3
"""Train transparent screening rules and validate screened A-share portfolios."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from multiprocessing import get_context
from pathlib import Path
import sys
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import (  # noqa: E402
    BacktestSignalCache,
    DEFAULT_SIGNAL_CACHE_DIR,
    DividendTBacktestConfig,
    T_POSITION_MODES,
    load_5min_bars_path,
    run_cosco_dividend_t_backtest,
)
from market_regime_alpha.dividend_t.cosco_profile import profile_for_watchlist_item  # noqa: E402
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine  # noqa: E402
from market_regime_alpha.dividend_t.fundamentals import build_fundamental_resolver  # noqa: E402
from market_regime_alpha.dividend_t.market_environment import (  # noqa: E402
    MarketEnvironmentFilter,
    build_market_environment_filter,
)
from market_regime_alpha.dividend_t.storage import load_watchlist  # noqa: E402
from market_regime_alpha.dividend_t.strategy_modes import STRATEGY_MODES, apply_strategy_mode  # noqa: E402


DEFAULT_WATCHLIST = PROJECT_ROOT / "data" / "external" / "watchlists" / "top1000_largecap_watchlist.csv"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "top1000_largecap_5min_1y"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "top1000_screened_portfolio_walkforward.md"


def _parse_positive_int_list(value: str, *, option_name: str) -> tuple[int, ...]:
    items: list[int] = []
    for raw in str(value).split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            parsed = int(item)
        except ValueError as exc:
            raise SystemExit(f"{option_name} must be a comma-separated list of positive integers") from exc
        if parsed <= 0:
            raise SystemExit(f"{option_name} values must be positive")
        items.append(parsed)
    if not items:
        raise SystemExit(f"{option_name} must include at least one horizon")
    return tuple(sorted(set(items)))


def _parse_rule_id_list(value: str | None) -> frozenset[str] | None:
    if value is None:
        return None
    items = frozenset(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise SystemExit("--capture-bias-rule-ids must include at least one rule id")
    unknown = sorted(items.difference(RANK_RULE_COLUMNS))
    if unknown:
        raise SystemExit(f"--capture-bias-rule-ids contains unknown rank rules: {', '.join(unknown)}")
    return items


@dataclass(frozen=True)
class WindowSpec:
    window_id: str
    train_start: date
    train_end: date
    valid_start: date
    valid_end: date


@dataclass(frozen=True)
class CaptureBiasRuleConstraints:
    min_positive_rate: float | None = None
    min_upside_capture: float | None = None
    min_trend_capture_return: float | None = None
    min_risk_on_after_10d_position: float | None = None
    max_capture_shortfall: float | None = None
    max_abs_drawdown: float | None = None
    max_soft_stop_flying_rate: float | None = None
    max_risk_on_position_underbuilt: float | None = None

    @property
    def is_empty(self) -> bool:
        return all(value is None for value in asdict(self).values())


@dataclass(frozen=True)
class PeriodBacktestRow:
    symbol: str
    name: str
    industry: str
    period: str
    status: str
    rows: int = 0
    start: str = "-"
    end: str = "-"
    total_return: float | None = None
    benchmark_return: float | None = None
    risk_matched_benchmark_return: float | None = None
    excess_return: float | None = None
    max_drawdown: float | None = None
    trade_count: int = 0
    completed_trades: int = 0
    win_rate: float | None = None
    gate_count: int = 0
    buy_signal_count: int = 0
    breakout_signal_count: int = 0
    breakout_watch_count: int = 0
    risk_on_target_add_count: int = 0
    sell_signal_count: int = 0
    buyback_trade_count: int = 0
    market_caution_gate_count: int = 0
    stop_signal_count: int = 0
    defensive_mode_count: int = 0
    balanced_mode_count: int = 0
    offensive_mode_count: int = 0
    risk_on_count: int = 0
    risk_on_share: float = 0.0
    market_score_avg: float = 0.0
    market_trend_score_avg: float = 0.0
    market_breadth_score_avg: float = 0.0
    market_amount_score_avg: float = 0.0
    market_limit_structure_score_avg: float = 0.0
    market_industry_diffusion_score_avg: float = 0.0
    market_model_state_score_avg: float = 0.0
    model_holding_win_rate_avg: float = 0.0
    model_holding_profit_spread_avg: float = 0.0
    model_new_buy_success_rate_avg: float = 0.0
    beta_hold_entry_count: int = 0
    beta_hold_bar_count: int = 0
    beta_hold_share: float = 0.0
    wait_beta_hold_count: int = 0
    full_position_bar_count: int = 0
    full_position_share: float = 0.0
    risk_on_after_1d_avg_position_pct: float = 0.0
    risk_on_after_3d_avg_position_pct: float = 0.0
    risk_on_after_5d_avg_position_pct: float = 0.0
    risk_on_after_10d_avg_position_pct: float = 0.0
    strong_confirm_episode_count: int = 0
    strong_confirm_to_exit_avg_bars: float = 0.0
    beta_hold_episode_avg_bars: float = 0.0
    avg_total_position_pct: float = 0.0
    max_total_position_pct_realized: float = 0.0
    avg_active_position_pct: float = 0.0
    max_active_position_pct: float = 0.0
    buy3_count: int = 0
    breakout_confirmed_count: int = 0
    confirmed_flow_count: int = 0
    confirmed_flow_share: float = 0.0
    avg_force_ratio: float = 0.0
    avg_buy_force_ratio: float = 0.0
    force_suppression_count: int = 0
    force_suppression_share: float = 0.0
    volume_price_score_avg: float = 0.0
    volume_breakout_count: int = 0
    low_volume_pullback_count: int = 0
    high_volume_stall_count: int = 0
    price_up_volume_down_count: int = 0
    vwap_support_count: int = 0
    post_breakout_volume_persistence_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    message: str = ""


@dataclass(frozen=True)
class CurvePayload:
    symbol: str
    status: str
    points: tuple[tuple[float | str, ...], ...] = ()
    trades: tuple[dict[str, object], ...] = ()
    trade_quality: tuple[dict[str, object], ...] = ()
    buy_event_study: tuple[dict[str, object], ...] = ()
    sell_event_study: tuple[dict[str, object], ...] = ()
    volume_price_window_study: tuple[dict[str, object], ...] = ()
    message: str = ""


@dataclass(frozen=True)
class RuleResult:
    window_id: str
    train_start: str
    train_end: str
    valid_start: str
    valid_end: str
    rule_id: str
    candidate_count: int
    top_n: int
    portfolio_weighting: str
    train_score: float
    train_total_return: float
    train_positive_rate: float
    train_max_drawdown: float
    train_stop_per_trade: float
    valid_total_return: float
    valid_benchmark_return: float
    valid_risk_matched_benchmark_return: float
    valid_excess_return: float
    valid_risk_matched_excess_return: float
    valid_max_drawdown: float
    valid_positive_rate: float
    valid_constituent_avg_return: float
    valid_constituent_median_return: float
    signal_quantile: float
    offensive_quantile: float
    trend_quantile: float
    capture_quantile: float
    drawdown_quantile: float
    stop_quantile: float


@dataclass(frozen=True)
class WindowRunResult:
    window: WindowSpec
    train_frame: pd.DataFrame
    valid_frame: pd.DataFrame
    ranked: pd.DataFrame
    rules: pd.DataFrame
    portfolio_rows: list[RuleResult]
    trades: pd.DataFrame
    trade_quality: pd.DataFrame
    buy_event_study: pd.DataFrame
    sell_event_study: pd.DataFrame
    volume_price_window_study: pd.DataFrame


def main() -> int:
    parser = argparse.ArgumentParser(description="Train screening rules and validate screened top1000 portfolios.")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=0, help="Limit watchlist size for smoke tests. 0 means all.")
    parser.add_argument("--walkforward-mode", choices=["rolling", "single"], default="rolling")
    parser.add_argument("--split-frac", type=float, default=0.50, help="Fraction of trade dates used for single-window training.")
    parser.add_argument("--train-days", type=int, default=120, help="Rolling walk-forward training trade days.")
    parser.add_argument("--valid-days", type=int, default=40, help="Rolling walk-forward validation trade days.")
    parser.add_argument("--step-days", type=int, default=40, help="Rolling walk-forward step size in trade days.")
    parser.add_argument("--min-valid-days", type=int, default=20, help="Minimum validation trade days for the last rolling window.")
    parser.add_argument("--initial-capital", type=float, default=500_000.0, help="Capital used to translate portfolio returns into simulated CNY PnL.")
    parser.add_argument("--top-n", nargs="*", type=int, default=[100, 150, 200])
    parser.add_argument(
        "--fixed-selected-symbols",
        default=None,
        help="Comma-separated symbols or a file/CSV path used as fixed selected candidates for A/B runs.",
    )
    parser.add_argument("--portfolio-weighting", choices=["equal", "rank-tier"], default="equal")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--worker-mode", choices=["process", "thread"], default="process")
    parser.add_argument("--strategy-mode", choices=STRATEGY_MODES, default="dynamic")
    parser.add_argument("--t-position-mode", choices=sorted(T_POSITION_MODES), default="full")
    parser.add_argument("--enable-t-sell", action="store_true", help="Opt in to ordinary T_SELL and reverse-T sell execution. Disabled by default.")
    parser.add_argument("--force-rule-id", default=None)
    parser.add_argument("--rule-selection-mode", choices=["train-objective", "capture-bias"], default="train-objective")
    parser.add_argument("--rule-selection-top-n", type=int, default=None)
    parser.add_argument(
        "--capture-bias-rule-ids",
        default=None,
        help="Comma-separated rank-rule allowlist used only by --rule-selection-mode capture-bias.",
    )
    parser.add_argument("--capture-bias-min-positive-rate", type=float, default=None)
    parser.add_argument("--capture-bias-min-upside-capture", type=float, default=None)
    parser.add_argument("--capture-bias-min-trend-capture-return", type=float, default=None)
    parser.add_argument("--capture-bias-min-risk-on-after-10d-position", type=float, default=None)
    parser.add_argument("--capture-bias-max-capture-shortfall", type=float, default=None)
    parser.add_argument("--capture-bias-max-abs-drawdown", type=float, default=None)
    parser.add_argument("--capture-bias-max-soft-stop-flying-rate", type=float, default=None)
    parser.add_argument("--capture-bias-max-risk-on-position-underbuilt", type=float, default=None)
    parser.add_argument("--market-filter", choices=["none", "equal-weight"], default="equal-weight")
    parser.add_argument("--market-filter-lookback-days", type=int, default=0)
    parser.add_argument("--fundamental-source", choices=["auto", "tushare", "profile"], default="profile")
    parser.add_argument("--candidate-entry-mode", choices=["off", "start", "start-and-confirm"], default="start-and-confirm")
    parser.add_argument("--candidate-entry-start-target-pct", type=float, default=0.70)
    parser.add_argument("--candidate-entry-start-max-bars", type=int, default=48)
    parser.add_argument("--candidate-entry-confirm-target-pct", type=float, default=1.00)
    parser.add_argument("--candidate-entry-confirm-min-strength", type=float, default=64.0)
    parser.add_argument("--candidate-entry-confirm-min-confirmations", type=int, default=2)
    parser.add_argument("--candidate-entry-confirm-probe-target-pct", type=float, default=None)
    parser.add_argument("--disable-candidate-entry-confirm-follow-through", action="store_true")
    parser.add_argument("--disable-candidate-entry-confirm-market-passthrough", action="store_true")
    parser.add_argument("--candidate-entry-min-hold-bars", type=int, default=1920)
    parser.add_argument("--candidate-entry-hard-stop-loss-pct", type=float, default=0.10)
    parser.add_argument("--risk-on-target-add-min-target-pct", type=float, default=None)
    parser.add_argument("--risk-on-target-add-bonus-pct", type=float, default=None)
    parser.add_argument("--risk-on-first-add-cap-pct", type=float, default=None)
    parser.add_argument("--risk-on-low-position-add-cap-pct", type=float, default=None)
    parser.add_argument("--risk-on-mid-position-add-cap-pct", type=float, default=None)
    parser.add_argument("--risk-on-high-quality-breakout-upgrade-target-pct", type=float, default=None)
    parser.add_argument("--enable-risk-on-high-position-reinforcement", action="store_true")
    parser.add_argument("--risk-on-high-position-reinforce-cap-pct", type=float, default=None)
    parser.add_argument("--risk-on-full-add-min-quality-score", type=float, default=None)
    parser.add_argument("--risk-on-full-add-min-main-rise-quality-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-quality-buffer", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-main-rise-quality-buffer", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-min-vwap-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-min-volume-price-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-min-volume-breakout-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-min-volume-persistence-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-min-flow-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-max-sell-pressure-score", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-max-down-probability-1d", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-max-down-probability-3d", type=float, default=None)
    parser.add_argument("--risk-on-secondary-add-min-confirmations", type=int, default=None)
    parser.add_argument("--risk-on-beta-hold-secondary-min-confirmations", type=int, default=None)
    parser.add_argument("--risk-on-add-follow-through-bars", type=int, default=None)
    parser.add_argument("--risk-on-add-follow-through-min-high-return-pct", type=float, default=None)
    parser.add_argument("--risk-on-add-follow-through-volume-ratio", type=float, default=None)
    parser.add_argument("--risk-on-add-follow-through-vwap-tolerance-pct", type=float, default=None)
    parser.add_argument("--risk-on-add-follow-through-failure-cooldown-bars", type=int, default=None)
    parser.add_argument("--volume-price-continuation-lookback-bars", type=int, default=None)
    parser.add_argument("--volume-price-continuation-min-return-pct", type=float, default=None)
    parser.add_argument("--volume-price-continuation-max-volume-ratio", type=float, default=None)
    parser.add_argument("--disable-buy-volume-price-window-filter", action="store_true")
    parser.add_argument("--buy-volume-price-short-lookback-bars", type=int, default=None)
    parser.add_argument("--buy-volume-price-mid-lookback-bars", type=int, default=None)
    parser.add_argument("--buy-volume-price-filter-min-return-pct", type=float, default=None)
    parser.add_argument("--buy-volume-price-filter-max-contract-ratio", type=float, default=None)
    parser.add_argument("--buy-volume-price-filter-min-quality-score", type=float, default=None)
    parser.add_argument("--disable-portfolio-main-rise-position-target", action="store_true")
    parser.add_argument("--portfolio-main-rise-position-target-pct", type=float, default=None)
    parser.add_argument("--portfolio-main-rise-min-model-state-score", type=float, default=None)
    parser.add_argument("--portfolio-main-rise-min-holding-win-rate", type=float, default=None)
    parser.add_argument("--portfolio-main-rise-min-profit-spread", type=float, default=None)
    parser.add_argument("--portfolio-main-rise-min-new-buy-success-rate", type=float, default=None)
    parser.add_argument("--disable-late-stage-stall-entry-filter", action="store_true")
    parser.add_argument("--late-stage-recent-high-lookback-bars", type=int, default=None)
    parser.add_argument("--late-stage-near-high-pct", type=float, default=None)
    parser.add_argument("--late-stage-stall-lookback-bars", type=int, default=None)
    parser.add_argument("--late-stage-max-stall-bars", type=int, default=None)
    parser.add_argument("--late-stage-max-upper-shadow-ratio", type=float, default=None)
    parser.add_argument("--late-stage-min-body-progress-ratio", type=float, default=None)
    parser.add_argument("--late-stage-min-range-pct", type=float, default=None)
    parser.add_argument("--breakout-follow-through-bars", type=int, default=None)
    parser.add_argument("--breakout-follow-through-min-high-return-pct", type=float, default=None)
    parser.add_argument("--breakout-follow-through-volume-ratio", type=float, default=None)
    parser.add_argument("--breakout-follow-through-failure-cooldown-bars", type=int, default=None)
    parser.add_argument("--enable-breakout-direct-buy", action="store_true")
    parser.add_argument("--breakout-direct-buy-probe-target-pct", type=float, default=None)
    parser.add_argument("--disable-breakout-direct-buy-risk-on-confirmation", action="store_true")
    parser.add_argument("--suppress-beta-hold-breakout-direct-buy", action="store_true")
    parser.add_argument("--signal-step-bars", type=int, default=24)
    parser.add_argument("--min-buy-point-quality-score", type=float, default=None)
    parser.add_argument("--min-main-rise-buy-quality-score", type=float, default=None)
    parser.add_argument("--min-breakout-buy-quality-score", type=float, default=None)
    parser.add_argument("--min-breakout-buy-main-rise-quality-score", type=float, default=None)
    parser.add_argument("--min-base-rebalance-buy-quality-score", type=float, default=None)
    parser.add_argument("--min-risk-on-add-quality-score", type=float, default=None)
    parser.add_argument("--min-risk-on-add-main-rise-quality-score", type=float, default=None)
    parser.add_argument("--buy-t-failure-cooldown-bars", type=int, default=None)
    parser.add_argument("--sell-point-continuation-quality-score", type=float, default=None)
    parser.add_argument("--export-trades", action="store_true", help="Export selected-candidate trade logs and point-quality labels.")
    parser.add_argument("--trade-quality-horizon-bars", type=int, default=48)
    parser.add_argument("--trade-quality-buy-up-threshold-pct", type=float, default=0.03)
    parser.add_argument("--trade-quality-stop-loss-threshold-pct", type=float, default=0.02)
    parser.add_argument("--trade-quality-sell-drawdown-threshold-pct", type=float, default=0.03)
    parser.add_argument("--trade-quality-sell-fly-threshold-pct", type=float, default=0.03)
    parser.add_argument("--buy-event-horizons", default="5,10,20,40", help="Comma-separated forward bar horizons for buy-point event study.")
    parser.add_argument("--sell-event-horizons", default="5,10,20,40", help="Comma-separated forward bar horizons for sell-point event study.")
    parser.add_argument(
        "--volume-price-event-windows",
        default="12,24,48,96",
        help="Comma-separated pre-trade lookback windows for volume/price sliding-window event study.",
    )
    parser.add_argument("--sell-event-drawdown-threshold-pct", type=float, default=0.03)
    parser.add_argument("--sell-event-rally-threshold-pct", type=float, default=0.03)
    parser.add_argument("--max-history-bars", type=int, default=240)
    parser.add_argument("--signal-cache-dir", type=Path, default=DEFAULT_SIGNAL_CACHE_DIR)
    parser.add_argument("--disable-offensive-volume-distribution", action="store_true")
    parser.add_argument("--offensive-volume-stall-reduce-score", type=float, default=None)
    parser.add_argument("--offensive-price-up-volume-down-reduce-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-hard-stall-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-hard-up-down-score", type=float, default=None)
    parser.add_argument(
        "--offensive-volume-distribution-min-profit-pct",
        type=float,
        default=None,
        help="Override current active-profit threshold for offensive volume-distribution reduction, e.g. 0.06.",
    )
    parser.add_argument(
        "--offensive-volume-distribution-min-peak-profit-pct",
        type=float,
        default=None,
        help="Override peak active-profit threshold for offensive volume-distribution reduction, e.g. 0.10.",
    )
    parser.add_argument("--offensive-volume-distribution-absorption-vwap-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-absorption-persistence-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-continuation-min-confirmations", type=int, default=None)
    parser.add_argument("--offensive-volume-distribution-reduce-pressure-count", type=int, default=None)
    parser.add_argument("--offensive-volume-distribution-low-vwap-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-low-persistence-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-low-flow-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-low-force-ratio", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-low-force-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-low-volume-price-score", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-sell-fraction", type=float, default=None)
    parser.add_argument("--offensive-volume-distribution-hard-sell-fraction", type=float, default=None)
    args = parser.parse_args()

    items = load_watchlist(args.watchlist)
    if not items:
        raise SystemExit(f"watchlist is empty or missing: {args.watchlist}")
    if args.limit > 0:
        items = items[: args.limit]
    top_n_values = sorted({value for value in args.top_n if value > 0})
    if not top_n_values:
        raise SystemExit("--top-n must contain at least one positive value")
    fixed_selected_symbols = _load_fixed_selected_symbols(args.fixed_selected_symbols)
    if fixed_selected_symbols and len(fixed_selected_symbols) < max(top_n_values):
        raise SystemExit("--fixed-selected-symbols must include at least max(--top-n) symbols")
    if args.rule_selection_top_n is not None and args.rule_selection_top_n not in top_n_values:
        raise SystemExit("--rule-selection-top-n must be one of --top-n values")
    rule_selection_top_n = args.rule_selection_top_n
    if rule_selection_top_n is None and args.rule_selection_mode == "capture-bias":
        rule_selection_top_n = max(top_n_values)
    capture_bias_rule_ids = _parse_rule_id_list(args.capture_bias_rule_ids)
    capture_bias_constraints = CaptureBiasRuleConstraints(
        min_positive_rate=args.capture_bias_min_positive_rate,
        min_upside_capture=args.capture_bias_min_upside_capture,
        min_trend_capture_return=args.capture_bias_min_trend_capture_return,
        min_risk_on_after_10d_position=args.capture_bias_min_risk_on_after_10d_position,
        max_capture_shortfall=args.capture_bias_max_capture_shortfall,
        max_abs_drawdown=args.capture_bias_max_abs_drawdown,
        max_soft_stop_flying_rate=args.capture_bias_max_soft_stop_flying_rate,
        max_risk_on_position_underbuilt=args.capture_bias_max_risk_on_position_underbuilt,
    )
    buy_event_horizons = _parse_positive_int_list(args.buy_event_horizons, option_name="--buy-event-horizons")
    sell_event_horizons = _parse_positive_int_list(args.sell_event_horizons, option_name="--sell-event-horizons")
    volume_price_event_windows = _parse_positive_int_list(args.volume_price_event_windows, option_name="--volume-price-event-windows")

    windows = _build_walkforward_windows(
        items,
        data_dir=args.data_dir,
        mode=args.walkforward_mode,
        split_frac=args.split_frac,
        train_days=args.train_days,
        valid_days=args.valid_days,
        step_days=args.step_days,
        min_valid_days=args.min_valid_days,
    )
    base_config = apply_strategy_mode(
        DividendTBacktestConfig(
            t_position_mode=args.t_position_mode,
            enable_t_sell=args.enable_t_sell,
            signal_step_bars=args.signal_step_bars,
            max_history_bars=args.max_history_bars,
            signal_cache_dir=args.signal_cache_dir,
        ),
        args.strategy_mode,
    )
    volume_distribution_overrides = {
        "offensive_volume_distribution_enabled": False if args.disable_offensive_volume_distribution else None,
        "offensive_volume_stall_reduce_score": args.offensive_volume_stall_reduce_score,
        "offensive_price_up_volume_down_reduce_score": args.offensive_price_up_volume_down_reduce_score,
        "offensive_volume_distribution_hard_stall_score": args.offensive_volume_distribution_hard_stall_score,
        "offensive_volume_distribution_hard_up_down_score": args.offensive_volume_distribution_hard_up_down_score,
        "offensive_volume_distribution_min_profit_pct": args.offensive_volume_distribution_min_profit_pct,
        "offensive_volume_distribution_min_peak_profit_pct": args.offensive_volume_distribution_min_peak_profit_pct,
        "offensive_volume_distribution_absorption_vwap_score": args.offensive_volume_distribution_absorption_vwap_score,
        "offensive_volume_distribution_absorption_persistence_score": args.offensive_volume_distribution_absorption_persistence_score,
        "offensive_volume_distribution_continuation_min_confirmations": args.offensive_volume_distribution_continuation_min_confirmations,
        "offensive_volume_distribution_reduce_pressure_count": args.offensive_volume_distribution_reduce_pressure_count,
        "offensive_volume_distribution_low_vwap_score": args.offensive_volume_distribution_low_vwap_score,
        "offensive_volume_distribution_low_persistence_score": args.offensive_volume_distribution_low_persistence_score,
        "offensive_volume_distribution_low_flow_score": args.offensive_volume_distribution_low_flow_score,
        "offensive_volume_distribution_low_force_ratio": args.offensive_volume_distribution_low_force_ratio,
        "offensive_volume_distribution_low_force_score": args.offensive_volume_distribution_low_force_score,
        "offensive_volume_distribution_low_volume_price_score": args.offensive_volume_distribution_low_volume_price_score,
        "offensive_volume_distribution_sell_fraction": args.offensive_volume_distribution_sell_fraction,
        "offensive_volume_distribution_hard_sell_fraction": args.offensive_volume_distribution_hard_sell_fraction,
    }
    configured_volume_distribution_overrides = {key: value for key, value in volume_distribution_overrides.items() if value is not None}
    if configured_volume_distribution_overrides:
        base_config = replace(base_config, **configured_volume_distribution_overrides)
    point_quality_overrides = {
        "min_buy_point_quality_score": args.min_buy_point_quality_score,
        "min_main_rise_buy_quality_score": args.min_main_rise_buy_quality_score,
        "min_breakout_buy_quality_score": args.min_breakout_buy_quality_score,
        "min_breakout_buy_main_rise_quality_score": args.min_breakout_buy_main_rise_quality_score,
        "min_base_rebalance_buy_quality_score": args.min_base_rebalance_buy_quality_score,
        "min_risk_on_add_quality_score": args.min_risk_on_add_quality_score,
        "min_risk_on_add_main_rise_quality_score": args.min_risk_on_add_main_rise_quality_score,
        "buy_t_failure_cooldown_bars": args.buy_t_failure_cooldown_bars,
        "sell_point_continuation_quality_score": args.sell_point_continuation_quality_score,
    }
    configured_point_quality_overrides = {key: value for key, value in point_quality_overrides.items() if value is not None}
    if configured_point_quality_overrides:
        base_config = replace(base_config, **configured_point_quality_overrides)
    buy_event_rule_overrides = {
        "candidate_entry_confirm_probe_target_pct": args.candidate_entry_confirm_probe_target_pct,
        "candidate_entry_confirm_requires_follow_through": False if args.disable_candidate_entry_confirm_follow_through else None,
        "candidate_entry_confirm_market_passthrough": False if args.disable_candidate_entry_confirm_market_passthrough else None,
        "risk_on_target_add_min_target_pct": args.risk_on_target_add_min_target_pct,
        "risk_on_target_add_bonus_pct": args.risk_on_target_add_bonus_pct,
        "risk_on_first_add_cap_pct": args.risk_on_first_add_cap_pct,
        "risk_on_low_position_add_cap_pct": args.risk_on_low_position_add_cap_pct,
        "risk_on_mid_position_add_cap_pct": args.risk_on_mid_position_add_cap_pct,
        "risk_on_high_quality_breakout_upgrade_target_pct": args.risk_on_high_quality_breakout_upgrade_target_pct,
        "enable_risk_on_high_position_reinforcement": True if args.enable_risk_on_high_position_reinforcement else None,
        "risk_on_high_position_reinforce_cap_pct": args.risk_on_high_position_reinforce_cap_pct,
        "risk_on_full_add_min_quality_score": args.risk_on_full_add_min_quality_score,
        "risk_on_full_add_min_main_rise_quality_score": args.risk_on_full_add_min_main_rise_quality_score,
        "risk_on_secondary_add_quality_buffer": args.risk_on_secondary_add_quality_buffer,
        "risk_on_secondary_add_main_rise_quality_buffer": args.risk_on_secondary_add_main_rise_quality_buffer,
        "risk_on_secondary_add_min_vwap_score": args.risk_on_secondary_add_min_vwap_score,
        "risk_on_secondary_add_min_volume_price_score": args.risk_on_secondary_add_min_volume_price_score,
        "risk_on_secondary_add_min_volume_breakout_score": args.risk_on_secondary_add_min_volume_breakout_score,
        "risk_on_secondary_add_min_volume_persistence_score": args.risk_on_secondary_add_min_volume_persistence_score,
        "risk_on_secondary_add_min_flow_score": args.risk_on_secondary_add_min_flow_score,
        "risk_on_secondary_add_max_sell_pressure_score": args.risk_on_secondary_add_max_sell_pressure_score,
        "risk_on_secondary_add_max_down_probability_1d": args.risk_on_secondary_add_max_down_probability_1d,
        "risk_on_secondary_add_max_down_probability_3d": args.risk_on_secondary_add_max_down_probability_3d,
        "risk_on_secondary_add_min_confirmations": args.risk_on_secondary_add_min_confirmations,
        "risk_on_beta_hold_secondary_min_confirmations": args.risk_on_beta_hold_secondary_min_confirmations,
        "risk_on_add_follow_through_bars": args.risk_on_add_follow_through_bars,
        "risk_on_add_follow_through_min_high_return_pct": args.risk_on_add_follow_through_min_high_return_pct,
        "risk_on_add_follow_through_volume_ratio": args.risk_on_add_follow_through_volume_ratio,
        "risk_on_add_follow_through_vwap_tolerance_pct": args.risk_on_add_follow_through_vwap_tolerance_pct,
        "risk_on_add_follow_through_failure_cooldown_bars": args.risk_on_add_follow_through_failure_cooldown_bars,
        "volume_price_continuation_lookback_bars": args.volume_price_continuation_lookback_bars,
        "volume_price_continuation_min_return_pct": args.volume_price_continuation_min_return_pct,
        "volume_price_continuation_max_volume_ratio": args.volume_price_continuation_max_volume_ratio,
        "enable_buy_volume_price_window_filter": False if args.disable_buy_volume_price_window_filter else None,
        "buy_volume_price_short_lookback_bars": args.buy_volume_price_short_lookback_bars,
        "buy_volume_price_mid_lookback_bars": args.buy_volume_price_mid_lookback_bars,
        "buy_volume_price_filter_min_return_pct": args.buy_volume_price_filter_min_return_pct,
        "buy_volume_price_filter_max_contract_ratio": args.buy_volume_price_filter_max_contract_ratio,
        "buy_volume_price_filter_min_quality_score": args.buy_volume_price_filter_min_quality_score,
        "enable_portfolio_main_rise_position_target": False if args.disable_portfolio_main_rise_position_target else None,
        "portfolio_main_rise_position_target_pct": args.portfolio_main_rise_position_target_pct,
        "portfolio_main_rise_min_model_state_score": args.portfolio_main_rise_min_model_state_score,
        "portfolio_main_rise_min_holding_win_rate": args.portfolio_main_rise_min_holding_win_rate,
        "portfolio_main_rise_min_profit_spread": args.portfolio_main_rise_min_profit_spread,
        "portfolio_main_rise_min_new_buy_success_rate": args.portfolio_main_rise_min_new_buy_success_rate,
        "late_stage_stall_entry_filter_enabled": False if args.disable_late_stage_stall_entry_filter else None,
        "late_stage_recent_high_lookback_bars": args.late_stage_recent_high_lookback_bars,
        "late_stage_near_high_pct": args.late_stage_near_high_pct,
        "late_stage_stall_lookback_bars": args.late_stage_stall_lookback_bars,
        "late_stage_max_stall_bars": args.late_stage_max_stall_bars,
        "late_stage_max_upper_shadow_ratio": args.late_stage_max_upper_shadow_ratio,
        "late_stage_min_body_progress_ratio": args.late_stage_min_body_progress_ratio,
        "late_stage_min_range_pct": args.late_stage_min_range_pct,
        "breakout_follow_through_bars": args.breakout_follow_through_bars,
        "breakout_follow_through_min_high_return_pct": args.breakout_follow_through_min_high_return_pct,
        "breakout_follow_through_volume_ratio": args.breakout_follow_through_volume_ratio,
        "breakout_follow_through_failure_cooldown_bars": args.breakout_follow_through_failure_cooldown_bars,
        "enable_breakout_direct_buy": True if args.enable_breakout_direct_buy else None,
        "breakout_direct_buy_probe_target_pct": args.breakout_direct_buy_probe_target_pct,
        "breakout_direct_buy_requires_risk_on_confirmation": False if args.disable_breakout_direct_buy_risk_on_confirmation else None,
        "suppress_beta_hold_breakout_direct_buy": True if args.suppress_beta_hold_breakout_direct_buy else None,
    }
    configured_buy_event_rule_overrides = {key: value for key, value in buy_event_rule_overrides.items() if value is not None}
    if configured_buy_event_rule_overrides:
        base_config = replace(base_config, **configured_buy_event_rule_overrides)

    print(f"walk-forward windows: {len(windows)}", flush=True)
    results = [
        _run_window(
            window,
            items=items,
            data_dir=args.data_dir,
            market_filter_mode=args.market_filter,
            market_filter_lookback_days=args.market_filter_lookback_days,
            base_config=base_config,
            force_rule_id=args.force_rule_id,
            rule_selection_mode=args.rule_selection_mode,
            rule_selection_top_n=rule_selection_top_n,
            capture_bias_rule_ids=capture_bias_rule_ids,
            capture_bias_constraints=capture_bias_constraints,
            fixed_selected_symbols=fixed_selected_symbols,
            fundamental_source=args.fundamental_source,
            top_n_values=top_n_values,
            portfolio_weighting=args.portfolio_weighting,
            candidate_entry_mode=args.candidate_entry_mode,
            candidate_entry_start_target_pct=args.candidate_entry_start_target_pct,
            candidate_entry_start_max_bars=args.candidate_entry_start_max_bars,
            candidate_entry_confirm_target_pct=args.candidate_entry_confirm_target_pct,
            candidate_entry_confirm_min_strength=args.candidate_entry_confirm_min_strength,
            candidate_entry_confirm_min_confirmations=args.candidate_entry_confirm_min_confirmations,
            candidate_entry_min_hold_bars=args.candidate_entry_min_hold_bars,
            candidate_entry_hard_stop_loss_pct=args.candidate_entry_hard_stop_loss_pct,
            export_trades=args.export_trades,
            trade_quality_horizon_bars=args.trade_quality_horizon_bars,
            trade_quality_buy_up_threshold_pct=args.trade_quality_buy_up_threshold_pct,
            trade_quality_stop_loss_threshold_pct=args.trade_quality_stop_loss_threshold_pct,
            trade_quality_sell_drawdown_threshold_pct=args.trade_quality_sell_drawdown_threshold_pct,
            trade_quality_sell_fly_threshold_pct=args.trade_quality_sell_fly_threshold_pct,
            buy_event_horizon_bars=buy_event_horizons,
            sell_event_horizon_bars=sell_event_horizons,
            volume_price_event_window_bars=volume_price_event_windows,
            sell_event_drawdown_threshold_pct=args.sell_event_drawdown_threshold_pct,
            sell_event_rally_threshold_pct=args.sell_event_rally_threshold_pct,
            workers=args.workers,
            worker_mode=args.worker_mode,
        )
        for window in windows
    ]

    train_frame = pd.concat([result.train_frame for result in results], ignore_index=True)
    valid_frame = pd.concat([result.valid_frame for result in results], ignore_index=True)
    ranked = pd.concat([result.ranked for result in results], ignore_index=True)
    rules = pd.concat([result.rules for result in results], ignore_index=True)
    trades = _concat_optional_frames(result.trades for result in results)
    trade_quality = _concat_optional_frames(result.trade_quality for result in results)
    trade_quality_summary = _summarize_trade_quality(trade_quality, top_n_values=top_n_values) if args.export_trades else pd.DataFrame()
    buy_event_study = _concat_optional_frames(result.buy_event_study for result in results)
    buy_event_summary = _summarize_buy_event_study(buy_event_study, top_n_values=top_n_values) if args.export_trades else pd.DataFrame()
    buy_event_industry_summary = (
        _summarize_buy_event_study_by(buy_event_study, top_n_values=top_n_values, group_col="industry") if args.export_trades else pd.DataFrame()
    )
    buy_event_market_summary = (
        _summarize_buy_event_study_by(buy_event_study, top_n_values=top_n_values, group_col="market_environment_state") if args.export_trades else pd.DataFrame()
    )
    buy_event_breakout_summary = (
        _summarize_buy_event_study_by(buy_event_study, top_n_values=top_n_values, group_col="breakout_alpha_tier") if args.export_trades else pd.DataFrame()
    )
    sell_event_study = _concat_optional_frames(result.sell_event_study for result in results)
    sell_event_summary = _summarize_sell_event_study(sell_event_study, top_n_values=top_n_values) if args.export_trades else pd.DataFrame()
    sell_event_reason_summary = (
        _summarize_sell_event_study_by(sell_event_study, top_n_values=top_n_values, group_col="sell_event_type") if args.export_trades else pd.DataFrame()
    )
    sell_event_market_summary = (
        _summarize_sell_event_study_by(sell_event_study, top_n_values=top_n_values, group_col="market_environment_state") if args.export_trades else pd.DataFrame()
    )
    volume_price_window_study = _concat_optional_frames(result.volume_price_window_study for result in results)
    volume_price_window_summary = (
        _summarize_volume_price_window_study(volume_price_window_study, top_n_values=top_n_values) if args.export_trades else pd.DataFrame()
    )
    portfolio_rows = [row for result in results for row in result.portfolio_rows]
    portfolio_frame = pd.DataFrame([asdict(row) for row in portfolio_rows])
    summary_frame = _summarize_walkforward_portfolios(portfolio_frame, initial_capital=args.initial_capital)
    attribution_frame = _build_return_leakage_attribution(valid_frame, ranked)

    output_prefix = args.report.with_suffix("")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    train_path = output_prefix.with_name(f"{output_prefix.name}_train.csv")
    valid_path = output_prefix.with_name(f"{output_prefix.name}_valid.csv")
    candidates_path = output_prefix.with_name(f"{output_prefix.name}_candidates.csv")
    rules_path = output_prefix.with_name(f"{output_prefix.name}_rules.csv")
    portfolio_path = output_prefix.with_name(f"{output_prefix.name}_portfolio.csv")
    summary_path = output_prefix.with_name(f"{output_prefix.name}_summary.csv")
    attribution_path = output_prefix.with_name(f"{output_prefix.name}_return_leakage_attribution.csv")
    trades_path = output_prefix.with_name(f"{output_prefix.name}_trades.csv")
    trade_quality_path = output_prefix.with_name(f"{output_prefix.name}_trade_quality.csv")
    trade_quality_summary_path = output_prefix.with_name(f"{output_prefix.name}_trade_quality_summary.csv")
    buy_event_study_path = output_prefix.with_name(f"{output_prefix.name}_buy_event_study.csv")
    buy_event_summary_path = output_prefix.with_name(f"{output_prefix.name}_buy_event_summary.csv")
    buy_event_industry_summary_path = output_prefix.with_name(f"{output_prefix.name}_buy_event_industry_summary.csv")
    buy_event_market_summary_path = output_prefix.with_name(f"{output_prefix.name}_buy_event_market_summary.csv")
    buy_event_breakout_summary_path = output_prefix.with_name(f"{output_prefix.name}_buy_event_breakout_summary.csv")
    sell_event_study_path = output_prefix.with_name(f"{output_prefix.name}_sell_event_study.csv")
    sell_event_summary_path = output_prefix.with_name(f"{output_prefix.name}_sell_event_summary.csv")
    sell_event_reason_summary_path = output_prefix.with_name(f"{output_prefix.name}_sell_event_reason_summary.csv")
    sell_event_market_summary_path = output_prefix.with_name(f"{output_prefix.name}_sell_event_market_summary.csv")
    volume_price_window_study_path = output_prefix.with_name(f"{output_prefix.name}_volume_price_window_study.csv")
    volume_price_window_summary_path = output_prefix.with_name(f"{output_prefix.name}_volume_price_window_summary.csv")

    train_frame.to_csv(train_path, index=False)
    valid_frame.to_csv(valid_path, index=False)
    ranked.to_csv(candidates_path, index=False)
    rules.to_csv(rules_path, index=False)
    portfolio_frame.to_csv(portfolio_path, index=False)
    summary_frame.to_csv(summary_path, index=False)
    attribution_frame.to_csv(attribution_path, index=False)
    if args.export_trades:
        trades.to_csv(trades_path, index=False)
        trade_quality.to_csv(trade_quality_path, index=False)
        trade_quality_summary.to_csv(trade_quality_summary_path, index=False)
        buy_event_study.to_csv(buy_event_study_path, index=False)
        buy_event_summary.to_csv(buy_event_summary_path, index=False)
        buy_event_industry_summary.to_csv(buy_event_industry_summary_path, index=False)
        buy_event_market_summary.to_csv(buy_event_market_summary_path, index=False)
        buy_event_breakout_summary.to_csv(buy_event_breakout_summary_path, index=False)
        sell_event_study.to_csv(sell_event_study_path, index=False)
        sell_event_summary.to_csv(sell_event_summary_path, index=False)
        sell_event_reason_summary.to_csv(sell_event_reason_summary_path, index=False)
        sell_event_market_summary.to_csv(sell_event_market_summary_path, index=False)
        volume_price_window_study.to_csv(volume_price_window_study_path, index=False)
        volume_price_window_summary.to_csv(volume_price_window_summary_path, index=False)
    report_config = replace(
        base_config,
        enable_market_filter=args.market_filter != "none",
        enable_candidate_entry=args.candidate_entry_mode != "off",
        candidate_entry_start_target_pct=args.candidate_entry_start_target_pct if args.candidate_entry_mode != "off" else base_config.candidate_entry_start_target_pct,
        candidate_entry_start_max_bars=args.candidate_entry_start_max_bars,
        candidate_entry_confirm_target_pct=(
            args.candidate_entry_confirm_target_pct
            if args.candidate_entry_mode == "start-and-confirm"
            else args.candidate_entry_start_target_pct
        ),
        candidate_entry_confirm_min_strength=args.candidate_entry_confirm_min_strength,
        candidate_entry_confirm_min_confirmations=args.candidate_entry_confirm_min_confirmations,
        candidate_entry_min_hold_bars=args.candidate_entry_min_hold_bars,
        candidate_entry_hard_stop_loss_pct=args.candidate_entry_hard_stop_loss_pct,
    )
    args.report.write_text(
        _format_report(
            windows=windows,
            train_frame=train_frame,
            valid_frame=valid_frame,
            ranked=ranked,
            rules=rules,
            portfolio_frame=portfolio_frame,
            summary_frame=summary_frame,
            attribution_frame=attribution_frame,
            initial_capital=args.initial_capital,
            paths={
                "train": train_path,
                "valid": valid_path,
                "candidates": candidates_path,
                "rules": rules_path,
                "portfolio": portfolio_path,
                "summary": summary_path,
                "attribution": attribution_path,
                "trades": trades_path,
                "trade_quality": trade_quality_path,
                "trade_quality_summary": trade_quality_summary_path,
                "buy_event_study": buy_event_study_path,
                "buy_event_summary": buy_event_summary_path,
                "buy_event_industry_summary": buy_event_industry_summary_path,
                "buy_event_market_summary": buy_event_market_summary_path,
                "buy_event_breakout_summary": buy_event_breakout_summary_path,
                "sell_event_study": sell_event_study_path,
                "sell_event_summary": sell_event_summary_path,
                "sell_event_reason_summary": sell_event_reason_summary_path,
                "sell_event_market_summary": sell_event_market_summary_path,
                "volume_price_window_study": volume_price_window_study_path,
                "volume_price_window_summary": volume_price_window_summary_path,
            },
            config=report_config,
            market_filter_lookback_days=args.market_filter_lookback_days,
            force_rule_id=args.force_rule_id,
            rule_selection_mode=args.rule_selection_mode,
            rule_selection_top_n=rule_selection_top_n,
            capture_bias_rule_ids=capture_bias_rule_ids,
            capture_bias_constraints=capture_bias_constraints,
            export_trades=args.export_trades,
            trade_quality_summary=trade_quality_summary,
            buy_event_summary=buy_event_summary,
            buy_event_breakout_summary=buy_event_breakout_summary,
            sell_event_summary=sell_event_summary,
            sell_event_reason_summary=sell_event_reason_summary,
            volume_price_window_summary=volume_price_window_summary,
        ),
        encoding="utf-8",
    )

    print("Screened Portfolio Walk-forward")
    print("=" * 36)
    print(f"Windows: {len(windows)}")
    print(f"Train ok: {(train_frame['status'] == 'ok').sum()} / {len(train_frame)}")
    print(f"Valid ok: {(valid_frame['status'] == 'ok').sum()} / {len(valid_frame)}")
    primary_top_n = 100 if 100 in set(portfolio_frame["top_n"].astype(int)) else int(portfolio_frame["top_n"].min())
    selected_rule_counts = portfolio_frame[portfolio_frame["top_n"] == primary_top_n]["rule_id"].value_counts().head(3)
    print(f"Selected rules: {', '.join(selected_rule_counts.index.astype(str))}")
    for _, row in summary_frame.sort_values(["portfolio_weighting", "top_n"]).iterrows():
        print(
            f"{row['portfolio_weighting']} Top {int(row['top_n'])}: walkforward={float(row['walkforward_total_return']):.2%}, "
            f"benchmark={float(row['walkforward_benchmark_return']):.2%}, "
            f"excess={float(row['walkforward_excess_return']):.2%}, "
            f"worst_window_dd={float(row['worst_window_max_drawdown']):.2%}",
        )
    print(f"Report: {args.report}")
    return 0


def _load_reference_trade_dates(items: list[Any], *, data_dir: Path) -> list[date]:
    dates: list[date] | None = None
    for item in items[:20]:
        try:
            bars = load_5min_bars_path(data_dir, symbol=item.symbol)
        except FileNotFoundError:
            continue
        trade_dates = sorted(pd.to_datetime(bars["timestamp"]).dt.date.unique())
        if trade_dates:
            dates = trade_dates
            break
    if not dates:
        raise ValueError(f"no local bars found in {data_dir}")
    return dates


def _build_walkforward_windows(
    items: list[Any],
    *,
    data_dir: Path,
    mode: str,
    split_frac: float,
    train_days: int,
    valid_days: int,
    step_days: int,
    min_valid_days: int,
) -> list[WindowSpec]:
    dates = _load_reference_trade_dates(items, data_dir=data_dir)
    if mode == "single":
        return [_infer_split_window(dates, split_frac=split_frac)]
    train_days = max(20, train_days)
    valid_days = max(5, valid_days)
    step_days = max(1, step_days)
    min_valid_days = max(1, min(min_valid_days, valid_days))
    windows: list[WindowSpec] = []
    start_index = 0
    while start_index + train_days + min_valid_days <= len(dates):
        train_start_index = start_index
        train_end_index = start_index + train_days - 1
        valid_start_index = train_end_index + 1
        valid_end_index = min(valid_start_index + valid_days - 1, len(dates) - 1)
        if valid_end_index - valid_start_index + 1 < min_valid_days:
            break
        windows.append(
            WindowSpec(
                window_id=f"wf{len(windows) + 1:02d}",
                train_start=dates[train_start_index],
                train_end=dates[train_end_index],
                valid_start=dates[valid_start_index],
                valid_end=dates[valid_end_index],
            )
        )
        start_index += step_days
    if not windows:
        return [_infer_split_window(dates, split_frac=split_frac)]
    return windows


def _infer_split_window(dates: list[date], *, split_frac: float) -> WindowSpec:
    split_index = int(len(dates) * max(0.10, min(0.90, split_frac)))
    split_index = max(1, min(split_index, len(dates) - 1))
    return WindowSpec(
        window_id="wf01",
        train_start=dates[0],
        train_end=dates[split_index - 1],
        valid_start=dates[split_index],
        valid_end=dates[-1],
    )


def _load_fixed_selected_symbols(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return []
    raw = value.strip()
    path = Path(raw)
    symbols: list[str] = []
    if path.exists():
        if path.suffix.lower() == ".csv":
            frame = pd.read_csv(path)
            if frame.empty:
                return []
            column = "symbol" if "symbol" in frame.columns else frame.columns[0]
            symbols = [str(symbol).strip() for symbol in frame[column].tolist()]
        else:
            symbols = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    else:
        symbols = [part.strip() for part in raw.split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        deduped.append(symbol)
    return deduped


def _fixed_selected_ranked(ranked: pd.DataFrame, fixed_symbols: list[str]) -> pd.DataFrame:
    order = {symbol: index + 1 for index, symbol in enumerate(fixed_symbols)}
    selected = ranked[ranked["symbol"].isin(order)].copy()
    missing = [symbol for symbol in fixed_symbols if symbol not in set(selected["symbol"])]
    if missing:
        raise ValueError(f"fixed selected symbols are not in ranked universe: {', '.join(missing[:10])}")
    selected["rank"] = selected["symbol"].map(order).astype(int)
    return selected.sort_values("rank").reset_index(drop=True)


def _run_window(
    window: WindowSpec,
    *,
    items: list[Any],
    data_dir: Path,
    market_filter_mode: str,
    market_filter_lookback_days: int,
    base_config: DividendTBacktestConfig,
    force_rule_id: str | None,
    rule_selection_mode: str,
    rule_selection_top_n: int | None,
    capture_bias_rule_ids: frozenset[str] | None,
    capture_bias_constraints: CaptureBiasRuleConstraints,
    fixed_selected_symbols: list[str],
    fundamental_source: str,
    top_n_values: list[int],
    portfolio_weighting: str,
    candidate_entry_mode: str,
    candidate_entry_start_target_pct: float,
    candidate_entry_start_max_bars: int,
    candidate_entry_confirm_target_pct: float,
    candidate_entry_confirm_min_strength: float,
    candidate_entry_confirm_min_confirmations: int,
    candidate_entry_min_hold_bars: int,
    candidate_entry_hard_stop_loss_pct: float,
    export_trades: bool,
    trade_quality_horizon_bars: int,
    trade_quality_buy_up_threshold_pct: float,
    trade_quality_stop_loss_threshold_pct: float,
    trade_quality_sell_drawdown_threshold_pct: float,
    trade_quality_sell_fly_threshold_pct: float,
    buy_event_horizon_bars: tuple[int, ...],
    sell_event_horizon_bars: tuple[int, ...],
    volume_price_event_window_bars: tuple[int, ...],
    sell_event_drawdown_threshold_pct: float,
    sell_event_rally_threshold_pct: float,
    workers: int,
    worker_mode: str,
) -> WindowRunResult:
    print(
        f"{window.window_id} train={window.train_start}..{window.train_end} "
        f"valid={window.valid_start}..{window.valid_end}",
        flush=True,
    )
    train_filter = _build_period_market_filter(
        market_filter_mode,
        items=items,
        data_dir=data_dir,
        start_date=window.train_start,
        end_date=window.train_end,
        lookback_days=market_filter_lookback_days,
    )
    valid_filter = _build_period_market_filter(
        market_filter_mode,
        items=items,
        data_dir=data_dir,
        start_date=window.valid_start,
        end_date=window.valid_end,
        lookback_days=market_filter_lookback_days,
    )
    train_config = replace(
        base_config,
        enable_market_filter=train_filter is not None,
        market_filter_name=train_filter.name if train_filter is not None else "none",
    )
    valid_config = replace(
        base_config,
        enable_market_filter=valid_filter is not None,
        market_filter_name=valid_filter.name if valid_filter is not None else "none",
    )
    curve_config = _candidate_entry_curve_config(
        valid_config,
        mode=candidate_entry_mode,
        start_target_pct=candidate_entry_start_target_pct,
        start_max_bars=candidate_entry_start_max_bars,
        confirm_target_pct=candidate_entry_confirm_target_pct,
        confirm_min_strength=candidate_entry_confirm_min_strength,
        confirm_min_confirmations=candidate_entry_confirm_min_confirmations,
        min_hold_bars=candidate_entry_min_hold_bars,
        hard_stop_loss_pct=candidate_entry_hard_stop_loss_pct,
    )
    train_rows = _run_period_batch(
        items,
        period="train",
        data_dir=data_dir,
        start_date=window.train_start,
        end_date=window.train_end,
        config=train_config,
        market_filter=train_filter,
        fundamental_source=fundamental_source,
        workers=workers,
        worker_mode=worker_mode,
    )
    valid_rows = _run_period_batch(
        items,
        period="valid",
        data_dir=data_dir,
        start_date=window.valid_start,
        end_date=window.valid_end,
        config=valid_config,
        market_filter=valid_filter,
        fundamental_source=fundamental_source,
        workers=workers,
        worker_mode=worker_mode,
    )

    train_frame = _with_window_columns(_rows_to_frame(train_rows), window)
    valid_frame = _with_window_columns(_rows_to_frame(valid_rows), window)
    train_features = _build_train_features(train_frame)
    rules = _with_window_columns(_train_rules(train_features, top_n_values=top_n_values), window)
    best_rule = _select_rule_for_window(
        rules,
        force_rule_id=force_rule_id,
        preferred_top_n=rule_selection_top_n,
        selection_mode=rule_selection_mode,
        capture_bias_rule_ids=capture_bias_rule_ids,
        capture_bias_constraints=capture_bias_constraints,
    )
    best_rule_id = best_rule["rule_id"]
    ranked = _rank_candidates(train_features, best_rule).copy()
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    ranked = _with_window_columns(ranked, window)
    selected_ranked = _fixed_selected_ranked(ranked, fixed_selected_symbols) if fixed_selected_symbols else ranked

    max_top_n = max(top_n_values)
    selected_symbols = selected_ranked.head(max_top_n)["symbol"].tolist()
    curve_payloads = _run_curve_batch(
        [item for item in items if item.symbol in set(selected_symbols)],
        data_dir=data_dir,
        start_date=window.valid_start,
        end_date=window.valid_end,
        config=curve_config,
        market_filter=valid_filter,
        fundamental_source=fundamental_source,
        export_trades=export_trades,
        trade_quality_horizon_bars=trade_quality_horizon_bars,
        trade_quality_buy_up_threshold_pct=trade_quality_buy_up_threshold_pct,
        trade_quality_stop_loss_threshold_pct=trade_quality_stop_loss_threshold_pct,
        trade_quality_sell_drawdown_threshold_pct=trade_quality_sell_drawdown_threshold_pct,
        trade_quality_sell_fly_threshold_pct=trade_quality_sell_fly_threshold_pct,
        buy_event_horizon_bars=buy_event_horizon_bars,
        sell_event_horizon_bars=sell_event_horizon_bars,
        volume_price_event_window_bars=volume_price_event_window_bars,
        sell_event_drawdown_threshold_pct=sell_event_drawdown_threshold_pct,
        sell_event_rally_threshold_pct=sell_event_rally_threshold_pct,
        workers=workers,
        worker_mode=worker_mode,
    )
    curve_map = {payload.symbol: payload for payload in curve_payloads if payload.status == "ok"}
    trade_frame, trade_quality_frame, buy_event_study_frame, sell_event_study_frame, volume_price_window_study_frame = _window_trade_frames(
        window,
        ranked=selected_ranked,
        payloads=curve_payloads,
        export_trades=export_trades,
    )

    portfolio_rows: list[RuleResult] = []
    for top_n in top_n_values:
        symbols = selected_ranked.head(top_n)["symbol"].tolist()
        train_sub = train_features[train_features["symbol"].isin(symbols)]
        valid_sub = valid_frame[(valid_frame["status"] == "ok") & (valid_frame["symbol"].isin(symbols))]
        portfolio = _portfolio_metrics(curve_map, symbols, weighting=portfolio_weighting)
        portfolio_rows.append(
            RuleResult(
                window_id=window.window_id,
                train_start=str(window.train_start),
                train_end=str(window.train_end),
                valid_start=str(window.valid_start),
                valid_end=str(window.valid_end),
                rule_id=str(best_rule_id),
                candidate_count=int(best_rule["candidate_count"]),
                top_n=top_n,
                portfolio_weighting=portfolio_weighting,
                train_score=float(train_sub["screen_score"].mean()),
                train_total_return=float(train_sub["total_return"].mean()),
                train_positive_rate=float((train_sub["total_return"] > 0).mean()),
                train_max_drawdown=float(train_sub["max_drawdown"].mean()),
                train_stop_per_trade=float(train_sub["stop_per_trade"].mean()),
                valid_total_return=portfolio["strategy_return"],
                valid_benchmark_return=portfolio["benchmark_return"],
                valid_risk_matched_benchmark_return=portfolio["risk_matched_benchmark_return"],
                valid_excess_return=portfolio["strategy_return"] - portfolio["benchmark_return"],
                valid_risk_matched_excess_return=portfolio["strategy_return"] - portfolio["risk_matched_benchmark_return"],
                valid_max_drawdown=portfolio["strategy_max_drawdown"],
                valid_positive_rate=float((valid_sub["total_return"] > 0).mean()),
                valid_constituent_avg_return=float(valid_sub["total_return"].mean()),
                valid_constituent_median_return=float(valid_sub["total_return"].median()),
                signal_quantile=float(best_rule["signal_quantile"]),
                offensive_quantile=float(best_rule["offensive_quantile"]),
                trend_quantile=float(best_rule["trend_quantile"]),
                capture_quantile=float(best_rule["capture_quantile"]),
                drawdown_quantile=float(best_rule["drawdown_quantile"]),
                stop_quantile=float(best_rule["stop_quantile"]),
            )
        )
    return WindowRunResult(
        window=window,
        train_frame=train_frame,
        valid_frame=valid_frame,
        ranked=ranked,
        rules=rules,
        portfolio_rows=portfolio_rows,
        trades=trade_frame,
        trade_quality=trade_quality_frame,
        buy_event_study=buy_event_study_frame,
        sell_event_study=sell_event_study_frame,
        volume_price_window_study=volume_price_window_study_frame,
    )


def _candidate_entry_curve_config(
    config: DividendTBacktestConfig,
    *,
    mode: str,
    start_target_pct: float,
    start_max_bars: int,
    confirm_target_pct: float,
    confirm_min_strength: float,
    confirm_min_confirmations: int,
    min_hold_bars: int,
    hard_stop_loss_pct: float,
) -> DividendTBacktestConfig:
    if mode == "off":
        return replace(config, enable_candidate_entry=False)
    return replace(
        config,
        enable_candidate_entry=True,
        candidate_entry_start_target_pct=start_target_pct,
        candidate_entry_start_max_bars=start_max_bars,
        candidate_entry_confirm_target_pct=confirm_target_pct if mode == "start-and-confirm" else start_target_pct,
        candidate_entry_confirm_min_strength=confirm_min_strength,
        candidate_entry_confirm_min_confirmations=confirm_min_confirmations,
        candidate_entry_min_hold_bars=min_hold_bars,
        candidate_entry_hard_stop_loss_pct=hard_stop_loss_pct,
    )


def _with_window_columns(frame: pd.DataFrame, window: WindowSpec) -> pd.DataFrame:
    data = frame.copy()
    values = {
        "window_id": window.window_id,
        "train_start": str(window.train_start),
        "train_end": str(window.train_end),
        "valid_start": str(window.valid_start),
        "valid_end": str(window.valid_end),
    }
    for column, value in values.items():
        data[column] = value
    leading = list(values)
    return data[leading + [column for column in data.columns if column not in leading]]


def _concat_optional_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    return pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()


def _window_trade_frames(
    window: WindowSpec,
    *,
    ranked: pd.DataFrame,
    payloads: list[CurvePayload],
    export_trades: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not export_trades:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    rank_lookup = ranked.set_index("symbol")["rank"].to_dict()
    trade_rows: list[dict[str, object]] = []
    quality_rows: list[dict[str, object]] = []
    buy_event_rows: list[dict[str, object]] = []
    sell_event_rows: list[dict[str, object]] = []
    volume_price_window_rows: list[dict[str, object]] = []
    for payload in payloads:
        if payload.status != "ok":
            continue
        for row in payload.trades:
            trade_rows.append(_with_trade_window_fields(window, row, rank_lookup=rank_lookup))
        for row in payload.trade_quality:
            quality_rows.append(_with_trade_window_fields(window, row, rank_lookup=rank_lookup))
        for row in payload.buy_event_study:
            buy_event_rows.append(_with_trade_window_fields(window, row, rank_lookup=rank_lookup))
        for row in payload.sell_event_study:
            sell_event_rows.append(_with_trade_window_fields(window, row, rank_lookup=rank_lookup))
        for row in payload.volume_price_window_study:
            volume_price_window_rows.append(_with_trade_window_fields(window, row, rank_lookup=rank_lookup))
    return (
        pd.DataFrame(trade_rows),
        pd.DataFrame(quality_rows),
        pd.DataFrame(buy_event_rows),
        pd.DataFrame(sell_event_rows),
        pd.DataFrame(volume_price_window_rows),
    )


def _with_trade_window_fields(window: WindowSpec, row: dict[str, object], *, rank_lookup: dict[str, object]) -> dict[str, object]:
    symbol = str(row.get("symbol", ""))
    return {
        "window_id": window.window_id,
        "train_start": str(window.train_start),
        "train_end": str(window.train_end),
        "valid_start": str(window.valid_start),
        "valid_end": str(window.valid_end),
        "rank": int(rank_lookup[symbol]) if symbol in rank_lookup else None,
        **row,
    }


def _evaluate_trade_quality(
    *,
    timestamp: str,
    side: str,
    price: float,
    bars: pd.DataFrame,
    horizon_bars: int,
    buy_up_threshold_pct: float,
    stop_loss_threshold_pct: float,
    sell_drawdown_threshold_pct: float,
    sell_fly_threshold_pct: float,
) -> dict[str, object]:
    future = _future_trade_bars(timestamp=timestamp, bars=bars, horizon_bars=horizon_bars)
    trade_type = _trade_type(side)
    if future.empty or price <= 0:
        return {
            "trade_type": trade_type,
            "horizon_bars": max(0, horizon_bars),
            "future_bar_count": 0,
            "future_max_return_pct": None,
            "future_min_return_pct": None,
            "future_end_return_pct": None,
            "buy_target_hit_bar": None,
            "stop_loss_hit_bar": None,
            "sell_drawdown_hit_bar": None,
            "sell_fly_hit_bar": None,
            "buy_accurate": False if trade_type == "buy" else None,
            "sell_accurate": False if trade_type == "sell_exit" else None,
            "sell_flying": False if trade_type == "sell_exit" else None,
        }

    high = pd.to_numeric(future["high"] if "high" in future else future["close"], errors="coerce")
    low = pd.to_numeric(future["low"] if "low" in future else future["close"], errors="coerce")
    close = pd.to_numeric(future["close"], errors="coerce")
    high_return = high / float(price) - 1.0
    low_return = low / float(price) - 1.0
    close_return = close / float(price) - 1.0
    buy_target_hit_bar = _first_hit_bar(high_return, buy_up_threshold_pct, direction=">=")
    stop_loss_hit_bar = _first_hit_bar(low_return, -abs(stop_loss_threshold_pct), direction="<=")
    sell_drawdown_hit_bar = _first_hit_bar(low_return, -abs(sell_drawdown_threshold_pct), direction="<=")
    sell_fly_hit_bar = _first_hit_bar(high_return, abs(sell_fly_threshold_pct), direction=">=")
    future_end_return = float(close_return.dropna().iloc[-1]) if not close_return.dropna().empty else None

    buy_accurate = None
    sell_accurate = None
    sell_flying = None
    if trade_type == "buy":
        buy_accurate = buy_target_hit_bar is not None and (stop_loss_hit_bar is None or buy_target_hit_bar <= stop_loss_hit_bar)
    elif trade_type == "sell_exit":
        sell_flying = sell_fly_hit_bar is not None
        sell_accurate = (
            sell_drawdown_hit_bar is not None
            and (sell_fly_hit_bar is None or sell_drawdown_hit_bar <= sell_fly_hit_bar)
        ) or (future_end_return is not None and future_end_return <= 0.0)

    return {
        "trade_type": trade_type,
        "horizon_bars": max(0, horizon_bars),
        "future_bar_count": int(len(future)),
        "future_max_return_pct": float(high_return.max()) if not high_return.dropna().empty else None,
        "future_min_return_pct": float(low_return.min()) if not low_return.dropna().empty else None,
        "future_end_return_pct": future_end_return,
        "buy_target_hit_bar": buy_target_hit_bar,
        "stop_loss_hit_bar": stop_loss_hit_bar,
        "sell_drawdown_hit_bar": sell_drawdown_hit_bar,
        "sell_fly_hit_bar": sell_fly_hit_bar,
        "buy_accurate": buy_accurate,
        "sell_accurate": sell_accurate,
        "sell_flying": sell_flying,
    }


def _evaluate_buy_event_study(
    *,
    symbol: str,
    name: str,
    industry: str,
    trade_index: int,
    trade: Any,
    bars: pd.DataFrame,
    horizon_bars: tuple[int, ...],
    point_lookup: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    if _trade_type(trade.side) != "buy" or float(trade.price) <= 0:
        return ()

    point = point_lookup.get(str(trade.timestamp))
    breakout_alpha = _breakout_alpha_features(point)
    records: list[dict[str, object]] = []
    for horizon in horizon_bars:
        future = _future_trade_bars(timestamp=trade.timestamp, bars=bars, horizon_bars=horizon)
        metrics = _buy_event_forward_metrics(price=float(trade.price), future=future)
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "industry": industry,
                "trade_index": trade_index,
                "timestamp": trade.timestamp,
                "action": trade.action,
                "side": trade.side,
                "buy_event_type": _buy_event_type(trade.action, trade.side),
                "shares": trade.shares,
                "price": trade.price,
                "cash_after": trade.cash_after,
                "equity_after": trade.equity_after,
                "reason": trade.reason,
                "horizon_bars": horizon,
                "market_regime_state": getattr(point, "market_regime_state", None),
                "market_environment_state": getattr(point, "market_environment_state", None),
                "market_environment_score": getattr(point, "market_environment_score", None),
                "attack_state": getattr(point, "attack_state", None),
                "strategy_mode": getattr(point, "strategy_mode", None),
                **breakout_alpha,
                **metrics,
            }
        )
    return tuple(records)


def _breakout_alpha_features(point: Any | None) -> dict[str, object]:
    breakout_score = _point_float(point, "breakout_score", 0.0)
    breakout_confirmed = _point_bool(point, "breakout_confirmed", False)
    breakout_state = _point_str(point, "breakout_state", "NONE")
    volume_price_score = _point_float(point, "volume_price_score", 50.0)
    volume_breakout_score = _point_float(point, "volume_breakout_score", 50.0)
    persistence_score = _point_float(point, "post_breakout_volume_persistence_score", 50.0)
    vwap_support_score = _point_float(point, "vwap_support_score", 50.0)
    flow_score = _point_float(point, "capital_flow_confirmation_score", 50.0)
    flow_confidence = _point_float(point, "capital_flow_confidence", 0.0)
    flow_state = _point_str(point, "capital_flow_confirmation_state", "UNCONFIRMED")
    force_weighted_score = _point_float(point, "force_weighted_score", 50.0)
    sell_pressure_score = _point_float(point, "sell_pressure_score", 50.0)
    down_probability_1d = _point_float(point, "down_probability_1d", 0.50)
    down_probability_3d = _point_float(point, "down_probability_3d", 0.50)
    high_volume_stall_score = _point_float(point, "high_volume_stall_score", 0.0)
    price_up_volume_down_score = _point_float(point, "price_up_volume_down_score", 0.0)
    buy_signal_strength = _point_float(point, "buy_signal_strength", 0.0)
    chan_score = _point_float(point, "chan_score", 50.0)
    chan_buy_point_type = _point_str(point, "chan_buy_point_type", "none")
    breakout_active = breakout_confirmed or breakout_score >= 86.0 or breakout_state.upper() in {
        "BREAKOUT_CONFIRMED",
        "BREAKOUT_ATTACK",
        "BREAKOUT_WATCH",
    }
    breakout_core = breakout_confirmed or breakout_score >= 88.0
    vwap_confirmed = vwap_support_score >= 70.0
    volume_confirmed = (
        volume_price_score >= 70.0
        and volume_breakout_score >= 68.0
        and persistence_score >= 70.0
    )
    strong_volume_confirmed = (
        volume_price_score >= 78.0
        and volume_breakout_score >= 74.0
        and persistence_score >= 76.0
    )
    flow_confirmed = flow_state.upper() == "CONFIRMED_INFLOW" or (flow_score >= 66.0 and flow_confidence >= 0.58)
    strong_flow_confirmed = flow_state.upper() == "CONFIRMED_INFLOW" and flow_score >= 72.0 and flow_confidence >= 0.50
    pressure_clean = sell_pressure_score < 70.0 and down_probability_1d < 0.60 and down_probability_3d < 0.62
    strong_pressure_clean = sell_pressure_score < 64.0 and down_probability_1d < 0.56 and down_probability_3d < 0.58
    stall_pressure = high_volume_stall_score >= 78.0 or price_up_volume_down_score >= 82.0
    buy3_support = chan_buy_point_type == "buy3" and chan_score >= 76.0
    confirmation_count = sum(
        (
            breakout_core,
            vwap_confirmed,
            volume_confirmed,
            flow_confirmed,
            pressure_clean,
            buy_signal_strength >= 72.0,
            buy3_support,
        )
    )
    score = (
        0.22 * _score_0_1(breakout_score, 78.0, 96.0)
        + 0.16 * _score_0_1(vwap_support_score, 62.0, 82.0)
        + 0.16 * _score_0_1(volume_price_score, 62.0, 84.0)
        + 0.14 * _score_0_1(persistence_score, 62.0, 84.0)
        + 0.14 * _score_0_1(flow_score, 58.0, 82.0)
        + 0.10 * _score_0_1(force_weighted_score, 48.0, 72.0)
        + 0.08 * _score_0_1(100.0 - sell_pressure_score, 30.0, 55.0)
    )
    if breakout_confirmed:
        score += 0.05
    if buy3_support:
        score += 0.03
    if stall_pressure and not (vwap_support_score >= 76.0 and persistence_score >= 76.0 and flow_confirmed):
        score -= 0.08
    score = max(0.0, min(score, 1.0))
    if not breakout_active:
        tier = "no_breakout_alpha"
    elif (
        score >= 0.90
        and (breakout_confirmed or breakout_score >= 92.0)
        and vwap_support_score >= 76.0
        and strong_volume_confirmed
        and strong_flow_confirmed
        and strong_pressure_clean
        and not stall_pressure
    ):
        tier = "high_quality_breakout"
    elif score >= 0.62 and breakout_core and vwap_confirmed and volume_confirmed and flow_confirmed and pressure_clean:
        tier = "qualified_breakout"
    elif breakout_core and (not volume_confirmed or not vwap_confirmed):
        tier = "weak_follow_breakout"
    elif stall_pressure and breakout_core:
        tier = "stall_pressure_breakout"
    else:
        tier = "low_quality_breakout"
    return {
        "breakout_alpha_tier": tier,
        "breakout_alpha_score": round(score, 4),
        "breakout_confirmation_count": int(confirmation_count),
        "breakout_active": breakout_active,
        "breakout_score": breakout_score,
        "breakout_confirmed": breakout_confirmed,
        "breakout_state": breakout_state,
        "buy_signal_strength": buy_signal_strength,
        "volume_price_score": volume_price_score,
        "volume_breakout_score": volume_breakout_score,
        "post_breakout_volume_persistence_score": persistence_score,
        "vwap_support_score": vwap_support_score,
        "capital_flow_confirmation_score": flow_score,
        "capital_flow_confirmation_state": flow_state,
        "capital_flow_confidence": flow_confidence,
        "force_weighted_score": force_weighted_score,
        "sell_pressure_score": sell_pressure_score,
        "down_probability_1d": down_probability_1d,
        "down_probability_3d": down_probability_3d,
        "high_volume_stall_score": high_volume_stall_score,
        "price_up_volume_down_score": price_up_volume_down_score,
        "chan_score": chan_score,
        "chan_buy_point_type": chan_buy_point_type,
        "breakout_volume_confirmed": volume_confirmed,
        "breakout_vwap_confirmed": vwap_confirmed,
        "breakout_flow_confirmed": flow_confirmed,
        "breakout_pressure_clean": pressure_clean,
        "breakout_stall_pressure": stall_pressure,
    }


def _point_float(point: Any | None, attr: str, default: float) -> float:
    value = getattr(point, attr, default) if point is not None else default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _point_str(point: Any | None, attr: str, default: str) -> str:
    value = getattr(point, attr, default) if point is not None else default
    return str(value) if value is not None else default


def _point_bool(point: Any | None, attr: str, default: bool) -> bool:
    value = getattr(point, attr, default) if point is not None else default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _score_0_1(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min((value - low) / (high - low), 1.0))


def _buy_event_forward_metrics(*, price: float, future: pd.DataFrame) -> dict[str, object]:
    if future.empty or price <= 0:
        return {
            "future_bar_count": 0,
            "end_return_pct": None,
            "max_favorable_return_pct": None,
            "max_adverse_return_pct": None,
            "max_favorable_hit_bar": None,
            "max_adverse_hit_bar": None,
            "target_1pct_hit_bar": None,
            "target_2pct_hit_bar": None,
            "target_3pct_hit_bar": None,
            "drawdown_2pct_hit_bar": None,
            "drawdown_3pct_hit_bar": None,
            "drawdown_5pct_hit_bar": None,
        }

    high = pd.to_numeric(future["high"] if "high" in future else future["close"], errors="coerce")
    low = pd.to_numeric(future["low"] if "low" in future else future["close"], errors="coerce")
    close = pd.to_numeric(future["close"], errors="coerce")
    high_return = high / price - 1.0
    low_return = low / price - 1.0
    close_return = close / price - 1.0
    clean_high = high_return.dropna()
    clean_low = low_return.dropna()
    clean_close = close_return.dropna()
    max_favorable = float(clean_high.max()) if not clean_high.empty else None
    max_adverse = float(clean_low.min()) if not clean_low.empty else None
    return {
        "future_bar_count": int(len(future)),
        "end_return_pct": float(clean_close.iloc[-1]) if not clean_close.empty else None,
        "max_favorable_return_pct": max_favorable,
        "max_adverse_return_pct": max_adverse,
        "max_favorable_hit_bar": _first_extreme_bar(high_return, max_favorable),
        "max_adverse_hit_bar": _first_extreme_bar(low_return, max_adverse),
        "target_1pct_hit_bar": _first_hit_bar(high_return, 0.01, direction=">="),
        "target_2pct_hit_bar": _first_hit_bar(high_return, 0.02, direction=">="),
        "target_3pct_hit_bar": _first_hit_bar(high_return, 0.03, direction=">="),
        "drawdown_2pct_hit_bar": _first_hit_bar(low_return, -0.02, direction="<="),
        "drawdown_3pct_hit_bar": _first_hit_bar(low_return, -0.03, direction="<="),
        "drawdown_5pct_hit_bar": _first_hit_bar(low_return, -0.05, direction="<="),
    }


def _buy_event_type(action: str, side: str) -> str:
    side_upper = str(side).upper()
    action_upper = str(action).upper()
    if side_upper == "BUY_CANDIDATE_CONFIRM":
        return "candidate_confirm"
    if side_upper == "BUY_RISK_ON_TARGET":
        return "risk_on_target_add"
    if side_upper == "BUY_BREAKOUT" or action_upper == "BREAKOUT_BUY_TIMING":
        return "breakout_buy"
    if side_upper == "BUY_T" or action_upper == "BUY_T_TIMING":
        return "buy_timing"
    return "other_buy"


def _evaluate_sell_event_study(
    *,
    symbol: str,
    name: str,
    industry: str,
    trade_index: int,
    trade: Any,
    bars: pd.DataFrame,
    horizon_bars: tuple[int, ...],
    point_lookup: dict[str, Any],
    drawdown_threshold_pct: float,
    rally_threshold_pct: float,
) -> tuple[dict[str, object], ...]:
    if _trade_type(trade.side) != "sell_exit" or float(trade.price) <= 0:
        return ()

    point = point_lookup.get(str(trade.timestamp))
    sell_event_type = _sell_event_type(
        action=trade.action,
        side=trade.side,
        reason=trade.reason,
        attack_state=getattr(point, "attack_state", None),
    )
    records: list[dict[str, object]] = []
    for horizon in horizon_bars:
        future = _future_trade_bars(timestamp=trade.timestamp, bars=bars, horizon_bars=horizon)
        metrics = _sell_event_forward_metrics(
            price=float(trade.price),
            future=future,
            drawdown_threshold_pct=drawdown_threshold_pct,
            rally_threshold_pct=rally_threshold_pct,
        )
        records.append(
            {
                "symbol": symbol,
                "name": name,
                "industry": industry,
                "trade_index": trade_index,
                "timestamp": trade.timestamp,
                "action": trade.action,
                "side": trade.side,
                "sell_event_type": sell_event_type,
                "shares": trade.shares,
                "price": trade.price,
                "cash_after": trade.cash_after,
                "equity_after": trade.equity_after,
                "realized_pnl": trade.realized_pnl,
                "reason": trade.reason,
                "horizon_bars": horizon,
                "market_regime_state": getattr(point, "market_regime_state", None),
                "market_environment_state": getattr(point, "market_environment_state", None),
                "market_environment_score": getattr(point, "market_environment_score", None),
                "attack_state": getattr(point, "attack_state", None),
                "strategy_mode": getattr(point, "strategy_mode", None),
                **metrics,
            }
        )
    return tuple(records)


def _sell_event_forward_metrics(
    *,
    price: float,
    future: pd.DataFrame,
    drawdown_threshold_pct: float,
    rally_threshold_pct: float,
) -> dict[str, object]:
    empty_record = {
        "future_bar_count": 0,
        "end_return_pct": None,
        "max_up_return_pct": None,
        "max_down_return_pct": None,
        "max_missed_upside_pct": None,
        "max_avoided_drawdown_pct": None,
        "max_up_hit_bar": None,
        "max_down_hit_bar": None,
        "rally_1pct_hit_bar": None,
        "rally_2pct_hit_bar": None,
        "rally_3pct_hit_bar": None,
        "rally_5pct_hit_bar": None,
        "drawdown_1pct_hit_bar": None,
        "drawdown_2pct_hit_bar": None,
        "drawdown_3pct_hit_bar": None,
        "drawdown_5pct_hit_bar": None,
        "sell_drawdown_hit_bar": None,
        "sell_rally_hit_bar": None,
        "risk_avoided": False,
        "sell_valid": False,
        "sell_flying": False,
    }
    if future.empty or price <= 0:
        return empty_record

    high = pd.to_numeric(future["high"] if "high" in future else future["close"], errors="coerce")
    low = pd.to_numeric(future["low"] if "low" in future else future["close"], errors="coerce")
    close = pd.to_numeric(future["close"], errors="coerce")
    high_return = high / price - 1.0
    low_return = low / price - 1.0
    close_return = close / price - 1.0
    clean_high = high_return.dropna()
    clean_low = low_return.dropna()
    clean_close = close_return.dropna()
    max_up = float(clean_high.max()) if not clean_high.empty else None
    max_down = float(clean_low.min()) if not clean_low.empty else None
    end_return = float(clean_close.iloc[-1]) if not clean_close.empty else None
    sell_drawdown_hit_bar = _first_hit_bar(low_return, -abs(drawdown_threshold_pct), direction="<=")
    sell_rally_hit_bar = _first_hit_bar(high_return, abs(rally_threshold_pct), direction=">=")
    risk_avoided = (
        sell_drawdown_hit_bar is not None
        and (sell_rally_hit_bar is None or sell_drawdown_hit_bar <= sell_rally_hit_bar)
    )
    sell_flying = sell_rally_hit_bar is not None
    sell_valid = risk_avoided or (sell_rally_hit_bar is None and end_return is not None and end_return <= 0.0)
    return {
        "future_bar_count": int(len(future)),
        "end_return_pct": end_return,
        "max_up_return_pct": max_up,
        "max_down_return_pct": max_down,
        "max_missed_upside_pct": max(max_up or 0.0, 0.0),
        "max_avoided_drawdown_pct": abs(min(max_down or 0.0, 0.0)),
        "max_up_hit_bar": _first_extreme_bar(high_return, max_up),
        "max_down_hit_bar": _first_extreme_bar(low_return, max_down),
        "rally_1pct_hit_bar": _first_hit_bar(high_return, 0.01, direction=">="),
        "rally_2pct_hit_bar": _first_hit_bar(high_return, 0.02, direction=">="),
        "rally_3pct_hit_bar": _first_hit_bar(high_return, 0.03, direction=">="),
        "rally_5pct_hit_bar": _first_hit_bar(high_return, 0.05, direction=">="),
        "drawdown_1pct_hit_bar": _first_hit_bar(low_return, -0.01, direction="<="),
        "drawdown_2pct_hit_bar": _first_hit_bar(low_return, -0.02, direction="<="),
        "drawdown_3pct_hit_bar": _first_hit_bar(low_return, -0.03, direction="<="),
        "drawdown_5pct_hit_bar": _first_hit_bar(low_return, -0.05, direction="<="),
        "sell_drawdown_hit_bar": sell_drawdown_hit_bar,
        "sell_rally_hit_bar": sell_rally_hit_bar,
        "risk_avoided": risk_avoided,
        "sell_valid": sell_valid,
        "sell_flying": sell_flying,
    }


def _evaluate_volume_price_window_study(
    *,
    symbol: str,
    name: str,
    industry: str,
    trade_index: int,
    trade: Any,
    bars: pd.DataFrame,
    horizon_bars: tuple[int, ...],
    lookback_window_bars: tuple[int, ...],
    point_lookup: dict[str, Any],
    sell_event_drawdown_threshold_pct: float,
    sell_event_rally_threshold_pct: float,
) -> tuple[dict[str, object], ...]:
    event_side = _trade_type(trade.side)
    if event_side not in {"buy", "sell_exit"} or float(trade.price) <= 0:
        return ()
    point = point_lookup.get(str(trade.timestamp))
    event_subtype = (
        _buy_event_type(trade.action, trade.side)
        if event_side == "buy"
        else _sell_event_type(
            action=trade.action,
            side=trade.side,
            reason=trade.reason,
            attack_state=getattr(point, "attack_state", None),
        )
    )
    records: list[dict[str, object]] = []
    for lookback in lookback_window_bars:
        volume_price_features = _volume_price_window_features(
            timestamp=trade.timestamp,
            bars=bars,
            lookback_bars=lookback,
        )
        for horizon in horizon_bars:
            future = _future_trade_bars(timestamp=trade.timestamp, bars=bars, horizon_bars=horizon)
            if event_side == "buy":
                outcome = _buy_event_forward_metrics(price=float(trade.price), future=future)
            else:
                outcome = _sell_event_forward_metrics(
                    price=float(trade.price),
                    future=future,
                    drawdown_threshold_pct=sell_event_drawdown_threshold_pct,
                    rally_threshold_pct=sell_event_rally_threshold_pct,
                )
            records.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "industry": industry,
                    "trade_index": trade_index,
                    "timestamp": trade.timestamp,
                    "action": trade.action,
                    "side": trade.side,
                    "event_side": event_side,
                    "event_subtype": event_subtype,
                    "shares": trade.shares,
                    "price": trade.price,
                    "cash_after": trade.cash_after,
                    "equity_after": trade.equity_after,
                    "realized_pnl": trade.realized_pnl,
                    "reason": trade.reason,
                    "horizon_bars": horizon,
                    "lookback_bars": lookback,
                    "market_regime_state": getattr(point, "market_regime_state", None),
                    "market_environment_state": getattr(point, "market_environment_state", None),
                    "market_environment_score": getattr(point, "market_environment_score", None),
                    "attack_state": getattr(point, "attack_state", None),
                    "strategy_mode": getattr(point, "strategy_mode", None),
                    **volume_price_features,
                    **outcome,
                }
            )
    return tuple(records)


def _volume_price_window_features(*, timestamp: str, bars: pd.DataFrame, lookback_bars: int) -> dict[str, object]:
    event_ts = pd.to_datetime(timestamp, errors="coerce")
    timestamps = pd.to_datetime(bars["timestamp"], errors="coerce")
    prior = bars[timestamps < event_ts].copy()
    window = prior.tail(max(1, lookback_bars))
    previous = prior.iloc[max(0, len(prior) - lookback_bars * 2) : max(0, len(prior) - lookback_bars)]
    if window.empty or len(window) < 3:
        return _empty_volume_price_window_features(lookback_bars, actual_bars=len(window))

    close = pd.to_numeric(window["close"], errors="coerce").dropna()
    high = pd.to_numeric(window["high"] if "high" in window else window["close"], errors="coerce").dropna()
    low = pd.to_numeric(window["low"] if "low" in window else window["close"], errors="coerce").dropna()
    volume = pd.to_numeric(window.get("volume", pd.Series(0.0, index=window.index)), errors="coerce").dropna()
    prev_volume = pd.to_numeric(previous.get("volume", pd.Series(0.0, index=previous.index)), errors="coerce").dropna()
    if close.empty:
        return _empty_volume_price_window_features(lookback_bars, actual_bars=len(window))

    first_close = float(close.iloc[0])
    last_close = float(close.iloc[-1])
    price_return_pct = last_close / first_close - 1.0 if first_close > 0 else 0.0
    close_mean = float(close.mean()) if not close.empty else 0.0
    close_sma_gap_pct = last_close / close_mean - 1.0 if close_mean > 0 else 0.0
    close_change = close.pct_change().dropna()
    path_sum = float(close_change.abs().sum()) if not close_change.empty else 0.0
    price_efficiency = abs(price_return_pct) / path_sum if path_sum > 0 else 0.0
    price_volatility_pct = float(close_change.std()) if len(close_change) >= 2 else 0.0
    high_max = float(high.max()) if not high.empty else last_close
    low_min = float(low.min()) if not low.empty else last_close
    high_low_range_pct = high_max / low_min - 1.0 if low_min > 0 else 0.0
    volume_mean = float(volume.mean()) if not volume.empty else 0.0
    prev_volume_mean = float(prev_volume.mean()) if not prev_volume.empty else 0.0
    volume_ratio_to_prev = volume_mean / prev_volume_mean - 1.0 if prev_volume_mean > 0 else 0.0
    half = max(1, len(volume) // 2)
    first_half_volume = float(volume.iloc[:half].mean()) if not volume.empty else 0.0
    second_half_volume = float(volume.iloc[-half:].mean()) if not volume.empty else 0.0
    volume_trend_pct = second_half_volume / first_half_volume - 1.0 if first_half_volume > 0 else 0.0
    volume_signal_pct = volume_ratio_to_prev if prev_volume_mean > 0 else volume_trend_pct
    volume_change = volume.pct_change().replace([float("inf"), float("-inf")], pd.NA).dropna()
    price_volume_corr = 0.0
    if (
        len(close_change) >= 3
        and len(volume_change) >= 3
        and float(close_change.std()) > 0
        and float(volume_change.std()) > 0
    ):
        price_volume_corr = float(close_change.corr(volume_change))
    up_bar_share = float((close.diff().dropna() > 0).mean()) if len(close) >= 2 else 0.0
    price_trend_bucket = _price_trend_bucket(price_return_pct)
    volume_trend_bucket = _volume_trend_bucket(volume_signal_pct)
    volume_price_state = _volume_price_state(price_return_pct, volume_signal_pct)
    return {
        "lookback_bar_count": int(len(window)),
        "price_return_pct": price_return_pct,
        "price_sma_gap_pct": close_sma_gap_pct,
        "price_efficiency": price_efficiency,
        "price_volatility_pct": price_volatility_pct,
        "high_low_range_pct": high_low_range_pct,
        "volume_mean": volume_mean,
        "volume_ratio_to_prev": volume_ratio_to_prev,
        "volume_trend_pct": volume_trend_pct,
        "volume_signal_pct": volume_signal_pct,
        "price_volume_corr": price_volume_corr,
        "up_bar_share": up_bar_share,
        "price_trend_bucket": price_trend_bucket,
        "volume_trend_bucket": volume_trend_bucket,
        "volume_price_state": volume_price_state,
    }


def _empty_volume_price_window_features(lookback_bars: int, *, actual_bars: int) -> dict[str, object]:
    return {
        "lookback_bar_count": int(actual_bars),
        "price_return_pct": 0.0,
        "price_sma_gap_pct": 0.0,
        "price_efficiency": 0.0,
        "price_volatility_pct": 0.0,
        "high_low_range_pct": 0.0,
        "volume_mean": 0.0,
        "volume_ratio_to_prev": 0.0,
        "volume_trend_pct": 0.0,
        "volume_signal_pct": 0.0,
        "price_volume_corr": 0.0,
        "up_bar_share": 0.0,
        "price_trend_bucket": "insufficient",
        "volume_trend_bucket": "insufficient",
        "volume_price_state": "insufficient_history",
        "requested_lookback_bars": int(lookback_bars),
    }


def _price_trend_bucket(price_return_pct: float) -> str:
    if price_return_pct >= 0.025:
        return "strong_up"
    if price_return_pct >= 0.0075:
        return "up"
    if price_return_pct <= -0.025:
        return "strong_down"
    if price_return_pct <= -0.0075:
        return "down"
    return "flat"


def _volume_trend_bucket(volume_signal_pct: float) -> str:
    if volume_signal_pct >= 0.25:
        return "strong_expand"
    if volume_signal_pct >= 0.05:
        return "expand"
    if volume_signal_pct <= -0.25:
        return "strong_contract"
    if volume_signal_pct <= -0.05:
        return "contract"
    return "flat"


def _volume_price_state(price_return_pct: float, volume_signal_pct: float) -> str:
    if price_return_pct >= 0.0075 and volume_signal_pct >= 0.05:
        return "price_up_volume_up"
    if price_return_pct >= 0.0075 and volume_signal_pct <= -0.05:
        return "price_up_volume_down"
    if price_return_pct <= -0.0075 and volume_signal_pct >= 0.05:
        return "price_down_volume_up"
    if price_return_pct <= -0.0075 and volume_signal_pct <= -0.05:
        return "price_down_volume_down"
    if abs(price_return_pct) < 0.0075 and volume_signal_pct >= 0.20:
        return "flat_volume_expand"
    if abs(price_return_pct) < 0.0075 and volume_signal_pct <= -0.20:
        return "flat_volume_contract"
    return "neutral_volume_price"


def _sell_event_type(action: str, side: str, reason: str, attack_state: object | None) -> str:
    action_upper = str(action).upper()
    side_upper = str(side).upper()
    reason_text = str(reason)
    reason_upper = reason_text.upper()
    reason_lower = reason_text.lower()
    attack_text = str(attack_state or "").upper()
    if "结构" in reason_text or "破位" in reason_text or "breakdown" in reason_lower or "SELL3" in reason_upper:
        return "structural_breakdown"
    if action_upper == "PROTECT_BREAKOUT_PROFIT" or side_upper == "SELL_BREAKOUT_PROFIT":
        return "drawdown_protection"
    if "BETA_HOLD" in reason_upper or (
        "BETA_HOLD" in attack_text and side_upper == "SELL_ATTACK_REDUCE" and action_upper == "REDUCE_ATTACK_POSITION"
    ):
        return "beta_hold_exit"
    if "派发" in reason_text or "滞涨" in reason_text or "量价" in reason_text or "volume" in reason_lower or "买卖力转弱" in reason_text:
        return "volume_distribution"
    if side_upper == "STOP_T" or action_upper == "STOP_T_WAIT":
        if "软止损" in reason_text or "只降" in reason_text:
            return "soft_stop"
        return "hard_stop"
    if action_upper == "WAIT_DAILY_WEAK" or "日线弱" in reason_text or "趋势衰退" in reason_text:
        return "trend_decay"
    if side_upper == "SELL_ATTACK_REDUCE" or action_upper == "REDUCE_ATTACK_POSITION":
        return "trend_decay"
    if side_upper == "SELL_T" or action_upper == "SELL_T_TIMING":
        return "t_sell"
    return "other_sell"


def _future_trade_bars(*, timestamp: str, bars: pd.DataFrame, horizon_bars: int) -> pd.DataFrame:
    if horizon_bars <= 0 or bars.empty:
        return bars.iloc[0:0]
    timestamps = pd.to_datetime(bars["timestamp"])
    trade_time = pd.to_datetime(timestamp)
    start = int(timestamps.searchsorted(trade_time, side="right"))
    return bars.iloc[start : start + horizon_bars]


def _first_hit_bar(values: pd.Series, threshold: float, *, direction: str) -> int | None:
    clean = values.reset_index(drop=True)
    if direction == ">=":
        hits = clean[clean >= threshold]
    elif direction == "<=":
        hits = clean[clean <= threshold]
    else:
        raise ValueError(f"unknown direction: {direction}")
    if hits.empty:
        return None
    return int(hits.index[0]) + 1


def _first_extreme_bar(values: pd.Series, extreme: float | None) -> int | None:
    if extreme is None:
        return None
    clean = values.reset_index(drop=True)
    hits = clean[clean == extreme]
    if hits.empty:
        return None
    return int(hits.index[0]) + 1


def _trade_type(side: str) -> str:
    side_upper = str(side).upper()
    if side_upper in {"BUY_BASE_TREND", "SELL_BASE_REGIME"}:
        return "rebalance"
    if side_upper == "BUY_CANDIDATE_START":
        return "candidate_start"
    if side_upper == "BUY_BACK_REVERSE_T":
        return "buyback"
    if side_upper == "SELL_REVERSE_T":
        return "reverse_sell"
    if side_upper.startswith("BUY"):
        return "buy"
    if side_upper.startswith("SELL") or side_upper.startswith("STOP"):
        return "sell_exit"
    return "other"


def _run_period_batch(
    items: list[Any],
    *,
    period: str,
    data_dir: Path,
    start_date: date,
    end_date: date,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
    fundamental_source: str,
    workers: int,
    worker_mode: str,
) -> list[PeriodBacktestRow]:
    total = len(items)
    progress_interval = max(1, min(100, total // 10 or 1))
    if workers <= 1:
        rows: list[PeriodBacktestRow] = []
        for index, item in enumerate(items, start=1):
            rows.append(
                _run_one_period(
                    item,
                    period=period,
                    data_dir=data_dir,
                    start_date=start_date,
                    end_date=end_date,
                    config=config,
                    market_filter=market_filter,
                    fundamental_source=fundamental_source,
                )
            )
            if index == total or index % progress_interval == 0:
                print(f"{period} {start_date}..{end_date}: {index}/{total}", flush=True)
        return rows
    print(f"{period} {start_date}..{end_date}: 0/{total}", flush=True)
    rows_by_symbol: dict[str, PeriodBacktestRow] = {}
    executor = _create_executor(workers=workers, worker_mode=worker_mode)
    futures = {
        executor.submit(
            _run_one_period,
            item,
            period=period,
            data_dir=data_dir,
            start_date=start_date,
            end_date=end_date,
            config=config,
            market_filter=market_filter,
            fundamental_source=fundamental_source,
        ): item
        for item in items
    }
    try:
        completed = 0
        for future in as_completed(futures):
            completed += 1
            item = futures[future]
            try:
                rows_by_symbol[item.symbol] = future.result()
            except Exception as exc:  # noqa: BLE001
                rows_by_symbol[item.symbol] = PeriodBacktestRow(
                    symbol=item.symbol,
                    name=item.name,
                    industry=item.industry,
                    period=period,
                    status="failed",
                    message=f"{type(exc).__name__}: {exc}",
                )
            if completed == total or completed % progress_interval == 0:
                print(f"{period} {start_date}..{end_date}: {completed}/{total}", flush=True)
    finally:
        executor.shutdown(wait=True, cancel_futures=False)
    return [rows_by_symbol[item.symbol] for item in items]


def _run_one_period(
    item: Any,
    *,
    period: str,
    data_dir: Path,
    start_date: date,
    end_date: date,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
    fundamental_source: str,
) -> PeriodBacktestRow:
    try:
        bars = _load_period_bars(item.symbol, data_dir=data_dir, start_date=start_date, end_date=end_date)
        if len(bars) <= config.min_lookback_bars + 1:
            raise ValueError(f"only {len(bars)} bars; need more than {config.min_lookback_bars + 1}")
        profile = profile_for_watchlist_item(item)
        resolver = build_fundamental_resolver(profile, source=fundamental_source)
        effective_config = replace(
            config,
            initial_base_position_pct=min(config.initial_base_position_pct, profile.default_base_position_pct),
            signal_cache_tag=f"industry_{fundamental_source}",
        )
        result = run_cosco_dividend_t_backtest(
            bars,
            config=effective_config,
            engine=CoscoTimingEngine(profile=profile, fundamental_resolver=resolver),
            market_filter=market_filter,
        )
        gate_count = sum(result.gate_counts.values())
        position_stats = _position_stats(result.equity_curve)
        signal_feature_stats = _signal_feature_stats(
            item.symbol,
            config=effective_config,
            start_date=start_date,
            end_date=end_date,
        )
        return PeriodBacktestRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            period=period,
            status="ok",
            rows=result.rows,
            start=result.start,
            end=result.end,
            total_return=result.total_return,
            benchmark_return=result.benchmark_return,
            risk_matched_benchmark_return=position_stats["risk_matched_benchmark_return"],
            excess_return=result.excess_return,
            max_drawdown=result.max_drawdown,
            trade_count=result.trade_count,
            completed_trades=result.completed_trades,
            win_rate=result.win_rate,
            gate_count=gate_count,
            buy_signal_count=result.action_counts.get("BUY_T_TIMING", 0),
            breakout_signal_count=result.action_counts.get("BREAKOUT_BUY_TIMING", 0),
            breakout_watch_count=result.action_counts.get("WATCH_BREAKOUT_NEXT_DAY", 0),
            risk_on_target_add_count=result.action_counts.get("RISK_ON_TARGET_ADD", 0),
            sell_signal_count=result.action_counts.get("SELL_T_TIMING", 0),
            buyback_trade_count=result.buyback_trade_count,
            market_caution_gate_count=result.gate_counts.get("WAIT_MARKET_CAUTION", 0),
            stop_signal_count=result.action_counts.get("STOP_T_WAIT", 0),
            defensive_mode_count=result.strategy_mode_counts.get("defensive", 0),
            balanced_mode_count=result.strategy_mode_counts.get("balanced", 0),
            offensive_mode_count=result.strategy_mode_counts.get("offensive", 0),
            risk_on_count=position_stats["risk_on_count"],
            risk_on_share=position_stats["risk_on_share"],
            market_score_avg=position_stats["market_score_avg"],
            market_trend_score_avg=position_stats["market_trend_score_avg"],
            market_breadth_score_avg=position_stats["market_breadth_score_avg"],
            market_amount_score_avg=position_stats["market_amount_score_avg"],
            market_limit_structure_score_avg=position_stats["market_limit_structure_score_avg"],
            market_industry_diffusion_score_avg=position_stats["market_industry_diffusion_score_avg"],
            market_model_state_score_avg=position_stats["market_model_state_score_avg"],
            model_holding_win_rate_avg=position_stats["model_holding_win_rate_avg"],
            model_holding_profit_spread_avg=position_stats["model_holding_profit_spread_avg"],
            model_new_buy_success_rate_avg=position_stats["model_new_buy_success_rate_avg"],
            beta_hold_entry_count=position_stats["beta_hold_entry_count"],
            beta_hold_bar_count=position_stats["beta_hold_bar_count"],
            beta_hold_share=position_stats["beta_hold_share"],
            wait_beta_hold_count=result.action_counts.get("WAIT_BETA_HOLD", 0),
            full_position_bar_count=position_stats["full_position_bar_count"],
            full_position_share=position_stats["full_position_share"],
            risk_on_after_1d_avg_position_pct=position_stats["risk_on_after_1d_avg_position_pct"],
            risk_on_after_3d_avg_position_pct=position_stats["risk_on_after_3d_avg_position_pct"],
            risk_on_after_5d_avg_position_pct=position_stats["risk_on_after_5d_avg_position_pct"],
            risk_on_after_10d_avg_position_pct=position_stats["risk_on_after_10d_avg_position_pct"],
            strong_confirm_episode_count=position_stats["strong_confirm_episode_count"],
            strong_confirm_to_exit_avg_bars=position_stats["strong_confirm_to_exit_avg_bars"],
            beta_hold_episode_avg_bars=position_stats["beta_hold_episode_avg_bars"],
            avg_total_position_pct=position_stats["avg_total_position_pct"],
            max_total_position_pct_realized=position_stats["max_total_position_pct_realized"],
            avg_active_position_pct=position_stats["avg_active_position_pct"],
            max_active_position_pct=position_stats["max_active_position_pct"],
            buy3_count=signal_feature_stats["buy3_count"],
            breakout_confirmed_count=signal_feature_stats["breakout_confirmed_count"],
            confirmed_flow_count=signal_feature_stats["confirmed_flow_count"],
            confirmed_flow_share=signal_feature_stats["confirmed_flow_share"],
            avg_force_ratio=signal_feature_stats["avg_force_ratio"],
            avg_buy_force_ratio=signal_feature_stats["avg_buy_force_ratio"],
            force_suppression_count=signal_feature_stats["force_suppression_count"],
            force_suppression_share=signal_feature_stats["force_suppression_share"],
            volume_price_score_avg=signal_feature_stats["volume_price_score_avg"],
            volume_breakout_count=signal_feature_stats["volume_breakout_count"],
            low_volume_pullback_count=signal_feature_stats["low_volume_pullback_count"],
            high_volume_stall_count=signal_feature_stats["high_volume_stall_count"],
            price_up_volume_down_count=signal_feature_stats["price_up_volume_down_count"],
            vwap_support_count=signal_feature_stats["vwap_support_count"],
            post_breakout_volume_persistence_count=signal_feature_stats["post_breakout_volume_persistence_count"],
            cache_hits=result.cache_hits,
            cache_misses=result.cache_misses,
        )
    except Exception as exc:  # noqa: BLE001
        return PeriodBacktestRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            period=period,
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
        )


def _position_stats(equity_curve: Iterable[Any]) -> dict[str, float | int]:
    total_positions: list[float] = []
    active_positions: list[float] = []
    market_metrics: dict[str, list[float]] = {
        "market_score_avg": [],
        "market_trend_score_avg": [],
        "market_breadth_score_avg": [],
        "market_amount_score_avg": [],
        "market_limit_structure_score_avg": [],
        "market_industry_diffusion_score_avg": [],
        "market_model_state_score_avg": [],
        "model_holding_win_rate_avg": [],
        "model_holding_profit_spread_avg": [],
        "model_new_buy_success_rate_avg": [],
    }
    records: list[dict[str, Any]] = []
    risk_on_count = 0
    beta_hold_bar_count = 0
    full_position_bar_count = 0
    point_count = 0
    risk_matched_curve = 1.0
    risk_matched_values: list[float] = []
    previous_close: float | None = None
    previous_total_position = 0.0
    for point in equity_curve:
        equity = float(getattr(point, "equity", 0.0) or 0.0)
        close = float(getattr(point, "close", 0.0) or 0.0)
        if equity <= 0 or close <= 0:
            continue
        base_shares = int(getattr(point, "base_shares", 0) or 0)
        t_shares = int(getattr(point, "t_shares", 0) or 0)
        total_position = ((base_shares + t_shares) * close) / equity
        active_position = (t_shares * close) / equity
        if previous_close is not None and previous_close > 0.0:
            bar_return = close / previous_close - 1.0
            risk_matched_curve *= max(0.0, 1.0 + min(max(previous_total_position, 0.0), 1.0) * bar_return)
        risk_matched_values.append(risk_matched_curve)
        previous_close = close
        previous_total_position = total_position
        market_environment_state = str(getattr(point, "market_environment_state", ""))
        attack_state = str(getattr(point, "attack_state", ""))
        is_risk_on = market_environment_state == "RISK_ON"
        is_beta_hold = attack_state == "BETA_HOLD"
        is_full_position = total_position >= 0.95
        total_positions.append(total_position)
        active_positions.append(active_position)
        _append_market_metric(market_metrics, "market_score_avg", point, "market_environment_score")
        _append_market_metric(market_metrics, "market_trend_score_avg", point, "market_trend_score")
        _append_market_metric(market_metrics, "market_breadth_score_avg", point, "market_breadth_score")
        _append_market_metric(market_metrics, "market_amount_score_avg", point, "market_amount_score")
        _append_market_metric(market_metrics, "market_limit_structure_score_avg", point, "market_limit_structure_score")
        _append_market_metric(market_metrics, "market_industry_diffusion_score_avg", point, "market_industry_diffusion_score")
        _append_market_metric(market_metrics, "market_model_state_score_avg", point, "market_model_state_score")
        _append_market_metric(market_metrics, "model_holding_win_rate_avg", point, "model_holding_win_rate")
        _append_market_metric(market_metrics, "model_holding_profit_spread_avg", point, "model_holding_profit_spread")
        _append_market_metric(market_metrics, "model_new_buy_success_rate_avg", point, "model_new_buy_success_rate")
        records.append(
            {
                "total_position": total_position,
                "is_risk_on": is_risk_on,
                "attack_state": attack_state,
                "is_beta_hold": is_beta_hold,
                "is_strong_confirm": attack_state in {"BETA_HOLD", "FULL_ATTACK", "CONFIRMED"},
            }
        )
        risk_on_count += int(is_risk_on)
        beta_hold_bar_count += int(is_beta_hold)
        full_position_bar_count += int(is_full_position)
        point_count += 1
    beta_hold_lengths = _episode_lengths(records, key="is_beta_hold")
    strong_confirm_lengths = _episode_lengths(records, key="is_strong_confirm")
    risk_on_after_positions = {
        horizon_days: _average_position_after_risk_on(records, horizon_bars=horizon_days * 48)
        for horizon_days in (1, 3, 5, 10)
    }
    return {
        "risk_on_count": risk_on_count,
        "risk_on_share": _safe_ratio(risk_on_count, point_count),
        "beta_hold_entry_count": len(beta_hold_lengths),
        "beta_hold_bar_count": beta_hold_bar_count,
        "beta_hold_share": _safe_ratio(beta_hold_bar_count, point_count),
        "full_position_bar_count": full_position_bar_count,
        "full_position_share": _safe_ratio(full_position_bar_count, point_count),
        "risk_on_after_1d_avg_position_pct": risk_on_after_positions[1],
        "risk_on_after_3d_avg_position_pct": risk_on_after_positions[3],
        "risk_on_after_5d_avg_position_pct": risk_on_after_positions[5],
        "risk_on_after_10d_avg_position_pct": risk_on_after_positions[10],
        "strong_confirm_episode_count": len(strong_confirm_lengths),
        "strong_confirm_to_exit_avg_bars": float(sum(strong_confirm_lengths) / len(strong_confirm_lengths)) if strong_confirm_lengths else 0.0,
        "beta_hold_episode_avg_bars": float(sum(beta_hold_lengths) / len(beta_hold_lengths)) if beta_hold_lengths else 0.0,
        "avg_total_position_pct": float(sum(total_positions) / len(total_positions)) if total_positions else 0.0,
        "max_total_position_pct_realized": float(max(total_positions)) if total_positions else 0.0,
        "avg_active_position_pct": float(sum(active_positions) / len(active_positions)) if active_positions else 0.0,
        "max_active_position_pct": float(max(active_positions)) if active_positions else 0.0,
        "risk_matched_benchmark_return": float(risk_matched_values[-1] - 1.0) if risk_matched_values else 0.0,
        "risk_matched_benchmark_max_drawdown": _max_drawdown(pd.Series(risk_matched_values)) if risk_matched_values else 0.0,
        **{key: _mean_or_zero(values) for key, values in market_metrics.items()},
    }


def _append_market_metric(metrics: dict[str, list[float]], key: str, point: Any, attr: str) -> None:
    value = getattr(point, attr, None)
    if value is None:
        return
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return
    metrics[key].append(parsed)


def _mean_or_zero(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _episode_lengths(records: list[dict[str, Any]], *, key: str) -> list[int]:
    lengths: list[int] = []
    current = 0
    for record in records:
        if bool(record.get(key)):
            current += 1
        elif current > 0:
            lengths.append(current)
            current = 0
    if current > 0:
        lengths.append(current)
    return lengths


def _average_position_after_risk_on(records: list[dict[str, Any]], *, horizon_bars: int) -> float:
    if not records or horizon_bars <= 0:
        return 0.0
    episode_averages: list[float] = []
    for index, record in enumerate(records):
        if not bool(record["is_risk_on"]):
            continue
        if index > 0 and bool(records[index - 1]["is_risk_on"]):
            continue
        segment = records[index : min(index + horizon_bars, len(records))]
        positions = [float(item["total_position"]) for item in segment]
        if positions:
            episode_averages.append(float(sum(positions) / len(positions)))
    return float(sum(episode_averages) / len(episode_averages)) if episode_averages else 0.0


def _signal_feature_stats(
    symbol: str,
    *,
    config: DividendTBacktestConfig,
    start_date: date,
    end_date: date,
) -> dict[str, float | int]:
    defaults: dict[str, float | int] = {
        "buy3_count": 0,
        "breakout_confirmed_count": 0,
        "confirmed_flow_count": 0,
        "confirmed_flow_share": 0.0,
        "avg_force_ratio": 0.0,
        "avg_buy_force_ratio": 0.0,
        "force_suppression_count": 0,
        "force_suppression_share": 0.0,
        "volume_price_score_avg": 0.0,
        "volume_breakout_count": 0,
        "low_volume_pullback_count": 0,
        "high_volume_stall_count": 0,
        "price_up_volume_down_count": 0,
        "vwap_support_count": 0,
        "post_breakout_volume_persistence_count": 0,
    }
    cache = BacktestSignalCache.for_symbol(symbol, config)
    if cache is None or not cache.path.exists():
        return defaults
    data = pd.read_csv(cache.path)
    if data.empty or "timestamp" not in data.columns:
        return defaults
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce")
    trade_dates = timestamps.dt.date
    data = data[(trade_dates >= start_date) & (trade_dates <= end_date)].copy()
    if data.empty:
        return defaults

    action = data.get("action", pd.Series("", index=data.index)).astype(str)
    is_buy = action.isin({"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"})
    force_ratio = pd.to_numeric(data.get("force_ratio", 1.0), errors="coerce").fillna(1.0)
    buy_force_ratio = force_ratio[is_buy]
    confirmed_flow = _confirmed_flow_mask(data)
    force_suppression = is_buy & (force_ratio < 1.0)
    return {
        "buy3_count": int((data.get("chan_buy_point_type", pd.Series("", index=data.index)).astype(str) == "buy3").sum()),
        "breakout_confirmed_count": int(_boolish_series(data.get("breakout_confirmed", pd.Series(False, index=data.index))).sum()),
        "confirmed_flow_count": int(confirmed_flow.sum()),
        "confirmed_flow_share": _safe_ratio(int(confirmed_flow.sum()), len(data)),
        "avg_force_ratio": float(force_ratio.mean()),
        "avg_buy_force_ratio": float(buy_force_ratio.mean()) if not buy_force_ratio.empty else 0.0,
        "force_suppression_count": int(force_suppression.sum()),
        "force_suppression_share": _safe_ratio(int(force_suppression.sum()), int(is_buy.sum())),
        "volume_price_score_avg": _numeric_mean(data, "volume_price_score"),
        "volume_breakout_count": _threshold_count(data, "volume_breakout_score", 70.0),
        "low_volume_pullback_count": _threshold_count(data, "low_volume_pullback_score", 70.0),
        "high_volume_stall_count": _threshold_count(data, "high_volume_stall_score", 72.0),
        "price_up_volume_down_count": _threshold_count(data, "price_up_volume_down_score", 76.0),
        "vwap_support_count": _threshold_count(data, "vwap_support_score", 68.0),
        "post_breakout_volume_persistence_count": _threshold_count(data, "post_breakout_volume_persistence_score", 70.0),
    }


def _confirmed_flow_mask(data: pd.DataFrame) -> pd.Series:
    state = data.get("capital_flow_confirmation_state", pd.Series("", index=data.index)).astype(str)
    score = pd.to_numeric(data.get("capital_flow_confirmation_score", 0.0), errors="coerce").fillna(0.0)
    confidence = pd.to_numeric(data.get("capital_flow_confidence", 0.0), errors="coerce").fillna(0.0)
    return (state == "CONFIRMED_INFLOW") | ((score >= 66.0) & (confidence >= 0.50))


def _boolish_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"1", "true", "yes"})


def _numeric_mean(data: pd.DataFrame, column: str) -> float:
    if column not in data.columns:
        return 0.0
    values = pd.to_numeric(data[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def _threshold_count(data: pd.DataFrame, column: str, threshold: float) -> int:
    if column not in data.columns:
        return 0
    values = pd.to_numeric(data[column], errors="coerce").fillna(0.0)
    return int((values >= threshold).sum())


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    denominator = float(denominator)
    if denominator <= 0:
        return 0.0
    return float(numerator) / denominator


def _run_curve_batch(
    items: list[Any],
    *,
    data_dir: Path,
    start_date: date,
    end_date: date,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
    fundamental_source: str,
    export_trades: bool,
    trade_quality_horizon_bars: int,
    trade_quality_buy_up_threshold_pct: float,
    trade_quality_stop_loss_threshold_pct: float,
    trade_quality_sell_drawdown_threshold_pct: float,
    trade_quality_sell_fly_threshold_pct: float,
    buy_event_horizon_bars: tuple[int, ...],
    sell_event_horizon_bars: tuple[int, ...],
    volume_price_event_window_bars: tuple[int, ...],
    sell_event_drawdown_threshold_pct: float,
    sell_event_rally_threshold_pct: float,
    workers: int,
    worker_mode: str,
) -> list[CurvePayload]:
    total = len(items)
    progress_interval = max(1, min(50, total // 5 or 1))
    print(f"curve {start_date}..{end_date}: 0/{total}", flush=True)
    executor = _create_executor(workers=workers, worker_mode=worker_mode)
    futures = {
        executor.submit(
            _run_one_curve,
            item,
            data_dir=data_dir,
            start_date=start_date,
            end_date=end_date,
            config=config,
            market_filter=market_filter,
            fundamental_source=fundamental_source,
            export_trades=export_trades,
            trade_quality_horizon_bars=trade_quality_horizon_bars,
            trade_quality_buy_up_threshold_pct=trade_quality_buy_up_threshold_pct,
            trade_quality_stop_loss_threshold_pct=trade_quality_stop_loss_threshold_pct,
            trade_quality_sell_drawdown_threshold_pct=trade_quality_sell_drawdown_threshold_pct,
            trade_quality_sell_fly_threshold_pct=trade_quality_sell_fly_threshold_pct,
            buy_event_horizon_bars=buy_event_horizon_bars,
            sell_event_horizon_bars=sell_event_horizon_bars,
            volume_price_event_window_bars=volume_price_event_window_bars,
            sell_event_drawdown_threshold_pct=sell_event_drawdown_threshold_pct,
            sell_event_rally_threshold_pct=sell_event_rally_threshold_pct,
        ): item
        for item in items
    }
    payloads: dict[str, CurvePayload] = {}
    try:
        completed = 0
        for future in as_completed(futures):
            completed += 1
            item = futures[future]
            try:
                payloads[item.symbol] = future.result()
            except Exception as exc:  # noqa: BLE001
                payloads[item.symbol] = CurvePayload(symbol=item.symbol, status="failed", message=f"{type(exc).__name__}: {exc}")
            if completed == total or completed % progress_interval == 0:
                print(f"curve {start_date}..{end_date}: {completed}/{total}", flush=True)
    finally:
        executor.shutdown(wait=True, cancel_futures=False)
    return [payloads[item.symbol] for item in items]


def _run_one_curve(
    item: Any,
    *,
    data_dir: Path,
    start_date: date,
    end_date: date,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
    fundamental_source: str,
    export_trades: bool,
    trade_quality_horizon_bars: int,
    trade_quality_buy_up_threshold_pct: float,
    trade_quality_stop_loss_threshold_pct: float,
    trade_quality_sell_drawdown_threshold_pct: float,
    trade_quality_sell_fly_threshold_pct: float,
    buy_event_horizon_bars: tuple[int, ...],
    sell_event_horizon_bars: tuple[int, ...],
    volume_price_event_window_bars: tuple[int, ...],
    sell_event_drawdown_threshold_pct: float,
    sell_event_rally_threshold_pct: float,
) -> CurvePayload:
    try:
        bars = _load_period_bars(item.symbol, data_dir=data_dir, start_date=start_date, end_date=end_date)
        profile = profile_for_watchlist_item(item)
        resolver = build_fundamental_resolver(profile, source=fundamental_source)
        effective_config = replace(
            config,
            initial_base_position_pct=min(config.initial_base_position_pct, profile.default_base_position_pct),
            signal_cache_tag=f"industry_{fundamental_source}",
        )
        result = run_cosco_dividend_t_backtest(
            bars,
            config=effective_config,
            engine=CoscoTimingEngine(profile=profile, fundamental_resolver=resolver),
            market_filter=market_filter,
        )
        first_open = float(bars["open"].iloc[0])
        points = _curve_points_with_risk_matched(result.equity_curve, initial_cash=float(result.initial_cash), first_open=first_open)
        trade_rows: tuple[dict[str, object], ...] = ()
        trade_quality_rows: tuple[dict[str, object], ...] = ()
        buy_event_rows: tuple[dict[str, object], ...] = ()
        sell_event_rows: tuple[dict[str, object], ...] = ()
        volume_price_window_rows: tuple[dict[str, object], ...] = ()
        if export_trades:
            point_lookup = {point.timestamp: point for point in result.equity_curve}
            trade_rows = tuple(
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "industry": item.industry,
                    "trade_index": index,
                    **trade.to_dict(),
                }
                for index, trade in enumerate(result.trades, start=1)
            )
            trade_quality_rows = tuple(
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "industry": item.industry,
                    "trade_index": index,
                    **trade.to_dict(),
                    **_evaluate_trade_quality(
                        timestamp=trade.timestamp,
                        side=trade.side,
                        price=trade.price,
                        bars=bars,
                        horizon_bars=trade_quality_horizon_bars,
                        buy_up_threshold_pct=trade_quality_buy_up_threshold_pct,
                        stop_loss_threshold_pct=trade_quality_stop_loss_threshold_pct,
                        sell_drawdown_threshold_pct=trade_quality_sell_drawdown_threshold_pct,
                        sell_fly_threshold_pct=trade_quality_sell_fly_threshold_pct,
                    ),
                }
                for index, trade in enumerate(result.trades, start=1)
            )
            buy_event_rows = tuple(
                row
                for index, trade in enumerate(result.trades, start=1)
                for row in _evaluate_buy_event_study(
                    symbol=item.symbol,
                    name=item.name,
                    industry=item.industry,
                    trade_index=index,
                    trade=trade,
                    bars=bars,
                    horizon_bars=buy_event_horizon_bars,
                    point_lookup=point_lookup,
                )
            )
            sell_event_rows = tuple(
                row
                for index, trade in enumerate(result.trades, start=1)
                for row in _evaluate_sell_event_study(
                    symbol=item.symbol,
                    name=item.name,
                    industry=item.industry,
                    trade_index=index,
                    trade=trade,
                    bars=bars,
                    horizon_bars=sell_event_horizon_bars,
                    point_lookup=point_lookup,
                    drawdown_threshold_pct=sell_event_drawdown_threshold_pct,
                    rally_threshold_pct=sell_event_rally_threshold_pct,
                )
            )
            volume_price_window_rows = tuple(
                row
                for index, trade in enumerate(result.trades, start=1)
                for row in _evaluate_volume_price_window_study(
                    symbol=item.symbol,
                    name=item.name,
                    industry=item.industry,
                    trade_index=index,
                    trade=trade,
                    bars=bars,
                    horizon_bars=tuple(sorted(set(buy_event_horizon_bars + sell_event_horizon_bars))),
                    lookback_window_bars=volume_price_event_window_bars,
                    point_lookup=point_lookup,
                    sell_event_drawdown_threshold_pct=sell_event_drawdown_threshold_pct,
                    sell_event_rally_threshold_pct=sell_event_rally_threshold_pct,
                )
            )
        return CurvePayload(
            symbol=item.symbol,
            status="ok",
            points=points,
            trades=trade_rows,
            trade_quality=trade_quality_rows,
            buy_event_study=buy_event_rows,
            sell_event_study=sell_event_rows,
            volume_price_window_study=volume_price_window_rows,
        )
    except Exception as exc:  # noqa: BLE001
        return CurvePayload(symbol=item.symbol, status="failed", message=f"{type(exc).__name__}: {exc}")


def _curve_points_with_risk_matched(
    equity_curve: Iterable[Any],
    *,
    initial_cash: float,
    first_open: float,
) -> tuple[tuple[float | str, ...], ...]:
    points: list[tuple[float | str, ...]] = []
    risk_matched_curve = 1.0
    previous_close: float | None = None
    previous_total_position = 0.0
    for point in equity_curve:
        close = float(getattr(point, "close", 0.0) or 0.0)
        equity = float(getattr(point, "equity", 0.0) or 0.0)
        if previous_close is not None and previous_close > 0.0 and close > 0.0:
            bar_return = close / previous_close - 1.0
            risk_matched_curve *= max(0.0, 1.0 + min(max(previous_total_position, 0.0), 1.0) * bar_return)
        total_position = 0.0
        if equity > 0.0 and close > 0.0:
            total_shares = int(getattr(point, "base_shares", 0) or 0) + int(getattr(point, "t_shares", 0) or 0)
            total_position = (total_shares * close) / equity
        points.append(
            (
                str(getattr(point, "timestamp", "")),
                equity / initial_cash if initial_cash > 0.0 else 1.0,
                close / first_open if first_open > 0.0 else 1.0,
                risk_matched_curve,
            )
        )
        if close > 0.0:
            previous_close = close
            previous_total_position = total_position
    return tuple(points)


def _create_executor(*, workers: int, worker_mode: str) -> ProcessPoolExecutor | ThreadPoolExecutor:
    if worker_mode == "thread":
        return ThreadPoolExecutor(max_workers=workers)
    try:
        return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("fork"))
    except (OSError, PermissionError):
        return ThreadPoolExecutor(max_workers=workers)


def _load_period_bars(symbol: str, *, data_dir: Path, start_date: date, end_date: date) -> Any:
    bars = load_5min_bars_path(data_dir, symbol=symbol)
    trade_dates = pd.to_datetime(bars["timestamp"]).dt.date
    return bars[(trade_dates >= start_date) & (trade_dates <= end_date)].copy().reset_index(drop=True)


def _build_period_market_filter(
    mode: str,
    *,
    items: list[Any],
    data_dir: Path,
    start_date: date,
    end_date: date,
    lookback_days: int = 0,
) -> MarketEnvironmentFilter | None:
    if mode == "none":
        return None
    if mode != "equal-weight":
        raise ValueError(f"unsupported market filter: {mode}")
    filter_start_date = _market_filter_start_date(start_date, lookback_days=lookback_days)
    daily_frames: list[pd.DataFrame] = []
    for item in items:
        try:
            bars = _load_period_bars(item.symbol, data_dir=data_dir, start_date=filter_start_date, end_date=end_date)
        except FileNotFoundError:
            continue
        if bars.empty:
            continue
        daily = _daily_market_filter_frame(bars, symbol=item.symbol, industry=item.industry)
        if daily.empty or float(daily["close"].iloc[0]) <= 0:
            continue
        daily_frames.append(daily)
    if not daily_frames:
        raise ValueError(f"no local CSV files available to build market filter in {data_dir}")
    frame = pd.concat(daily_frames, ignore_index=True)
    return build_market_environment_filter(frame, name=f"composite_equal_weight:{len(daily_frames)}")


def _daily_market_filter_frame(bars: pd.DataFrame, *, symbol: str, industry: str) -> pd.DataFrame:
    data = bars.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["trade_date"] = data["timestamp"].dt.date
    if "amount" not in data.columns:
        data["amount"] = pd.to_numeric(data["close"], errors="coerce") * pd.to_numeric(data.get("volume", 0.0), errors="coerce")
    daily = (
        data.sort_values("timestamp")
        .groupby("trade_date", sort=True)
        .agg(
            close=("close", "last"),
            amount=("amount", "sum"),
        )
        .reset_index()
    )
    daily["timestamp"] = [pd.Timestamp(trade_date) + pd.Timedelta(hours=15) for trade_date in daily["trade_date"]]
    daily["symbol"] = symbol
    daily["industry"] = industry or "UNKNOWN"
    return daily[["timestamp", "symbol", "industry", "close", "amount"]]


def _market_filter_start_date(start_date: date, *, lookback_days: int) -> date:
    return start_date - timedelta(days=max(0, lookback_days))


def _rows_to_frame(rows: Iterable[PeriodBacktestRow]) -> pd.DataFrame:
    return pd.DataFrame([asdict(row) for row in rows])


def _build_return_leakage_attribution(valid_frame: pd.DataFrame, ranked: pd.DataFrame) -> pd.DataFrame:
    if valid_frame.empty:
        return pd.DataFrame()
    data = valid_frame[valid_frame["status"] == "ok"].copy()
    if data.empty:
        return pd.DataFrame()
    numeric_columns = [
        "total_return",
        "benchmark_return",
        "buy_signal_count",
        "breakout_signal_count",
        "risk_on_target_add_count",
        "sell_signal_count",
        "stop_signal_count",
        "risk_on_share",
        "beta_hold_entry_count",
        "beta_hold_bar_count",
        "beta_hold_share",
        "wait_beta_hold_count",
        "full_position_bar_count",
        "full_position_share",
        "risk_on_after_1d_avg_position_pct",
        "risk_on_after_3d_avg_position_pct",
        "risk_on_after_5d_avg_position_pct",
        "risk_on_after_10d_avg_position_pct",
        "strong_confirm_episode_count",
        "strong_confirm_to_exit_avg_bars",
        "beta_hold_episode_avg_bars",
        "avg_total_position_pct",
        "max_total_position_pct_realized",
        "avg_active_position_pct",
        "max_active_position_pct",
        "buy3_count",
        "breakout_confirmed_count",
        "confirmed_flow_count",
        "confirmed_flow_share",
        "avg_force_ratio",
        "avg_buy_force_ratio",
        "force_suppression_count",
        "force_suppression_share",
        "volume_price_score_avg",
        "volume_breakout_count",
        "low_volume_pullback_count",
        "high_volume_stall_count",
        "price_up_volume_down_count",
        "vwap_support_count",
        "post_breakout_volume_persistence_count",
        "rows",
    ]
    for column in numeric_columns:
        if column not in data.columns:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0.0)
    data = data[data["benchmark_return"] > 0].copy()
    if data.empty:
        return pd.DataFrame()

    rank_columns = [column for column in ["window_id", "symbol", "rank", "screen_score"] if column in ranked.columns]
    if {"window_id", "symbol"}.issubset(rank_columns):
        data = data.merge(ranked[rank_columns].drop_duplicates(["window_id", "symbol"]), on=["window_id", "symbol"], how="left")
    else:
        data["rank"] = pd.NA
        data["screen_score"] = pd.NA

    data["capture_rate"] = (data["total_return"] / data["benchmark_return"]).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    data["missed_return"] = data["benchmark_return"] - data["total_return"]
    data["signal_count"] = data["buy_signal_count"] + data["breakout_signal_count"]
    data["target_add_density"] = data["risk_on_target_add_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    data["early_exit_count"] = data["sell_signal_count"] + data["stop_signal_count"]
    data["is_risk_on"] = data["risk_on_share"] >= 0.20
    data["has_buy3_or_breakout"] = (
        (data["buy3_count"] > 0)
        | (data["breakout_confirmed_count"] > 0)
        | (data["breakout_signal_count"] > 0)
        | (data["volume_breakout_count"] > 0)
    )
    data["has_funding_confirmation"] = data["confirmed_flow_count"] > 0
    data["non_force_confirmation_count"] = (
        (data["buy3_count"] > 0).astype(int)
        + ((data["breakout_confirmed_count"] > 0) | (data["breakout_signal_count"] > 0)).astype(int)
        + (data["confirmed_flow_count"] > 0).astype(int)
        + (
            (data["volume_breakout_count"] > 0)
            | (data["post_breakout_volume_persistence_count"] > 0)
            | (data["vwap_support_count"] > 0)
            | (data["low_volume_pullback_count"] > 0)
        ).astype(int)
    )
    data["force_ratio_raw_suppressed"] = (data["force_suppression_share"] >= 0.50) | (
        (data["avg_buy_force_ratio"] > 0) & (data["avg_buy_force_ratio"] < 1.0)
    )
    data["force_ratio_suppressed"] = data["force_ratio_raw_suppressed"] & (data["non_force_confirmation_count"] <= 1)
    data["low_position_flag"] = (data["max_total_position_pct_realized"] < 0.35) | (data["avg_total_position_pct"] < 0.18)
    data["risk_on_position_underbuilt_flag"] = (
        data["is_risk_on"]
        & (data["non_force_confirmation_count"] >= 2)
        & data["low_position_flag"]
        & (data["capture_rate"] < 0.45)
    )
    data["early_exit_flag"] = (data["early_exit_count"] >= data["signal_count"].clip(lower=1) * 3) & (data["capture_rate"] < 0.35)
    data["volume_price_constructive_count"] = (
        data["volume_breakout_count"]
        + data["low_volume_pullback_count"]
        + data["vwap_support_count"]
        + data["post_breakout_volume_persistence_count"]
    )
    data["volume_price_risk_flag"] = (data["high_volume_stall_count"] > 0) | (data["price_up_volume_down_count"] > 0)
    data["volume_price_weak_follow_flag"] = (
        (data["capture_rate"] < 0.45)
        & data["has_buy3_or_breakout"]
        & (data["volume_price_constructive_count"] <= 1)
        & (data["volume_price_score_avg"] < 70.0)
    )
    data["primary_leak_reason"] = data.apply(_primary_leak_reason, axis=1)
    data["volume_price_secondary_reason"] = data.apply(_volume_price_secondary_reason, axis=1)
    data["attribution_note"] = data.apply(_attribution_note, axis=1)

    columns = [
        "window_id",
        "valid_start",
        "valid_end",
        "rank",
        "symbol",
        "name",
        "industry",
        "total_return",
        "benchmark_return",
        "capture_rate",
        "missed_return",
        "is_risk_on",
        "risk_on_share",
        "beta_hold_entry_count",
        "beta_hold_bar_count",
        "beta_hold_share",
        "wait_beta_hold_count",
        "full_position_bar_count",
        "full_position_share",
        "risk_on_after_1d_avg_position_pct",
        "risk_on_after_3d_avg_position_pct",
        "risk_on_after_5d_avg_position_pct",
        "risk_on_after_10d_avg_position_pct",
        "strong_confirm_episode_count",
        "strong_confirm_to_exit_avg_bars",
        "beta_hold_episode_avg_bars",
        "has_buy3_or_breakout",
        "buy3_count",
        "breakout_confirmed_count",
        "breakout_signal_count",
        "volume_breakout_count",
        "risk_on_target_add_count",
        "target_add_density",
        "has_funding_confirmation",
        "confirmed_flow_count",
        "confirmed_flow_share",
        "non_force_confirmation_count",
        "force_ratio_suppressed",
        "force_ratio_raw_suppressed",
        "avg_force_ratio",
        "avg_buy_force_ratio",
        "force_suppression_count",
        "force_suppression_share",
        "early_exit_flag",
        "early_exit_count",
        "sell_signal_count",
        "stop_signal_count",
        "avg_total_position_pct",
        "max_total_position_pct_realized",
        "avg_active_position_pct",
        "max_active_position_pct",
        "volume_price_score_avg",
        "low_volume_pullback_count",
        "high_volume_stall_count",
        "price_up_volume_down_count",
        "vwap_support_count",
        "post_breakout_volume_persistence_count",
        "primary_leak_reason",
        "volume_price_secondary_reason",
        "attribution_note",
    ]
    for column in columns:
        if column not in data.columns:
            data[column] = pd.NA
    return data.sort_values(["missed_return", "benchmark_return"], ascending=[False, False])[columns].reset_index(drop=True)


def _primary_leak_reason(row: pd.Series) -> str:
    if not bool(row["is_risk_on"]):
        return "market_not_risk_on"
    if not bool(row["has_buy3_or_breakout"]) and not bool(row["has_funding_confirmation"]):
        return "no_attack_trigger"
    if bool(row["risk_on_position_underbuilt_flag"]):
        return "risk_on_position_underbuilt"
    if bool(row["force_ratio_suppressed"]) and bool(row["low_position_flag"]):
        return "force_ratio_position_suppressed"
    if bool(row["volume_price_risk_flag"]) or bool(row["volume_price_weak_follow_flag"]):
        return "volume_price_distribution_or_weak_follow"
    if bool(row["early_exit_flag"]):
        return "sell_stop_early_exit"
    if bool(row["low_position_flag"]):
        return "position_too_low"
    return "hold_extension_or_selection_gap"


def _volume_price_secondary_reason(row: pd.Series) -> str:
    if bool(row["high_volume_stall_count"] > 0) and bool(row["price_up_volume_down_count"] > 0):
        return "stall_and_price_up_volume_down"
    if bool(row["high_volume_stall_count"] > 0):
        return "high_volume_stall"
    if bool(row["price_up_volume_down_count"] > 0):
        return "price_up_volume_down"
    if bool(row["volume_breakout_count"] > 0) and not bool(row["post_breakout_volume_persistence_count"] > 0):
        return "breakout_volume_not_persistent"
    if not bool(row["vwap_support_count"] > 0) and not bool(row["low_volume_pullback_count"] > 0):
        return "no_vwap_or_pullback_support"
    if bool(row["risk_on_target_add_count"] <= 0) and bool(row["non_force_confirmation_count"] >= 2):
        return "target_add_not_triggered_after_confirm"
    return "mixed_or_selection_gap"


def _attribution_note(row: pd.Series) -> str:
    return (
        f"RISK_ON={float(row['risk_on_share']):.1%}; "
        f"三买/突破={int(row['buy3_count'])}/{int(row['breakout_confirmed_count'])}; "
        f"资金确认={int(row['confirmed_flow_count'])}; "
        f"目标补仓={int(row['risk_on_target_add_count'])}; "
        f"BETA_HOLD={float(row.get('beta_hold_share', 0.0)):.1%}; "
        f"满仓={float(row.get('full_position_share', 0.0)):.1%}; "
        f"量价二级={row['volume_price_secondary_reason']}; "
        f"force压制={float(row['force_suppression_share']):.1%}; "
        f"早退SELL/STOP={int(row['sell_signal_count'])}/{int(row['stop_signal_count'])}; "
        f"仓位avg/max={float(row['avg_total_position_pct']):.1%}/{float(row['max_total_position_pct_realized']):.1%}"
    )


def _build_train_features(train_frame: pd.DataFrame) -> pd.DataFrame:
    data = train_frame[train_frame["status"] == "ok"].copy()
    numeric_columns = [
        "total_return",
        "benchmark_return",
        "risk_matched_benchmark_return",
        "excess_return",
        "max_drawdown",
        "trade_count",
        "completed_trades",
        "win_rate",
        "buy_signal_count",
        "breakout_signal_count",
        "breakout_watch_count",
        "risk_on_target_add_count",
        "sell_signal_count",
        "stop_signal_count",
        "defensive_mode_count",
        "balanced_mode_count",
        "offensive_mode_count",
        "risk_on_count",
        "risk_on_share",
        "beta_hold_entry_count",
        "beta_hold_bar_count",
        "beta_hold_share",
        "wait_beta_hold_count",
        "full_position_bar_count",
        "full_position_share",
        "risk_on_after_1d_avg_position_pct",
        "risk_on_after_3d_avg_position_pct",
        "risk_on_after_5d_avg_position_pct",
        "risk_on_after_10d_avg_position_pct",
        "strong_confirm_episode_count",
        "strong_confirm_to_exit_avg_bars",
        "beta_hold_episode_avg_bars",
        "avg_total_position_pct",
        "max_total_position_pct_realized",
        "avg_active_position_pct",
        "max_active_position_pct",
        "buy3_count",
        "breakout_confirmed_count",
        "confirmed_flow_count",
        "confirmed_flow_share",
        "volume_price_score_avg",
        "volume_breakout_count",
        "low_volume_pullback_count",
        "high_volume_stall_count",
        "price_up_volume_down_count",
        "vwap_support_count",
        "post_breakout_volume_persistence_count",
        "rows",
    ]
    for column in numeric_columns:
        if column not in data.columns:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce")
    mode_total = (data["defensive_mode_count"] + data["balanced_mode_count"] + data["offensive_mode_count"]).replace(0, pd.NA)
    data["offensive_share"] = (data["offensive_mode_count"] / mode_total).fillna(0.0)
    data["signal_count"] = data["buy_signal_count"] + data["breakout_signal_count"]
    data["signal_density"] = data["signal_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    data["target_add_density"] = data["risk_on_target_add_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    data["target_add_density"] = data["target_add_density"].fillna(0.0)
    data["stop_per_trade"] = (data["stop_signal_count"] / data["trade_count"].replace(0, pd.NA)).fillna(data["stop_signal_count"])
    data["stop_density"] = data["stop_signal_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    data["early_exit_count"] = data["sell_signal_count"] + data["stop_signal_count"]
    data["early_exit_density"] = data["early_exit_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    data["early_exit_per_trade"] = (data["early_exit_count"] / data["trade_count"].replace(0, pd.NA)).fillna(data["early_exit_count"])
    data["trend_strength"] = data["benchmark_return"].clip(lower=0.0)
    data["upside_capture"] = (data["total_return"] / data["benchmark_return"].where(data["benchmark_return"] > 0)).fillna(0.0).clip(-1.0, 2.0)
    data["risk_matched_excess_return"] = data["total_return"] - data["risk_matched_benchmark_return"].fillna(0.0)
    data["risk_matched_capture"] = (
        data["total_return"] / data["risk_matched_benchmark_return"].where(data["risk_matched_benchmark_return"] > 0)
    ).fillna(0.0).clip(-1.0, 2.0)
    data["trend_capture_return"] = data["total_return"].where(data["benchmark_return"] > 0, 0.0)
    data["capture_shortfall"] = (
        data["trend_strength"]
        * (0.70 - data["upside_capture"].clip(lower=0.0, upper=0.70)).clip(lower=0.0)
        / 0.70
    ).fillna(0.0)
    data["win_rate"] = data["win_rate"].fillna(0.0)
    data["signal_rank"] = data["signal_density"].rank(pct=True)
    data["target_add_rank"] = data["target_add_density"].rank(pct=True)
    data["offensive_rank"] = data["offensive_share"].rank(pct=True)
    data["trend_strength_rank"] = data["trend_strength"].rank(pct=True)
    data["upside_capture_rank"] = data["upside_capture"].rank(pct=True)
    data["capture_shortfall_rank"] = (-data["capture_shortfall"]).rank(pct=True)
    data["excess_rank"] = data["excess_return"].rank(pct=True)
    data["risk_matched_excess_rank"] = data["risk_matched_excess_return"].rank(pct=True)
    data["risk_matched_capture_rank"] = data["risk_matched_capture"].rank(pct=True)
    data["trend_capture_rank"] = (
        0.45 * data["trend_strength_rank"]
        + 0.35 * data["upside_capture_rank"]
        + 0.08 * data["excess_rank"]
        + 0.04 * data["risk_matched_excess_rank"]
        + 0.08 * data["capture_shortfall_rank"]
    )
    data["drawdown_rank"] = data["max_drawdown"].rank(pct=True)
    data["stop_rank"] = (-data["stop_per_trade"]).rank(pct=True)
    data["early_exit_rank"] = (-data["early_exit_per_trade"]).rank(pct=True)
    data["win_rank"] = data["win_rate"].rank(pct=True)
    data["train_return_rank"] = data["total_return"].rank(pct=True)
    data["position_time_rank"] = data["avg_total_position_pct"].rank(pct=True)
    data["peak_position_rank"] = data["max_total_position_pct_realized"].rank(pct=True)
    data["trend_structure_count"] = (
        data["buy3_count"]
        + data["breakout_confirmed_count"]
        + data["breakout_signal_count"]
        + data["confirmed_flow_count"]
        + data["volume_breakout_count"]
        + data["vwap_support_count"]
        + data["post_breakout_volume_persistence_count"]
    )
    data["trend_structure_density"] = data["trend_structure_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    data["trend_structure_density"] = data["trend_structure_density"].fillna(0.0)
    data["trend_structure_rank"] = data["trend_structure_density"].rank(pct=True)
    data["risk_on_rank"] = data["risk_on_share"].rank(pct=True)
    data["volume_quality_rank"] = data["volume_price_score_avg"].rank(pct=True)
    data["risk_on_after_1d_rank"] = data["risk_on_after_1d_avg_position_pct"].rank(pct=True)
    data["risk_on_after_3d_rank"] = data["risk_on_after_3d_avg_position_pct"].rank(pct=True)
    data["risk_on_after_5d_rank"] = data["risk_on_after_5d_avg_position_pct"].rank(pct=True)
    data["risk_on_after_10d_rank"] = data["risk_on_after_10d_avg_position_pct"].rank(pct=True)
    data["beta_hold_share_rank"] = data["beta_hold_share"].rank(pct=True)
    data["full_position_share_rank"] = data["full_position_share"].rank(pct=True)
    data["strong_confirm_lifecycle_rank"] = data["strong_confirm_to_exit_avg_bars"].rank(pct=True)
    data["beta_hold_lifecycle_rank"] = data["beta_hold_episode_avg_bars"].rank(pct=True)
    data["distribution_risk_density"] = (
        (data["high_volume_stall_count"] + data["price_up_volume_down_count"]) / data["rows"].replace(0, pd.NA) * 10_000.0
    )
    data["distribution_risk_density"] = data["distribution_risk_density"].fillna(0.0)
    data["distribution_risk_rank"] = (-data["distribution_risk_density"]).rank(pct=True)
    divergence_scale = float(data["distribution_risk_density"].quantile(0.75))
    if divergence_scale <= 0.0:
        divergence_scale = 1.0
    divergence_intensity = (data["distribution_risk_density"] / divergence_scale).clip(lower=0.0, upper=1.0)
    capture_unit = (data["upside_capture"].clip(lower=0.0, upper=1.2) / 1.2).fillna(0.0)
    position_unit = data["risk_on_after_10d_avg_position_pct"].clip(lower=0.0, upper=1.0).fillna(0.0)
    beta_hold_unit = data["beta_hold_share"].clip(lower=0.0, upper=1.0).fillna(0.0)
    data["volume_divergence_capture"] = (
        (1.0 - divergence_intensity) * (0.68 * capture_unit + 0.20 * position_unit + 0.12 * beta_hold_unit)
        + divergence_intensity
        * (0.44 * capture_unit + 0.28 * position_unit + 0.18 * beta_hold_unit + 0.10 * data["capture_shortfall_rank"])
    ).fillna(0.0)
    data["volume_divergence_capture_rank"] = data["volume_divergence_capture"].rank(pct=True)
    up_volume_down_density = data["price_up_volume_down_count"] / data["rows"].replace(0, pd.NA) * 10_000.0
    up_volume_down_density = up_volume_down_density.fillna(0.0)
    continuation_scale = float(up_volume_down_density.quantile(0.75))
    if continuation_scale <= 0.0:
        continuation_scale = 1.0
    continuation_intensity = (up_volume_down_density / continuation_scale).clip(lower=0.0, upper=1.0)
    data["volume_price_continuation_capture"] = (
        (1.0 - continuation_intensity) * (0.50 * capture_unit + 0.24 * position_unit + 0.16 * beta_hold_unit + 0.10 * data["risk_matched_capture_rank"])
        + continuation_intensity
        * (0.42 * capture_unit + 0.28 * position_unit + 0.20 * beta_hold_unit + 0.10 * data["capture_shortfall_rank"])
    ).fillna(0.0)
    data["volume_price_continuation_capture_rank"] = data["volume_price_continuation_capture"].rank(pct=True)
    position_underbuilt_gap = (0.75 - data["risk_on_after_10d_avg_position_pct"].fillna(0.0)).clip(lower=0.0, upper=0.75) / 0.75
    upside_shortfall_unit = (1.0 - data["upside_capture"].clip(lower=0.0, upper=1.0)).fillna(1.0)
    data["risk_on_position_underbuilt"] = (
        data["trend_strength"].clip(lower=0.0)
        * position_underbuilt_gap
        * upside_shortfall_unit
    ).fillna(0.0)
    data["risk_on_position_underbuilt_rank"] = (-data["risk_on_position_underbuilt"]).rank(pct=True)
    trend_shortfall_ratio = (
        data["capture_shortfall"] / data["trend_strength"].where(data["trend_strength"] > 0)
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    stop_intensity = (data["stop_per_trade"] / 4.0).clip(lower=0.0, upper=1.0).fillna(0.0)
    early_exit_intensity = (data["early_exit_per_trade"] / 6.0).clip(lower=0.0, upper=1.0).fillna(0.0)
    data["soft_stop_flying_rate"] = (
        0.38 * stop_intensity
        + 0.26 * early_exit_intensity
        + 0.24 * trend_shortfall_ratio
        + 0.12 * (1.0 - data["beta_hold_lifecycle_rank"].fillna(0.0))
    ).clip(lower=0.0, upper=1.0)
    data["soft_stop_flying_rank"] = (-data["soft_stop_flying_rate"]).rank(pct=True)
    data = data.copy()
    data["target_add_efficiency"] = (
        data["trend_capture_return"].clip(lower=0.0)
        / data["risk_on_target_add_count"].clip(lower=1)
    )
    data["target_add_efficiency_rank"] = data["target_add_efficiency"].rank(pct=True)
    data["capture_resilience"] = (
        0.26 * data["upside_capture_rank"]
        + 0.20 * data["capture_shortfall_rank"]
        + 0.16 * data["soft_stop_flying_rank"]
        + 0.10 * data["volume_divergence_capture_rank"]
        + 0.08 * data["volume_price_continuation_capture_rank"]
        + 0.08 * data["risk_on_position_underbuilt_rank"]
        + 0.07 * data["early_exit_rank"]
        + 0.05 * data["distribution_risk_rank"]
    )
    data = data.copy()
    data["risk_on_position_capture_rank"] = (
        0.30 * data["risk_on_after_3d_rank"]
        + 0.22 * data["risk_on_after_5d_rank"]
        + 0.16 * data["risk_on_after_10d_rank"]
        + 0.12 * data["position_time_rank"]
        + 0.10 * data["full_position_share_rank"]
        + 0.10 * data["target_add_rank"]
    )
    data["hold_lifecycle_rank"] = (
        0.48 * data["beta_hold_lifecycle_rank"]
        + 0.34 * data["strong_confirm_lifecycle_rank"]
        + 0.18 * data["early_exit_rank"]
    )
    data["strong_beta_score"] = (
        0.34 * data["trend_strength_rank"]
        + 0.20 * data["train_return_rank"]
        + 0.16 * data["upside_capture_rank"]
        + 0.10 * data["excess_rank"]
        + 0.10 * data["trend_structure_rank"]
        + 0.06 * data["offensive_rank"]
        + 0.04 * data["volume_quality_rank"]
    )
    data["main_uptrend_score"] = (
        0.26 * data["trend_strength_rank"]
        + 0.18 * data["trend_structure_rank"]
        + 0.15 * data["risk_on_position_capture_rank"]
        + 0.12 * data["offensive_rank"]
        + 0.11 * data["risk_on_rank"]
        + 0.08 * data["train_return_rank"]
        + 0.06 * data["upside_capture_rank"]
        + 0.04 * data["capture_shortfall_rank"]
    )
    data["risk_adjusted_beta_score"] = (
        0.28 * data["strong_beta_score"]
        + 0.22 * data["main_uptrend_score"]
        + 0.16 * data["drawdown_rank"]
        + 0.12 * data["stop_rank"]
        + 0.08 * data["distribution_risk_rank"]
        + 0.08 * data["win_rank"]
        + 0.06 * data["capture_shortfall_rank"]
    )
    data["beta_hold_capture_score"] = (
        0.24 * data["trend_strength_rank"]
        + 0.20 * data["upside_capture_rank"]
        + 0.16 * data["risk_on_position_capture_rank"]
        + 0.14 * data["hold_lifecycle_rank"]
        + 0.10 * data["target_add_rank"]
        + 0.08 * data["trend_structure_rank"]
        + 0.04 * data["early_exit_rank"]
        + 0.04 * data["capture_shortfall_rank"]
    )
    data["main_uptrend_capture_score"] = (
        0.24 * data["trend_capture_rank"]
        + 0.20 * data["risk_on_position_capture_rank"]
        + 0.16 * data["upside_capture_rank"]
        + 0.14 * data["hold_lifecycle_rank"]
        + 0.10 * data["trend_structure_rank"]
        + 0.08 * data["capture_shortfall_rank"]
        + 0.05 * data["distribution_risk_rank"]
        + 0.03 * data["drawdown_rank"]
    )
    data["main_rise_capture_bias_score"] = (
        0.22 * data["trend_capture_rank"]
        + 0.16 * data["capture_resilience"]
        + 0.15 * data["risk_on_position_capture_rank"]
        + 0.12 * data["hold_lifecycle_rank"]
        + 0.08 * data["target_add_efficiency_rank"]
        + 0.06 * data["volume_divergence_capture_rank"]
        + 0.05 * data["volume_price_continuation_capture_rank"]
        + 0.06 * data["soft_stop_flying_rank"]
        + 0.04 * data["capture_shortfall_rank"]
        + 0.02 * data["risk_on_position_underbuilt_rank"]
        + 0.03 * data["trend_structure_rank"]
        + 0.01 * data["drawdown_rank"]
    )
    data["main_rise_capture_resilience_score"] = (
        0.28 * data["main_rise_capture_bias_score"]
        + 0.16 * data["volume_divergence_capture_rank"]
        + 0.14 * data["volume_price_continuation_capture_rank"]
        + 0.16 * data["soft_stop_flying_rank"]
        + 0.12 * data["capture_shortfall_rank"]
        + 0.08 * data["risk_on_position_capture_rank"]
        + 0.06 * data["risk_on_position_underbuilt_rank"]
    )
    data["screen_score"] = (
        0.28 * data["main_rise_capture_bias_score"]
        + 0.18 * data["main_uptrend_capture_score"]
        + 0.16 * data["beta_hold_capture_score"]
        + 0.12 * data["main_rise_capture_resilience_score"]
        + 0.10 * data["main_uptrend_score"]
        + 0.08 * data["risk_adjusted_beta_score"]
        + 0.04 * data["trend_capture_rank"]
        + 0.03 * data["signal_rank"]
        + 0.01 * data["drawdown_rank"]
    )
    return data.sort_values("screen_score", ascending=False).reset_index(drop=True)


RANK_RULE_COLUMNS = {
    "main_rise_capture_bias_score_rank": "main_rise_capture_bias_score",
    "main_rise_capture_resilience_score_rank": "main_rise_capture_resilience_score",
    "main_uptrend_capture_score_rank": "main_uptrend_capture_score",
    "risk_on_position_capture_rank": "risk_on_position_capture_rank",
    "trend_capture_rank": "trend_capture_rank",
    "strong_beta_score_rank": "strong_beta_score",
    "main_uptrend_score_rank": "main_uptrend_score",
    "beta_hold_capture_score_rank": "beta_hold_capture_score",
    "risk_adjusted_beta_score_rank": "risk_adjusted_beta_score",
    "beta_hold_share_rank": "beta_hold_share_rank",
    "full_position_share_rank": "full_position_share_rank",
    "hold_lifecycle_rank": "hold_lifecycle_rank",
    "screen_score_rank": "screen_score",
}

CAPTURE_BIAS_RULE_IDS = frozenset(
    {
        "main_rise_capture_bias_score_rank",
        "main_rise_capture_resilience_score_rank",
        "main_uptrend_capture_score_rank",
        "risk_on_position_capture_rank",
        "beta_hold_capture_score_rank",
        "beta_hold_share_rank",
        "full_position_share_rank",
        "hold_lifecycle_rank",
        "trend_capture_rank",
    }
)


def _train_rule_objective(train_sub: pd.DataFrame) -> float:
    return (
        0.32 * float(train_sub["total_return"].mean())
        + 0.34 * float(train_sub["trend_capture_return"].mean())
        + 0.18 * float(train_sub["trend_strength"].mean())
        + 0.16 * float(train_sub["upside_capture"].clip(lower=0.0, upper=1.5).mean())
        + 0.12 * float(train_sub["avg_total_position_pct"].mean())
        + 0.06 * float(train_sub["full_position_share"].mean())
        + 0.05 * float(train_sub["beta_hold_share"].mean())
        + 0.05 * float(train_sub["main_uptrend_capture_score"].mean())
        + 0.04 * float(train_sub["risk_on_position_capture_rank"].mean())
        + 0.03 * float((train_sub["total_return"] > 0).mean())
        + 0.05 * float(train_sub["volume_divergence_capture"].mean())
        + 0.05 * float(train_sub["volume_price_continuation_capture"].mean())
        + 0.04 * float(train_sub["risk_matched_excess_return"].mean())
        - 0.28 * float(train_sub["capture_shortfall"].mean())
        - 0.08 * float(train_sub["soft_stop_flying_rate"].mean())
        - 0.10 * float(train_sub["risk_on_position_underbuilt"].mean())
        - 0.11 * abs(float(train_sub["max_drawdown"].mean()))
        - 0.012 * float(train_sub["early_exit_per_trade"].mean())
        - 0.008 * float(train_sub["stop_per_trade"].mean())
    )


def _rule_record(
    *,
    rule_id: str,
    candidates: pd.DataFrame,
    train_sub: pd.DataFrame,
    top_n: int,
    train_objective: float,
    signal_quantile: float,
    offensive_quantile: float,
    trend_quantile: float,
    capture_quantile: float,
    drawdown_quantile: float,
    stop_quantile: float,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "candidate_count": len(candidates),
        "top_n": top_n,
        "train_objective": train_objective,
        "train_avg_total_return": float(train_sub["total_return"].mean()),
        "train_median_total_return": float(train_sub["total_return"].median()),
        "train_positive_rate": float((train_sub["total_return"] > 0).mean()),
        "train_avg_benchmark_return": float(train_sub["benchmark_return"].mean()),
        "train_avg_risk_matched_benchmark_return": float(train_sub["risk_matched_benchmark_return"].mean()),
        "train_avg_risk_matched_excess_return": float(train_sub["risk_matched_excess_return"].mean()),
        "train_avg_trend_strength": float(train_sub["trend_strength"].mean()),
        "train_avg_upside_capture": float(train_sub["upside_capture"].mean()),
        "train_avg_capture_shortfall": float(train_sub["capture_shortfall"].mean()),
        "train_avg_trend_capture_return": float(train_sub["trend_capture_return"].mean()),
        "train_avg_position_pct": float(train_sub["avg_total_position_pct"].mean()),
        "train_avg_max_drawdown": float(train_sub["max_drawdown"].mean()),
        "train_avg_stop_per_trade": float(train_sub["stop_per_trade"].mean()),
        "train_avg_early_exit_per_trade": float(train_sub["early_exit_per_trade"].mean()),
        "train_avg_distribution_risk_density": float(train_sub["distribution_risk_density"].mean()),
        "train_avg_volume_divergence_capture": float(train_sub["volume_divergence_capture"].mean()),
        "train_avg_volume_price_continuation_capture": float(train_sub["volume_price_continuation_capture"].mean()),
        "train_avg_risk_on_position_underbuilt": float(train_sub["risk_on_position_underbuilt"].mean()),
        "train_avg_soft_stop_flying_rate": float(train_sub["soft_stop_flying_rate"].mean()),
        "train_avg_risk_on_after_10d_position": float(train_sub["risk_on_after_10d_avg_position_pct"].mean()),
        "train_avg_main_rise_capture_bias_score": float(train_sub["main_rise_capture_bias_score"].mean()),
        "train_avg_main_rise_capture_resilience_score": float(train_sub["main_rise_capture_resilience_score"].mean()),
        "signal_quantile": signal_quantile,
        "offensive_quantile": offensive_quantile,
        "trend_quantile": trend_quantile,
        "capture_quantile": capture_quantile,
        "drawdown_quantile": drawdown_quantile,
        "stop_quantile": stop_quantile,
    }


def _train_rules(train_features: pd.DataFrame, *, top_n_values: list[int]) -> pd.DataFrame:
    max_top_n = max(top_n_values)
    records: list[dict[str, object]] = []
    for rule_id, sort_column in RANK_RULE_COLUMNS.items():
        candidates = train_features.sort_values([sort_column, "screen_score"], ascending=[False, False])
        if len(candidates) < max_top_n:
            continue
        for top_n in top_n_values:
            train_sub = candidates.head(top_n)
            records.append(
                _rule_record(
                    rule_id=rule_id,
                    candidates=candidates,
                    train_sub=train_sub,
                    top_n=top_n,
                    train_objective=_train_rule_objective(train_sub),
                    signal_quantile=0.0,
                    offensive_quantile=0.0,
                    trend_quantile=0.0,
                    capture_quantile=0.0,
                    drawdown_quantile=0.0,
                    stop_quantile=1.0,
                )
            )
    signal_quantiles = (0.25, 0.35, 0.45, 0.55, 0.65)
    offensive_quantiles = (0.25, 0.35, 0.45, 0.55, 0.65)
    trend_quantiles = (0.20, 0.30, 0.40, 0.50)
    capture_quantiles = (0.20, 0.30, 0.40, 0.50)
    drawdown_quantiles = (0.10, 0.20, 0.30, 0.40)
    stop_quantiles = (0.50, 0.60, 0.70, 0.80)
    for signal_q in signal_quantiles:
        signal_min = float(train_features["signal_density"].quantile(signal_q))
        for offensive_q in offensive_quantiles:
            offensive_min = float(train_features["offensive_share"].quantile(offensive_q))
            for trend_q in trend_quantiles:
                trend_min = float(train_features["trend_strength"].quantile(trend_q))
                for capture_q in capture_quantiles:
                    capture_min = float(train_features["upside_capture"].quantile(capture_q))
                    for drawdown_q in drawdown_quantiles:
                        drawdown_min = float(train_features["max_drawdown"].quantile(drawdown_q))
                        for stop_q in stop_quantiles:
                            stop_max = float(train_features["stop_per_trade"].quantile(stop_q))
                            mask = (
                                (train_features["signal_density"] >= signal_min)
                                & (train_features["offensive_share"] >= offensive_min)
                                & (train_features["trend_strength"] >= trend_min)
                                & (train_features["upside_capture"] >= capture_min)
                                & (train_features["max_drawdown"] >= drawdown_min)
                                & (train_features["stop_per_trade"] <= stop_max)
                                & (train_features["trade_count"] >= 5)
                                & (train_features["signal_count"] > 0)
                            )
                            candidates = train_features[mask].sort_values("screen_score", ascending=False)
                            if len(candidates) < max_top_n:
                                continue
                            rule_id = (
                                f"sig{signal_q:.2f}_off{offensive_q:.2f}_tr{trend_q:.2f}_"
                                f"cap{capture_q:.2f}_dd{drawdown_q:.2f}_stop{stop_q:.2f}"
                            )
                            for top_n in top_n_values:
                                train_sub = candidates.head(top_n)
                                records.append(
                                    _rule_record(
                                        rule_id=rule_id,
                                        candidates=candidates,
                                        train_sub=train_sub,
                                        top_n=top_n,
                                        train_objective=_train_rule_objective(train_sub),
                                        signal_quantile=signal_q,
                                        offensive_quantile=offensive_q,
                                        trend_quantile=trend_q,
                                        capture_quantile=capture_q,
                                        drawdown_quantile=drawdown_q,
                                        stop_quantile=stop_q,
                                    )
                                )
    if not records:
        fallback = train_features.sort_values("screen_score", ascending=False)
        for top_n in top_n_values:
            train_sub = fallback.head(top_n)
            records.append(
                _rule_record(
                    rule_id="fallback_score_rank",
                    candidates=fallback,
                    train_sub=train_sub,
                    top_n=top_n,
                    train_objective=_train_rule_objective(train_sub),
                    signal_quantile=0.0,
                    offensive_quantile=0.0,
                    trend_quantile=0.0,
                    capture_quantile=0.0,
                    drawdown_quantile=0.0,
                    stop_quantile=1.0,
                )
            )
    rules = pd.DataFrame(records)
    return rules.sort_values(["top_n", "train_objective"], ascending=[True, False]).reset_index(drop=True)


def _select_rule_for_window(
    rules: pd.DataFrame,
    *,
    force_rule_id: str | None,
    preferred_top_n: int | None,
    selection_mode: str = "train-objective",
    capture_bias_rule_ids: frozenset[str] | None = None,
    capture_bias_constraints: CaptureBiasRuleConstraints | None = None,
) -> pd.Series:
    if force_rule_id:
        forced = rules[rules["rule_id"] == force_rule_id].copy()
        if forced.empty:
            available = ", ".join(sorted(str(value) for value in rules["rule_id"].dropna().unique()))
            raise ValueError(f"unknown force_rule_id={force_rule_id!r}; available rules: {available}")
        if preferred_top_n is not None:
            preferred = forced[forced["top_n"] == preferred_top_n]
            if not preferred.empty:
                return preferred.sort_values("train_objective", ascending=False).iloc[0]
        return forced.sort_values(["top_n", "train_objective"], ascending=[False, False]).iloc[0]

    if selection_mode == "capture-bias":
        candidates = rules.copy()
        if preferred_top_n is not None:
            preferred = candidates[candidates["top_n"] == preferred_top_n].copy()
            if not preferred.empty:
                candidates = preferred
        capture_candidates = _capture_bias_rule_candidates(
            candidates,
            rule_ids=capture_bias_rule_ids,
            constraints=capture_bias_constraints or CaptureBiasRuleConstraints(),
        )
        if not capture_candidates.empty:
            candidates = capture_candidates
        elif capture_bias_rule_ids is not None or not (capture_bias_constraints or CaptureBiasRuleConstraints()).is_empty:
            top_n_message = f" for top_n={preferred_top_n}" if preferred_top_n is not None else ""
            raise ValueError(f"capture-bias constraints removed all candidate rules{top_n_message}")
        candidates["rule_selection_score"] = _capture_bias_rule_selection_score(candidates)
        return candidates.sort_values(["rule_selection_score", "train_objective"], ascending=[False, False]).iloc[0]

    if selection_mode == "train-objective":
        if preferred_top_n is not None:
            preferred = rules[rules["top_n"] == preferred_top_n]
            if not preferred.empty:
                return preferred.sort_values("train_objective", ascending=False).iloc[0]
        return rules.sort_values(["top_n", "train_objective"], ascending=[True, False]).iloc[0]

    raise ValueError(f"unknown rule selection mode: {selection_mode}")


def _capture_bias_rule_candidates(
    rules: pd.DataFrame,
    *,
    rule_ids: frozenset[str] | None,
    constraints: CaptureBiasRuleConstraints,
) -> pd.DataFrame:
    allowed_ids = rule_ids or CAPTURE_BIAS_RULE_IDS
    candidates = rules[rules["rule_id"].isin(allowed_ids)].copy()
    if candidates.empty:
        return candidates
    candidates = _apply_rule_min_constraint(
        candidates,
        "train_positive_rate",
        constraints.min_positive_rate,
        "--capture-bias-min-positive-rate",
    )
    candidates = _apply_rule_min_constraint(
        candidates,
        "train_avg_upside_capture",
        constraints.min_upside_capture,
        "--capture-bias-min-upside-capture",
    )
    candidates = _apply_rule_min_constraint(
        candidates,
        "train_avg_trend_capture_return",
        constraints.min_trend_capture_return,
        "--capture-bias-min-trend-capture-return",
    )
    candidates = _apply_rule_min_constraint(
        candidates,
        "train_avg_risk_on_after_10d_position",
        constraints.min_risk_on_after_10d_position,
        "--capture-bias-min-risk-on-after-10d-position",
    )
    candidates = _apply_rule_max_constraint(
        candidates,
        "train_avg_capture_shortfall",
        constraints.max_capture_shortfall,
        "--capture-bias-max-capture-shortfall",
    )
    candidates = _apply_rule_max_constraint(
        candidates,
        "train_avg_max_drawdown",
        constraints.max_abs_drawdown,
        "--capture-bias-max-abs-drawdown",
        absolute=True,
    )
    candidates = _apply_rule_max_constraint(
        candidates,
        "train_avg_soft_stop_flying_rate",
        constraints.max_soft_stop_flying_rate,
        "--capture-bias-max-soft-stop-flying-rate",
    )
    candidates = _apply_rule_max_constraint(
        candidates,
        "train_avg_risk_on_position_underbuilt",
        constraints.max_risk_on_position_underbuilt,
        "--capture-bias-max-risk-on-position-underbuilt",
    )
    return candidates


def _apply_rule_min_constraint(
    rules: pd.DataFrame,
    column: str,
    threshold: float | None,
    option_name: str,
) -> pd.DataFrame:
    if threshold is None:
        return rules
    if column not in rules.columns:
        raise ValueError(f"{option_name} requires rule metric column {column!r}")
    values = pd.to_numeric(rules[column], errors="coerce").fillna(float("-inf"))
    return rules[values >= threshold].copy()


def _apply_rule_max_constraint(
    rules: pd.DataFrame,
    column: str,
    threshold: float | None,
    option_name: str,
    *,
    absolute: bool = False,
) -> pd.DataFrame:
    if threshold is None:
        return rules
    if column not in rules.columns:
        raise ValueError(f"{option_name} requires rule metric column {column!r}")
    values = pd.to_numeric(rules[column], errors="coerce")
    if absolute:
        values = values.abs()
    values = values.fillna(float("inf"))
    return rules[values <= threshold].copy()


def _capture_bias_rule_selection_score(rules: pd.DataFrame) -> pd.Series:
    upside_capture = rules["train_avg_upside_capture"].clip(lower=0.0, upper=1.5)
    main_rise_capture_bias = _optional_rule_metric(rules, "train_avg_main_rise_capture_bias_score")
    risk_on_after_10d_position = _optional_rule_metric(
        rules,
        "train_avg_risk_on_after_10d_position",
        fallback_column="train_avg_position_pct",
    )
    distribution_risk_density = _optional_rule_metric(rules, "train_avg_distribution_risk_density")
    volume_divergence_capture = _optional_rule_metric(rules, "train_avg_volume_divergence_capture")
    volume_price_continuation_capture = _optional_rule_metric(rules, "train_avg_volume_price_continuation_capture")
    soft_stop_flying_rate = _optional_rule_metric(rules, "train_avg_soft_stop_flying_rate")
    risk_on_position_underbuilt = _optional_rule_metric(rules, "train_avg_risk_on_position_underbuilt")
    risk_matched_excess = _optional_rule_metric(rules, "train_avg_risk_matched_excess_return")
    main_rise_capture_resilience = _optional_rule_metric(
        rules,
        "train_avg_main_rise_capture_resilience_score",
        fallback_column="train_avg_main_rise_capture_bias_score",
    )
    return (
        0.34 * rules["train_avg_trend_capture_return"]
        + 0.22 * upside_capture
        + 0.14 * main_rise_capture_bias
        + 0.10 * main_rise_capture_resilience
        + 0.10 * risk_on_after_10d_position
        + 0.10 * rules["train_positive_rate"]
        + 0.06 * rules["train_avg_position_pct"]
        + 0.08 * volume_divergence_capture
        + 0.06 * volume_price_continuation_capture
        + 0.04 * risk_matched_excess
        - 0.28 * rules["train_avg_capture_shortfall"]
        - 0.08 * soft_stop_flying_rate
        - 0.10 * risk_on_position_underbuilt
        - 0.08 * rules["train_avg_max_drawdown"].abs()
        - 0.05 * rules["train_avg_stop_per_trade"]
        - 0.04 * rules["train_avg_early_exit_per_trade"]
        - 0.0015 * distribution_risk_density
    )


def _optional_rule_metric(
    rules: pd.DataFrame,
    column: str,
    *,
    fallback_column: str | None = None,
    default: float = 0.0,
) -> pd.Series:
    if column in rules:
        return pd.to_numeric(rules[column], errors="coerce").fillna(default)
    if fallback_column is not None and fallback_column in rules:
        return pd.to_numeric(rules[fallback_column], errors="coerce").fillna(default)
    return pd.Series(default, index=rules.index, dtype="float64")


def _rank_candidates(train_features: pd.DataFrame, rule: pd.Series) -> pd.DataFrame:
    rule_id = str(rule["rule_id"])
    if rule_id in RANK_RULE_COLUMNS:
        sort_column = RANK_RULE_COLUMNS[rule_id]
        return train_features.sort_values([sort_column, "screen_score"], ascending=[False, False]).reset_index(drop=True)
    if rule_id == "fallback_score_rank":
        return train_features.sort_values("screen_score", ascending=False).reset_index(drop=True)
    signal_min = float(train_features["signal_density"].quantile(float(rule["signal_quantile"])))
    offensive_min = float(train_features["offensive_share"].quantile(float(rule["offensive_quantile"])))
    trend_min = float(train_features["trend_strength"].quantile(float(rule["trend_quantile"])))
    capture_min = float(train_features["upside_capture"].quantile(float(rule["capture_quantile"])))
    drawdown_min = float(train_features["max_drawdown"].quantile(float(rule["drawdown_quantile"])))
    stop_max = float(train_features["stop_per_trade"].quantile(float(rule["stop_quantile"])))
    mask = (
        (train_features["signal_density"] >= signal_min)
        & (train_features["offensive_share"] >= offensive_min)
        & (train_features["trend_strength"] >= trend_min)
        & (train_features["upside_capture"] >= capture_min)
        & (train_features["max_drawdown"] >= drawdown_min)
        & (train_features["stop_per_trade"] <= stop_max)
        & (train_features["trade_count"] >= 5)
        & (train_features["signal_count"] > 0)
    )
    return train_features[mask].sort_values("screen_score", ascending=False).reset_index(drop=True)


def _portfolio_metrics(curve_map: dict[str, CurvePayload], symbols: list[str], *, weighting: str = "equal") -> dict[str, float]:
    strategy_frames = []
    benchmark_frames = []
    risk_matched_benchmark_frames = []
    for symbol in symbols:
        payload = curve_map.get(symbol)
        if payload is None or not payload.points:
            continue
        columns = ["timestamp", symbol, f"{symbol}_benchmark", f"{symbol}_risk_matched_benchmark"]
        frame = pd.DataFrame(payload.points, columns=columns[: len(payload.points[0])])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        strategy_frames.append(frame[["timestamp", symbol]].set_index("timestamp"))
        benchmark_frames.append(frame[["timestamp", f"{symbol}_benchmark"]].rename(columns={f"{symbol}_benchmark": symbol}).set_index("timestamp"))
        if f"{symbol}_risk_matched_benchmark" in frame.columns:
            risk_matched_benchmark_frames.append(
                frame[["timestamp", f"{symbol}_risk_matched_benchmark"]]
                .rename(columns={f"{symbol}_risk_matched_benchmark": symbol})
                .set_index("timestamp")
            )
    if not strategy_frames:
        return {
            "strategy_return": 0.0,
            "benchmark_return": 0.0,
            "risk_matched_benchmark_return": 0.0,
            "strategy_max_drawdown": 0.0,
        }
    weights = _portfolio_weights(symbols, weighting=weighting)
    strategy = _weighted_portfolio_curve(pd.concat(strategy_frames, axis=1, sort=False), weights)
    benchmark = _weighted_portfolio_curve(pd.concat(benchmark_frames, axis=1, sort=False), weights)
    risk_matched_benchmark = (
        _weighted_portfolio_curve(pd.concat(risk_matched_benchmark_frames, axis=1, sort=False), weights)
        if risk_matched_benchmark_frames
        else pd.Series([1.0], dtype=float)
    )
    return {
        "strategy_return": float(strategy.iloc[-1] - 1.0),
        "benchmark_return": float(benchmark.iloc[-1] - 1.0),
        "risk_matched_benchmark_return": float(risk_matched_benchmark.iloc[-1] - 1.0),
        "strategy_max_drawdown": _max_drawdown(strategy),
    }


def _portfolio_weights(symbols: list[str], *, weighting: str) -> dict[str, float]:
    if weighting == "equal":
        return {symbol: 1.0 for symbol in symbols}
    if weighting != "rank-tier":
        raise ValueError(f"unknown portfolio weighting: {weighting}")
    weights: dict[str, float] = {}
    for rank, symbol in enumerate(symbols, start=1):
        if rank <= 30:
            weights[symbol] = 1.6
        elif rank <= 80:
            weights[symbol] = 1.0
        else:
            weights[symbol] = 0.45
    return weights


def _weighted_portfolio_curve(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    aligned = frame.sort_index().ffill().dropna(how="all")
    if aligned.empty:
        return pd.Series([1.0], dtype=float)
    weight_series = pd.Series({column: float(weights.get(column, 0.0)) for column in aligned.columns})
    weighted_sum = aligned.mul(weight_series, axis=1).sum(axis=1, min_count=1)
    active_weight = aligned.notna().mul(weight_series, axis=1).sum(axis=1)
    return (weighted_sum / active_weight.replace(0.0, pd.NA)).dropna()


def _max_drawdown(curve: pd.Series) -> float:
    peak = curve.cummax()
    drawdown = curve / peak - 1.0
    return float(drawdown.min())


def _summarize_walkforward_portfolios(portfolio_frame: pd.DataFrame, *, initial_capital: float) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    starting_capital = max(float(initial_capital), 0.0)
    group_columns = ["portfolio_weighting", "top_n"] if "portfolio_weighting" in portfolio_frame.columns else ["top_n"]
    for group_key, group in portfolio_frame.sort_values(group_columns + ["valid_start"]).groupby(group_columns, sort=True):
        if isinstance(group_key, tuple):
            portfolio_weighting, top_n = group_key
        else:
            portfolio_weighting, top_n = "equal", group_key
        strategy_curve = (1.0 + group["valid_total_return"]).cumprod()
        benchmark_curve = (1.0 + group["valid_benchmark_return"]).cumprod()
        risk_matched_benchmark_curve = (1.0 + group.get("valid_risk_matched_benchmark_return", pd.Series(0.0, index=group.index))).cumprod()
        strategy_return = float(strategy_curve.iloc[-1] - 1.0)
        benchmark_return = float(benchmark_curve.iloc[-1] - 1.0)
        risk_matched_benchmark_return = float(risk_matched_benchmark_curve.iloc[-1] - 1.0)
        records.append(
            {
                "portfolio_weighting": str(portfolio_weighting),
                "top_n": int(top_n),
                "window_count": int(len(group)),
                "initial_capital": starting_capital,
                "final_equity": starting_capital * (1.0 + strategy_return),
                "profit": starting_capital * strategy_return,
                "benchmark_final_equity": starting_capital * (1.0 + benchmark_return),
                "benchmark_profit": starting_capital * benchmark_return,
                "risk_matched_benchmark_final_equity": starting_capital * (1.0 + risk_matched_benchmark_return),
                "risk_matched_benchmark_profit": starting_capital * risk_matched_benchmark_return,
                "walkforward_total_return": strategy_return,
                "walkforward_benchmark_return": benchmark_return,
                "walkforward_risk_matched_benchmark_return": risk_matched_benchmark_return,
                "walkforward_excess_return": float(strategy_curve.iloc[-1] - benchmark_curve.iloc[-1]),
                "walkforward_risk_matched_excess_return": float(strategy_curve.iloc[-1] - risk_matched_benchmark_curve.iloc[-1]),
                "avg_window_return": float(group["valid_total_return"].mean()),
                "median_window_return": float(group["valid_total_return"].median()),
                "window_win_rate": float((group["valid_total_return"] > 0).mean()),
                "worst_window_max_drawdown": float(group["valid_max_drawdown"].min()),
                "avg_window_max_drawdown": float(group["valid_max_drawdown"].mean()),
                "avg_constituent_positive_rate": float(group["valid_positive_rate"].mean()),
                "avg_train_total_return": float(group["train_total_return"].mean()),
                "avg_train_stop_per_trade": float(group["train_stop_per_trade"].mean()),
            }
        )
    return pd.DataFrame(records)


def _summarize_trade_quality(trade_quality: pd.DataFrame, *, top_n_values: list[int]) -> pd.DataFrame:
    if trade_quality.empty:
        return pd.DataFrame()
    records: list[dict[str, object]] = []
    for top_n in sorted(top_n_values):
        data = trade_quality[pd.to_numeric(trade_quality["rank"], errors="coerce") <= top_n].copy()
        if data.empty:
            continue
        buy = data[data["trade_type"] == "buy"]
        sell = data[data["trade_type"] == "sell_exit"]
        timing_trade_count = int(len(buy) + len(sell))
        records.append(
            {
                "top_n": top_n,
                "trade_count": int(len(data)),
                "timing_trade_count": timing_trade_count,
                "non_timing_trade_count": int(len(data) - timing_trade_count),
                "buy_trade_count": int(len(buy)),
                "sell_exit_trade_count": int(len(sell)),
                "buy_accuracy": _bool_mean(buy, "buy_accurate"),
                "sell_accuracy": _bool_mean(sell, "sell_accurate"),
                "sell_flying_rate": _bool_mean(sell, "sell_flying"),
                "avg_buy_future_max_return_pct": _frame_mean(buy, "future_max_return_pct"),
                "avg_buy_future_min_return_pct": _frame_mean(buy, "future_min_return_pct"),
                "avg_sell_future_max_return_pct": _frame_mean(sell, "future_max_return_pct"),
                "avg_sell_future_min_return_pct": _frame_mean(sell, "future_min_return_pct"),
                "avg_realized_pnl": _frame_mean(data, "realized_pnl"),
            }
        )
    return pd.DataFrame(records)


def _summarize_buy_event_study(buy_event_study: pd.DataFrame, *, top_n_values: list[int]) -> pd.DataFrame:
    return _summarize_buy_event_study_by(buy_event_study, top_n_values=top_n_values, group_col=None)


def _summarize_buy_event_study_by(
    buy_event_study: pd.DataFrame,
    *,
    top_n_values: list[int],
    group_col: str | None,
) -> pd.DataFrame:
    if buy_event_study.empty:
        return pd.DataFrame()
    records: list[dict[str, object]] = []
    for top_n in sorted(top_n_values):
        data = buy_event_study[pd.to_numeric(buy_event_study["rank"], errors="coerce") <= top_n].copy()
        if data.empty:
            continue
        if group_col is None:
            for horizon, group in data.groupby("horizon_bars", dropna=False):
                records.append(_buy_event_summary_record(top_n=top_n, horizon_bars=horizon, data=group))
        elif group_col in data.columns:
            data[group_col] = data[group_col].fillna("UNKNOWN").replace("", "UNKNOWN")
            for (horizon, group_value), group in data.groupby(["horizon_bars", group_col], dropna=False):
                records.append(
                    _buy_event_summary_record(
                        top_n=top_n,
                        horizon_bars=horizon,
                        data=group,
                        group_col=group_col,
                        group_value=group_value,
                    )
                )
    return pd.DataFrame(records)


def _buy_event_summary_record(
    *,
    top_n: int,
    horizon_bars: object,
    data: pd.DataFrame,
    group_col: str | None = None,
    group_value: object | None = None,
) -> dict[str, object]:
    end_return = pd.to_numeric(data["end_return_pct"], errors="coerce").dropna()
    favorable = pd.to_numeric(data["max_favorable_return_pct"], errors="coerce").dropna()
    adverse = pd.to_numeric(data["max_adverse_return_pct"], errors="coerce").dropna()
    wins = end_return[end_return > 0]
    losses = end_return[end_return < 0]
    record: dict[str, object] = {
        "top_n": top_n,
        "horizon_bars": int(horizon_bars),
        "event_count": int(len(data)),
        "valid_event_count": int(len(end_return)),
        "avg_end_return_pct": _series_mean(end_return),
        "median_end_return_pct": _series_median(end_return),
        "p05_end_return_pct": _series_quantile(end_return, 0.05),
        "p10_end_return_pct": _series_quantile(end_return, 0.10),
        "p25_end_return_pct": _series_quantile(end_return, 0.25),
        "p75_end_return_pct": _series_quantile(end_return, 0.75),
        "p90_end_return_pct": _series_quantile(end_return, 0.90),
        "win_rate": _series_rate(end_return > 0),
        "loss_rate": _series_rate(end_return < 0),
        "avg_win_pct": _series_mean(wins),
        "avg_loss_pct": _series_mean(losses),
        "median_loss_pct": _series_median(losses),
        "profit_loss_ratio": _profit_loss_ratio(wins, losses),
        "avg_max_favorable_return_pct": _series_mean(favorable),
        "median_max_favorable_return_pct": _series_median(favorable),
        "avg_max_adverse_return_pct": _series_mean(adverse),
        "median_max_adverse_return_pct": _series_median(adverse),
        "mfe_mae_ratio": _mfe_mae_ratio(favorable, adverse),
        "worst_end_return_pct": _series_min(end_return),
        "worst_adverse_return_pct": _series_min(adverse),
        "extreme_loss_rate_3pct": _series_rate(end_return <= -0.03),
        "extreme_loss_rate_5pct": _series_rate(end_return <= -0.05),
        "adverse_3pct_rate": _event_hit_rate(data, "drawdown_3pct_hit_bar"),
        "adverse_5pct_rate": _event_hit_rate(data, "drawdown_5pct_hit_bar"),
        "target_1pct_rate": _event_hit_rate(data, "target_1pct_hit_bar"),
        "target_2pct_rate": _event_hit_rate(data, "target_2pct_hit_bar"),
        "target_3pct_rate": _event_hit_rate(data, "target_3pct_hit_bar"),
        "avg_future_bar_count": _frame_mean(data, "future_bar_count"),
    }
    if group_col is not None:
        record[group_col] = group_value
    return record


def _summarize_sell_event_study(sell_event_study: pd.DataFrame, *, top_n_values: list[int]) -> pd.DataFrame:
    return _summarize_sell_event_study_by(sell_event_study, top_n_values=top_n_values, group_col=None)


def _summarize_sell_event_study_by(
    sell_event_study: pd.DataFrame,
    *,
    top_n_values: list[int],
    group_col: str | None,
) -> pd.DataFrame:
    if sell_event_study.empty:
        return pd.DataFrame()
    records: list[dict[str, object]] = []
    for top_n in sorted(top_n_values):
        data = sell_event_study[pd.to_numeric(sell_event_study["rank"], errors="coerce") <= top_n].copy()
        if data.empty:
            continue
        if group_col is None:
            for horizon, group in data.groupby("horizon_bars", dropna=False):
                records.append(_sell_event_summary_record(top_n=top_n, horizon_bars=horizon, data=group))
        elif group_col in data.columns:
            data[group_col] = data[group_col].fillna("UNKNOWN").replace("", "UNKNOWN")
            for (horizon, group_value), group in data.groupby(["horizon_bars", group_col], dropna=False):
                records.append(
                    _sell_event_summary_record(
                        top_n=top_n,
                        horizon_bars=horizon,
                        data=group,
                        group_col=group_col,
                        group_value=group_value,
                    )
                )
    return pd.DataFrame(records)


def _sell_event_summary_record(
    *,
    top_n: int,
    horizon_bars: object,
    data: pd.DataFrame,
    group_col: str | None = None,
    group_value: object | None = None,
) -> dict[str, object]:
    end_return = pd.to_numeric(data["end_return_pct"], errors="coerce").dropna()
    missed_upside = pd.to_numeric(data["max_missed_upside_pct"], errors="coerce").dropna()
    avoided_drawdown = pd.to_numeric(data["max_avoided_drawdown_pct"], errors="coerce").dropna()
    sell_valid_rate = _bool_mean(data, "sell_valid")
    sell_flying_rate = _bool_mean(data, "sell_flying")
    protection_ratio = _protection_to_missed_ratio(avoided_drawdown, missed_upside)
    record: dict[str, object] = {
        "top_n": top_n,
        "horizon_bars": int(horizon_bars),
        "event_count": int(len(data)),
        "valid_event_count": int(len(end_return)),
        "avg_end_return_pct": _series_mean(end_return),
        "median_end_return_pct": _series_median(end_return),
        "p10_end_return_pct": _series_quantile(end_return, 0.10),
        "p25_end_return_pct": _series_quantile(end_return, 0.25),
        "p75_end_return_pct": _series_quantile(end_return, 0.75),
        "p90_end_return_pct": _series_quantile(end_return, 0.90),
        "end_nonpositive_rate": _series_rate(end_return <= 0),
        "risk_avoided_rate": _bool_mean(data, "risk_avoided"),
        "sell_valid_rate": sell_valid_rate,
        "sell_flying_rate": sell_flying_rate,
        "avg_missed_upside_pct": _series_mean(missed_upside),
        "median_missed_upside_pct": _series_median(missed_upside),
        "worst_missed_upside_pct": _series_max(missed_upside),
        "avg_avoided_drawdown_pct": _series_mean(avoided_drawdown),
        "median_avoided_drawdown_pct": _series_median(avoided_drawdown),
        "max_avoided_drawdown_pct": _series_max(avoided_drawdown),
        "protection_to_missed_ratio": protection_ratio,
        "drawdown_1pct_rate": _event_hit_rate(data, "drawdown_1pct_hit_bar"),
        "drawdown_2pct_rate": _event_hit_rate(data, "drawdown_2pct_hit_bar"),
        "drawdown_3pct_rate": _event_hit_rate(data, "drawdown_3pct_hit_bar"),
        "drawdown_5pct_rate": _event_hit_rate(data, "drawdown_5pct_hit_bar"),
        "rally_1pct_rate": _event_hit_rate(data, "rally_1pct_hit_bar"),
        "rally_2pct_rate": _event_hit_rate(data, "rally_2pct_hit_bar"),
        "rally_3pct_rate": _event_hit_rate(data, "rally_3pct_hit_bar"),
        "rally_5pct_rate": _event_hit_rate(data, "rally_5pct_hit_bar"),
        "avg_future_bar_count": _frame_mean(data, "future_bar_count"),
        "sell_event_decision": _sell_event_decision(
            event_count=int(len(end_return)),
            sell_valid_rate=sell_valid_rate,
            sell_flying_rate=sell_flying_rate,
            avg_end_return=_series_mean(end_return),
            protection_to_missed_ratio=protection_ratio,
        ),
    }
    if group_col is not None:
        record[group_col] = group_value
    return record


def _summarize_volume_price_window_study(study: pd.DataFrame, *, top_n_values: list[int]) -> pd.DataFrame:
    if study.empty:
        return pd.DataFrame()
    records: list[dict[str, object]] = []
    for top_n in sorted(top_n_values):
        data = study[pd.to_numeric(study["rank"], errors="coerce") <= top_n].copy()
        if data.empty:
            continue
        data["volume_price_state"] = data["volume_price_state"].fillna("UNKNOWN").replace("", "UNKNOWN")
        for (event_side, horizon, lookback, state), group in data.groupby(
            ["event_side", "horizon_bars", "lookback_bars", "volume_price_state"],
            dropna=False,
        ):
            records.append(
                _volume_price_window_summary_record(
                    top_n=top_n,
                    event_side=event_side,
                    horizon_bars=horizon,
                    lookback_bars=lookback,
                    volume_price_state=state,
                    data=group,
                )
            )
    return pd.DataFrame(records)


def _volume_price_window_summary_record(
    *,
    top_n: int,
    event_side: object,
    horizon_bars: object,
    lookback_bars: object,
    volume_price_state: object,
    data: pd.DataFrame,
) -> dict[str, object]:
    end_return = pd.to_numeric(data["end_return_pct"], errors="coerce").dropna()
    favorable = pd.to_numeric(data.get("max_favorable_return_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    adverse = pd.to_numeric(data.get("max_adverse_return_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    missed_upside = pd.to_numeric(data.get("max_missed_upside_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    avoided_drawdown = pd.to_numeric(data.get("max_avoided_drawdown_pct", pd.Series(dtype=float)), errors="coerce").dropna()
    wins = end_return[end_return > 0]
    losses = end_return[end_return < 0]
    event_side_text = str(event_side)
    record: dict[str, object] = {
        "top_n": top_n,
        "event_side": event_side_text,
        "horizon_bars": int(horizon_bars),
        "lookback_bars": int(lookback_bars),
        "volume_price_state": volume_price_state,
        "event_count": int(len(data)),
        "valid_event_count": int(len(end_return)),
        "avg_price_return_pct": _frame_mean(data, "price_return_pct"),
        "avg_price_sma_gap_pct": _frame_mean(data, "price_sma_gap_pct"),
        "avg_price_efficiency": _frame_mean(data, "price_efficiency"),
        "avg_price_volatility_pct": _frame_mean(data, "price_volatility_pct"),
        "avg_volume_signal_pct": _frame_mean(data, "volume_signal_pct"),
        "avg_volume_ratio_to_prev": _frame_mean(data, "volume_ratio_to_prev"),
        "avg_price_volume_corr": _frame_mean(data, "price_volume_corr"),
        "avg_up_bar_share": _frame_mean(data, "up_bar_share"),
        "avg_end_return_pct": _series_mean(end_return),
        "median_end_return_pct": _series_median(end_return),
        "win_rate": _series_rate(end_return > 0),
        "profit_loss_ratio": _profit_loss_ratio(wins, losses),
        "avg_max_favorable_return_pct": _series_mean(favorable),
        "avg_max_adverse_return_pct": _series_mean(adverse),
        "target_2pct_rate": _event_hit_rate(data, "target_2pct_hit_bar"),
        "adverse_3pct_rate": _event_hit_rate(data, "drawdown_3pct_hit_bar"),
        "sell_valid_rate": _bool_mean(data, "sell_valid"),
        "sell_flying_rate": _bool_mean(data, "sell_flying"),
        "risk_avoided_rate": _bool_mean(data, "risk_avoided"),
        "avg_missed_upside_pct": _series_mean(missed_upside),
        "avg_avoided_drawdown_pct": _series_mean(avoided_drawdown),
        "protection_to_missed_ratio": _protection_to_missed_ratio(avoided_drawdown, missed_upside),
    }
    if event_side_text == "buy":
        record["signal_value_score"] = float(record["avg_end_return_pct"]) + 0.25 * float(record["avg_max_favorable_return_pct"]) - 0.25 * abs(float(record["avg_max_adverse_return_pct"]))
    elif event_side_text == "sell_exit":
        record["signal_value_score"] = float(record["sell_valid_rate"]) - float(record["sell_flying_rate"])
    else:
        record["signal_value_score"] = 0.0
    return record


def _protection_to_missed_ratio(avoided_drawdown: pd.Series, missed_upside: pd.Series) -> float:
    avg_missed = _series_mean(missed_upside)
    return float(_series_mean(avoided_drawdown) / avg_missed) if avg_missed > 0 else 0.0


def _sell_event_decision(
    *,
    event_count: int,
    sell_valid_rate: float,
    sell_flying_rate: float,
    avg_end_return: float,
    protection_to_missed_ratio: float,
) -> str:
    if event_count < 10:
        return "review_low_sample"
    if sell_valid_rate < 0.35 and sell_flying_rate >= 0.40 and avg_end_return > 0:
        return "delete_or_disable"
    if sell_valid_rate < 0.45 or avg_end_return > 0.005:
        return "downweight"
    if sell_flying_rate > 0.35 and protection_to_missed_ratio < 1.0:
        return "downweight"
    return "keep"


def _series_mean(values: pd.Series) -> float:
    return float(values.mean()) if not values.empty else 0.0


def _series_median(values: pd.Series) -> float:
    return float(values.median()) if not values.empty else 0.0


def _series_quantile(values: pd.Series, quantile: float) -> float:
    return float(values.quantile(quantile)) if not values.empty else 0.0


def _series_min(values: pd.Series) -> float:
    return float(values.min()) if not values.empty else 0.0


def _series_max(values: pd.Series) -> float:
    return float(values.max()) if not values.empty else 0.0


def _series_rate(values: pd.Series) -> float:
    return float(values.mean()) if not values.empty else 0.0


def _profit_loss_ratio(wins: pd.Series, losses: pd.Series) -> float:
    avg_win = _series_mean(wins)
    avg_loss = abs(_series_mean(losses))
    return float(avg_win / avg_loss) if avg_loss > 0 else 0.0


def _mfe_mae_ratio(favorable: pd.Series, adverse: pd.Series) -> float:
    avg_favorable = _series_mean(favorable)
    avg_adverse = abs(_series_mean(adverse))
    return float(avg_favorable / avg_adverse) if avg_adverse > 0 else 0.0


def _event_hit_rate(data: pd.DataFrame, column: str) -> float:
    if data.empty or column not in data:
        return 0.0
    return float(data[column].notna().mean())


def _bool_mean(data: pd.DataFrame, column: str) -> float:
    if data.empty or column not in data:
        return 0.0
    values = data[column].dropna()
    return float(values.astype(bool).mean()) if not values.empty else 0.0


def _capture_bias_constraint_summary(
    rule_ids: frozenset[str] | None,
    constraints: CaptureBiasRuleConstraints,
) -> str:
    parts: list[str] = []
    if rule_ids is not None:
        parts.append("规则池=" + ",".join(sorted(rule_ids)))
    for field, value in asdict(constraints).items():
        if value is not None:
            parts.append(f"{field}={value}")
    return "无" if not parts else "；".join(parts)


def _format_report(
    *,
    windows: list[WindowSpec],
    train_frame: pd.DataFrame,
    valid_frame: pd.DataFrame,
    ranked: pd.DataFrame,
    rules: pd.DataFrame,
    portfolio_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    attribution_frame: pd.DataFrame,
    initial_capital: float,
    paths: dict[str, Path],
    config: DividendTBacktestConfig,
    market_filter_lookback_days: int,
    force_rule_id: str | None,
    rule_selection_mode: str,
    rule_selection_top_n: int | None,
    capture_bias_rule_ids: frozenset[str] | None,
    capture_bias_constraints: CaptureBiasRuleConstraints,
    export_trades: bool,
    trade_quality_summary: pd.DataFrame,
    buy_event_summary: pd.DataFrame,
    buy_event_breakout_summary: pd.DataFrame,
    sell_event_summary: pd.DataFrame,
    sell_event_reason_summary: pd.DataFrame,
    volume_price_window_summary: pd.DataFrame,
) -> str:
    train_ok = train_frame[train_frame["status"] == "ok"]
    valid_ok = valid_frame[valid_frame["status"] == "ok"]
    summary_table = "\n".join(_summary_row(row) for _, row in summary_frame.sort_values(["portfolio_weighting", "top_n"]).iterrows())
    available_top_n = sorted(int(value) for value in portfolio_frame["top_n"].dropna().unique())
    primary_top_n = 100 if 100 in available_top_n else available_top_n[0]
    window_table = "\n".join(_window_row(row) for _, row in portfolio_frame[portfolio_frame["top_n"] == primary_top_n].sort_values("valid_start").iterrows())
    latest_window_id = windows[-1].window_id
    latest_ranked = ranked[ranked["window_id"] == latest_window_id].sort_values("rank")
    top_candidates = "\n".join(_candidate_row(row) for _, row in latest_ranked.head(20).iterrows())
    top_rules = (
        rules[rules["top_n"] == primary_top_n]
        .sort_values(["window_id", "train_objective"], ascending=[True, False])
        .groupby("window_id", as_index=False)
        .head(1)
    )
    rule_table = "\n".join(_rule_row(row) for _, row in top_rules.iterrows())
    leakage_reason_table = _leakage_reason_table(attribution_frame)
    leakage_secondary_table = _leakage_secondary_table(attribution_frame)
    leakage_beta_hold_stall_table = _leakage_beta_hold_stall_table(attribution_frame)
    leakage_top_table = _leakage_top_table(attribution_frame.head(15))
    trade_quality_section = _trade_quality_report_section(trade_quality_summary, paths=paths) if export_trades else ""
    buy_event_section = _buy_event_report_section(buy_event_summary, paths=paths) if export_trades else ""
    breakout_event_section = _breakout_event_report_section(buy_event_breakout_summary, paths=paths) if export_trades else ""
    sell_event_section = _sell_event_report_section(sell_event_summary, sell_event_reason_summary, paths=paths) if export_trades else ""
    volume_price_window_section = _volume_price_window_report_section(volume_price_window_summary, paths=paths) if export_trades else ""
    target_add_mean = float(valid_ok["risk_on_target_add_count"].mean()) if "risk_on_target_add_count" in valid_ok else 0.0
    target_add_density = (
        float((valid_ok["risk_on_target_add_count"] / valid_ok["rows"].replace(0, pd.NA) * 10_000.0).fillna(0.0).mean())
        if {"risk_on_target_add_count", "rows"}.issubset(valid_ok.columns)
        else 0.0
    )
    beta_hold_entry_mean = _frame_mean(valid_ok, "beta_hold_entry_count")
    beta_hold_bar_mean = _frame_mean(valid_ok, "beta_hold_bar_count")
    beta_hold_share_mean = _frame_mean(valid_ok, "beta_hold_share")
    wait_beta_hold_mean = _frame_mean(valid_ok, "wait_beta_hold_count")
    full_position_share_mean = _frame_mean(valid_ok, "full_position_share")
    risk_on_after_1d_mean = _frame_mean(valid_ok, "risk_on_after_1d_avg_position_pct")
    risk_on_after_3d_mean = _frame_mean(valid_ok, "risk_on_after_3d_avg_position_pct")
    risk_on_after_5d_mean = _frame_mean(valid_ok, "risk_on_after_5d_avg_position_pct")
    risk_on_after_10d_mean = _frame_mean(valid_ok, "risk_on_after_10d_avg_position_pct")
    strong_confirm_avg_bars = _frame_mean(valid_ok, "strong_confirm_to_exit_avg_bars")
    beta_hold_episode_avg_bars = _frame_mean(valid_ok, "beta_hold_episode_avg_bars")
    market_score_mean = _frame_mean(valid_ok, "market_score_avg")
    market_trend_score_mean = _frame_mean(valid_ok, "market_trend_score_avg")
    market_breadth_score_mean = _frame_mean(valid_ok, "market_breadth_score_avg")
    market_amount_score_mean = _frame_mean(valid_ok, "market_amount_score_avg")
    market_limit_structure_score_mean = _frame_mean(valid_ok, "market_limit_structure_score_avg")
    market_industry_diffusion_score_mean = _frame_mean(valid_ok, "market_industry_diffusion_score_avg")
    market_model_state_score_mean = _frame_mean(valid_ok, "market_model_state_score_avg")
    model_holding_win_rate_mean = _frame_mean(valid_ok, "model_holding_win_rate_avg")
    model_holding_profit_spread_mean = _frame_mean(valid_ok, "model_holding_profit_spread_avg")
    model_new_buy_success_rate_mean = _frame_mean(valid_ok, "model_new_buy_success_rate_avg")
    return (
        "# Top1000 多窗口筛选规则训练与组合验证\n\n"
        "## 结论\n\n"
        "- 本报告使用多窗口 walk-forward 口径：每个窗口只用历史训练段学习筛选规则，再在下一段验证期交易候选股。\n"
        "- 训练目标已从低回撤候选池升级为“低回撤 + 趋势收益捕获”：评分同时奖励趋势强度、上涨捕获、超额排名、进攻触发和风险控制。\n"
        "- 组合结果应优先看多窗口复利收益、同期买入持有基准、窗口胜率和最差窗口回撤。\n\n"
        "## 数据与切分\n\n"
        f"- 窗口数量：{len(windows)}\n"
        f"- 首个训练段：{windows[0].train_start} 至 {windows[0].train_end}\n"
        f"- 最后验证段：{windows[-1].valid_start} 至 {windows[-1].valid_end}\n"
        f"- 训练成功：{len(train_ok)} / {len(train_frame)}\n"
        f"- 验证成功：{len(valid_ok)} / {len(valid_frame)}\n"
        f"- 策略模式：{config.strategy_mode}\n"
        f"- 市场过滤：{'开启' if config.enable_market_filter else '关闭'}（每个窗口独立构建复合 RISK_ON 代理：趋势/宽度/成交额/涨跌停/行业扩散/模型自身状态，向前带 {market_filter_lookback_days} 天历史）\n"
        f"- RISK_ON 盈利扩散穿透：开启；持仓胜率/浮盈扩散/新买点成功率会参与复合 RISK_ON 升级与降级\n"
        f"- 规则选择：{rule_selection_mode}；选择 TopN：{rule_selection_top_n if rule_selection_top_n is not None else 'legacy-min'}；强制规则：{force_rule_id or '无'}\n"
        f"- Capture-bias 候选约束：{_capture_bias_constraint_summary(capture_bias_rule_ids, capture_bias_constraints)}\n"
        f"- 组合权重：{portfolio_frame['portfolio_weighting'].iloc[0] if 'portfolio_weighting' in portfolio_frame.columns and not portfolio_frame.empty else 'equal'}\n"
        f"- T_SELL 执行：{'开启' if config.enable_t_sell else '关闭'}；关闭时普通 T 卖和倒 T 卖只计信号、不执行\n"
        f"- 候选池入选建仓：{'开启' if config.enable_candidate_entry else '关闭'}；"
        f"验证期启动目标 {config.candidate_entry_start_target_pct:.0%}，"
        f"启动仓市场折扣 {'开启' if config.candidate_entry_start_respect_market_cap else '关闭'}，"
        f"启动窗口 {config.candidate_entry_start_max_bars} 根，"
        f"首次强趋势确认目标 {config.candidate_entry_confirm_target_pct:.0%}，"
        f"确认试探上限 {config.candidate_entry_confirm_probe_target_pct:.0%}，"
        f"跟随确认 {'开启' if config.candidate_entry_confirm_requires_follow_through else '关闭'}，"
        f"确认强度 ≥ {config.candidate_entry_confirm_min_strength:.1f}，"
        f"非 force 确认 ≥ {config.candidate_entry_confirm_min_confirmations}，"
        f"保护持有 {config.candidate_entry_min_hold_bars} 根，"
        f"硬止损 {config.candidate_entry_hard_stop_loss_pct:.0%}；"
        "仅对每个窗口训练后入选的组合曲线生效\n"
        f"- 信号步长：每 {config.signal_step_bars} 根 5 分钟 K 线\n\n"
        f"- RISK_ON 目标加仓：最低目标 {config.risk_on_target_add_min_target_pct:.0%}，"
        f"额外加权 {config.risk_on_target_add_bonus_pct:.0%}，"
        f"首买/低仓/中仓/高仓核心 cap {config.risk_on_first_add_cap_pct:.0%}/"
        f"{config.risk_on_low_position_add_cap_pct:.0%}/{config.risk_on_mid_position_add_cap_pct:.0%}，"
        f"{config.risk_on_high_position_reinforce_cap_pct:.0%}，"
        f"高质量突破升级目标 {config.risk_on_high_quality_breakout_upgrade_target_pct:.0%}，"
        f"高仓核心强化 {'开启' if config.enable_risk_on_high_position_reinforcement else '关闭'}，"
        f"二次加仓至少 {config.risk_on_secondary_add_min_confirmations} 个确认"
        f"（BETA_HOLD {config.risk_on_beta_hold_secondary_min_confirmations} 个），满仓需极强确认\n"
        f"- 组合层主升目标：{'开启' if config.enable_portfolio_main_rise_position_target else '关闭'}；"
        f"目标 {config.portfolio_main_rise_position_target_pct:.0%}，"
        f"模型状态 ≥ {config.portfolio_main_rise_min_model_state_score:.1f}，"
        f"持仓胜率/浮盈扩散/新买点成功率 ≥ "
        f"{config.portfolio_main_rise_min_holding_win_rate:.0%}/"
        f"{config.portfolio_main_rise_min_profit_spread:.0%}/"
        f"{config.portfolio_main_rise_min_new_buy_success_rate:.0%}\n"
        f"- RISK_ON 买后跟随确认：{config.risk_on_add_follow_through_bars} 根内新高 ≥ "
        f"{config.risk_on_add_follow_through_min_high_return_pct:.1%}，"
        f"量能 ≥ 前段均量 {config.risk_on_add_follow_through_volume_ratio:.0%}，"
        f"VWAP 容忍 {config.risk_on_add_follow_through_vwap_tolerance_pct:.1%}，"
        f"失败冷却 {config.risk_on_add_follow_through_failure_cooldown_bars} 根，"
        f"高位滞涨过滤 {'开启' if config.late_stage_stall_entry_filter_enabled else '关闭'}，"
        f"量价延续窗口 {config.volume_price_continuation_lookback_bars} 根，"
        f"价涨量缩延续阈值 {config.volume_price_continuation_min_return_pct:.1%}/"
        f"{config.volume_price_continuation_max_volume_ratio:.0%}\n"
        f"- 12/24bar 买点量价过滤：{'开启' if config.enable_buy_volume_price_window_filter else '关闭'}；"
        f"窗口 {config.buy_volume_price_short_lookback_bars}/{config.buy_volume_price_mid_lookback_bars} 根，"
        f"最小涨幅 {config.buy_volume_price_filter_min_return_pct:.1%}，"
        f"缩量阈值 {config.buy_volume_price_filter_max_contract_ratio:.0%}，"
        f"质量底线 {config.buy_volume_price_filter_min_quality_score:.2f}\n"
        f"- 突破买入跟随确认：{config.breakout_follow_through_bars} 根内新高 ≥ {config.breakout_follow_through_min_high_return_pct:.1%}，"
        f"量能 ≥ 前段均量 {config.breakout_follow_through_volume_ratio:.0%}，失败冷却 {config.breakout_follow_through_failure_cooldown_bars} 根；"
        f"直接突破买入 {'开启' if config.enable_breakout_direct_buy or config.breakout_direct_buy_probe_target_pct > 0 else '关闭'}，"
        f"探针上限 {config.breakout_direct_buy_probe_target_pct:.0%}，"
        f"需 RISK_ON 四重确认 {'是' if config.breakout_direct_buy_requires_risk_on_confirmation else '否'}\n\n"
        "## 50 万资金模拟\n\n"
        f"- 初始资金：{initial_capital:,.2f} 元\n"
        "- 资金曲线按各验证窗口组合收益顺序复利；训练窗口默认不交易，用于学习下一窗口规则。\n\n"
        "## 全量验证基线\n\n"
        f"- 全量窗口-单票策略均值：{_fmt_pct(valid_ok['total_return'].mean())}\n"
        f"- 全量窗口-单票策略中位数：{_fmt_pct(valid_ok['total_return'].median())}\n"
        f"- 全量窗口-单票盈利率：{_fmt_pct((valid_ok['total_return'] > 0).mean())}\n"
        f"- 全量窗口-单票平均最大回撤：{_fmt_pct(valid_ok['max_drawdown'].mean())}\n"
        f"- 全量窗口-单票买入持有均值：{_fmt_pct(valid_ok['benchmark_return'].mean())}\n"
        f"- 全量窗口-单票风险匹配持有均值：{_fmt_pct(valid_ok.get('risk_matched_benchmark_return', pd.Series(0.0, index=valid_ok.index)).mean())}\n\n"
        "## 持仓目标引擎\n\n"
        f"- 验证段单票平均目标补仓次数：{target_add_mean:.2f}\n"
        f"- 验证段单票平均目标补仓密度：每万根 5 分钟 K 线 {target_add_density:.2f} 次\n"
        "- 目标补仓密度用于诊断持仓引擎是否抓到 RISK_ON 加仓点；默认候选排序不直接按补仓次数加权，避免过度奖励交易频率。\n\n"
        "## 持仓生命周期诊断\n\n"
        f"- 验证段单票平均 BETA_HOLD 触发次数：{beta_hold_entry_mean:.2f}\n"
        f"- 验证段单票平均 BETA_HOLD 持有 bar：{beta_hold_bar_mean:.2f}，占比 {_fmt_pct(beta_hold_share_mean)}\n"
        f"- 验证段单票平均 WAIT_BETA_HOLD 次数：{wait_beta_hold_mean:.2f}\n"
        f"- 验证段单票满仓 bar 占比：{_fmt_pct(full_position_share_mean)}\n"
        f"- RISK_ON 后平均仓位：1日 {_fmt_pct(risk_on_after_1d_mean)}，3日 {_fmt_pct(risk_on_after_3d_mean)}，"
        f"5日 {_fmt_pct(risk_on_after_5d_mean)}，10日 {_fmt_pct(risk_on_after_10d_mean)}\n"
        f"- 复合 RISK_ON 均值：总分 {market_score_mean:.1f}，趋势 {market_trend_score_mean:.1f}，"
        f"宽度 {market_breadth_score_mean:.1f}，成交额 {market_amount_score_mean:.1f}，"
        f"涨跌停结构 {market_limit_structure_score_mean:.1f}，行业扩散 {market_industry_diffusion_score_mean:.1f}，"
        f"模型自身 {market_model_state_score_mean:.1f}；模型持仓胜率 {_fmt_pct(model_holding_win_rate_mean)}，"
        f"浮盈扩散 {_fmt_pct(model_holding_profit_spread_mean)}，新买点成功率 {_fmt_pct(model_new_buy_success_rate_mean)}\n"
        f"- 首次强趋势确认到退出平均持仓：{strong_confirm_avg_bars:.2f} bars；"
        f"BETA_HOLD episode 平均：{beta_hold_episode_avg_bars:.2f} bars\n\n"
        "## 多窗口组合汇总\n\n"
        "| 权重 | 组合 | 窗口数 | 期末权益 | 收益金额 | 多窗口复利 | 买入持有复利 | 风险匹配持有 | 超额 | 风险匹配超额 | 窗口胜率 | 最差窗口回撤 |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{summary_table}\n\n"
        f"## Top{primary_top_n} 分窗口结果\n\n"
        "| 窗口 | 训练段 | 验证段 | 规则 | 验证收益 | 买入持有 | 风险匹配持有 | 超额 | 风险匹配超额 | 最大回撤 | 成分盈利率 |\n"
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{window_table}\n\n"
        f"## 每窗口训练目标最高的 Top{primary_top_n} 参考规则\n\n"
        "| 窗口 | 规则 | 候选池 | 训练均值 | 训练趋势 | 上涨捕获 | 平均仓位 | 漏捕获惩罚 | 训练回撤 | STOP/交易 | 早退/交易 |\n"
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{rule_table}\n\n"
        f"## 最新窗口候选前 20（{latest_window_id}）\n\n"
        "| 排名 | 代码 | 名称 | 训练收益 | 买入持有 | 上涨捕获 | 训练回撤 | 信号密度 | 目标补仓密度 | 进攻占比 | STOP/交易 | 强beta | 主升 | 评分 |\n"
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{top_candidates}\n\n"
        "## 漏收益归因\n\n"
        "- 归因口径只统计验证段内买入持有收益为正的单票窗口，衡量策略是否错过上涨段。\n"
        "- `risk_on_position_underbuilt` 表示 RISK_ON、三买/突破/资金/量价确认已经存在，但实际仓位仍偏低；这是主升段漏收益的优先优化项。\n"
        "- `force_ratio_position_suppressed` 现在只在缺少非 force 确认时触发；有量价、突破、三买或资金确认时，不再把低 force_ratio 直接当作主因。\n"
        "- `sell_stop_early_exit` 表示上涨段里 SELL/STOP 密集且捕获率低；后续应检查进攻模式止盈/止损状态机。\n\n"
        "| 主要原因 | 股票窗口数 | 平均漏收益 | 平均捕获率 | 平均实际仓位 | 平均最大仓位 |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: |\n"
        f"{leakage_reason_table}\n\n"
        "### 量价二级归因\n\n"
        "| 二级原因 | 股票窗口数 | 平均漏收益 | 平均捕获率 | 平均目标补仓 | 平均实际仓位 |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: |\n"
        f"{leakage_secondary_table}\n\n"
        "### BETA_HOLD 下 stall 诊断\n\n"
        "| 分组 | 股票窗口数 | 平均漏收益 | 平均捕获率 | 平均 BETA_HOLD 占比 | 平均满仓占比 | 平均实际仓位 | 平均早退次数 |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{leakage_beta_hold_stall_table}\n\n"
        "### 最大漏收益样例\n\n"
        "| 窗口 | 代码 | 名称 | 买入持有 | 策略 | 捕获率 | RISK_ON | 三买/突破 | 资金确认 | 目标补仓 | force压制 | 早退 | avg/max仓位 | 原因 | 二级原因 |\n"
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- |\n"
        f"{leakage_top_table}\n\n"
        f"{trade_quality_section}"
        f"{buy_event_section}"
        f"{breakout_event_section}"
        f"{sell_event_section}"
        f"{volume_price_window_section}"
        "## 输出文件\n\n"
        f"- 训练段明细：`{paths['train']}`\n"
        f"- 验证段明细：`{paths['valid']}`\n"
        f"- 候选排序：`{paths['candidates']}`\n"
        f"- 规则搜索：`{paths['rules']}`\n"
        f"- 组合结果：`{paths['portfolio']}`\n\n"
        f"- 多窗口汇总：`{paths['summary']}`\n\n"
        f"- 漏收益归因：`{paths['attribution']}`\n\n"
        f"{_trade_quality_output_paths(paths) if export_trades else ''}"
        f"{_buy_event_output_paths(paths) if export_trades else ''}"
        f"{_sell_event_output_paths(paths) if export_trades else ''}"
        f"{_volume_price_window_output_paths(paths) if export_trades else ''}"
        "## 方法说明\n\n"
        "- `trend_strength` 使用训练段个股买入持有收益的正值部分，代表训练期是否处于可捕获趋势。\n"
        "- `upside_capture` 使用训练段策略收益 / 个股买入持有收益，且只在买入持有为正时有效，用于约束策略不能只低回撤但错过主升段。\n"
        "- `capture_shortfall` 对“个股上涨但策略捕获低于 70%”的部分按趋势强度扣分，用于惩罚主升段漏收益。\n"
        "- 每个验证窗口的规则只由本窗口训练段产生，规则搜索表不再使用验证段 preview 字段，避免规则选择泄漏验证期信息。\n\n"
        "## Caveats\n\n"
        "- 这仍是当前本地样本窗口内的滚动 walk-forward，不等于完整跨牛熊周期验证；应继续扩展到更长历史。\n"
        "- Top1000 universe 仍是当前快照，不是 point-in-time universe。\n"
        "- 验证段组合采用等权组合曲线；实际资金会受到 100 股手数、最低佣金、滑点和容量约束影响。\n"
    )


def _trade_quality_report_section(trade_quality_summary: pd.DataFrame, *, paths: dict[str, Path]) -> str:
    if trade_quality_summary.empty:
        table = "| n/a | 0 | 0 | 0 | 0 | n/a | n/a | n/a | n/a | n/a |"
    else:
        table = "\n".join(_trade_quality_row(row) for _, row in trade_quality_summary.sort_values("top_n").iterrows())
    return (
        "## 逐笔买卖点质量\n\n"
        "- 买点准确：买后 N 根 bar 内最大收益达到阈值，且先于止损阈值触发。\n"
        "- 卖点准确：卖后 N 根 bar 内先出现回撤阈值，或 N 根结束仍未高于卖出价。\n"
        "- 卖飞：卖后 N 根 bar 内继续上涨超过阈值；该指标独立于卖点准确率。\n\n"
        "| 组合 | 择时交易数 | 全量成交数 | 买入数 | 卖出/止损数 | 买点准确 | 卖点准确 | 卖飞率 | 买后最大收益 | 卖后最大上涨 |\n"
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{table}\n\n"
        f"- 逐笔交易：`{paths['trades']}`\n"
        f"- 逐笔质量标签：`{paths['trade_quality']}`\n"
        f"- 质量汇总：`{paths['trade_quality_summary']}`\n\n"
    )


def _trade_quality_row(row: pd.Series) -> str:
    timing_trade_count = int(row.get("timing_trade_count", row["trade_count"]))
    return (
        f"| Top {int(row['top_n'])} | {timing_trade_count} | {int(row['trade_count'])} | "
        f"{int(row['buy_trade_count'])} | "
        f"{int(row['sell_exit_trade_count'])} | {_fmt_pct(row['buy_accuracy'])} | "
        f"{_fmt_pct(row['sell_accuracy'])} | {_fmt_pct(row['sell_flying_rate'])} | "
        f"{_fmt_pct(row['avg_buy_future_max_return_pct'])} | {_fmt_pct(row['avg_sell_future_max_return_pct'])} |"
    )


def _buy_event_report_section(buy_event_summary: pd.DataFrame, *, paths: dict[str, Path]) -> str:
    if buy_event_summary.empty:
        table = "| n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |"
    else:
        table = "\n".join(
            _buy_event_row(row)
            for _, row in buy_event_summary.sort_values(["top_n", "horizon_bars"]).iterrows()
        )
    return (
        "## 买点事件研究\n\n"
        "- 仅统计模型确认买入事件，不含候选池启动仓和倒 T 买回。\n"
        "- 终点收益使用买后 N 根 bar 的收盘价；最大浮盈/最大浮亏分别使用窗口内最高价/最低价。\n"
        "- 盈亏比 = 平均盈利 / 平均亏损绝对值；极端亏损率统计终点收益 ≤ -3% / ≤ -5%。\n\n"
        "| 组合 | Horizon | 买点数 | 平均收益 | 中位收益 | 胜率 | 盈亏比 | 平均最大浮盈 | 平均最大浮亏 | 最差终点 | 最差浮亏 | ≤-3% / ≤-5% |\n"
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{table}\n\n"
        f"- 买点事件明细：`{paths['buy_event_study']}`\n"
        f"- 买点总体汇总：`{paths['buy_event_summary']}`\n"
        f"- 买点行业汇总：`{paths['buy_event_industry_summary']}`\n"
        f"- 买点市场环境汇总：`{paths['buy_event_market_summary']}`\n\n"
    )


def _breakout_event_report_section(breakout_summary: pd.DataFrame, *, paths: dict[str, Path]) -> str:
    if breakout_summary.empty:
        table = "| n/a | n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a |"
    else:
        table = "\n".join(
            _breakout_event_row(row)
            for _, row in breakout_summary.sort_values(
                ["top_n", "horizon_bars", "breakout_alpha_tier"],
                key=_breakout_event_sort_key,
            ).iterrows()
        )
    return (
        "## 高质量突破确认分层\n\n"
        "- `high_quality_breakout` 要求突破、VWAP、量能延续、资金确认和低抛压/低下行概率同时成立。\n"
        "- `qualified_breakout` 是可用但未达到高质量的确认突破；`weak_follow`/`stall_pressure` 用于识别容易冲高回落的突破。\n"
        "- 该分层只做事件研究，不改变默认交易动作；默认加仓仍由 RISK_ON_TARGET_ADD 执行。\n\n"
        "| 组合 | Horizon | Tier | 事件数 | 平均收益 | 胜率 | 盈亏比 | 平均最大浮盈 | 平均最大浮亏 | ≤-3% / ≤-5% |\n"
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{table}\n\n"
        f"- 突破分层汇总：`{paths['buy_event_breakout_summary']}`\n\n"
    )


def _breakout_event_sort_key(values: pd.Series) -> pd.Series:
    order = {
        "high_quality_breakout": 0,
        "qualified_breakout": 1,
        "stall_pressure_breakout": 2,
        "weak_follow_breakout": 3,
        "low_quality_breakout": 4,
        "no_breakout_alpha": 5,
    }
    if values.name == "breakout_alpha_tier":
        return values.map(order).fillna(99)
    return values


def _breakout_event_row(row: pd.Series) -> str:
    return (
        f"| Top {int(row['top_n'])} | {int(row['horizon_bars'])} | {row['breakout_alpha_tier']} | "
        f"{int(row['event_count'])} | {_fmt_pct(row['avg_end_return_pct'])} | "
        f"{_fmt_pct(row['win_rate'])} | {float(row['profit_loss_ratio']):.2f} | "
        f"{_fmt_pct(row['avg_max_favorable_return_pct'])} | {_fmt_pct(row['avg_max_adverse_return_pct'])} | "
        f"{_fmt_pct(row['extreme_loss_rate_3pct'])} / {_fmt_pct(row['extreme_loss_rate_5pct'])} |"
    )


def _buy_event_row(row: pd.Series) -> str:
    return (
        f"| Top {int(row['top_n'])} | {int(row['horizon_bars'])} | {int(row['event_count'])} | "
        f"{_fmt_pct(row['avg_end_return_pct'])} | {_fmt_pct(row['median_end_return_pct'])} | "
        f"{_fmt_pct(row['win_rate'])} | {float(row['profit_loss_ratio']):.2f} | "
        f"{_fmt_pct(row['avg_max_favorable_return_pct'])} | {_fmt_pct(row['avg_max_adverse_return_pct'])} | "
        f"{_fmt_pct(row['worst_end_return_pct'])} | {_fmt_pct(row['worst_adverse_return_pct'])} | "
        f"{_fmt_pct(row['extreme_loss_rate_3pct'])} / {_fmt_pct(row['extreme_loss_rate_5pct'])} |"
    )


def _trade_quality_output_paths(paths: dict[str, Path]) -> str:
    return (
        f"- 逐笔交易：`{paths['trades']}`\n"
        f"- 逐笔质量标签：`{paths['trade_quality']}`\n"
        f"- 逐笔质量汇总：`{paths['trade_quality_summary']}`\n\n"
    )


def _buy_event_output_paths(paths: dict[str, Path]) -> str:
    return (
        f"- 买点事件明细：`{paths['buy_event_study']}`\n"
        f"- 买点总体汇总：`{paths['buy_event_summary']}`\n"
        f"- 买点行业汇总：`{paths['buy_event_industry_summary']}`\n"
        f"- 买点市场环境汇总：`{paths['buy_event_market_summary']}`\n\n"
        f"- 买点突破分层汇总：`{paths['buy_event_breakout_summary']}`\n\n"
    )


def _sell_event_report_section(
    sell_event_summary: pd.DataFrame,
    sell_event_reason_summary: pd.DataFrame,
    *,
    paths: dict[str, Path],
) -> str:
    if sell_event_summary.empty:
        summary_table = "| n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |"
    else:
        summary_table = "\n".join(
            _sell_event_row(row)
            for _, row in sell_event_summary.sort_values(["top_n", "horizon_bars"]).iterrows()
        )
    if sell_event_reason_summary.empty:
        reason_table = "| n/a | n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a |"
    else:
        reason_table = "\n".join(
            _sell_event_reason_row(row)
            for _, row in sell_event_reason_summary.sort_values(["top_n", "horizon_bars", "sell_event_type"]).iterrows()
        )
    return (
        "## 卖点事件研究\n\n"
        "- 仅统计真实卖出/减仓事件，不含倒 T 买回、底仓再平衡和候选池启动仓。\n"
        "- 卖后终点收益为正代表卖出后继续上涨，偏卖飞；为负代表卖出后下跌，偏规避风险。\n"
        "- 有效卖点：卖后先触发回撤阈值，或未触发卖飞且窗口结束不高于卖出价。\n"
        "- 决策建议：`keep` 保留；`downweight` 降权；`delete_or_disable` 候选删除/关闭；`review_low_sample` 样本不足。\n\n"
        "| 组合 | Horizon | 卖点数 | 平均卖后收益 | 中位卖后收益 | 有效率 | 卖飞率 | 平均错过上涨 | 平均规避回撤 | 保护/卖飞比 | 建议 |\n"
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
        f"{summary_table}\n\n"
        "### 按卖点原因拆分\n\n"
        "| 组合 | Horizon | 类型 | 卖点数 | 平均卖后收益 | 有效率 | 卖飞率 | 平均错过上涨 | 平均规避回撤 | 建议 |\n"
        "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
        f"{reason_table}\n\n"
        f"- 卖点事件明细：`{paths['sell_event_study']}`\n"
        f"- 卖点总体汇总：`{paths['sell_event_summary']}`\n"
        f"- 卖点原因汇总：`{paths['sell_event_reason_summary']}`\n"
        f"- 卖点市场环境汇总：`{paths['sell_event_market_summary']}`\n\n"
    )


def _sell_event_row(row: pd.Series) -> str:
    return (
        f"| Top {int(row['top_n'])} | {int(row['horizon_bars'])} | {int(row['event_count'])} | "
        f"{_fmt_pct(row['avg_end_return_pct'])} | {_fmt_pct(row['median_end_return_pct'])} | "
        f"{_fmt_pct(row['sell_valid_rate'])} | {_fmt_pct(row['sell_flying_rate'])} | "
        f"{_fmt_pct(row['avg_missed_upside_pct'])} | {_fmt_pct(row['avg_avoided_drawdown_pct'])} | "
        f"{float(row['protection_to_missed_ratio']):.2f} | {row['sell_event_decision']} |"
    )


def _sell_event_reason_row(row: pd.Series) -> str:
    return (
        f"| Top {int(row['top_n'])} | {int(row['horizon_bars'])} | {row['sell_event_type']} | "
        f"{int(row['event_count'])} | {_fmt_pct(row['avg_end_return_pct'])} | "
        f"{_fmt_pct(row['sell_valid_rate'])} | {_fmt_pct(row['sell_flying_rate'])} | "
        f"{_fmt_pct(row['avg_missed_upside_pct'])} | {_fmt_pct(row['avg_avoided_drawdown_pct'])} | "
        f"{row['sell_event_decision']} |"
    )


def _volume_price_window_report_section(summary: pd.DataFrame, *, paths: dict[str, Path]) -> str:
    if summary.empty:
        buy_table = "| n/a | n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a |"
        sell_table = "| n/a | n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a |"
        selected_top_n = "n/a"
        selected_horizon = "n/a"
    else:
        top_values = sorted(int(value) for value in summary["top_n"].dropna().unique())
        selected_top_n = 100 if 100 in top_values else top_values[-1]
        horizon_values = sorted(int(value) for value in summary["horizon_bars"].dropna().unique())
        selected_horizon = 20 if 20 in horizon_values else horizon_values[min(len(horizon_values) - 1, 0)]
        selected = summary[
            (pd.to_numeric(summary["top_n"], errors="coerce") == selected_top_n)
            & (pd.to_numeric(summary["horizon_bars"], errors="coerce") == selected_horizon)
        ].copy()
        buy = selected[(selected["event_side"] == "buy") & (pd.to_numeric(selected["event_count"], errors="coerce") >= 20)]
        sell = selected[(selected["event_side"] == "sell_exit") & (pd.to_numeric(selected["event_count"], errors="coerce") >= 30)]
        buy = buy.sort_values(["signal_value_score", "event_count"], ascending=[False, False]).head(12)
        sell = sell.sort_values(["signal_value_score", "event_count"], ascending=[False, False]).head(12)
        buy_table = "\n".join(_volume_price_buy_row(row) for _, row in buy.iterrows()) if not buy.empty else "| n/a | n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a |"
        sell_table = "\n".join(_volume_price_sell_row(row) for _, row in sell.iterrows()) if not sell.empty else "| n/a | n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a |"
    return (
        "## 量价滑动窗口事件研究\n\n"
        "- 对每笔买入/卖出，使用成交前历史 bar 计算滑动窗口特征，避免使用成交后数据。\n"
        "- 窗口特征包括价格趋势、均线偏离、路径效率、量能相对前窗变化、量价相关和量价状态。\n"
        f"- 下表展示 Top {selected_top_n}、未来 {selected_horizon} 根 bar 评价窗口下，样本过滤后的量价状态：买点 n≥20，卖点 n≥30。\n\n"
        "### 买点量价状态\n\n"
        "| 回看窗口 | 量价状态 | 事件数 | 买后收益 | 胜率 | 盈亏比 | 平均MFE | 平均MAE | 量能变化 |\n"
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{buy_table}\n\n"
        "### 卖点量价状态\n\n"
        "| 回看窗口 | 量价状态 | 事件数 | 卖后收益 | 有效率 | 卖飞率 | 规避回撤 | 错过上涨 | 量能变化 |\n"
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{sell_table}\n\n"
        f"- 量价滑动窗口明细：`{paths['volume_price_window_study']}`\n"
        f"- 量价滑动窗口汇总：`{paths['volume_price_window_summary']}`\n\n"
    )


def _volume_price_buy_row(row: pd.Series) -> str:
    return (
        f"| {int(row['lookback_bars'])} | {row['volume_price_state']} | {int(row['event_count'])} | "
        f"{_fmt_pct(row['avg_end_return_pct'])} | {_fmt_pct(row['win_rate'])} | "
        f"{float(row['profit_loss_ratio']):.2f} | {_fmt_pct(row['avg_max_favorable_return_pct'])} | "
        f"{_fmt_pct(row['avg_max_adverse_return_pct'])} | {_fmt_pct(row['avg_volume_signal_pct'])} |"
    )


def _volume_price_sell_row(row: pd.Series) -> str:
    return (
        f"| {int(row['lookback_bars'])} | {row['volume_price_state']} | {int(row['event_count'])} | "
        f"{_fmt_pct(row['avg_end_return_pct'])} | {_fmt_pct(row['sell_valid_rate'])} | "
        f"{_fmt_pct(row['sell_flying_rate'])} | {_fmt_pct(row['avg_avoided_drawdown_pct'])} | "
        f"{_fmt_pct(row['avg_missed_upside_pct'])} | {_fmt_pct(row['avg_volume_signal_pct'])} |"
    )


def _sell_event_output_paths(paths: dict[str, Path]) -> str:
    return (
        f"- 卖点事件明细：`{paths['sell_event_study']}`\n"
        f"- 卖点总体汇总：`{paths['sell_event_summary']}`\n"
        f"- 卖点原因汇总：`{paths['sell_event_reason_summary']}`\n"
        f"- 卖点市场环境汇总：`{paths['sell_event_market_summary']}`\n\n"
    )


def _volume_price_window_output_paths(paths: dict[str, Path]) -> str:
    return (
        f"- 量价滑动窗口明细：`{paths['volume_price_window_study']}`\n"
        f"- 量价滑动窗口汇总：`{paths['volume_price_window_summary']}`\n\n"
    )


def _leakage_reason_table(attribution_frame: pd.DataFrame) -> str:
    if attribution_frame.empty:
        return "| n/a | 0 | n/a | n/a | n/a | n/a |"
    grouped = (
        attribution_frame.groupby("primary_leak_reason", dropna=False)
        .agg(
            row_count=("symbol", "count"),
            avg_missed_return=("missed_return", "mean"),
            avg_capture_rate=("capture_rate", "mean"),
            avg_position=("avg_total_position_pct", "mean"),
            avg_max_position=("max_total_position_pct_realized", "mean"),
        )
        .reset_index()
        .sort_values(["row_count", "avg_missed_return"], ascending=[False, False])
    )
    return "\n".join(
        (
            f"| {row['primary_leak_reason']} | {int(row['row_count'])} | "
            f"{_fmt_pct(row['avg_missed_return'])} | {_fmt_pct(row['avg_capture_rate'])} | "
            f"{_fmt_pct(row['avg_position'])} | {_fmt_pct(row['avg_max_position'])} |"
        )
        for _, row in grouped.iterrows()
    )


def _leakage_secondary_table(attribution_frame: pd.DataFrame) -> str:
    if attribution_frame.empty or "volume_price_secondary_reason" not in attribution_frame.columns:
        return "| n/a | 0 | n/a | n/a | n/a | n/a |"
    volume_price = attribution_frame[
        attribution_frame["primary_leak_reason"] == "volume_price_distribution_or_weak_follow"
    ].copy()
    if volume_price.empty:
        return "| n/a | 0 | n/a | n/a | n/a | n/a |"
    grouped = (
        volume_price.groupby("volume_price_secondary_reason", dropna=False)
        .agg(
            row_count=("symbol", "count"),
            avg_missed_return=("missed_return", "mean"),
            avg_capture_rate=("capture_rate", "mean"),
            avg_target_add=("risk_on_target_add_count", "mean"),
            avg_position=("avg_total_position_pct", "mean"),
        )
        .reset_index()
        .sort_values(["row_count", "avg_missed_return"], ascending=[False, False])
    )
    return "\n".join(
        (
            f"| {row['volume_price_secondary_reason']} | {int(row['row_count'])} | "
            f"{_fmt_pct(row['avg_missed_return'])} | {_fmt_pct(row['avg_capture_rate'])} | "
            f"{float(row['avg_target_add']):.2f} | {_fmt_pct(row['avg_position'])} |"
        )
        for _, row in grouped.iterrows()
    )


def _leakage_beta_hold_stall_table(attribution_frame: pd.DataFrame) -> str:
    if attribution_frame.empty or "volume_price_secondary_reason" not in attribution_frame.columns:
        return "| n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a |"
    data = attribution_frame[attribution_frame["volume_price_secondary_reason"] == "stall_and_price_up_volume_down"].copy()
    if data.empty:
        return "| n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a |"
    beta_hold_share = pd.to_numeric(data.get("beta_hold_share", 0.0), errors="coerce").fillna(0.0)
    data["beta_hold_bucket"] = pd.Series("no_or_low_beta_hold", index=data.index)
    data.loc[beta_hold_share >= 0.20, "beta_hold_bucket"] = "beta_hold_active"
    grouped = (
        data.groupby("beta_hold_bucket", dropna=False)
        .agg(
            row_count=("symbol", "count"),
            avg_missed_return=("missed_return", "mean"),
            avg_capture_rate=("capture_rate", "mean"),
            avg_beta_hold_share=("beta_hold_share", "mean"),
            avg_full_position_share=("full_position_share", "mean"),
            avg_position=("avg_total_position_pct", "mean"),
            avg_early_exit=("early_exit_count", "mean"),
        )
        .reset_index()
        .sort_values(["row_count", "avg_missed_return"], ascending=[False, False])
    )
    return "\n".join(
        (
            f"| {row['beta_hold_bucket']} | {int(row['row_count'])} | "
            f"{_fmt_pct(row['avg_missed_return'])} | {_fmt_pct(row['avg_capture_rate'])} | "
            f"{_fmt_pct(row['avg_beta_hold_share'])} | {_fmt_pct(row['avg_full_position_share'])} | "
            f"{_fmt_pct(row['avg_position'])} | {float(row['avg_early_exit']):.2f} |"
        )
        for _, row in grouped.iterrows()
    )


def _leakage_top_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "| n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |"
    rows: list[str] = []
    for _, row in frame.iterrows():
        rows.append(
            f"| {row['window_id']} | {row['symbol']} | {row['name']} | "
            f"{_fmt_pct(row['benchmark_return'])} | {_fmt_pct(row['total_return'])} | {_fmt_pct(row['capture_rate'])} | "
            f"{_fmt_pct(row['risk_on_share'])} | {int(row['buy3_count'])}/{int(row['breakout_confirmed_count'])} | "
            f"{int(row['confirmed_flow_count'])} | {int(row['risk_on_target_add_count'])} | {_fmt_pct(row['force_suppression_share'])} | "
            f"{int(row['sell_signal_count'])}/{int(row['stop_signal_count'])} | "
            f"{_fmt_pct(row['avg_total_position_pct'])}/{_fmt_pct(row['max_total_position_pct_realized'])} | "
            f"{row['primary_leak_reason']} | {row['volume_price_secondary_reason']} |"
        )
    return "\n".join(rows)


def _frame_mean(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def _summary_row(row: pd.Series) -> str:
    return (
        f"| {row.get('portfolio_weighting', 'equal')} | Top {int(row['top_n'])} | {int(row['window_count'])} | "
        f"{float(row['final_equity']):,.2f} | {float(row['profit']):,.2f} | "
        f"{_fmt_pct(row['walkforward_total_return'])} | {_fmt_pct(row['walkforward_benchmark_return'])} | "
        f"{_fmt_pct(row.get('walkforward_risk_matched_benchmark_return', 0.0))} | "
        f"{_fmt_pct(row['walkforward_excess_return'])} | {_fmt_pct(row.get('walkforward_risk_matched_excess_return', 0.0))} | "
        f"{_fmt_pct(row['window_win_rate'])} | "
        f"{_fmt_pct(row['worst_window_max_drawdown'])} |"
    )


def _window_row(row: pd.Series) -> str:
    return (
        f"| {row['window_id']} | {row['train_start']}..{row['train_end']} | "
        f"{row['valid_start']}..{row['valid_end']} | `{row['rule_id']}` | "
        f"{_fmt_pct(row['valid_total_return'])} | {_fmt_pct(row['valid_benchmark_return'])} | "
        f"{_fmt_pct(row.get('valid_risk_matched_benchmark_return', 0.0))} | "
        f"{_fmt_pct(row['valid_excess_return'])} | {_fmt_pct(row.get('valid_risk_matched_excess_return', 0.0))} | "
        f"{_fmt_pct(row['valid_max_drawdown'])} | "
        f"{_fmt_pct(row['valid_positive_rate'])} |"
    )


def _rule_row(row: pd.Series) -> str:
    return (
        f"| {row['window_id']} | `{row['rule_id']}` | {int(row['candidate_count'])} | "
        f"{_fmt_pct(row['train_avg_total_return'])} | {_fmt_pct(row['train_avg_benchmark_return'])} | "
        f"{float(row['train_avg_upside_capture']):.2f} | {_fmt_pct(row.get('train_avg_position_pct', 0.0))} | "
        f"{_fmt_pct(row['train_avg_capture_shortfall'])} | {_fmt_pct(row['train_avg_max_drawdown'])} | "
        f"{float(row['train_avg_stop_per_trade']):.2f} | {float(row.get('train_avg_early_exit_per_trade', 0.0)):.2f} |"
    )


def _candidate_row(row: pd.Series) -> str:
    return (
        f"| {int(row['rank'])} | `{row['symbol']}` | {row['name']} | {_fmt_pct(row['total_return'])} | "
        f"{_fmt_pct(row['benchmark_return'])} | {float(row['upside_capture']):.2f} | "
        f"{_fmt_pct(row['max_drawdown'])} | {float(row['signal_density']):.2f} | "
        f"{float(row['target_add_density']):.2f} | {_fmt_pct(row['offensive_share'])} | "
        f"{float(row['stop_per_trade']):.2f} | {float(row['strong_beta_score']):.3f} | "
        f"{float(row['main_uptrend_score']):.3f} | {float(row['screen_score']):.3f} |"
    )


def _fmt_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
