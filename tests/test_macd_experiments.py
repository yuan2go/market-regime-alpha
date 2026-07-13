from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.backtest import BacktestSignal, BacktestSignalCache, DividendTBacktestConfig
from market_regime_alpha.dividend_t.macd import (
    BarInterval,
    HistogramToleranceMode,
    MACDConfig,
)
from market_regime_alpha.dividend_t.macd_experiments import (
    AblationArmContext,
    CounterfactualEvent,
    CounterfactualEventType,
    ExecutionResolution,
    MACD_CACHE_SCHEMA_VERSION,
    MACDExperimentIdentity,
    ablation_profiles,
    build_experiment_identity,
    cache_metadata,
    canonical_experiment_config,
    canonical_json,
    experiment_config_hash,
    evaluate_counterfactual,
    factorial_attribution,
    intent_bucket,
    signal_cache_path,
    summarize_macd_events,
    summarize_macd_events_by_intent,
    validate_four_arm_contexts,
)
from market_regime_alpha.dividend_t.signal_intent import (
    EntryConfirmation,
    ExitConfirmation,
    MACDPolicyConfig,
)


def identity_fixture(**overrides: object) -> MACDExperimentIdentity:
    identity = build_experiment_identity(
        git_commit="03548f0123456789",
        dataset_version="dataset-v1",
        pipeline_id="dividend-t-5m",
        macd_config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
        policy_config=MACDPolicyConfig(),
        execution_config=DividendTBacktestConfig(signal_cache_dir=None),
        sizing_owner="dividend_t_backtest_execution",
    )
    return replace(identity, **overrides)


def test_canonical_identity_contains_required_fields() -> None:
    payload = canonical_experiment_config(identity_fixture())

    required = {
        "git_commit",
        "dataset_version",
        "data_split_hash",
        "pipeline_id",
        "macd_contract_version",
        "macd_algorithm_version",
        "macd_policy_version",
        "technical_score_version",
        "signal_intent_mapping_version",
        "confirmation_rule_version",
        "bar_interval",
        "closed_bars_only",
        "price_field",
        "price_adjustment_mode",
        "histogram_tolerance_mode",
        "fast_period",
        "slow_period",
        "signal_period",
        "cross_lookback_bars",
        "histogram_flat_tolerance",
        "score_weight",
        "conflict_gate_enabled",
        "mean_reversion_size_multiplier",
        "accepted_entry_confirmations",
        "accepted_exit_confirmations",
        "risk_enforcement_version",
        "sizing_owner",
        "execution_config_hash",
    }
    assert required <= set(payload)
    assert payload["accepted_entry_confirmations"] == sorted(payload["accepted_entry_confirmations"])
    assert payload["bar_interval"] == "5m"


@pytest.mark.parametrize(
    "mutation",
    [
        {"git_commit": "different"},
        {"dataset_version": "dataset-v2"},
        {"data_split_hash": "split-v2"},
        {"pipeline_id": "other-pipeline"},
        {"macd_contract_version": "macd-data-v2"},
        {"macd_algorithm_version": "macd-v2"},
        {"macd_policy_version": "policy-v2"},
        {"technical_score_version": "score-v2"},
        {"signal_intent_mapping_version": "intent-v2"},
        {"confirmation_rule_version": "confirm-v2"},
        {"fast_period": 10},
        {"slow_period": 30},
        {"signal_period": 7},
        {"cross_lookback_bars": 4},
        {"histogram_flat_tolerance": 0.001},
        {"score_weight": 0.15},
        {"conflict_gate_enabled": True},
        {"mean_reversion_size_multiplier": 0.25},
        {"accepted_entry_confirmations": frozenset({EntryConfirmation.VWAP_RECLAIM})},
        {"accepted_exit_confirmations": frozenset({ExitConfirmation.VOLUME_STALLING})},
        {"bar_interval": BarInterval.DAY_1},
        {"price_adjustment_mode": "UNADJUSTED"},
        {"histogram_tolerance_mode": "RELATIVE"},
        {"sizing_owner": "other_owner"},
        {"execution_config_hash": "execution-v2"},
    ],
)
def test_every_result_affecting_field_changes_experiment_hash(mutation: dict[str, object]) -> None:
    base = identity_fixture()
    assert experiment_config_hash(replace(base, **mutation)) != experiment_config_hash(base)


