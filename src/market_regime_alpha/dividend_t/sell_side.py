"""Research-only sell-side action taxonomy.

This module freezes action ownership and intent/enforcement combinations before
any broader production strategy migration.  It has no production profile or
MACD promotion side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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
