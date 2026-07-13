#!/usr/bin/env python3
"""Run batch backtests for the dividend watchlist."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta
from multiprocessing import get_context
from pathlib import Path
import subprocess
import sys
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import (  # noqa: E402
    AkshareADataProvider,
    BaoStockADataProvider,
    EastMoneyDirectProvider,
    TushareADataProvider,
    YFinanceADataProvider,
)
from market_regime_alpha.dividend_t.backtest import (  # noqa: E402
    DEFAULT_SIGNAL_CACHE_DIR,
    DEFAULT_SIGNAL_HISTORY_BARS,
    DividendTBacktestConfig,
    load_5min_bars_path,
    run_cosco_dividend_t_backtest,
)
from market_regime_alpha.dividend_t.cosco_profile import profile_for_watchlist_item  # noqa: E402
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine  # noqa: E402
from market_regime_alpha.dividend_t.macd import BarInterval, MACDConfig  # noqa: E402
from market_regime_alpha.dividend_t.fundamentals import build_fundamental_resolver  # noqa: E402
from market_regime_alpha.dividend_t.market_environment import (  # noqa: E402
    MarketEnvironmentFilter,
    build_market_environment_filter,
)
from market_regime_alpha.dividend_t.storage import load_watchlist  # noqa: E402
from market_regime_alpha.dividend_t.macd_experiments import (  # noqa: E402
    MACD_PROFILE_NAMES,
    build_experiment_identity,
    macd_policy_config_for_profile,
)
from market_regime_alpha.dividend_t.strategy_modes import STRATEGY_MODES, apply_strategy_mode  # noqa: E402


DEFAULT_REPORT = PROJECT_ROOT / "reports" / "backtests" / "dividend_watchlist_backtest.md"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min"


@dataclass(frozen=True)
class BatchRow:
    symbol: str
    name: str
    industry: str
    status: str
    rows: int = 0
    start: str = "-"
    end: str = "-"
    total_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    max_drawdown: float | None = None
    trade_count: int = 0
    completed_trades: int = 0
    win_rate: float | None = None
    gate_count: int = 0
    strong_trend_gate_count: int = 0
    buy_signal_count: int = 0
    breakout_signal_count: int = 0
    breakout_watch_count: int = 0
    sell_signal_count: int = 0
    buyback_trade_count: int = 0
    market_caution_gate_count: int = 0
    stop_signal_count: int = 0
    defensive_mode_count: int = 0
    balanced_mode_count: int = 0
    offensive_mode_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    data_source: str = "-"
    message: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dividend watchlist batch backtests.")
    parser.add_argument("--watchlist", type=Path, help="Watchlist CSV path. Defaults to dividend_t_watchlist.csv.")
    parser.add_argument("--data-dir", type=Path, help="Directory containing per-symbol 5-minute CSV files.")
    parser.add_argument("--provider", choices=["none", "qmt", "eastmoney", "akshare", "baostock", "yfinance", "tushare"], default="none")
    parser.add_argument("--days", type=int, default=45, help="Lookback calendar days for provider fetch.")
    parser.add_argument("--limit", type=int, default=0, help="Limit the number of watchlist symbols. 0 means all.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Optional symbol filter, for example 601919.SH 600900.SH.")
    parser.add_argument("--timeout-seconds", type=float, default=35.0, help="Per-symbol provider timeout.")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent symbols.")
    parser.add_argument("--worker-mode", choices=["auto", "process", "thread"], default="auto", help="Use process workers when available for CPU-bound backtests; auto falls back to threads in restricted environments.")
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--base-pct", type=float, default=0.10, help="Initial base position ratio, constrained to 0.05-0.10.")
    parser.add_argument("--t-pct", type=float, default=1.00, help="Legacy alias for the default total position cap after a BUY signal, constrained to <=1.00.")
    parser.add_argument("--min-t-pct", type=float, default=0.03, help="Minimum active-position probe increment above the base position.")
    parser.add_argument("--enable-t-sell", action="store_true", help="Opt in to ordinary T_SELL and reverse-T sell execution. Disabled by default.")
    parser.add_argument("--max-signal-position-pct", type=float, default=1.00)
    parser.add_argument("--strategy-mode", choices=STRATEGY_MODES, default="balanced", help="Named position profile: balanced, defensive, or offensive.")
    parser.add_argument("--market-filter", choices=["none", "equal-weight"], default="none", help="Market environment filter built from the local watchlist equal-weight proxy.")
    parser.add_argument("--strong-confirm-signals", type=int, default=3)
    parser.add_argument("--trend-exit-confirm-signals", type=int, default=4)
    parser.add_argument("--defensive-confirm-signals", type=int, default=2)
    parser.add_argument("--kelly-scale", type=float, default=0.65)
    parser.add_argument("--min-buy-strength", type=float, default=66.0)
    parser.add_argument("--min-lookback-bars", type=int, default=48)
    parser.add_argument("--max-history-bars", type=int, default=DEFAULT_SIGNAL_HISTORY_BARS)
    parser.add_argument("--signal-step-bars", type=int, default=6, help="Evaluate one signal every N bars. 6 means about 30 minutes.")
    parser.add_argument("--base-rebalance-cooldown-bars", type=int, default=48, help="Cooldown before another base rebalance. 48 means about one trading day.")
    parser.add_argument("--no-reverse-t", action="store_true", help="Disable reverse-T sell and buyback loop.")
    parser.add_argument("--disable-profit-protection", action="store_true", help="Disable breakout profit protection.")
    parser.add_argument("--profit-protect-trigger-pct", type=float, default=0.012)
    parser.add_argument("--profit-protect-sell-fraction", type=float, default=0.50)
    parser.add_argument("--disable-attack-state-machine", action="store_true", help="Disable breakout attack state machine.")
    parser.add_argument("--attack-watch-position-pct", type=float, default=0.25)
    parser.add_argument("--attack-confirm-position-pct", type=float, default=0.70)
    parser.add_argument("--attack-full-position-pct", type=float, default=1.00)
    parser.add_argument("--attack-confirm-min-breakout-score", type=float, default=92.0)
    parser.add_argument("--attack-confirm-min-buy-strength", type=float, default=70.0)
    parser.add_argument("--attack-full-confirm-signals", type=int, default=1)
    parser.add_argument("--disable-buy-volume-price-window-filter", action="store_true")
    parser.add_argument("--buy-volume-price-short-lookback-bars", type=int, default=12)
    parser.add_argument("--buy-volume-price-mid-lookback-bars", type=int, default=24)
    parser.add_argument("--buy-volume-price-filter-min-return-pct", type=float, default=0.004)
    parser.add_argument("--buy-volume-price-filter-max-contract-ratio", type=float, default=0.82)
    parser.add_argument("--buy-volume-price-filter-min-quality-score", type=float, default=0.34)
    parser.add_argument("--disable-portfolio-main-rise-position-target", action="store_true")
    parser.add_argument("--portfolio-main-rise-position-target-pct", type=float, default=0.95)
    parser.add_argument("--portfolio-main-rise-min-model-state-score", type=float, default=62.0)
    parser.add_argument("--portfolio-main-rise-min-holding-win-rate", type=float, default=0.56)
    parser.add_argument("--portfolio-main-rise-min-profit-spread", type=float, default=0.62)
    parser.add_argument("--portfolio-main-rise-min-new-buy-success-rate", type=float, default=0.45)
    parser.add_argument("--signal-cache-dir", type=Path, default=DEFAULT_SIGNAL_CACHE_DIR, help="Directory for reusable timing signal cache.")
    parser.add_argument("--signal-cache-save-every", type=int, default=200, help="Persist signal cache after this many new signals.")
    parser.add_argument("--no-signal-cache", action="store_true", help="Disable reusable timing signal cache.")
    parser.add_argument(
        "--macd-profile",
        choices=MACD_PROFILE_NAMES,
        default="baseline",
        help="MACD research profile; production default remains baseline.",
    )
    parser.add_argument(
        "--dataset-version",
        help="Required content/version identity for non-baseline MACD experiments.",
    )
    parser.add_argument("--no-industry-params", action="store_true", help="Disable industry-specific profile and position parameters.")
    parser.add_argument("--fundamental-source", choices=["auto", "tushare", "profile"], default="auto", help="Fundamental F source for industry profiles.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.macd_profile != "baseline" and not args.dataset_version:
        parser.error("non-baseline --macd-profile requires --dataset-version")

    items = load_watchlist(args.watchlist) if args.watchlist else load_watchlist()
    if args.symbols:
        symbols = {symbol.upper() for symbol in args.symbols}
        items = [item for item in items if item.symbol.upper() in symbols]
    if args.limit > 0:
        items = items[: args.limit]

    config = DividendTBacktestConfig(
        initial_cash=args.initial_cash,
        initial_base_position_pct=args.base_pct,
        t_trade_pct=args.t_pct,
        min_t_trade_pct=args.min_t_pct,
        enable_t_sell=args.enable_t_sell,
        max_signal_position_pct=args.max_signal_position_pct,
        strong_trend_confirm_signals=args.strong_confirm_signals,
        trend_exit_confirm_signals=args.trend_exit_confirm_signals,
        defensive_confirm_signals=args.defensive_confirm_signals,
        kelly_fraction_scale=args.kelly_scale,
        min_buy_signal_strength=args.min_buy_strength,
        min_lookback_bars=args.min_lookback_bars,
        max_history_bars=args.max_history_bars,
        signal_step_bars=args.signal_step_bars,
        base_rebalance_cooldown_bars=args.base_rebalance_cooldown_bars,
        allow_reverse_t=not args.no_reverse_t,
        enable_profit_protection=not args.disable_profit_protection,
        profit_protect_trigger_pct=args.profit_protect_trigger_pct,
        profit_protect_sell_fraction=args.profit_protect_sell_fraction,
        enable_attack_state_machine=not args.disable_attack_state_machine,
        attack_watch_position_pct=args.attack_watch_position_pct,
        attack_confirm_position_pct=args.attack_confirm_position_pct,
        attack_full_position_pct=args.attack_full_position_pct,
        attack_confirm_min_breakout_score=args.attack_confirm_min_breakout_score,
        attack_confirm_min_buy_strength=args.attack_confirm_min_buy_strength,
        attack_full_confirm_signals=args.attack_full_confirm_signals,
        enable_buy_volume_price_window_filter=not args.disable_buy_volume_price_window_filter,
        buy_volume_price_short_lookback_bars=args.buy_volume_price_short_lookback_bars,
        buy_volume_price_mid_lookback_bars=args.buy_volume_price_mid_lookback_bars,
        buy_volume_price_filter_min_return_pct=args.buy_volume_price_filter_min_return_pct,
        buy_volume_price_filter_max_contract_ratio=args.buy_volume_price_filter_max_contract_ratio,
        buy_volume_price_filter_min_quality_score=args.buy_volume_price_filter_min_quality_score,
        enable_portfolio_main_rise_position_target=not args.disable_portfolio_main_rise_position_target,
        portfolio_main_rise_position_target_pct=args.portfolio_main_rise_position_target_pct,
        portfolio_main_rise_min_model_state_score=args.portfolio_main_rise_min_model_state_score,
        portfolio_main_rise_min_holding_win_rate=args.portfolio_main_rise_min_holding_win_rate,
        portfolio_main_rise_min_profit_spread=args.portfolio_main_rise_min_profit_spread,
        portfolio_main_rise_min_new_buy_success_rate=args.portfolio_main_rise_min_new_buy_success_rate,
        signal_cache_dir=None if args.no_signal_cache else args.signal_cache_dir,
        signal_cache_save_every=args.signal_cache_save_every,
    )
    config = apply_strategy_mode(config, args.strategy_mode)
    market_filter = _build_market_filter(args.market_filter, items=items, data_dir=args.data_dir)
    if market_filter is not None:
        config = replace(config, enable_market_filter=True, market_filter_name=market_filter.name)
    rows = _run_batch(
        items,
        config=config,
        market_filter=market_filter,
        data_dir=args.data_dir,
        provider=args.provider,
        days=args.days,
        timeout_seconds=args.timeout_seconds,
        workers=args.workers,
        worker_mode=args.worker_mode,
        use_industry_params=not args.no_industry_params,
        fundamental_source=args.fundamental_source,
        macd_profile=args.macd_profile,
        dataset_version=args.dataset_version,
        git_commit=_git_commit(),
    )
    report = _format_batch_report(
        rows,
        provider=args.provider,
        data_dir=args.data_dir,
        config=config,
        fundamental_source=args.fundamental_source,
        workers=args.workers,
        worker_mode=args.worker_mode,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    _write_csv(rows, args.report.with_suffix(".csv"))

    ok_rows = [row for row in rows if row.status == "ok"]
    print("Dividend Watchlist Backtest")
    print("=" * 36)
    print(f"Symbols: {len(rows)}, ok: {len(ok_rows)}, failed: {len(rows) - len(ok_rows)}")
    if ok_rows:
        avg_total = sum(row.total_return or 0 for row in ok_rows) / len(ok_rows)
        avg_excess = sum(row.excess_return or 0 for row in ok_rows) / len(ok_rows)
        print(f"Average total return: {avg_total:.2%}")
        print(f"Average excess return: {avg_excess:.2%}")
    print(f"Report: {args.report}")
    print(f"CSV: {args.report.with_suffix('.csv')}")
    return 0


def _run_batch(
    items: list[Any],
    *,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
    data_dir: Path | None,
    provider: str,
    days: int,
    timeout_seconds: float,
    workers: int,
    worker_mode: str,
    use_industry_params: bool,
    fundamental_source: str,
    macd_profile: str,
    dataset_version: str | None,
    git_commit: str,
) -> list[BatchRow]:
    if workers <= 1:
        return [
            _run_one(
                item,
                config=config,
                market_filter=market_filter,
                data_dir=data_dir,
                provider=provider,
                days=days,
                timeout_seconds=timeout_seconds,
                use_industry_params=use_industry_params,
                fundamental_source=fundamental_source,
                macd_profile=macd_profile,
                dataset_version=dataset_version,
                git_commit=git_commit,
            )
            for item in items
        ]
    rows_by_symbol: dict[str, BatchRow] = {}
    executor, actual_worker_mode = _create_batch_executor(workers=workers, worker_mode=worker_mode)
    futures = {
        executor.submit(
            _run_one,
            item,
            config=config,
            market_filter=market_filter,
            data_dir=data_dir,
            provider=provider,
            days=days,
            timeout_seconds=timeout_seconds,
            use_industry_params=use_industry_params,
            fundamental_source=fundamental_source,
            macd_profile=macd_profile,
            dataset_version=dataset_version,
            git_commit=git_commit,
        ): item
        for item in items
    }
    try:
        for future in as_completed(futures):
            item = futures[future]
            try:
                rows_by_symbol[item.symbol] = future.result()
            except Exception as exc:  # noqa: BLE001
                rows_by_symbol[item.symbol] = BatchRow(
                    symbol=item.symbol,
                    name=item.name,
                    industry=item.industry,
                    status="failed",
                    data_source=provider,
                    message=f"{type(exc).__name__}: {exc}",
                )
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True, cancel_futures=False)
    if worker_mode != actual_worker_mode:
        print(f"worker-mode fallback: requested={worker_mode}, actual={actual_worker_mode}", file=sys.stderr)
    return [rows_by_symbol[item.symbol] for item in items]


def _create_batch_executor(*, workers: int, worker_mode: str) -> tuple[ProcessPoolExecutor | ThreadPoolExecutor, str]:
    if worker_mode == "thread":
        return ThreadPoolExecutor(max_workers=workers), "thread"
    try:
        return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("fork")), "process"
    except (OSError, PermissionError):
        if worker_mode == "process":
            raise
        return ThreadPoolExecutor(max_workers=workers), "thread"


def _build_market_filter(mode: str, *, items: list[Any], data_dir: Path | None) -> MarketEnvironmentFilter | None:
    if mode == "none":
        return None
    if mode != "equal-weight":
        raise ValueError(f"unsupported market filter: {mode}")
    source_dir = data_dir or DEFAULT_DATA_DIR
    daily_frames: list[pd.DataFrame] = []
    for item in items:
        try:
            bars = load_5min_bars_path(source_dir, symbol=item.symbol)
        except FileNotFoundError:
            continue
        daily = _daily_market_filter_frame(bars, symbol=item.symbol, industry=item.industry)
        if daily.empty or float(daily["close"].iloc[0]) <= 0:
            continue
        daily_frames.append(daily)
    if not daily_frames:
        raise ValueError(f"no local CSV files available to build market filter in {source_dir}")
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


def _run_one(
    item: Any,
    *,
    config: DividendTBacktestConfig,
    market_filter: MarketEnvironmentFilter | None,
    data_dir: Path | None,
    provider: str,
    days: int,
    timeout_seconds: float,
    use_industry_params: bool,
    fundamental_source: str,
    macd_profile: str,
    dataset_version: str | None,
    git_commit: str,
) -> BatchRow:
    try:
        bars, data_source = _load_bars(item.symbol, data_dir=data_dir, provider=provider, days=days, timeout_seconds=timeout_seconds)
        if len(bars) <= config.min_lookback_bars + 1:
            raise ValueError(f"only {len(bars)} bars; need more than {config.min_lookback_bars + 1}")
        profile = profile_for_watchlist_item(item)
        resolver = build_fundamental_resolver(profile, source=fundamental_source) if use_industry_params else None
        effective_config = _config_for_profile(config, profile=profile, fundamental_source=fundamental_source) if use_industry_params else config
        effective_config = replace(
            effective_config,
            signal_cache_tag=f"{effective_config.signal_cache_tag}-{macd_profile}",
        )
        policy_config = macd_policy_config_for_profile(macd_profile)
        engine = CoscoTimingEngine(
            profile=profile if use_industry_params else None,
            fundamental_resolver=resolver,
            macd_policy_config=policy_config,
        )
        experiment_identity = (
            build_experiment_identity(
                git_commit=git_commit,
                dataset_version=dataset_version,
                pipeline_id="dividend-watchlist-5m",
                macd_config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
                policy_config=policy_config,
                execution_config=effective_config,
                sizing_owner="dividend_t_backtest_execution",
            )
            if dataset_version
            else None
        )
        result = run_cosco_dividend_t_backtest(
            bars,
            config=effective_config,
            engine=engine,
            market_filter=market_filter,
            experiment_identity=experiment_identity,
            pipeline_id="dividend-watchlist-5m",
        )
        gate_count = sum(result.gate_counts.values())
        return BatchRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            status="ok",
            rows=result.rows,
            start=result.start,
            end=result.end,
            total_return=result.total_return,
            benchmark_return=result.benchmark_return,
            excess_return=result.excess_return,
            max_drawdown=result.max_drawdown,
            trade_count=result.trade_count,
            completed_trades=result.completed_trades,
            win_rate=result.win_rate,
            gate_count=gate_count,
            strong_trend_gate_count=result.gate_counts.get("WAIT_STRONG_TREND", 0),
            buy_signal_count=result.action_counts.get("BUY_T_TIMING", 0),
            breakout_signal_count=result.action_counts.get("BREAKOUT_BUY_TIMING", 0),
            breakout_watch_count=result.action_counts.get("WATCH_BREAKOUT_NEXT_DAY", 0),
            sell_signal_count=result.action_counts.get("SELL_T_TIMING", 0),
            buyback_trade_count=result.buyback_trade_count,
            market_caution_gate_count=result.gate_counts.get("WAIT_MARKET_CAUTION", 0),
            stop_signal_count=result.action_counts.get("STOP_T_WAIT", 0),
            defensive_mode_count=result.strategy_mode_counts.get("defensive", 0),
            balanced_mode_count=result.strategy_mode_counts.get("balanced", 0),
            offensive_mode_count=result.strategy_mode_counts.get("offensive", 0),
            cache_hits=result.cache_hits,
            cache_misses=result.cache_misses,
            data_source=data_source,
        )
    except Exception as exc:  # noqa: BLE001
        return BatchRow(
            symbol=item.symbol,
            name=item.name,
            industry=item.industry,
            status="failed",
            data_source=provider,
            message=f"{type(exc).__name__}: {exc}",
        )


def _config_for_profile(config: DividendTBacktestConfig, *, profile: Any, fundamental_source: str) -> DividendTBacktestConfig:
    return replace(
        config,
        initial_base_position_pct=min(config.initial_base_position_pct, profile.default_base_position_pct),
        signal_cache_tag=f"industry_{fundamental_source}",
    )


def _load_bars(item_symbol: str, *, data_dir: Path | None, provider: str, days: int, timeout_seconds: float) -> tuple[Any, str]:
    if data_dir is not None:
        return load_5min_bars_path(data_dir, symbol=item_symbol), str(data_dir)
    if provider == "none":
        return load_5min_bars_path(DEFAULT_DATA_DIR, symbol=item_symbol), str(DEFAULT_DATA_DIR)
    if provider == "yfinance":
        output = _fetch_yfinance_to_csv(item_symbol, timeout_seconds=timeout_seconds)
        return load_5min_bars_path(output, symbol=item_symbol), str(output)
    return _fetch_with_timeout(item_symbol, provider=provider, days=days, timeout_seconds=timeout_seconds), provider


def _fetch_yfinance_to_csv(symbol: str, *, timeout_seconds: float) -> Path:
    output = DEFAULT_DATA_DIR / f"{symbol}_5min.csv"
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "fetch_yfinance_5min.py"),
        symbol,
        "--output",
        str(output),
        "--timeout-seconds",
        str(max(5.0, timeout_seconds * 0.75)),
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(detail)
    return output


def _fetch_with_timeout(symbol: str, *, provider: str, days: int, timeout_seconds: float) -> Any:
    ctx = get_context("fork")
    queue = ctx.Queue()
    process = ctx.Process(target=_fetch_worker, args=(queue, symbol, provider, days))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError(f"{provider} fetch timed out after {timeout_seconds:.1f}s")
    if queue.empty():
        raise RuntimeError(f"{provider} fetch returned no result")
    status, payload = queue.get()
    if status == "ok":
        return payload
    raise RuntimeError(payload)


def _fetch_worker(queue: Any, symbol: str, provider: str, days: int) -> None:
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        if provider == "qmt":
            from market_regime_alpha.data_sources.a_share_bars import QmtL1Provider

            client = QmtL1Provider()
        elif provider == "eastmoney":
            client = EastMoneyDirectProvider(timeout_seconds=10.0)
        elif provider == "akshare":
            client = AkshareADataProvider()
        elif provider == "baostock":
            client = BaoStockADataProvider()
        elif provider == "yfinance":
            client = YFinanceADataProvider()
        elif provider == "tushare":
            client = TushareADataProvider()
        else:
            raise ValueError(f"unsupported provider: {provider}")
        bars = client.minute_bars(
            symbol,
            start_date=start.strftime("%Y-%m-%d 09:00:00"),
            end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        queue.put(("ok", bars))
    except Exception as exc:  # noqa: BLE001
        queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _format_batch_report(
    rows: list[BatchRow],
    *,
    provider: str,
    data_dir: Path | None,
    config: DividendTBacktestConfig,
    fundamental_source: str,
    workers: int,
    worker_mode: str,
) -> str:
    ok_rows = [row for row in rows if row.status == "ok"]
    failed_rows = [row for row in rows if row.status != "ok"]
    avg_total = _average(row.total_return for row in ok_rows)
    avg_excess = _average(row.excess_return for row in ok_rows)
    positive_excess = sum(1 for row in ok_rows if (row.excess_return or 0) > 0)
    table = "\n".join(_table_row(row) for row in ok_rows)
    if not table:
        table = "| - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |\n"
    failures = "\n".join(f"- `{row.symbol}` {row.name}：{row.message}" for row in failed_rows) or "- 无"
    data_source = f"CSV目录 `{data_dir}`" if data_dir else f"provider `{provider}`"
    return (
        "# 红利观察池做 T 模型批量回测\n\n"
        "## 数据与参数\n\n"
        f"- 数据来源：{data_source}\n"
        f"- 成功标的：{len(ok_rows)} / {len(rows)}\n"
        f"- 初始资金：{config.initial_cash:,.2f}\n"
        f"- 策略模式：{config.strategy_mode}\n"
        f"- 市场环境过滤：{'开启' if config.enable_market_filter else '关闭'}（{config.market_filter_name}）\n"
        f"- RISK_ON 盈利扩散穿透：开启；持仓胜率/浮盈扩散/新买点成功率会参与复合 RISK_ON 升降级\n"
        f"- T_SELL 执行：{'开启' if config.enable_t_sell else '关闭'}；关闭时普通 T 卖和倒 T 卖只计信号、不执行\n"
        f"- 防守/震荡初始底仓比例：{config.initial_base_position_pct:.0%}\n"
        f"- 底仓目标上限：{config.strong_trend_base_position_pct:.0%}\n"
        f"- 全局最大总仓位硬上限：{config.max_signal_position_pct:.0%}\n"
        f"- 强趋势/趋势观察/震荡目标上限：{config.strong_trend_signal_position_pct:.0%} / "
        f"{config.trend_watch_signal_position_pct:.0%} / {config.range_signal_position_pct:.0%}\n"
        f"- 进攻状态机：{'开启' if config.enable_attack_state_machine else '关闭'}；"
        f"预警 {config.attack_watch_position_pct:.0%} / 确认 {config.attack_confirm_position_pct:.0%} / 满攻 {config.attack_full_position_pct:.0%}\n"
        f"- 满攻触发：突破分 ≥ {config.attack_confirm_min_breakout_score:.1f}，买入强度 ≥ {config.attack_confirm_min_buy_strength:.1f}，确认 {config.attack_full_confirm_signals} 次\n"
        f"- 组合层主升目标：{'开启' if config.enable_portfolio_main_rise_position_target else '关闭'}；"
        f"目标 {config.portfolio_main_rise_position_target_pct:.0%}，模型状态 ≥ {config.portfolio_main_rise_min_model_state_score:.1f}，"
        f"持仓胜率/浮盈扩散/新买点成功率 ≥ {config.portfolio_main_rise_min_holding_win_rate:.0%}/"
        f"{config.portfolio_main_rise_min_profit_spread:.0%}/{config.portfolio_main_rise_min_new_buy_success_rate:.0%}\n"
        f"- 12/24bar 买点量价过滤：{'开启' if config.enable_buy_volume_price_window_filter else '关闭'}；"
        f"窗口 {config.buy_volume_price_short_lookback_bars}/{config.buy_volume_price_mid_lookback_bars} 根，"
        f"最小涨幅 {config.buy_volume_price_filter_min_return_pct:.1%}，缩量阈值 {config.buy_volume_price_filter_max_contract_ratio:.0%}，"
        f"质量底线 {config.buy_volume_price_filter_min_quality_score:.2f}\n"
        f"- 单次底仓再平衡步长：{config.base_rebalance_step_pct:.0%}\n"
        f"- 底仓再平衡冷却：{config.base_rebalance_cooldown_bars} 根 5 分钟 K 线\n"
        f"- 强趋势确认次数：{config.strong_trend_confirm_signals}\n"
        f"- 趋势退出确认次数：{config.trend_exit_confirm_signals}\n"
        f"- 防守确认次数：{config.defensive_confirm_signals}\n"
        f"- 默认买入后总仓位上限：{config.default_buy_total_cap_pct:.0%}（legacy `t_trade_pct`）\n"
        f"- 默认主动增量上限：{config.default_active_position_cap_pct:.0%}（总仓位上限 - 初始底仓）\n"
        f"- 最小主动试探增量：{config.min_t_trade_pct:.0%}\n"
        f"- Kelly 折扣：{config.kelly_fraction_scale:.0%}\n"
        f"- 最低买入强度：{config.min_buy_signal_strength:.1f}\n"
        f"- 倒 T 闭环：{'开启' if config.allow_reverse_t else '关闭'}\n"
        f"- 突破仓利润保护：{'开启' if config.enable_profit_protection else '关闭'}，触发浮盈 {config.profit_protect_trigger_pct:.1%}，卖出比例 {config.profit_protect_sell_fraction:.0%}\n"
        f"- 最小回看：{config.min_lookback_bars} 根 5 分钟 K 线\n"
        f"- 单次信号最大历史窗口：{config.max_history_bars} 根 5 分钟 K 线\n\n"
        f"- 基本面 F 来源：{fundamental_source}；Tushare 不可用时按单标的回退行业默认 F 并继续回测\n\n"
        f"- 信号评估步长：每 {config.signal_step_bars} 根 5 分钟 K 线评估一次\n\n"
        f"- 执行并行：{worker_mode} workers={workers}\n\n"
        f"- 信号缓存：{config.signal_cache_dir or '关闭'}\n\n"
        "## 总结\n\n"
        f"- 平均总收益：{_fmt_pct(avg_total)}\n"
        f"- 平均超额收益：{_fmt_pct(avg_excess)}\n"
        f"- 跑赢买入持有数量：{positive_excess} / {len(ok_rows)}\n"
        f"- 动态/静态模式触发 防守/平衡/进攻："
        f"{sum(row.defensive_mode_count for row in ok_rows)} / "
        f"{sum(row.balanced_mode_count for row in ok_rows)} / "
        f"{sum(row.offensive_mode_count for row in ok_rows)}\n"
        f"- 缓存命中/未命中：{sum(row.cache_hits for row in ok_rows)} / {sum(row.cache_misses for row in ok_rows)}\n"
        f"- 失败数量：{len(failed_rows)}\n\n"
        "## 明细\n\n"
        "| 代码 | 名称 | 行业 | 行数 | 区间 | 总收益 | 基准 | 超额 | 最大回撤 | 交易/门控 | 买回次数 | 强趋势保护 | 市场谨慎/STOP | 模式防/平/攻 | 低吸买/突破买/预警/卖 | 缓存命中/未命中 |\n"
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        f"{table}\n\n"
        "## 数据失败\n\n"
        f"{failures}\n\n"
        "## 初步解释\n\n"
        "- 强趋势模式允许用主动仓位跟随，突破模块用于捕获放量突破；`WATCH_BREAKOUT_NEXT_DAY` 只预警，不买入。\n"
        "- `--strategy-mode defensive` 会收窄主动仓和关闭进攻状态机；`--strategy-mode offensive` 会放宽强信号仓位并保留进攻状态机。\n"
        "- `--strategy-mode dynamic` 默认使用防守画像；只有 `RISK_ON` 且个股强趋势、三买或资金确认时才切进攻。\n"
        "- `--market-filter equal-weight` 用观察池等权代理判断市场环境：偏弱时停止新买入，谨慎时只放行高质量买点。\n"
        "- 如果时间尺度门控次数高，说明日线/分时门控正在阻止盘中误买。\n"
        "- 该批量回测仍是研究工具，不包含真实盘口排队、涨跌停无法成交、分红除权和不同股票基本面 F 的个性化校准。\n"
    )


def _write_csv(rows: list[BatchRow], path: Path) -> None:
    payload = [row.__dict__ for row in rows]
    pd.DataFrame(payload).to_csv(path, index=False)


def _table_row(row: BatchRow) -> str:
    interval = f"{row.start[:10]} -> {row.end[:10]}"
    trade_gate = f"{row.trade_count}/{row.gate_count}"
    return (
        f"| `{row.symbol}` | {row.name} | {row.industry} | {row.rows} | {interval} | "
        f"{_fmt_pct(row.total_return)} | {_fmt_pct(row.benchmark_return)} | {_fmt_pct(row.excess_return)} | "
        f"{_fmt_pct(row.max_drawdown)} | {trade_gate} | {row.buyback_trade_count} | {row.strong_trend_gate_count} | "
        f"{row.market_caution_gate_count}/{row.stop_signal_count} | "
        f"{row.defensive_mode_count}/{row.balanced_mode_count}/{row.offensive_mode_count} | "
        f"{row.buy_signal_count}/{row.breakout_signal_count}/{row.breakout_watch_count}/{row.sell_signal_count} | {row.cache_hits}/{row.cache_misses} |"
    )


def _average(values: Any) -> float | None:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
