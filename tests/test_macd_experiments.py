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
    MACD_CACHE_SCHEMA_VERSION,
    MACDExperimentIdentity,
    ablation_profiles,
    build_experiment_identity,
    cache_metadata,
    canonical_experiment_config,
    canonical_json,
    experiment_config_hash,
    signal_cache_path,
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
