from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.dividend_t.models import PositionState, RetreatInputs, ScoreBreakdown, Signal, TechnicalInputs, TrendState
from market_regime_alpha.dividend_t.macd import MACDCross, MACDHistogramTrend, MACDZeroAxis
from market_regime_alpha.dividend_t.signal_intent import (
    SETUP_INTENT_MAP,
    CandidateContractError,
    CandidateSignal,
    EntryConfirmation,
    ExitConfirmation,
    PrimarySetupCode,
    RiskEnforcement,
    SignalIntent,
    MACDPolicyConfig,
    MACDPolicyState,
    apply_macd_policy,
    apply_macd_sizing_once,
    candidate_for,
    intent_for_setup,
    no_candidate,
    validate_candidate,
)
from market_regime_alpha.dividend_t.strategy import select_simplified_candidate


def score_fixture() -> ScoreBreakdown:
    return ScoreBreakdown(F_score=80, G_score=4, Z_score=4, K_score=4, S_score=2, R_score=80, T_score=80, total_score=80, C_score=65)


def candidate_fixture(
    *,
    signal: Signal | None = Signal.BUY_T,
    setup: PrimarySetupCode | str | None = PrimarySetupCode.PULLBACK_LOW_BUY,
    intent: SignalIntent = SignalIntent.MEAN_REVERSION_T,
    decision_bar_time: str = "2026-07-13 10:05:00",
    confirmation_bar_time: str | None = None,
    entry_confirmations: frozenset[EntryConfirmation] = frozenset({EntryConfirmation.SUPPORT_HOLD}),
    exit_confirmations: frozenset[ExitConfirmation] = frozenset({ExitConfirmation.NONE}),
    risk_enforcement: RiskEnforcement = RiskEnforcement.NONE,
) -> CandidateSignal:
    return CandidateSignal(
        candidate_signal=signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        candidate_signal_intent=intent,
        decision_bar_time=decision_bar_time,
        confirmation_bar_time=confirmation_bar_time or decision_bar_time,
        entry_confirmations=entry_confirmations,
        exit_confirmations=exit_confirmations,
        risk_enforcement=risk_enforcement,
    )


def test_primary_setup_uniquely_maps_to_intent() -> None:
    assert intent_for_setup(PrimarySetupCode.PULLBACK_LOW_BUY) is SignalIntent.MEAN_REVERSION_T
    assert intent_for_setup(PrimarySetupCode.THIRD_BUY_FOLLOW) is SignalIntent.TREND_FOLLOWING
    assert intent_for_setup(PrimarySetupCode.STRUCTURE_BREAK) is SignalIntent.RISK_REDUCTION
    assert intent_for_setup(PrimarySetupCode.BUILD_BASE) is SignalIntent.BASE_ACCUMULATION


def test_every_primary_setup_has_one_non_none_intent() -> None:
    assert set(SETUP_INTENT_MAP) == set(PrimarySetupCode)
    assert all(intent is not SignalIntent.NONE for intent in SETUP_INTENT_MAP.values())


def test_unknown_setup_raises_in_strict_mode_and_stays_unknown_in_compatibility_mode() -> None:
    with pytest.raises(CandidateContractError, match="UNKNOWN_PRIMARY_SETUP"):
        intent_for_setup("legacy-unknown", strict=True)
    assert intent_for_setup("legacy-unknown", strict=False) is SignalIntent.NONE

    candidate = candidate_fixture(setup="legacy-unknown", intent=SignalIntent.NONE)
    validation = validate_candidate(candidate, strict=False)
    assert validation.policy_applicable is False
    assert "UNKNOWN_PRIMARY_SETUP" in validation.trace_codes
    assert "UNKNOWN_SIGNAL_INTENT" in validation.trace_codes


def test_live_candidate_cannot_use_none_intent() -> None:
    candidate = candidate_fixture(intent=SignalIntent.NONE)

    with pytest.raises(CandidateContractError, match="UNKNOWN_SIGNAL_INTENT"):
        validate_candidate(candidate, strict=True)


def test_none_intent_is_valid_only_when_there_is_no_candidate() -> None:
    candidate = no_candidate("2026-07-13 10:05:00")

    validation = validate_candidate(candidate, strict=True)

    assert candidate.candidate_signal is None
    assert candidate.candidate_signal_intent is SignalIntent.NONE
    assert validation.policy_applicable is False
    assert validation.trace_codes == ()


