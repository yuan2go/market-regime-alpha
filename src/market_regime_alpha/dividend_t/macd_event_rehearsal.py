"""Controlled non-empty MACD event rehearsal.

This is a research fixture, not a trading strategy and not a final-test runner.
It deliberately exercises the same shared policy and counterfactual execution
functions used by the four-arm runner, while keeping every timestamp inside a
small, non-test synthetic session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, cast

import pandas as pd

from market_regime_alpha.dividend_t.backtest import (
    CounterfactualExecutionContext,
    DividendTBacktestConfig,
    evaluate_sizing_counterfactual_paths,
    resolve_counterfactual_execution,
)
from market_regime_alpha.dividend_t.macd import MACDCross, MACDDataReason, MACDHistogramTrend, MACDZeroAxis
from market_regime_alpha.dividend_t.macd_experiments import (
    CounterfactualEvent,
    CounterfactualEventType,
    CounterfactualPathOutcome,
    ablation_profiles,
    canonical_json,
    factorial_attribution,
    intent_bucket,
)
from market_regime_alpha.dividend_t.macd_oos import write_immutable_run_artifact
from market_regime_alpha.dividend_t.models import Signal, TechnicalInputs
from market_regime_alpha.dividend_t.scoring import technical_score_diagnostics
from market_regime_alpha.dividend_t.signal_audit import audit_report, label_candidate_outcomes
from market_regime_alpha.dividend_t.signal_intent import (
    EntryConfirmation,
    ExitConfirmation,
    CandidateSignal,
    MACDPolicyConfig,
    MACDPolicyState,
    PrimarySetupCode,
    RiskEnforcement,
    SignalIntent,
    apply_macd_policy,
    apply_macd_sizing_once,
)


EVENT_REHEARSAL_VERSION = "macd-nonempty-event-rehearsal-v1"
_SYMBOL = "600000.SH"
_CANDIDATE_TIME = "2026-01-05 09:55:00"
_NEXT_EXECUTION_TIME = "2026-01-05 10:05:00"


@dataclass(frozen=True)
class RehearsalExecutionCheck:
    passed: bool
    detail: str


@dataclass(frozen=True)
class ControlledEventRehearsal:
    events_by_profile: dict[str, tuple[CounterfactualEvent, ...]]
    execution_checks: dict[str, RehearsalExecutionCheck]
    intent_buckets: frozenset[str]
    audit: dict[str, object]


@dataclass(frozen=True)
class _Scenario:
    name: str
    candidate: CandidateSignal
    macd: MACDPolicyState
    original_trade_pct: float
    score_suppression_candidate: bool = False
    context: CounterfactualExecutionContext = CounterfactualExecutionContext(100_000.0, 100_000.0)
    next_bar: dict[str, object] | None = None


def run_controlled_event_rehearsal() -> ControlledEventRehearsal:
    """Execute fixed current-bar scenarios through the shared MACD policy.

    It intentionally does not load a local history dataset or invoke the
    sealed OOS runner.  Every bar is final, timestamped as a close, and every
    simulated order uses the next eligible bar open.
    """

    scenarios = _scenarios()
    events_by_profile: dict[str, tuple[CounterfactualEvent, ...]] = {}
    for profile_name, policy in ablation_profiles().items():
        events_by_profile[profile_name] = tuple(
            _evaluate_scenario(scenario, policy=policy, profile_name=profile_name)
            for scenario in scenarios
        )
    all_events = tuple(event for events in events_by_profile.values() for event in events)
    checks = _execution_checks(events_by_profile)
    return ControlledEventRehearsal(
        events_by_profile=events_by_profile,
        execution_checks=checks,
        intent_buckets=frozenset(intent_bucket(event) for event in all_events),
        audit=_audit_fixture_report(),
    )


def write_controlled_event_rehearsal(root: Path, *, run_id: str) -> Path:
    """Publish a checksummed REHEARSAL-only artifact without overwrite support."""

    rehearsal = run_controlled_event_rehearsal()

    def writer(stage: Path) -> None:
        _write_json(
            stage / "manifest.json",
            {
                "version": EVENT_REHEARSAL_VERSION,
                "classification": "REHEARSAL",
                "sealed_test_accessed": False,
                "dataset_kind": "controlled-event-fixture",
                "candidate_time": _CANDIDATE_TIME,
                "next_eligible_execution_time": _NEXT_EXECUTION_TIME,
                "production_default": {"score_weight": 0.0, "conflict_gate_enabled": False},
            },
        )
        for profile, events in rehearsal.events_by_profile.items():
            folder = stage / profile
            folder.mkdir()
            policy = ablation_profiles()[profile]
            _write_json(folder / "config.json", _policy_payload(policy, profile))
            _write_json(folder / "metrics.json", _event_metrics(events))
            _write_jsonl(folder / "counterfactual_events.jsonl", events)
        attribution = _event_attribution(rehearsal.events_by_profile)
        (stage / "attribution").mkdir()
        _write_json(stage / "attribution" / "metrics.json", attribution)
        _write_json(stage / "execution_evidence.json", {key: asdict(value) for key, value in rehearsal.execution_checks.items()})
        (stage / "audit").mkdir()
        _write_json(stage / "audit" / "report.json", rehearsal.audit)
        (stage / "report.md").write_text(_format_report(rehearsal, attribution), encoding="utf-8")

    return write_immutable_run_artifact(root, run_id=run_id, writer=writer)


def _scenarios() -> tuple[_Scenario, ...]:
    strong_bear = MACDPolicyState(True, MACDCross.BEARISH, MACDZeroAxis.BELOW, -0.8, MACDHistogramTrend.EXPANDING)
    strong_bull = MACDPolicyState(True, MACDCross.BULLISH, MACDZeroAxis.ABOVE, 0.8, MACDHistogramTrend.EXPANDING)
    trend_bear = MACDPolicyState(True, MACDCross.BEARISH, MACDZeroAxis.STRADDLING, -0.4, MACDHistogramTrend.EXPANDING)
    return (
        _Scenario(
            "score_suppressed_buy",
            _candidate(Signal.BUY_T, PrimarySetupCode.TREND_FOLLOW),
            MACDPolicyState(True, MACDCross.NONE, MACDZeroAxis.ABOVE, 0.1, MACDHistogramTrend.FLAT),
            0.20,
            score_suppression_candidate=True,
            next_bar=_normal_bar(),
        ),
        _Scenario(
            "trend_buy_downgraded",
            _candidate(Signal.BUY_T, PrimarySetupCode.TREND_FOLLOW),
            trend_bear,
            0.20,
            next_bar=_normal_bar(),
        ),
        _Scenario(
            "mean_buy_sized",
            _candidate(Signal.BUY_T, PrimarySetupCode.PULLBACK_LOW_BUY, entries={EntryConfirmation.SUPPORT_HOLD}),
            strong_bear,
            0.20,
            next_bar=_normal_bar(),
        ),
        _Scenario(
            "mean_sell_sized",
            _candidate(Signal.SELL_T, PrimarySetupCode.PRESSURE_SELL_T, exits={ExitConfirmation.RESISTANCE_REJECTION}),
            strong_bull,
            0.20,
            context=CounterfactualExecutionContext(100_000.0, 50_000.0, total_sell_shares=2_000, sellable_shares=2_000, previous_daily_close=10.0),
            next_bar=_normal_bar(),
        ),
        _Scenario(
            "hard_risk_unchanged",
            _candidate(Signal.CLEAR, PrimarySetupCode.CLEAR, risk=RiskEnforcement.HARD),
            strong_bull,
            0.20,
            context=CounterfactualExecutionContext(100_000.0, 50_000.0, total_sell_shares=2_000, sellable_shares=2_000, previous_daily_close=10.0),
            next_bar=_normal_bar(),
        ),
        _Scenario(
            "soft_risk_unchanged",
            _candidate(Signal.STOP_T, PrimarySetupCode.STOP_T, risk=RiskEnforcement.SOFT),
            strong_bear,
            0.20,
            context=CounterfactualExecutionContext(100_000.0, 50_000.0, total_sell_shares=2_000, sellable_shares=2_000, previous_daily_close=10.0),
            next_bar=_normal_bar(),
        ),
    )


def _candidate(
    signal: Signal,
    setup: PrimarySetupCode,
    *,
    entries: set[EntryConfirmation] | None = None,
    exits: set[ExitConfirmation] | None = None,
    risk: RiskEnforcement = RiskEnforcement.NONE,
) -> CandidateSignal:
    intent = {
        PrimarySetupCode.TREND_FOLLOW: SignalIntent.TREND_FOLLOWING,
        PrimarySetupCode.PULLBACK_LOW_BUY: SignalIntent.MEAN_REVERSION_T,
        PrimarySetupCode.PRESSURE_SELL_T: SignalIntent.MEAN_REVERSION_T,
        PrimarySetupCode.CLEAR: SignalIntent.RISK_REDUCTION,
        PrimarySetupCode.STOP_T: SignalIntent.RISK_REDUCTION,
    }[setup]
    return CandidateSignal(
        candidate_signal=signal,
        candidate_setup_code=setup,
        primary_setup_code=setup,
        candidate_signal_intent=intent,
        decision_bar_time=_CANDIDATE_TIME,
        confirmation_bar_time=_CANDIDATE_TIME,
        entry_confirmations=frozenset(entries or {EntryConfirmation.NONE}),
        exit_confirmations=frozenset(exits or {ExitConfirmation.NONE}),
        risk_enforcement=risk,
    )


def _evaluate_scenario(scenario: _Scenario, *, policy: MACDPolicyConfig, profile_name: str) -> CounterfactualEvent:
    score_suppressed = scenario.score_suppression_candidate and policy.score_weight > 0.0 and _score_threshold_suppressed()
    original = scenario.original_trade_pct
    candidate_without = scenario.candidate.candidate_signal.value if scenario.candidate.candidate_signal else None
    config_hash = _profile_hash(policy, profile_name)
    if score_suppressed:
        return _evaluate_blocked_or_suppressed(
            CounterfactualEvent.create(
                symbol=_SYMBOL,
                candidate_bar_close_time=_CANDIDATE_TIME,
                next_eligible_execution_time=_NEXT_EXECUTION_TIME,
                candidate_without_macd_score=candidate_without,
                candidate_with_macd_score=None,
                candidate_before_policy=None,
                candidate_after_policy=None,
                original_suggested_trade_pct=original,
                adjusted_suggested_trade_pct=original,
                signal_intent=scenario.candidate.candidate_signal_intent.value,
                primary_setup_code=_setup_value(scenario.candidate.primary_setup_code),
                risk_enforcement=scenario.candidate.risk_enforcement.value,
                macd_score=0.0,
                macd_cross=scenario.macd.cross.value,
                macd_zero_axis=scenario.macd.zero_axis.value,
                macd_histogram_trend=scenario.macd.histogram_trend.value,
                experiment_config_hash=config_hash,
                macd_score_changed_candidate=True,
                macd_policy_changed_candidate=False,
            ),
            scenario,
        )
    policy_decision = apply_macd_policy(scenario.candidate, scenario.macd, policy)
    sizing = apply_macd_sizing_once(
        policy_decision,
        original_suggested_trade_pct=original,
        effective_minimum_trade_pct=policy.minimum_executable_trade_pct,
        sizing_owner="dividend_t_backtest_execution",
    )
    event = CounterfactualEvent.create(
        symbol=_SYMBOL,
        candidate_bar_close_time=_CANDIDATE_TIME,
        next_eligible_execution_time=_NEXT_EXECUTION_TIME,
        candidate_without_macd_score=candidate_without,
        candidate_with_macd_score=candidate_without,
        candidate_before_policy=candidate_without,
        candidate_after_policy=sizing.final_signal.value,
        original_suggested_trade_pct=original,
        adjusted_suggested_trade_pct=sizing.adjusted_suggested_trade_pct,
        signal_intent=scenario.candidate.candidate_signal_intent.value,
        primary_setup_code=_setup_value(scenario.candidate.primary_setup_code),
        risk_enforcement=scenario.candidate.risk_enforcement.value,
        macd_score=20.0 if scenario.macd.cross is MACDCross.BEARISH else 80.0,
        macd_cross=scenario.macd.cross.value,
        macd_zero_axis=scenario.macd.zero_axis.value,
        macd_histogram_trend=scenario.macd.histogram_trend.value,
        experiment_config_hash=config_hash,
        macd_score_changed_candidate=False,
        macd_policy_changed_candidate=sizing.trace.signal_downgraded or sizing.trace.macd_sizing_applied,
    )
    if event.event_type is CounterfactualEventType.POLICY_SIZED:
        return evaluate_sizing_counterfactual_paths(
            event,
            next_bar=scenario.next_bar or _normal_bar(),
            context=scenario.context,
            config=DividendTBacktestConfig(),
            forward_bars=_forward_bars(),
            outcome_resolver=_outcome,
        )
    if event.event_type in {CounterfactualEventType.POLICY_DOWNGRADED, CounterfactualEventType.UNCHANGED}:
        return _evaluate_blocked_or_suppressed(event, scenario)
    return event


def _evaluate_blocked_or_suppressed(event: CounterfactualEvent, scenario: _Scenario) -> CounterfactualEvent:
    resolution = resolve_counterfactual_execution(
        event,
        next_bar=scenario.next_bar or _normal_bar(),
        context=scenario.context,
        config=DividendTBacktestConfig(),
        trade_pct=event.original_suggested_trade_pct,
    )
    outcome = _outcome(event, resolution, _forward_bars()) if resolution.executable else None
    return replace(
        event,
        executable=resolution.executable,
        block_reason=resolution.block_reason,
        reference_fill_price=resolution.reference_fill_price,
        counterfactual_shares=resolution.shares,
        slippage_amount=resolution.slippage_amount,
        fee_amount=resolution.fee_amount,
        counterfactual_net_pnl=outcome.net_pnl if outcome else None,
        holding_period_bars=outcome.holding_period_bars if outcome else None,
        max_adverse_excursion=outcome.max_adverse_excursion if outcome else None,
    )


def _score_threshold_suppressed() -> bool:
    technical = TechnicalInputs(
        position_quality=60.0,
        volume_structure=60.0,
        trend_quality=60.0,
        intraday_support=60.0,
        chan_score=60.0,
        macd_dif=-0.2,
        macd_dea=-0.1,
        macd_histogram=-0.1,
        macd_histogram_delta=-0.05,
        macd_histogram_trend=MACDHistogramTrend.EXPANDING,
        macd_cross=MACDCross.BEARISH,
        macd_cross_age=0,
        macd_zero_axis=MACDZeroAxis.BELOW,
        macd_data_ready=True,
        macd_data_reason=MACDDataReason.READY,
        macd_score=0.0,
    )
    scores = technical_score_diagnostics(technical, macd_weight=0.15)
    return scores.technical_score_without_macd >= 55.0 > scores.technical_score_with_macd


def _normal_bar() -> dict[str, object]:
    return {"timestamp": _NEXT_EXECUTION_TIME, "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 1_000_000.0, "prev_close": 10.0, "is_suspended": False}


def _forward_bars() -> tuple[dict[str, object], ...]:
    return (
        {"timestamp": "2026-01-05 10:10:00", "high": 10.4, "low": 9.8, "close": 10.2},
        {"timestamp": "2026-01-05 10:15:00", "high": 10.5, "low": 9.7, "close": 10.3},
    )


def _outcome(event: CounterfactualEvent, resolution: Any, forward: object) -> CounterfactualPathOutcome:
    bars: tuple[dict[str, object], ...] = tuple(cast(Iterable[dict[str, object]], forward))
    closes = [float(cast(str | int | float, bar["close"])) for bar in bars]
    highs = [float(cast(str | int | float, bar["high"])) for bar in bars]
    lows = [float(cast(str | int | float, bar["low"])) for bar in bars]
    fill = float(resolution.reference_fill_price)
    sell = event.candidate_before_policy in {Signal.SELL_T.value, Signal.CLEAR.value, Signal.REDUCE.value, Signal.STOP_T.value}
    mark = closes[-1]
    pnl = (fill - mark if sell else mark - fill) * resolution.shares - resolution.fee_amount
    mae = (fill - max(highs) if sell else min(lows) - fill) / fill
    return CounterfactualPathOutcome(net_pnl=pnl, holding_period_bars=len(bars), max_adverse_excursion=mae)


def _execution_checks(events_by_profile: dict[str, tuple[CounterfactualEvent, ...]]) -> dict[str, RehearsalExecutionCheck]:
    event = next(event for event in events_by_profile["policy-only"] if event.primary_setup_code == PrimarySetupCode.TREND_FOLLOW.value)
    config = DividendTBacktestConfig()
    suspended = {**_normal_bar(), "timestamp": "2026-01-05 10:00:00", "is_suspended": True, "volume": 0.0}
    suspended_resolution = resolve_counterfactual_execution(
        replace(event, next_eligible_execution_time="2026-01-05 10:00:00"),
        next_bar=suspended,
        context=CounterfactualExecutionContext(100_000.0, 100_000.0),
        config=config,
        trade_pct=0.20,
    )
    next_resolution = resolve_counterfactual_execution(event, next_bar=_normal_bar(), context=CounterfactualExecutionContext(100_000.0, 100_000.0), config=config, trade_pct=0.20)
    sell_event = next(event for event in events_by_profile["policy-only"] if event.primary_setup_code == PrimarySetupCode.PRESSURE_SELL_T.value)
    t1 = resolve_counterfactual_execution(sell_event, next_bar=_normal_bar(), context=CounterfactualExecutionContext(100_000.0, 10_000.0, total_sell_shares=1_000, sellable_shares=0, previous_daily_close=10.0), config=config, trade_pct=0.20)
    limit_up = resolve_counterfactual_execution(event, next_bar={**_normal_bar(), "open": 11.0}, context=CounterfactualExecutionContext(100_000.0, 100_000.0, previous_daily_close=10.0), config=config, trade_pct=0.20)
    limit_down = resolve_counterfactual_execution(sell_event, next_bar={**_normal_bar(), "open": 9.0}, context=CounterfactualExecutionContext(100_000.0, 10_000.0, total_sell_shares=1_000, sellable_shares=1_000, previous_daily_close=10.0), config=config, trade_pct=0.20)
    cash = resolve_counterfactual_execution(event, next_bar=_normal_bar(), context=CounterfactualExecutionContext(100_000.0, 0.0), config=config, trade_pct=0.20)
    sized = [event for events in events_by_profile.values() for event in events if event.event_type is CounterfactualEventType.POLICY_SIZED]
    return {
        "suspension_skip": RehearsalExecutionCheck(suspended_resolution.block_reason == "SUSPENDED" and next_resolution.executable, "09:55 candidate skips suspended 10:00 and resolves at 10:05 open"),
        "t1_lock": RehearsalExecutionCheck(t1.block_reason == "T1_LOCK", "sell requires sellable T shares"),
        "limit_up": RehearsalExecutionCheck(limit_up.block_reason == "LIMIT_UP", "buy cannot fill at limit up"),
        "limit_down": RehearsalExecutionCheck(limit_down.block_reason == "LIMIT_DOWN", "sell cannot fill at limit down"),
        "cash_limit": RehearsalExecutionCheck(cash.block_reason == "CASH_OR_MIN_LOT", "buy respects cash and lot constraint"),
        "sized_paths": RehearsalExecutionCheck(bool(sized) and all(event.adjusted_path_executable and event.original_path_executable and event.adjusted_path_shares < event.original_path_shares for event in sized), "sized events retain adjusted and original next-open paths"),
    }


def _policy_payload(policy: MACDPolicyConfig, profile: str) -> dict[str, object]:
    payload = asdict(policy)
    payload["profile"] = profile
    payload["rehearsal_config_hash"] = _profile_hash(policy, profile)
    return _json_value(payload)


def _profile_hash(policy: MACDPolicyConfig, profile: str) -> str:
    payload = _json_value({"version": EVENT_REHEARSAL_VERSION, "profile": profile, "policy": asdict(policy)})
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _event_metrics(events: tuple[CounterfactualEvent, ...]) -> dict[str, object]:
    counts = {event_type.value: 0 for event_type in CounterfactualEventType}
    for event in events:
        counts[event.event_type.value] += 1
    return {"event_count": len(events), "event_types": counts, "intent_buckets": sorted({intent_bucket(event) for event in events})}


def _event_attribution(events_by_profile: dict[str, tuple[CounterfactualEvent, ...]]) -> dict[str, object]:
    changed = {
        profile: sum(event.event_type is not CounterfactualEventType.UNCHANGED for event in events)
        for profile, events in events_by_profile.items()
    }
    return {"changed_event_count": asdict(factorial_attribution(baseline=changed["baseline"], score_only=changed["score-only"], policy_only=changed["policy-only"], full=changed["full"]))}


def _audit_fixture_report() -> dict[str, object]:
    bars: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    for index in range(12):
        start = pd.Timestamp("2026-01-05 09:35:00") + pd.Timedelta(minutes=20 * index)
        price = 10.0 + index * 0.05
        bars.extend(
            [
                {"symbol": _SYMBOL, "timestamp": start, "open": price, "high": price + 0.1, "low": price - 0.1, "close": price, "suspended": False, "at_limit_up": False, "at_limit_down": False},
                {"symbol": _SYMBOL, "timestamp": start + pd.Timedelta(minutes=5), "open": price + 0.02, "high": price + 0.14, "low": price - 0.03, "close": price + (0.08 if index % 2 == 0 else -0.05), "suspended": False, "at_limit_up": False, "at_limit_down": False},
                {"symbol": _SYMBOL, "timestamp": start + pd.Timedelta(minutes=10), "open": price + 0.03, "high": price + 0.16, "low": price - 0.06, "close": price + (0.10 if index % 3 else -0.07), "suspended": False, "at_limit_up": False, "at_limit_down": False},
            ]
        )
        if index % 5 == 0:
            action = "STOP_T"
            setup = "stop_t"
            intent = "RISK_REDUCTION"
        elif index % 5 == 1:
            action = "SELL_T"
            setup = "pressure_sell_t"
            intent = "MEAN_REVERSION_T"
        elif index % 5 == 2:
            action = "REVERSE_T_SELL"
            setup = "reverse_t_sell"
            intent = "MEAN_REVERSION_T"
        else:
            action = "BUY_T"
            setup = "pullback_low_buy"
            intent = "MEAN_REVERSION_T"
        candidates.append({
            "symbol": _SYMBOL,
            "timestamp": start,
            "action": action,
            "primary_setup_code": setup,
            "signal_intent": intent,
            "market_regime": "RANGE" if index % 2 else "BULL",
            "industry": "transport",
            "symbol_type": "A_SHARE",
            "volatility_bucket": "HIGH" if index % 3 else "LOW",
            "trend_state": "UPTREND" if index % 2 else "RANGE",
            "holding_period_bucket": "INTRADAY_1BAR",
            "up_probability": 0.65 if index % 2 else 0.35,
            "force_buy_edge": 50.0 + index * 2.0,
            "buy_strength_score": 58.0 + index,
            "sell_pressure": 55.0 + index,
            "capital_flow": 52.0 + index,
            "multi_period_trend": 54.0 + index,
            "risk_reward": 1.0 + index * 0.05,
            "breakout": 70.0 + index,
            "macd_score_weight": 0.15,
            "mean_reversion_size_multiplier": 0.5,
        })
    labels = label_candidate_outcomes(pd.DataFrame(candidates), pd.DataFrame(bars), intraday_horizons=(1,), daily_horizons=())
    labels["success"] = labels["success_bar_1"].fillna(0).astype(int)
    labels["net_return"] = labels["cost_adjusted_return_bar_1"].fillna(0.0)
    return audit_report(labels)


def _format_report(rehearsal: ControlledEventRehearsal, attribution: dict[str, object]) -> str:
    counts = cast(
        dict[str, int],
        _event_metrics(tuple(event for events in rehearsal.events_by_profile.values() for event in events))["event_types"],
    )
    checks = "\n".join(f"- {name}: {'PASS' if value.passed else 'FAIL'} — {value.detail}" for name, value in rehearsal.execution_checks.items())
    return (
        "# MACD Non-empty Event Rehearsal\n\n"
        "- Classification: `REHEARSAL`\n"
        "- Sealed test accessed: `False`\n"
        "- Purpose: verify event and counterfactual plumbing, not model profitability.\n"
        "- Production defaults remain `score_weight=0.0`, `conflict_gate_enabled=False`.\n\n"
        "## Aggregate event types\n\n"
        + "\n".join(f"- {name}: {count}" for name, count in counts.items())
        + "\n\n## Execution checks\n\n"
        + checks
        + "\n\n## Factorial changed-event attribution\n\n"
        + f"`{json.dumps(attribution, sort_keys=True)}`\n"
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(_json_value(payload), allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, events: tuple[CounterfactualEvent, ...]) -> None:
    path.write_text("".join(json.dumps(_json_value(asdict(event)), ensure_ascii=True, sort_keys=True) + "\n" for event in events), encoding="utf-8")


def _json_value(value: object) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    return value


def _setup_value(value: PrimarySetupCode | str | None) -> str:
    if isinstance(value, PrimarySetupCode):
        return value.value
    if isinstance(value, str) and value:
        return value
    raise ValueError("controlled rehearsal requires a primary setup")
