"""Immutable input snapshots and calculated Outcome revision draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
import re
from typing import TypeAlias
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_regime_alpha.outcome.domain.vocabulary import (
    OutcomeAvailabilityStatus,
    OutcomeBarrierDirection,
    OutcomeCompletionRule,
    OutcomeDependencyRole,
    OutcomeFinalityStatus,
    OutcomeGapKind,
    OutcomeMetricKind,
    OutcomeReasonDimension,
    OutcomeReferenceValueStatus,
    OutcomeSourceKind,
    OutcomeStatus,
    OutcomeValueField,
    OutcomeValueType,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_ALGORITHM_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _sha(value: str, field_name: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256")
    return value


def _positive_decimal(value: Decimal, field_name: str) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be finite and positive")
    return value


@dataclass(frozen=True, slots=True)
class FrozenDecisionReference:
    decision_reference_observation_id: UUID
    content_sha256: str
    value_status: OutcomeReferenceValueStatus
    availability_status: OutcomeAvailabilityStatus
    finality_status: OutcomeFinalityStatus
    decimal_value: Decimal | None

    def __post_init__(self) -> None:
        _sha(self.content_sha256, "Decision reference hash")
        expected_availability = {
            OutcomeReferenceValueStatus.PRESENT: OutcomeAvailabilityStatus.AVAILABLE,
            OutcomeReferenceValueStatus.UNAVAILABLE: OutcomeAvailabilityStatus.UNAVAILABLE,
            OutcomeReferenceValueStatus.FAILED: OutcomeAvailabilityStatus.FAILED,
        }[self.value_status]
        if self.availability_status is not expected_availability:
            raise ValueError("Decision reference value and availability states differ")
        if self.finality_status is not OutcomeFinalityStatus.UNKNOWN:
            raise ValueError("WP-10 accepts only UNKNOWN Decision reference finality")
        if self.value_status is OutcomeReferenceValueStatus.PRESENT:
            if self.decimal_value is None:
                raise ValueError("present Decision reference requires a value")
            _positive_decimal(self.decimal_value, "Decision reference value")
        elif self.decimal_value is not None:
            raise ValueError("unavailable/failed Decision reference cannot carry a value")


@dataclass(frozen=True, slots=True)
class OutcomeCheckpoint:
    target_checkpoint_id: UUID
    content_sha256: str
    ordinal: int
    checkpoint_code: str
    session_offset: int
    local_time: time
    timezone_name: str
    timeframe: str
    price_basis: str
    value_field: OutcomeValueField

    def __post_init__(self) -> None:
        _sha(self.content_sha256, "Outcome checkpoint hash")
        if self.ordinal < 1 or self.session_offset < 1:
            raise ValueError("Outcome checkpoint ordinal/session offset must be positive")
        if not _CODE.fullmatch(self.checkpoint_code):
            raise ValueError("Outcome checkpoint code has an invalid format")
        if self.local_time.tzinfo is not None:
            raise ValueError("Outcome checkpoint local_time must be timezone-naive")
        if self.local_time.second or self.local_time.microsecond:
            raise ValueError("Outcome checkpoint local_time must have minute precision")
        try:
            ZoneInfo(self.timezone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Outcome checkpoint timezone is invalid") from exc
        if self.timeframe not in {
            "MINUTE_1",
            "MINUTE_5",
            "MINUTE_15",
            "MINUTE_30",
            "MINUTE_60",
            "DAILY",
        }:
            raise ValueError("Outcome checkpoint timeframe is invalid")
        if self.price_basis not in {
            "RAW_UNADJUSTED",
            "FORWARD_ADJUSTED",
            "BACKWARD_ADJUSTED",
        }:
            raise ValueError("Outcome checkpoint price basis is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeMetricDefinition:
    target_metric_definition_id: UUID
    ordinal: int
    metric_code: str
    metric_kind: OutcomeMetricKind
    value_type: OutcomeValueType
    unit: str
    completion_rule: OutcomeCompletionRule
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: str
    code_artifact_id: UUID
    code_content_sha256: str
    code_size_bytes: int
    config_artifact_id: UUID
    config_content_sha256: str
    config_size_bytes: int
    content_sha256: str
    barrier_direction: OutcomeBarrierDirection | None = None
    barrier_threshold: Decimal | None = None

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not _CODE.fullmatch(self.metric_code):
            raise ValueError("Outcome metric ordinal/code is invalid")
        if not _CODE.fullmatch(self.algorithm_code):
            raise ValueError("Outcome metric algorithm code is invalid")
        if not _ALGORITHM_VERSION.fullmatch(self.algorithm_version):
            raise ValueError("Outcome metric algorithm version is invalid")
        _sha(self.algorithm_sha256, "metric algorithm hash")
        _sha(self.code_content_sha256, "metric code artifact hash")
        _sha(self.config_content_sha256, "metric config artifact hash")
        _sha(self.content_sha256, "metric definition hash")
        if self.code_size_bytes < 0 or self.config_size_bytes < 0:
            raise ValueError("metric artifact sizes must be non-negative")
        expected_shape = {
            OutcomeMetricKind.SIMPLE_RETURN: (OutcomeValueType.DECIMAL, "RATIO"),
            OutcomeMetricKind.MAX_FAVORABLE_EXCURSION: (
                OutcomeValueType.DECIMAL,
                "RATIO",
            ),
            OutcomeMetricKind.MAX_ADVERSE_EXCURSION: (
                OutcomeValueType.DECIMAL,
                "RATIO",
            ),
            OutcomeMetricKind.OBSERVATION_VALUE: (
                OutcomeValueType.DECIMAL,
                "PRICE",
            ),
            OutcomeMetricKind.BARRIER_HIT: (OutcomeValueType.BOOLEAN, "BOOLEAN"),
        }[self.metric_kind]
        if (self.value_type, self.unit) != expected_shape:
            raise ValueError("Outcome metric value type/unit disagrees with kind")
        if self.metric_kind is OutcomeMetricKind.BARRIER_HIT:
            if self.barrier_direction is None or self.barrier_threshold is None:
                raise ValueError("barrier metric requires direction and threshold")
            _positive_decimal(self.barrier_threshold, "barrier threshold")
        elif self.barrier_direction is not None or self.barrier_threshold is not None:
            raise ValueError("non-barrier metric cannot carry barrier fields")


@dataclass(frozen=True, slots=True)
class OutcomeMetricDependency:
    target_metric_dependency_id: UUID
    ordinal: int
    target_metric_definition_id: UUID
    target_checkpoint_id: UUID
    role: OutcomeDependencyRole
    content_sha256: str

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise ValueError("Outcome dependency ordinal must be positive")
        _sha(self.content_sha256, "metric dependency hash")


@dataclass(frozen=True, slots=True)
class OutcomeTargetDefinition:
    target_definition_id: UUID
    target_code: str
    version: int
    content_sha256: str
    reference_checkpoint_id: UUID
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: str
    code_artifact_id: UUID
    code_content_sha256: str
    code_size_bytes: int
    config_artifact_id: UUID
    config_content_sha256: str
    config_size_bytes: int
    checkpoints: tuple[OutcomeCheckpoint, ...]
    metrics: tuple[OutcomeMetricDefinition, ...]
    dependencies: tuple[OutcomeMetricDependency, ...]

    def __post_init__(self) -> None:
        if self.version < 1 or not _CODE.fullmatch(self.target_code):
            raise ValueError("Outcome Target identity/version is invalid")
        if not _CODE.fullmatch(self.algorithm_code):
            raise ValueError("Outcome Target algorithm code is invalid")
        if not _ALGORITHM_VERSION.fullmatch(self.algorithm_version):
            raise ValueError("Outcome Target algorithm version is invalid")
        for label, value in (
            ("Target hash", self.content_sha256),
            ("Target algorithm hash", self.algorithm_sha256),
            ("Target code artifact hash", self.code_content_sha256),
            ("Target config artifact hash", self.config_content_sha256),
        ):
            _sha(value, label)
        if self.code_size_bytes < 0 or self.config_size_bytes < 0:
            raise ValueError("Target artifact sizes must be non-negative")
        if not self.checkpoints or not self.metrics or not self.dependencies:
            raise ValueError("Outcome Target requires complete non-empty rosters")
        _ordered_unique(
            tuple(item.ordinal for item in self.checkpoints),
            "checkpoints",
        )
        _contiguous(tuple(item.ordinal for item in self.metrics), "metrics")
        _contiguous(tuple(item.ordinal for item in self.dependencies), "dependencies")
        checkpoints = {item.target_checkpoint_id: item for item in self.checkpoints}
        metrics = {item.target_metric_definition_id: item for item in self.metrics}
        if len(checkpoints) != len(self.checkpoints) or len(metrics) != len(self.metrics):
            raise ValueError("Outcome Target child identities must be unique")
        seen_bindings: set[tuple[UUID, UUID, OutcomeDependencyRole]] = set()
        by_metric: dict[UUID, list[OutcomeMetricDependency]] = {
            metric_id: [] for metric_id in metrics
        }
        for dependency in self.dependencies:
            if dependency.target_metric_definition_id not in metrics:
                raise ValueError("Outcome dependency references an unknown metric")
            if dependency.role is OutcomeDependencyRole.REFERENCE:
                if dependency.target_checkpoint_id != self.reference_checkpoint_id:
                    raise ValueError("REFERENCE must bind the frozen reference checkpoint")
            elif dependency.target_checkpoint_id not in checkpoints:
                raise ValueError("Outcome dependency references an unknown checkpoint")
            key = (
                dependency.target_metric_definition_id,
                dependency.target_checkpoint_id,
                dependency.role,
            )
            if key in seen_bindings:
                raise ValueError("Outcome dependency bindings must be unique")
            seen_bindings.add(key)
            by_metric[dependency.target_metric_definition_id].append(dependency)
        for metric_id, metric in metrics.items():
            _validate_metric_dependencies(metric, tuple(by_metric[metric_id]))


def _contiguous(values: tuple[int, ...], label: str) -> None:
    if values != tuple(range(1, len(values) + 1)):
        raise ValueError(f"Outcome Target {label} must be ordered and contiguous")


def _ordered_unique(values: tuple[int, ...], label: str) -> None:
    if any(value < 1 for value in values) or values != tuple(sorted(set(values))):
        raise ValueError(f"Outcome Target {label} must preserve strict Target order")


def _validate_metric_dependencies(
    metric: OutcomeMetricDefinition,
    dependencies: tuple[OutcomeMetricDependency, ...],
) -> None:
    roles = tuple(item.role for item in dependencies)
    if metric.metric_kind is OutcomeMetricKind.SIMPLE_RETURN and sorted(roles) != sorted(
        (OutcomeDependencyRole.REFERENCE, OutcomeDependencyRole.OBSERVATION)
    ):
        raise ValueError("SIMPLE_RETURN requires one REFERENCE and one OBSERVATION")
    if metric.metric_kind is OutcomeMetricKind.OBSERVATION_VALUE and roles != (
        OutcomeDependencyRole.OBSERVATION,
    ):
        raise ValueError("OBSERVATION_VALUE requires one OBSERVATION")
    if metric.metric_kind in {
        OutcomeMetricKind.MAX_FAVORABLE_EXCURSION,
        OutcomeMetricKind.MAX_ADVERSE_EXCURSION,
        OutcomeMetricKind.BARRIER_HIT,
    } and (
        roles.count(OutcomeDependencyRole.REFERENCE) != 1
        or roles.count(OutcomeDependencyRole.PATH_MEMBER) < 1
        or any(
            item not in {
                OutcomeDependencyRole.REFERENCE,
                OutcomeDependencyRole.PATH_MEMBER,
            }
            for item in roles
        )
    ):
        raise ValueError(f"{metric.metric_kind.value} requires REFERENCE plus PATH_MEMBER")


@dataclass(frozen=True, slots=True)
class OutcomeSessionSource:
    session_id: UUID
    session_offset: int
    exchange: str
    session_date: date
    timezone_name: str
    open_at: datetime
    close_at: datetime
    source_capture_id: UUID
    provider_product_id: UUID
    recorded_at: datetime
    known_at: datetime
    source_kind: OutcomeSourceKind = field(
        default=OutcomeSourceKind.TRADING_SESSION,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.session_offset < 1 or not self.exchange:
            raise ValueError("Outcome Session offset/exchange is invalid")
        _utc(self.open_at, "Session open")
        _utc(self.close_at, "Session close")
        _utc(self.recorded_at, "Session recorded_at")
        _utc(self.known_at, "Session known_at")
        if not self.open_at < self.close_at or self.known_at < self.recorded_at:
            raise ValueError("Outcome Session temporal order is invalid")
        try:
            ZoneInfo(self.timezone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Outcome Session timezone is invalid") from exc


@dataclass(frozen=True, slots=True)
class OutcomeBarSource:
    bar_revision_id: UUID
    target_checkpoint_id: UUID
    source_ordinal: int
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID
    session_id: UUID
    timeframe: str
    price_basis: str
    event_start: datetime
    event_end: datetime
    revision: int
    recorded_at: datetime
    known_at: datetime
    open_value: Decimal
    high_value: Decimal
    low_value: Decimal
    close_value: Decimal
    source_kind: OutcomeSourceKind = field(
        default=OutcomeSourceKind.BAR_REVISION,
        init=False,
    )

    def __post_init__(self) -> None:
        _validate_observation_source(self)
        if self.revision < 1:
            raise ValueError("Outcome bar revision must be positive")
        values = (
            self.open_value,
            self.high_value,
            self.low_value,
            self.close_value,
        )
        for value in values:
            _positive_decimal(value, "Outcome OHLC value")
        if self.high_value < max(values) or self.low_value > min(values):
            raise ValueError("Outcome OHLC structure is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeGapSource:
    gap_id: UUID
    target_checkpoint_id: UUID
    source_ordinal: int
    provider_product_id: UUID
    capture_id: UUID
    instrument_id: UUID
    session_id: UUID
    timeframe: str
    price_basis: str
    event_start: datetime
    event_end: datetime
    gap_kind: OutcomeGapKind
    reason_code: str
    recorded_at: datetime
    known_at: datetime
    source_kind: OutcomeSourceKind = field(
        default=OutcomeSourceKind.SOURCE_GAP,
        init=False,
    )

    def __post_init__(self) -> None:
        _validate_observation_source(self)
        if not re.fullmatch(r"^[A-Z][A-Z0-9_]{0,99}$", self.reason_code):
            raise ValueError("Outcome SourceGap reason code is invalid")


OutcomeObservationSource: TypeAlias = OutcomeBarSource | OutcomeGapSource


def _validate_observation_source(value: OutcomeObservationSource) -> None:
    if value.source_ordinal < 1:
        raise ValueError("Outcome source ordinal must be positive")
    _utc(value.event_start, "Outcome source event_start")
    _utc(value.event_end, "Outcome source event_end")
    _utc(value.recorded_at, "Outcome source recorded_at")
    _utc(value.known_at, "Outcome source known_at")
    if (
        value.event_end <= value.event_start
        or value.known_at < value.recorded_at
        or value.known_at < value.event_end
    ):
        raise ValueError("Outcome source temporal order is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeObservationDraft:
    target_checkpoint_id: UUID
    source_kind: OutcomeSourceKind
    source_fact_id: UUID
    status: OutcomeStatus
    availability_status: OutcomeAvailabilityStatus
    finality_status: OutcomeFinalityStatus
    selected_value: Decimal | None
    open_value: Decimal | None
    high_value: Decimal | None
    low_value: Decimal | None
    close_value: Decimal | None
    event_start: datetime
    event_end: datetime
    known_at: datetime
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        for value, label in (
            (self.event_start, "Outcome observation event_start"),
            (self.event_end, "Outcome observation event_end"),
            (self.known_at, "Outcome observation known_at"),
        ):
            _utc(value, label)
        if self.event_end <= self.event_start or self.known_at < self.event_end:
            raise ValueError("Outcome observation temporal order is invalid")
        if self.finality_status is not OutcomeFinalityStatus.UNKNOWN:
            raise ValueError("Outcome observation finality must be UNKNOWN")
        values = (
            self.selected_value,
            self.open_value,
            self.high_value,
            self.low_value,
            self.close_value,
        )
        usable = self.status in {OutcomeStatus.COMPLETE, OutcomeStatus.PARTIAL}
        if usable:
            if (
                self.source_kind is not OutcomeSourceKind.BAR_REVISION
                or self.availability_status is not OutcomeAvailabilityStatus.AVAILABLE
                or any(value is None for value in values)
            ):
                raise ValueError("Outcome observation state shape is invalid")
            present = tuple(value for value in values if value is not None)
            if any(not value.is_finite() or value <= 0 for value in present):
                raise ValueError("Outcome observation state shape is invalid")
            _, open_value, high_value, low_value, close_value = present
            if high_value < max(open_value, low_value, close_value) or low_value > min(
                open_value,
                high_value,
                close_value,
            ):
                raise ValueError("Outcome observation state shape is invalid")
        else:
            expected_availability = {
                OutcomeStatus.UNAVAILABLE: OutcomeAvailabilityStatus.UNAVAILABLE,
                OutcomeStatus.FAILED: OutcomeAvailabilityStatus.FAILED,
            }.get(self.status)
            if (
                expected_availability is None
                or self.source_kind is not OutcomeSourceKind.SOURCE_GAP
                or self.availability_status is not expected_availability
                or any(value is not None for value in values)
            ):
                raise ValueError("Outcome observation state shape is invalid")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    name: getattr(self, name)
                    for name in self.__dataclass_fields__
                    if name != "content_sha256"
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class OutcomeMetricDraft:
    target_metric_definition_id: UUID
    ordinal: int
    metric_code: str
    metric_kind: OutcomeMetricKind
    value_type: OutcomeValueType
    unit: str
    completion_rule: OutcomeCompletionRule
    status: OutcomeStatus
    availability_status: OutcomeAvailabilityStatus
    finality_status: OutcomeFinalityStatus
    decimal_value: Decimal | None
    boolean_value: bool | None
    first_passage_at: datetime | None
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: str
    code_artifact_id: UUID
    code_content_sha256: str
    code_size_bytes: int
    config_artifact_id: UUID
    config_content_sha256: str
    config_size_bytes: int
    target_metric_sha256: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not _CODE.fullmatch(self.metric_code):
            raise ValueError("Outcome metric identity is invalid")
        if not _CODE.fullmatch(self.algorithm_code) or not _ALGORITHM_VERSION.fullmatch(
            self.algorithm_version
        ):
            raise ValueError("Outcome metric algorithm identity is invalid")
        for value, label in (
            (self.algorithm_sha256, "Outcome metric algorithm hash"),
            (self.code_content_sha256, "Outcome metric code hash"),
            (self.config_content_sha256, "Outcome metric config hash"),
            (self.target_metric_sha256, "Outcome Target metric hash"),
        ):
            _sha(value, label)
        if self.code_size_bytes < 0 or self.config_size_bytes < 0:
            raise ValueError("Outcome metric artifact sizes must be non-negative")
        if self.finality_status is not OutcomeFinalityStatus.UNKNOWN:
            raise ValueError("Outcome metric finality must be UNKNOWN")
        usable = self.status in {OutcomeStatus.COMPLETE, OutcomeStatus.PARTIAL}
        if usable:
            typed_value = (
                self.decimal_value is not None and self.boolean_value is None
                if self.value_type is OutcomeValueType.DECIMAL
                else self.decimal_value is None and isinstance(self.boolean_value, bool)
            )
            if (
                self.availability_status is not OutcomeAvailabilityStatus.AVAILABLE
                or not typed_value
                or (
                    self.decimal_value is not None
                    and not self.decimal_value.is_finite()
                )
            ):
                raise ValueError("Outcome metric state shape is invalid")
        else:
            expected_availability = {
                OutcomeStatus.UNAVAILABLE: OutcomeAvailabilityStatus.UNAVAILABLE,
                OutcomeStatus.FAILED: OutcomeAvailabilityStatus.FAILED,
            }.get(self.status)
            if (
                expected_availability is None
                or self.availability_status is not expected_availability
                or self.decimal_value is not None
                or self.boolean_value is not None
                or self.first_passage_at is not None
            ):
                raise ValueError("Outcome metric state shape is invalid")
        if self.first_passage_at is not None:
            _utc(self.first_passage_at, "Outcome metric first passage")
            if self.metric_kind is not OutcomeMetricKind.BARRIER_HIT:
                raise ValueError("Outcome metric first passage requires a barrier")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    name: getattr(self, name)
                    for name in self.__dataclass_fields__
                    if name != "content_sha256"
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class OutcomeReferenceDependencyDraft:
    target_metric_dependency_id: UUID
    target_metric_definition_id: UUID
    target_checkpoint_id: UUID
    dependency_role: OutcomeDependencyRole
    decision_reference_observation_id: UUID

    def __post_init__(self) -> None:
        if self.dependency_role is not OutcomeDependencyRole.REFERENCE:
            raise ValueError("Outcome REFERENCE dependency role is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeObservationDependencyDraft:
    target_metric_dependency_id: UUID
    target_metric_definition_id: UUID
    target_checkpoint_id: UUID
    dependency_role: OutcomeDependencyRole

    def __post_init__(self) -> None:
        if self.dependency_role not in {
            OutcomeDependencyRole.OBSERVATION,
            OutcomeDependencyRole.PATH_MEMBER,
        }:
            raise ValueError("Outcome observation dependency role is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeReasonDraft:
    ordinal: int
    dimension: OutcomeReasonDimension
    reason_code: str
    target_checkpoint_id: UUID | None = None
    target_metric_definition_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not re.fullmatch(
            r"^[A-Z][A-Z0-9_]{0,99}$",
            self.reason_code,
        ):
            raise ValueError("Outcome reason identity is invalid")
        checkpoint_shape = self.target_checkpoint_id is not None
        metric_shape = self.target_metric_definition_id is not None
        valid_shape = {
            OutcomeReasonDimension.REVISION: not checkpoint_shape and not metric_shape,
            OutcomeReasonDimension.SOURCE: checkpoint_shape and not metric_shape,
            OutcomeReasonDimension.OBSERVATION: checkpoint_shape and not metric_shape,
            OutcomeReasonDimension.METRIC: metric_shape and not checkpoint_shape,
        }[self.dimension]
        if not valid_shape:
            raise ValueError("Outcome reason dimension shape is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeRevisionDraft:
    target_definition_id: UUID
    target_definition_sha256: str
    decision_reference_observation_id: UUID
    decision_reference_sha256: str
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    status: OutcomeStatus
    availability_status: OutcomeAvailabilityStatus
    finality_status: OutcomeFinalityStatus
    sessions: tuple[OutcomeSessionSource, ...]
    sources: tuple[OutcomeObservationSource, ...]
    observations: tuple[OutcomeObservationDraft, ...]
    metrics: tuple[OutcomeMetricDraft, ...]
    reference_dependencies: tuple[OutcomeReferenceDependencyDraft, ...]
    observation_dependencies: tuple[OutcomeObservationDependencyDraft, ...]
    reasons: tuple[OutcomeReasonDraft, ...]
    source_roster_sha256: str = field(init=False)
    observation_roster_sha256: str = field(init=False)
    metric_roster_sha256: str = field(init=False)
    reference_dependency_roster_sha256: str = field(init=False)
    observation_dependency_roster_sha256: str = field(init=False)
    reason_roster_sha256: str = field(init=False)
    definition_summary_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _sha(self.target_definition_sha256, "Outcome Target definition hash")
        _sha(self.decision_reference_sha256, "Outcome Decision reference hash")
        _utc(self.observation_cutoff, "Outcome observation cutoff")
        _utc(self.knowledge_cutoff, "Outcome knowledge cutoff")
        if self.finality_status is not OutcomeFinalityStatus.UNKNOWN:
            raise ValueError("Outcome aggregate finality must be UNKNOWN")
        expected_availability = {
            OutcomeStatus.COMPLETE: {OutcomeAvailabilityStatus.AVAILABLE},
            OutcomeStatus.UNAVAILABLE: {OutcomeAvailabilityStatus.UNAVAILABLE},
            OutcomeStatus.FAILED: {OutcomeAvailabilityStatus.FAILED},
            OutcomeStatus.PARTIAL: {
                OutcomeAvailabilityStatus.AVAILABLE,
                OutcomeAvailabilityStatus.UNAVAILABLE,
            },
        }[self.status]
        if self.availability_status not in expected_availability:
            raise ValueError("Outcome aggregate state shape is invalid")
        if (
            not self.sessions
            or not self.sources
            or not self.observations
            or not self.metrics
            or not (self.reference_dependencies or self.observation_dependencies)
        ):
            raise ValueError("Outcome revision requires complete non-empty fact rosters")
        if len(self.sources) != len(self.observations):
            raise ValueError("Outcome source and observation rosters differ")
        if tuple(item.ordinal for item in self.metrics) != tuple(
            range(1, len(self.metrics) + 1)
        ):
            raise ValueError("Outcome metric roster must be ordered and contiguous")
        if self.reasons and tuple(item.ordinal for item in self.reasons) != tuple(
            range(1, len(self.reasons) + 1)
        ):
            raise ValueError("Outcome reason roster must be ordered and contiguous")
        roster_fields = (
            ("source_roster_sha256", (*self.sessions, *self.sources)),
            ("observation_roster_sha256", self.observations),
            ("metric_roster_sha256", self.metrics),
            ("reference_dependency_roster_sha256", self.reference_dependencies),
            ("observation_dependency_roster_sha256", self.observation_dependencies),
            ("reason_roster_sha256", self.reasons),
        )
        for field_name, roster in roster_fields:
            object.__setattr__(self, field_name, canonical_json_sha256(roster))
        object.__setattr__(
            self,
            "definition_summary_sha256",
            canonical_json_sha256(
                {
                    "availability_status": self.availability_status,
                    "decision_reference_observation_id": (
                        self.decision_reference_observation_id
                    ),
                    "decision_reference_sha256": self.decision_reference_sha256,
                    "finality_status": self.finality_status,
                    "knowledge_cutoff": self.knowledge_cutoff,
                    "observation_count": len(self.observations),
                    "observation_cutoff": self.observation_cutoff,
                    "observation_dependency_count": len(
                        self.observation_dependencies
                    ),
                    "reference_dependency_count": len(self.reference_dependencies),
                    "metric_count": len(self.metrics),
                    "reason_count": len(self.reasons),
                    "source_count": len(self.sessions) + len(self.sources),
                    "status": self.status,
                    "target_definition_id": self.target_definition_id,
                    "target_definition_sha256": self.target_definition_sha256,
                    **{name: getattr(self, name) for name, _ in roster_fields},
                }
            ),
        )


__all__ = [
    "FrozenDecisionReference",
    "OutcomeBarSource",
    "OutcomeCheckpoint",
    "OutcomeGapSource",
    "OutcomeMetricDefinition",
    "OutcomeMetricDependency",
    "OutcomeMetricDraft",
    "OutcomeObservationDependencyDraft",
    "OutcomeObservationDraft",
    "OutcomeObservationSource",
    "OutcomeReasonDraft",
    "OutcomeReferenceDependencyDraft",
    "OutcomeRevisionDraft",
    "OutcomeSessionSource",
    "OutcomeTargetDefinition",
]