def test_confirmation_must_belong_to_current_decision_bar() -> None:
    candidate = candidate_fixture(confirmation_bar_time="2026-07-13 10:00:00")

    with pytest.raises(CandidateContractError, match="current decision bar"):
        validate_candidate(candidate, strict=True)


def test_none_confirmation_cannot_accompany_real_confirmation() -> None:
    candidate = candidate_fixture(entry_confirmations=frozenset({EntryConfirmation.NONE, EntryConfirmation.SUPPORT_HOLD}))

    with pytest.raises(CandidateContractError, match="NONE cannot accompany entry confirmations"):
        validate_candidate(candidate, strict=True)


def test_candidate_constructor_assigns_intent_from_setup_once() -> None:
    candidate = candidate_for(
        Signal.BUY_T,
        PrimarySetupCode.BREAKOUT_CONFIRMED,
        TechnicalInputs(80, 80, 80, 80, chan_structure_type="breakout", near_support=True, shrinking_pullback=True),
        "2026-07-13 15:00:00",
    )

    assert candidate.primary_setup_code is PrimarySetupCode.BREAKOUT_CONFIRMED
    assert candidate.candidate_setup_code is PrimarySetupCode.BREAKOUT_CONFIRMED
    assert candidate.candidate_signal_intent is SignalIntent.TREND_FOLLOWING
    assert validate_candidate(candidate, strict=True).policy_applicable is True


def test_confirmations_are_recomputed_from_current_technical_snapshot() -> None:
    current = candidate_for(
        Signal.BUY_T,
        PrimarySetupCode.PULLBACK_LOW_BUY,
        TechnicalInputs(80, 80, 80, 80, near_support=True, shrinking_pullback=True, intraday_reversal=True),
        "2026-07-13 10:05:00",
    )
    next_bar = candidate_for(
        Signal.BUY_T,
        PrimarySetupCode.PULLBACK_LOW_BUY,
        TechnicalInputs(80, 80, 80, 80),
        "2026-07-13 10:10:00",
    )

    assert EntryConfirmation.SUPPORT_HOLD in current.entry_confirmations
    assert EntryConfirmation.INTRADAY_REVERSAL in current.entry_confirmations
    assert next_bar.entry_confirmations == frozenset({EntryConfirmation.NONE})
    assert next_bar.confirmation_bar_time == next_bar.decision_bar_time


def test_primary_breakout_setup_wins_over_companion_pullback_flags() -> None:
    candidate = select_simplified_candidate(
        score=score_fixture(),
        retreat=RetreatInputs(4, 4, 3, 2),
        technical=TechnicalInputs(
            80,
            80,
            80,
            80,
            chan_score=80,
            trend_state=TrendState.BREAKOUT,
            chan_structure_type="breakout",
            chan_buy_point_type="buy2",
            near_support=True,
            shrinking_pullback=True,
        ),
        position=PositionState(),
        decision_bar_time="2026-07-13 15:00:00",
    )

    assert candidate.primary_setup_code is PrimarySetupCode.BREAKOUT_CONFIRMED
    assert candidate.candidate_signal_intent is SignalIntent.TREND_FOLLOWING


def test_risk_setup_priority_is_unique() -> None:
    candidate = select_simplified_candidate(
        score=score_fixture(),
        retreat=RetreatInputs(4, 4, 3, 2),
        technical=TechnicalInputs(
            80,
            80,
            30,
            40,
            trend_state=TrendState.DOWNTREND,
            chan_structure_type="breakdown",
            chan_sell_point_type="sell3",
            sector_healthy=False,
        ),
        position=PositionState(),
        decision_bar_time="2026-07-13 15:00:00",
    )

    assert candidate.candidate_signal is Signal.STOP_T
    assert candidate.primary_setup_code is PrimarySetupCode.STRUCTURE_BREAK
    assert candidate.candidate_signal_intent is SignalIntent.RISK_REDUCTION
    assert candidate.risk_enforcement is RiskEnforcement.HARD


def test_candidate_setup_and_primary_setup_must_match_in_v1() -> None:
    candidate = replace(candidate_fixture(), candidate_setup_code=PrimarySetupCode.VWAP_RECLAIM)

    with pytest.raises(CandidateContractError, match="candidate_setup_code must equal primary_setup_code"):
        validate_candidate(candidate, strict=True)


