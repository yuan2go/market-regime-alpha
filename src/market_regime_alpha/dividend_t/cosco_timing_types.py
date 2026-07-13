"""Shared data contracts for the COSCO 5-minute timing engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

from market_regime_alpha.dividend_t.macd import MACD_ALGORITHM_VERSION, MACD_CONTRACT_VERSION
from market_regime_alpha.dividend_t.models import Signal
from market_regime_alpha.dividend_t.signal_intent import (
    CONFIRMATION_RULE_VERSION,
    MACD_POLICY_VERSION,
    SIGNAL_INTENT_MAPPING_VERSION,
    CandidateSignal,
    EntryConfirmation,
    ExitConfirmation,
    PrimarySetupCode,
    RiskEnforcement,
    SignalIntent,
    intent_for_setup,
    validate_candidate,
)

if TYPE_CHECKING:
    from market_regime_alpha.dividend_t.attention import AttentionScore
    from market_regime_alpha.dividend_t.certainty import CertaintyScore
    from market_regime_alpha.dividend_t.chan import ChanStructure
    from market_regime_alpha.dividend_t.dynamic_weights import DynamicWeights
    from market_regime_alpha.dividend_t.force_ratio import ForceRatioEstimate
    from market_regime_alpha.dividend_t.memory import MemoryScore
    from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate

@dataclass(frozen=True)
class ReferencePrices:
    current_price: float
    support_price: float
    resistance_price: float
    buy_reference_price: float | None
    sell_reference_price: float | None
    stop_price: float | None
    buy_back_reference_price: float | None = None


@dataclass(frozen=True)
class SignalStrength:
    score: float
    label: str
    estimated_win_rate: float
    reward_risk_ratio: float
    kelly_fraction: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MarketRegime:
    state: str
    label: str
    base_position_target_pct: float
    base_position_limit_pct: float
    t_trade_limit_pct: float
    active_position_cap_pct: float = 0.0
    max_total_position_pct: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MultiPeriodTrend:
    score: float
    daily_5d_state: str
    weekly_state: str
    monthly_state: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    trend_5_20_state: str = "INSUFFICIENT"
    return_5d: float = 0.0
    return_20d: float = 0.0
    ma20_slope: float = 0.0


@dataclass(frozen=True)
class CapitalFlowEstimate:
    score: float
    state: str
    short_flow_ratio: float
    medium_flow_ratio: float
    long_flow_ratio: float
    confirmation_score: float
    confirmation_state: str
    confidence: float
    source_type: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VolumePriceStructure:
    score: float
    state: str
    volume_breakout_score: float = 50.0
    low_volume_pullback_score: float = 50.0
    high_volume_stall_score: float = 0.0
    price_up_volume_down_score: float = 0.0
    vwap_support_score: float = 50.0
    post_breakout_volume_persistence_score: float = 50.0
    volume_expansion_ratio: float = 1.0
    price_efficiency: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TrendProbability:
    up_1d: float
    down_1d: float
    up_3d: float
    down_3d: float
    edge_1d: float
    edge_3d: float
    state: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BreakoutSetup:
    score: float
    state: str
    breakout_level: float | None
    trigger_price: float | None
    day_return: float
    recent_return: float
    volume_expansion: float
    distance_to_breakout: float | None
    breakout_confirmed: bool
    pre_breakout_watch: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DailyContext:
    score: float
    state: str
    fundamental_score: float
    base_position_limit_pct: float
    close: float
    previous_close: float | None
    ma3: float | None
    ma5: float | None
    daily_support: float | None
    daily_resistance: float | None
    allow_t: bool
    allow_overnight: bool
    buyback_allowed: bool
    position_multiplier: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntradayContext:
    score: float
    state: str
    support_confirmed: bool
    resistance_confirmed: bool
    late_session: bool
    near_support: bool
    near_resistance: bool
    rebound_from_low: bool
    five_min_reclaim: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ManualCandidateDecision:
    """Winning 5-minute setup before quality, freshness, or policy filters."""

    action: str
    candidate_signal: Signal | None
    candidate_setup_code: PrimarySetupCode | None
    primary_setup_code: PrimarySetupCode | None
    signal_intent: SignalIntent
    decision_bar_time: str
    confirmation_bar_time: str
    entry_confirmations: frozenset[EntryConfirmation]
    exit_confirmations: frozenset[ExitConfirmation]
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE


def manual_candidate(
    action: str,
    candidate_signal: Signal | None,
    setup: PrimarySetupCode | None,
    *,
    decision_bar_time: str,
    entry_confirmations: frozenset[EntryConfirmation] = frozenset({EntryConfirmation.NONE}),
    exit_confirmations: frozenset[ExitConfirmation] = frozenset({ExitConfirmation.NONE}),
    reasons: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE,
) -> ManualCandidateDecision:
    """Assign a branch-selected setup's intent exactly once."""

    intent = SignalIntent.NONE if setup is None else intent_for_setup(setup)
    candidate = ManualCandidateDecision(
        action=action,
        candidate_signal=candidate_signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        signal_intent=intent,
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=decision_bar_time,
        entry_confirmations=entry_confirmations,
        exit_confirmations=exit_confirmations,
        reasons=reasons,
        warnings=warnings,
        risk_enforcement=risk_enforcement,
    )
    validate_candidate(policy_candidate_from_manual(candidate), strict=True)
    return candidate


