"""Domain-neutral contracts implemented by canonical lifecycle stage adapters.

Handlers load and invoke existing domain authorities.  The runner consumes only
these contracts and journal references; it does not interpret model scores or
reimplement domain decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptResult,
    LifecycleObjectReference,
    LifecycleRun,
    LifecycleStage,
    validate_lifecycle_object_references,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    WAITING_LIFECYCLE_RUN_STATUSES,
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.evidence.canonical import require_sha256, require_text


class StageMutationKind(str, Enum):
    """Recovery contract of a stage's existing domain operation."""

    PURE = "PURE"
    READ_ONLY = "READ_ONLY"
    IDEMPOTENT_MUTATION = "IDEMPOTENT_MUTATION"


_RECEIPT_STAGE_STATUSES = frozenset(
    {
        LifecycleStageStatus.COMPLETED,
        LifecycleStageStatus.WAITING,
        LifecycleStageStatus.BLOCKED,
        LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
    }
)


def _require_sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    for value in values:
        require_text(label, value)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must be sorted")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")


@dataclass(frozen=True, slots=True)
class StageExecutionResult:
    """Verified references and orchestration outcome returned by one handler."""

    stage_status: LifecycleStageStatus
    run_status: LifecycleRunStatus
    input_references: tuple[LifecycleObjectReference, ...]
    output_references: tuple[LifecycleObjectReference, ...]
    model_versions: tuple[tuple[str, str], ...]
    configuration_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    blocker_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.stage_status, LifecycleStageStatus):
            raise TypeError("stage_status must be a LifecycleStageStatus")
        if self.stage_status not in _RECEIPT_STAGE_STATUSES:
            raise ValueError("stage_status must be receipt-bearing")
        if not isinstance(self.run_status, LifecycleRunStatus):
            raise TypeError("run_status must be a LifecycleRunStatus")
        validate_lifecycle_object_references(
            "input_references", self.input_references
        )
        validate_lifecycle_object_references(
            "output_references", self.output_references
        )
        self._validate_model_versions()
        _require_sorted_unique_text("configuration_hashes", self.configuration_hashes)
        for value in self.configuration_hashes:
            require_sha256("configuration_hashes", value)
        _require_sorted_unique_text("reason_codes", self.reason_codes)
        self._validate_status_pair()
        reason_required = (
            self.stage_status
            in {
                LifecycleStageStatus.WAITING,
                LifecycleStageStatus.BLOCKED,
                LifecycleStageStatus.SKIPPED_NOT_APPLICABLE,
            }
            or self.run_status in WAITING_LIFECYCLE_RUN_STATUSES
        )
        if reason_required:
            if self.blocker_reason is None:
                raise ValueError("waiting, blocked, or skipped result requires a reason")
            require_text("blocker_reason", self.blocker_reason)
        elif self.blocker_reason is not None:
            raise ValueError("non-reasoned result cannot carry blocker_reason")
        if (
            self.stage_status is LifecycleStageStatus.SKIPPED_NOT_APPLICABLE
            and self.output_references
        ):
            raise ValueError("not-applicable stage cannot publish output references")

    def _validate_model_versions(self) -> None:
        if not isinstance(self.model_versions, tuple):
            raise TypeError("model_versions must be a tuple")
        if self.model_versions != tuple(sorted(self.model_versions)):
            raise ValueError("model_versions must be sorted")
        if len(set(self.model_versions)) != len(self.model_versions):
            raise ValueError("model_versions must be unique")
        for value in self.model_versions:
            if not isinstance(value, tuple) or len(value) != 2:
                raise TypeError("model_versions entries must be (model_id, version)")
            model_id, version = value
            require_text("model_id", model_id)
            require_text("model_version", version)
            if "@" in model_id or "@" in version:
                raise ValueError("model identity and version cannot contain '@'")

    def _validate_status_pair(self) -> None:
        if self.run_status in {
            LifecycleRunStatus.CREATED,
            LifecycleRunStatus.RETRYING,
            LifecycleRunStatus.FAILED,
        }:
            raise ValueError("handler cannot return a control or failure run status")
        if self.stage_status is LifecycleStageStatus.SKIPPED_NOT_APPLICABLE:
            if self.run_status is not LifecycleRunStatus.RUNNING:
                raise ValueError("not-applicable stage must leave the run RUNNING")
        elif self.stage_status is LifecycleStageStatus.BLOCKED:
            if self.run_status is not LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION:
                raise ValueError("blocked stage must block on model validation")
        elif self.stage_status is LifecycleStageStatus.WAITING:
            waiting_targets = WAITING_LIFECYCLE_RUN_STATUSES - {
                LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
            }
            if self.run_status not in waiting_targets:
                raise ValueError("waiting stage must return a waiting run status")
        elif self.run_status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION:
            raise ValueError("only a blocked stage may block model validation")
        if (
            self.run_status is LifecycleRunStatus.COMPLETED
            and self.stage_status is not LifecycleStageStatus.COMPLETED
        ):
            raise ValueError("only a completed stage may complete a run")

    @property
    def receipt_model_versions(self) -> tuple[str, ...]:
        """Return the canonical receipt representation of model/version pairs."""

        return tuple(f"{model_id}@{version}" for model_id, version in self.model_versions)


