"""Independent calibration fit, artifact and evaluation framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from math import exp, log
from statistics import fmean
from typing import Any

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    GOVERNED_NON_PRODUCTION_LIMITATIONS,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text


class CalibrationMethod(str, Enum):
    PLATT_LOGISTIC = "PLATT_LOGISTIC"
    ISOTONIC = "ISOTONIC"
    BINNING = "BINNING"


class CalibrationPartition(str, Enum):
    FIT = "FIT"
    VALIDATION = "VALIDATION"
    OOS = "OOS"


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    observation_id: str
    score: Decimal
    outcome: int
    partition: CalibrationPartition

    def __post_init__(self) -> None:
        require_text("observation_id", self.observation_id)
        if self.outcome not in {0, 1} or isinstance(self.outcome, bool):
            raise ValueError("Calibration outcome must be binary")


@dataclass(frozen=True, slots=True)
class CalibrationProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    method: CalibrationMethod
    bin_count: int
    minimum_fit_samples: int
    maximum_iterations: int
    learning_rate: Decimal

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        method: CalibrationMethod,
        bin_count: int = 10,
        minimum_fit_samples: int = 30,
        maximum_iterations: int = 500,
        learning_rate: Decimal = Decimal("0.05"),
    ) -> CalibrationProtocol:
        if bin_count < 2 or minimum_fit_samples <= 0 or maximum_iterations <= 0 or learning_rate <= 0:
            raise ValueError("Calibration protocol parameters are invalid")
        values = {
            "schema": "calibration-protocol/v1",
            "protocol_version": protocol_version,
            "method": method.value,
            "bin_count": bin_count,
            "minimum_fit_samples": minimum_fit_samples,
            "maximum_iterations": maximum_iterations,
            "learning_rate": str(learning_rate),
        }
        artifact_id, digest = content_identity("calibration-protocol", values)
        return cls(artifact_id, digest, protocol_version, method, bin_count, minimum_fit_samples, maximum_iterations, learning_rate)


@dataclass(frozen=True, slots=True)
class CalibrationFit:
    fit_id: ArtifactId
    fit_hash: str
    protocol_reference: ValidationArtifactReference
    fit_observation_ids: tuple[str, ...]
    parameters: tuple[tuple[str, Decimal], ...]
    training_loss: Decimal
    created_at: datetime

    def __post_init__(self) -> None:
        require_sha256("fit_hash", self.fit_hash)
        if self.fit_observation_ids != tuple(sorted(set(self.fit_observation_ids))):
            raise ValueError("fit observations must be unique and sorted")
        if self.parameters != tuple(sorted(self.parameters)):
            raise ValueError("Calibration parameters must be unique and sorted")


@dataclass(frozen=True, slots=True)
class CalibrationEvaluation:
    evaluation_id: ArtifactId
    evaluation_hash: str
    partition: CalibrationPartition
    observation_ids: tuple[str, ...]
    brier: Decimal
    log_loss: Decimal
    reliability: Decimal
    ece: Decimal
    coverage: Decimal
    bins: tuple[tuple[Decimal, Decimal, int], ...]


@dataclass(frozen=True, slots=True)
class CalibrationArtifact:
    artifact_id: ArtifactId
    artifact_hash: str
    protocol_reference: ValidationArtifactReference
    fit: CalibrationFit
    evaluations: tuple[CalibrationEvaluation, ...]
    calibrated: bool
    qualification_evidence: ValidationArtifactReference | None
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "calibration-artifact/v1"

    def __post_init__(self) -> None:
        require_sha256("artifact_hash", self.artifact_hash)
        if self.calibrated and self.qualification_evidence is None:
            raise ValueError("calibrated Artifact requires qualification evidence")
        if self.calibrated and CalibrationPartition.OOS not in {item.partition for item in self.evaluations}:
            raise ValueError("calibrated Artifact requires separate OOS evaluation")
        if canonical_hash(self.identity_payload()) != self.artifact_hash:
            raise ValueError("Calibration Artifact hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _artifact_payload(
            self.protocol_reference,
            self.fit,
            self.evaluations,
            self.calibrated,
            self.qualification_evidence,
            self.created_at,
            self.limitations,
        )


def fit_calibration(
    *, protocol: CalibrationProtocol, observations: tuple[CalibrationObservation, ...], created_at: datetime
) -> CalibrationArtifact:
    ids = tuple(item.observation_id for item in observations)
    if len(ids) != len(set(ids)):
        raise ValueError("Calibration observations must be globally disjoint")
    fit = tuple(item for item in observations if item.partition is CalibrationPartition.FIT)
    validation = tuple(item for item in observations if item.partition is CalibrationPartition.VALIDATION)
    oos = tuple(item for item in observations if item.partition is CalibrationPartition.OOS)
    if len(fit) < protocol.minimum_fit_samples or not validation:
        raise ValueError("Calibration requires sufficient fit and separate validation data")
    params, predict = _fit_method(protocol, fit)
    fit_loss = _log_loss([predict(float(item.score)) for item in fit], [item.outcome for item in fit])
    protocol_ref = ValidationArtifactReference("CALIBRATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash)
    fit_payload = {
        "protocol_reference": protocol_ref.to_canonical_dict(),
        "fit_observation_ids": sorted(item.observation_id for item in fit),
        "parameters": [[name, str(value)] for name, value in params],
        "training_loss": str(fit_loss),
        "created_at": timestamp(created_at),
    }
    fit_id, fit_hash = content_identity("calibration-fit", fit_payload)
    fit_artifact = CalibrationFit(
        fit_id, fit_hash, protocol_ref, tuple(sorted(item.observation_id for item in fit)), params, fit_loss, created_at
    )
    evaluations = tuple(
        _evaluate(partition, values, predict)
        for partition, values in ((CalibrationPartition.VALIDATION, validation), (CalibrationPartition.OOS, oos))
        if values
    )
    limitations = tuple(sorted({*ENGINEERING_LIMITATIONS, "CALIBRATED_FALSE", "QUALIFICATION_EVIDENCE_NOT_ESTABLISHED"}))
    payload = _artifact_payload(protocol_ref, fit_artifact, evaluations, False, None, created_at, limitations)
    artifact_id, artifact_hash = content_identity("calibration-artifact", payload)
    return CalibrationArtifact(artifact_id, artifact_hash, protocol_ref, fit_artifact, evaluations, False, None, created_at, limitations)


def qualify_calibration(
    *,
    artifact: CalibrationArtifact,
    qualification_evidence: ValidationArtifactReference,
    created_at: datetime,
) -> CalibrationArtifact:
    """Explicit Governance transition; fitting alone never invokes this path."""
    if artifact.calibrated:
        return artifact
    if CalibrationPartition.OOS not in {item.partition for item in artifact.evaluations}:
        raise ValueError("Calibration qualification requires locked OOS evaluation")
    limitations = GOVERNED_NON_PRODUCTION_LIMITATIONS
    payload = _artifact_payload(
        artifact.protocol_reference,
        artifact.fit,
        artifact.evaluations,
        True,
        qualification_evidence,
        created_at,
        limitations,
    )
    artifact_id, artifact_hash = content_identity("calibration-artifact", payload)
    return CalibrationArtifact(
        artifact_id,
        artifact_hash,
        artifact.protocol_reference,
        artifact.fit,
        artifact.evaluations,
        True,
        qualification_evidence,
        created_at,
        limitations,
    )


def _fit_method(
    protocol: CalibrationProtocol, observations: tuple[CalibrationObservation, ...]
) -> tuple[tuple[tuple[str, Decimal], ...], Any]:
    x = [float(item.score) for item in observations]
    y = [item.outcome for item in observations]
    if protocol.method is CalibrationMethod.PLATT_LOGISTIC:
        a = b = 0.0
        rate = float(protocol.learning_rate)
        for _ in range(protocol.maximum_iterations):
            probabilities = [_sigmoid(a * value + b) for value in x]
            a -= rate * fmean((p - target) * value for p, target, value in zip(probabilities, y, x, strict=True))
            b -= rate * fmean(p - target for p, target in zip(probabilities, y, strict=True))
        params: tuple[tuple[str, Decimal], ...] = (
            ("intercept", Decimal(str(b))),
            ("slope", Decimal(str(a))),
        )
        return params, lambda value: _sigmoid(a * value + b)
    ordered = sorted(zip(x, y, strict=True))
    if protocol.method is CalibrationMethod.BINNING:
        bins = _equal_count_bins(ordered, protocol.bin_count)
    else:
        bins = _isotonic_bins(ordered)
    params = tuple((f"bin_{index}:{low}:{high}", Decimal(str(probability))) for index, (low, high, probability) in enumerate(bins))
    return params, lambda value: _bin_predict(value, bins)


def _evaluate(partition: CalibrationPartition, observations: tuple[CalibrationObservation, ...], predict: Any) -> CalibrationEvaluation:
    probabilities = [predict(float(item.score)) for item in observations]
    outcomes = [item.outcome for item in observations]
    brier = Decimal(str(fmean((p - y) ** 2 for p, y in zip(probabilities, outcomes, strict=True))))
    loss = _log_loss(probabilities, outcomes)
    bins = _reliability_bins(probabilities, outcomes, 10)
    ece = Decimal(str(sum(count / len(outcomes) * abs(float(predicted) - float(observed)) for predicted, observed, count in bins)))
    reliability = Decimal(
        str(sum(count / len(outcomes) * (float(predicted) - float(observed)) ** 2 for predicted, observed, count in bins))
    )
    values = {
        "partition": partition.value,
        "observation_ids": sorted(item.observation_id for item in observations),
        "brier": str(brier),
        "log_loss": str(loss),
        "reliability": str(reliability),
        "ece": str(ece),
        "coverage": "1",
        "bins": [[str(a), str(b), count] for a, b, count in bins],
    }
    artifact_id, digest = content_identity("calibration-evaluation", values)
    return CalibrationEvaluation(
        artifact_id,
        digest,
        partition,
        tuple(sorted(item.observation_id for item in observations)),
        brier,
        loss,
        reliability,
        ece,
        Decimal("1"),
        bins,
    )


def _artifact_payload(
    protocol: ValidationArtifactReference,
    fit: CalibrationFit,
    evaluations: tuple[CalibrationEvaluation, ...],
    calibrated: bool,
    evidence: ValidationArtifactReference | None,
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "calibration-artifact/v1",
        "protocol_reference": protocol.to_canonical_dict(),
        "fit": {"fit_id": str(fit.fit_id), "fit_hash": fit.fit_hash},
        "evaluations": [
            {"evaluation_id": str(item.evaluation_id), "evaluation_hash": item.evaluation_hash, "partition": item.partition.value}
            for item in evaluations
        ],
        "calibrated": calibrated,
        "qualification_evidence": None if evidence is None else evidence.to_canonical_dict(),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1 / (1 + z)
    z = exp(value)
    return z / (1 + z)


def _log_loss(probabilities: list[float], outcomes: list[int]) -> Decimal:
    epsilon = 1e-15
    return Decimal(
        str(
            fmean(
                -(y * log(max(epsilon, min(1 - epsilon, p))) + (1 - y) * log(max(epsilon, min(1 - epsilon, 1 - p))))
                for p, y in zip(probabilities, outcomes, strict=True)
            )
        )
    )


def _equal_count_bins(values: list[tuple[float, int]], count: int) -> list[tuple[float, float, float]]:
    width = max(1, (len(values) + count - 1) // count)
    return [
        (chunk[0][0], chunk[-1][0], fmean(item[1] for item in chunk))
        for start in range(0, len(values), width)
        if (chunk := values[start : start + width])
    ]


def _isotonic_bins(values: list[tuple[float, int]]) -> list[tuple[float, float, float]]:
    blocks: list[list[tuple[float, int]]] = [[item] for item in values]
    index = 0
    while index < len(blocks) - 1:
        if fmean(y for _x, y in blocks[index]) <= fmean(y for _x, y in blocks[index + 1]):
            index += 1
        else:
            blocks[index : index + 2] = [blocks[index] + blocks[index + 1]]
            index = max(0, index - 1)
    return [(block[0][0], block[-1][0], fmean(y for _x, y in block)) for block in blocks]


def _bin_predict(value: float, bins: list[tuple[float, float, float]]) -> float:
    for low, high, probability in bins:
        if low <= value <= high:
            return probability
    return bins[0][2] if value < bins[0][0] else bins[-1][2]


def _reliability_bins(probabilities: list[float], outcomes: list[int], count: int) -> tuple[tuple[Decimal, Decimal, int], ...]:
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(count)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        buckets[min(count - 1, int(probability * count))].append((probability, outcome))
    return tuple(
        (Decimal(str(fmean(p for p, _y in bucket))), Decimal(str(fmean(y for _p, y in bucket))), len(bucket))
        for bucket in buckets
        if bucket
    )
