"""Exact immutable inputs prepared outside the Outcome write transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market_regime_alpha.outcome.domain.authority import (
    OutcomeCommitmentSnapshot,
    OutcomeRuntimeSnapshot,
)
from market_regime_alpha.outcome.domain.model import (
    OutcomeObservationSource,
    OutcomeSessionSource,
    OutcomeTargetDefinition,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class PreparedOutcomeInputs:
    commitment: OutcomeCommitmentSnapshot
    target: OutcomeTargetDefinition
    runtime: OutcomeRuntimeSnapshot
    observation_cutoff: datetime
    knowledge_cutoff: datetime
    due_at: datetime
    sessions: tuple[OutcomeSessionSource, ...]
    sources: tuple[OutcomeObservationSource, ...]
    is_due: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_cutoff",
            require_utc(self.observation_cutoff, field="Outcome observation cutoff"),
        )
        object.__setattr__(
            self,
            "knowledge_cutoff",
            require_utc(self.knowledge_cutoff, field="Outcome knowledge cutoff"),
        )
        object.__setattr__(
            self,
            "due_at",
            require_utc(self.due_at, field="Outcome due time"),
        )
        if (
            self.commitment.target_definition_id != self.target.target_definition_id
            or self.commitment.target_version != self.target.version
            or self.commitment.target_definition_sha256 != self.target.content_sha256
            or self.commitment.target_checkpoint_id != self.target.reference_checkpoint_id
        ):
            raise ValueError("prepared Outcome commitment and Target differ")
        if not self.sessions:
            raise ValueError("Outcome due assessment requires exact Session facts")
        if self.is_due and len(self.sources) != len(self.target.checkpoints):
            raise ValueError("due Outcome preparation requires complete source coverage")
        if not self.is_due and self.sources:
            raise ValueError("NOT_DUE Outcome preparation cannot resolve observations")

    def semantic_request_sha256(
        self,
        *,
        observation_cutoff: datetime,
        knowledge_cutoff: datetime,
        expected_current_revision_id: object,
        actor_type: str,
        actor_id: str,
        reason_code: str,
    ) -> str:
        return canonical_json_sha256(
            {
                "actor_id": actor_id,
                "actor_type": actor_type,
                "commitment_id": self.commitment.commitment_id,
                "decision_reference_observation_id": (self.commitment.decision_reference_observation_id),
                "decision_reference_sha256": (self.commitment.decision_reference_sha256),
                "exploratory_retrospective_scope": (self.commitment.exploratory_retrospective_scope),
                "expected_current_revision_id": expected_current_revision_id,
                "knowledge_cutoff": knowledge_cutoff,
                "observation_cutoff": observation_cutoff,
                "reason_code": reason_code,
                "runtime_attempt_id": self.runtime.attempt_id,
                "runtime_fence_token": self.runtime.fence_token,
                "runtime_run_id": self.runtime.run_id,
                "runtime_step_id": self.runtime.step_id,
                "sessions": self.sessions,
                "sources": self.sources,
                "target_algorithm_sha256": self.target.algorithm_sha256,
                "target_code_content_sha256": self.target.code_content_sha256,
                "target_config_content_sha256": self.target.config_content_sha256,
                "target_definition_id": self.target.target_definition_id,
                "target_definition_sha256": self.target.content_sha256,
            }
        )


__all__ = ["PreparedOutcomeInputs"]
