"""Stable public exports for Selection Core domain."""

from market_regime_alpha.selection.domain.evidence import (
    CriterionEvidence,
    MarketLineage,
    MembershipEvidence,
)
from market_regime_alpha.selection.domain.model import (
    EligibilityPolicy,
    EligibilityRule,
    UniverseDefinition,
    UniverseScopeSpecification,
)
from market_regime_alpha.selection.domain.results import (
    EligibilityAssessmentDecision,
    EligibilityBatch,
    EligibilityReasonDecision,
    FrozenUniverse,
    UniverseMemberDecision,
)
from market_regime_alpha.selection.domain.vocabulary import (
    CriterionOperator,
    CriterionResult,
    CriterionValueKind,
    EligibilityRuleKind,
    EligibilityStatus,
    MarketEvidenceStatus,
    UniverseMembershipStatus,
)

__all__ = [
    "CriterionEvidence",
    "CriterionOperator",
    "CriterionResult",
    "CriterionValueKind",
    "EligibilityAssessmentDecision",
    "EligibilityBatch",
    "EligibilityPolicy",
    "EligibilityReasonDecision",
    "EligibilityRule",
    "EligibilityRuleKind",
    "EligibilityStatus",
    "FrozenUniverse",
    "MarketEvidenceStatus",
    "MarketLineage",
    "MembershipEvidence",
    "UniverseDefinition",
    "UniverseMemberDecision",
    "UniverseMembershipStatus",
    "UniverseScopeSpecification",
]
