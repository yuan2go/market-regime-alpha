from __future__ import annotations

from datetime import timedelta

import pytest

from market_regime_alpha.runtime.domain import (
    AttemptState,
    ExternalEffectClass,
    InvalidRuntimeTransition,
    RetryPolicy,
    RunState,
    StepDependency,
    StepSpec,
    StepState,
    ensure_attempt_transition,
    ensure_run_transition,
    ensure_step_transition,
    validate_step_dag,
)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RunState.QUEUED, RunState.RUNNING),
        (RunState.RUNNING, RunState.WAITING),
        (RunState.WAITING, RunState.RUNNING),
        (RunState.RUNNING, RunState.SUCCEEDED),
        (RunState.QUEUED, RunState.CANCELLED),
    ],
)
def test_run_state_machine_accepts_only_frozen_edges(
    source: RunState,
    target: RunState,
) -> None:
    ensure_run_transition(source, target)


def test_terminal_runtime_states_never_reopen() -> None:
    with pytest.raises(InvalidRuntimeTransition):
        ensure_run_transition(RunState.SUCCEEDED, RunState.RUNNING)
    with pytest.raises(InvalidRuntimeTransition):
        ensure_step_transition(StepState.FAILED, StepState.READY)
    with pytest.raises(InvalidRuntimeTransition):
        ensure_attempt_transition(AttemptState.ABANDONED, AttemptState.RUNNING)


def test_retry_policy_and_step_dag_are_typed_and_acyclic() -> None:
    policy = RetryPolicy(
        max_attempts=3,
        backoff=(timedelta(0), timedelta(seconds=1)),
        retryable_codes=frozenset({"TRANSIENT"}),
    )
    capture = StepSpec(
        step_key="capture",
        step_kind="CAPTURE",
        implementation="tests.capture",
        implementation_version="1",
        ordinal=1,
        required=True,
        request_hash="1" * 64,
        input_evidence_hash=None,
        retry_policy=policy,
    )
    normalize = StepSpec(
        step_key="normalize",
        step_kind="NORMALIZE_PIT",
        implementation="tests.normalize",
        implementation_version="1",
        ordinal=2,
        required=True,
        request_hash="2" * 64,
        input_evidence_hash="3" * 64,
        retry_policy=policy,
    )

    validate_step_dag(
        (capture, normalize),
        (StepDependency(predecessor_key="capture", successor_key="normalize"),),
    )

    with pytest.raises(ValueError, match="cycle"):
        validate_step_dag(
            (capture, normalize),
            (
                StepDependency(predecessor_key="capture", successor_key="normalize"),
                StepDependency(predecessor_key="normalize", successor_key="capture"),
            ),
        )


def test_non_idempotent_remote_command_is_rejected_at_planning_boundary() -> None:
    step = StepSpec(
        step_key="broker-side-effect",
        step_kind="EXTERNAL_COMMAND",
        implementation="tests.external_command",
        implementation_version="1",
        ordinal=1,
        required=True,
        request_hash="4" * 64,
        input_evidence_hash=None,
        retry_policy=RetryPolicy(
            max_attempts=1,
            backoff=(),
            retryable_codes=frozenset(),
        ),
        external_effect_class=ExternalEffectClass.NON_IDEMPOTENT_REMOTE_COMMAND,
    )

    with pytest.raises(ValueError, match="NON_IDEMPOTENT_REMOTE_COMMAND"):
        validate_step_dag((step,), ())


def test_candidate_to_context_chain_is_mandatory_and_cannot_bypass_decision() -> None:
    policy = RetryPolicy(max_attempts=1, backoff=(), retryable_codes=frozenset())

    def step(key: str, kind: str, ordinal: int) -> StepSpec:
        return StepSpec(
            step_key=key,
            step_kind=kind,
            implementation=f"tests.{key}",
            implementation_version="1",
            ordinal=ordinal,
            required=True,
            request_hash=str(ordinal) * 64,
            input_evidence_hash=None,
            retry_policy=policy,
        )

    build = step("build-candidates", "BUILD_CANDIDATE_SET", 1)
    opened = step("open-decision", "OPEN_DECISION_RUN", 2)
    context = step("assess-context", "ASSESS_CONTEXT", 3)
    required_edges = (
        StepDependency("build-candidates", "open-decision"),
        StepDependency("open-decision", "assess-context"),
    )
    validate_step_dag((build, opened, context), required_edges)

    with pytest.raises(ValueError, match="each occur exactly once"):
        validate_step_dag((build,), ())
    with pytest.raises(ValueError, match="direct REQUIRED_SUCCESS"):
        validate_step_dag((build, opened, context), ())
    with pytest.raises(ValueError, match="cannot bypass"):
        validate_step_dag(
            (build, opened, context),
            (
                *required_edges,
                StepDependency("build-candidates", "assess-context"),
            ),
        )
