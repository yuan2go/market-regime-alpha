"""Locked evaluation/OOS protocol and fail-closed execution runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from math import sqrt
from random import Random
from statistics import fmean, pstdev
from typing import Any, Callable, cast

from market_regime_alpha.application.research_evaluation.targets import OutcomeTargetProtocol
from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import FormalPITEvidenceArtifact
from market_regime_alpha.data.pit_contracts import PITValidationOutcome
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text


class EvaluationPartition(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    LOCKED_OOS = "LOCKED_OOS"


class MultipleTestingMethod(str, Enum):
    BONFERRONI = "BONFERRONI"
    BENJAMINI_HOCHBERG = "BENJAMINI_HOCHBERG"


class EvaluationMetricStatus(str, Enum):
    ESTIMATED = "ESTIMATED"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class EvaluationWindow:
    window_id: str
    partition: EvaluationPartition
    start_date: date
    end_date: date
    fold: int

    def __post_init__(self) -> None:
        require_text("window_id", self.window_id)
        if self.start_date > self.end_date or self.fold <= 0:
            raise ValueError("Evaluation window is invalid")


@dataclass(frozen=True, slots=True)
class FormalEvaluationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    target_protocol_reference: ValidationArtifactReference
    windows: tuple[EvaluationWindow, ...]
    embargo_sessions: int
    purge_overlapping_labels: bool
    bootstrap_iterations: int
    bootstrap_block_sessions: int
    confidence_level: Decimal
    multiple_testing_method: MultipleTestingMethod
    hypothesis_family_id: str
    top_k: int
    sensitivity_return_multipliers: tuple[Decimal, ...]
    locked_at: datetime

    def __post_init__(self) -> None:
        require_sha256("protocol_hash", self.protocol_hash)
        require_text("protocol_version", self.protocol_version)
        if self.protocol_id != ArtifactId(
            f"formal-evaluation-protocol:{self.protocol_hash[7:]}"
        ):
            raise ValueError("Formal Evaluation Protocol identity mismatch")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Formal Evaluation Protocol lock time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.protocol_hash:
            raise ValueError("Formal Evaluation Protocol hash mismatch")

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        target_protocol: OutcomeTargetProtocol,
        windows: tuple[EvaluationWindow, ...],
        bootstrap_iterations: int,
        bootstrap_block_sessions: int = 1,
        confidence_level: Decimal,
        multiple_testing_method: MultipleTestingMethod,
        hypothesis_family_id: str | None = None,
        top_k: int = 5,
        locked_at: datetime,
        sensitivity_return_multipliers: tuple[Decimal, ...] = (
            Decimal("0.9"),
            Decimal("1"),
            Decimal("1.1"),
        ),
    ) -> FormalEvaluationProtocol:
        ordered = tuple(sorted(windows, key=lambda item: (item.fold, item.partition.value, item.start_date)))
        if not ordered or len({item.window_id for item in ordered}) != len(ordered):
            raise ValueError("Formal Evaluation windows must be non-empty and unique")
        if (
            not Decimal("0") < confidence_level < Decimal("1")
            or bootstrap_iterations <= 0
            or bootstrap_block_sessions <= 0
            or top_k <= 0
        ):
            raise ValueError("Formal Evaluation statistics configuration is invalid")
        family_id = hypothesis_family_id or f"ENGINEERING:{protocol_version}"
        require_text("hypothesis_family_id", family_id)
        sensitivity = tuple(sorted(set(sensitivity_return_multipliers)))
        if not sensitivity or any(value <= 0 for value in sensitivity) or Decimal("1") not in sensitivity:
            raise ValueError("Formal Evaluation sensitivity requires positive multipliers including baseline 1")
        _validate_fold_windows(ordered)
        embargo = derive_embargo_sessions(target_protocol)
        target_ref = ValidationArtifactReference("OUTCOME_TARGET_PROTOCOL", target_protocol.protocol_id, target_protocol.protocol_hash)
        values = _protocol_payload(
            protocol_version,
            target_ref,
            ordered,
            embargo,
            bootstrap_iterations,
            bootstrap_block_sessions,
            confidence_level,
            multiple_testing_method,
            family_id,
            top_k,
            sensitivity,
            locked_at,
        )
        artifact_id, digest = content_identity("formal-evaluation-protocol", values)
        return cls(
            artifact_id,
            digest,
            protocol_version,
            target_ref,
            ordered,
            embargo,
            True,
            bootstrap_iterations,
            bootstrap_block_sessions,
            confidence_level,
            multiple_testing_method,
            family_id,
            top_k,
            sensitivity,
            locked_at,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _protocol_payload(
            self.protocol_version,
            self.target_protocol_reference,
            self.windows,
            self.embargo_sessions,
            self.bootstrap_iterations,
            self.bootstrap_block_sessions,
            self.confidence_level,
            self.multiple_testing_method,
            self.hypothesis_family_id,
            self.top_k,
            self.sensitivity_return_multipliers,
            self.locked_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": str(self.protocol_id),
            "protocol_hash": self.protocol_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: dict[str, Any]
    ) -> FormalEvaluationProtocol:
        windows_value = value["windows"]
        sensitivity_value = value["sensitivity_return_multipliers"]
        if not isinstance(windows_value, list) or not isinstance(
            sensitivity_value, list
        ):
            raise ValueError("Formal Evaluation Protocol payload arrays are invalid")
        protocol = cls(
            protocol_id=ArtifactId(str(value["protocol_id"])),
            protocol_hash=str(value["protocol_hash"]),
            protocol_version=str(value["protocol_version"]),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping_value(value["target_protocol_reference"])
            ),
            windows=tuple(
                EvaluationWindow(
                    window_id=str(_mapping_value(item)["window_id"]),
                    partition=EvaluationPartition(
                        str(_mapping_value(item)["partition"])
                    ),
                    start_date=date.fromisoformat(
                        str(_mapping_value(item)["start_date"])
                    ),
                    end_date=date.fromisoformat(
                        str(_mapping_value(item)["end_date"])
                    ),
                    fold=int(_mapping_value(item)["fold"]),
                )
                for item in windows_value
            ),
            embargo_sessions=int(value["embargo_sessions"]),
            purge_overlapping_labels=bool(value["purge_overlapping_labels"]),
            bootstrap_iterations=int(value["bootstrap_iterations"]),
            bootstrap_block_sessions=int(value["bootstrap_block_sessions"]),
            confidence_level=Decimal(str(value["confidence_level"])),
            multiple_testing_method=MultipleTestingMethod(
                str(value["multiple_testing_method"])
            ),
            hypothesis_family_id=str(value["hypothesis_family_id"]),
            top_k=int(value["top_k"]),
            sensitivity_return_multipliers=tuple(
                Decimal(str(item)) for item in sensitivity_value
            ),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
        )
        if value.get("schema") != "formal-evaluation-protocol/v2":
            raise ValueError("unsupported Formal Evaluation Protocol schema")
        if value.get("bootstrap_method") != "TRADING_DATE_MOVING_BLOCK":
            raise ValueError("Formal Evaluation bootstrap method drift")
        return protocol


def derive_embargo_sessions(target_protocol: OutcomeTargetProtocol) -> int:
    """Derive embargo from the existing Target label interval, never a literal."""
    if not target_protocol.targets:
        raise ValueError("Target Protocol requires targets")
    # Every current target begins at frozen DecisionTime and ends at the
    # protocol's future session offset.  The entire label interval is embargoed.
    return target_protocol.session_offset


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    observation_id: str
    session_date: date
    label_end_date: date
    symbol: str
    score: Decimal
    realized_return: Decimal
    mfe: Decimal | None
    mae: Decimal | None
    regime: str
    liquidity_slice: str
    market_cap_slice: str
    theme_slice: str

    def __post_init__(self) -> None:
        require_text("observation_id", self.observation_id)
        require_text("symbol", self.symbol)
        if self.label_end_date < self.session_date:
            raise ValueError("Evaluation label cannot end before its session")


@dataclass(frozen=True, slots=True)
class EvaluationMetric:
    fold: int
    partition: EvaluationPartition
    sensitivity_return_multiplier: Decimal
    metric_name: str
    slice_kind: str
    slice_value: str
    sample_count: int
    status: EvaluationMetricStatus
    estimate: Decimal | None
    confidence_low: Decimal | None
    confidence_high: Decimal | None
    raw_p_value: Decimal | None
    adjusted_p_value: Decimal | None
    hypothesis_family_id: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text("metric_name", self.metric_name)
        require_text("hypothesis_family_id", self.hypothesis_family_id)
        values = (
            self.estimate,
            self.confidence_low,
            self.confidence_high,
            self.raw_p_value,
            self.adjusted_p_value,
        )
        if self.status is EvaluationMetricStatus.ESTIMATED:
            if any(value is None for value in values) or self.reason_codes:
                raise ValueError("estimated Evaluation metric requires complete statistics")
        elif any(value is not None for value in values) or not self.reason_codes:
            raise ValueError("NOT_ESTIMABLE metric requires reasons and no statistics")


@dataclass(frozen=True, slots=True)
class FormalEvaluationResult:
    result_id: ArtifactId
    result_hash: str
    protocol_reference: ValidationArtifactReference
    pit_evidence_reference: ValidationArtifactReference | None
    panel_reference: ValidationArtifactReference
    panel_source_references: tuple[ValidationArtifactReference, ...]
    metrics: tuple[EvaluationMetric, ...]
    excluded_observation_ids: tuple[str, ...]
    authority: ResearchEvidenceAuthority
    formal_oos: bool
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "formal-evaluation-result/v2"

    def __post_init__(self) -> None:
        require_sha256("result_hash", self.result_hash)
        if self.formal_oos != (self.authority is ResearchEvidenceAuthority.FORMAL_OOS):
            raise ValueError("Formal OOS flag and evidence authority mismatch")
        if self.formal_oos and self.pit_evidence_reference is None:
            raise ValueError("Formal OOS result requires Formal PIT evidence")
        if self.panel_source_references != tuple(
            sorted(
                set(self.panel_source_references),
                key=lambda item: (item.artifact_kind, str(item.artifact_id), item.content_hash),
            )
        ):
            raise ValueError("Formal Evaluation Panel lineage must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Formal Evaluation result hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _result_payload(
            self.protocol_reference,
            self.pit_evidence_reference,
            self.panel_reference,
            self.panel_source_references,
            self.metrics,
            self.excluded_observation_ids,
            self.authority,
            self.formal_oos,
            self.reason_codes,
            self.created_at,
            self.limitations,
        )


MetricFunction = Callable[[tuple[EvaluationObservation, ...]], Decimal | None]


def run_formal_evaluation(
    *,
    protocol: FormalEvaluationProtocol,
    panel_reference: ValidationArtifactReference,
    observations: tuple[EvaluationObservation, ...],
    formal_pit_evidence: FormalPITEvidenceArtifact | None,
    created_at: datetime,
    panel_source_references: tuple[ValidationArtifactReference, ...] = (),
    frozen_trading_dates: tuple[date, ...] = (),
) -> FormalEvaluationResult:
    if not observations:
        raise ValueError("Evaluation Runtime requires observations")
    ids = tuple(item.observation_id for item in observations)
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation observations must be unique")
    admitted, excluded = _admit_observations(
        protocol,
        observations,
        frozen_trading_dates=frozen_trading_dates,
    )
    if not admitted:
        raise ValueError("purging and Embargo removed every Evaluation observation")
    formal_pit_rejections = _formal_pit_rejections(
        protocol=protocol,
        evidence=formal_pit_evidence,
        panel_source_references=panel_source_references,
        evaluated_at=created_at,
    )
    real_formal_pit_candidate = not formal_pit_rejections
    locked_oos_present = any(window.partition is EvaluationPartition.LOCKED_OOS for _item, window in admitted)
    # This pure research harness cannot reload PostgreSQL owners or issue a
    # Formal OOS qualification decision.  Migration 046 enforces the same
    # artifact ceiling; the separate owner-resolving writer performs the gate.
    formal = False
    authority = ResearchEvidenceAuthority.ENGINEERING_ONLY
    pit_ref = (
        None
        if formal_pit_evidence is None
        else ValidationArtifactReference("FORMAL_PIT_EVIDENCE", formal_pit_evidence.evidence_id, formal_pit_evidence.evidence_hash)
    )
    ordered_panel_sources = tuple(
        sorted(
            set(panel_source_references),
            key=lambda item: (item.artifact_kind, str(item.artifact_id), item.content_hash),
        )
    )
    metric_specs: tuple[tuple[str, MetricFunction], ...] = (
        ("IC", _ic),
        ("RANK_IC", _rank_ic),
        ("ICIR", _icir),
        ("POSITIVE_IC_RATIO", _positive_ic_ratio),
        ("TOP_K_RETURN", lambda values: _top_k_return(values, protocol.top_k)),
        ("SPREAD", lambda values: _spread(values, protocol.top_k)),
        ("HIT_RATE", lambda values: _hit_rate(values, protocol.top_k)),
        ("RETURN", _return),
        ("MFE", _mfe),
        ("MAE", _mae),
        ("TURNOVER", lambda values: _turnover(values, protocol.top_k)),
        ("DRAWDOWN", lambda values: _drawdown(values, protocol.top_k)),
        (
            "INCREMENTAL_LIFT",
            lambda values: _incremental_lift(values, protocol.top_k),
        ),
    )
    raw: list[
        tuple[
            int,
            EvaluationPartition,
            Decimal,
            str,
            str,
            str,
            int,
            EvaluationMetricStatus,
            Decimal | None,
            Decimal | None,
            Decimal | None,
            Decimal | None,
            Decimal | None,
            str,
            tuple[str, ...],
        ]
    ] = []
    fold_partitions = sorted(
        {(window.fold, window.partition) for _observation, window in admitted},
        key=lambda item: (item[0], item[1].value),
    )
    for fold, partition in fold_partitions:
        partition_values = tuple(observation for observation, window in admitted if window.fold == fold and window.partition is partition)
        for multiplier in protocol.sensitivity_return_multipliers:
            sensitivity_values = tuple(_apply_return_sensitivity(item, multiplier) for item in partition_values)
            for slice_kind, groups in _slices(sensitivity_values).items():
                for slice_value, values in groups.items():
                    for metric_name, function in metric_specs:
                        available = _metric_available(metric_name, values)
                        estimate = function(available)
                        if estimate is None:
                            raw.append(
                                (
                                    fold,
                                    partition,
                                    multiplier,
                                    metric_name,
                                    slice_kind,
                                    slice_value,
                                    len(available),
                                    EvaluationMetricStatus.NOT_ESTIMABLE,
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    protocol.hypothesis_family_id,
                                    (_not_estimable_reason(metric_name),),
                                )
                            )
                            continue
                        low, high, p_value = _bootstrap(
                            function,
                            available,
                            protocol.bootstrap_iterations,
                            protocol.confidence_level,
                            block_sessions=protocol.bootstrap_block_sessions,
                            seed=f"{fold}:{partition.value}:{multiplier}:{slice_kind}:{slice_value}:{metric_name}",
                        )
                        raw.append(
                            (
                                fold,
                                partition,
                                multiplier,
                                metric_name,
                                slice_kind,
                                slice_value,
                                len(available),
                                EvaluationMetricStatus.ESTIMATED,
                                estimate,
                                low,
                                high,
                                p_value,
                                None,
                                protocol.hypothesis_family_id,
                                (),
                            )
                        )
    estimable_indices = [
        index
        for index, item in enumerate(raw)
        if item[7] is EvaluationMetricStatus.ESTIMATED
    ]
    adjusted = _adjust_p_values(
        [cast(Decimal, raw[index][11]) for index in estimable_indices],
        protocol.multiple_testing_method,
    )
    for index, adjusted_value in zip(estimable_indices, adjusted, strict=True):
        raw[index] = (*raw[index][:12], adjusted_value, *raw[index][13:])
    metrics = tuple(EvaluationMetric(*item) for item in raw)
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    reason_set = {
        "FORMAL_OOS_BLOCKED",
        "FORMAL_OOS_OWNER_QUALIFICATION_REQUIRED",
    }
    if not real_formal_pit_candidate:
        reason_set.update(formal_pit_rejections)
    if not locked_oos_present:
        reason_set.add("LOCKED_OOS_OBSERVATIONS_REQUIRED")
    reasons = tuple(sorted(reason_set))
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "FORMAL_OOS_FALSE"}))
    protocol_ref = ValidationArtifactReference("FORMAL_EVALUATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    payload = _result_payload(
        protocol_ref,
        pit_ref,
        panel_reference,
        ordered_panel_sources,
        metrics,
        tuple(sorted(excluded)),
        authority,
        formal,
        reasons,
        created_at,
        limitations,
    )
    result_id, digest = content_identity("formal-evaluation-result", payload)
    return FormalEvaluationResult(
        result_id,
        digest,
        protocol_ref,
        pit_ref,
        panel_reference,
        ordered_panel_sources,
        metrics,
        tuple(sorted(excluded)),
        authority,
        formal,
        reasons,
        created_at,
        limitations,
    )


def _admit_observations(
    protocol: FormalEvaluationProtocol,
    observations: tuple[EvaluationObservation, ...],
    *,
    frozen_trading_dates: tuple[date, ...] = (),
) -> tuple[tuple[tuple[EvaluationObservation, EvaluationWindow], ...], set[str]]:
    if frozen_trading_dates and frozen_trading_dates != tuple(
        sorted(set(frozen_trading_dates))
    ):
        raise ValueError("Frozen Trading Calendar dates must be unique and sorted")
    frozen_set = set(frozen_trading_dates)
    if frozen_trading_dates and any(
        window.start_date not in frozen_set or window.end_date not in frozen_set
        for window in protocol.windows
    ):
        raise ValueError("Evaluation windows are outside the Frozen Trading Calendar")
    if frozen_trading_dates and any(
        item.session_date not in frozen_set or item.label_end_date not in frozen_set
        for item in observations
    ):
        raise ValueError("Evaluation label interval is outside the Frozen Trading Calendar")
    admitted: list[tuple[EvaluationObservation, EvaluationWindow]] = []
    excluded: set[str] = set()
    for observation in observations:
        windows = [item for item in protocol.windows if item.start_date <= observation.session_date <= item.end_date]
        if not windows:
            excluded.add(observation.observation_id)
            continue
        observation_admitted = False
        for window in windows:
            partition_order = {
                EvaluationPartition.TRAIN: 0,
                EvaluationPartition.VALIDATION: 1,
                EvaluationPartition.LOCKED_OOS: 2,
            }
            future_windows = [
                item
                for item in protocol.windows
                if item.fold == window.fold
                and partition_order[item.partition] == partition_order[window.partition] + 1
            ]
            boundary = min((item.start_date for item in future_windows), default=None)
            if boundary is not None:
                partition_dates = (
                    [
                        item
                        for item in frozen_trading_dates
                        if window.start_date <= item <= window.end_date
                    ]
                    if frozen_trading_dates
                    else sorted(
                        {
                            item.session_date
                            for item in observations
                            if window.start_date <= item.session_date <= window.end_date
                        }
                    )
                )
                embargo_dates = set(partition_dates[-protocol.embargo_sessions :])
                if observation.label_end_date >= boundary or observation.session_date in embargo_dates:
                    continue
            admitted.append((observation, window))
            observation_admitted = True
        if not observation_admitted:
            excluded.add(observation.observation_id)
    return tuple(admitted), excluded


def _apply_return_sensitivity(observation: EvaluationObservation, multiplier: Decimal) -> EvaluationObservation:
    return replace(
        observation,
        realized_return=observation.realized_return * multiplier,
        mfe=None if observation.mfe is None else observation.mfe * multiplier,
        mae=None if observation.mae is None else observation.mae * multiplier,
    )


def _formal_pit_rejections(
    *,
    protocol: FormalEvaluationProtocol,
    evidence: FormalPITEvidenceArtifact | None,
    panel_source_references: tuple[ValidationArtifactReference, ...],
    evaluated_at: datetime,
) -> tuple[str, ...]:
    if evidence is None:
        return ("REAL_FORMAL_PIT_REQUIRED",)
    reasons: set[str] = set()
    if evidence.outcome is not PITValidationOutcome.SATISFIED:
        reasons.add("FORMAL_PIT_NOT_SATISFIED")
    if not evidence.selected_fact_authorities or any(
        item.system_time_authority != "POSTGRESQL_CLOCK" for item in evidence.selected_fact_authorities
    ):
        reasons.add("REAL_FORMAL_PIT_POSTGRESQL_CLOCK_REQUIRED")
    if evidence.available_at > evaluated_at or evidence.recorded_at > evaluated_at:
        reasons.add("FORMAL_PIT_NOT_AVAILABLE_AT_EVALUATION")
    validation_protocol = evidence.lineage.validation_protocol
    if validation_protocol.artifact_id != protocol.protocol_id or validation_protocol.content_hash != protocol.protocol_hash:
        reasons.add("FORMAL_PIT_PROTOCOL_LINEAGE_MISMATCH")
    dataset = evidence.lineage.dataset
    if not any(item.artifact_id == dataset.artifact_id and item.content_hash == dataset.content_hash for item in panel_source_references):
        reasons.add("FORMAL_PIT_PANEL_DATASET_LINEAGE_MISMATCH")
    return tuple(sorted(reasons))


def _slices(values: tuple[EvaluationObservation, ...]) -> dict[str, dict[str, tuple[EvaluationObservation, ...]]]:
    fields = {
        "ALL": lambda item: "ALL",
        "REGIME": lambda item: item.regime,
        "LIQUIDITY": lambda item: item.liquidity_slice,
        "MARKET_CAP": lambda item: item.market_cap_slice,
        "THEME": lambda item: item.theme_slice,
    }
    result: dict[str, dict[str, tuple[EvaluationObservation, ...]]] = {}
    for name, getter in fields.items():
        groups: dict[str, list[EvaluationObservation]] = {}
        for item in values:
            groups.setdefault(getter(item), []).append(item)
        result[name] = {key: tuple(group) for key, group in sorted(groups.items())}
    return result


def _metric_available(name: str, values: tuple[EvaluationObservation, ...]) -> tuple[EvaluationObservation, ...]:
    if name == "MFE":
        return tuple(item for item in values if item.mfe is not None)
    if name == "MAE":
        return tuple(item for item in values if item.mae is not None)
    return values


def _ic(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    return _mean_optional(_daily_correlations(values, ranked=False))


def _rank_ic(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    return _mean_optional(_daily_correlations(values, ranked=True))


def _icir(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    daily = _daily_correlations(values, ranked=False)
    if len(daily) < 2:
        return None
    deviation = pstdev(float(item) for item in daily)
    if deviation == 0:
        return None
    return Decimal(str(fmean(float(item) for item in daily) / deviation))


def _positive_ic_ratio(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    daily = _daily_correlations(values, ranked=False)
    if not daily:
        return None
    return Decimal(sum(item > 0 for item in daily)) / Decimal(len(daily))


def _top_k_return(
    values: tuple[EvaluationObservation, ...], top_k: int
) -> Decimal | None:
    daily = [
        _mean(tuple(item.realized_return for item in ordered[:top_k]))
        for ordered in _ordered_daily(values)
        if ordered
    ]
    return _mean_optional(tuple(daily))


def _spread(
    values: tuple[EvaluationObservation, ...], top_k: int
) -> Decimal | None:
    daily: list[Decimal] = []
    for ordered in _ordered_daily(values):
        count = min(top_k, len(ordered))
        if count == 0:
            continue
        daily.append(
            _mean(tuple(item.realized_return for item in ordered[:count]))
            - _mean(tuple(item.realized_return for item in ordered[-count:]))
        )
    return _mean_optional(tuple(daily))


def _hit_rate(
    values: tuple[EvaluationObservation, ...], top_k: int
) -> Decimal | None:
    selected = tuple(
        item
        for ordered in _ordered_daily(values)
        for item in ordered[: min(top_k, len(ordered))]
    )
    if not selected:
        return None
    return Decimal(sum(item.realized_return > 0 for item in selected)) / Decimal(
        len(selected)
    )


def _return(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    return None if not values else _mean(tuple(item.realized_return for item in values))


def _mfe(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    return (
        None
        if not values
        else _mean(tuple(item.mfe for item in values if item.mfe is not None))
    )


def _mae(values: tuple[EvaluationObservation, ...]) -> Decimal | None:
    return (
        None
        if not values
        else _mean(tuple(item.mae for item in values if item.mae is not None))
    )


def _turnover(
    values: tuple[EvaluationObservation, ...], top_k: int
) -> Decimal | None:
    selected = [
        {item.symbol for item in ordered[: min(top_k, len(ordered))]}
        for ordered in _ordered_daily(values)
    ]
    if len(selected) < 2:
        return None
    values_by_date = tuple(
        Decimal(len(current.symmetric_difference(previous)))
        / Decimal(max(1, len(current | previous)))
        for previous, current in zip(selected, selected[1:])
    )
    return _mean(values_by_date)


def _drawdown(
    values: tuple[EvaluationObservation, ...], top_k: int
) -> Decimal | None:
    returns = tuple(
        _mean(tuple(item.realized_return for item in ordered[: min(top_k, len(ordered))]))
        for ordered in _ordered_daily(values)
        if ordered
    )
    if not returns:
        return None
    wealth = peak = Decimal("1")
    drawdown = Decimal("0")
    for value in returns:
        wealth *= Decimal("1") + value
        peak = max(peak, wealth)
        drawdown = min(drawdown, wealth / peak - Decimal("1"))
    return drawdown


def _incremental_lift(
    values: tuple[EvaluationObservation, ...], top_k: int
) -> Decimal | None:
    top = _top_k_return(values, top_k)
    if top is None:
        return None
    daily_baseline = tuple(
        _mean(tuple(item.realized_return for item in ordered))
        for ordered in _ordered_daily(values)
        if ordered
    )
    baseline = _mean_optional(daily_baseline)
    return None if baseline is None else top - baseline


def _bootstrap(
    function: MetricFunction,
    values: tuple[EvaluationObservation, ...],
    iterations: int,
    confidence: Decimal,
    *,
    block_sessions: int,
    seed: str,
) -> tuple[Decimal, Decimal, Decimal]:
    sessions = _group_by_session(values)
    if not sessions:
        raise ValueError("cluster bootstrap requires trading-date observations")
    random = Random(seed)
    estimates: list[Decimal] = []
    session_dates = tuple(sorted(sessions))
    for _iteration in range(iterations):
        sampled: list[EvaluationObservation] = []
        sample_slot = 0
        while sample_slot < len(session_dates):
            start = random.randrange(len(session_dates))
            for offset in range(block_sessions):
                if sample_slot >= len(session_dates):
                    break
                source_date = session_dates[(start + offset) % len(session_dates)]
                synthetic_date = date.min + timedelta(days=sample_slot)
                sampled.extend(
                    replace(item, session_date=synthetic_date)
                    for item in sessions[source_date]
                )
                sample_slot += 1
        estimate = function(tuple(sampled))
        if estimate is not None:
            estimates.append(estimate)
    if not estimates:
        raise ValueError("cluster bootstrap produced no estimable draws")
    estimates.sort()
    alpha = (Decimal("1") - confidence) / Decimal("2")
    low = estimates[min(len(estimates) - 1, int(alpha * len(estimates)))]
    high = estimates[min(len(estimates) - 1, int((Decimal("1") - alpha) * len(estimates)))]
    non_positive = sum(item <= 0 for item in estimates)
    non_negative = sum(item >= 0 for item in estimates)
    p_value = Decimal("2") * Decimal(min(non_positive, non_negative)) / Decimal(len(estimates))
    return low, high, min(Decimal("1"), p_value)


def _adjust_p_values(values: list[Decimal], method: MultipleTestingMethod) -> list[Decimal]:
    if method is MultipleTestingMethod.BONFERRONI:
        return [min(Decimal("1"), value * len(values)) for value in values]
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    adjusted = [Decimal("1")] * len(values)
    running = Decimal("1")
    for rank, (index, value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, value * Decimal(len(values)) / Decimal(rank))
        adjusted[index] = min(Decimal("1"), running)
    return adjusted


def _correlation(left: list[float], right: list[float]) -> Decimal | None:
    if len(left) < 2 or pstdev(left) == 0 or pstdev(right) == 0:
        return None
    lm, rm = fmean(left), fmean(right)
    denominator = sqrt(sum((item - lm) ** 2 for item in left) * sum((item - rm) ** 2 for item in right))
    return Decimal(str(sum((x - lm) * (y - rm) for x, y in zip(left, right, strict=True)) / denominator))


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for original, _value in ordered[index:end]:
            result[original] = rank
        index = end
    return result


def _group_by_session(
    values: tuple[EvaluationObservation, ...],
) -> dict[date, tuple[EvaluationObservation, ...]]:
    grouped: dict[date, list[EvaluationObservation]] = {}
    for item in values:
        grouped.setdefault(item.session_date, []).append(item)
    return {
        session: tuple(sorted(items, key=lambda item: item.symbol))
        for session, items in grouped.items()
    }


def _ordered_daily(
    values: tuple[EvaluationObservation, ...],
) -> tuple[tuple[EvaluationObservation, ...], ...]:
    grouped = _group_by_session(values)
    return tuple(
        tuple(
            sorted(
                grouped[session],
                key=lambda item: (-item.score, item.symbol),
            )
        )
        for session in sorted(grouped)
    )


def _daily_correlations(
    values: tuple[EvaluationObservation, ...], *, ranked: bool
) -> tuple[Decimal, ...]:
    correlations: list[Decimal] = []
    for observations in _group_by_session(values).values():
        scores = [float(item.score) for item in observations]
        returns = [float(item.realized_return) for item in observations]
        if ranked:
            scores = _ranks(scores)
            returns = _ranks(returns)
        correlation = _correlation(scores, returns)
        if correlation is not None:
            correlations.append(correlation)
    return tuple(correlations)


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("mean requires values")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _mean_optional(values: tuple[Decimal, ...]) -> Decimal | None:
    return None if not values else _mean(values)


def _not_estimable_reason(metric_name: str) -> str:
    if metric_name in {"IC", "RANK_IC", "ICIR", "POSITIVE_IC_RATIO"}:
        return "INSUFFICIENT_DAILY_CROSS_SECTIONS"
    if metric_name == "TURNOVER":
        return "INSUFFICIENT_ORDERED_TRADING_DATES"
    return "INSUFFICIENT_METRIC_OBSERVATIONS"


def _mapping_value(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Formal Evaluation payload is not an object")
    return value


def _validate_fold_windows(windows: tuple[EvaluationWindow, ...]) -> None:
    for fold in {item.fold for item in windows}:
        scoped = [item for item in windows if item.fold == fold]
        partitions = {item.partition for item in scoped}
        if partitions != set(EvaluationPartition):
            raise ValueError("each Evaluation fold requires Train, Validation, and Locked OOS")
        for left in scoped:
            for right in scoped:
                if left.window_id < right.window_id and max(left.start_date, right.start_date) <= min(left.end_date, right.end_date):
                    raise ValueError("Evaluation windows cannot overlap")


def _protocol_payload(
    version: str,
    target: ValidationArtifactReference,
    windows: tuple[EvaluationWindow, ...],
    embargo: int,
    iterations: int,
    block_sessions: int,
    confidence: Decimal,
    method: MultipleTestingMethod,
    hypothesis_family_id: str,
    top_k: int,
    sensitivity: tuple[Decimal, ...],
    locked_at: datetime,
) -> dict[str, Any]:
    return {
        "schema": "formal-evaluation-protocol/v2",
        "protocol_version": version,
        "target_protocol_reference": target.to_canonical_dict(),
        "windows": [
            {
                "window_id": item.window_id,
                "partition": item.partition.value,
                "start_date": item.start_date.isoformat(),
                "end_date": item.end_date.isoformat(),
                "fold": item.fold,
            }
            for item in windows
        ],
        "embargo_sessions": embargo,
        "purge_overlapping_labels": True,
        "bootstrap_iterations": iterations,
        "bootstrap_method": "TRADING_DATE_MOVING_BLOCK",
        "bootstrap_block_sessions": block_sessions,
        "confidence_level": str(confidence),
        "multiple_testing_method": method.value,
        "hypothesis_family_id": hypothesis_family_id,
        "top_k": top_k,
        "sensitivity_return_multipliers": [str(item) for item in sensitivity],
        "locked_at": timestamp(locked_at),
    }


def _result_payload(
    protocol: ValidationArtifactReference,
    pit: ValidationArtifactReference | None,
    panel: ValidationArtifactReference,
    panel_sources: tuple[ValidationArtifactReference, ...],
    metrics: tuple[EvaluationMetric, ...],
    excluded: tuple[str, ...],
    authority: ResearchEvidenceAuthority,
    formal: bool,
    reasons: tuple[str, ...],
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "formal-evaluation-result/v2",
        "protocol_reference": protocol.to_canonical_dict(),
        "pit_evidence_reference": None if pit is None else pit.to_canonical_dict(),
        "panel_reference": panel.to_canonical_dict(),
        "panel_source_references": [item.to_canonical_dict() for item in panel_sources],
        "metrics": [
            {
                "fold": item.fold,
                "partition": item.partition.value,
                "sensitivity_return_multiplier": str(item.sensitivity_return_multiplier),
                "metric_name": item.metric_name,
                "slice_kind": item.slice_kind,
                "slice_value": item.slice_value,
                "sample_count": item.sample_count,
                "status": item.status.value,
                "estimate": None if item.estimate is None else str(item.estimate),
                "confidence_low": None if item.confidence_low is None else str(item.confidence_low),
                "confidence_high": None if item.confidence_high is None else str(item.confidence_high),
                "raw_p_value": None if item.raw_p_value is None else str(item.raw_p_value),
                "adjusted_p_value": None if item.adjusted_p_value is None else str(item.adjusted_p_value),
                "hypothesis_family_id": item.hypothesis_family_id,
                "reason_codes": list(item.reason_codes),
            }
            for item in metrics
        ],
        "excluded_observation_ids": list(excluded),
        "authority": authority.value,
        "formal_oos": formal,
        "reason_codes": list(reasons),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }
