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

__all__ = [
    "CurrentEvidenceSnapshot",
    "EvidenceCommit",
    "EvidenceCommitResult",
    "EvidenceQualityStatus",
    "ProviderAttemptOutcome",
    "ProviderAttemptSnapshot",
    "StartedProviderAttempt",
]
