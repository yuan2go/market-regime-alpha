from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
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
from market_regime_alpha.research_qualification.application.backtests import (
    BacktestApplication,
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
    BacktestExecutionKind,
    BacktestFoldDependency,
    BacktestFoldSession,
    BacktestFoldSpecification,
    BacktestPolicyDefaults,
    BacktestSampleMember,
    BacktestSessionRole,
    BacktestSpecification,
    BacktestWalkForwardMode,
    BacktestWalkForwardPolicy,
    VersionedAuthorityBinding,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
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
                        raise ResearchUnknownCommitResultError(
                            "injected lost Backtest commit acknowledgement"
                        )

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
    assert archive_hash is not None and seal_hash is not None and universe is not None

    old_sessions = tuple(
        session for fold in legacy.folds for session in fold.sessions
    )
    fit_protocol = _authority(
        legacy.folds[0].evaluation_protocol_id,
        legacy.folds[0].evaluation_protocol_sha256,
    )
    validation_protocol = _authority(
        legacy.folds[1].evaluation_protocol_id,
        legacy.folds[1].evaluation_protocol_sha256,
    )

    def fold(ordinal, purpose, selected, protocol):
        role = (
            BacktestSessionRole.FIT_INPUT
            if purpose is PartitionPurpose.FIT
            else BacktestSessionRole.EVALUATION
        )
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
        candidate=_authority(
            legacy.candidate_policy_id, legacy.candidate_policy_sha256
        ),
        context=_authority(legacy.context_policy_id, legacy.context_policy_sha256),
        strategy=_authority(
            legacy.strategy_version_id, legacy.strategy_version_sha256
        ),
        portfolio=_authority(
            legacy.portfolio_policy_id, legacy.portfolio_policy_sha256
        ),
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
        for ordinal, (fold_item, arm) in enumerate(
            ((fold_item, arm) for fold_item in folds for arm in arms), start=1
        )
    )
    evaluations = tuple(
        BacktestEvaluationRequirement(
            uuid4(),
            fold_item.ordinal,
            fold_item.exploratory_backtest_fold_id,
            fold_item.evaluation_protocol,
            True,
        )
        for fold_item in folds
    )
    return BacktestSpecification(
        exploratory_backtest_run_id=uuid4(),
        run_code=f"generic-{uuid4().hex[:10]}",
        generation=42,
        hypothesis="Three arbitrary rule arms over two explicit expanding folds.",
        market_archive=_authority(legacy.market_archive_id, archive_hash[0]),
        market_archive_seal=_authority(legacy.market_archive_seal_id, seal_hash[0]),
        universe_revision=_authority(stack.universe_revision_id, universe[0]),
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
        feature_definitions=tuple(
            _authority(identity, content_hash)
            for identity, content_hash in legacy.feature_definitions
        ),
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

    reloaded = PostgresBacktestQueryPort(backtest_stack.pool).load(
        specification.exploratory_backtest_run_id
    )
    assert reloaded.specification_sha256 == specification.content_sha256
    assert reloaded.projection_sha256 == execution_plan.projection_sha256
    assert reloaded.fold_session_binding_count == 7

    with pytest.raises(IdempotencyKeyReusedError):
        application.predeclare(
            replace(specification, random_seed=1730),
            context,
        )


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
                    "exploratory_backtest_run_id": (
                        specification.exploratory_backtest_run_id
                    ),
                    "specification_schema_version": (
                        specification.specification_schema_version
                    ),
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

    assert {item.exploratory_backtest_run_id for item in results} == {
        specification.exploratory_backtest_run_id
    }
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

    assert result.exploratory_backtest_run_id == (
        specification.exploratory_backtest_run_id
    )
    assert result.replayed is True
    assert PostgresBacktestQueryPort(backtest_stack.pool).load(
        specification.exploratory_backtest_run_id
    ).specification_sha256 == specification.content_sha256
