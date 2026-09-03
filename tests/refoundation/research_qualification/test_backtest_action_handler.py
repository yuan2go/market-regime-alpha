from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from market_regime_alpha.interfaces.backtest_actions import (
    BacktestCanonicalActionHandler,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestEvaluationRequirement,
    BacktestEvaluationScopeKind,
    BacktestFoldSession,
    BacktestFoldSpecification,
    BacktestSessionRole,
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.decision_support.domain.context import (
    ContextKind,
    ContextState,
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


def test_context_evaluation_projects_exact_context_authority_into_partition() -> None:
    arm_id = UUID(int=31)
    requirement = BacktestEvaluationRequirement(
        requirement_id=UUID(int=32),
        ordinal=1,
        fold_id=None,
        evaluation_protocol=AuthorityBinding(UUID(int=33), "a" * 64),
        primary=False,
        scope_kind=BacktestEvaluationScopeKind.CONTEXT,
        arm_id=arm_id,
        slice_key="MARKET_REGIME:NEGATIVE",
    )
    fold = BacktestFoldSpecification(
        exploratory_backtest_fold_id=UUID(int=34),
        ordinal=1,
        purpose=PartitionPurpose.VALIDATION,
        exchange_code="XSHG",
        purge_sessions=0,
        embargo_sessions=0,
        evaluation_protocol=requirement.evaluation_protocol,
        sessions=(
            BacktestFoldSession(
                exploratory_backtest_fold_session_id=UUID(int=35),
                ordinal=1,
                trading_session_id=UUID(int=36),
                session_date=date(2026, 1, 5),
                role=BacktestSessionRole.EVALUATION,
            ),
        ),
    )
    specification = cast(
        BacktestSpecification,
        SimpleNamespace(
            exploratory_backtest_run_id=UUID(int=37),
            arm_folds=(SimpleNamespace(arm_id=arm_id, fold_id=fold.exploratory_backtest_fold_id),),
            folds=(fold,),
            exchange_code="XSHG",
            target=SimpleNamespace(
                authority_id=UUID(int=38),
                version=1,
                content_sha256="b" * 64,
            ),
            code_artifact=ArtifactBinding(UUID(int=39), "c" * 64, 1),
            config_artifact=ArtifactBinding(UUID(int=40), "d" * 64, 1),
            provenance_sha256="e" * 64,
        ),
    )
    action = BacktestExpectedAction(
        action_id=UUID(int=41),
        ordinal=1,
        kind=BacktestActionKind.COMPLETE_AGGREGATE_EVALUATION,
        exploratory_backtest_run_id=specification.exploratory_backtest_run_id,
        arm_id=arm_id,
        fold_id=None,
        fold_session_id=None,
        model_training_requirement_id=None,
        dependency_action_ids=(),
        evaluation_requirement_id=requirement.requirement_id,
    )
    handler = BacktestCanonicalActionHandler(
        artifacts=cast(Any, SimpleNamespace()),
        selection=cast(Any, SimpleNamespace()),
        research_definitions=cast(Any, SimpleNamespace()),
        reads=cast(Any, SimpleNamespace()),
        feature_materializers=(cast(Any, SimpleNamespace()),),
        worker_id="test-worker",
    )

    plan = handler._partition_plan(  # noqa: SLF001 - verifies projection boundary
        specification,
        action,
        requirement,
        UUID(int=42),
    )

    assert plan.backtest_source is not None
    assert plan.backtest_source.context_kind is ContextKind.MARKET_REGIME
    assert plan.backtest_source.context_state is ContextState.NEGATIVE
