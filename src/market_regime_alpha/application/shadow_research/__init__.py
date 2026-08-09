"""Prospective Shadow engineering authority over existing Research Summaries."""

from market_regime_alpha.application.shadow_research.contracts import (
    ShadowDecision,
    ShadowOutcomeStatus,
    ShadowSessionCommand,
    ShadowSessionSnapshot,
    ShadowSessionStatus,
)
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
    ShadowResearchConflict,
    ShadowResearchIntegrityError,
)

__all__ = [
    "PostgresShadowResearchRepository",
    "ShadowDecision",
    "ShadowOutcomeStatus",
    "ShadowResearchConflict",
    "ShadowResearchIntegrityError",
    "ShadowSessionCommand",
    "ShadowSessionSnapshot",
    "ShadowSessionStatus",
]
