"""Closed Selection Core vocabularies."""

from enum import StrEnum


class UniverseMembershipStatus(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class CriterionResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class MarketEvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    STALE = "STALE"
    GAP = "GAP"
    CONFLICT = "CONFLICT"


class EligibilityRuleKind(StrEnum):
    NOT_SUSPENDED = "NOT_SUSPENDED"
    NOT_SPECIAL_TREATMENT = "NOT_SPECIAL_TREATMENT"
    MIN_LISTING_AGE = "MIN_LISTING_AGE"
    MIN_LIQUIDITY = "MIN_LIQUIDITY"
    LIMIT_METADATA_PRESENT = "LIMIT_METADATA_PRESENT"


class CriterionValueKind(StrEnum):
    STATUS = "STATUS"
    DECIMAL = "DECIMAL"
    COUNT = "COUNT"
    MISSING = "MISSING"


class CriterionOperator(StrEnum):
    EQ = "EQ"
    GTE = "GTE"


__all__ = [
    "CriterionOperator",
    "CriterionResult",
    "CriterionValueKind",
    "EligibilityRuleKind",
    "EligibilityStatus",
    "MarketEvidenceStatus",
    "UniverseMembershipStatus",
]
