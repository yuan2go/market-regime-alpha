"""Closed Target Definition vocabulary owned by Research & Qualification."""

from enum import StrEnum


class TargetRegistrationStatus(StrEnum):
    REGISTERED = "REGISTERED"


class TargetInstrumentScope(StrEnum):
    A_SHARE_EQUITY = "A_SHARE_EQUITY"


class TargetMarketScope(StrEnum):
    SSE_SZSE = "SSE_SZSE"


class TargetCheckpointRole(StrEnum):
    DECISION_REFERENCE = "DECISION_REFERENCE"
    OUTCOME_OBSERVATION = "OUTCOME_OBSERVATION"


class TargetTimingRule(StrEnum):
    SESSION_LOCAL_BAR_END = "SESSION_LOCAL_BAR_END"


class TargetReferenceRule(StrEnum):
    EXACT_SESSION_BAR = "EXACT_SESSION_BAR"


class TargetBarTimeframe(StrEnum):
    MINUTE_1 = "MINUTE_1"
    MINUTE_5 = "MINUTE_5"
    MINUTE_15 = "MINUTE_15"
    MINUTE_30 = "MINUTE_30"
    MINUTE_60 = "MINUTE_60"
    DAILY = "DAILY"


class TargetPriceBasis(StrEnum):
    RAW_UNADJUSTED = "RAW_UNADJUSTED"
    FORWARD_ADJUSTED = "FORWARD_ADJUSTED"
    BACKWARD_ADJUSTED = "BACKWARD_ADJUSTED"


class TargetValueField(StrEnum):
    OPEN = "OPEN"
    HIGH = "HIGH"
    LOW = "LOW"
    CLOSE = "CLOSE"


class TargetAvailabilityRule(StrEnum):
    EXACT_REVISION_OR_SOURCE_GAP = "EXACT_REVISION_OR_SOURCE_GAP"


class TargetFinalityRule(StrEnum):
    RECORD_UNKNOWN = "RECORD_UNKNOWN"


class TargetMetricKind(StrEnum):
    SIMPLE_RETURN = "SIMPLE_RETURN"
    MAX_FAVORABLE_EXCURSION = "MAX_FAVORABLE_EXCURSION"
    MAX_ADVERSE_EXCURSION = "MAX_ADVERSE_EXCURSION"
    BARRIER_HIT = "BARRIER_HIT"
    OBSERVATION_VALUE = "OBSERVATION_VALUE"


class TargetValueType(StrEnum):
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"


class TargetMetricUnit(StrEnum):
    RATIO = "RATIO"
    PRICE = "PRICE"
    BOOLEAN = "BOOLEAN"


class TargetCompletionRule(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class TargetBarrierDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class TargetDependencyRole(StrEnum):
    REFERENCE = "REFERENCE"
    OBSERVATION = "OBSERVATION"
    PATH_MEMBER = "PATH_MEMBER"


__all__ = [
    "TargetAvailabilityRule",
    "TargetBarTimeframe",
    "TargetBarrierDirection",
    "TargetCheckpointRole",
    "TargetCompletionRule",
    "TargetDependencyRole",
    "TargetFinalityRule",
    "TargetInstrumentScope",
    "TargetMarketScope",
    "TargetMetricKind",
    "TargetMetricUnit",
    "TargetPriceBasis",
    "TargetReferenceRule",
    "TargetRegistrationStatus",
    "TargetTimingRule",
    "TargetValueField",
    "TargetValueType",
]
