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


def test_dataset_names_do_not_collide_across_expanding_folds_or_shared_arm_prefixes():
    from datetime import UTC, datetime, time
    from market_regime_alpha.shared.hashing import sha256_bytes
    from market_regime_alpha.runtime.ports import ArtifactRecord
    day = date(2026, 1, 5)
    reference = SimpleNamespace(role="DECISION_REFERENCE", session_offset=0, local_time=time(14, 55), timezone_name="UTC")
    session = SimpleNamespace(session_date=day, open_at=datetime(2026, 1, 5, 9, tzinfo=UTC), close_at=datetime(2026, 1, 5, 15, tzinfo=UTC))
    template = SimpleNamespace(universe_id=UUID(int=101), market_provider_product_id=UUID(int=102), classification_scheme="INDEX_MEMBERSHIP", classification_code="CSI300")
    reads = SimpleNamespace(
        universe_template=lambda _spec: template,
        target_checkpoints=lambda _spec: (reference,),
        trading_session=lambda _spec, _id: session,
        retrospective_universe_id=lambda **_kwargs: UUID(int=103),
        eligible_population=lambda **_kwargs: (),
        archive_seal=lambda _spec: SimpleNamespace(knowledge_cutoff=datetime(2026, 9, 5, tzinfo=UTC)),
        feature_definitions=lambda _spec: (SimpleNamespace(feature_definition_id=UUID(int=104)),),
    )
    definitions = []
    def publish(content, **_kwargs):
        digest = sha256_bytes(content)
        return ArtifactRecord(UUID(digest[:32]), digest, len(content), "application/json", "objects/" + digest, "AVAILABLE", None, None)
    handler = BacktestCanonicalActionHandler(
        artifacts=cast(Any, SimpleNamespace(publish=publish)), selection=cast(Any, SimpleNamespace()),
        research_definitions=cast(Any, SimpleNamespace(register_exploratory_backtest_dataset=lambda definition, *_args, **_kwargs: definitions.append(definition))),
        reads=cast(Any, reads), feature_materializers=(cast(Any, SimpleNamespace()),), worker_id="test",
    )
    folds = tuple(SimpleNamespace(exploratory_backtest_fold_id=UUID(int=200+i), sessions=(SimpleNamespace(exploratory_backtest_fold_session_id=UUID(int=300+i), trading_session_id=UUID(int=400), session_date=day, role=BacktestSessionRole.FIT_INPUT),)) for i in range(2))
    spec = SimpleNamespace(exploratory_backtest_run_id=UUID(int=500), folds=folds, sample_members=(), eligibility_policy=AuthorityBinding(UUID(int=501), "a"*64), market_archive=AuthorityBinding(UUID(int=502), "b"*64), market_archive_seal=AuthorityBinding(UUID(int=503), "c"*64), code_artifact=ArtifactBinding(UUID(int=504), "d"*64, 1), config_artifact=ArtifactBinding(UUID(int=505), "e"*64, 1))
    for index, (arm, fold) in enumerate(((UUID(int=600), folds[0]), (UUID(int=600), folds[1]), (UUID(int=601), folds[0]))):
        action = BacktestExpectedAction(UUID(int=700+index), index+1, BacktestActionKind.MATERIALIZE_DATASET, spec.exploratory_backtest_run_id, arm, fold.exploratory_backtest_fold_id, fold.sessions[0].exploratory_backtest_fold_session_id, None, ())
        handler.execute_step(cast(Any, spec), action, cast(Any, SimpleNamespace(step_key="register-dataset")))
    assert len({d.dataset_id for d in definitions}) == 3
    assert len({(d.dataset_code, d.version) for d in definitions}) == 3
