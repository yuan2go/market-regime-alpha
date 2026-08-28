"""Pure Run, Step, Attempt, retry, and DAG invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_STEP_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")


class RunState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class AttemptState(StrEnum):
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    ABANDONED = "ABANDONED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class RuntimeMode(StrEnum):
    OPERATIONAL = "OPERATIONAL"
    HISTORICAL = "HISTORICAL"
    REPLAY = "REPLAY"
    SHADOW = "SHADOW"
    PROSPECTIVE = "PROSPECTIVE"


class ExternalEffectClass(StrEnum):
    NONE = "NONE"
    PURE_READ = "PURE_READ"
    CONTENT_PUT = "CONTENT_PUT"
    IDEMPOTENT_REMOTE_COMMAND = "IDEMPOTENT_REMOTE_COMMAND"
    NON_IDEMPOTENT_REMOTE_COMMAND = "NON_IDEMPOTENT_REMOTE_COMMAND"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"


class InvalidRuntimeTransition(ValueError):
    """A lifecycle edge is outside the frozen state machine."""


_RUN_EDGES = frozenset(
    {
        (RunState.QUEUED, RunState.RUNNING),
        (RunState.QUEUED, RunState.CANCELLED),
        (RunState.RUNNING, RunState.WAITING),
        (RunState.RUNNING, RunState.SUCCEEDED),
        (RunState.RUNNING, RunState.BLOCKED),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.RUNNING, RunState.CANCELLED),
        (RunState.WAITING, RunState.RUNNING),
        (RunState.WAITING, RunState.BLOCKED),
        (RunState.WAITING, RunState.FAILED),
        (RunState.WAITING, RunState.CANCELLED),
    }
)

_STEP_EDGES = frozenset(
    {
        (StepState.PENDING, StepState.READY),
        (StepState.PENDING, StepState.SKIPPED),
        (StepState.READY, StepState.CLAIMED),
        (StepState.CLAIMED, StepState.RUNNING),
        (StepState.CLAIMED, StepState.READY),
        (StepState.RUNNING, StepState.READY),
        (StepState.RUNNING, StepState.WAITING),
        (StepState.RUNNING, StepState.SUCCEEDED),
        (StepState.RUNNING, StepState.BLOCKED),
        (StepState.RUNNING, StepState.FAILED),
        (StepState.WAITING, StepState.READY),
        *((state, StepState.CANCELLED) for state in (
            StepState.PENDING,
            StepState.READY,
            StepState.CLAIMED,
            StepState.RUNNING,
            StepState.WAITING,
        )),
    }
)

_ATTEMPT_EDGES = frozenset(
    {
        (AttemptState.CLAIMED, AttemptState.RUNNING),
        (AttemptState.CLAIMED, AttemptState.ABANDONED),
        (AttemptState.RUNNING, AttemptState.SUCCEEDED),
        (AttemptState.RUNNING, AttemptState.FAILED_RETRYABLE),
        (AttemptState.RUNNING, AttemptState.FAILED_TERMINAL),
        (AttemptState.RUNNING, AttemptState.ABANDONED),
        (AttemptState.RUNNING, AttemptState.RECONCILIATION_REQUIRED),
    }
)


def ensure_run_transition(source: RunState, target: RunState) -> None:
    _ensure_transition("Run", source, target, _RUN_EDGES)


def ensure_step_transition(source: StepState, target: StepState) -> None:
    _ensure_transition("Step", source, target, _STEP_EDGES)


def ensure_attempt_transition(source: AttemptState, target: AttemptState) -> None:
    _ensure_transition("Attempt", source, target, _ATTEMPT_EDGES)


def _ensure_transition(
    kind: str,
    source: StrEnum,
    target: StrEnum,
    edges: frozenset[tuple[StrEnum, StrEnum]],
) -> None:
    if (source, target) not in edges:
        raise InvalidRuntimeTransition(
            f"{kind} transition {source.value} -> {target.value} is not allowed"
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    backoff: tuple[timedelta, ...]
    retryable_codes: frozenset[str]
    deadline: datetime | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= 64:
            raise ValueError("max_attempts must be between 1 and 64")
        if len(self.backoff) > self.max_attempts - 1:
            raise ValueError("backoff cannot contain more entries than retries")
        if any(delay < timedelta(0) or delay > timedelta(days=1) for delay in self.backoff):
            raise ValueError("backoff delays must be between zero and one day")
        if any(not _CODE.fullmatch(code) for code in self.retryable_codes):
            raise ValueError("retryable codes must use the closed code format")
        if self.deadline is not None:
            object.__setattr__(self, "deadline", require_utc(self.deadline, field="deadline"))

    def delay_after(self, attempt_no: int) -> timedelta:
        if attempt_no <= 0:
            raise ValueError("attempt_no must be positive")
        retry_index = attempt_no - 1
        if retry_index >= len(self.backoff):
            return timedelta(0)
        return self.backoff[retry_index]


@dataclass(frozen=True, slots=True)
class StepSpec:
    step_key: str
    step_kind: str
    implementation: str
    implementation_version: str
    ordinal: int
    required: bool
    request_hash: str
    input_evidence_hash: str | None
    retry_policy: RetryPolicy
    external_effect_class: ExternalEffectClass = ExternalEffectClass.NONE

    def __post_init__(self) -> None:
        if not _STEP_KEY.fullmatch(self.step_key):
            raise ValueError("step_key has an invalid format")
        if not _CODE.fullmatch(self.step_kind):
            raise ValueError("step_kind has an invalid format")
        if not self.implementation or not self.implementation_version:
            raise ValueError("implementation identity is required")
        if isinstance(self.ordinal, bool) or self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        ContentHash(self.request_hash)
        if self.input_evidence_hash is not None:
            ContentHash(self.input_evidence_hash)


@dataclass(frozen=True, slots=True)
class StepDependency:
    predecessor_key: str
    successor_key: str
    dependency_kind: str = "REQUIRED_SUCCESS"

    def __post_init__(self) -> None:
        if self.predecessor_key == self.successor_key:
            raise ValueError("a Step cannot depend on itself")
        if self.dependency_kind not in {"REQUIRED_SUCCESS", "TERMINAL"}:
            raise ValueError("unknown dependency kind")


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    schedule_id: UUID
    schedule_code: str
    revision: int
    runtime_mode: RuntimeMode
    schedule_expression: str | None
    timezone_name: str
    step_catalog_hash: str
    enabled: bool
    supersedes_schedule_id: UUID | None = None

    def __post_init__(self) -> None:
        if not _STEP_KEY.fullmatch(self.schedule_code):
            raise ValueError("schedule_code has an invalid format")
        if isinstance(self.revision, bool) or self.revision <= 0:
            raise ValueError("schedule revision must be positive")
        if not self.timezone_name:
            raise ValueError("timezone_name is required")
        ContentHash(self.step_catalog_hash)
        if self.supersedes_schedule_id == self.schedule_id:
            raise ValueError("a schedule revision cannot supersede itself")


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_id: UUID
    schedule_id: UUID
    fire_key: str
    runtime_mode: RuntimeMode
    requested_at: datetime
    decision_time: datetime | None
    code_sha: str
    config_artifact_id: UUID
    config_hash: str
    parent_run_id: UUID | None = None
    original_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.fire_key:
            raise ValueError("fire_key is required")
        object.__setattr__(
            self,
            "requested_at",
            require_utc(self.requested_at, field="requested_at"),
        )
        if self.decision_time is not None:
            object.__setattr__(
                self,
                "decision_time",
                require_utc(self.decision_time, field="decision_time"),
            )
        if not re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", self.code_sha):
            raise ValueError("code_sha must be a lowercase SHA-1 or SHA-256")
        ContentHash(self.config_hash)
        if self.parent_run_id == self.run_id or self.original_run_id == self.run_id:
            raise ValueError("a Run cannot reference itself")


def validate_step_dag(
    steps: tuple[StepSpec, ...],
    dependencies: tuple[StepDependency, ...],
) -> None:
    if not steps:
        raise ValueError("a Run requires at least one Step")
    if any(
        step.external_effect_class
        is ExternalEffectClass.NON_IDEMPOTENT_REMOTE_COMMAND
        for step in steps
    ):
        raise ValueError(
            "NON_IDEMPOTENT_REMOTE_COMMAND is forbidden from unattended Runtime"
        )
    keys = [step.step_key for step in steps]
    ordinals = [step.ordinal for step in steps]
    if len(set(keys)) != len(keys):
        raise ValueError("Step keys must be unique")
    if len(set(ordinals)) != len(ordinals):
        raise ValueError("Step ordinals must be unique")
    known = set(keys)
    graph: dict[str, set[str]] = {key: set() for key in keys}
    for dependency in dependencies:
        if dependency.predecessor_key not in known or dependency.successor_key not in known:
            raise ValueError("Step dependency references an unknown Step")
        graph[dependency.predecessor_key].add(dependency.successor_key)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("Step dependency graph contains a cycle")
        if key in visited:
            return
        visiting.add(key)
        for successor in graph[key]:
            visit(successor)
        visiting.remove(key)
        visited.add(key)

    for key in keys:
        visit(key)


__all__ = [
    "AttemptState",
    "ExternalEffectClass",
    "InvalidRuntimeTransition",
    "RetryPolicy",
    "RunSpec",
    "RunState",
    "RuntimeMode",
    "ScheduleSpec",
    "StepDependency",
    "StepSpec",
    "StepState",
    "ensure_attempt_transition",
    "ensure_run_transition",
    "ensure_step_transition",
    "validate_step_dag",
]
