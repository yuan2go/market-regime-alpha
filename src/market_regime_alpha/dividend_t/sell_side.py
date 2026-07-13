"""Research-only sell-side action taxonomy.

This module freezes action ownership and intent/enforcement combinations before
any broader production strategy migration.  It has no production profile or
MACD promotion side effect.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import math
from typing import Any

from .backtest import EXECUTION_CONSTRAINT_VERSION, CounterfactualExecutionContext, DividendTBacktestConfig, resolve_execution_request
from .macd_experiments import ExecutionResolution
from .models import Signal
from .signal_intent import PrimarySetupCode, RiskEnforcement, SignalIntent


SELL_SIDE_CONTRACT_VERSION = "sell-side-actions-v1"


class SellAction(StrEnum):
    TAKE_PROFIT_T = "TAKE_PROFIT_T"
    TAKE_PROFIT_REDUCE_T = "TAKE_PROFIT_REDUCE_T"
    RISK_REDUCE_T = "RISK_REDUCE_T"
    EXIT_T_SOFT = "EXIT_T_SOFT"
    EXIT_T_HARD = "EXIT_T_HARD"
    STOP_T = "STOP_T"
    REVERSE_T_SELL = "REVERSE_T_SELL"
    CLEAR_BASE = "CLEAR_BASE"


@dataclass(frozen=True)
class SellActionSpec:
    action: SellAction
    signal: Signal
    primary_setup_code: PrimarySetupCode
    signal_intent: SignalIntent
    risk_enforcement: RiskEnforcement
    position_scope: str
    default_trade_pct: float
    waiting_allowed: bool
    macd_policy_allowed: bool
    creates_buyback_obligation: bool
    success_label: str
    invalidation_condition: str


@dataclass(frozen=True)
class PositionLifecycleContext:
    """Current-bar position context required by research sell selection."""

    entry_price: float
    entry_time: str
    holding_bars: int
    unrealized_return: float
    max_unrealized_return: float
    drawdown_from_peak: float
    t_position_pct: float
    base_position_pct: float
    same_day_bought_qty: int
    sellable_qty: int
    pending_buyback: bool
    setup_invalidation_level: str
    atr_trailing_level: float | None
    current_price: float


@dataclass(frozen=True)
class SellLifecyclePolicy:
    atr_multiple: float = 2.0
    mfe_drawdown_trigger: float = 0.03
    time_stop_bars: int = 24
    minimum_profit_for_take_profit: float = 0.02


@dataclass(frozen=True)
class ResearchSellDecision:
    action: SellAction | None
    reason: str


@dataclass(frozen=True)
class PendingBuyback:
    remaining_shares: int
    allocated_proceeds: float
    target_price: float
    created_bar_index: int
    created_trade_date: str
    expiry_bars: int
    expiry_trade_days: int | None


@dataclass(frozen=True)
class ResearchExecutionState:
    """Research-only state transition input shared by labels and rehearsal."""

    cash: float
    base_shares: int
    t_shares: int
    base_locked_shares: int = 0
    t_locked_shares: int = 0
    trade_date: str | None = None
    pending_buyback: PendingBuyback | None = None


@dataclass(frozen=True)
class ResearchExecutionTransition:
    state: ResearchExecutionState
    resolution: ExecutionResolution
    pending_buyback_event: str | None = None


SELL_ACTION_SPECS: dict[SellAction, SellActionSpec] = {
    SellAction.TAKE_PROFIT_T: SellActionSpec(
        SellAction.TAKE_PROFIT_T,
        Signal.SELL_T,
        PrimarySetupCode.TAKE_PROFIT_T,
        SignalIntent.MEAN_REVERSION_T,
        RiskEnforcement.NONE,
        "T_POSITION",
        1.0,
        True,
        True,
        False,
        "directional_decline_and_completed_t_cycle",
        "exit_confirmation_lost",
    ),
    SellAction.TAKE_PROFIT_REDUCE_T: SellActionSpec(
        SellAction.TAKE_PROFIT_REDUCE_T,
        Signal.REDUCE,
        PrimarySetupCode.TAKE_PROFIT_REDUCE_T,
        SignalIntent.MEAN_REVERSION_T,
        RiskEnforcement.NONE,
        "T_POSITION",
        0.5,
        True,
        True,
        False,
        "directional_decline",
        "profit_drawdown_recovers",
    ),
    SellAction.RISK_REDUCE_T: SellActionSpec(
        SellAction.RISK_REDUCE_T,
        Signal.REDUCE,
        PrimarySetupCode.RISK_REDUCE_T,
        SignalIntent.RISK_REDUCTION,
        RiskEnforcement.SOFT,
        "T_POSITION",
        0.5,
        True,
        False,
        False,
        "risk_reduction_tail_metrics",
        "soft_risk_recovered",
    ),
    SellAction.EXIT_T_SOFT: SellActionSpec(
        SellAction.EXIT_T_SOFT,
        Signal.STOP_T,
        PrimarySetupCode.EXIT_T_SOFT,
        SignalIntent.RISK_REDUCTION,
        RiskEnforcement.SOFT,
        "T_POSITION",
        1.0,
        True,
        False,
        False,
        "risk_reduction_tail_metrics",
        "soft_exit_recovered",
    ),
    SellAction.EXIT_T_HARD: SellActionSpec(
        SellAction.EXIT_T_HARD,
        Signal.STOP_T,
        PrimarySetupCode.EXIT_T_HARD,
        SignalIntent.RISK_REDUCTION,
        RiskEnforcement.HARD,
        "T_POSITION",
        1.0,
        False,
        False,
        False,
        "risk_reduction_tail_metrics",
        "hard_exit_only",
    ),
    SellAction.STOP_T: SellActionSpec(
        SellAction.STOP_T,
        Signal.STOP_T,
        PrimarySetupCode.STOP_T,
        SignalIntent.RISK_REDUCTION,
        RiskEnforcement.HARD,
        "T_POSITION",
        1.0,
        False,
        False,
        False,
        "risk_reduction_tail_metrics",
        "hard_stop_only",
    ),
    SellAction.REVERSE_T_SELL: SellActionSpec(
        SellAction.REVERSE_T_SELL,
        Signal.SELL_REVERSE_T,
        PrimarySetupCode.REVERSE_T_SELL,
        SignalIntent.MEAN_REVERSION_T,
        RiskEnforcement.NONE,
        "BASE_POSITION",
        0.5,
        True,
        True,
        True,
        "completed_t_cycle",
        "buyback_expired_or_hard_risk",
    ),
    SellAction.CLEAR_BASE: SellActionSpec(
        SellAction.CLEAR_BASE,
        Signal.CLEAR,
        PrimarySetupCode.CLEAR_BASE,
        SignalIntent.RISK_REDUCTION,
        RiskEnforcement.HARD,
        "BASE_AND_T_POSITION",
        1.0,
        False,
        False,
        False,
        "risk_reduction_tail_metrics",
        "hard_exit_only",
    ),
}


def sell_action_spec(action: SellAction | str) -> SellActionSpec:
    """Get the frozen specification for one research sell action."""

    try:
        normalized = SellAction(action)
    except ValueError as exc:
        raise ValueError(f"UNKNOWN_SELL_ACTION: {action}") from exc
    return SELL_ACTION_SPECS[normalized]


def select_research_sell_action(context: PositionLifecycleContext, policy: SellLifecyclePolicy) -> ResearchSellDecision:
    """Choose one research action from lifecycle context, without production routing."""

    invalidation = context.setup_invalidation_level.upper()
    if invalidation == "HARD":
        return ResearchSellDecision(SellAction.EXIT_T_HARD, "SETUP_INVALIDATION_HARD")
    if context.atr_trailing_level is not None and context.current_price <= context.atr_trailing_level:
        return ResearchSellDecision(SellAction.STOP_T, "ATR_TRAILING_STOP")
    if invalidation == "SOFT":
        return ResearchSellDecision(SellAction.EXIT_T_SOFT, "SETUP_INVALIDATION_SOFT")
    if (
        context.max_unrealized_return >= policy.minimum_profit_for_take_profit
        and context.drawdown_from_peak <= -policy.mfe_drawdown_trigger
    ):
        return ResearchSellDecision(SellAction.TAKE_PROFIT_T, "MFE_DRAWDOWN")
    if context.holding_bars >= policy.time_stop_bars:
        return ResearchSellDecision(SellAction.RISK_REDUCE_T, "TIME_STOP")
    return ResearchSellDecision(None, "NO_SELL_ACTION")


def atr_trailing_level(peak_price: float, *, atr: float, policy: SellLifecyclePolicy) -> float:
    """Return the research ATR trailing threshold from a precomputed peak."""

    if not all(math.isfinite(value) for value in (peak_price, atr, policy.atr_multiple)) or peak_price <= 0.0 or atr < 0.0:
        raise ValueError("ATR_TRAILING_INPUT_INVALID")
    return peak_price - atr * policy.atr_multiple


def advance_research_execution_state(
    state: ResearchExecutionState,
    *,
    bar_time: str,
    bar_index: int,
) -> ResearchExecutionState:
    """Unlock T+1 shares on a new trading day and expire pending buybacks."""

    trade_date = _trade_date(bar_time)
    unlocked = state.trade_date is not None and trade_date != state.trade_date
    result = replace(
        state,
        trade_date=trade_date,
        base_locked_shares=0 if unlocked else state.base_locked_shares,
        t_locked_shares=0 if unlocked else state.t_locked_shares,
    )
    pending = result.pending_buyback
    if pending is None:
        return result
    if bar_index - pending.created_bar_index > pending.expiry_bars:
        return replace(result, pending_buyback=None)
    if pending.expiry_trade_days is not None and _trade_day_distance(pending.created_trade_date, trade_date) > pending.expiry_trade_days:
        return replace(result, pending_buyback=None)
    return result


def execute_research_action(
    state: ResearchExecutionState,
    *,
    signal: Signal,
    symbol: str,
    candidate_bar_close_time: str,
    next_bar: Any,
    config: DividendTBacktestConfig,
    trade_pct: float,
    bar_index: int,
    hard_risk_exit: bool = False,
    reverse_buyback_target_price: float | None = None,
    reverse_expiry_bars: int = 24,
    reverse_expiry_trade_days: int | None = None,
) -> ResearchExecutionTransition:
    """Resolve and apply a single research execution transition.

    It uses the shared counterfactual resolver for fills and constraints.  A
    research-only per-bar fill cap permits controlled partial-fill rehearsal.
    """

    bar_time = str(next_bar["timestamp"])
    expiry_event = _pending_expiry_event(state.pending_buyback, bar_time=bar_time, bar_index=bar_index)
    prepared = advance_research_execution_state(state, bar_time=bar_time, bar_index=bar_index)
    if expiry_event is not None:
        return ResearchExecutionTransition(
            prepared,
            ExecutionResolution(False, expiry_event, bar_time, None, 0, 0.0, 0.0, 0.0, EXECUTION_CONSTRAINT_VERSION),
            expiry_event,
        )
    if hard_risk_exit and prepared.pending_buyback is not None:
        prepared = replace(prepared, pending_buyback=None)
        pending_event = "BUYBACK_CANCELLED_BY_HARD_RISK"
    else:
        pending_event = None
    pending = prepared.pending_buyback
    context = CounterfactualExecutionContext(
        equity_before=max(prepared.cash + (prepared.base_shares + prepared.t_shares) * float(next_bar["open"]), 0.0),
        cash=prepared.cash,
        total_sell_shares=prepared.base_shares + prepared.t_shares,
        sellable_shares=max(0, prepared.base_shares + prepared.t_shares - prepared.base_locked_shares - prepared.t_locked_shares),
        base_shares=prepared.base_shares,
        base_locked_shares=prepared.base_locked_shares,
        t_shares=prepared.t_shares,
        t_locked_shares=prepared.t_locked_shares,
        hard_risk_exit=hard_risk_exit,
        pending_buyback_shares=pending.remaining_shares if pending is not None else 0,
        pending_buyback_target_price=pending.target_price if pending is not None else None,
    )
    resolution = resolve_execution_request(
        signal=signal.value,
        symbol=symbol,
        candidate_bar_close_time=candidate_bar_close_time,
        next_bar=next_bar,
        context=context,
        config=config,
        trade_pct=trade_pct,
    )
    resolution = _cap_research_fill(resolution, next_bar, config)
    if not resolution.executable or resolution.reference_fill_price is None:
        return ResearchExecutionTransition(prepared, resolution, pending_event)
    state_after = _apply_resolution(prepared, signal, resolution, config)
    if signal is Signal.SELL_REVERSE_T:
        if reverse_buyback_target_price is None or reverse_buyback_target_price <= 0.0:
            raise ValueError("REVERSE_T_BUYBACK_TARGET_REQUIRED")
        proceeds = resolution.reference_fill_price * resolution.shares - resolution.fee_amount
        state_after = replace(
            state_after,
            pending_buyback=PendingBuyback(
                remaining_shares=resolution.shares,
                allocated_proceeds=proceeds,
                target_price=reverse_buyback_target_price,
                created_bar_index=bar_index,
                created_trade_date=_trade_date(str(next_bar["timestamp"])),
                expiry_bars=reverse_expiry_bars,
                expiry_trade_days=reverse_expiry_trade_days,
            ),
        )
        pending_event = "PENDING_BUYBACK_CREATED"
    return ResearchExecutionTransition(state_after, resolution, pending_event)


def _apply_resolution(
    state: ResearchExecutionState,
    signal: Signal,
    resolution: ExecutionResolution,
    config: DividendTBacktestConfig,
) -> ResearchExecutionState:
    assert resolution.reference_fill_price is not None
    if signal in {Signal.BUY_T, Signal.BUY_BACK_REVERSE_T, Signal.BUILD_BASE}:
        pending = state.pending_buyback
        next_pending = (
            replace(pending, remaining_shares=pending.remaining_shares - resolution.shares)
            if signal is Signal.BUY_BACK_REVERSE_T and pending is not None and pending.remaining_shares > resolution.shares
            else None
        )
        return replace(
            state,
            cash=state.cash - resolution.reference_fill_price * resolution.shares - resolution.fee_amount,
            t_shares=state.t_shares + resolution.shares,
            pending_buyback=next_pending,
        )
    proceeds = resolution.reference_fill_price * resolution.shares - resolution.fee_amount
    if signal is Signal.SELL_REVERSE_T:
        return replace(state, cash=state.cash + proceeds, base_shares=state.base_shares - resolution.shares)
    if signal is Signal.CLEAR:
        sold_t = min(state.t_shares, resolution.shares)
        return replace(
            state,
            cash=state.cash + proceeds,
            t_shares=state.t_shares - sold_t,
            base_shares=state.base_shares - (resolution.shares - sold_t),
        )
    return replace(state, cash=state.cash + proceeds, t_shares=max(0, state.t_shares - resolution.shares))


def _cap_research_fill(resolution: ExecutionResolution, row: Any, config: DividendTBacktestConfig) -> ExecutionResolution:
    cap = row.get("research_max_fill_shares") if hasattr(row, "get") else None
    if cap is None or not resolution.executable:
        return resolution
    try:
        cap_shares = int(float(cap) // config.min_lot) * config.min_lot
    except (TypeError, ValueError):
        return resolution
    if cap_shares <= 0 or cap_shares >= resolution.shares:
        return resolution
    ratio = cap_shares / resolution.shares
    return replace(
        resolution,
        shares=cap_shares,
        slippage_amount=resolution.slippage_amount * ratio,
        fee_amount=resolution.fee_amount * ratio,
        execution_cost=resolution.execution_cost * ratio,
    )


def _trade_date(timestamp: str) -> str:
    return timestamp[:10]


def _trade_day_distance(start: str, end: str) -> int:
    from datetime import date

    return max(0, (date.fromisoformat(end) - date.fromisoformat(start)).days)


def _pending_expiry_event(pending: PendingBuyback | None, *, bar_time: str, bar_index: int) -> str | None:
    if pending is None:
        return None
    if bar_index - pending.created_bar_index > pending.expiry_bars:
        return "BUYBACK_EXPIRED_BARS"
    if (
        pending.expiry_trade_days is not None
        and _trade_day_distance(pending.created_trade_date, _trade_date(bar_time)) > pending.expiry_trade_days
    ):
        return "BUYBACK_EXPIRED_TRADE_DAYS"
    return None
