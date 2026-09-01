"""Immutable provider-neutral Target Definition aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetAvailabilityRule,
    TargetBarTimeframe,
    TargetBarrierDirection,
    TargetCheckpointRole,
    TargetCompletionRule,
    TargetDependencyRole,
    TargetFinalityRule,
    TargetInstrumentScope,
    TargetMarketScope,
    TargetMetricKind,
    TargetMetricUnit,
    TargetPriceBasis,
    TargetReferenceRule,
    TargetRegistrationStatus,
    TargetTimingRule,
    TargetValueField,
    TargetValueType,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


_IDENTITY_CODE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_ALGORITHM_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _content_hash(value: ContentHash | str) -> ContentHash:
    return value if isinstance(value, ContentHash) else ContentHash(value)


def _require_enum(value: object, expected: type[object], field_name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be {expected.__name__}")


def _require_positive_ordinal(value: int, field_name: str) -> None:
    if isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be positive")


def _artifact_payload(binding: ArtifactBinding) -> dict[str, object]:
    return {
        "artifact_id": binding.artifact_id,
        "content_sha256": str(binding.content_sha256),
        "size_bytes": binding.size_bytes,
    }


def _algorithm_payload(
    binding: TargetAlgorithmBinding,
    *,
    include_content_hash: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "algorithm_code": binding.algorithm_code,
        "algorithm_sha256": str(binding.algorithm_sha256),
        "algorithm_version": binding.algorithm_version,
        "code_artifact": _artifact_payload(binding.code_artifact),
        "config_artifact": _artifact_payload(binding.config_artifact),
    }
    if include_content_hash:
        payload["content_sha256"] = str(binding.content_sha256)
    return payload


@dataclass(frozen=True, slots=True)
class TargetAlgorithmBinding:
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: ContentHash | str
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _IDENTITY_CODE.fullmatch(self.algorithm_code):
            raise ValueError("algorithm_code has an invalid format")
        if not _ALGORITHM_VERSION.fullmatch(self.algorithm_version):
            raise ValueError("algorithm_version has an invalid format")
        algorithm_hash = _content_hash(self.algorithm_sha256)
        object.__setattr__(self, "algorithm_sha256", algorithm_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "algorithm_code": self.algorithm_code,
                        "algorithm_version": self.algorithm_version,
                        "algorithm_sha256": str(algorithm_hash),
                        "code_artifact": _artifact_payload(self.code_artifact),
                        "config_artifact": _artifact_payload(self.config_artifact),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class TargetCheckpoint:
    target_checkpoint_id: UUID
    target_definition_id: UUID
    checkpoint_code: str
    ordinal: int
    role: TargetCheckpointRole
    session_offset: int
    timing_rule: TargetTimingRule
    local_time: time
    timezone_name: str
    timeframe: TargetBarTimeframe
    price_basis: TargetPriceBasis
    value_field: TargetValueField
    reference_rule: TargetReferenceRule
    availability_rule: TargetAvailabilityRule
    finality_rule: TargetFinalityRule
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _IDENTITY_CODE.fullmatch(self.checkpoint_code):
            raise ValueError("checkpoint_code has an invalid format")
        _require_positive_ordinal(self.ordinal, "checkpoint ordinal")
        _require_enum(self.role, TargetCheckpointRole, "role")
        if isinstance(self.session_offset, bool) or self.session_offset < 0:
            raise ValueError("session_offset must be non-negative")
        _require_enum(self.timing_rule, TargetTimingRule, "timing_rule")
        if not isinstance(self.local_time, time) or self.local_time.tzinfo is not None:
            raise ValueError("local_time must be a timezone-naive time")
        if self.local_time.second != 0 or self.local_time.microsecond != 0:
            raise ValueError("local_time must have minute precision")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone_name must identify an IANA timezone") from exc
        _require_enum(self.timeframe, TargetBarTimeframe, "timeframe")
        _require_enum(self.price_basis, TargetPriceBasis, "price_basis")
        _require_enum(self.value_field, TargetValueField, "value_field")
        _require_enum(self.reference_rule, TargetReferenceRule, "reference_rule")
        _require_enum(
            self.availability_rule,
            TargetAvailabilityRule,
            "availability_rule",
        )
        _require_enum(self.finality_rule, TargetFinalityRule, "finality_rule")
        if (
            self.role is TargetCheckpointRole.DECISION_REFERENCE
            and self.session_offset != 0
        ):
            raise ValueError("DECISION_REFERENCE session_offset must be zero")
        if (
            self.role is TargetCheckpointRole.OUTCOME_OBSERVATION
            and self.session_offset < 1
        ):
            raise ValueError("OUTCOME_OBSERVATION session_offset must be positive")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "availability_rule": self.availability_rule,
                        "checkpoint_code": self.checkpoint_code,
                        "finality_rule": self.finality_rule,
                        "local_time": self.local_time.isoformat(),
                        "ordinal": self.ordinal,
                        "price_basis": self.price_basis,
                        "reference_rule": self.reference_rule,
                        "role": self.role,
                        "session_offset": self.session_offset,
                        "timeframe": self.timeframe,
                        "timezone_name": self.timezone_name,
                        "timing_rule": self.timing_rule,
                        "value_field": self.value_field,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class TargetMetricDefinition:
    target_metric_definition_id: UUID
    target_definition_id: UUID
    metric_code: str
    ordinal: int
    metric_kind: TargetMetricKind
    value_type: TargetValueType
    unit: TargetMetricUnit
    completion_rule: TargetCompletionRule
    algorithm: TargetAlgorithmBinding
    barrier_direction: TargetBarrierDirection | None = None
    barrier_threshold: Decimal | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _IDENTITY_CODE.fullmatch(self.metric_code):
            raise ValueError("metric_code has an invalid format")
        _require_positive_ordinal(self.ordinal, "metric ordinal")
        _require_enum(self.metric_kind, TargetMetricKind, "metric_kind")
        _require_enum(self.value_type, TargetValueType, "value_type")
        _require_enum(self.unit, TargetMetricUnit, "unit")
        _require_enum(self.completion_rule, TargetCompletionRule, "completion_rule")
        if not isinstance(self.algorithm, TargetAlgorithmBinding):
            raise TypeError("algorithm must be TargetAlgorithmBinding")
        if self.metric_kind is TargetMetricKind.BARRIER_HIT:
            if not isinstance(self.barrier_direction, TargetBarrierDirection):
                raise ValueError("BARRIER_HIT requires barrier_direction")
            if (
                not isinstance(self.barrier_threshold, Decimal)
                or not self.barrier_threshold.is_finite()
                or self.barrier_threshold <= 0
            ):
                raise ValueError("BARRIER_HIT requires a positive barrier_threshold")
            if (
                self.value_type is not TargetValueType.BOOLEAN
                or self.unit is not TargetMetricUnit.BOOLEAN
            ):
                raise ValueError("BARRIER_HIT must use BOOLEAN value and unit")
        elif self.barrier_direction is not None or self.barrier_threshold is not None:
            raise ValueError("non-barrier metrics cannot carry barrier semantics")
        elif self.metric_kind in {
            TargetMetricKind.SIMPLE_RETURN,
            TargetMetricKind.MAX_FAVORABLE_EXCURSION,
            TargetMetricKind.MAX_ADVERSE_EXCURSION,
        } and (
            self.value_type is not TargetValueType.DECIMAL
            or self.unit is not TargetMetricUnit.RATIO
        ):
            raise ValueError("return/excursion metrics must use DECIMAL RATIO")
        elif self.metric_kind is TargetMetricKind.OBSERVATION_VALUE and (
            self.value_type is not TargetValueType.DECIMAL
            or self.unit is not TargetMetricUnit.PRICE
        ):
            raise ValueError("OBSERVATION_VALUE must use DECIMAL PRICE")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "algorithm": _algorithm_payload(
                            self.algorithm,
                            include_content_hash=True,
                        ),
                        "barrier_direction": self.barrier_direction,
                        "barrier_threshold": self.barrier_threshold,
                        "completion_rule": self.completion_rule,
                        "metric_code": self.metric_code,
                        "metric_kind": self.metric_kind,
                        "ordinal": self.ordinal,
                        "unit": self.unit,
                        "value_type": self.value_type,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class TargetMetricDependency:
    target_metric_dependency_id: UUID
    target_definition_id: UUID
    target_metric_definition_id: UUID
    target_checkpoint_id: UUID
    ordinal: int
    role: TargetDependencyRole
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        _require_positive_ordinal(self.ordinal, "dependency ordinal")
        _require_enum(self.role, TargetDependencyRole, "role")
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "ordinal": self.ordinal,
                        "role": self.role,
                        "target_checkpoint_id": self.target_checkpoint_id,
                        "target_metric_definition_id": (
                            self.target_metric_definition_id
                        ),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    target_definition_id: UUID
    target_code: str
    version: int
    supersedes_target_definition_id: UUID | None
    instrument_scope: TargetInstrumentScope
    market_scope: TargetMarketScope
    algorithm: TargetAlgorithmBinding
    checkpoints: tuple[TargetCheckpoint, ...]
    metrics: tuple[TargetMetricDefinition, ...]
    dependencies: tuple[TargetMetricDependency, ...]
    registration_status: TargetRegistrationStatus = TargetRegistrationStatus.REGISTERED
    checkpoint_roster_sha256: ContentHash = field(init=False)
    metric_roster_sha256: ContentHash = field(init=False)
    dependency_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if not _IDENTITY_CODE.fullmatch(self.target_code):
            raise ValueError("target_code has an invalid format")
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("TargetDefinition version must be positive")
        if self.version == 1 and self.supersedes_target_definition_id is not None:
            raise ValueError("TargetDefinition version one cannot supersede another")
        if self.version > 1 and self.supersedes_target_definition_id is None:
            raise ValueError("later TargetDefinition versions require supersession")
        if self.supersedes_target_definition_id == self.target_definition_id:
            raise ValueError("TargetDefinition cannot supersede itself")
        _require_enum(self.instrument_scope, TargetInstrumentScope, "instrument_scope")
        _require_enum(self.market_scope, TargetMarketScope, "market_scope")
        _require_enum(
            self.registration_status,
            TargetRegistrationStatus,
            "registration_status",
        )
        if not isinstance(self.algorithm, TargetAlgorithmBinding):
            raise TypeError("algorithm must be TargetAlgorithmBinding")
        self._validate_rosters()

        checkpoint_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(checkpoint.content_sha256),
                        "ordinal": checkpoint.ordinal,
                        "target_checkpoint_id": checkpoint.target_checkpoint_id,
                    }
                    for checkpoint in self.checkpoints
                )
            )
        )
        metric_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(metric.content_sha256),
                        "ordinal": metric.ordinal,
                        "target_metric_definition_id": (
                            metric.target_metric_definition_id
                        ),
                    }
                    for metric in self.metrics
                )
            )
        )
        dependency_hash = ContentHash(
            canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(dependency.content_sha256),
                        "ordinal": dependency.ordinal,
                        "target_metric_dependency_id": (
                            dependency.target_metric_dependency_id
                        ),
                    }
                    for dependency in self.dependencies
                )
            )
        )
        object.__setattr__(self, "checkpoint_roster_sha256", checkpoint_hash)
        object.__setattr__(self, "metric_roster_sha256", metric_hash)
        object.__setattr__(self, "dependency_roster_sha256", dependency_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "algorithm": _algorithm_payload(
                            self.algorithm,
                            include_content_hash=True,
                        ),
                        "checkpoint_count": len(self.checkpoints),
                        "checkpoint_roster_sha256": str(checkpoint_hash),
                        "dependency_count": len(self.dependencies),
                        "dependency_roster_sha256": str(dependency_hash),
                        "instrument_scope": self.instrument_scope,
                        "market_scope": self.market_scope,
                        "metric_count": len(self.metrics),
                        "metric_roster_sha256": str(metric_hash),
                        "registration_status": self.registration_status,
                        "supersedes_target_definition_id": (
                            self.supersedes_target_definition_id
                        ),
                        "target_code": self.target_code,
                        "version": self.version,
                    }
                )
            ),
        )

    def _validate_rosters(self) -> None:
        if not self.checkpoints:
            raise ValueError("TargetDefinition requires checkpoints")
        if not self.metrics:
            raise ValueError("TargetDefinition requires metrics")
        if not self.dependencies:
            raise ValueError("TargetDefinition requires dependencies")
        _require_contiguous(
            tuple(item.ordinal for item in self.checkpoints),
            "checkpoint ordinals",
        )
        _require_contiguous(
            tuple(item.ordinal for item in self.metrics),
            "metric ordinals",
        )
        _require_contiguous(
            tuple(item.ordinal for item in self.dependencies),
            "dependency ordinals",
        )
        if (
            any(
                item.target_definition_id != self.target_definition_id
                for item in self.checkpoints
            )
            or any(
                item.target_definition_id != self.target_definition_id
                for item in self.metrics
            )
            or any(
                item.target_definition_id != self.target_definition_id
                for item in self.dependencies
            )
        ):
            raise ValueError("all Target children must belong to the same Target Definition")
        _require_unique_ids(
            tuple(item.target_checkpoint_id for item in self.checkpoints),
            "checkpoint identities",
        )
        _require_unique_ids(
            tuple(item.target_metric_definition_id for item in self.metrics),
            "metric identities",
        )
        _require_unique_ids(
            tuple(item.target_metric_dependency_id for item in self.dependencies),
            "dependency identities",
        )
        if len(
            {
                item.checkpoint_code
                for item in self.checkpoints
            }
        ) != len(self.checkpoints):
            raise ValueError("checkpoint codes must be unique")
        if len({item.metric_code for item in self.metrics}) != len(self.metrics):
            raise ValueError("metric codes must be unique")
        references = tuple(
            item
            for item in self.checkpoints
            if item.role is TargetCheckpointRole.DECISION_REFERENCE
        )
        if len(references) != 1:
            raise ValueError("TargetDefinition requires exactly one DECISION_REFERENCE")
        if not any(
            item.role is TargetCheckpointRole.OUTCOME_OBSERVATION
            for item in self.checkpoints
        ):
            raise ValueError("TargetDefinition requires an OUTCOME_OBSERVATION")
        if not any(
            item.completion_rule is TargetCompletionRule.REQUIRED
            for item in self.metrics
        ):
            raise ValueError("TargetDefinition requires at least one REQUIRED metric")

        checkpoints = {
            item.target_checkpoint_id: item for item in self.checkpoints
        }
        metrics = {
            item.target_metric_definition_id: item for item in self.metrics
        }
        for dependency in self.dependencies:
            if dependency.target_checkpoint_id not in checkpoints:
                raise ValueError("dependency references an unknown checkpoint")
            if dependency.target_metric_definition_id not in metrics:
                raise ValueError("dependency references an unknown metric")
        dependency_bindings = {
            (
                item.target_metric_definition_id,
                item.target_checkpoint_id,
                item.role,
            )
            for item in self.dependencies
        }
        if len(dependency_bindings) != len(self.dependencies):
            raise ValueError("metric dependency bindings must be unique")
        for metric_id, metric in metrics.items():
            metric_dependencies = tuple(
                item
                for item in self.dependencies
                if item.target_metric_definition_id == metric_id
            )
            if not metric_dependencies:
                raise ValueError("every metric requires dependencies")
            _validate_metric_dependency_shape(metric, metric_dependencies)
            for dependency in metric_dependencies:
                checkpoint = checkpoints[dependency.target_checkpoint_id]
                if (
                    dependency.role is TargetDependencyRole.REFERENCE
                    and checkpoint.role is not TargetCheckpointRole.DECISION_REFERENCE
                ):
                    raise ValueError("REFERENCE dependency must bind the reference checkpoint")
                if (
                    dependency.role in {
                        TargetDependencyRole.OBSERVATION,
                        TargetDependencyRole.PATH_MEMBER,
                    }
                    and checkpoint.role is not TargetCheckpointRole.OUTCOME_OBSERVATION
                ):
                    raise ValueError(
                        "OBSERVATION/PATH_MEMBER dependency must bind an outcome checkpoint"
                    )


def _validate_metric_dependency_shape(
    metric: TargetMetricDefinition,
    dependencies: tuple[TargetMetricDependency, ...],
) -> None:
    roles = tuple(item.role for item in dependencies)
    if metric.metric_kind is TargetMetricKind.SIMPLE_RETURN:
        if (
            len(roles) != 2
            or roles.count(TargetDependencyRole.REFERENCE) != 1
            or roles.count(TargetDependencyRole.OBSERVATION) != 1
        ):
            raise ValueError(
                "SIMPLE_RETURN requires REFERENCE and OBSERVATION dependencies; "
                "dependency shape is exactly one of each"
            )
        return
    if metric.metric_kind is TargetMetricKind.OBSERVATION_VALUE:
        if roles != (TargetDependencyRole.OBSERVATION,):
            raise ValueError(
                "OBSERVATION_VALUE dependency shape requires exactly one OBSERVATION"
            )
        return
    if (
        roles.count(TargetDependencyRole.REFERENCE) != 1
        or roles.count(TargetDependencyRole.PATH_MEMBER) < 1
        or any(
            role
            not in {
                TargetDependencyRole.REFERENCE,
                TargetDependencyRole.PATH_MEMBER,
            }
            for role in roles
        )
    ):
        raise ValueError(
            f"{metric.metric_kind.value} dependency shape requires exactly one "
            "REFERENCE and at least one PATH_MEMBER"
        )


def _require_contiguous(values: tuple[int, ...], field_name: str) -> None:
    if values != tuple(range(1, len(values) + 1)):
        raise ValueError(f"{field_name} must be ordered and contiguous")


def _require_unique_ids(values: tuple[UUID, ...], field_name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be unique")


__all__ = [
    "TargetAlgorithmBinding",
    "TargetCheckpoint",
    "TargetDefinition",
    "TargetMetricDefinition",
    "TargetMetricDependency",
]
