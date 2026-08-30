"""Narrow read-only inputs used to prepare one Decision Run."""

from typing import Protocol

from market_regime_alpha.decision_support.domain import (
    OpenDecisionRunRequest,
    PreparedDecisionInputs,
)
from market_regime_alpha.runtime.ports import AttemptClaim


class DecisionInputPreparationProvider(Protocol):
    """Resolve exact immutable Candidate, Target, Runtime, and Market facts."""

    def prepare(
        self,
        request: OpenDecisionRunRequest,
        runtime_claim: AttemptClaim,
    ) -> PreparedDecisionInputs: ...


class DecisionDependencyRepository(Protocol):
    """Lock and revalidate a prepared snapshot without resolving replacements."""

    def lock_and_revalidate(self, prepared: PreparedDecisionInputs) -> None: ...


__all__ = ["DecisionDependencyRepository", "DecisionInputPreparationProvider"]