def ready_policy_state(
    *,
    cross: MACDCross,
    axis: MACDZeroAxis,
    histogram: float,
    trend: MACDHistogramTrend = MACDHistogramTrend.EXPANDING,
) -> MACDPolicyState:
    return MACDPolicyState(
        data_ready=True,
        cross=cross,
        zero_axis=axis,
        histogram=histogram,
        histogram_trend=trend,
    )


def experimental_policy(**overrides: object) -> MACDPolicyConfig:
    values = {"score_weight": 0.15, "conflict_gate_enabled": True}
    values.update(overrides)
    return MACDPolicyConfig(**values)


@pytest.mark.parametrize("axis", [MACDZeroAxis.BELOW, MACDZeroAxis.STRADDLING])
def test_trend_buy_bearish_cross_in_weak_axis_downgrades(axis: MACDZeroAxis) -> None:
    candidate = candidate_fixture(setup=PrimarySetupCode.BREAKOUT_CONFIRMED, intent=SignalIntent.TREND_FOLLOWING)

    decision = apply_macd_policy(
        candidate,
        ready_policy_state(cross=MACDCross.BEARISH, axis=axis, histogram=-0.2),
        experimental_policy(),
    )

    assert decision.final_signal is Signal.HOLD
    assert decision.trace.downgrade_source == "MACD_CONFLICT"


def test_trend_buy_bearish_cross_above_is_not_blocked() -> None:
    candidate = candidate_fixture(setup=PrimarySetupCode.BREAKOUT_CONFIRMED, intent=SignalIntent.TREND_FOLLOWING)

    decision = apply_macd_policy(
        candidate,
        ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.ABOVE, histogram=0.2),
        experimental_policy(),
    )

    assert decision.final_signal is Signal.BUY_T
    assert decision.macd_sizing_multiplier == 1.0


def test_unready_or_disabled_policy_is_identity() -> None:
    candidate = candidate_fixture(setup=PrimarySetupCode.BREAKOUT_CONFIRMED, intent=SignalIntent.TREND_FOLLOWING)
    bearish = ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.BELOW, histogram=-0.2)
    unready = MACDPolicyState.neutral()

    assert apply_macd_policy(candidate, unready, experimental_policy()).final_signal is Signal.BUY_T
    assert apply_macd_policy(candidate, bearish, MACDPolicyConfig()).final_signal is Signal.BUY_T


def test_mean_reversion_buy_requires_configured_current_confirmation() -> None:
    state = ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.BELOW, histogram=-0.2)
    accepted = candidate_fixture(entry_confirmations=frozenset({EntryConfirmation.SUPPORT_HOLD}))
    rejected = candidate_fixture(entry_confirmations=frozenset({EntryConfirmation.SELLING_PRESSURE_EXHAUSTION}))

    accepted_decision = apply_macd_policy(accepted, state, experimental_policy())
    rejected_decision = apply_macd_policy(rejected, state, experimental_policy())

    assert accepted_decision.final_signal is Signal.BUY_T
    assert accepted_decision.macd_sizing_multiplier == 0.5
    assert rejected_decision.final_signal is Signal.HOLD
    assert rejected_decision.trace.downgrade_source == "MACD_CONFIRMATION_REQUIRED"


def test_mean_reversion_sell_uses_exit_confirmation_set() -> None:
    candidate = candidate_fixture(
        signal=Signal.SELL_T,
        setup=PrimarySetupCode.PRESSURE_SELL_T,
        intent=SignalIntent.MEAN_REVERSION_T,
        entry_confirmations=frozenset({EntryConfirmation.NONE}),
        exit_confirmations=frozenset({ExitConfirmation.RESISTANCE_REJECTION}),
    )
    state = ready_policy_state(cross=MACDCross.BULLISH, axis=MACDZeroAxis.ABOVE, histogram=0.2)

    decision = apply_macd_policy(candidate, state, experimental_policy())

    assert decision.final_signal is Signal.SELL_T
    assert decision.macd_sizing_multiplier == 0.5


