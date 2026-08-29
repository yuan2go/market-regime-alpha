"""Closed Research Definition vocabulary."""

from enum import StrEnum


class FeatureValueType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class FeatureIntervalUnit(StrEnum):
    MINUTE = "MINUTE"
    TRADING_SESSION = "TRADING_SESSION"
    CALENDAR_DAY = "CALENDAR_DAY"


class FeatureSourceRequirement(StrEnum):
    MARKET_BAR_REVISION = "MARKET_BAR_REVISION"
    INSTRUMENT_FACT_REVISION = "INSTRUMENT_FACT_REVISION"
    TRADING_SESSION = "TRADING_SESSION"
    UNIVERSE_MEMBER = "UNIVERSE_MEMBER"
    ELIGIBILITY_ASSESSMENT = "ELIGIBILITY_ASSESSMENT"


class FeatureAvailabilityRule(StrEnum):
    DECISION_VISIBLE_AT_OR_BEFORE = "DECISION_VISIBLE_AT_OR_BEFORE"


class FeatureMissingnessPolicy(StrEnum):
    EXPLICIT_STATUS = "EXPLICIT_STATUS"


class FeatureCellStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICT = "CONFLICT"


class DatasetSourceRole(StrEnum):
    POPULATION = "POPULATION"
    FEATURE_DEFINITION = "FEATURE_DEFINITION"
    MARKET_BAR_REVISION = "MARKET_BAR_REVISION"
    MARKET_INSTRUMENT_FACT_REVISION = "MARKET_INSTRUMENT_FACT_REVISION"
    MARKET_TRADING_SESSION = "MARKET_TRADING_SESSION"
    MARKET_SOURCE_GAP = "MARKET_SOURCE_GAP"
    MARKET_CAPTURE = "MARKET_CAPTURE"


__all__ = [
    "DatasetSourceRole",
    "FeatureAvailabilityRule",
    "FeatureCellStatus",
    "FeatureIntervalUnit",
    "FeatureMissingnessPolicy",
    "FeatureSourceRequirement",
    "FeatureValueType",
]
