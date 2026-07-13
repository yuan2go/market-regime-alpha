"""Explicit candidate setup, intent, confirmation, and trace contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from market_regime_alpha.dividend_t.chan import BUY_POINTS, SELL_POINTS
from market_regime_alpha.dividend_t.macd import BarInterval, MACDCross, MACDHistogramTrend, MACDResult, MACDZeroAxis
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


class RiskEnforcement(str, Enum):
    NONE = "NONE"
    SOFT = "SOFT"
    HARD = "HARD"


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
    TAKE_PROFIT_T = "take_profit_t"
    TAKE_PROFIT_REDUCE_T = "take_profit_reduce_t"
    RISK_REDUCE_T = "risk_reduce_t"
    EXIT_T_SOFT = "exit_t_soft"
    EXIT_T_HARD = "exit_t_hard"
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
    CLEAR_BASE = "clear_base"
    BUILD_BASE = "build_base"


SETUP_INTENT_MAP: dict[PrimarySetupCode, SignalIntent] = {
    PrimarySetupCode.PULLBACK_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.VWAP_RECLAIM: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.INTRADAY_REVERSAL: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.RANGE_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.PRESSURE_SELL_T: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.TAKE_PROFIT_T: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.TAKE_PROFIT_REDUCE_T: SignalIntent.MEAN_REVERSION_T,
    PrimarySetupCode.RISK_REDUCE_T: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.EXIT_T_SOFT: SignalIntent.RISK_REDUCTION,
    PrimarySetupCode.EXIT_T_HARD: SignalIntent.RISK_REDUCTION,
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
    PrimarySetupCode.CLEAR_BASE: SignalIntent.RISK_REDUCTION,
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
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE


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
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE
    contract_trace_codes: tuple[str, ...] = ()
    macd_policy_applied: bool = False
    signal_downgraded: bool = False
    downgrade_source: str | None = None
    downgrade_reason: str | None = None
    original_suggested_trade_pct: float | None = None
    macd_sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    sizing_adjustment_source: str | None = None
    macd_sizing_applied: bool = False
    macd_sizing_owner: str | None = None


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
    if not isinstance(candidate.risk_enforcement, RiskEnforcement):
        errors.append("risk_enforcement must be a RiskEnforcement")
    elif candidate.candidate_signal_intent is SignalIntent.RISK_REDUCTION and candidate.risk_enforcement is RiskEnforcement.NONE:
        errors.append("RISK_ENFORCEMENT_REQUIRED")
    elif candidate.candidate_signal_intent is not SignalIntent.RISK_REDUCTION and candidate.risk_enforcement is not RiskEnforcement.NONE:
        errors.append("RISK_ENFORCEMENT_ONLY_FOR_RISK_INTENT")

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
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE,
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
        risk_enforcement=risk_enforcement,
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
        risk_enforcement=RiskEnforcement.NONE,
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
        risk_enforcement=candidate.risk_enforcement,
        contract_trace_codes=contract_trace_codes,
    )


DEFAULT_ACCEPTED_ENTRY_CONFIRMATIONS = frozenset(
    {
        EntryConfirmation.INTRADAY_REVERSAL,
        EntryConfirmation.CHAN_BUY_POINT,
        EntryConfirmation.SUPPORT_HOLD,
        EntryConfirmation.VWAP_RECLAIM,
    }
)
DEFAULT_ACCEPTED_EXIT_CONFIRMATIONS = frozenset(
    {
        ExitConfirmation.VOLUME_STALLING,
        ExitConfirmation.RESISTANCE_REJECTION,
        ExitConfirmation.CHAN_SELL_POINT,
        ExitConfirmation.TOP_DIVERGENCE,
    }
)


@dataclass(frozen=True)
class MACDPolicyConfig:
    score_weight: float = 0.0
    conflict_gate_enabled: bool = False
    mean_reversion_size_multiplier: float = 0.5
    minimum_executable_trade_pct: float = 0.0
    trend_buy_block_bearish_cross: bool = True
    trend_buy_block_zero_axis_states: frozenset[MACDZeroAxis] = frozenset({MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING})
    mean_reversion_buy_accepted_confirmations: frozenset[EntryConfirmation] = DEFAULT_ACCEPTED_ENTRY_CONFIRMATIONS
    mean_reversion_sell_accepted_confirmations: frozenset[ExitConfirmation] = DEFAULT_ACCEPTED_EXIT_CONFIRMATIONS
    policy_version: str = MACD_POLICY_VERSION

    def __post_init__(self) -> None:
        for name in ("score_weight", "mean_reversion_size_multiplier", "minimum_executable_trade_pct"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        for name in ("conflict_gate_enabled", "trend_buy_block_bearish_cross"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if any(not isinstance(item, MACDZeroAxis) for item in self.trend_buy_block_zero_axis_states):
            raise ValueError("trend buy zero-axis states must use MACDZeroAxis")
        if not self.mean_reversion_buy_accepted_confirmations or any(
            not isinstance(item, EntryConfirmation) or item is EntryConfirmation.NONE
            for item in self.mean_reversion_buy_accepted_confirmations
        ):
            raise ValueError("accepted entry confirmations must be non-empty and exclude NONE")
        if not self.mean_reversion_sell_accepted_confirmations or any(
            not isinstance(item, ExitConfirmation) or item is ExitConfirmation.NONE
            for item in self.mean_reversion_sell_accepted_confirmations
        ):
            raise ValueError("accepted exit confirmations must be non-empty and exclude NONE")
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")


@dataclass(frozen=True)
class MACDPolicyState:
    data_ready: bool
    cross: MACDCross
    zero_axis: MACDZeroAxis
    histogram: float | None
    histogram_trend: MACDHistogramTrend

    def __post_init__(self) -> None:
        if not isinstance(self.data_ready, bool):
            raise ValueError("MACD policy readiness must be boolean")
        if not isinstance(self.cross, MACDCross) or not isinstance(self.zero_axis, MACDZeroAxis):
            raise ValueError("MACD policy cross and zero axis must use enums")
        if not isinstance(self.histogram_trend, MACDHistogramTrend):
            raise ValueError("MACD policy histogram trend must use enum")
        if self.data_ready and (self.histogram is None or not math.isfinite(float(self.histogram))):
            raise ValueError("ready MACD policy state requires finite histogram")
        if not self.data_ready and self.histogram is not None:
            raise ValueError("unready MACD policy state cannot carry histogram")

    @classmethod
    def neutral(cls) -> "MACDPolicyState":
        return cls(False, MACDCross.NONE, MACDZeroAxis.STRADDLING, None, MACDHistogramTrend.FLAT)

    @classmethod
    def from_technical(cls, technical: TechnicalInputs) -> "MACDPolicyState":
        return cls(
            technical.macd_data_ready,
            technical.macd_cross,
            technical.macd_zero_axis,
            technical.macd_histogram,
            technical.macd_histogram_trend,
        )

    @classmethod
    def from_result(cls, result: MACDResult, *, expected_interval: BarInterval) -> "MACDPolicyState":
        """Accept only formal, closed-bar MACD results for a matching pipeline."""

        if result.provisional:
            raise CandidateContractError("PROVISIONAL_MACD_NOT_ALLOWED")
        if result.config.bar_interval is not expected_interval:
            raise CandidateContractError(
                f"MACD_INTERVAL_MISMATCH: expected {expected_interval.value}, got {result.config.bar_interval.value}"
            )
        return cls(
            result.data_ready,
            result.cross,
            result.zero_axis,
            result.histogram,
            result.histogram_trend,
        )


@dataclass(frozen=True)
class PolicyDecision:
    final_signal: Signal
    macd_sizing_multiplier: float
    trace: DecisionTrace


@dataclass(frozen=True)
class SizingDecision:
    final_signal: Signal
    adjusted_suggested_trade_pct: float
    trace: DecisionTrace


def apply_macd_policy(
    candidate: CandidateSignal,
    macd: MACDPolicyState,
    config: MACDPolicyConfig,
    *,
    strict_contracts: bool = True,
) -> PolicyDecision:
    """Apply the one shared asymmetric policy without performing size arithmetic."""

    signal = candidate.candidate_signal or Signal.HOLD
    validation = validate_candidate(candidate, strict=strict_contracts)
    if not validation.policy_applicable:
        return _policy_decision(candidate, signal, contract_trace_codes=validation.trace_codes)
    if candidate.risk_enforcement is RiskEnforcement.HARD:
        return _policy_decision(candidate, signal)
    if not macd.data_ready or not config.conflict_gate_enabled:
        return _policy_decision(candidate, signal)
    if candidate.candidate_signal_intent in {SignalIntent.RISK_REDUCTION, SignalIntent.BASE_ACCUMULATION, SignalIntent.NONE}:
        return _policy_decision(candidate, signal, policy_applied=candidate.candidate_signal_intent is not SignalIntent.NONE)

    trend_conflict = (
        candidate.candidate_signal_intent is SignalIntent.TREND_FOLLOWING
        and signal is Signal.BUY_T
        and config.trend_buy_block_bearish_cross
        and macd.cross is MACDCross.BEARISH
        and macd.zero_axis in config.trend_buy_block_zero_axis_states
    )
    if trend_conflict:
        return _policy_decision(candidate, Signal.HOLD, downgrade_source="MACD_CONFLICT", policy_applied=True)

    if candidate.candidate_signal_intent is not SignalIntent.MEAN_REVERSION_T:
        return _policy_decision(candidate, signal, policy_applied=True)
    opposing_buy = (
        signal is Signal.BUY_T
        and macd.cross is MACDCross.BEARISH
        and macd.zero_axis in {MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING}
        and macd.histogram is not None
        and macd.histogram < 0.0
        and macd.histogram_trend is MACDHistogramTrend.EXPANDING
    )
    opposing_sell = (
        signal is Signal.SELL_T
        and macd.cross is MACDCross.BULLISH
        and macd.zero_axis in {MACDZeroAxis.ABOVE, MACDZeroAxis.STRADDLING}
        and macd.histogram is not None
        and macd.histogram > 0.0
        and macd.histogram_trend is MACDHistogramTrend.EXPANDING
    )
    if not opposing_buy and not opposing_sell:
        return _policy_decision(candidate, signal, policy_applied=True)
    accepted = (
        bool(candidate.entry_confirmations & config.mean_reversion_buy_accepted_confirmations)
        if opposing_buy
        else bool(candidate.exit_confirmations & config.mean_reversion_sell_accepted_confirmations)
    )
    if not accepted:
        return _policy_decision(candidate, Signal.HOLD, downgrade_source="MACD_CONFIRMATION_REQUIRED", policy_applied=True)
    return _policy_decision(
        candidate,
        signal,
        macd_sizing_multiplier=float(config.mean_reversion_size_multiplier),
        sizing_source="MACD_MEAN_REVERSION",
        policy_applied=True,
    )


def apply_macd_sizing_once(
    policy: PolicyDecision,
    *,
    original_suggested_trade_pct: float,
    effective_minimum_trade_pct: float,
    sizing_owner: str,
) -> SizingDecision:
    """The sole arithmetic owner used once at each position-aware boundary."""

    if policy.trace.macd_sizing_applied:
        raise CandidateContractError("DUPLICATE_SIZING_ADJUSTMENT")
    original = float(original_suggested_trade_pct)
    minimum = float(effective_minimum_trade_pct)
    if any(not math.isfinite(value) or value < 0.0 for value in (original, minimum)):
        raise ValueError("trade percentages must be finite and non-negative")
    if not isinstance(sizing_owner, str) or not sizing_owner.strip():
        raise ValueError("sizing_owner must be non-empty")
    multiplier = policy.macd_sizing_multiplier
    if policy.final_signal is Signal.HOLD:
        trace = _sized_trace(policy.trace, original, 0.0, applied=False, owner=None)
        return SizingDecision(policy.final_signal, 0.0, trace)
    if multiplier == 1.0:
        trace = _sized_trace(policy.trace, original, original, applied=False, owner=None)
        return SizingDecision(policy.final_signal, original, trace)
    adjusted = original * multiplier
    if adjusted <= minimum:
        trace = _sized_trace(
            policy.trace,
            original,
            0.0,
            applied=True,
            owner=sizing_owner,
            downgrade_source="MACD_SIZING_TO_ZERO",
        )
        return SizingDecision(Signal.HOLD, 0.0, trace)
    trace = _sized_trace(policy.trace, original, adjusted, applied=True, owner=sizing_owner)
    return SizingDecision(policy.final_signal, adjusted, trace)


def _policy_decision(
    candidate: CandidateSignal,
    final_signal: Signal,
    *,
    macd_sizing_multiplier: float = 1.0,
    downgrade_source: str | None = None,
    sizing_source: str | None = None,
    contract_trace_codes: tuple[str, ...] = (),
    policy_applied: bool = False,
) -> PolicyDecision:
    trace = DecisionTrace(
        candidate_signal=candidate.candidate_signal,
        candidate_signal_intent=candidate.candidate_signal_intent,
        candidate_setup_code=candidate.candidate_setup_code,
        primary_setup_code=candidate.primary_setup_code,
        entry_confirmations=tuple(sorted(item.value for item in candidate.entry_confirmations)),
        exit_confirmations=tuple(sorted(item.value for item in candidate.exit_confirmations)),
        candidate_reasons=candidate.candidate_reasons,
        final_signal=final_signal,
        risk_enforcement=candidate.risk_enforcement,
        contract_trace_codes=contract_trace_codes,
        macd_policy_applied=policy_applied,
        signal_downgraded=final_signal is not (candidate.candidate_signal or Signal.HOLD),
        downgrade_source=downgrade_source,
        downgrade_reason=downgrade_source,
        macd_sizing_multiplier=macd_sizing_multiplier,
        sizing_adjustment_source=sizing_source,
    )
    return PolicyDecision(final_signal, macd_sizing_multiplier, trace)


def _sized_trace(
    trace: DecisionTrace,
    original: float,
    adjusted: float,
    *,
    applied: bool,
    owner: str | None,
    downgrade_source: str | None = None,
) -> DecisionTrace:
    from dataclasses import replace

    return replace(
        trace,
        final_signal=Signal.HOLD if downgrade_source else trace.final_signal,
        signal_downgraded=trace.signal_downgraded or downgrade_source is not None,
        downgrade_source=downgrade_source or trace.downgrade_source,
        downgrade_reason=downgrade_source or trace.downgrade_reason,
        original_suggested_trade_pct=original,
        adjusted_suggested_trade_pct=adjusted,
        macd_sizing_applied=applied,
        macd_sizing_owner=owner,
    )
