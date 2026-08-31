"""Closed vocabulary for Market Target Outcome facts."""

from enum import StrEnum


class OutcomeStatus(StrEnum):
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class OutcomeAvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class OutcomeFinalityStatus(StrEnum):
    UNKNOWN = "UNKNOWN"


class OutcomeReferenceValueStatus(StrEnum):
    PRESENT = "PRESENT"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class OutcomeSourceKind(StrEnum):
    TRADING_SESSION = "TRADING_SESSION"
    BAR_REVISION = "BAR_REVISION"
    SOURCE_GAP = "SOURCE_GAP"


class OutcomeGapKind(StrEnum):
    MISSING = "MISSING"
    PLACEHOLDER = "PLACEHOLDER"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    CONFLICT = "CONFLICT"
    INVALID_OHLC = "INVALID_OHLC"


class OutcomeMetricKind(StrEnum):
    SIMPLE_RETURN = "SIMPLE_RETURN"
    MAX_FAVORABLE_EXCURSION = "MAX_FAVORABLE_EXCURSION"
    MAX_ADVERSE_EXCURSION = "MAX_ADVERSE_EXCURSION"
    BARRIER_HIT = "BARRIER_HIT"
    OBSERVATION_VALUE = "OBSERVATION_VALUE"


class OutcomeValueType(StrEnum):
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"


class OutcomeCompletionRule(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class OutcomeDependencyRole(StrEnum):
    REFERENCE = "REFERENCE"
    OBSERVATION = "OBSERVATION"
    PATH_MEMBER = "PATH_MEMBER"


class OutcomeBarrierDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class OutcomeValueField(StrEnum):
    OPEN = "OPEN"
    HIGH = "HIGH"
    LOW = "LOW"
    CLOSE = "CLOSE"


class OutcomeReasonDimension(StrEnum):
    REVISION = "REVISION"
    OBSERVATION = "OBSERVATION"
    METRIC = "METRIC"
    SOURCE = "SOURCE"


class OutcomeMismatchKind(StrEnum):
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    MISSING_ROW = "MISSING_ROW"
    EXTRA_ROW = "EXTRA_ROW"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    COUNT_MISMATCH = "COUNT_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    REVISION_CHAIN_MISMATCH = "REVISION_CHAIN_MISMATCH"
    CUTOFF_MISMATCH = "CUTOFF_MISMATCH"
    REFERENCE_MISMATCH = "REFERENCE_MISMATCH"
    SOURCE_STATE_MISMATCH = "SOURCE_STATE_MISMATCH"
    METRIC_VALUE_MISMATCH = "METRIC_VALUE_MISMATCH"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    REASON_MISMATCH = "REASON_MISMATCH"
    RUNTIME_IDENTITY_MISMATCH = "RUNTIME_IDENTITY_MISMATCH"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    IMMUTABLE_FACT_MUTATION = "IMMUTABLE_FACT_MUTATION"


__all__ = [
    "OutcomeAvailabilityStatus",
    "OutcomeBarrierDirection",
    "OutcomeCompletionRule",
    "OutcomeDependencyRole",
    "OutcomeFinalityStatus",
    "OutcomeGapKind",
    "OutcomeMetricKind",
    "OutcomeMismatchKind",
    "OutcomeReasonDimension",
    "OutcomeReferenceValueStatus",
    "OutcomeSourceKind",
    "OutcomeStatus",
    "OutcomeValueField",
    "OutcomeValueType",
]
