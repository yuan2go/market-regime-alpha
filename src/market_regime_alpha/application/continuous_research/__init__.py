"""PostgreSQL-authoritative continuous research orchestration contracts.

This package owns all-day orchestration only. Provider, Dataset, Feature,
Candidate, Signal, Forecast, Canonical, and execution behavior remain in their
existing bounded contexts.
"""

from market_regime_alpha.application.continuous_research.evidence import (
    CurrentEvidenceSnapshot,
    EvidenceCommit,
    EvidenceCommitResult,
    EvidenceQualityStatus,
    ProviderAttemptOutcome,
    ProviderAttemptSnapshot,
    StartedProviderAttempt,
)
from market_regime_alpha.application.continuous_research.change_detection import (
    ChangeDecision,
    MaterialIdentityInput,
    RecordedChangeDecision,
)
from market_regime_alpha.application.continuous_research.children import (
    ContinuousChildReference,
)
from market_regime_alpha.application.continuous_research.scope import (
    ContinuousResearchScope,
    ContinuousResearchScopeRecord,
    prepare_continuous_research_scope,
)

__all__ = [
    "ChangeDecision",
    "ContinuousChildReference",
    "ContinuousResearchScope",
    "ContinuousResearchScopeRecord",
    "CurrentEvidenceSnapshot",
    "EvidenceCommit",
    "EvidenceCommitResult",
    "EvidenceQualityStatus",
    "MaterialIdentityInput",
    "ProviderAttemptOutcome",
    "ProviderAttemptSnapshot",
    "RecordedChangeDecision",
    "StartedProviderAttempt",
    "prepare_continuous_research_scope",
]
