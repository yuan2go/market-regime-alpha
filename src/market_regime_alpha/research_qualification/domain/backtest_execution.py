"""Pure Backtest execution graph and orthogonal lifecycle projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from datetime import datetime
from uuid import UUID

from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


class BacktestActionKind(StrEnum):
    MATERIALIZE_DATASET = "MATERIALIZE_DATASET"
    GENERATE_DECISION_SUPPORT = "GENERATE_DECISION_SUPPORT"
    SETTLE_OUTCOME = "SETTLE_OUTCOME"
    COMPLETE_FOLD_EVALUATION = "COMPLETE_FOLD_EVALUATION"
    TRAIN_MODEL = "TRAIN_MODEL"
    COMPLETE_AGGREGATE_EVALUATION = "COMPLETE_AGGREGATE_EVALUATION"


class BacktestObservedState(StrEnum):
    ABSENT = "ABSENT"
    MATCHED_INCOMPLETE = "MATCHED_INCOMPLETE"
    MATCHED_COMPLETE = "MATCHED_COMPLETE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    MISMATCH = "MISMATCH"


class BacktestExecutionState(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"


class BacktestResearchState(StrEnum):
    ESTIMABLE = "ESTIMABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BacktestNextOperation(StrEnum):
    EXECUTE = "EXECUTE"
    RECOVER = "RECOVER"
    RETRY = "RETRY"


@dataclass(frozen=True, slots=True)
class BacktestExpectedAction:
    action_id: UUID
    ordinal: int
    kind: BacktestActionKind
    exploratory_backtest_run_id: UUID
    arm_id: UUID | None
    fold_id: UUID | None
    fold_session_id: UUID | None
    model_training_requirement_id: UUID | None
    dependency_action_ids: tuple[UUID, ...]
    evaluation_requirement_id: UUID | None = None
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("action ordinal must be positive")
        if len(set(self.dependency_action_ids)) != len(self.dependency_action_ids):
            raise ValueError("action dependency roster contains duplicates")
        content: dict[str, object] = {
            "action_id": self.action_id,
            "arm_id": self.arm_id,
            "dependency_action_ids": self.dependency_action_ids,
            "exploratory_backtest_run_id": self.exploratory_backtest_run_id,
            "fold_id": self.fold_id,
            "fold_session_id": self.fold_session_id,
            "kind": self.kind,
            "model_training_requirement_id": self.model_training_requirement_id,
            "ordinal": self.ordinal,
        }
        if self.evaluation_requirement_id is not None:
            content["evaluation_requirement_id"] = self.evaluation_requirement_id
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(canonical_json_sha256(content)),
        )


@dataclass(frozen=True, slots=True)
class BacktestActionObservation:
    action_id: UUID
    state: BacktestObservedState
    research_state: BacktestResearchState = BacktestResearchState.NOT_APPLICABLE


@dataclass(frozen=True, slots=True)
class BacktestReadyAction:
    action: BacktestExpectedAction
    operation: BacktestNextOperation


@dataclass(frozen=True, slots=True)
class BacktestFoldLifecycle:
    fold_id: UUID
    execution_state: BacktestExecutionState
    research_state: BacktestResearchState


@dataclass(frozen=True, slots=True)
class BacktestExecutionPlan:
    exploratory_backtest_run_id: UUID
    expected_actions: tuple[BacktestExpectedAction, ...]
    ready_actions: tuple[BacktestReadyAction, ...]
    fold_lifecycles: tuple[BacktestFoldLifecycle, ...]
    execution_state: BacktestExecutionState
    research_state: BacktestResearchState
    integrity_mismatch_action_ids: tuple[UUID, ...]
    action_roster_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        ordinals = tuple(action.ordinal for action in self.expected_actions)
        if ordinals != tuple(range(1, len(self.expected_actions) + 1)):
            raise ValueError("expected action ordinals must be contiguous")
        object.__setattr__(
            self,
            "action_roster_sha256",
            ContentHash(
                canonical_json_sha256(
                    tuple(
                        {
                            "action_id": action.action_id,
                            "content_sha256": str(action.content_sha256),
                            "ordinal": action.ordinal,
                        }
                        for action in self.expected_actions
                    )
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestRuntimeBinding:
    """Immutable lineage from one derived action to one canonical RuntimeRun."""

    backtest_runtime_binding_id: UUID
    exploratory_backtest_run_id: UUID
    specification_sha256: ContentHash | str
    action: BacktestExpectedAction
    runtime_run_id: UUID
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        specification_hash = ContentHash(str(self.specification_sha256))
        if self.action.exploratory_backtest_run_id != self.exploratory_backtest_run_id:
            raise ValueError("Runtime binding action belongs to another Backtest")
        object.__setattr__(self, "specification_sha256", specification_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "action_content_sha256": str(self.action.content_sha256),
                        "action_id": self.action.action_id,
                        "action_kind": self.action.kind,
                        "evaluation_requirement_id": (self.action.evaluation_requirement_id),
                        "exploratory_backtest_arm_id": self.action.arm_id,
                        "exploratory_backtest_fold_id": self.action.fold_id,
                        "exploratory_backtest_fold_session_id": (self.action.fold_session_id),
                        "exploratory_backtest_run_id": (self.exploratory_backtest_run_id),
                        "model_training_requirement_id": (self.action.model_training_requirement_id),
                        "runtime_run_id": self.runtime_run_id,
                        "specification_sha256": str(specification_hash),
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class BacktestEvaluationExecution:
    """Exact completed Evaluation lineage for one frozen requirement."""

    backtest_evaluation_execution_id: UUID
    exploratory_backtest_run_id: UUID
    specification_sha256: ContentHash | str
    backtest_evaluation_requirement_id: UUID
    evaluation_run_id: UUID
    evaluation_protocol_id: UUID
    evaluation_metric_count: int
    evaluation_metric_roster_sha256: ContentHash | str
    canonical_completed_at: datetime
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        specification_hash = ContentHash(str(self.specification_sha256))
        metric_roster_hash = ContentHash(str(self.evaluation_metric_roster_sha256))
        if self.evaluation_metric_count < 1:
            raise ValueError("Evaluation execution metric roster must be non-empty")
        if self.canonical_completed_at.tzinfo is None:
            raise ValueError("Evaluation completion time must be timezone-aware")
        object.__setattr__(self, "specification_sha256", specification_hash)
        object.__setattr__(self, "evaluation_metric_roster_sha256", metric_roster_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "backtest_evaluation_requirement_id": (self.backtest_evaluation_requirement_id),
                        "evaluation_metric_count": self.evaluation_metric_count,
                        "evaluation_metric_roster_sha256": str(metric_roster_hash),
                        "evaluation_protocol_id": self.evaluation_protocol_id,
                        "evaluation_run_id": self.evaluation_run_id,
                        "exploratory_backtest_run_id": (self.exploratory_backtest_run_id),
                        "specification_sha256": str(specification_hash),
                    }
                )
            ),
        )


__all__ = [
    "BacktestActionKind",
    "BacktestActionObservation",
    "BacktestExecutionPlan",
    "BacktestEvaluationExecution",
    "BacktestExecutionState",
    "BacktestExpectedAction",
    "BacktestFoldLifecycle",
    "BacktestNextOperation",
    "BacktestObservedState",
    "BacktestReadyAction",
    "BacktestResearchState",
    "BacktestRuntimeBinding",
]
