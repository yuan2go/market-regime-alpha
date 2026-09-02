"""Selection aggregate persistence port."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.selection.domain import (
    EligibilityAssessmentDecision,
    EligibilityBatch,
    EligibilityPolicy,
    FrozenUniverse,
    UniverseDefinition,
    UniverseMemberDecision,
    UniverseScopeSpecification,
    ExploratoryRetrospectiveSelectionScope,
)
from market_regime_alpha.shared.time import DecisionTime


class SelectionRepository(Protocol):
    def register_universe(self, definition: UniverseDefinition) -> int: ...

    def register_eligibility_policy(self, policy: EligibilityPolicy) -> int: ...

    def load_eligibility_policy(self, policy_id: UUID) -> EligibilityPolicy: ...

    def validate_and_lock_scope(
        self,
        *,
        universe_id: UUID,
        scope: UniverseScopeSpecification,
    ) -> int: ...

    def insert_frozen_universe(
        self,
        *,
        universe_revision_id: UUID,
        universe_id: UUID,
        revision: int,
        decision_time: DecisionTime,
        scope: UniverseScopeSpecification,
        members: tuple[UniverseMemberDecision, ...],
    ) -> None: ...

    def load_frozen_universe(
        self,
        universe_revision_id: UUID,
        *,
        result_hash: str,
        receipt_id: UUID,
        replayed: bool,
    ) -> FrozenUniverse: ...

    def lock_frozen_universe(
        self,
        universe_revision_id: UUID,
    ) -> FrozenUniverse: ...

    def insert_eligibility_assessments(
        self,
        *,
        universe: FrozenUniverse,
        policy: EligibilityPolicy,
        decision_time: DecisionTime,
        assessments: tuple[EligibilityAssessmentDecision, ...],
    ) -> None: ...

    def load_eligibility_batch(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        decision_time: DecisionTime,
        result_hash: str,
        receipt_id: UUID,
        replayed: bool,
    ) -> EligibilityBatch: ...

    def bind_exploratory_retrospective_universe(
        self,
        universe_revision_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None: ...

    def bind_exploratory_retrospective_eligibility(
        self,
        *,
        universe: FrozenUniverse,
        eligibility_policy_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
        assessment_count: int,
    ) -> None: ...

    def require_exploratory_retrospective_universe_scope(
        self,
        universe_revision_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None: ...

    def require_exploratory_retrospective_eligibility_scope(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None: ...


__all__ = ["SelectionRepository"]