@pytest.mark.parametrize(
    ("signal", "setup"),
    [
        (Signal.CLEAR, PrimarySetupCode.CLEAR),
        (Signal.REDUCE, PrimarySetupCode.REDUCE),
        (Signal.STOP_T, PrimarySetupCode.STOP_T),
        (Signal.STOP_T, PrimarySetupCode.STRUCTURE_BREAK),
    ],
)
def test_hard_risk_is_explicit_and_macd_invariant(signal: Signal, setup: PrimarySetupCode) -> None:
    candidate = candidate_fixture(
        signal=signal,
        setup=setup,
        intent=SignalIntent.RISK_REDUCTION,
        risk_enforcement=RiskEnforcement.HARD,
    )
    state = ready_policy_state(cross=MACDCross.BULLISH, axis=MACDZeroAxis.ABOVE, histogram=0.2)

    decision = apply_macd_policy(candidate, state, experimental_policy())

    assert decision.final_signal is signal
    assert decision.trace.risk_enforcement is RiskEnforcement.HARD
    assert not decision.trace.macd_policy_applied


def test_risk_candidate_requires_explicit_enforcement() -> None:
    candidate = candidate_fixture(
        signal=Signal.STOP_T,
        setup=PrimarySetupCode.STOP_T,
        intent=SignalIntent.RISK_REDUCTION,
    )

    with pytest.raises(CandidateContractError, match="RISK_ENFORCEMENT_REQUIRED"):
        validate_candidate(candidate, strict=True)


def test_sizing_owner_applies_multiplier_once_and_zero_becomes_hold() -> None:
    candidate = candidate_fixture()
    policy = apply_macd_policy(
        candidate,
        ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.BELOW, histogram=-0.2),
        experimental_policy(),
    )

    sized = apply_macd_sizing_once(
        policy,
        original_suggested_trade_pct=0.20,
        effective_minimum_trade_pct=0.01,
        sizing_owner="test_owner",
    )

    assert sized.adjusted_suggested_trade_pct == 0.10
    assert sized.trace.macd_sizing_applied
    assert sized.trace.macd_sizing_owner == "test_owner"
    with pytest.raises(CandidateContractError, match="DUPLICATE_SIZING_ADJUSTMENT"):
        apply_macd_sizing_once(
            replace(policy, trace=sized.trace),
            original_suggested_trade_pct=0.20,
            effective_minimum_trade_pct=0.01,
            sizing_owner="test_owner",
        )

    zero = apply_macd_policy(candidate, ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.BELOW, histogram=-0.2), experimental_policy(mean_reversion_size_multiplier=0.0))
    zero_sized = apply_macd_sizing_once(
        zero,
        original_suggested_trade_pct=0.20,
        effective_minimum_trade_pct=0.0,
        sizing_owner="test_owner",
    )
    assert zero_sized.final_signal is Signal.HOLD
    assert zero_sized.trace.downgrade_source == "MACD_SIZING_TO_ZERO"


@pytest.mark.parametrize(
    "state",
    [
        ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.BELOW, histogram=-0.2, trend=MACDHistogramTrend.CONTRACTING),
        ready_policy_state(cross=MACDCross.BEARISH, axis=MACDZeroAxis.BELOW, histogram=0.0),
        ready_policy_state(cross=MACDCross.NONE, axis=MACDZeroAxis.BELOW, histogram=-0.2),
    ],
)
def test_mean_reversion_requires_complete_strong_opposition(state: MACDPolicyState) -> None:
    decision = apply_macd_policy(candidate_fixture(), state, experimental_policy())

    assert decision.final_signal is Signal.BUY_T
    assert decision.macd_sizing_multiplier == 1.0


def test_soft_risk_and_base_accumulation_are_not_changed() -> None:
    bullish = ready_policy_state(cross=MACDCross.BULLISH, axis=MACDZeroAxis.ABOVE, histogram=0.2)
    soft = candidate_fixture(
        signal=Signal.SELL_T,
        setup=PrimarySetupCode.TOP_DIVERGENCE_RISK,
        intent=SignalIntent.RISK_REDUCTION,
        risk_enforcement=RiskEnforcement.SOFT,
    )
    base = candidate_fixture(
        signal=Signal.BUILD_BASE,
        setup=PrimarySetupCode.BUILD_BASE,
        intent=SignalIntent.BASE_ACCUMULATION,
    )

    assert apply_macd_policy(soft, bullish, experimental_policy()).final_signal is Signal.SELL_T
    assert apply_macd_policy(base, bullish, experimental_policy()).final_signal is Signal.BUILD_BASE


def test_policy_config_rejects_none_in_accepted_confirmation_sets() -> None:
    with pytest.raises(ValueError, match="exclude NONE"):
        MACDPolicyConfig(mean_reversion_buy_accepted_confirmations=frozenset({EntryConfirmation.NONE}))
