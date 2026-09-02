"""Typed, immutable Context policy and assessment authority.

Context is a decision-time fact derived only from exact, already-recorded Decision
inputs.  The module deliberately contains no repository or provider seam: callers
must prepare the complete Candidate x metric source roster before reduction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from statistics import median
import re
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_REQUEST_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class ContextKind(StrEnum):
    MARKET_REGIME = "MARKET_REGIME"
    ETF_ROTATION = "ETF_ROTATION"
    THEME_ROTATION = "THEME_ROTATION"
    CAPITAL_BREADTH = "CAPITAL_BREADTH"


class ContextMeasure(StrEnum):
    RETURN = "RETURN"
    ADVANCE_RATE = "ADVANCE_RATE"
    TURNOVER = "TURNOVER"
    MEMBER_COVERAGE = "MEMBER_COVERAGE"
    FLOW_PROXY = "FLOW_PROXY"


class ContextReducer(StrEnum):
    MEAN_DECIMAL = "MEAN_DECIMAL"
    MEDIAN_DECIMAL = "MEDIAN_DECIMAL"
    SUM_DECIMAL = "SUM_DECIMAL"
    TRUE_RATE = "TRUE_RATE"


class ContextOperator(StrEnum):
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"
    BETWEEN = "BETWEEN"


class ContextMissingnessPolicy(StrEnum):
    UNKNOWN = "UNKNOWN"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    FAILED = "FAILED"


class ContextSourceKind(StrEnum):
    MARKET_BAR = "BAR_REVISION"
    SOURCE_GAP = "SOURCE_GAP"


class ContextSourceRole(StrEnum):
    PRIMARY_DECISION_REFERENCE = "PRIMARY_DECISION_REFERENCE"


class ContextSourceValueStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class ContextMetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    FAILED = "FAILED"


class ContextState(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"


def _typed(value: object, expected: type[StrEnum], label: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{label} must be typed")


def _sha256(value: str, label: str) -> str:
    try:
        return str(ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256") from exc


def _finite(value: Decimal | None, label: str) -> Decimal | None:
    if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
        raise ValueError(f"{label} must be a finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class DecisionArtifactBinding:
    artifact_id: UUID
    content_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            _sha256(self.content_sha256, "artifact content hash"),
        )
        if isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("artifact size must be non-negative")


@dataclass(frozen=True, slots=True)
class ContextMetricDefinition:
    context_policy_metric_id: UUID
    context_policy_id: UUID
    metric_code: str
    ordinal: int
    context_kind: ContextKind
    measure: ContextMeasure
    reducer: ContextReducer
    operator: ContextOperator
    lower_threshold: Decimal
    upper_threshold: Decimal | None
    minimum_source_count: int
    minimum_available_count: int
    missingness_policy: ContextMissingnessPolicy
    source_role: ContextSourceRole
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.metric_code):
            raise ValueError("Context metric code is invalid")
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Context metric ordinal must be positive")
        _typed(self.context_kind, ContextKind, "Context kind")
        _typed(self.measure, ContextMeasure, "Context measure")
        _typed(self.reducer, ContextReducer, "Context reducer")
        _typed(self.operator, ContextOperator, "Context operator")
        _typed(
            self.missingness_policy,
            ContextMissingnessPolicy,
            "Context missingness policy",
        )
        _typed(self.source_role, ContextSourceRole, "Context source role")
        boolean_measure = self.measure in {
            ContextMeasure.ADVANCE_RATE,
            ContextMeasure.MEMBER_COVERAGE,
        }
        if boolean_measure and self.reducer is not ContextReducer.TRUE_RATE:
            raise ValueError("BOOLEAN measure requires TRUE_RATE reducer")
        if not boolean_measure and self.reducer is ContextReducer.TRUE_RATE:
            raise ValueError("DECIMAL measure cannot use TRUE_RATE reducer")
        _finite(self.lower_threshold, "Context lower threshold")
        _finite(self.upper_threshold, "Context upper threshold")
        if self.operator is ContextOperator.BETWEEN:
            if self.upper_threshold is None:
                raise ValueError("BETWEEN requires an upper threshold")
            if self.lower_threshold > self.upper_threshold:
                raise ValueError("BETWEEN thresholds are out of order")
        elif self.upper_threshold is not None:
            raise ValueError("upper threshold is only valid for BETWEEN")
        if isinstance(self.minimum_source_count, bool) or self.minimum_source_count < 0:
            raise ValueError("minimum source count must be non-negative")
        if (
            isinstance(self.minimum_available_count, bool)
            or self.minimum_available_count < 0
        ):
            raise ValueError("minimum available count must be non-negative")
        if self.minimum_available_count > self.minimum_source_count > 0:
            raise ValueError("minimum available count cannot exceed minimum source count")
        object.__setattr__(self, "content_sha256", canonical_json_sha256(self._payload()))

    @property
    def value_type(self) -> str:
        return (
            "BOOLEAN"
            if self.reducer is ContextReducer.TRUE_RATE
            else "DECIMAL"
        )

    def _payload(self) -> dict[str, object]:
        return {
            "context_kind": self.context_kind,
            "context_policy_id": self.context_policy_id,
            "context_policy_metric_id": self.context_policy_metric_id,
            "lower_threshold": self.lower_threshold,
            "measure": self.measure,
            "metric_code": self.metric_code,
            "minimum_available_count": self.minimum_available_count,
            "minimum_source_count": self.minimum_source_count,
            "missingness_policy": self.missingness_policy,
            "operator": self.operator,
            "ordinal": self.ordinal,
            "reducer": self.reducer,
            "source_role": self.source_role,
            "upper_threshold": self.upper_threshold,
        }


@dataclass(frozen=True, slots=True)
class ContextPolicyPlan:
    context_policy_id: UUID
    policy_code: str
    version: int
    supersedes_policy_id: UUID | None
    metrics: tuple[ContextMetricDefinition, ...]
    code_artifact: DecisionArtifactBinding
    config_artifact: DecisionArtifactBinding
    provenance_sha256: str
    metric_count: int = field(init=False)
    kind_count: int = field(init=False)
    metric_roster_sha256: str = field(init=False)
    kind_roster_sha256: str = field(init=False)
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.policy_code):
            raise ValueError("Context policy code is invalid")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("Context policy version must be positive")
        if (self.version == 1) != (self.supersedes_policy_id is None):
            raise ValueError("Context policy predecessor shape is invalid")
        if not self.metrics:
            raise ValueError("Context policy metric roster must be non-empty")
        if tuple(item.ordinal for item in self.metrics) != tuple(
            range(1, len(self.metrics) + 1)
        ):
            raise ValueError("Context metric ordinals must be contiguous")
        metric_ids = tuple(item.context_policy_metric_id for item in self.metrics)
        metric_codes = tuple(item.metric_code for item in self.metrics)
        if len(set(metric_ids)) != len(metric_ids) or len(set(metric_codes)) != len(
            metric_codes
        ):
            raise ValueError("Context policy contains a duplicate metric")
        if any(item.context_policy_id != self.context_policy_id for item in self.metrics):
            raise ValueError("Context metric belongs to a different policy")
        provenance = _sha256(self.provenance_sha256, "Context policy provenance")
        object.__setattr__(self, "provenance_sha256", provenance)
        metric_roster = tuple(
            {
                "content_sha256": item.content_sha256,
                "context_policy_metric_id": item.context_policy_metric_id,
                "ordinal": item.ordinal,
            }
            for item in self.metrics
        )
        kinds = tuple(dict.fromkeys(item.context_kind for item in self.metrics))
        kind_roster = tuple(
            {"context_kind": kind, "ordinal": ordinal}
            for ordinal, kind in enumerate(kinds, start=1)
        )
        metric_hash = canonical_json_sha256(metric_roster)
        kind_hash = canonical_json_sha256(kind_roster)
        object.__setattr__(self, "metric_count", len(self.metrics))
        object.__setattr__(self, "kind_count", len(kinds))
        object.__setattr__(self, "metric_roster_sha256", metric_hash)
        object.__setattr__(self, "kind_roster_sha256", kind_hash)
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "code_artifact": self.code_artifact,
                    "config_artifact": self.config_artifact,
                    "context_policy_id": self.context_policy_id,
                    "kind_count": len(kinds),
                    "kind_roster_sha256": kind_hash,
                    "metric_count": len(self.metrics),
                    "metric_roster_sha256": metric_hash,
                    "policy_code": self.policy_code,
                    "provenance_sha256": provenance,
                    "supersedes_policy_id": self.supersedes_policy_id,
                    "version": self.version,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class PreparedContextSource:
    context_policy_metric_id: UUID
    candidate_id: UUID
    instrument_id: UUID
    source_kind: ContextSourceKind
    source_ordinal: int
    decision_reference_observation_id: UUID
    bar_revision_id: UUID | None
    source_gap_id: UUID | None
    known_at: datetime
    value_status: ContextSourceValueStatus
    decimal_value: Decimal | None
    boolean_value: bool | None

    def __post_init__(self) -> None:
        _typed(self.source_kind, ContextSourceKind, "Context source kind")
        _typed(self.value_status, ContextSourceValueStatus, "Context source status")
        if isinstance(self.source_ordinal, bool) or self.source_ordinal < 1:
            raise ValueError("Context source ordinal must be positive")
        if self.source_kind is ContextSourceKind.MARKET_BAR:
            if self.bar_revision_id is None or self.source_gap_id is not None:
                raise ValueError("Market bar Context source requires exact bar revision")
        elif self.source_gap_id is None or self.bar_revision_id is not None:
            raise ValueError("Source gap Context source requires exact gap")
        object.__setattr__(
            self,
            "known_at",
            require_utc(self.known_at, field="Context source known_at"),
        )
        _finite(self.decimal_value, "Context source decimal value")
        if self.boolean_value is not None and not isinstance(self.boolean_value, bool):
            raise TypeError("Context source boolean value must be bool")
        value_count = int(self.decimal_value is not None) + int(
            self.boolean_value is not None
        )
        if self.value_status is ContextSourceValueStatus.AVAILABLE:
            if value_count != 1:
                raise ValueError("available Context source requires exactly one value")
        elif value_count:
            raise ValueError("unavailable Context source cannot carry a value")

    def validate_for_decision_time(self, decision_time: datetime) -> None:
        cutoff = require_utc(decision_time, field="DecisionTime")
        if self.known_at > cutoff:
            raise ValueError("Context source was not known by DecisionTime")


@dataclass(frozen=True, slots=True)
class PreparedContextInputs:
    decision_run_id: UUID
    candidate_set_id: UUID
    candidate_set_content_sha256: str
    candidate_roster_sha256: str
    decision_time: datetime
    candidate_count: int
    policy: ContextPolicyPlan
    sources: tuple[PreparedContextSource, ...]
    source_roster_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_set_content_sha256",
            _sha256(self.candidate_set_content_sha256, "CandidateSet content hash"),
        )
        object.__setattr__(
            self,
            "candidate_roster_sha256",
            _sha256(self.candidate_roster_sha256, "Candidate roster hash"),
        )
        object.__setattr__(
            self,
            "decision_time",
            require_utc(self.decision_time, field="DecisionTime"),
        )
        if isinstance(self.candidate_count, bool) or self.candidate_count < 0:
            raise ValueError("Candidate count must be non-negative")
        expected_total = self.candidate_count * self.policy.metric_count
        if len(self.sources) != expected_total:
            raise ValueError("Context requires the complete Candidate roster per metric")
        expected_candidates: tuple[tuple[UUID, UUID], ...] | None = None
        metric_by_id = {
            item.context_policy_metric_id: item for item in self.policy.metrics
        }
        for metric in self.policy.metrics:
            roster = tuple(
                source
                for source in self.sources
                if source.context_policy_metric_id == metric.context_policy_metric_id
            )
            if len(roster) != self.candidate_count:
                raise ValueError("Context requires the complete Candidate roster per metric")
            if tuple(item.source_ordinal for item in roster) != tuple(
                range(1, self.candidate_count + 1)
            ):
                raise ValueError("Context source ordinals must be contiguous")
            candidates = tuple((item.candidate_id, item.instrument_id) for item in roster)
            if len(set(candidates)) != len(candidates):
                raise ValueError("Context source roster contains a duplicate Candidate")
            if expected_candidates is None:
                expected_candidates = candidates
            elif candidates != expected_candidates:
                raise ValueError("Context requires the complete Candidate roster per metric")
            for source in roster:
                source.validate_for_decision_time(self.decision_time)
                if source.value_status is ContextSourceValueStatus.AVAILABLE:
                    is_boolean = source.boolean_value is not None
                    if (metric.value_type == "BOOLEAN") != is_boolean:
                        raise ValueError("Context source value type conflicts with metric")
        if any(source.context_policy_metric_id not in metric_by_id for source in self.sources):
            raise ValueError("Context source belongs to an undeclared metric")
        object.__setattr__(
            self,
            "source_roster_sha256",
            canonical_json_sha256(
                tuple(
                    {
                        "bar_revision_id": source.bar_revision_id,
                        "boolean_value": source.boolean_value,
                        "candidate_id": source.candidate_id,
                        "context_policy_metric_id": source.context_policy_metric_id,
                        "decimal_value": source.decimal_value,
                        "decision_reference_observation_id": (
                            source.decision_reference_observation_id
                        ),
                        "instrument_id": source.instrument_id,
                        "known_at": source.known_at,
                        "source_gap_id": source.source_gap_id,
                        "source_kind": source.source_kind,
                        "source_ordinal": source.source_ordinal,
                        "value_status": source.value_status,
                    }
                    for source in self.sources
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ContextMetricSourcePlan:
    context_metric_source_id: UUID
    source: PreparedContextSource
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "context_metric_source_id": self.context_metric_source_id,
                    "source": self.source,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ContextMetricPlan:
    context_metric_id: UUID
    definition: ContextMetricDefinition
    status: ContextMetricStatus
    state: ContextState
    decimal_value: Decimal | None
    source_count: int
    available_count: int
    unavailable_count: int
    failed_count: int
    source_roster_sha256: str
    sources: tuple[ContextMetricSourcePlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _typed(self.status, ContextMetricStatus, "Context metric status")
        _typed(self.state, ContextState, "Context metric state")
        _finite(self.decimal_value, "Context metric value")
        object.__setattr__(
            self,
            "source_roster_sha256",
            _sha256(self.source_roster_sha256, "Context metric source roster hash"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "available_count": self.available_count,
                    "context_metric_id": self.context_metric_id,
                    "decimal_value": self.decimal_value,
                    "definition_sha256": self.definition.content_sha256,
                    "failed_count": self.failed_count,
                    "source_count": self.source_count,
                    "source_roster_sha256": self.source_roster_sha256,
                    "state": self.state,
                    "status": self.status,
                    "unavailable_count": self.unavailable_count,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ContextAssessmentPlan:
    context_assessment_id: UUID
    assessment_group_id: UUID
    ordinal: int
    context_kind: ContextKind
    status: ContextMetricStatus
    state: ContextState
    metric_count: int
    metric_roster_sha256: str
    metrics: tuple[ContextMetricPlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metric_roster_sha256",
            _sha256(self.metric_roster_sha256, "Context metric roster hash"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "assessment_group_id": self.assessment_group_id,
                    "context_assessment_id": self.context_assessment_id,
                    "context_kind": self.context_kind,
                    "metric_count": self.metric_count,
                    "metric_roster_sha256": self.metric_roster_sha256,
                    "ordinal": self.ordinal,
                    "state": self.state,
                    "status": self.status,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ContextAssessmentAuthority:
    assessment_group_id: UUID
    decision_run_id: UUID
    context_policy_id: UUID
    context_policy_content_sha256: str
    candidate_set_id: UUID
    candidate_set_content_sha256: str
    candidate_roster_sha256: str
    decision_time: datetime
    candidate_count: int
    request_identity: str
    request_sha256: str
    command_receipt_id: UUID
    recorded_at: datetime
    assessment_count: int
    metric_count: int
    source_count: int
    assessment_roster_sha256: str
    assessments: tuple[ContextAssessmentPlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _REQUEST_IDENTITY.fullmatch(self.request_identity):
            raise ValueError("Context request identity is invalid")
        object.__setattr__(self, "request_sha256", _sha256(self.request_sha256, "request hash"))
        object.__setattr__(
            self,
            "context_policy_content_sha256",
            _sha256(self.context_policy_content_sha256, "Context policy hash"),
        )
        object.__setattr__(
            self,
            "candidate_set_content_sha256",
            _sha256(self.candidate_set_content_sha256, "CandidateSet content hash"),
        )
        object.__setattr__(
            self,
            "candidate_roster_sha256",
            _sha256(self.candidate_roster_sha256, "Candidate roster hash"),
        )
        object.__setattr__(
            self,
            "decision_time",
            require_utc(self.decision_time, field="DecisionTime"),
        )
        if isinstance(self.candidate_count, bool) or self.candidate_count < 0:
            raise ValueError("Candidate count must be non-negative")
        object.__setattr__(
            self,
            "assessment_roster_sha256",
            _sha256(self.assessment_roster_sha256, "Context assessment roster hash"),
        )
        object.__setattr__(
            self,
            "recorded_at",
            require_utc(self.recorded_at, field="Context recorded_at"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "assessment_count": self.assessment_count,
                    "assessment_group_id": self.assessment_group_id,
                    "assessment_roster_sha256": self.assessment_roster_sha256,
                    "candidate_roster_sha256": self.candidate_roster_sha256,
                    "candidate_set_content_sha256": self.candidate_set_content_sha256,
                    "candidate_set_id": self.candidate_set_id,
                    "candidate_count": self.candidate_count,
                    "context_policy_content_sha256": (
                        self.context_policy_content_sha256
                    ),
                    "context_policy_id": self.context_policy_id,
                    "decision_run_id": self.decision_run_id,
                    "decision_time": self.decision_time,
                    "metric_count": self.metric_count,
                    "request_identity": self.request_identity,
                    "request_sha256": self.request_sha256,
                    "source_count": self.source_count,
                }
            ),
        )


def _missing_status(policy: ContextMissingnessPolicy) -> ContextMetricStatus:
    return ContextMetricStatus(policy.value)


def _reduce(
    metric: ContextMetricDefinition,
    available: tuple[PreparedContextSource, ...],
) -> Decimal:
    if metric.reducer is ContextReducer.TRUE_RATE:
        true_count = sum(source.boolean_value is True for source in available)
        return Decimal(true_count) / Decimal(len(available))
    values = tuple(source.decimal_value for source in available)
    decimal_values = tuple(value for value in values if value is not None)
    if metric.reducer is ContextReducer.MEAN_DECIMAL:
        return sum(decimal_values, Decimal("0")) / Decimal(len(decimal_values))
    if metric.reducer is ContextReducer.MEDIAN_DECIMAL:
        return median(decimal_values)
    if metric.reducer is ContextReducer.SUM_DECIMAL:
        return sum(decimal_values, Decimal("0"))
    raise AssertionError("unreachable Context reducer")


def _state(metric: ContextMetricDefinition, value: Decimal) -> ContextState:
    if metric.operator is ContextOperator.AT_LEAST:
        return ContextState.POSITIVE if value >= metric.lower_threshold else ContextState.NEGATIVE
    if metric.operator is ContextOperator.AT_MOST:
        return ContextState.POSITIVE if value <= metric.lower_threshold else ContextState.NEGATIVE
    assert metric.upper_threshold is not None
    return (
        ContextState.POSITIVE
        if metric.lower_threshold <= value <= metric.upper_threshold
        else ContextState.NEGATIVE
    )


def _assessment_status(metrics: tuple[ContextMetricPlan, ...]) -> ContextMetricStatus:
    for status in (
        ContextMetricStatus.FAILED,
        ContextMetricStatus.NOT_ESTIMABLE,
        ContextMetricStatus.UNKNOWN,
    ):
        if any(metric.status is status for metric in metrics):
            return status
    return ContextMetricStatus.AVAILABLE


def _assessment_state(metrics: tuple[ContextMetricPlan, ...]) -> ContextState:
    if any(metric.state is ContextState.UNKNOWN for metric in metrics):
        return ContextState.UNKNOWN
    if any(metric.state is ContextState.NEGATIVE for metric in metrics):
        return ContextState.NEGATIVE
    if all(metric.state is ContextState.POSITIVE for metric in metrics):
        return ContextState.POSITIVE
    return ContextState.NEUTRAL


def build_context_assessment_authority(
    *,
    assessment_group_id: UUID,
    prepared: PreparedContextInputs,
    request_identity: str,
    request_sha256: str,
    command_receipt_id: UUID,
    recorded_at: datetime,
    assessment_id_factory: Callable[[ContextKind, int], UUID],
    metric_id_factory: Callable[[ContextMetricDefinition], UUID],
    source_id_factory: Callable[[ContextMetricDefinition, PreparedContextSource], UUID],
) -> ContextAssessmentAuthority:
    """Reduce a complete frozen source roster into immutable Context authority."""

    metric_plans: dict[UUID, ContextMetricPlan] = {}
    for metric in prepared.policy.metrics:
        sources = tuple(
            source
            for source in prepared.sources
            if source.context_policy_metric_id == metric.context_policy_metric_id
        )
        available = tuple(
            source
            for source in sources
            if source.value_status is ContextSourceValueStatus.AVAILABLE
        )
        unavailable_count = sum(
            source.value_status is ContextSourceValueStatus.UNAVAILABLE
            for source in sources
        )
        failed_count = sum(
            source.value_status is ContextSourceValueStatus.FAILED for source in sources
        )
        source_plans = tuple(
            ContextMetricSourcePlan(
                context_metric_source_id=source_id_factory(metric, source),
                source=source,
            )
            for source in sources
        )
        source_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": source_plan.content_sha256,
                    "context_metric_source_id": source_plan.context_metric_source_id,
                    "ordinal": source_plan.source.source_ordinal,
                }
                for source_plan in source_plans
            )
        )
        insufficient = (
            len(sources) < metric.minimum_source_count
            or len(available) < metric.minimum_available_count
            or failed_count > 0
        )
        if insufficient:
            status = _missing_status(metric.missingness_policy)
            state = ContextState.UNKNOWN
            value = None
        else:
            status = ContextMetricStatus.AVAILABLE
            state = ContextState.NEUTRAL
            value = _reduce(metric, available)
            state = _state(metric, value)
        metric_plans[metric.context_policy_metric_id] = ContextMetricPlan(
            context_metric_id=metric_id_factory(metric),
            definition=metric,
            status=status,
            state=state,
            decimal_value=value,
            source_count=len(sources),
            available_count=len(available),
            unavailable_count=unavailable_count,
            failed_count=failed_count,
            source_roster_sha256=source_hash,
            sources=source_plans,
        )

    kinds = tuple(dict.fromkeys(metric.context_kind for metric in prepared.policy.metrics))
    assessments: list[ContextAssessmentPlan] = []
    for ordinal, kind in enumerate(kinds, start=1):
        metrics = tuple(
            metric_plans[definition.context_policy_metric_id]
            for definition in prepared.policy.metrics
            if definition.context_kind is kind
        )
        metric_roster_sha256 = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": metric.content_sha256,
                    "context_metric_id": metric.context_metric_id,
                    "ordinal": item_ordinal,
                }
                for item_ordinal, metric in enumerate(metrics, start=1)
            )
        )
        assessments.append(
            ContextAssessmentPlan(
                context_assessment_id=assessment_id_factory(kind, ordinal),
                assessment_group_id=assessment_group_id,
                ordinal=ordinal,
                context_kind=kind,
                status=_assessment_status(metrics),
                state=_assessment_state(metrics),
                metric_count=len(metrics),
                metric_roster_sha256=metric_roster_sha256,
                metrics=metrics,
            )
        )
    assessment_tuple = tuple(assessments)
    assessment_roster_sha256 = canonical_json_sha256(
        tuple(
            {
                "content_sha256": assessment.content_sha256,
                "context_assessment_id": assessment.context_assessment_id,
                "ordinal": assessment.ordinal,
            }
            for assessment in assessment_tuple
        )
    )
    return ContextAssessmentAuthority(
        assessment_group_id=assessment_group_id,
        decision_run_id=prepared.decision_run_id,
        context_policy_id=prepared.policy.context_policy_id,
        context_policy_content_sha256=prepared.policy.content_sha256,
        candidate_set_id=prepared.candidate_set_id,
        candidate_set_content_sha256=prepared.candidate_set_content_sha256,
        candidate_roster_sha256=prepared.candidate_roster_sha256,
        decision_time=prepared.decision_time,
        candidate_count=prepared.candidate_count,
        request_identity=request_identity,
        request_sha256=request_sha256,
        command_receipt_id=command_receipt_id,
        recorded_at=recorded_at,
        assessment_count=len(assessment_tuple),
        metric_count=len(metric_plans),
        source_count=len(prepared.sources),
        assessment_roster_sha256=assessment_roster_sha256,
        assessments=assessment_tuple,
    )


__all__ = [
    "ContextAssessmentAuthority",
    "ContextAssessmentPlan",
    "ContextKind",
    "ContextMeasure",
    "ContextMetricDefinition",
    "ContextMetricPlan",
    "ContextMetricSourcePlan",
    "ContextMetricStatus",
    "ContextMissingnessPolicy",
    "ContextOperator",
    "ContextPolicyPlan",
    "ContextReducer",
    "ContextSourceKind",
    "ContextSourceRole",
    "ContextSourceValueStatus",
    "ContextState",
    "DecisionArtifactBinding",
    "PreparedContextInputs",
    "PreparedContextSource",
    "build_context_assessment_authority",
]
