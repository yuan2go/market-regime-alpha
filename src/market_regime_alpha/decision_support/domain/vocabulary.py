"""Closed WP-09 Decision Run and reference vocabulary."""

from enum import StrEnum


class DecisionRunStatus(StrEnum):
    OPENED = "OPENED"


class CandidateDisposition(StrEnum):
    SELECTED = "SELECTED"
    RANKED_NOT_SELECTED = "RANKED_NOT_SELECTED"
    UNRANKABLE = "UNRANKABLE"


class DecisionRuntimeMode(StrEnum):
    OPERATIONAL = "OPERATIONAL"
    HISTORICAL = "HISTORICAL"
    REPLAY = "REPLAY"
    SHADOW = "SHADOW"
    PROSPECTIVE = "PROSPECTIVE"


class ResearchPurpose(StrEnum):
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    LOCKED_OOS = "LOCKED_OOS"
    PROSPECTIVE = "PROSPECTIVE"


class QualificationInputRole(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    LIMITATION = "LIMITATION"


class DecisionReferenceSourceKind(StrEnum):
    BAR_REVISION = "BAR_REVISION"
    SOURCE_GAP = "SOURCE_GAP"


class DecisionReferenceValueStatus(StrEnum):
    PRESENT = "PRESENT"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class DecisionReferenceAvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class DecisionReferenceFinalityStatus(StrEnum):
    UNKNOWN = "UNKNOWN"


class DecisionRunMismatchKind(StrEnum):
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    MISSING_ROW = "MISSING_ROW"
    EXTRA_ROW = "EXTRA_ROW"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    COUNT_MISMATCH = "COUNT_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    REFERENCE_STATE_MISMATCH = "REFERENCE_STATE_MISMATCH"
    RUNTIME_IDENTITY_MISMATCH = "RUNTIME_IDENTITY_MISMATCH"
    IMMUTABLE_FACT_MUTATION = "IMMUTABLE_FACT_MUTATION"


__all__ = [
    "CandidateDisposition",
    "DecisionReferenceAvailabilityStatus",
    "DecisionReferenceFinalityStatus",
    "DecisionReferenceSourceKind",
    "DecisionReferenceValueStatus",
    "DecisionRunMismatchKind",
    "DecisionRunStatus",
    "DecisionRuntimeMode",
    "QualificationInputRole",
    "ResearchPurpose",
]
