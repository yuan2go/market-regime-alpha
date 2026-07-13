"""Canonical identities, profiles, and cache metadata for MACD experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from market_regime_alpha.dividend_t.macd import (
    BAR_CONTRACT_VERSION,
    DATA_QUALITY_RULE_VERSION,
    MACD_ALGORITHM_VERSION,
    MACD_CONTRACT_VERSION,
    PRICE_ADJUSTMENT_VERSION,
    BarInterval,
    HistogramToleranceMode,
    MACDConfig,
    MACDPriceField,
    MACDZeroAxis,
    PriceAdjustmentMode,
)
from market_regime_alpha.dividend_t.scoring import TECHNICAL_SCORE_VERSION
from market_regime_alpha.dividend_t.signal_intent import (
    CONFIRMATION_RULE_VERSION,
    MACD_POLICY_VERSION,
    SIGNAL_INTENT_MAPPING_VERSION,
    EntryConfirmation,
    ExitConfirmation,
    MACDPolicyConfig,
)


MACD_CACHE_SCHEMA_VERSION = "macd-signal-cache-v2"
RISK_ENFORCEMENT_VERSION = "risk-enforcement-v1"
MACD_PROFILE_NAMES = ("baseline", "score-only", "policy-only", "full")
LEGACY_CACHE_COMPATIBILITY_MODE = "legacy-baseline-only"


@dataclass(frozen=True)
class MACDExperimentIdentity:
    git_commit: str
    dataset_version: str
    pipeline_id: str
    macd_contract_version: str
    macd_algorithm_version: str
    macd_policy_version: str
    technical_score_version: str
    signal_intent_mapping_version: str
    confirmation_rule_version: str
    bar_contract_version: str
    price_adjustment_version: str
    data_quality_rule_version: str
    risk_enforcement_version: str
    sizing_owner: str
    execution_config_hash: str
    bar_interval: BarInterval
    closed_bars_only: bool
    price_field: MACDPriceField
    price_adjustment_mode: PriceAdjustmentMode
    histogram_tolerance_mode: HistogramToleranceMode
    fast_period: int
    slow_period: int
    signal_period: int
    cross_lookback_bars: int
    histogram_flat_tolerance: float
    score_weight: float
    conflict_gate_enabled: bool
    mean_reversion_size_multiplier: float
    minimum_executable_trade_pct: float
    trend_buy_block_bearish_cross: bool
    trend_buy_block_zero_axis_states: frozenset[MACDZeroAxis]
    accepted_entry_confirmations: frozenset[EntryConfirmation]
    accepted_exit_confirmations: frozenset[ExitConfirmation]


def build_experiment_identity(
    *,
    git_commit: str,
    dataset_version: str,
    pipeline_id: str,
    macd_config: MACDConfig,
    policy_config: MACDPolicyConfig,
    execution_config: Any,
    sizing_owner: str,
) -> MACDExperimentIdentity:
    """Build the complete result-affecting identity from validated configs."""

    for name, value in (
        ("git_commit", git_commit),
        ("dataset_version", dataset_version),
        ("pipeline_id", pipeline_id),
        ("sizing_owner", sizing_owner),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty")
    return MACDExperimentIdentity(
        git_commit=git_commit.strip(),
        dataset_version=dataset_version.strip(),
        pipeline_id=pipeline_id.strip(),
        macd_contract_version=MACD_CONTRACT_VERSION,
        macd_algorithm_version=macd_config.algorithm_version or MACD_ALGORITHM_VERSION,
        macd_policy_version=policy_config.policy_version or MACD_POLICY_VERSION,
        technical_score_version=TECHNICAL_SCORE_VERSION,
        signal_intent_mapping_version=SIGNAL_INTENT_MAPPING_VERSION,
        confirmation_rule_version=effective_confirmation_rule_version(
            CONFIRMATION_RULE_VERSION,
            policy_config.mean_reversion_buy_accepted_confirmations,
            policy_config.mean_reversion_sell_accepted_confirmations,
        ),
        bar_contract_version=BAR_CONTRACT_VERSION,
        price_adjustment_version=PRICE_ADJUSTMENT_VERSION,
        data_quality_rule_version=DATA_QUALITY_RULE_VERSION,
        risk_enforcement_version=RISK_ENFORCEMENT_VERSION,
        sizing_owner=sizing_owner.strip(),
        execution_config_hash=execution_config_hash(execution_config),
        bar_interval=macd_config.bar_interval,
        closed_bars_only=macd_config.closed_bars_only,
        price_field=macd_config.price_field,
        price_adjustment_mode=macd_config.price_adjustment_mode,
        histogram_tolerance_mode=macd_config.histogram_tolerance_mode,
        fast_period=macd_config.fast_period,
        slow_period=macd_config.slow_period,
        signal_period=macd_config.signal_period,
        cross_lookback_bars=macd_config.cross_lookback_bars,
        histogram_flat_tolerance=float(macd_config.histogram_flat_tolerance),
        score_weight=float(policy_config.score_weight),
        conflict_gate_enabled=policy_config.conflict_gate_enabled,
        mean_reversion_size_multiplier=float(policy_config.mean_reversion_size_multiplier),
        minimum_executable_trade_pct=float(policy_config.minimum_executable_trade_pct),
        trend_buy_block_bearish_cross=policy_config.trend_buy_block_bearish_cross,
        trend_buy_block_zero_axis_states=policy_config.trend_buy_block_zero_axis_states,
        accepted_entry_confirmations=policy_config.mean_reversion_buy_accepted_confirmations,
        accepted_exit_confirmations=policy_config.mean_reversion_sell_accepted_confirmations,
    )


def canonical_experiment_config(identity: MACDExperimentIdentity) -> dict[str, object]:
    """Return the canonical identity payload without any display-only profile label."""

    return _canonical_value(asdict(identity))


def canonical_json(payload: Mapping[str, object]) -> str:
    """Serialize canonical JSON with stable enum, collection, float, and None rules."""

    normalized = _canonical_value(dict(payload))
    return json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def experiment_config_hash(identity: MACDExperimentIdentity) -> str:
    """Return the full SHA-256 of the canonical experiment identity."""

    payload = canonical_experiment_config(identity)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def execution_config_hash(config: Any) -> str:
    """Hash all execution semantics while excluding cache location/flush controls."""

    if not is_dataclass(config):
        raise TypeError("execution config must be a dataclass instance")
    payload = asdict(config)
    for non_semantic in ("signal_cache_dir", "signal_cache_save_every", "signal_cache_tag"):
        payload.pop(non_semantic, None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def effective_confirmation_rule_version(
    base_version: str,
    entries: frozenset[EntryConfirmation],
    exits: frozenset[ExitConfirmation],
) -> str:
    accepted = {
        "entries": sorted(item.value for item in entries),
        "exits": sorted(item.value for item in exits),
        "validity": "current-decision-bar-only",
    }
    suffix = hashlib.sha256(canonical_json(accepted).encode("utf-8")).hexdigest()[:12]
    return f"{base_version}+{suffix}"


def ablation_profiles() -> dict[str, MACDPolicyConfig]:
    """Return the fixed 2x2 score/policy experiment arms."""

    return {
        "baseline": MACDPolicyConfig(score_weight=0.0, conflict_gate_enabled=False),
        "score-only": MACDPolicyConfig(score_weight=0.15, conflict_gate_enabled=False),
        "policy-only": MACDPolicyConfig(score_weight=0.0, conflict_gate_enabled=True),
        "full": MACDPolicyConfig(score_weight=0.15, conflict_gate_enabled=True),
    }


def macd_policy_config_for_profile(profile: str) -> MACDPolicyConfig:
    try:
        return ablation_profiles()[profile]
    except KeyError as exc:
        raise ValueError(f"unknown MACD profile: {profile}") from exc


def signal_cache_path(
    root: Path,
    *,
    symbol: str,
    identity: MACDExperimentIdentity,
    profile_label: str | None = None,
) -> Path:
    """Build a content-addressed cache path; profile_label is intentionally ignored."""

    del profile_label
    safe_symbol = _safe_path_part(symbol.replace(".", "_"))
    return (
        Path(root)
        / MACD_CACHE_SCHEMA_VERSION
        / _safe_path_part(identity.dataset_version)
        / _safe_path_part(identity.pipeline_id)
        / identity.bar_interval.value
        / f"{safe_symbol}-{experiment_config_hash(identity)}.csv"
    )


def cache_metadata(identity: MACDExperimentIdentity) -> dict[str, str]:
    return {
        "_cache_schema_version": MACD_CACHE_SCHEMA_VERSION,
        "_experiment_config_hash": experiment_config_hash(identity),
        "_git_commit": identity.git_commit,
        "_dataset_version": identity.dataset_version,
        "_pipeline_id": identity.pipeline_id,
        "_sizing_owner": identity.sizing_owner,
    }


def validate_runtime_identity(
    identity: MACDExperimentIdentity,
    *,
    policy_config: MACDPolicyConfig,
    execution_config: Any,
    expected_pipeline_id: str,
    expected_sizing_owner: str,
) -> None:
    """Prevent a display profile or stale identity from describing different runtime semantics."""

    expected = {
        "pipeline_id": expected_pipeline_id,
        "sizing_owner": expected_sizing_owner,
        "execution_config_hash": execution_config_hash(execution_config),
        "score_weight": float(policy_config.score_weight),
        "conflict_gate_enabled": policy_config.conflict_gate_enabled,
        "mean_reversion_size_multiplier": float(policy_config.mean_reversion_size_multiplier),
        "minimum_executable_trade_pct": float(policy_config.minimum_executable_trade_pct),
        "accepted_entry_confirmations": policy_config.mean_reversion_buy_accepted_confirmations,
        "accepted_exit_confirmations": policy_config.mean_reversion_sell_accepted_confirmations,
    }
    mismatches = [name for name, value in expected.items() if getattr(identity, name) != value]
    if mismatches:
        raise ValueError(f"EXPERIMENT_IDENTITY_RUNTIME_MISMATCH: {','.join(sorted(mismatches))}")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON rejects non-finite floats")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(normalized, key=lambda item: canonical_json({"value": item}))
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _safe_path_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip())
    if not cleaned:
        raise ValueError("cache path identity parts must be non-empty")
    return cleaned