@dataclass(frozen=True, slots=True)
class LifecycleStageContext:
    """Journal-bound input given to both recovery and execution paths."""

    run: LifecycleRun
    stage: LifecycleStage
    attempt: LifecycleAttempt
    prior_stages: tuple[LifecycleStage, ...]
    initial_references: tuple[LifecycleObjectReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run, LifecycleRun):
            raise TypeError("run must be a LifecycleRun")
        if not isinstance(self.stage, LifecycleStage):
            raise TypeError("stage must be a LifecycleStage")
        if not isinstance(self.attempt, LifecycleAttempt):
            raise TypeError("attempt must be a LifecycleAttempt")
        if self.run.status is not LifecycleRunStatus.RUNNING:
            raise ValueError("stage context requires a RUNNING run")
        if self.stage.stage_status is not LifecycleStageStatus.RUNNING:
            raise ValueError("stage context requires a RUNNING stage")
        if self.attempt.result is not LifecycleAttemptResult.RUNNING:
            raise ValueError("stage context requires a RUNNING attempt")
        if (
            self.stage.run_id != self.run.run_id
            or self.attempt.run_id != self.run.run_id
            or self.attempt.stage_name is not self.stage.stage_name
        ):
            raise ValueError("run, stage, and attempt identities must align")
        if self.attempt.attempt_number != self.stage.attempt_count:
            raise ValueError("attempt number must match the stage projection")
        if not isinstance(self.prior_stages, tuple) or any(
            not isinstance(item, LifecycleStage) for item in self.prior_stages
        ):
            raise TypeError("prior_stages must contain LifecycleStage values")
        if any(item.run_id != self.run.run_id for item in self.prior_stages):
            raise ValueError("prior stages must bind the context run")
        expected_prior = LIFECYCLE_STAGE_ORDER[
            : LIFECYCLE_STAGE_ORDER.index(self.stage.stage_name)
        ]
        if tuple(item.stage_name for item in self.prior_stages) != expected_prior:
            raise ValueError("prior_stages must be the exact ordered stage prefix")
        validate_lifecycle_object_references(
            "initial_references", self.initial_references
        )

    @property
    def stage_name(self) -> LifecycleStageName:
        return self.stage.stage_name

    @property
    def stage_idempotency_key(self) -> str:
        return f"{self.run.run_id}:{self.stage.stage_name.value}"

    @property
    def upstream_references(self) -> tuple[LifecycleObjectReference, ...]:
        """Return unique outputs from the settled ordered stage prefix."""

        references: dict[
            tuple[str, str, str], LifecycleObjectReference
        ] = {}
        for stage in self.prior_stages:
            for reference in stage.output_references:
                existing = references.setdefault(reference.sort_key, reference)
                if existing != reference:
                    raise ValueError("prior stages carry conflicting output references")
        result = tuple(sorted(references.values(), key=lambda item: item.sort_key))
        validate_lifecycle_object_references("upstream_references", result)
        return result


@runtime_checkable
class LifecycleStageHandler(Protocol):
    """One recoverable adapter around an existing Reader or domain service."""

    @property
    def stage_name(self) -> LifecycleStageName: ...

    @property
    def mutation_kind(self) -> StageMutationKind: ...

    def recover(
        self, context: LifecycleStageContext
    ) -> StageExecutionResult | None: ...

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult: ...
