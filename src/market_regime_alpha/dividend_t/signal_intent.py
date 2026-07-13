"""Explicit candidate setup, intent, confirmation, and trace contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.dividend_t.chan import BUY_POINTS, SELL_POINTS
from market_regime_alpha.dividend_t.models import Signal, TechnicalInputs


SIGNAL_INTENT_MAPPING_VERSION = "signal-intent-map-v1"
CONFIRMATION_RULE_VERSION = "confirmation-rules-v1"
MACD_POLICY_VERSION = "signal-intent-macd-v1"


class SignalIntent(str, Enum):
    NONE = "NONE"
    MEAN_REVERSION_T = "MEAN_REVERSION_T"
    TREND_FOLLOWING = "TREND_FOLLOWING"
    RISK_REDUCTION = "RISK_REDUCTION"
    BASE_ACCUMULATION = "BASE_ACCUMULATION"


class EntryConfirmation(str, Enum):
    NONE = "NONE"
    INTRADAY_REVERSAL = "INTRADAY_REVERSAL"
    CHAN_BUY_POINT = "CHAN_BUY_POINT"
    SUPPORT_HOLD = "SUPPORT_HOLD"
    VWAP_RECLAIM = "VWAP_RECLAIM"
    SELLING_PRESSURE_EXHAUSTION = "SELLING_PRESSURE_EXHAUSTION"


class ExitConfirmation(str, Enum):
    NONE = "NONE"
    VOLUME_STALLING = "VOLUME_STALLING"
    RESISTANCE_REJECTION = "RESISTANCE_REJECTION"
    CHAN_SELL_POINT = "CHAN_SELL_POINT"
    TOP_DIVERGENCE = "TOP_DIVERGENCE"
    MOMENTUM_EXHAUSTION = "MOMENTUM_EXHAUSTION"


class PrimarySetupCode(str, Enum):
    PULLBACK_LOW_BUY = "pullback_low_buy"
    VWAP_RECLAIM = "vwap_reclaim"
    INTRADAY_REVERSAL = "intraday_reversal"
    RANGE_LOW_BUY = "range_low_buy"
    PRESSURE_SELL_T = "pressure_sell_t"
    REVERSE_T_SELL = "reverse_t_sell"
    FORCE_REVERSAL_PROBE = "force_reversal_probe"
    TREND_FOLLOW = "trend_follow"
    TREND_PULLBACK_FOLLOW = "trend_pullback_follow"
    BREAKOUT_CONFIRMED = "breakout_confirmed"
    THIRD_BUY_FOLLOW = "third_buy_follow"
    STRONG_LAUNCH_FOLLOW = "strong_launch_follow"
    ATTENTION_FEEDBACK_FOLLOW = "attention_feedback_follow"
    CLEAR = "clear"
    REDUCE = "reduce"
    STOP_T = "stop_t"
    THIRD_SELL = "third_sell"
    STRUCTURE_BREAK = "structure_break"
    CHAN_SELL_RISK = "chan_sell_risk"
    TOP_DIVERGENCE_RISK = "top_divergence_risk"
    BUILD_BASE = "build_base"


SETUP_INTENT_MAP: dict[PrimarySetupCode, SignalIntent] = {
    PrimarySetupCode.PULLBACK_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.VWAP_RECLAIM: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.INTRADAY_REVERSAL: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.RANGE_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.PRESSURE_SELL_T: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.REVERSE_T_SELL: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.FORCE_REVERSAL_PROBE: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.TREND_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.TREND_PULLBACK_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.BREAKOUT_CONFIRMED: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.THIRD_BUY_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.STRONG_LAUNCH_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.ATTENTION_FEEDBACK_FOLLOW: SignalIntent.TREND_FOLLOWING,
    PrimarySetupCode.CLEAR: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.REDUCE: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.STOP_T: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.THIRD_SELL: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.STRUCTURE_BREAK: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.CHAN_SELL_RISK: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.TOP_DIVERGENCE_RISK: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.BUILD_BASE: SignalIntent.BASE_ACCUMULATION,
}


class CandidateContractError(ValueError):
    """Raised when a candidate violates the explicit intent contract."""


def intent_for_setup(setup: PrimarySetupCode | str, *, strict: bool = True) -> SignalIntent:
    """Resolve intent only through the single versioned setup map."""

    if isinstance(setup, PrimarySetupCode):
        return SETUP_INTENT_MAP[setup]
    if strict:
        raise CandidateContractError(f"UNKNOWN_PRIMARY_SETUP: {setup}")
    return SignalIntent.NONE


@dataclass(frozen=True)
class CandidateSignal:
    candidate_signal: Signal | None
    candidate_setup_code: PrimarySetupCode | str | None
    primary_setup_code: PrimarySetupCode | str | None
    candidate_signal_intent: SignalIntent
    decision_bar_time: str
    confirmation_bar_time: str
    entry_confirmations: frozenset[EntryConfirmation]
    exit_confirmations: frozenset[ExitConfirmation]
    candidate_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateValidation:
    policy_applicable: bool
    trace_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionTrace:
    candidate_signal: Signal | None
    candidate_signal_intent: SignalIntent
    candidate_setup_code: PrimarySetupCode | str | None
    primary_setup_code: PrimarySetupCode | str | None
    entry_confirmations: tuple[str, ...]
    exit_confirmations: tuple[str, ...]
    candidate_reasons: tuple[str, ...]
    final_signal: Signal
    contract_trace_codes: tuple[str, ...] = ()
    macd_policy_applied: bool = False
    signal_downgraded: bool = False
    downgrade_source: str | None = None
    downgrade_reason: str | None = None
    original_suggested_trade_pct: float | None = None
    sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    sizing_adjustment_source: str | None = None
    sizing_adjustment_applied: bool = False


def validate_candidate(candidate: CandidateSignal, *, strict: bool) -> CandidateValidation:
    """Validate strict live candidates or diagnose compatible legacy records."""

    has_live_signal = candidate.candidate_signal is not None and candidate.candidate_signal is not Signal.HOLD
    errors: list[str] = []

    if has_live_signal and candidate.candidate_signal_intent is SignalIntent.NONE:
        errors.append("UNKNOWN_SIGNAL_INTENT")
    if has_live_signal and not isinstance(candidate.primary_setup_code, PrimarySetupCode):
        errors.append("UNKNOWN_PRIMARY_SETUP")
    if isinstance(candidate.primary_setup_code, PrimarySetupCode):
        mapped = intent_for_setup(candidate.primary_setup_code)
        if candidate.candidate_signal_intent is not mapped:
            errors.append("SETUP_INTENT_MISMATCH")
    if candidate.candidate_setup_code != candidate.primary_setup_code:
        errors.append("candidate_setup_code must equal primary_setup_code in v1")

    if not candidate.decision_bar_time or not candidate.confirmation_bar_time:
        errors.append("candidate bar time must be explicit")
    has_real_confirmation = any(item is not EntryConfirmation.NONE for item in candidate.entry_confirmations) or any(
        item is not ExitConfirmation.NONE for item in candidate.exit_confirmations
    )
    if has_real_confirmation and candidate.confirmation_bar_time != candidate.decision_bar_time:
        errors.append("confirmation must belong to current decision bar")
    if EntryConfirmation.NONE in candidate.entry_confirmations and len(candidate.entry_confirmations) > 1:
        errors.append("NONE cannot accompany entry confirmations")
    if ExitConfirmation.NONE in candidate.exit_confirmations and len(candidate.exit_confirmations) > 1:
        errors.append("NONE cannot accompany exit confirmations")
    if not candidate.entry_confirmations or not all(isinstance(item, EntryConfirmation) for item in candidate.entry_confirmations):
        errors.append("entry confirmations must use EntryConfirmation values")
    if not candidate.exit_confirmations or not all(isinstance(item, ExitConfirmation) for item in candidate.exit_confirmations):
        errors.append("exit confirmations must use ExitConfirmation values")

    if errors and strict:
        raise CandidateContractError("; ".join(errors))
    return CandidateValidation(policy_applicable=has_live_signal and not errors, trace_codes=tuple(errors))


def current_entry_confirmations(technical: TechnicalInputs) -> frozenset[EntryConfirmation]:
    values: set[EntryConfirmation] = set()
    if technical.intraday_reversal:
        values.add(EntryConfirmation.INTRADAY_REVERSAL)
    if technical.chan_buy_point_type in BUY_POINTS:
        values.add(EntryConfirmation.CHAN_BUY_POINT)
    if technical.near_support and (technical.shrinking_pullback or technical.intraday_reversal):
        values.add(EntryConfirmation.SUPPORT_HOLD)
    return frozenset(values)


def current_exit_confirmations(technical: TechnicalInputs) -> frozenset[ExitConfirmation]:
    values: set[ExitConfirmation] = set()
    if technical.volume_stalling:
        values.add(ExitConfirmation.VOLUME_STALLING)
    if technical.near_resistance and technical.volume_stalling:
        values.add(ExitConfirmation.RESISTANCE_REJECTION)
    if technical.chan_sell_point_type in SELL_POINTS:
        values.add(ExitConfirmation.CHAN_SELL_POINT)
    if technical.chan_divergence_type == "top":
        values.add(ExitConfirmation.TOP_DIVERGENCE)
    return frozenset(values)


def candidate_for(
    signal: Signal,
    setup: PrimarySetupCode,
    technical: TechnicalInputs,
    decision_bar_time: str,
    *,
    reasons: tuple[str, ...] = (),
) -> CandidateSignal:
    """Construct a live candidate and assign its intent exactly once."""

    entry = current_entry_confirmations(technical)
    exit_ = current_exit_confirmations(technical)
    candidate = CandidateSignal(
        candidate_signal=signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        candidate_signal_intent=intent_for_setup(setup),
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=decision_bar_time,
        entry_confirmations=entry or frozenset({EntryConfirmation.NONE}),
        exit_confirmations=exit_ or frozenset({ExitConfirmation.NONE}),
        candidate_reasons=reasons,
    )
    validate_candidate(candidate, strict=True)
    return candidate


def no_candidate(decision_bar_time: str, *, reasons: tuple[str, ...] = ()) -> CandidateSignal:
    candidate = CandidateSignal(
        candidate_signal=None,
        candidate_setup_code=None,
        primary_setup_code=None,
        candidate_signal_intent=SignalIntent.NONE,
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=decision_bar_time,
        entry_confirmations=frozenset({EntryConfirmation.NONE}),
        exit_confirmations=frozenset({ExitConfirmation.NONE}),
        candidate_reasons=reasons,
    )
    validate_candidate(candidate, strict=True)
    return candidate


def decision_trace_for(
    candidate: CandidateSignal,
    *,
    final_signal: Signal,
    contract_trace_codes: tuple[str, ...] = (),
) -> DecisionTrace:
    return DecisionTrace(
        candidate_signal=candidate.candidate_signal,
        candidate_signal_intent=candidate.candidate_signal_intent,
        candidate_setup_code=candidate.candidate_setup_code,
        primary_setup_code=candidate.primary_setup_code,
        entry_confirmations=tuple(sorted(item.value for item in candidate.entry_confirmations)),
        exit_confirmations=tuple(sorted(item.value for item in candidate.exit_confirmations)),
        candidate_reasons=candidate.candidate_reasons,
        final_signal=final_signal,
        contract_trace_codes=contract_trace_codes,
    )
