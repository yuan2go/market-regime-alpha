"""Frozen multi-target hypothesis family and family-level evaluation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ENGINEERING_LIMITATIONS,
    ResearchEvidenceAuthority,
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    FORMAL_EVALUATION_IMPLEMENTATION_IDENTITY,
    FORMAL_EVALUATION_METRIC_NAMES,
    FORMAL_EVALUATION_SLICE_KINDS,
    EvaluationMetric,
    EvaluationMetricStatus,
    EvaluationObservation,
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingMethod,
    adjust_multiple_testing,
    run_formal_evaluation,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.pit_authority import FormalPITEvidenceArtifact
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text


@dataclass(frozen=True, slots=True)
class FrozenHypothesisFamily:
    family_id: ArtifactId
    family_hash: str
    formal_protocol_reference: ValidationArtifactReference
    evaluation_protocol_reference: ValidationArtifactReference
    target_protocol_reference: ValidationArtifactReference
    target_references: tuple[ValidationArtifactReference, ...]
    hypothesis_family_key: str
    multiple_testing_method: MultipleTestingMethod
    windows: tuple[EvaluationWindow, ...]
    sensitivity_return_multipliers: tuple[Decimal, ...]
    metric_names: tuple[str, ...]
    slice_kinds: tuple[str, ...]
    evaluation_implementation_identity: str
    frozen_at: datetime
    schema_version: str = "frozen-hypothesis-family/v1"

    def __post_init__(self) -> None:
        require_sha256("Frozen Hypothesis Family hash", self.family_hash)
        require_text("Frozen Hypothesis Family key", self.hypothesis_family_key)
        if self.formal_protocol_reference.artifact_kind != "FORMAL_RESEARCH_PROTOCOL":
            raise ValueError("Frozen Family requires Formal Research Protocol")
        if self.evaluation_protocol_reference.artifact_kind != "FORMAL_EVALUATION_PROTOCOL":
            raise ValueError("Frozen Family requires Formal Evaluation Protocol")
        if self.target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("Frozen Family requires Outcome Target Protocol")
        if any(item.artifact_kind != "OUTCOME_TARGET" for item in self.target_references):
            raise ValueError("Frozen Family Target owner kind mismatch")
        if self.target_references != tuple(
            sorted(set(self.target_references), key=_reference_key)
        ) or not self.target_references:
            raise ValueError("Frozen Family Targets must be non-empty, unique and sorted")
        if self.windows != tuple(
            sorted(
                self.windows,
                key=lambda item: (
                    item.fold,
                    item.partition.value,
                    item.start_date,
                    item.window_id,
                ),
            )
        ):
            raise ValueError("Frozen Family windows must be sorted")
        if self.sensitivity_return_multipliers != tuple(
            sorted(set(self.sensitivity_return_multipliers))
        ):
            raise ValueError("Frozen Family sensitivities must be unique and sorted")
        if self.metric_names != FORMAL_EVALUATION_METRIC_NAMES:
            raise ValueError("Frozen Family metric catalog identity mismatch")
        if self.slice_kinds != FORMAL_EVALUATION_SLICE_KINDS:
            raise ValueError("Frozen Family slice catalog identity mismatch")
        if (
            self.evaluation_implementation_identity
            != FORMAL_EVALUATION_IMPLEMENTATION_IDENTITY
        ):
            raise ValueError("Frozen Family evaluation implementation mismatch")
        if self.frozen_at.tzinfo is None or self.frozen_at.utcoffset() is None:
            raise ValueError("Frozen Family time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.family_hash:
            raise ValueError("Frozen Hypothesis Family identity hash mismatch")
        if self.family_id != ArtifactId(
            f"frozen-hypothesis-family:{self.family_hash[7:]}"
        ):
            raise ValueError("Frozen Hypothesis Family identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        formal_protocol_reference: ValidationArtifactReference,
        evaluation_protocol: FormalEvaluationProtocol,
        target_references: tuple[ValidationArtifactReference, ...],
        frozen_at: datetime,
    ) -> FrozenHypothesisFamily:
        ordered_targets = tuple(sorted(set(target_references), key=_reference_key))
        evaluation_reference = ValidationArtifactReference(
            "FORMAL_EVALUATION_PROTOCOL",
            evaluation_protocol.protocol_id,
            evaluation_protocol.protocol_hash,
        )
        values = {
            "formal_protocol_reference": formal_protocol_reference,
            "evaluation_protocol_reference": evaluation_reference,
            "target_protocol_reference": evaluation_protocol.target_protocol_reference,
            "target_references": ordered_targets,
            "hypothesis_family_key": evaluation_protocol.hypothesis_family_id,
            "multiple_testing_method": evaluation_protocol.multiple_testing_method,
            "windows": evaluation_protocol.windows,
            "sensitivity_return_multipliers": (
                evaluation_protocol.sensitivity_return_multipliers
            ),
            "metric_names": FORMAL_EVALUATION_METRIC_NAMES,
            "slice_kinds": FORMAL_EVALUATION_SLICE_KINDS,
            "evaluation_implementation_identity": (
                FORMAL_EVALUATION_IMPLEMENTATION_IDENTITY
            ),
            "frozen_at": frozen_at,
        }
        payload = _family_payload(**values)
        family_id, digest = content_identity("frozen-hypothesis-family", payload)
        return cls(
            family_id=family_id,
            family_hash=digest,
            formal_protocol_reference=formal_protocol_reference,
            evaluation_protocol_reference=evaluation_reference,
            target_protocol_reference=evaluation_protocol.target_protocol_reference,
            target_references=ordered_targets,
            hypothesis_family_key=evaluation_protocol.hypothesis_family_id,
            multiple_testing_method=evaluation_protocol.multiple_testing_method,
            windows=evaluation_protocol.windows,
            sensitivity_return_multipliers=(
                evaluation_protocol.sensitivity_return_multipliers
            ),
            metric_names=FORMAL_EVALUATION_METRIC_NAMES,
            slice_kinds=FORMAL_EVALUATION_SLICE_KINDS,
            evaluation_implementation_identity=(
                FORMAL_EVALUATION_IMPLEMENTATION_IDENTITY
            ),
            frozen_at=frozen_at,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "FROZEN_HYPOTHESIS_FAMILY", self.family_id, self.family_hash
        )

    def identity_payload(self) -> dict[str, Any]:
        return _family_payload(
            formal_protocol_reference=self.formal_protocol_reference,
            evaluation_protocol_reference=self.evaluation_protocol_reference,
            target_protocol_reference=self.target_protocol_reference,
            target_references=self.target_references,
            hypothesis_family_key=self.hypothesis_family_key,
            multiple_testing_method=self.multiple_testing_method,
            windows=self.windows,
            sensitivity_return_multipliers=self.sensitivity_return_multipliers,
            metric_names=self.metric_names,
            slice_kinds=self.slice_kinds,
            evaluation_implementation_identity=(
                self.evaluation_implementation_identity
            ),
            frozen_at=self.frozen_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "family_id": str(self.family_id),
            "family_hash": self.family_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> FrozenHypothesisFamily:
        return cls(
            family_id=ArtifactId(str(value["family_id"])),
            family_hash=str(value["family_hash"]),
            formal_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["formal_protocol_reference"])
            ),
            evaluation_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["evaluation_protocol_reference"])
            ),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_protocol_reference"])
            ),
            target_references=tuple(
                ValidationArtifactReference.from_canonical_dict(_mapping(item))
                for item in _sequence(value["target_references"])
            ),
            hypothesis_family_key=str(value["hypothesis_family_key"]),
            multiple_testing_method=MultipleTestingMethod(
                str(value["multiple_testing_method"])
            ),
            windows=tuple(_window_from_dict(_mapping(item)) for item in _sequence(value["windows"])),
            sensitivity_return_multipliers=tuple(
                Decimal(str(item))
                for item in _sequence(value["sensitivity_return_multipliers"])
            ),
            metric_names=tuple(
                str(item) for item in _sequence(value["metric_names"])
            ),
            slice_kinds=tuple(
                str(item) for item in _sequence(value["slice_kinds"])
            ),
            evaluation_implementation_identity=str(
                value["evaluation_implementation_identity"]
            ),
            frozen_at=datetime.fromisoformat(str(value["frozen_at"])),
            schema_version=str(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class FamilyEvaluationInput:
    target_reference: ValidationArtifactReference
    panel_reference: ValidationArtifactReference
    observations: tuple[EvaluationObservation, ...]
    panel_source_references: tuple[ValidationArtifactReference, ...] = ()

    def __post_init__(self) -> None:
        if self.target_reference.artifact_kind != "OUTCOME_TARGET":
            raise ValueError("Family Evaluation input requires Outcome Target")
        if not self.observations:
            raise ValueError("Family Evaluation input requires observations")


@dataclass(frozen=True, slots=True)
class FamilyEvaluationObservationBindings:
    """Caller scope for one Target; all values are owner-resolved later."""

    target_reference: ValidationArtifactReference
    panel_reference: ValidationArtifactReference
    observation_bindings: tuple[FormalEvaluationObservationBinding, ...]

    def __post_init__(self) -> None:
        if self.target_reference.artifact_kind != "OUTCOME_TARGET":
            raise ValueError("Family bindings require Outcome Target")
        if self.panel_reference.artifact_kind != "RESEARCH_PANEL_V2":
            raise ValueError("Family bindings require Research Panel V2")
        ordered = tuple(
            sorted(self.observation_bindings, key=lambda item: item.observation_id)
        )
        if (
            not ordered
            or self.observation_bindings != ordered
            or len({item.observation_id for item in ordered}) != len(ordered)
        ):
            raise ValueError(
                "Family observation bindings must be non-empty, unique and sorted"
            )


@dataclass(frozen=True, slots=True)
class RawOOSEvidenceIdentity:
    """Underlying market path identity, intentionally revision-independent."""

    subject: str
    decision_session_date: date
    outcome_session_date: date
    partition_kind: str = "LOCKED_OOS"
    schema_version: str = "raw-oos-evidence-identity/v1"

    def __post_init__(self) -> None:
        require_text("Raw OOS subject", self.subject)
        if self.outcome_session_date < self.decision_session_date:
            raise ValueError("Raw OOS outcome session precedes decision session")
        if self.partition_kind != "LOCKED_OOS":
            raise ValueError("Raw OOS partition cannot be weakened")
        if self.schema_version != "raw-oos-evidence-identity/v1":
            raise ValueError("unsupported Raw OOS Evidence identity schema")

    @property
    def identity_hash(self) -> str:
        return canonical_hash(self.to_canonical_dict())

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "subject": self.subject,
            "decision_session_date": self.decision_session_date.isoformat(),
            "outcome_session_date": self.outcome_session_date.isoformat(),
            "partition_kind": self.partition_kind,
        }


@dataclass(frozen=True, slots=True)
class LockedOOSTargetObservationConsumption:
    consumption_id: ArtifactId
    consumption_hash: str
    raw_evidence_identity_hash: str
    family_reference: ValidationArtifactReference
    target_reference: ValidationArtifactReference
    forecast_reference: ValidationArtifactReference
    label_reference: ValidationArtifactReference
    observation_set_reference: ValidationArtifactReference
    consumed_at: datetime
    schema_version: str = "locked-oos-target-observation-consumption/v1"

    def __post_init__(self) -> None:
        require_sha256("Target OOS consumption hash", self.consumption_hash)
        require_sha256("Raw OOS Evidence identity hash", self.raw_evidence_identity_hash)
        expected = (
            (self.family_reference, "FROZEN_HYPOTHESIS_FAMILY"),
            (self.target_reference, "OUTCOME_TARGET"),
            (self.forecast_reference, "OUTCOME_TARGET_BOUND_FORECAST"),
            (self.label_reference, "TARGET_OUTCOME_LABEL"),
            (
                self.observation_set_reference,
                "FORMAL_EVALUATION_OBSERVATION_SET",
            ),
        )
        if any(reference.artifact_kind != kind for reference, kind in expected):
            raise ValueError("Target OOS consumption owner kind mismatch")
        if self.consumed_at.tzinfo is None or self.consumed_at.utcoffset() is None:
            raise ValueError("Target OOS consumption time must be timezone-aware")
        if canonical_hash(self.identity_payload()) != self.consumption_hash:
            raise ValueError("Target OOS consumption hash mismatch")
        if self.consumption_id != ArtifactId(
            f"locked-oos-target-consumption:{self.consumption_hash[7:]}"
        ):
            raise ValueError("Target OOS consumption identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> LockedOOSTargetObservationConsumption:
        payload = _target_consumption_payload(**values)
        artifact_id, digest = content_identity(
            "locked-oos-target-consumption", payload
        )
        return cls(artifact_id, digest, **values)

    def identity_payload(self) -> dict[str, Any]:
        return _target_consumption_payload(
            raw_evidence_identity_hash=self.raw_evidence_identity_hash,
            family_reference=self.family_reference,
            target_reference=self.target_reference,
            forecast_reference=self.forecast_reference,
            label_reference=self.label_reference,
            observation_set_reference=self.observation_set_reference,
            consumed_at=self.consumed_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "consumption_id": str(self.consumption_id),
            "consumption_hash": self.consumption_hash,
            **self.identity_payload(),
        }


@dataclass(frozen=True, slots=True)
class FamilyEvaluationMetric:
    target_reference: ValidationArtifactReference
    metric: EvaluationMetric

    def __post_init__(self) -> None:
        if self.target_reference.artifact_kind != "OUTCOME_TARGET":
            raise ValueError("Family metric requires Outcome Target")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "target_reference": self.target_reference.to_canonical_dict(),
            "metric": _metric_payload(self.metric),
        }


@dataclass(frozen=True, slots=True)
class FormalHypothesisFamilyEvaluationResult:
    result_id: ArtifactId
    result_hash: str
    family_reference: ValidationArtifactReference
    evaluation_protocol_reference: ValidationArtifactReference
    pit_evidence_reference: ValidationArtifactReference | None
    metrics: tuple[FamilyEvaluationMetric, ...]
    excluded_observation_ids: tuple[str, ...]
    authority: ResearchEvidenceAuthority
    formal_oos: bool
    reason_codes: tuple[str, ...]
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "formal-hypothesis-family-evaluation-result/v1"

    def __post_init__(self) -> None:
        require_sha256("Family Evaluation result hash", self.result_hash)
        if self.family_reference.artifact_kind != "FROZEN_HYPOTHESIS_FAMILY":
            raise ValueError("Family Evaluation result family kind mismatch")
        if self.formal_oos or self.authority is not ResearchEvidenceAuthority.ENGINEERING_ONLY:
            raise ValueError("Family Evaluation candidate cannot self-grant Formal OOS")
        if canonical_hash(self.identity_payload()) != self.result_hash:
            raise ValueError("Family Evaluation result hash mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return _family_result_payload(
            family_reference=self.family_reference,
            evaluation_protocol_reference=self.evaluation_protocol_reference,
            pit_evidence_reference=self.pit_evidence_reference,
            metrics=self.metrics,
            excluded_observation_ids=self.excluded_observation_ids,
            authority=self.authority,
            formal_oos=self.formal_oos,
            reason_codes=self.reason_codes,
            created_at=self.created_at,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "result_id": str(self.result_id),
            "result_hash": self.result_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> FormalHypothesisFamilyEvaluationResult:
        pit_value = value["pit_evidence_reference"]
        return cls(
            result_id=ArtifactId(str(value["result_id"])),
            result_hash=str(value["result_hash"]),
            family_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["family_reference"])
            ),
            evaluation_protocol_reference=(
                ValidationArtifactReference.from_canonical_dict(
                    _mapping(value["evaluation_protocol_reference"])
                )
            ),
            pit_evidence_reference=(
                None
                if pit_value is None
                else ValidationArtifactReference.from_canonical_dict(
                    _mapping(pit_value)
                )
            ),
            metrics=tuple(
                FamilyEvaluationMetric(
                    ValidationArtifactReference.from_canonical_dict(
                        _mapping(_mapping(item)["target_reference"])
                    ),
                    _metric_from_payload(_mapping(_mapping(item)["metric"])),
                )
                for item in _sequence(value["metrics"])
            ),
            excluded_observation_ids=tuple(
                str(item) for item in _sequence(value["excluded_observation_ids"])
            ),
            authority=ResearchEvidenceAuthority(str(value["authority"])),
            formal_oos=bool(value["formal_oos"]),
            reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in _sequence(value["limitations"])),
            schema_version=str(value["schema_version"]),
        )


def run_formal_hypothesis_family_evaluation(
    *,
    family: FrozenHypothesisFamily,
    protocol: FormalEvaluationProtocol,
    inputs: tuple[FamilyEvaluationInput, ...],
    formal_pit_evidence: FormalPITEvidenceArtifact | None,
    created_at: datetime,
    frozen_trading_dates: tuple[date, ...] = (),
) -> FormalHypothesisFamilyEvaluationResult:
    if family.evaluation_protocol_reference != ValidationArtifactReference(
        "FORMAL_EVALUATION_PROTOCOL", protocol.protocol_id, protocol.protocol_hash
    ):
        raise ValueError("Family Evaluation Protocol owner mismatch")
    ordered_inputs = tuple(sorted(inputs, key=lambda item: _reference_key(item.target_reference)))
    actual_targets = tuple(item.target_reference for item in ordered_inputs)
    if actual_targets != family.target_references:
        raise ValueError("Family Evaluation requires the exact frozen Target family")
    results = tuple(
        (
            item.target_reference,
            run_formal_evaluation(
                protocol=protocol,
                panel_reference=item.panel_reference,
                observations=item.observations,
                formal_pit_evidence=formal_pit_evidence,
                created_at=created_at,
                panel_source_references=item.panel_source_references,
                frozen_trading_dates=frozen_trading_dates,
                preserve_planned_dimensions=True,
            ),
        )
        for item in ordered_inputs
    )
    flattened = [
        FamilyEvaluationMetric(target, metric)
        for target, result in results
        for metric in result.metrics
    ]
    _verify_planned_family_dimensions(family=family, metrics=tuple(flattened))
    # Every planned family member stays in the multiplicity denominator.
    # Treating unavailable hypotheses as absent would make the correction
    # data-dependent and reward missing folds/slices/Targets.
    adjusted = adjust_multiple_testing(
        tuple(
            (
                _required_decimal(item.metric.raw_p_value)
                if item.metric.status is EvaluationMetricStatus.ESTIMATED
                else Decimal("1")
            )
            for item in flattened
        ),
        family.multiple_testing_method,
    )
    for index, adjusted_value in enumerate(adjusted):
        item = flattened[index]
        if item.metric.status is not EvaluationMetricStatus.ESTIMATED:
            continue
        flattened[index] = FamilyEvaluationMetric(
            item.target_reference,
            replace(item.metric, adjusted_p_value=adjusted_value),
        )
    metrics = tuple(flattened)
    excluded = tuple(
        sorted(
            f"{target.artifact_id}:{item}"
            for target, result in results
            for item in result.excluded_observation_ids
        )
    )
    reasons = tuple(
        sorted(
            {
                "FORMAL_OOS_BLOCKED",
                "FORMAL_OOS_FAMILY_OWNER_QUALIFICATION_REQUIRED",
                *(reason for _target, result in results for reason in result.reason_codes),
            }
        )
    )
    limitations = tuple(
        sorted({*ENGINEERING_LIMITATIONS, "FORMAL_OOS_FALSE", "FAMILY_LEVEL_MULTIPLICITY"})
    )
    pit_reference = (
        None
        if formal_pit_evidence is None
        else ValidationArtifactReference(
            "FORMAL_PIT_EVIDENCE",
            formal_pit_evidence.evidence_id,
            formal_pit_evidence.evidence_hash,
        )
    )
    values = {
        "family_reference": family.reference,
        "evaluation_protocol_reference": family.evaluation_protocol_reference,
        "pit_evidence_reference": pit_reference,
        "metrics": metrics,
        "excluded_observation_ids": excluded,
        "authority": ResearchEvidenceAuthority.ENGINEERING_ONLY,
        "formal_oos": False,
        "reason_codes": reasons,
        "created_at": created_at,
        "limitations": limitations,
    }
    payload = _family_result_payload(**values)
    result_id, digest = content_identity("formal-family-evaluation-result", payload)
    return FormalHypothesisFamilyEvaluationResult(
        result_id=result_id,
        result_hash=digest,
        family_reference=family.reference,
        evaluation_protocol_reference=family.evaluation_protocol_reference,
        pit_evidence_reference=pit_reference,
        metrics=metrics,
        excluded_observation_ids=excluded,
        authority=ResearchEvidenceAuthority.ENGINEERING_ONLY,
        formal_oos=False,
        reason_codes=reasons,
        created_at=created_at,
        limitations=limitations,
    )


def _verify_planned_family_dimensions(
    *,
    family: FrozenHypothesisFamily,
    metrics: tuple[FamilyEvaluationMetric, ...],
) -> None:
    """Keep every predeclared fold/sensitivity/metric in the family denominator."""

    if any(
        item.metric.metric_name not in family.metric_names
        or item.metric.slice_kind not in family.slice_kinds
        for item in metrics
    ):
        raise ValueError("Family Evaluation produced an unfrozen hypothesis dimension")
    fold_partitions = tuple(
        sorted(
            {(item.fold, item.partition) for item in family.windows},
            key=lambda item: (item[0], item[1].value),
        )
    )
    expected_all = {
        (
            target,
            fold,
            partition,
            sensitivity,
            metric_name,
        )
        for target in family.target_references
        for fold, partition in fold_partitions
        for sensitivity in family.sensitivity_return_multipliers
        for metric_name in family.metric_names
    }
    actual_all = [
        (
            item.target_reference,
            item.metric.fold,
            item.metric.partition,
            item.metric.sensitivity_return_multiplier,
            item.metric.metric_name,
        )
        for item in metrics
        if item.metric.slice_kind == "ALL" and item.metric.slice_value == "ALL"
    ]
    if len(actual_all) != len(set(actual_all)) or set(actual_all) != expected_all:
        raise ValueError("Family Evaluation omitted a frozen ALL-slice hypothesis")
    grouped: dict[tuple[object, ...], set[str]] = {}
    for item in metrics:
        key = (
            item.target_reference,
            item.metric.fold,
            item.metric.partition,
            item.metric.sensitivity_return_multiplier,
            item.metric.slice_kind,
            item.metric.slice_value,
        )
        grouped.setdefault(key, set()).add(item.metric.metric_name)
    if any(names != set(family.metric_names) for names in grouped.values()):
        raise ValueError("Family Evaluation slice omitted a frozen metric")


def _family_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "frozen-hypothesis-family/v1",
        "formal_protocol_reference": values["formal_protocol_reference"].to_canonical_dict(),
        "evaluation_protocol_reference": values["evaluation_protocol_reference"].to_canonical_dict(),
        "target_protocol_reference": values["target_protocol_reference"].to_canonical_dict(),
        "target_references": [item.to_canonical_dict() for item in values["target_references"]],
        "hypothesis_family_key": values["hypothesis_family_key"],
        "multiple_testing_method": values["multiple_testing_method"].value,
        "windows": [_window_payload(item) for item in values["windows"]],
        "sensitivity_return_multipliers": [str(item) for item in values["sensitivity_return_multipliers"]],
        "metric_names": list(values["metric_names"]),
        "slice_kinds": list(values["slice_kinds"]),
        "evaluation_implementation_identity": values[
            "evaluation_implementation_identity"
        ],
        "frozen_at": timestamp(values["frozen_at"]),
    }


def _family_result_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "formal-hypothesis-family-evaluation-result/v1",
        "family_reference": values["family_reference"].to_canonical_dict(),
        "evaluation_protocol_reference": values["evaluation_protocol_reference"].to_canonical_dict(),
        "pit_evidence_reference": (
            None
            if values["pit_evidence_reference"] is None
            else values["pit_evidence_reference"].to_canonical_dict()
        ),
        "metrics": [item.to_canonical_dict() for item in values["metrics"]],
        "excluded_observation_ids": list(values["excluded_observation_ids"]),
        "authority": values["authority"].value,
        "formal_oos": values["formal_oos"],
        "reason_codes": list(values["reason_codes"]),
        "created_at": timestamp(values["created_at"]),
        "limitations": list(values["limitations"]),
    }


def _target_consumption_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "locked-oos-target-observation-consumption/v1",
        "raw_evidence_identity_hash": values["raw_evidence_identity_hash"],
        "family_reference": values["family_reference"].to_canonical_dict(),
        "target_reference": values["target_reference"].to_canonical_dict(),
        "forecast_reference": values["forecast_reference"].to_canonical_dict(),
        "label_reference": values["label_reference"].to_canonical_dict(),
        "observation_set_reference": values[
            "observation_set_reference"
        ].to_canonical_dict(),
        "consumed_at": timestamp(values["consumed_at"]),
    }


def _metric_payload(item: EvaluationMetric) -> dict[str, Any]:
    return {
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


def _metric_from_payload(value: Mapping[str, Any]) -> EvaluationMetric:
    def optional_decimal(name: str) -> Decimal | None:
        raw = value[name]
        return None if raw is None else Decimal(str(raw))

    return EvaluationMetric(
        fold=int(value["fold"]),
        partition=EvaluationPartition(str(value["partition"])),
        sensitivity_return_multiplier=Decimal(
            str(value["sensitivity_return_multiplier"])
        ),
        metric_name=str(value["metric_name"]),
        slice_kind=str(value["slice_kind"]),
        slice_value=str(value["slice_value"]),
        sample_count=int(value["sample_count"]),
        status=EvaluationMetricStatus(str(value["status"])),
        estimate=optional_decimal("estimate"),
        confidence_low=optional_decimal("confidence_low"),
        confidence_high=optional_decimal("confidence_high"),
        raw_p_value=optional_decimal("raw_p_value"),
        adjusted_p_value=optional_decimal("adjusted_p_value"),
        hypothesis_family_id=str(value["hypothesis_family_id"]),
        reason_codes=tuple(str(item) for item in _sequence(value["reason_codes"])),
    )


def _window_payload(item: EvaluationWindow) -> dict[str, Any]:
    return {
        "window_id": item.window_id,
        "partition": item.partition.value,
        "start_date": item.start_date.isoformat(),
        "end_date": item.end_date.isoformat(),
        "fold": item.fold,
    }


def _window_from_dict(value: Mapping[str, Any]) -> EvaluationWindow:
    return EvaluationWindow(
        window_id=str(value["window_id"]),
        partition=EvaluationPartition(str(value["partition"])),
        start_date=date.fromisoformat(str(value["start_date"])),
        end_date=date.fromisoformat(str(value["end_date"])),
        fold=int(value["fold"]),
    )


def _required_decimal(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("estimated Family metric is missing raw p-value")
    return value


def _reference_key(item: ValidationArtifactReference) -> tuple[str, str, str]:
    return item.artifact_kind, str(item.artifact_id), item.content_hash


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Frozen Family payload value must be an object")
    return value


def _sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Frozen Family payload value must be an array")
    return tuple(value)


__all__ = [
    "FamilyEvaluationInput",
    "FamilyEvaluationMetric",
    "FamilyEvaluationObservationBindings",
    "FormalHypothesisFamilyEvaluationResult",
    "FrozenHypothesisFamily",
    "LockedOOSTargetObservationConsumption",
    "RawOOSEvidenceIdentity",
    "run_formal_hypothesis_family_evaluation",
]
