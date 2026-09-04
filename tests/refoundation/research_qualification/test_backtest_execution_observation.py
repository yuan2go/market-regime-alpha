from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.queries.backtest_execution import (
    _reconcile_current_runtime,
)
from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionObservation,
    BacktestObservedState,
    BacktestResearchState,
    BacktestRuntimeBinding,
)
from tests.refoundation.research_qualification.test_backtest_execution_planner import (
    _run,
)


def _runtime_row(*, state: str, latest_attempt_state: str | None = None):
    run = _run()
    action = BacktestExecutionPlanner().compile(run).expected_actions[0]
    runtime_run_id = UUID(int=9000)
    binding = BacktestRuntimeBinding(
        UUID(int=9001),
        run.exploratory_backtest_run_id,
        run.specification_sha256,
        action,
        runtime_run_id,
    )
    config_artifact_id = UUID(int=9002)
    row = {
        "backtest_runtime_binding_id": binding.backtest_runtime_binding_id,
        "specification_sha256": str(run.specification_sha256),
        "action_id": action.action_id,
        "action_kind": action.kind.value,
        "action_content_sha256": str(action.content_sha256),
        "exploratory_backtest_arm_id": action.arm_id,
        "exploratory_backtest_fold_id": action.fold_id,
        "exploratory_backtest_fold_session_id": action.fold_session_id,
        "model_training_requirement_id": action.model_training_requirement_id,
        "evaluation_requirement_id": action.evaluation_requirement_id,
        "runtime_run_id": runtime_run_id,
        "content_sha256": str(binding.content_sha256),
        "runtime_mode": "HISTORICAL",
        "fire_key": str(action.action_id),
        "code_sha": "a" * 64,
        "config_artifact_id": config_artifact_id,
        "config_hash": "b" * 64,
        "runtime_state": state,
        "root_code_sha": "a" * 64,
        "root_config_artifact_id": config_artifact_id,
        "root_config_hash": "b" * 64,
        "latest_attempt_state": latest_attempt_state,
    }
    return run, action, row


def test_current_owner_without_runtime_lineage_is_integrity_mismatch() -> None:
    run, action, _ = _runtime_row(state="RUNNING")

    result = _reconcile_current_runtime(
        run,
        action,
        BacktestActionObservation(
            action.action_id,
            BacktestObservedState.MATCHED_COMPLETE,
        ),
        (),
    )

    assert result.state is BacktestObservedState.MISMATCH


def test_runtime_retryable_and_terminal_failures_remain_distinct() -> None:
    run, action, retryable = _runtime_row(
        state="RUNNING",
        latest_attempt_state="FAILED_RETRYABLE",
    )
    _, _, terminal = _runtime_row(
        state="FAILED",
        latest_attempt_state="FAILED_TERMINAL",
    )
    absent = BacktestActionObservation(
        action.action_id,
        BacktestObservedState.ABSENT,
    )

    retryable_result = _reconcile_current_runtime(
        run,
        action,
        absent,
        [retryable],
    )
    terminal_result = _reconcile_current_runtime(
        run,
        action,
        absent,
        [terminal],
    )

    assert retryable_result.state is BacktestObservedState.FAILED_RETRYABLE
    assert terminal_result.state is BacktestObservedState.FAILED_TERMINAL


def test_succeeded_runtime_requires_exact_completed_owner() -> None:
    run, action, succeeded = _runtime_row(state="SUCCEEDED")
    completed = BacktestActionObservation(
        action.action_id,
        BacktestObservedState.MATCHED_COMPLETE,
        BacktestResearchState.NOT_ESTIMABLE,
    )

    exact = _reconcile_current_runtime(run, action, completed, [succeeded])
    missing = _reconcile_current_runtime(
        run,
        action,
        BacktestActionObservation(
            action.action_id,
            BacktestObservedState.ABSENT,
        ),
        [succeeded],
    )

    assert exact == completed
    assert missing.state is BacktestObservedState.MISMATCH


def test_runtime_action_or_code_drift_is_integrity_mismatch() -> None:
    run, action, row = _runtime_row(state="RUNNING")
    row["code_sha"] = "c" * 64

    result = _reconcile_current_runtime(
        run,
        action,
        BacktestActionObservation(
            action.action_id,
            BacktestObservedState.ABSENT,
        ),
        [row],
    )

    assert result.state is BacktestObservedState.MISMATCH
