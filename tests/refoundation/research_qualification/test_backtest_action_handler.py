from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from market_regime_alpha.interfaces.backtest_actions import (
    BacktestCanonicalActionHandler,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestActionKind,
    BacktestExpectedAction,
)


def test_evaluation_action_has_one_ordered_owner_runtime_dag() -> None:
    action = BacktestExpectedAction(
        action_id=UUID(int=1),
        ordinal=1,
        kind=BacktestActionKind.COMPLETE_FOLD_EVALUATION,
        exploratory_backtest_run_id=UUID(int=2),
        arm_id=UUID(int=3),
        fold_id=UUID(int=4),
        fold_session_id=None,
        model_training_requirement_id=None,
        dependency_action_ids=(),
        evaluation_requirement_id=UUID(int=5),
    )
    handler = BacktestCanonicalActionHandler(
        artifacts=cast(Any, SimpleNamespace()),
        selection=cast(Any, SimpleNamespace()),
        research_definitions=cast(Any, SimpleNamespace()),
        reads=cast(Any, SimpleNamespace()),
        feature_materializers=(cast(Any, SimpleNamespace()),),
        worker_id="test-worker",
    )

    steps = handler.steps(
        cast(
            BacktestSpecification,
            SimpleNamespace(content_sha256="f" * 64),
        ),
        action,
    )

    assert tuple(step.step_key for step in steps) == (
        "freeze-partition",
        "register-experiment",
        "open-experiment-run",
        "open-evaluation",
        "acquire-outcome-inputs",
        "evaluate",
        "bind-evaluation",
    )
    assert tuple(step.step_kind for step in steps) == (
        "FREEZE_PARTITION",
        "REGISTER_EXPERIMENT",
        "OPEN_EXPERIMENT_RUN",
        "OPEN_EVALUATION",
        "ACQUIRE_OUTCOME_INPUTS",
        "EVALUATE",
        "RECORD_EVIDENCE",
    )
    assert len({str(step.request_sha256) for step in steps}) == len(steps)


def test_model_action_has_one_ordered_owner_runtime_dag() -> None:
    action = BacktestExpectedAction(
        action_id=UUID(int=11),
        ordinal=1,
        kind=BacktestActionKind.TRAIN_MODEL,
        exploratory_backtest_run_id=UUID(int=12),
        arm_id=UUID(int=13),
        fold_id=UUID(int=14),
        fold_session_id=None,
        model_training_requirement_id=UUID(int=15),
        dependency_action_ids=(),
    )
    handler = BacktestCanonicalActionHandler(
        artifacts=cast(Any, SimpleNamespace()),
        selection=cast(Any, SimpleNamespace()),
        research_definitions=cast(Any, SimpleNamespace()),
        reads=cast(Any, SimpleNamespace()),
        feature_materializers=(cast(Any, SimpleNamespace()),),
        worker_id="test-worker",
    )

    steps = handler.steps(
        cast(
            BacktestSpecification,
            SimpleNamespace(content_sha256="f" * 64),
        ),
        action,
    )

    assert tuple(step.step_key for step in steps) == (
        "open-model-training",
        "register-model-version",
        "bind-model-lineage",
    )
    assert tuple(step.step_kind for step in steps) == (
        "OPEN_MODEL_TRAINING_RUN",
        "REGISTER_MODEL_VERSION",
        "RECORD_EVIDENCE",
    )
    assert len({str(step.request_sha256) for step in steps}) == len(steps)
