"""Stable public exports for Selection Core domain."""

from market_regime_alpha.selection.domain.candidate_inputs import (
    CandidateArtifactBinding,
    CandidateCellStatus,
    CandidateDatasetPopulation,
    CandidatePopulationCell,
    CandidatePopulationRow,
)
from market_regime_alpha.selection.domain.candidate_policy import (
    CandidateFeatureValueType,
    CandidatePolicy,
    CandidatePolicyComponent,
    DesirabilityDirection,
)
from market_regime_alpha.selection.domain.candidate_ranking import (
    arithmetic_midrank_percentiles,
    build_candidate_set,
    normalize_declared_weights,
    project_exact_values,
)
from market_regime_alpha.selection.domain.candidate_results import (
    CandidateBuildResult,
    CandidateComponentDiagnostic,
    CandidateDisposition,
    CandidateRankingPlan,
    CandidateRankingStatus,
    CandidateRecord,
    CandidateScoreComponentRecord,
    CandidateSetResult,
    candidate_result_content_sha256,
)
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
    "CandidateArtifactBinding",
    "CandidateBuildResult",
    "CandidateCellStatus",
    "CandidateComponentDiagnostic",
    "CandidateDatasetPopulation",
    "CandidateDisposition",
    "CandidateFeatureValueType",
    "CandidatePolicy",
    "CandidatePolicyComponent",
    "CandidatePopulationCell",
    "CandidatePopulationRow",
    "CandidateRankingPlan",
    "CandidateRankingStatus",
    "CandidateRecord",
    "CandidateScoreComponentRecord",
    "CandidateSetResult",
    "candidate_result_content_sha256",
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
    "DesirabilityDirection",
    "arithmetic_midrank_percentiles",
    "build_candidate_set",
    "normalize_declared_weights",
    "project_exact_values",
]
