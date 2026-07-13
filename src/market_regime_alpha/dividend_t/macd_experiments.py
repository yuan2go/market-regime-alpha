"""Canonical identities, profiles, and cache metadata for MACD experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from dataclasses import replace
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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
LEGACY_DATA_SPLIT_HASH = "legacy-unspecified-split-v1"


class CounterfactualEventType(str, Enum):
    UNCHANGED = "UNCHANGED"
    SCORE_SUPPRESSED = "SCORE_SUPPRESSED"
    POLICY_DOWNGRADED = "POLICY_DOWNGRADED"
    POLICY_SIZED = "POLICY_SIZED"
    SCORE_AND_POLICY_INTERACTION = "SCORE_AND_POLICY_INTERACTION"


@dataclass(frozen=True)
class ExecutionResolution:
    executable: bool
    block_reason: str | None
    execution_time: str | None
    reference_fill_price: float | None
    shares: int
    slippage_amount: float
    fee_amount: float


@dataclass(frozen=True)
class CounterfactualPathOutcome:
    net_pnl: float
    holding_period_bars: int
    max_adverse_excursion: float


@dataclass(frozen=True)
class CounterfactualEvent:
    symbol: str
    candidate_bar_close_time: str
    next_eligible_execution_time: str
    candidate_without_macd_score: str | None
    candidate_with_macd_score: str | None
    candidate_before_policy: str | None
    candidate_after_policy: str | None
    original_suggested_trade_pct: float
    adjusted_suggested_trade_pct: float
    signal_intent: str
    primary_setup_code: str | None
    risk_enforcement: str
    macd_score: float
    macd_cross: str
    macd_zero_axis: str
    macd_histogram_trend: str
    experiment_config_hash: str
    macd_score_changed_candidate: bool
    macd_policy_changed_candidate: bool
    event_type: CounterfactualEventType
    executable: bool = False
    block_reason: str | None = None
    reference_fill_price: float | None = None
    counterfactual_shares: int = 0
    slippage_amount: float = 0.0
    fee_amount: float = 0.0
    counterfactual_net_pnl: float | None = None
    holding_period_bars: int | None = None
    adjusted_path_executable: bool = False
    adjusted_path_fill_price: float | None = None
    adjusted_path_shares: int = 0
    adjusted_path_slippage_amount: float = 0.0
    adjusted_path_fee_amount: float = 0.0
    adjusted_path_net_pnl: float | None = None
    adjusted_path_holding_period_bars: int | None = None
    adjusted_path_max_adverse_excursion: float | None = None
    original_path_executable: bool = False
    original_path_fill_price: float | None = None
    original_path_shares: int = 0
    original_path_slippage_amount: float = 0.0
    original_path_fee_amount: float = 0.0
    original_path_net_pnl: float | None = None
    original_path_holding_period_bars: int | None = None
    original_path_max_adverse_excursion: float | None = None
    max_adverse_excursion: float | None = None
    avoided_tail_loss_amount: float = 0.0

    @classmethod
    def create(cls, **values: Any) -> "CounterfactualEvent":
        candidate_time = str(values["candidate_bar_close_time"])
        execution_time = str(values["next_eligible_execution_time"])
        if datetime.fromisoformat(execution_time) <= datetime.fromisoformat(candidate_time):
            raise ValueError("COUNTERFACTUAL_EXECUTION_NOT_AFTER_CANDIDATE")
        original = float(values["original_suggested_trade_pct"])
        adjusted = float(values["adjusted_suggested_trade_pct"])
        if any(not math.isfinite(item) or item < 0.0 for item in (original, adjusted)):
            raise ValueError("counterfactual trade percentages must be finite and non-negative")
        config_hash = values.get("experiment_config_hash")
        if not isinstance(config_hash, str) or not config_hash.strip():
            raise ValueError("counterfactual event requires experiment_config_hash")
        macd_score = float(values["macd_score"])
        if not math.isfinite(macd_score) or not 0.0 <= macd_score <= 100.0:
            raise ValueError("counterfactual macd_score must be in [0, 100]")
        policy_changed = values.get("candidate_before_policy") != values.get("candidate_after_policy") or not math.isclose(
            original,
            adjusted,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
        values["macd_policy_changed_candidate"] = bool(values["macd_policy_changed_candidate"]) or policy_changed
        event_type = classify_counterfactual_event(
            score_changed=bool(values["macd_score_changed_candidate"]),
            candidate_before_policy=values.get("candidate_before_policy"),
            candidate_after_policy=values.get("candidate_after_policy"),
            original_suggested_trade_pct=original,
            adjusted_suggested_trade_pct=adjusted,
        )
        return cls(**values, event_type=event_type)

    @property
    def policy_eligible(self) -> bool:
        return self.signal_intent in {"MEAN_REVERSION_T", "TREND_FOLLOWING"} and self.candidate_before_policy not in {
            None,
            "HOLD",
        }

    @property
    def policy_blocked(self) -> bool:
        return self.policy_eligible and self.candidate_after_policy == "HOLD"

    @property
    def policy_resized(self) -> bool:
        return self.policy_eligible and self.candidate_after_policy != "HOLD" and not math.isclose(
            self.original_suggested_trade_pct,
            self.adjusted_suggested_trade_pct,
            rel_tol=0.0,
            abs_tol=1e-15,
        )


@dataclass(frozen=True)
class MACDGateMetrics:
    event_count: int
    score_suppression_rate: float
    policy_block_rate: float
    policy_resize_rate: float
    effective_block_rate: float
    wrong_block_rate: float
    avoided_loss_amount: float
    missed_profit_amount: float
    net_block_benefit: float
    zero_pnl_block_count: int
    coverage_change: float
    average_holding_period_change: float
    drawdown_change: float
    turnover_change: float
    hard_risk_event_count: int
    hard_risk_max_adverse_excursion: float | None
    hard_risk_avoided_loss_amount: float


@dataclass(frozen=True)
class FactorialAttribution:
    baseline: float
    score_only: float
    policy_only: float
    full: float
    score_effect: float
    policy_effect: float
    interaction_effect: float
    total_effect: float


@dataclass(frozen=True)
class AblationArmContext:
    profile: str
    experiment_config_hash: str
    dataset_version: str
    train_range: tuple[str, str]
    validation_range: tuple[str, str]
    test_range: tuple[str, str]
    execution_config_hash: str
    random_seed: int


@dataclass(frozen=True)
class MACDExperimentIdentity:
    git_commit: str
    dataset_version: str
    data_split_hash: str
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
    data_split_hash: str = LEGACY_DATA_SPLIT_HASH,
) -> MACDExperimentIdentity:
    """Build the complete result-affecting identity from validated configs."""

    for name, value in (
        ("git_commit", git_commit),
        ("dataset_version", dataset_version),
        ("pipeline_id", pipeline_id),
        ("sizing_owner", sizing_owner),
        ("data_split_hash", data_split_hash),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty")
    return MACDExperimentIdentity(
        git_commit=git_commit.strip(),
        dataset_version=dataset_version.strip(),
        data_split_hash=data_split_hash.strip(),
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

    if not is_dataclass(config) or isinstance(config, type):
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


def classify_counterfactual_event(
    *,
    score_changed: bool,
    candidate_before_policy: str | None,
    candidate_after_policy: str | None,
    original_suggested_trade_pct: float,
    adjusted_suggested_trade_pct: float,
) -> CounterfactualEventType:
    """Classify the score and policy contributions without conflating the two layers."""

    policy_changed = candidate_before_policy != candidate_after_policy
    sizing_changed = not math.isclose(
        original_suggested_trade_pct,
        adjusted_suggested_trade_pct,
        rel_tol=0.0,
        abs_tol=1e-15,
    )
    if score_changed and (policy_changed or sizing_changed):
        return CounterfactualEventType.SCORE_AND_POLICY_INTERACTION
    if score_changed:
        return CounterfactualEventType.SCORE_SUPPRESSED
    if policy_changed and candidate_after_policy == "HOLD":
        return CounterfactualEventType.POLICY_DOWNGRADED
    if sizing_changed:
        return CounterfactualEventType.POLICY_SIZED
    return CounterfactualEventType.UNCHANGED


def evaluate_counterfactual(
    event: CounterfactualEvent,
    *,
    next_bar: object,
    execution_resolver: Callable[[CounterfactualEvent, object], ExecutionResolution],
) -> CounterfactualEvent:
    """Resolve a counterfactual on the raw next eligible bar, never on candidate-bar extrema."""

    resolution = execution_resolver(event, next_bar)
    if resolution.execution_time is not None:
        execution_time = datetime.fromisoformat(resolution.execution_time)
        candidate_time = datetime.fromisoformat(event.candidate_bar_close_time)
        eligible_time = datetime.fromisoformat(event.next_eligible_execution_time)
        if execution_time <= candidate_time or execution_time < eligible_time:
            raise ValueError("COUNTERFACTUAL_EXECUTION_TIME_INVALID")
    return replace(
        event,
        executable=resolution.executable,
        block_reason=resolution.block_reason,
        reference_fill_price=resolution.reference_fill_price,
        counterfactual_shares=resolution.shares,
        slippage_amount=resolution.slippage_amount,
        fee_amount=resolution.fee_amount,
    )


def summarize_macd_events(
    events: Sequence[CounterfactualEvent],
    *,
    baseline_coverage: float = 0.0,
    experiment_coverage: float = 0.0,
    baseline_average_holding_period: float = 0.0,
    experiment_average_holding_period: float = 0.0,
    baseline_max_drawdown: float = 0.0,
    experiment_max_drawdown: float = 0.0,
    baseline_turnover: float = 0.0,
    experiment_turnover: float = 0.0,
) -> MACDGateMetrics:
    """Aggregate ordinary policy outcomes and hard-risk diagnostics separately."""

    hard_risk = [event for event in events if event.risk_enforcement == "HARD"]
    ordinary = [event for event in events if event.risk_enforcement != "HARD"]
    score_suppressed = [
        event
        for event in ordinary
        if event.macd_score_changed_candidate
        and event.event_type
        in {CounterfactualEventType.SCORE_SUPPRESSED, CounterfactualEventType.SCORE_AND_POLICY_INTERACTION}
    ]
    policy_eligible = [event for event in ordinary if event.policy_eligible]
    policy_blocked = [event for event in policy_eligible if event.policy_blocked]
    policy_resized = [event for event in policy_eligible if event.policy_resized]
    evaluated_blocks = [
        event for event in policy_blocked if event.executable and event.counterfactual_net_pnl is not None
    ]
    evaluated_pnls = [
        float(event.counterfactual_net_pnl)
        for event in evaluated_blocks
        if event.counterfactual_net_pnl is not None
    ]
    avoided_loss = sum(-pnl for pnl in evaluated_pnls if pnl < 0)
    missed_profit = sum(pnl for pnl in evaluated_pnls if pnl > 0)
    zero_pnl = sum(pnl == 0 for pnl in evaluated_pnls)
    adverse = [event.max_adverse_excursion for event in hard_risk if event.max_adverse_excursion is not None]
    return MACDGateMetrics(
        event_count=len(events),
        score_suppression_rate=_rate(len(score_suppressed), len(ordinary)),
        policy_block_rate=_rate(len(policy_blocked), len(policy_eligible)),
        policy_resize_rate=_rate(len(policy_resized), len(policy_eligible)),
        effective_block_rate=_rate(
            sum(pnl < 0 for pnl in evaluated_pnls), len(evaluated_pnls)
        ),
        wrong_block_rate=_rate(
            sum(pnl > 0 for pnl in evaluated_pnls), len(evaluated_pnls)
        ),
        avoided_loss_amount=avoided_loss,
        missed_profit_amount=missed_profit,
        net_block_benefit=avoided_loss - missed_profit,
        zero_pnl_block_count=zero_pnl,
        coverage_change=experiment_coverage - baseline_coverage,
        average_holding_period_change=experiment_average_holding_period - baseline_average_holding_period,
        drawdown_change=experiment_max_drawdown - baseline_max_drawdown,
        turnover_change=experiment_turnover - baseline_turnover,
        hard_risk_event_count=len(hard_risk),
        hard_risk_max_adverse_excursion=min(adverse) if adverse else None,
        hard_risk_avoided_loss_amount=sum(event.avoided_tail_loss_amount for event in hard_risk),
    )


def intent_bucket(event: CounterfactualEvent) -> str:
    """Return stable research strata without applying ordinary hit-rate semantics to hard risk."""

    if event.signal_intent == "MEAN_REVERSION_T":
        side = "SELL" if event.candidate_before_policy == "SELL_T" else "BUY"
        return f"MEAN_REVERSION_T_{side}"
    if event.signal_intent == "TREND_FOLLOWING":
        side = "SELL" if event.candidate_before_policy == "SELL_T" else "BUY"
        return f"TREND_FOLLOWING_{side}"
    if event.signal_intent == "RISK_REDUCTION":
        return f"RISK_REDUCTION_{event.risk_enforcement}"
    if event.signal_intent == "BASE_ACCUMULATION":
        return "BASE_ACCUMULATION"
    return event.signal_intent


def summarize_macd_events_by_intent(
    events: Sequence[CounterfactualEvent],
) -> dict[str, MACDGateMetrics]:
    grouped: dict[str, list[CounterfactualEvent]] = {}
    for event in events:
        grouped.setdefault(intent_bucket(event), []).append(event)
    return {bucket: summarize_macd_events(items) for bucket, items in sorted(grouped.items())}


def factorial_attribution(
    *, baseline: float, score_only: float, policy_only: float, full: float
) -> FactorialAttribution:
    """Compute the 2x2 score, policy, and score-policy interaction effects."""

    score_effect = score_only - baseline
    policy_effect = policy_only - baseline
    interaction_effect = full - score_only - policy_only + baseline
    return FactorialAttribution(
        baseline=baseline,
        score_only=score_only,
        policy_only=policy_only,
        full=full,
        score_effect=score_effect,
        policy_effect=policy_effect,
        interaction_effect=interaction_effect,
        total_effect=full - baseline,
    )


def validate_four_arm_contexts(contexts: Mapping[str, AblationArmContext]) -> None:
    """Guarantee that only MACD score/policy configuration differs between ablation arms."""

    expected = set(MACD_PROFILE_NAMES)
    if set(contexts) != expected:
        raise ValueError("ABLATION_PROFILES_INCOMPLETE")
    hashes = [contexts[name].experiment_config_hash for name in MACD_PROFILE_NAMES]
    if len(set(hashes)) != len(hashes):
        raise ValueError("ABLATION_CONFIG_HASH_NOT_UNIQUE")
    reference = contexts["baseline"]
    shared_fields = (
        "dataset_version",
        "train_range",
        "validation_range",
        "test_range",
        "execution_config_hash",
        "random_seed",
    )
    for name in MACD_PROFILE_NAMES[1:]:
        candidate = contexts[name]
        mismatches = [field for field in shared_fields if getattr(candidate, field) != getattr(reference, field)]
        if mismatches:
            raise ValueError(f"ABLATION_CONTEXT_MISMATCH: {name}: {','.join(mismatches)}")


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


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
