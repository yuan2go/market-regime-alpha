"""Frozen Evaluation Protocol semantics and pure V1 reducers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import re
from statistics import median
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import PartitionPurpose
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    AcceptanceState,
    CandidateDisposition,
    EvaluationInclusionPolicy,
    EvaluationInputState,
    EvaluationMetricState,
    EvaluationMissingnessPolicy,
    EvaluationReducer,
    EvaluationRunStatus,
    EvaluationSliceKind,
    MetricDirection,
    SourceMetricValueType,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_CODE = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


@dataclass(frozen=True, slots=True)
class EvaluationProtocolPlan:
    evaluation_protocol_id: UUID
    protocol_code: str
    protocol_version: int
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    applicable_purpose: PartitionPurpose
    decision_rule: str
    metrics: tuple[ProtocolMetricDefinition, ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    metric_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.protocol_code):
            raise ValueError("protocol_code has an invalid format")
        if not self.decision_rule.strip():
            raise ValueError("decision_rule is required")
        if isinstance(self.protocol_version, bool) or self.protocol_version < 1:
            raise ValueError("protocol_version must be positive")
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        if not self.metrics:
            raise ValueError("EvaluationProtocol requires metrics")
        if tuple(item.ordinal for item in self.metrics) != tuple(range(1, len(self.metrics) + 1)):
            raise ValueError("Protocol metric ordinals must be contiguous")
        if len({item.metric_code for item in self.metrics}) != len(self.metrics):
            raise ValueError("Protocol metric codes must be unique")
        target_hash = ContentHash(str(self.target_definition_sha256))
        provenance_hash = ContentHash(str(self.provenance_sha256))
        roster_hash = ContentHash(canonical_json_sha256(self.metrics))
        object.__setattr__(self, "target_definition_sha256", target_hash)
        object.__setattr__(self, "provenance_sha256", provenance_hash)
        object.__setattr__(self, "metric_roster_sha256", roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "applicable_purpose": self.applicable_purpose,
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "decision_rule": self.decision_rule,
                        "metric_roster_sha256": roster_hash,
                        "protocol_code": self.protocol_code,
                        "protocol_version": self.protocol_version,
                        "provenance_sha256": provenance_hash,
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": target_hash,
                        "target_version": self.target_version,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationRunPlan:
    evaluation_run_id: UUID
    experiment_run_id: UUID
    evaluation_protocol_id: UUID
    requested_knowledge_cutoff: datetime
    request_identity: str

    def __post_init__(self) -> None:
        if not self.request_identity.strip():
            raise ValueError("request_identity is required")


@dataclass(frozen=True, slots=True)
class ProtocolMetricDefinition:
    evaluation_protocol_metric_id: UUID
    metric_code: str
    ordinal: int
    source_target_metric_definition_id: UUID
    source_metric_code: str
    source_value_type: SourceMetricValueType
    reducer: EvaluationReducer
    slice_kind: EvaluationSliceKind
    candidate_disposition: CandidateDisposition | None
    direction: MetricDirection
    minimum_estimable_count: int
    acceptance_operator: AcceptanceOperator
    acceptance_threshold: Decimal | None
    inclusion_policy: EvaluationInclusionPolicy = EvaluationInclusionPolicy.COMPLETE_ONLY
    missingness_policy: EvaluationMissingnessPolicy = EvaluationMissingnessPolicy.RETAIN_AND_ESTIMATE
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.metric_code) or not _CODE.fullmatch(
            self.source_metric_code
        ):
            raise ValueError("metric_code has an invalid format")
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("ordinal must be positive")
        if (
            isinstance(self.minimum_estimable_count, bool)
            or self.minimum_estimable_count < 1
        ):
            raise ValueError("minimum_estimable_count must be positive")
        compatible = {
            EvaluationReducer.MEAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.MEDIAN_DECIMAL: SourceMetricValueType.DECIMAL,
            EvaluationReducer.TRUE_RATE: SourceMetricValueType.BOOLEAN,
        }
        required = compatible.get(self.reducer)
        if required is not None and self.source_value_type is not required:
            raise ValueError("reducer is incompatible with source metric value type")
        if self.slice_kind is EvaluationSliceKind.CANDIDATE_DISPOSITION:
            if self.candidate_disposition is None:
                raise ValueError("candidate_disposition is required for this slice")
        elif self.candidate_disposition is not None:
            raise ValueError("candidate_disposition is forbidden for ALL_MEMBERS")
        if self.acceptance_operator is AcceptanceOperator.NONE:
            if self.acceptance_threshold is not None:
                raise ValueError("descriptive metric cannot have acceptance threshold")
        elif self.acceptance_threshold is None:
            raise ValueError("acceptance threshold is required")
        if self.direction is MetricDirection.DESCRIPTIVE and self.acceptance_operator is not AcceptanceOperator.NONE:
            raise ValueError("descriptive direction requires NONE acceptance")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "acceptance_operator": self.acceptance_operator,
                        "acceptance_threshold": self.acceptance_threshold,
                        "candidate_disposition": self.candidate_disposition,
                        "direction": self.direction,
                        "inclusion_policy": self.inclusion_policy,
                        "metric_code": self.metric_code,
                        "minimum_estimable_count": self.minimum_estimable_count,
                        "missingness_policy": self.missingness_policy,
                        "ordinal": self.ordinal,
                        "reducer": self.reducer,
                        "slice_kind": self.slice_kind,
                        "source_metric_code": self.source_metric_code,
                        "source_target_metric_definition_id": self.source_target_metric_definition_id,
                        "source_value_type": self.source_value_type,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    evaluation_observation_id: UUID
    candidate_disposition: CandidateDisposition
    source_value_status: str
    decimal_value: Decimal | None
    boolean_value: bool | None


@dataclass(frozen=True, slots=True)
class EvaluationMetricObservationResult:
    evaluation_observation_id: UUID
    state: EvaluationInputState
    reason_code: str


@dataclass(frozen=True, slots=True)
class EvaluationMetricResult:
    state: EvaluationMetricState
    decimal_value: Decimal | None
    boolean_value: bool | None
    estimable_count: int
    acceptance_state: AcceptanceState
    observations: tuple[EvaluationMetricObservationResult, ...]


def transition_evaluation_run(
    current: EvaluationRunStatus,
    target: EvaluationRunStatus,
) -> EvaluationRunStatus:
    allowed = {
        EvaluationRunStatus.OPEN: {
            EvaluationRunStatus.INPUTS_ACQUIRED,
            EvaluationRunStatus.FAILED,
        },
        EvaluationRunStatus.INPUTS_ACQUIRED: {
            EvaluationRunStatus.COMPLETED,
            EvaluationRunStatus.FAILED,
        },
        EvaluationRunStatus.COMPLETED: set(),
        EvaluationRunStatus.FAILED: set(),
    }
    if target not in allowed[current]:
        raise ValueError(f"EvaluationRun transition {current} -> {target} is forbidden")
    return target


def evaluate_metric(
    metric: ProtocolMetricDefinition,
    inputs: tuple[EvaluationInput, ...],
) -> EvaluationMetricResult:
    observations: list[EvaluationMetricObservationResult] = []
    included: list[EvaluationInput] = []
    for item in inputs:
        if (
            metric.slice_kind is EvaluationSliceKind.CANDIDATE_DISPOSITION
            and item.candidate_disposition is not metric.candidate_disposition
        ):
            observations.append(
                EvaluationMetricObservationResult(
                    item.evaluation_observation_id,
                    EvaluationInputState.EXCLUDED,
                    "OUTSIDE_DECLARED_SLICE",
                )
            )
            continue
        has_value = (
            item.decimal_value is not None
            if metric.source_value_type is SourceMetricValueType.DECIMAL
            else item.boolean_value is not None
        )
        allowed_status = item.source_value_status == "COMPLETE" or (
            metric.inclusion_policy is EvaluationInclusionPolicy.AVAILABLE_VALUE
            and item.source_value_status == "PARTIAL"
        )
        if not has_value or not allowed_status:
            observations.append(
                EvaluationMetricObservationResult(
                    item.evaluation_observation_id,
                    EvaluationInputState.NOT_ESTIMABLE,
                    f"SOURCE_{item.source_value_status}",
                )
            )
            continue
        included.append(item)
        observations.append(
            EvaluationMetricObservationResult(
                item.evaluation_observation_id,
                EvaluationInputState.INCLUDED,
                "INCLUDED_BY_PROTOCOL",
            )
        )
    complete_required = (
        metric.missingness_policy is EvaluationMissingnessPolicy.REQUIRE_COMPLETE_ROSTER
        and any(item.state is EvaluationInputState.NOT_ESTIMABLE for item in observations)
    )
    if len(included) < metric.minimum_estimable_count or complete_required:
        return EvaluationMetricResult(
            EvaluationMetricState.NOT_ESTIMABLE,
            None,
            None,
            len(included),
            AcceptanceState.NOT_ESTIMABLE,
            tuple(observations),
        )
    values: list[Decimal]
    if metric.reducer is EvaluationReducer.MEAN_DECIMAL:
        values = [item.decimal_value for item in included if item.decimal_value is not None]
        value = sum(values, Decimal(0)) / Decimal(len(values))
    elif metric.reducer is EvaluationReducer.MEDIAN_DECIMAL:
        values = [item.decimal_value for item in included if item.decimal_value is not None]
        value = median(values)
    elif metric.reducer is EvaluationReducer.TRUE_RATE:
        value = Decimal(sum(item.boolean_value is True for item in included)) / Decimal(len(included))
    else:
        eligible_count = sum(
            item.state is not EvaluationInputState.EXCLUDED for item in observations
        )
        value = Decimal(len(included)) / Decimal(eligible_count) if eligible_count else Decimal(0)
    acceptance = _acceptance(metric, value)
    return EvaluationMetricResult(
        EvaluationMetricState.ESTIMATED,
        value,
        None,
        len(included),
        acceptance,
        tuple(observations),
    )


def _acceptance(metric: ProtocolMetricDefinition, value: Decimal) -> AcceptanceState:
    if metric.acceptance_operator is AcceptanceOperator.NONE:
        return AcceptanceState.NOT_APPLICABLE
    threshold = metric.acceptance_threshold
    assert threshold is not None
    accepted = value >= threshold if metric.acceptance_operator is AcceptanceOperator.AT_LEAST else value <= threshold
    return AcceptanceState.ACCEPTED if accepted else AcceptanceState.REJECTED


__all__ = [
    "EvaluationInput",
    "EvaluationMetricObservationResult",
    "EvaluationMetricResult",
    "ProtocolMetricDefinition",
    "EvaluationProtocolPlan",
    "EvaluationRunPlan",
    "evaluate_metric",
    "transition_evaluation_run",
]
