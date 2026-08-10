"""Locked evaluation/OOS protocol and fail-closed execution runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from math import sqrt
from random import Random
from statistics import fmean, pstdev
from typing import Any, Callable

from market_regime_alpha.application.research_evaluation.targets import OutcomeTargetProtocol
from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    GOVERNED_NON_PRODUCTION_LIMITATIONS,
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
    confidence_level: Decimal
    multiple_testing_method: MultipleTestingMethod
    sensitivity_return_multipliers: tuple[Decimal, ...]
    locked_at: datetime

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        target_protocol: OutcomeTargetProtocol,
        windows: tuple[EvaluationWindow, ...],
        bootstrap_iterations: int,
        confidence_level: Decimal,
        multiple_testing_method: MultipleTestingMethod,
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
        if not Decimal("0") < confidence_level < Decimal("1") or bootstrap_iterations <= 0:
            raise ValueError("Formal Evaluation statistics configuration is invalid")
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
            confidence_level,
            multiple_testing_method,
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
            confidence_level,
            multiple_testing_method,
            sensitivity,
            locked_at,
        )


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


@dataclass(frozen=True, slots=True)
class EvaluationMetric:
    fold: int
    partition: EvaluationPartition
    sensitivity_return_multiplier: Decimal
    metric_name: str
    slice_kind: str
    slice_value: str
    sample_count: int
    estimate: Decimal
    confidence_low: Decimal
    confidence_high: Decimal
    raw_p_value: Decimal
    adjusted_p_value: Decimal


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
    schema_version: str = "formal-evaluation-result/v1"

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


MetricFunction = Callable[[tuple[EvaluationObservation, ...]], Decimal]


def run_formal_evaluation(
    *,
    protocol: FormalEvaluationProtocol,
    panel_reference: ValidationArtifactReference,
    observations: tuple[EvaluationObservation, ...],
    formal_pit_evidence: FormalPITEvidenceArtifact | None,
    created_at: datetime,
    panel_source_references: tuple[ValidationArtifactReference, ...] = (),
) -> FormalEvaluationResult:
    if not observations:
        raise ValueError("Evaluation Runtime requires observations")
    ids = tuple(item.observation_id for item in observations)
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation observations must be unique")
    admitted, excluded = _admit_observations(protocol, observations)
    if not admitted:
        raise ValueError("purging and Embargo removed every Evaluation observation")
    formal_pit_rejections = _formal_pit_rejections(
        protocol=protocol,
        evidence=formal_pit_evidence,
        panel_source_references=panel_source_references,
        evaluated_at=created_at,
    )
    real_formal_pit = not formal_pit_rejections
    locked_oos_present = any(window.partition is EvaluationPartition.LOCKED_OOS for _item, window in admitted)
    formal = real_formal_pit and locked_oos_present
    authority = ResearchEvidenceAuthority.FORMAL_OOS if formal else ResearchEvidenceAuthority.ENGINEERING_ONLY
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
        ("HIT_RATE", _hit_rate),
        ("RETURN", _return),
        ("MFE", _mfe),
        ("MAE", _mae),
    )
    raw: list[tuple[int, EvaluationPartition, Decimal, str, str, str, int, Decimal, Decimal, Decimal, Decimal]] = []
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
                        if not available:
                            continue
                        estimate = function(available)
                        low, high, p_value = _bootstrap(
                            function,
                            available,
                            protocol.bootstrap_iterations,
                            protocol.confidence_level,
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
                                estimate,
                                low,
                                high,
                                p_value,
                            )
                        )
    adjusted = _adjust_p_values([item[-1] for item in raw], protocol.multiple_testing_method)
    metrics = tuple(EvaluationMetric(*item, adjusted[index]) for index, item in enumerate(raw))
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    if formal:
        reasons = ("FORMAL_OOS_EVIDENCE_EMITTED", "LOCKED_OOS_EVALUATED", "REAL_FORMAL_PIT_ACCEPTED")
        limitations = GOVERNED_NON_PRODUCTION_LIMITATIONS
    else:
        reason_set = {"FORMAL_OOS_BLOCKED"}
        if not real_formal_pit:
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
    protocol: FormalEvaluationProtocol, observations: tuple[EvaluationObservation, ...]
) -> tuple[tuple[tuple[EvaluationObservation, EvaluationWindow], ...], set[str]]:
    admitted: list[tuple[EvaluationObservation, EvaluationWindow]] = []
    excluded: set[str] = set()
    for observation in observations:
        windows = [item for item in protocol.windows if item.start_date <= observation.session_date <= item.end_date]
        if not windows:
            excluded.add(observation.observation_id)
            continue
        observation_admitted = False
        for window in windows:
            future_windows = [
                item for item in protocol.windows if item.fold == window.fold and item.partition is not EvaluationPartition.TRAIN
            ]
            boundary = min((item.start_date for item in future_windows), default=None)
            if window.partition is EvaluationPartition.TRAIN and boundary is not None:
                train_dates = sorted({item.session_date for item in observations if window.start_date <= item.session_date < boundary})
                embargo_dates = set(train_dates[-protocol.embargo_sessions :])
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


def _ic(values: tuple[EvaluationObservation, ...]) -> Decimal:
    return _correlation([float(item.score) for item in values], [float(item.realized_return) for item in values])


def _rank_ic(values: tuple[EvaluationObservation, ...]) -> Decimal:
    return _correlation(_ranks([float(item.score) for item in values]), _ranks([float(item.realized_return) for item in values]))


def _hit_rate(values: tuple[EvaluationObservation, ...]) -> Decimal:
    return Decimal(sum(item.realized_return > 0 for item in values)) / Decimal(len(values))


def _return(values: tuple[EvaluationObservation, ...]) -> Decimal:
    return sum((item.realized_return for item in values), Decimal("0")) / Decimal(len(values))


def _mfe(values: tuple[EvaluationObservation, ...]) -> Decimal:
    return sum((item.mfe for item in values if item.mfe is not None), Decimal("0")) / Decimal(len(values))


def _mae(values: tuple[EvaluationObservation, ...]) -> Decimal:
    return sum((item.mae for item in values if item.mae is not None), Decimal("0")) / Decimal(len(values))


def _bootstrap(
    function: MetricFunction, values: tuple[EvaluationObservation, ...], iterations: int, confidence: Decimal, *, seed: str
) -> tuple[Decimal, Decimal, Decimal]:
    random = Random(seed)
    estimates = sorted(function(tuple(random.choice(values) for _ in values)) for _ in range(iterations))
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


def _correlation(left: list[float], right: list[float]) -> Decimal:
    if len(left) < 2 or pstdev(left) == 0 or pstdev(right) == 0:
        return Decimal("0")
    lm, rm = fmean(left), fmean(right)
    denominator = sqrt(sum((item - lm) ** 2 for item in left) * sum((item - rm) ** 2 for item in right))
    return Decimal(str(sum((x - lm) * (y - rm) for x, y in zip(left, right, strict=True)) / denominator))


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [0.0] * len(values)
    for rank, (index, _value) in enumerate(ordered, start=1):
        result[index] = float(rank)
    return result


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
    confidence: Decimal,
    method: MultipleTestingMethod,
    sensitivity: tuple[Decimal, ...],
    locked_at: datetime,
) -> dict[str, Any]:
    return {
        "schema": "formal-evaluation-protocol/v1",
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
        "confidence_level": str(confidence),
        "multiple_testing_method": method.value,
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
        "schema_version": "formal-evaluation-result/v1",
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
                "estimate": str(item.estimate),
                "confidence_low": str(item.confidence_low),
                "confidence_high": str(item.confidence_high),
                "raw_p_value": str(item.raw_p_value),
                "adjusted_p_value": str(item.adjusted_p_value),
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