def test_set_order_float_none_and_enum_serialization_are_stable() -> None:
    left = identity_fixture(
        accepted_entry_confirmations=frozenset(
            {EntryConfirmation.SUPPORT_HOLD, EntryConfirmation.VWAP_RECLAIM}
        ),
        histogram_flat_tolerance=-0.0,
    )
    right = identity_fixture(
        accepted_entry_confirmations=frozenset(
            {EntryConfirmation.VWAP_RECLAIM, EntryConfirmation.SUPPORT_HOLD}
        ),
        histogram_flat_tolerance=0.0,
    )

    assert experiment_config_hash(left) == experiment_config_hash(right)
    assert canonical_json({"value": None, "mode": HistogramToleranceMode.ABSOLUTE, "number": -0.0}) == (
        '{"mode":"ABSOLUTE","number":0.0,"value":null}'
    )


def test_four_profiles_have_distinct_hashes_and_baseline_stays_disabled() -> None:
    profiles = ablation_profiles()
    hashes = {
        name: experiment_config_hash(
            build_experiment_identity(
                git_commit="03548f0",
                dataset_version="dataset-v1",
                pipeline_id="dividend-t-5m",
                macd_config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
                policy_config=policy,
                execution_config=DividendTBacktestConfig(),
                sizing_owner="dividend_t_backtest_execution",
            )
        )
        for name, policy in profiles.items()
    }

    assert set(profiles) == {"baseline", "score-only", "policy-only", "full"}
    assert len(set(hashes.values())) == 4
    assert profiles["baseline"].score_weight == 0.0
    assert profiles["baseline"].conflict_gate_enabled is False


def test_canonical_cache_path_ignores_profile_label_and_uses_full_hash(tmp_path: Path) -> None:
    identity = identity_fixture()
    first = signal_cache_path(tmp_path, symbol="601919.SH", identity=identity, profile_label="baseline")
    second = signal_cache_path(tmp_path, symbol="601919.SH", identity=identity, profile_label="renamed-label")

    assert first == second
    assert MACD_CACHE_SCHEMA_VERSION in first.parts
    assert experiment_config_hash(identity) in first.name


def test_cache_validates_internal_config_hash(tmp_path: Path) -> None:
    identity = identity_fixture()
    path = signal_cache_path(tmp_path, symbol="601919.SH", identity=identity)
    cache = BacktestSignalCache(path, expected_metadata=cache_metadata(identity))
    cache.set(_minimal_signal())
    cache.save()

    reopened = BacktestSignalCache(path, expected_metadata=cache_metadata(identity))
    assert reopened.get("2026-07-13 10:05:00") is not None

    data = pd.read_csv(path)
    data["_experiment_config_hash"] = "tampered"
    data.to_csv(path, index=False)
    with pytest.raises(ValueError, match="CACHE_CONFIG_HASH_MISMATCH"):
        BacktestSignalCache(path, expected_metadata=cache_metadata(identity))


def test_old_cache_cannot_be_read_as_macd_experiment(tmp_path: Path) -> None:
    identity = identity_fixture()
    path = signal_cache_path(tmp_path, symbol="601919.SH", identity=identity)
    path.parent.mkdir(parents=True)
    pd.DataFrame([_minimal_signal().__dict__]).to_csv(path, index=False)

    with pytest.raises(ValueError, match="CACHE_IDENTITY_MISSING"):
        BacktestSignalCache(path, expected_metadata=cache_metadata(identity))


@pytest.mark.parametrize(
    ("score_changed", "before", "after", "original", "adjusted", "expected"),
    [
        (False, "BUY_T", "BUY_T", 0.20, 0.20, CounterfactualEventType.UNCHANGED),
        (True, None, None, 0.20, 0.20, CounterfactualEventType.SCORE_SUPPRESSED),
        (False, "BUY_T", "HOLD", 0.20, 0.0, CounterfactualEventType.POLICY_DOWNGRADED),
        (False, "BUY_T", "BUY_T", 0.20, 0.10, CounterfactualEventType.POLICY_SIZED),
        (True, "BUY_T", "HOLD", 0.20, 0.0, CounterfactualEventType.SCORE_AND_POLICY_INTERACTION),
    ],
)
def test_counterfactual_event_classifies_score_policy_and_interaction(
    score_changed: bool,
    before: str | None,
    after: str | None,
    original: float,
    adjusted: float,
    expected: CounterfactualEventType,
) -> None:
    event = event_fixture(
        macd_score_changed_candidate=score_changed,
        candidate_before_policy=before,
        candidate_after_policy=after,
        original_suggested_trade_pct=original,
        adjusted_suggested_trade_pct=adjusted,
    )
    assert event.event_type is expected


def test_counterfactual_resolver_receives_raw_next_bar_object() -> None:
    event = event_fixture()
    raw_next_bar = {"open": 10.10, "feature_adjusted_close": 5.05}

    def resolver(_event: CounterfactualEvent, bar: object) -> ExecutionResolution:
        assert isinstance(bar, dict)
        assert bar["open"] == 10.10
        return ExecutionResolution(True, None, "2026-07-13 10:10:00", 10.10, 100, 0.0, 0.25)

    evaluated = evaluate_counterfactual(event, next_bar=raw_next_bar, execution_resolver=resolver)
    assert evaluated.reference_fill_price == 10.10
    assert evaluated.fee_amount == 0.25


def test_metrics_report_net_benefit_and_keep_hard_risk_separate() -> None:
    events = [
        event_fixture(candidate_after_policy="HOLD", counterfactual_net_pnl=-120.0),
        event_fixture(candidate_after_policy="HOLD", counterfactual_net_pnl=45.0),
        event_fixture(candidate_after_policy="HOLD", counterfactual_net_pnl=0.0),
        event_fixture(
            signal_intent="RISK_REDUCTION",
            risk_enforcement="HARD",
            candidate_before_policy="STOP_T",
            candidate_after_policy="STOP_T",
            counterfactual_net_pnl=-300.0,
            max_adverse_excursion=-0.12,
            avoided_tail_loss_amount=300.0,
        ),
    ]

    metrics = summarize_macd_events(
        events,
        baseline_coverage=0.60,
        experiment_coverage=0.50,
        baseline_average_holding_period=8.0,
        experiment_average_holding_period=7.0,
        baseline_max_drawdown=-0.20,
        experiment_max_drawdown=-0.16,
        baseline_turnover=1.20,
        experiment_turnover=0.90,
    )

    assert metrics.avoided_loss_amount == 120.0
    assert metrics.missed_profit_amount == 45.0
    assert metrics.net_block_benefit == 75.0
    assert metrics.effective_block_rate == pytest.approx(1 / 3)
    assert metrics.wrong_block_rate == pytest.approx(1 / 3)
    assert metrics.hard_risk_event_count == 1
    assert metrics.hard_risk_max_adverse_excursion == -0.12
    assert metrics.hard_risk_avoided_loss_amount == 300.0
    assert metrics.coverage_change == pytest.approx(-0.10)
    assert metrics.drawdown_change == pytest.approx(0.04)
    assert metrics.turnover_change == pytest.approx(-0.30)


