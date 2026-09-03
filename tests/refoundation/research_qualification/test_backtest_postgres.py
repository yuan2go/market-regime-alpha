from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
import json
from uuid import uuid4
from threading import Lock

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.backtest_uow import (
    PostgresBacktestUnitOfWork,
    PostgresBacktestUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.backtests import (
    PostgresBacktestQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_history import (
    PostgresBacktestAuthorityQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_execution import (
    PostgresBacktestExecutionObservationPort,
)
from market_regime_alpha.interfaces.backtest import (
    decode_backtest_specification,
    encode_backtest_specification,
)
from market_regime_alpha.interfaces.cli import main as cli_main
from market_regime_alpha.infrastructure.postgres.research_model_uow import (
    PostgresResearchModelUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.application.backtests import (
    BacktestApplication,
)
from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutionPlanner,
)
from market_regime_alpha.research_qualification.domain.backtest import (
    AuthorityBinding,
    BacktestArmFold,
    BacktestArmSpecification,
    BacktestComparisonRole,
    BacktestContextMode,
    BacktestCostAssumption,
    BacktestCostChargeSide,
    BacktestCostKind,
    BacktestEvaluationRequirement,
    BacktestEvaluationScopeKind,
    BacktestExecutionKind,
    BacktestFoldDependency,
    BacktestFoldSession,
    BacktestFoldSpecification,
    BacktestModelTrainingRecipe,
    BacktestModelTrainingRequirement,
    BacktestPolicyDefaults,
    BacktestSampleMember,
    BacktestSessionRole,
    BacktestSpecification,
    BacktestWalkForwardMode,
    BacktestWalkForwardPolicy,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestObservedState,
    BacktestRuntimeBinding,
)
from market_regime_alpha.research_qualification.domain.backtest_compatibility import (
    HistoricalBacktestCompatibilityError,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.research_qualification.application.research_models import (
    ModelCommands,
)
from market_regime_alpha.research_qualification.domain.research_models import (
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelScalarType,
    ResearchModelPlan,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)
from market_regime_alpha.research_qualification.errors import (
    ResearchUnknownCommitResultError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash

from tests.refoundation.research_qualification import (
    test_exploratory_backtest_postgres as _legacy,
)


class _UnknownCommitBacktestProvider:
    def __init__(self, pool) -> None:
        self._pool = pool
        self._lock = Lock()
        self._raised = False

    def __call__(self):
        provider = self

        class _UnknownCommitBacktestUow(PostgresBacktestUnitOfWork):
            def commit(self) -> None:
                super().commit()
                with provider._lock:
                    if not provider._raised:
                        provider._raised = True
                        raise ResearchUnknownCommitResultError("injected lost Backtest commit acknowledgement")

        return _UnknownCommitBacktestUow(self._pool)


@pytest.fixture
def backtest_stack(target_database_url, tmp_path, request):
    return _legacy.backtest_stack.__wrapped__(target_database_url, tmp_path, request)


def _authority(identity, content_sha256) -> AuthorityBinding:
    return AuthorityBinding(identity, str(content_sha256))


def _current_specification(stack) -> BacktestSpecification:
    legacy = _legacy._plan(stack)
    with stack.pool.connection(read_only=True) as connection:
        archive_hash = connection.execute(
            "SELECT content_sha256 FROM mra.market_archive WHERE market_archive_id = %s",
            (legacy.market_archive_id,),
        ).fetchone()
        seal_hash = connection.execute(
            "SELECT content_sha256 FROM mra.market_archive_seal WHERE market_archive_seal_id = %s",
            (legacy.market_archive_seal_id,),
        ).fetchone()
        universe = connection.execute(
            """
            SELECT scope_content_sha256
            FROM mra.universe_revision
            WHERE universe_revision_id = %s
            """,
            (stack.universe_revision_id,),
        ).fetchone()
        eligibility = connection.execute(
            """
            SELECT content_sha256
            FROM mra.eligibility_policy
            WHERE eligibility_policy_id = %s
            """,
            (stack.eligibility_policy_id,),
        ).fetchone()
    assert archive_hash is not None and seal_hash is not None and universe is not None and eligibility is not None

    old_sessions = tuple(session for fold in legacy.folds for session in fold.sessions)
    fit_protocol = _authority(
        legacy.folds[0].evaluation_protocol_id,
        legacy.folds[0].evaluation_protocol_sha256,
    )
    validation_protocol = _authority(
        legacy.folds[1].evaluation_protocol_id,
        legacy.folds[1].evaluation_protocol_sha256,
    )

    def fold(ordinal, purpose, selected, protocol):
        role = BacktestSessionRole.FIT_INPUT if purpose is PartitionPurpose.FIT else BacktestSessionRole.EVALUATION
        return BacktestFoldSpecification(
            exploratory_backtest_fold_id=uuid4(),
            ordinal=ordinal,
            purpose=purpose,
            exchange_code="XSHG",
            purge_sessions=0,
            embargo_sessions=0,
            evaluation_protocol=protocol,
            sessions=tuple(
                BacktestFoldSession(
                    exploratory_backtest_fold_session_id=uuid4(),
                    ordinal=index,
                    trading_session_id=session.trading_session_id,
                    session_date=session.session_date,
                    role=role,
                )
                for index, session in enumerate(selected, start=1)
            ),
        )

    folds = (
        fold(1, PartitionPurpose.FIT, old_sessions[:2], fit_protocol),
        fold(
            2,
            PartitionPurpose.VALIDATION,
            old_sessions[2:3],
            validation_protocol,
        ),
        fold(3, PartitionPurpose.FIT, old_sessions[:3], fit_protocol),
        fold(
            4,
            PartitionPurpose.VALIDATION,
            old_sessions[3:4],
            validation_protocol,
        ),
    )
    costs = (
        BacktestCostAssumption(
            uuid4(),
            1,
            BacktestCostKind.COMMISSION_BPS,
            BacktestCostChargeSide.BOTH,
            Decimal("3"),
        ),
        BacktestCostAssumption(
            uuid4(),
            2,
            BacktestCostKind.STAMP_DUTY_BPS,
            BacktestCostChargeSide.SELL,
            Decimal("5"),
        ),
    )
    cost_hash = canonical_json_sha256(
        tuple(
            {
                "content_sha256": str(cost.content_sha256),
                "assumption_id": cost.assumption_id,
                "ordinal": cost.ordinal,
            }
            for cost in costs
        )
    )
    defaults = BacktestPolicyDefaults(
        candidate=_authority(legacy.candidate_policy_id, legacy.candidate_policy_sha256),
        context=_authority(legacy.context_policy_id, legacy.context_policy_sha256),
        strategy=_authority(legacy.strategy_version_id, legacy.strategy_version_sha256),
        portfolio=_authority(legacy.portfolio_policy_id, legacy.portfolio_policy_sha256),
        risk=_authority(legacy.risk_policy_id, legacy.risk_policy_sha256),
    )
    arms = tuple(
        BacktestArmSpecification(
            exploratory_backtest_arm_id=uuid4(),
            ordinal=ordinal,
            arm_code=code,
            execution_kind=BacktestExecutionKind.RULE,
            comparison_role=role,
            context_mode=context_mode,
            candidate=defaults.candidate,
            context=defaults.context,
            strategy=defaults.strategy,
            model=None,
            portfolio=defaults.portfolio,
            risk=defaults.risk,
            effective_cost_roster_sha256=cost_hash,
        )
        for ordinal, (code, role, context_mode) in enumerate(
            (
                (
                    "rule-baseline",
                    BacktestComparisonRole.BASELINE,
                    BacktestContextMode.CURRENT_GATE,
                ),
                (
                    "rule-challenger",
                    BacktestComparisonRole.CHALLENGER,
                    BacktestContextMode.CURRENT_GATE,
                ),
                (
                    "rule-diagnostic",
                    BacktestComparisonRole.DIAGNOSTIC,
                    BacktestContextMode.OBSERVATIONAL,
                ),
            ),
            start=1,
        )
    )
    dependencies = (
        BacktestFoldDependency(
            uuid4(),
            1,
            folds[0].exploratory_backtest_fold_id,
            folds[1].exploratory_backtest_fold_id,
        ),
        BacktestFoldDependency(
            uuid4(),
            2,
            folds[2].exploratory_backtest_fold_id,
            folds[3].exploratory_backtest_fold_id,
        ),
    )
    arm_folds = tuple(
        BacktestArmFold(
            uuid4(),
            ordinal,
            arm.exploratory_backtest_arm_id,
            fold_item.exploratory_backtest_fold_id,
        )
        for ordinal, (fold_item, arm) in enumerate(((fold_item, arm) for fold_item in folds for arm in arms), start=1)
    )
    fold_by_id = {fold_item.exploratory_backtest_fold_id: fold_item for fold_item in folds}
    evaluations = tuple(
        BacktestEvaluationRequirement(
            uuid4(),
            ordinal,
            participation.fold_id,
            fold_by_id[participation.fold_id].evaluation_protocol,
            True,
            arm_id=participation.arm_id,
        )
        for ordinal, participation in enumerate(arm_folds, start=1)
    ) + tuple(
        BacktestEvaluationRequirement(
            uuid4(),
            len(arm_folds) + ordinal,
            None,
            validation_protocol,
            True,
            scope_kind=BacktestEvaluationScopeKind.AGGREGATE,
            arm_id=arm.exploratory_backtest_arm_id,
        )
        for ordinal, arm in enumerate(arms, start=1)
    )
    return BacktestSpecification(
        exploratory_backtest_run_id=uuid4(),
        run_code=f"generic-{uuid4().hex[:10]}",
        generation=42,
        hypothesis="Three arbitrary rule arms over two explicit expanding folds.",
        market_archive=_authority(legacy.market_archive_id, archive_hash[0]),
        market_archive_seal=_authority(legacy.market_archive_seal_id, seal_hash[0]),
        universe_revision=_authority(stack.universe_revision_id, universe[0]),
        eligibility_policy=_authority(stack.eligibility_policy_id, eligibility[0]),
        sample_scope_code="deterministic-one",
        sample_members=(
            BacktestSampleMember(
                stack.universe_member_id,
                stack.instrument_id.value,
                1,
            ),
        ),
        exchange_code="XSHG",
        first_trading_session_id=old_sessions[0].trading_session_id,
        last_trading_session_id=old_sessions[3].trading_session_id,
        feature_definitions=tuple(_authority(identity, content_hash) for identity, content_hash in legacy.feature_definitions),
        target=VersionedAuthorityBinding(
            legacy.target_definition_id,
            legacy.target_version,
            legacy.target_definition_sha256,
        ),
        defaults=defaults,
        arms=arms,
        folds=folds,
        fold_dependencies=dependencies,
        arm_folds=arm_folds,
        model_training_requirements=(),
        walk_forward_policy=BacktestWalkForwardPolicy(
            "expanding-v1",
            1,
            BacktestWalkForwardMode.EXPANDING,
            2,
            1,
            1,
        ),
        cost_assumptions=costs,
        evaluation_requirements=evaluations,
        random_seed=1729,
        code_artifact=ArtifactBinding(
            legacy.code_artifact.artifact_id,
            legacy.code_artifact.content_sha256,
            legacy.code_artifact.size_bytes,
        ),
        config_artifact=ArtifactBinding(
            legacy.config_artifact.artifact_id,
            legacy.config_artifact.content_sha256,
            legacy.config_artifact.size_bytes,
        ),
        provenance_sha256=legacy.provenance_sha256,
    )


def _current_model_specification(stack) -> BacktestSpecification:
    rule_specification = _current_specification(stack)
    model_id = uuid4()
    model_plan = ResearchModelPlan(
        model_id=model_id,
        model_code=f"generic_ridge_{uuid4().hex[:8]}",
        target_definition_id=rule_specification.target.authority_id,
        target_version=rule_specification.target.version,
        target_definition_sha256=rule_specification.target.content_sha256,
        feature_definitions=tuple((item.authority_id, item.content_sha256) for item in rule_specification.feature_definitions),
        code_artifact=rule_specification.code_artifact,
        config_artifact=rule_specification.config_artifact,
        provenance_sha256="a" * 64,
    )
    ModelCommands(
        PostgresResearchModelUnitOfWorkProvider(stack.pool),
        id_factory=uuid4,
    ).register_model(
        model_plan,
        _legacy._context("register-current-backtest-model"),
    )
    model_binding = AuthorityBinding(model_id, model_plan.content_sha256)
    model_arm = replace(
        rule_specification.arms[1],
        arm_code="model-challenger",
        execution_kind=BacktestExecutionKind.MODEL,
        model=model_binding,
    )
    arms = (
        rule_specification.arms[0],
        model_arm,
        rule_specification.arms[2],
    )
    recipe = BacktestModelTrainingRecipe(
        algorithm_code="deterministic_ridge",
        algorithm_version="1.0.0",
        implementation_sha256="d" * 64,
        environment=ModelExecutionEnvironment(
            python_implementation="cpython",
            python_version="3.12.11",
            runtime_code="uv",
            runtime_version="0.8.13",
            uv_lock_sha256="e" * 64,
            dependencies=(
                ModelDependencyVersion(
                    1,
                    "market_regime_alpha",
                    "0.1.0",
                    "f" * 64,
                ),
            ),
        ),
        hyperparameters=(
            ModelScalarParameter(
                1,
                "ridge_alpha",
                ModelScalarType.DECIMAL,
                decimal_value=Decimal("0.01"),
            ),
        ),
    )
    fold_by_id = {fold.exploratory_backtest_fold_id: fold for fold in rule_specification.folds}
    requirements = []
    with stack.pool.connection(read_only=True) as connection:
        for ordinal, dependency in enumerate(
            rule_specification.fold_dependencies,
            start=1,
        ):
            fit_protocol = fold_by_id[dependency.fit_fold_id].evaluation_protocol
            metric_row = connection.execute(
                """
                SELECT evaluation_protocol_metric_id, content_sha256
                FROM mra.evaluation_protocol_metric
                WHERE evaluation_protocol_id = %s
                ORDER BY ordinal
                LIMIT 1
                """,
                (fit_protocol.authority_id,),
            ).fetchone()
            assert metric_row is not None
            requirements.append(
                BacktestModelTrainingRequirement(
                    requirement_id=uuid4(),
                    ordinal=ordinal,
                    model_arm_id=model_arm.exploratory_backtest_arm_id,
                    fit_fold_id=dependency.fit_fold_id,
                    validation_fold_id=dependency.validation_fold_id,
                    model_definition=model_binding,
                    training_metric=AuthorityBinding(
                        metric_row[0],
                        metric_row[1],
                    ),
                    planned_model_version=ordinal,
                    recipe=recipe,
                )
            )
    return replace(
        rule_specification,
        arms=arms,
        model_training_requirements=tuple(requirements),
    )


def test_current_predeclaration_is_root_owned_relational_and_replayable(
    backtest_stack,
) -> None:
    specification = _current_specification(backtest_stack)
    application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )
    context = _legacy._context("generic-predeclare")

    receipt_count_before = _receipt_count(backtest_stack)
    validation = application.validate(specification)
    execution_plan = application.plan(specification)
    assert _receipt_count(backtest_stack) == receipt_count_before
    assert validation.valid is True
    assert len(execution_plan.arms) == 3

    result = application.predeclare(specification, context)
    replay = application.predeclare(specification, context)

    assert result.replayed is False
    assert replay.replayed is True
    assert replay.result_hash == result.result_hash
    with psycopg.connect(backtest_stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT root.session_count, root.current_specification_sha256,
                   specification.distinct_trading_session_count,
                   specification.fold_session_binding_count,
                   (SELECT count(*) FROM mra.backtest_arm_specification
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id),
                   (SELECT count(*) FROM mra.backtest_fold_dependency
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id),
                   (SELECT count(*) FROM mra.backtest_arm_fold
                    WHERE exploratory_backtest_run_id = root.exploratory_backtest_run_id)
            FROM mra.exploratory_backtest_run AS root
            JOIN mra.backtest_specification AS specification
              USING (exploratory_backtest_run_id)
            WHERE root.exploratory_backtest_run_id = %s
            """,
            (specification.exploratory_backtest_run_id,),
        ).fetchone()
        overlap = connection.execute(
            """
            SELECT count(*) - count(DISTINCT trading_session_id)
            FROM mra.exploratory_backtest_fold_session
            WHERE exploratory_backtest_run_id = %s
            """,
            (specification.exploratory_backtest_run_id,),
        ).fetchone()
    assert row == (
        None,
        str(specification.content_sha256),
        4,
        7,
        3,
        2,
        12,
    )
    assert overlap == (3,)

    reloaded = PostgresBacktestQueryPort(backtest_stack.pool).load(specification.exploratory_backtest_run_id)
    assert reloaded.specification_sha256 == specification.content_sha256
    assert reloaded.projection_sha256 == execution_plan.projection_sha256
    assert reloaded.fold_session_binding_count == 7

    reloaded_specification = PostgresBacktestQueryPort(backtest_stack.pool).load_specification(specification.exploratory_backtest_run_id)
    assert reloaded_specification == specification
    assert reloaded_specification.content_sha256 == reloaded.specification_sha256

    with pytest.raises(IdempotencyKeyReusedError):
        application.predeclare(
            replace(specification, random_seed=1730),
            context,
        )


def test_generic_authority_query_loads_current_closure_and_root_artifacts(
    backtest_stack,
) -> None:
    specification = _current_specification(backtest_stack)
    BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    ).predeclare(
        specification,
        _legacy._context("generic-authority-current"),
    )

    receipt_count_before = _receipt_count(backtest_stack)
    snapshot = PostgresBacktestAuthorityQueryPort(backtest_stack.pool).load(specification.exploratory_backtest_run_id)

    assert snapshot.run.specification_sha256 == specification.content_sha256
    assert snapshot.run.exploratory_backtest_run_id == (specification.exploratory_backtest_run_id)
    assert {(binding.artifact_id, binding.content_sha256, binding.size_bytes) for binding in snapshot.artifact_bindings} == {
        (
            specification.code_artifact.artifact_id,
            specification.code_artifact.content_sha256,
            specification.code_artifact.size_bytes,
        ),
        (
            specification.config_artifact.artifact_id,
            specification.config_artifact.content_sha256,
            specification.config_artifact.size_bytes,
        ),
    }
    assert _receipt_count(backtest_stack) == receipt_count_before


def test_generic_authority_query_does_not_treat_missing_current_spec_as_legacy(
    backtest_stack,
) -> None:
    legacy = _legacy._plan(backtest_stack)
    _legacy.ExploratoryBacktestCommands(
        _legacy.PostgresExploratoryBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    ).register(
        legacy,
        _legacy._context("generic-authority-non-allowlisted-legacy"),
    )

    receipt_count_before = _receipt_count(backtest_stack)
    with pytest.raises(
        HistoricalBacktestCompatibilityError,
        match="missing current specification is not a legacy contract",
    ):
        PostgresBacktestAuthorityQueryPort(backtest_stack.pool).load(legacy.exploratory_backtest_run_id)
    assert _receipt_count(backtest_stack) == receipt_count_before


def test_current_model_recipe_round_trips_as_typed_relational_closure(
    backtest_stack,
) -> None:
    specification = _current_model_specification(backtest_stack)
    application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )

    application.predeclare(
        specification,
        _legacy._context("model-recipe-predeclare"),
    )
    reloaded = PostgresBacktestQueryPort(backtest_stack.pool).load_specification(specification.exploratory_backtest_run_id)

    assert reloaded == specification
    assert reloaded.model_training_requirements[0].recipe is not None
    assert (
        reloaded.model_training_requirements[0].recipe.content_sha256 == specification.model_training_requirements[0].recipe.content_sha256
    )
    with backtest_stack.pool.connection(read_only=True) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*)
                 FROM mra.backtest_model_training_requirement
                WHERE exploratory_backtest_run_id = %s),
              (SELECT count(*)
                 FROM mra.backtest_model_training_dependency
                WHERE exploratory_backtest_run_id = %s),
              (SELECT count(*)
                 FROM mra.backtest_model_training_hyperparameter
                WHERE exploratory_backtest_run_id = %s)
            """,
            (
                specification.exploratory_backtest_run_id,
                specification.exploratory_backtest_run_id,
                specification.exploratory_backtest_run_id,
            ),
        ).fetchone()
    assert counts == (2, 2, 2)


def test_operator_json_round_trips_complete_typed_current_specification(
    backtest_stack,
) -> None:
    specification = _current_model_specification(backtest_stack)

    encoded = encode_backtest_specification(specification)
    decoded = decode_backtest_specification(encoded)

    assert decoded == specification
    assert encode_backtest_specification(decoded) == encoded


def test_generic_backtest_cli_validate_plan_predeclare_and_inspect_are_application_backed(
    backtest_stack,
    tmp_path,
) -> None:
    specification = _current_specification(backtest_stack)
    input_path = tmp_path / "backtest-specification.json"
    input_path.write_bytes(encode_backtest_specification(specification))
    environment = {
        "MRA_DATABASE_URL": backtest_stack.database_url,
        "MRA_ARTIFACT_ROOT": str((tmp_path / "cli-artifacts").resolve()),
        "MRA_SCHEMA": "mra",
        "MRA_SCHEMA_EPOCH": "MRA_REFOUNDATION_1",
        "MRA_POOL_MIN_SIZE": "0",
        "MRA_POOL_MAX_SIZE": "2",
    }
    receipt_count_before = _receipt_count(backtest_stack)

    validate_output = StringIO()
    assert (
        cli_main(
            ["backtest", "validate", "--specification", str(input_path)],
            environ=environment,
            stdout=validate_output,
            stderr=StringIO(),
        )
        == 0
    )
    plan_output = StringIO()
    assert (
        cli_main(
            ["backtest", "plan", "--specification", str(input_path)],
            environ=environment,
            stdout=plan_output,
            stderr=StringIO(),
        )
        == 0
    )
    assert json.loads(validate_output.getvalue())["valid"] is True
    assert json.loads(plan_output.getvalue())["source"] == "CURRENT_RELATIONAL"
    assert _receipt_count(backtest_stack) == receipt_count_before

    predeclare_output = StringIO()
    assert (
        cli_main(
            [
                "backtest",
                "predeclare",
                "--specification",
                str(input_path),
                "--actor-id",
                "backtest-cli-test",
                "--idempotency-key",
                "backtest-cli-predeclare",
            ],
            environ=environment,
            stdout=predeclare_output,
            stderr=StringIO(),
        )
        == 0
    )
    inspect_output = StringIO()
    assert (
        cli_main(
            [
                "backtest",
                "inspect",
                "--run-id",
                str(specification.exploratory_backtest_run_id),
            ],
            environ=environment,
            stdout=inspect_output,
            stderr=StringIO(),
        )
        == 0
    )
    assert json.loads(predeclare_output.getvalue())["exploratory_backtest_run_id"] == str(specification.exploratory_backtest_run_id)
    assert json.loads(inspect_output.getvalue())["execution_state"] == "PLANNED"


def test_database_recomputes_current_model_recipe_child_hash(
    backtest_stack,
) -> None:
    specification = _current_model_specification(backtest_stack)
    recipe = specification.model_training_requirements[0].recipe
    assert recipe is not None
    object.__setattr__(
        recipe.environment.dependencies[0],
        "content_sha256",
        ContentHash("0" * 64),
    )

    with pytest.raises(RuntimeStateConflictError):
        BacktestApplication(
            PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
            id_factory=uuid4,
        ).predeclare(
            specification,
            _legacy._context("forged-model-recipe-child"),
        )

    with backtest_stack.pool.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM mra.exploratory_backtest_run
            WHERE exploratory_backtest_run_id = %s
            """,
            (specification.exploratory_backtest_run_id,),
        ).fetchone()
    assert row == (0,)


def _receipt_count(stack) -> int:
    with stack.pool.connection(read_only=True) as connection:
        row = connection.execute("SELECT count(*) FROM mra.command_receipt").fetchone()
    assert row is not None
    return int(row[0])


def test_database_recomputes_current_specification_hash(backtest_stack) -> None:
    specification = _current_specification(backtest_stack)
    forged_hash = ContentHash("0" * 64)
    object.__setattr__(specification, "content_sha256", forged_hash)
    object.__setattr__(
        specification,
        "definition_sha256",
        ContentHash(
            canonical_json_sha256(
                {
                    "current_specification_sha256": str(forged_hash),
                    "exploratory_backtest_run_id": (specification.exploratory_backtest_run_id),
                    "specification_schema_version": (specification.specification_schema_version),
                }
            )
        ),
    )
    application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )

    with pytest.raises(RuntimeStateConflictError):
        application.predeclare(
            specification,
            _legacy._context("forged-current-specification"),
        )

    with backtest_stack.pool.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM mra.exploratory_backtest_run
            WHERE exploratory_backtest_run_id = %s
            """,
            (specification.exploratory_backtest_run_id,),
        ).fetchone()
    assert row == (0,)


def test_current_predeclaration_freezes_sparse_arm_fold_participation(
    backtest_stack,
) -> None:
    complete = _current_specification(backtest_stack)
    fit_ids = {fold.exploratory_backtest_fold_id for fold in complete.folds if fold.purpose is PartitionPurpose.FIT}
    first_arm_id = complete.arms[0].exploratory_backtest_arm_id
    selected = tuple(binding for binding in complete.arm_folds if not (binding.arm_id == first_arm_id and binding.fold_id in fit_ids))
    selected_scopes = {(item.arm_id, item.fold_id) for item in selected}
    selected_requirements = tuple(
        requirement
        for requirement in complete.evaluation_requirements
        if requirement.scope_kind is not BacktestEvaluationScopeKind.FOLD or (requirement.arm_id, requirement.fold_id) in selected_scopes
    )
    sparse = replace(
        complete,
        arm_folds=tuple(replace(binding, ordinal=ordinal) for ordinal, binding in enumerate(selected, start=1)),
        evaluation_requirements=tuple(
            replace(requirement, ordinal=ordinal) for ordinal, requirement in enumerate(selected_requirements, start=1)
        ),
    )
    application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )

    result = application.predeclare(
        sparse,
        _legacy._context("sparse-arm-fold-participation"),
    )

    assert result.exploratory_backtest_run_id == sparse.exploratory_backtest_run_id
    with backtest_stack.pool.connection(read_only=True) as connection:
        count = connection.execute(
            """
            SELECT count(*) FROM mra.backtest_arm_fold
            WHERE exploratory_backtest_run_id = %s
            """,
            (sparse.exploratory_backtest_run_id,),
        ).fetchone()
    assert count == (10,)


def test_concurrent_current_predeclaration_converges_on_one_identity(
    backtest_stack,
) -> None:
    specification = _current_specification(backtest_stack)
    context = _legacy._context("concurrent-generic-predeclare")

    def execute(_index):
        return BacktestApplication(
            PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
            id_factory=uuid4,
        ).predeclare(specification, context)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(execute, range(2)))

    assert {item.exploratory_backtest_run_id for item in results} == {specification.exploratory_backtest_run_id}
    assert sorted(item.replayed for item in results) == [False, True]
    with backtest_stack.pool.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM mra.backtest_specification
            WHERE exploratory_backtest_run_id = %s
            """,
            (specification.exploratory_backtest_run_id,),
        ).fetchone()
    assert row == (1,)


def test_database_recomputes_current_arm_content_hash(backtest_stack) -> None:
    specification = _current_specification(backtest_stack)
    object.__setattr__(specification.arms[0], "content_sha256", ContentHash("0" * 64))
    forged = replace(specification, arms=specification.arms)
    application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )

    with pytest.raises(RuntimeStateConflictError):
        application.predeclare(
            forged,
            _legacy._context("forged-current-arm"),
        )


def test_unknown_commit_reconciles_exact_current_backtest(backtest_stack) -> None:
    specification = _current_specification(backtest_stack)
    application = BacktestApplication(
        _UnknownCommitBacktestProvider(backtest_stack.pool),
        id_factory=uuid4,
    )

    result = application.predeclare(
        specification,
        _legacy._context("unknown-commit-generic-predeclare"),
    )

    assert result.exploratory_backtest_run_id == (specification.exploratory_backtest_run_id)
    assert result.replayed is True
    assert (
        PostgresBacktestQueryPort(backtest_stack.pool).load(specification.exploratory_backtest_run_id).specification_sha256
        == specification.content_sha256
    )


def test_runtime_action_binding_is_application_backed_append_only_lineage(
    backtest_stack,
) -> None:
    specification = _current_specification(backtest_stack)
    application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(backtest_stack.pool),
        id_factory=uuid4,
    )
    application.predeclare(
        specification,
        _legacy._context("runtime-binding-predeclare"),
    )
    frozen = application.plan(specification)
    action = BacktestExecutionPlanner().compile(frozen).expected_actions[0]
    schedule_id = uuid4()
    runtime_run_id = uuid4()
    with psycopg.connect(backtest_stack.database_url) as connection:
        connection.execute(
            """
            INSERT INTO mra.runtime_schedule (
                schedule_id, schedule_code, revision, runtime_mode,
                schedule_expression, timezone_name, step_catalog_hash, enabled
            ) VALUES (%s, %s, 1, 'HISTORICAL', NULL, 'Asia/Shanghai', %s, true)
            """,
            (schedule_id, f"generic-backtest-{uuid4().hex[:8]}", "f" * 64),
        )
        connection.execute(
            """
            INSERT INTO mra.runtime_run (
                run_id, schedule_id, fire_key, runtime_mode, requested_at,
                decision_time, code_sha, config_artifact_id, config_hash,
                schema_epoch, state
            ) VALUES (
                %s, %s, %s, 'HISTORICAL', %s, NULL, %s, %s, %s,
                'MRA_REFOUNDATION_1', 'QUEUED'
            )
            """,
            (
                runtime_run_id,
                schedule_id,
                str(action.action_id),
                datetime.now(UTC),
                str(specification.code_artifact.content_sha256),
                specification.config_artifact.artifact_id,
                str(specification.config_artifact.content_sha256),
            ),
        )
    binding = BacktestRuntimeBinding(
        uuid4(),
        specification.exploratory_backtest_run_id,
        specification.content_sha256,
        action,
        runtime_run_id,
    )
    context = _legacy._context("bind-runtime-action")

    first = application.bind_runtime(binding, context)
    replay = application.bind_runtime(binding, context)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.binding_id == binding.backtest_runtime_binding_id
    with psycopg.connect(backtest_stack.database_url) as connection:
        row = connection.execute(
            """
            SELECT action_id, runtime_run_id, content_sha256
            FROM mra.backtest_runtime_binding
            WHERE backtest_runtime_binding_id = %s
            """,
            (binding.backtest_runtime_binding_id,),
        ).fetchone()
    assert row == (
        action.action_id,
        runtime_run_id,
        str(binding.content_sha256),
    )
    observations = PostgresBacktestExecutionObservationPort(backtest_stack.pool).observe(frozen, (action,))
    assert len(observations) == 1
    assert observations[0].action_id == action.action_id
    assert observations[0].state is BacktestObservedState.MATCHED_INCOMPLETE
