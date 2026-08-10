"""Locked evaluation/OOS protocol and fail-closed execution runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from math import sqrt
from random import Random
from statistics import fmean, pstdev
from typing import Any, Callable

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
    ) -> FormalEvaluationProtocol:
        ordered = tuple(sorted(windows, key=lambda item: (item.fold, item.partition.value, item.start_date)))
        if not ordered or len({item.window_id for item in ordered}) != len(ordered):
            raise ValueError("Formal Evaluation windows must be non-empty and unique")
        if not Decimal("0") < confidence_level < Decimal("1") or bootstrap_iterations <= 0:
            raise ValueError("Formal Evaluation statistics configuration is invalid")
        _validate_fold_windows(ordered)
        embargo = derive_embargo_sessions(target_protocol)
        target_ref = ValidationArtifactReference("OUTCOME_TARGET_PROTOCOL", target_protocol.protocol_id, target_protocol.protocol_hash)
        values = _protocol_payload(
            protocol_version, target_ref, ordered, embargo, bootstrap_iterations, confidence_level, multiple_testing_method, locked_at
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
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Formal Evaluation result hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _result_payload(
            self.protocol_reference,
            self.pit_evidence_reference,
            self.panel_reference,
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
) -> FormalEvaluationResult:
    if not observations:
        raise ValueError("Evaluation Runtime requires observations")
    ids = tuple(item.observation_id for item in observations)
    if len(ids) != len(set(ids)):
        raise ValueError("Evaluation observations must be unique")
    admitted, excluded = _admit_observations(protocol, observations)
    if not admitted:
        raise ValueError("purging and Embargo removed every Evaluation observation")
    formal = formal_pit_evidence is not None and formal_pit_evidence.outcome is PITValidationOutcome.SATISFIED
    authority = ResearchEvidenceAuthority.FORMAL_OOS if formal else ResearchEvidenceAuthority.ENGINEERING_ONLY
    pit_ref = (
        None
        if formal_pit_evidence is None
        else ValidationArtifactReference("FORMAL_PIT_EVIDENCE", formal_pit_evidence.evidence_id, formal_pit_evidence.evidence_hash)
    )
    metric_specs: tuple[tuple[str, MetricFunction], ...] = (
        ("IC", _ic),
        ("RANK_IC", _rank_ic),
        ("HIT_RATE", _hit_rate),
        ("RETURN", _return),
        ("MFE", _mfe),
        ("MAE", _mae),
    )
    raw: list[tuple[str, str, str, int, Decimal, Decimal, Decimal, Decimal]] = []
    for slice_kind, groups in _slices(admitted).items():
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
                    seed=f"{slice_kind}:{slice_value}:{metric_name}",
                )
                raw.append((metric_name, slice_kind, slice_value, len(available), estimate, low, high, p_value))
    adjusted = _adjust_p_values([item[-1] for item in raw], protocol.multiple_testing_method)
    metrics = tuple(EvaluationMetric(*item, adjusted[index]) for index, item in enumerate(raw))
    reasons = ("REAL_FORMAL_PIT_ACCEPTED", "FORMAL_OOS_EVIDENCE_EMITTED") if formal else ("FORMAL_OOS_BLOCKED", "REAL_FORMAL_PIT_REQUIRED")
    limitations = tuple(sorted(set(ENGINEERING_LIMITATIONS) | (set() if formal else {"FORMAL_OOS_FALSE"})))
    protocol_ref = ValidationArtifactReference("FORMAL_EVALUATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    payload = _result_payload(
        protocol_ref, pit_ref, panel_reference, metrics, tuple(sorted(excluded)), authority, formal, reasons, created_at, limitations
    )
    result_id, digest = content_identity("formal-evaluation-result", payload)
    return FormalEvaluationResult(
        result_id,
        digest,
        protocol_ref,
        pit_ref,
        panel_reference,
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
) -> tuple[tuple[EvaluationObservation, ...], set[str]]:
    admitted: list[EvaluationObservation] = []
    excluded: set[str] = set()
    for observation in observations:
        windows = [item for item in protocol.windows if item.start_date <= observation.session_date <= item.end_date]
        if not windows:
            excluded.add(observation.observation_id)
            continue
        window = windows[0]
        future_windows = [item for item in protocol.windows if item.fold == window.fold and item.partition is not EvaluationPartition.TRAIN]
        boundary = min((item.start_date for item in future_windows), default=None)
        if (
            window.partition is EvaluationPartition.TRAIN
            and boundary is not None
            and observation.label_end_date >= boundary - timedelta(days=protocol.embargo_sessions)
        ):
            excluded.add(observation.observation_id)
            continue
        admitted.append(observation)
    return tuple(admitted), excluded


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
        "locked_at": timestamp(locked_at),
    }


def _result_payload(
    protocol: ValidationArtifactReference,
    pit: ValidationArtifactReference | None,
    panel: ValidationArtifactReference,
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
        "metrics": [
            {
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