def test_intent_buckets_separate_buy_sell_and_risk_enforcement() -> None:
    events = [
        event_fixture(signal_intent="MEAN_REVERSION_T", candidate_before_policy="BUY_T"),
        event_fixture(signal_intent="MEAN_REVERSION_T", candidate_before_policy="SELL_T"),
        event_fixture(signal_intent="TREND_FOLLOWING", candidate_before_policy="BUY_T"),
        event_fixture(signal_intent="RISK_REDUCTION", risk_enforcement="HARD", candidate_before_policy="STOP_T"),
        event_fixture(signal_intent="RISK_REDUCTION", risk_enforcement="SOFT", candidate_before_policy="SELL_T"),
        event_fixture(signal_intent="BASE_ACCUMULATION", candidate_before_policy="BUILD_BASE"),
    ]

    assert {intent_bucket(event) for event in events} == {
        "MEAN_REVERSION_T_BUY",
        "MEAN_REVERSION_T_SELL",
        "TREND_FOLLOWING_BUY",
        "RISK_REDUCTION_HARD",
        "RISK_REDUCTION_SOFT",
        "BASE_ACCUMULATION",
    }
    assert set(summarize_macd_events_by_intent(events)) == {intent_bucket(event) for event in events}


def test_factorial_attribution_separates_score_policy_and_interaction() -> None:
    attribution = factorial_attribution(baseline=100.0, score_only=108.0, policy_only=105.0, full=116.0)

    assert attribution.score_effect == 8.0
    assert attribution.policy_effect == 5.0
    assert attribution.interaction_effect == 3.0
    assert attribution.total_effect == 16.0


def test_four_arm_context_requires_same_data_splits_execution_and_seed() -> None:
    contexts = {
        name: AblationArmContext(
            profile=name,
            experiment_config_hash=f"hash-{name}",
            dataset_version="dataset-v1",
            train_range=("2024-01-01", "2024-12-31"),
            validation_range=("2025-01-01", "2025-06-30"),
            test_range=("2025-07-01", "2025-12-31"),
            execution_config_hash="execution-v1",
            random_seed=20260713,
        )
        for name in ("baseline", "score-only", "policy-only", "full")
    }
    validate_four_arm_contexts(contexts)

    changed = dict(contexts)
    changed["full"] = replace(changed["full"], random_seed=7)
    with pytest.raises(ValueError, match="ABLATION_CONTEXT_MISMATCH"):
        validate_four_arm_contexts(changed)


def event_fixture(**overrides: object) -> CounterfactualEvent:
    values: dict[str, object] = {
        "symbol": "601919.SH",
        "candidate_bar_close_time": "2026-07-13 10:05:00",
        "next_eligible_execution_time": "2026-07-13 10:10:00",
        "candidate_without_macd_score": "BUY_T",
        "candidate_with_macd_score": "BUY_T",
        "candidate_before_policy": "BUY_T",
        "candidate_after_policy": "BUY_T",
        "original_suggested_trade_pct": 0.20,
        "adjusted_suggested_trade_pct": 0.20,
        "signal_intent": "MEAN_REVERSION_T",
        "primary_setup_code": "pullback_low_buy",
        "risk_enforcement": "NONE",
        "macd_score": 20.0,
        "macd_cross": "BEARISH",
        "macd_zero_axis": "BELOW",
        "macd_histogram_trend": "EXPANDING",
        "experiment_config_hash": "hash-full",
        "macd_score_changed_candidate": False,
        "macd_policy_changed_candidate": False,
        "executable": True,
        "reference_fill_price": 10.0,
        "counterfactual_net_pnl": None,
    }
    values.update(overrides)
    return CounterfactualEvent.create(**values)


def _minimal_signal() -> BacktestSignal:
    return BacktestSignal(
        timestamp="2026-07-13 10:05:00",
        action="WAIT",
        daily_state="STRONG",
        intraday_state="RANGE",
        trend_state="RANGE",
        market_regime_state="RANGE_T",
        position_multiplier=1.0,
        fundamental_score=70.0,
        base_position_limit_pct=0.10,
        base_position_target_pct=0.10,
        t_trade_limit_pct=0.50,
    )
