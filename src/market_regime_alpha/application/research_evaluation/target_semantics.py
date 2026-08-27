"""Frozen, content-addressed Target semantics shared by independent readers.

The specification declares meaning only. Historical materialization and the
independent correctness checker remain responsible for separate owner reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.market_data.contracts import (
    canonical_decimal,
    parse_canonical_decimal,
)


TARGET_SEMANTIC_SCHEMA_V1 = "target-semantic-specification/v1"
WP_ALPHA_CORRECTNESS_02_SEMANTIC_REVISION = (
    "wp-alpha-correctness-02-target-semantics/v1"
)


class TargetSemanticStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class BarrierOrderingOutcome(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_TOUCH = "NO_TOUCH"
    UP_FIRST = "UP_FIRST"
    DOWN_FIRST = "DOWN_FIRST"
    AMBIGUOUS_NOT_OBSERVABLE = "AMBIGUOUS_NOT_OBSERVABLE"


@dataclass(frozen=True, slots=True)
class TargetSemanticSpecification:
    specification_id: ArtifactId
    specification_hash: str
    semantic_revision: str
    timezone_name: str
    decision_reference_local_time: str
    outcome_window_start_local_time: str
    source_timeframe: str
    accepted_raw_adjustment_bases: tuple[str, ...]
    exact_point_partial_allowed: bool
    schema_version: str = TARGET_SEMANTIC_SCHEMA_V1

    def __post_init__(self) -> None:
        if self.schema_version != TARGET_SEMANTIC_SCHEMA_V1:
            raise ValueError("unsupported Target semantic specification schema")
        require_sha256("specification_hash", self.specification_hash)
        for label, value in (
            ("semantic_revision", self.semantic_revision),
            ("timezone_name", self.timezone_name),
            ("decision_reference_local_time", self.decision_reference_local_time),
            ("outcome_window_start_local_time", self.outcome_window_start_local_time),
            ("source_timeframe", self.source_timeframe),
        ):
            require_text(label, value)
        if self.accepted_raw_adjustment_bases != tuple(
            sorted(set(self.accepted_raw_adjustment_bases))
        ):
            raise ValueError("Target raw adjustment bases must be unique and sorted")
        if not self.accepted_raw_adjustment_bases:
            raise ValueError("Target semantics require a Raw adjustment basis")
        if self.exact_point_partial_allowed:
            raise ValueError("exact Decision reference cannot permit PARTIAL")
        digest = canonical_hash(self.identity_payload())
        if digest != self.specification_hash:
            raise ValueError("Target semantic specification hash mismatch")
        if self.specification_id != ArtifactId(
            f"target-semantic-specification:{digest[7:]}"
        ):
            raise ValueError("Target semantic specification identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        semantic_revision: str,
        timezone_name: str,
        decision_reference_local_time: str,
        outcome_window_start_local_time: str,
        source_timeframe: str,
        accepted_raw_adjustment_bases: tuple[str, ...],
        exact_point_partial_allowed: bool,
    ) -> TargetSemanticSpecification:
        normalized_adjustment_bases = tuple(
            sorted(set(accepted_raw_adjustment_bases))
        )
        values = {
            "semantic_revision": semantic_revision,
            "timezone_name": timezone_name,
            "decision_reference_local_time": decision_reference_local_time,
            "outcome_window_start_local_time": outcome_window_start_local_time,
            "source_timeframe": source_timeframe,
            "accepted_raw_adjustment_bases": normalized_adjustment_bases,
            "exact_point_partial_allowed": exact_point_partial_allowed,
            "schema_version": TARGET_SEMANTIC_SCHEMA_V1,
        }
        digest = canonical_hash(_specification_payload(**values))
        return cls(
            specification_id=ArtifactId(
                f"target-semantic-specification:{digest[7:]}"
            ),
            specification_hash=digest,
            semantic_revision=semantic_revision,
            timezone_name=timezone_name,
            decision_reference_local_time=decision_reference_local_time,
            outcome_window_start_local_time=outcome_window_start_local_time,
            source_timeframe=source_timeframe,
            accepted_raw_adjustment_bases=normalized_adjustment_bases,
            exact_point_partial_allowed=exact_point_partial_allowed,
            schema_version=TARGET_SEMANTIC_SCHEMA_V1,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "TARGET_SEMANTIC_SPECIFICATION",
            self.specification_id,
            self.specification_hash,
        )

    def identity_payload(self) -> dict[str, object]:
        return _specification_payload(
            semantic_revision=self.semantic_revision,
            timezone_name=self.timezone_name,
            decision_reference_local_time=self.decision_reference_local_time,
            outcome_window_start_local_time=self.outcome_window_start_local_time,
            source_timeframe=self.source_timeframe,
            accepted_raw_adjustment_bases=self.accepted_raw_adjustment_bases,
            exact_point_partial_allowed=self.exact_point_partial_allowed,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "specification_id": str(self.specification_id),
            "specification_hash": self.specification_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> TargetSemanticSpecification:
        return cls(
            specification_id=ArtifactId(str(payload["specification_id"])),
            specification_hash=str(payload["specification_hash"]),
            semantic_revision=str(payload["semantic_revision"]),
            timezone_name=str(payload["timezone_name"]),
            decision_reference_local_time=str(
                payload["decision_reference_local_time"]
            ),
            outcome_window_start_local_time=str(
                payload["outcome_window_start_local_time"]
            ),
            source_timeframe=str(payload["source_timeframe"]),
            accepted_raw_adjustment_bases=_strings(
                payload["accepted_raw_adjustment_bases"]
            ),
            exact_point_partial_allowed=_boolean(
                payload["exact_point_partial_allowed"]
            ),
            schema_version=str(payload["schema_version"]),
        )


def wp_alpha_correctness_02_target_semantic_specification(
) -> TargetSemanticSpecification:
    return TargetSemanticSpecification.create(
        semantic_revision=WP_ALPHA_CORRECTNESS_02_SEMANTIC_REVISION,
        timezone_name="Asia/Shanghai",
        decision_reference_local_time="14:55:00",
        outcome_window_start_local_time="09:30:00",
        source_timeframe="MINUTE_5",
        accepted_raw_adjustment_bases=(
            "BAOSTOCK_ADJUSTFLAG_3_RAW",
            "RAW_UNADJUSTED",
        ),
        exact_point_partial_allowed=False,
    )


@dataclass(frozen=True, slots=True)
class TargetSemanticResult:
    semantic_specification: ValidationArtifactReference
    symbol: str
    decision_time: datetime
    target_session: date
    outcome_window_start: datetime
    outcome_window_end: datetime
    expected_outcome_bar_count: int
    observed_outcome_bar_count: int
    decision_reference_status: TargetSemanticStatus
    outcome_window_status: TargetSemanticStatus
    checkpoint_observation_status: TargetSemanticStatus
    checkpoint_return_status: TargetSemanticStatus
    mfe_status: TargetSemanticStatus
    mae_status: TargetSemanticStatus
    barrier_status: TargetSemanticStatus
    decision_reference_price: Decimal | None
    checkpoint_price: Decimal | None
    checkpoint_return: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    barrier_passages: tuple[tuple[str, datetime | None], ...]
    barrier_ordering: BarrierOrderingOutcome
    decision_source_references: tuple[ValidationArtifactReference, ...]
    outcome_source_references: tuple[ValidationArtifactReference, ...]
    diagnostic_source_references: tuple[ValidationArtifactReference, ...]
    reason_codes: tuple[str, ...]
    schema_version: str = "target-semantic-result/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "target-semantic-result/v1":
            raise ValueError("unsupported Target semantic result schema")
        if self.semantic_specification.artifact_kind != (
            "TARGET_SEMANTIC_SPECIFICATION"
        ):
            raise ValueError("Target result requires a semantic specification")
        require_text("symbol", self.symbol)
        for label, value in (
            ("decision_time", self.decision_time),
            ("outcome_window_start", self.outcome_window_start),
            ("outcome_window_end", self.outcome_window_end),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} must be timezone-aware")
        if (
            not self.decision_time < self.outcome_window_start
            or self.outcome_window_end < self.outcome_window_start
            or self.expected_outcome_bar_count < 0
            or self.observed_outcome_bar_count < 0
            or self.observed_outcome_bar_count > self.expected_outcome_bar_count
        ):
            raise ValueError("Target outcome coverage is invalid")
        if self.decision_reference_status is TargetSemanticStatus.PARTIAL:
            raise ValueError("exact Decision reference cannot be PARTIAL")
        _validate_status_value(
            "decision_reference", self.decision_reference_status, self.decision_reference_price
        )
        _validate_status_value(
            "checkpoint_observation",
            self.checkpoint_observation_status,
            self.checkpoint_price,
        )
        _validate_status_value(
            "checkpoint_return", self.checkpoint_return_status, self.checkpoint_return
        )
        _validate_status_value("mfe", self.mfe_status, self.mfe)
        _validate_status_value("mae", self.mae_status, self.mae)
        if self.checkpoint_return is not None:
            assert self.decision_reference_price is not None
            assert self.checkpoint_price is not None
            expected = (
                self.checkpoint_price - self.decision_reference_price
            ) / self.decision_reference_price
            if self.checkpoint_return != expected:
                raise ValueError("Target checkpoint return arithmetic mismatch")
        if self.outcome_window_status is TargetSemanticStatus.COMPLETE and (
            self.observed_outcome_bar_count != self.expected_outcome_bar_count
        ):
            raise ValueError("complete Target window requires the exact grid")
        if self.outcome_window_status is TargetSemanticStatus.PARTIAL and not (
            0 < self.observed_outcome_bar_count < self.expected_outcome_bar_count
        ):
            raise ValueError("partial Target window requires a proper subset")
        if self.outcome_window_status is TargetSemanticStatus.UNAVAILABLE and (
            self.observed_outcome_bar_count != 0
        ):
            raise ValueError("unavailable Target window cannot contain valid bars")
        if (
            self.barrier_passages
            != tuple(sorted(self.barrier_passages, key=lambda item: item[0]))
            or len({item[0] for item in self.barrier_passages})
            != len(self.barrier_passages)
        ):
            raise ValueError("Target barrier passages must be sorted")
        for barrier_id, passage_at in self.barrier_passages:
            require_text("barrier_id", barrier_id)
            if passage_at is not None and (
                passage_at.tzinfo is None
                or passage_at.utcoffset() is None
                or not self.outcome_window_start
                < passage_at
                <= self.outcome_window_end
            ):
                raise ValueError("Target barrier passage time is invalid")
        if (
            self.barrier_status is TargetSemanticStatus.PARTIAL
        ) != (
            self.barrier_ordering
            is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
        ):
            raise ValueError("Target barrier ambiguity/status mismatch")
        if self.barrier_status in {
            TargetSemanticStatus.UNAVAILABLE,
            TargetSemanticStatus.FAILED,
        } and (
            self.barrier_ordering is not BarrierOrderingOutcome.NOT_APPLICABLE
            or any(item[1] is not None for item in self.barrier_passages)
        ):
            raise ValueError("unavailable Target barriers cannot invent passages")
        source_groups = (
            self.decision_source_references,
            self.outcome_source_references,
            self.diagnostic_source_references,
        )
        for values in source_groups:
            if len(values) != len(set(values)) or any(
                item.artifact_kind != "HISTORICAL_NORMALIZED_BAR" for item in values
            ):
                raise ValueError("Target source lineage is invalid")
        if set(self.decision_source_references).intersection(
            self.outcome_source_references
        ) or sum(len(values) for values in source_groups) != len(
            set().union(*source_groups)
        ):
            raise ValueError("Target source lineage groups must be disjoint")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Target semantic reasons must be unique and sorted")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "semantic_specification": self.semantic_specification.to_canonical_dict(),
            "symbol": self.symbol,
            "decision_time": canonical_datetime(self.decision_time),
            "target_session": self.target_session.isoformat(),
            "outcome_window_start": canonical_datetime(self.outcome_window_start),
            "outcome_window_end": canonical_datetime(self.outcome_window_end),
            "expected_outcome_bar_count": self.expected_outcome_bar_count,
            "observed_outcome_bar_count": self.observed_outcome_bar_count,
            "decision_reference_status": self.decision_reference_status.value,
            "outcome_window_status": self.outcome_window_status.value,
            "checkpoint_observation_status": self.checkpoint_observation_status.value,
            "checkpoint_return_status": self.checkpoint_return_status.value,
            "mfe_status": self.mfe_status.value,
            "mae_status": self.mae_status.value,
            "barrier_status": self.barrier_status.value,
            "decision_reference_price": _optional_decimal(
                self.decision_reference_price
            ),
            "checkpoint_price": _optional_decimal(self.checkpoint_price),
            "checkpoint_return": _optional_decimal(self.checkpoint_return),
            "mfe": _optional_decimal(self.mfe),
            "mae": _optional_decimal(self.mae),
            "barrier_passages": [
                {
                    "barrier_id": barrier_id,
                    "first_passage_at": (
                        None if instant is None else canonical_datetime(instant)
                    ),
                }
                for barrier_id, instant in self.barrier_passages
            ],
            "barrier_ordering": self.barrier_ordering.value,
            "decision_source_references": [
                item.to_canonical_dict()
                for item in self.decision_source_references
            ],
            "outcome_source_references": [
                item.to_canonical_dict() for item in self.outcome_source_references
            ],
            "diagnostic_source_references": [
                item.to_canonical_dict()
                for item in self.diagnostic_source_references
            ],
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TargetSemanticResult:
        return cls(
            semantic_specification=ValidationArtifactReference.from_canonical_dict(
                _mapping(payload["semantic_specification"])
            ),
            symbol=str(payload["symbol"]),
            decision_time=_instant(payload["decision_time"]),
            target_session=date.fromisoformat(str(payload["target_session"])),
            outcome_window_start=_instant(payload["outcome_window_start"]),
            outcome_window_end=_instant(payload["outcome_window_end"]),
            expected_outcome_bar_count=int(payload["expected_outcome_bar_count"]),
            observed_outcome_bar_count=int(payload["observed_outcome_bar_count"]),
            decision_reference_status=TargetSemanticStatus(
                str(payload["decision_reference_status"])
            ),
            outcome_window_status=TargetSemanticStatus(
                str(payload["outcome_window_status"])
            ),
            checkpoint_observation_status=TargetSemanticStatus(
                str(payload["checkpoint_observation_status"])
            ),
            checkpoint_return_status=TargetSemanticStatus(
                str(payload["checkpoint_return_status"])
            ),
            mfe_status=TargetSemanticStatus(str(payload["mfe_status"])),
            mae_status=TargetSemanticStatus(str(payload["mae_status"])),
            barrier_status=TargetSemanticStatus(str(payload["barrier_status"])),
            decision_reference_price=_parse_optional_decimal(
                payload["decision_reference_price"]
            ),
            checkpoint_price=_parse_optional_decimal(payload["checkpoint_price"]),
            checkpoint_return=_parse_optional_decimal(payload["checkpoint_return"]),
            mfe=_parse_optional_decimal(payload["mfe"]),
            mae=_parse_optional_decimal(payload["mae"]),
            barrier_passages=tuple(
                (
                    str(item["barrier_id"]),
                    None
                    if item["first_passage_at"] is None
                    else _instant(item["first_passage_at"]),
                )
                for item in _mappings(payload["barrier_passages"])
            ),
            barrier_ordering=BarrierOrderingOutcome(
                str(payload["barrier_ordering"])
            ),
            decision_source_references=_references(
                payload["decision_source_references"]
            ),
            outcome_source_references=_references(
                payload["outcome_source_references"]
            ),
            diagnostic_source_references=_references(
                payload["diagnostic_source_references"]
            ),
            reason_codes=_strings(payload["reason_codes"]),
            schema_version=str(payload["schema_version"]),
        )


def _specification_payload(**values: Any) -> dict[str, object]:
    return {
        "schema_version": values["schema_version"],
        "semantic_revision": values["semantic_revision"],
        "timezone_name": values["timezone_name"],
        "decision_reference_local_time": values[
            "decision_reference_local_time"
        ],
        "outcome_window_start_local_time": values[
            "outcome_window_start_local_time"
        ],
        "source_timeframe": values["source_timeframe"],
        "accepted_raw_adjustment_bases": list(
            values["accepted_raw_adjustment_bases"]
        ),
        "exact_point_partial_allowed": values["exact_point_partial_allowed"],
    }


def _validate_status_value(
    label: str, status: TargetSemanticStatus, value: Decimal | None
) -> None:
    if (status is TargetSemanticStatus.COMPLETE) != (value is not None):
        raise ValueError(f"{label} status/value mismatch")
    if value is not None and (not value.is_finite()):
        raise ValueError(f"{label} must be finite")


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _parse_optional_decimal(value: object) -> Decimal | None:
    return None if value is None else parse_canonical_decimal("value", value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("Target semantic boolean must be a bool")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError("Target semantic string array is invalid")
    return tuple(value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("Target semantic object is invalid")
    return value


def _mappings(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise TypeError("Target semantic object array is invalid")
    return tuple(_mapping(item) for item in value)


def _references(value: object) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        ValidationArtifactReference.from_canonical_dict(item)
        for item in _mappings(value)
    )


def _instant(value: object) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Target semantic instant must be timezone-aware")
    return result


__all__ = [
    "BarrierOrderingOutcome",
    "TARGET_SEMANTIC_SCHEMA_V1",
    "TargetSemanticResult",
    "TargetSemanticSpecification",
    "TargetSemanticStatus",
    "WP_ALPHA_CORRECTNESS_02_SEMANTIC_REVISION",
    "wp_alpha_correctness_02_target_semantic_specification",
]
