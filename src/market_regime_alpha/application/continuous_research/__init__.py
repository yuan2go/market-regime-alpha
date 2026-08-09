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
from market_regime_alpha.application.continuous_research.free_data_runtime import (
    CanonicalFreeDataProvider,
    CanonicalFreeDataResearchComposition,
    ControlledRuntimeModelSelector,
)
from market_regime_alpha.application.continuous_research.scope import (
    ContinuousResearchScope,
    ContinuousResearchScopeRecord,
    prepare_continuous_research_scope,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
    ContinuousTickExecutionResult,
)
from market_regime_alpha.application.continuous_research.scheduler import (
    ContinuousResearchScheduleRunner,
    ContinuousScheduleRunResult,
    ContinuousScheduleSnapshot,
    ContinuousScheduleStatus,
    TradingDayAssessment,
)

__all__ = [
    "ChangeDecision",
    "CanonicalFreeDataProvider",
    "CanonicalFreeDataResearchComposition",
    "ContinuousChildReference",
    "ContinuousResearchScope",
    "ContinuousResearchScopeRecord",
    "ContinuousResearchScheduleRunner",
    "ContinuousResearchTickRunner",
    "ContinuousTickExecutionResult",
    "ControlledRuntimeModelSelector",
    "ContinuousScheduleRunResult",
    "ContinuousScheduleSnapshot",
    "ContinuousScheduleStatus",
    "CurrentEvidenceSnapshot",
    "EvidenceCommit",
    "EvidenceCommitResult",
    "EvidenceQualityStatus",
    "MaterialIdentityInput",
    "ProviderAttemptOutcome",
    "ProviderAttemptSnapshot",
    "RecordedChangeDecision",
    "StartedProviderAttempt",
    "TradingDayAssessment",
    "prepare_continuous_research_scope",
]