def policy_candidate_from_manual(candidate: ManualCandidateDecision) -> CandidateSignal:
    """Copy a manual candidate into the shared policy contract without inference."""

    return CandidateSignal(
        candidate_signal=candidate.candidate_signal,
        candidate_setup_code=candidate.candidate_setup_code,
        primary_setup_code=candidate.primary_setup_code,
        candidate_signal_intent=candidate.signal_intent,
        decision_bar_time=candidate.decision_bar_time,
        confirmation_bar_time=candidate.confirmation_bar_time,
        entry_confirmations=candidate.entry_confirmations,
        exit_confirmations=candidate.exit_confirmations,
        candidate_reasons=candidate.reasons,
        risk_enforcement=candidate.risk_enforcement,
    )


class CandidateTraceFields(TypedDict):
    candidate_signal: str | None
    candidate_setup_code: str | None
    primary_setup_code: str | None
    candidate_signal_intent: str
    decision_bar_time: str
    confirmation_bar_time: str
    entry_confirmations: tuple[str, ...]
    exit_confirmations: tuple[str, ...]
    risk_enforcement: str


def candidate_trace_fields(candidate: ManualCandidateDecision) -> CandidateTraceFields:
    """Serialize candidate identity without parsing actions or reason text."""

    return {
        "candidate_signal": candidate.candidate_signal.value if candidate.candidate_signal else None,
        "candidate_setup_code": candidate.candidate_setup_code.value if candidate.candidate_setup_code else None,
        "primary_setup_code": candidate.primary_setup_code.value if candidate.primary_setup_code else None,
        "candidate_signal_intent": candidate.signal_intent.value,
        "decision_bar_time": candidate.decision_bar_time,
        "confirmation_bar_time": candidate.confirmation_bar_time,
        "entry_confirmations": tuple(sorted(item.value for item in candidate.entry_confirmations)),
        "exit_confirmations": tuple(sorted(item.value for item in candidate.exit_confirmations)),
        "risk_enforcement": candidate.risk_enforcement.value,
    }


@dataclass(frozen=True)
class TimingDecisionTrace:
    candidate_signal: str | None = None
    candidate_setup_code: str | None = None
    primary_setup_code: str | None = None
    candidate_signal_intent: str = SignalIntent.NONE.value
    risk_enforcement: str = RiskEnforcement.NONE.value
    decision_bar_time: str = ""
    confirmation_bar_time: str = ""
    entry_confirmations: tuple[str, ...] = (EntryConfirmation.NONE.value,)
    exit_confirmations: tuple[str, ...] = (ExitConfirmation.NONE.value,)
    raw_candidate_action: str = "WAIT"
    quality_filtered_action: str = "WAIT"
    macd_filtered_action: str = "WAIT"
    freshness_filtered_action: str = "WAIT"
    final_action: str = "WAIT"
    final_signal: str = Signal.HOLD.value
    signal_downgraded: bool = False
    downgrade_source: str | None = None
    downgrade_reason: str | None = None
    original_suggested_trade_pct: float | None = None
    macd_sizing_multiplier: float = 1.0
    adjusted_suggested_trade_pct: float | None = None
    sizing_adjustment_source: str | None = None
    macd_sizing_applied: bool = False
    macd_policy_applied: bool = False
    macd_contract_version: str = MACD_CONTRACT_VERSION
    macd_algorithm_version: str = MACD_ALGORITHM_VERSION
    macd_policy_version: str = MACD_POLICY_VERSION
    signal_intent_mapping_version: str = SIGNAL_INTENT_MAPPING_VERSION
    confirmation_rule_version: str = CONFIRMATION_RULE_VERSION


@dataclass(frozen=True)
class CoscoTimingSnapshot:
    symbol: str
    name: str
    timestamp: str
    generated_at: str
    data_source: str
    data_age_minutes: float
    data_fresh: bool
    freshness_status: str
    freshness_limit_minutes: float
    interval_minutes: int
    action: str
    confidence: float
    prices: ReferencePrices
    attention: AttentionScore
    certainty: CertaintyScore
    memory: MemoryScore
    sell_pressure: SellPressureEstimate
    weights: DynamicWeights
    force: ForceRatioEstimate
    market_regime: MarketRegime
    multi_period_trend: MultiPeriodTrend
    capital_flow: CapitalFlowEstimate
    volume_price_structure: VolumePriceStructure
    chan_structure: ChanStructure
    trend_probability: TrendProbability
    breakout_setup: BreakoutSetup
    signal_strength: SignalStrength
    risk_reward_ratio: float
    trend_state: str
    daily_context: DailyContext
    intraday_context: IntradayContext
    decision_trace: TimingDecisionTrace
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    data_attempts: tuple[dict[str, object], ...] = field(default_factory=tuple)
    runtime_profile: tuple[dict[str, object], ...] = field(default_factory=tuple)
    manual_only: bool = True
    is_realtime: bool = False
    signal_blocked: bool = False
    buy_point_subtype: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoscoTimingUnavailable:
    symbol: str
    status: str
    message: str
    required_user_steps: tuple[str, ...]
    data_source: str = "tushare_stk_mins_5min"
    is_realtime: bool = False
    data_attempts: tuple[dict[str, object], ...] = field(default_factory=tuple)
    runtime_profile: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
