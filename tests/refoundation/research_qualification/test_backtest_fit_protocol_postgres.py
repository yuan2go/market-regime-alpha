from dataclasses import replace
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.backtest_uow import PostgresBacktestUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.evaluation_uow import PostgresEvaluationUnitOfWorkProvider
from market_regime_alpha.research_qualification.application.backtests import BacktestApplication
from market_regime_alpha.research_qualification.application.evaluations import EvaluationCommands
from market_regime_alpha.research_qualification.domain.evaluation import EvaluationProtocolPlan
from market_regime_alpha.research_qualification.domain.evaluation_formula import BacktestFormulaCode, BacktestMetricSurface, EvaluationFormulaDefinition
from market_regime_alpha.research_qualification.domain.research_vocabulary import EvaluationSourceKind, EvaluationSourceMeasure, EvaluationSliceKind, PartitionPurpose
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from tests.refoundation.research_qualification.test_backtest_postgres import _current_specification, _authority, backtest_stack
from tests.refoundation.research_qualification.test_exploratory_backtest_postgres import _context
from tests.refoundation.research_qualification.test_wp17p_evaluation_source_repository import _metric

__all__ = ['backtest_stack']


def test_backtest_rejects_validation_only_metrics_in_fit_before_creating_root(backtest_stack):
    stack = backtest_stack
    specification = _current_specification(stack)
    with stack.pool.connection(read_only=True) as connection:
        target_metric_id, target_metric_code = connection.execute(
            'SELECT target_metric_definition_id, metric_code FROM mra.target_metric_definition WHERE target_definition_id = %s ORDER BY ordinal LIMIT 1',
            (specification.target.authority_id,),
        ).fetchone()
    metric = replace(_metric(EvaluationSourceKind.SIGNAL_STATUS, EvaluationSourceMeasure.SIGNAL_PRESENT),
                     source_target_metric_definition_id=target_metric_id, source_metric_code=target_metric_code,
                     slice_kind=EvaluationSliceKind.ALL_MEMBERS, backtest_arm_kind=None)
    metric = replace(metric, formula=EvaluationFormulaDefinition(
        metric.evaluation_protocol_metric_id, BacktestFormulaCode.MEAN,
        1, 34, 'ROUND_HALF_EVEN', (), BacktestMetricSurface.SIGNAL_FORECAST,
    ))
    protocol = EvaluationProtocolPlan(
        uuid4(), 'invalid_fit_signal_protocol', 1, specification.target.authority_id,
        specification.target.version, str(specification.target.content_sha256),
        PartitionPurpose.FIT, 'DESCRIPTIVE_ENGINEERING_ONLY', (metric,),
        specification.code_artifact, specification.config_artifact, str(specification.provenance_sha256),
    )
    EvaluationCommands(PostgresEvaluationUnitOfWorkProvider(stack.pool, id_factory=uuid4), id_factory=uuid4).register_protocol(protocol, _context('invalid-fit-protocol'))
    fold_id = specification.folds[0].exploratory_backtest_fold_id
    binding = _authority(protocol.evaluation_protocol_id, protocol.content_sha256)
    specification = replace(
        specification,
        folds=tuple(replace(fold, evaluation_protocol=binding) if fold.exploratory_backtest_fold_id == fold_id else fold for fold in specification.folds),
        evaluation_requirements=tuple(replace(item, evaluation_protocol=binding) if item.fold_id == fold_id else item for item in specification.evaluation_requirements),
    )
    application = BacktestApplication(PostgresBacktestUnitOfWorkProvider(stack.pool), id_factory=uuid4)
    with pytest.raises(RuntimeStateConflictError) as error:
        application.predeclare(specification, _context('invalid-fit-campaign'))
    assert 'FIT' in str(error.value) and 'validation-only' in str(error.value), repr(error.value.__cause__)
    with stack.pool.connection(read_only=True) as connection:
        assert connection.execute('SELECT count(*) FROM mra.exploratory_backtest_run').fetchone() == (0,)


def test_backtest_rejects_outcome_checkpoint_as_forecast_commitment_before_execution(backtest_stack):
    from market_regime_alpha.decision_support.application.strategy import StrategyCommands
    from market_regime_alpha.decision_support.domain.strategy import StrategyPlan
    from market_regime_alpha.infrastructure.postgres.strategy_uow import PostgresStrategyUnitOfWorkProvider
    from market_regime_alpha.infrastructure.postgres.queries.decision_strategy import PostgresStrategyQueryProvider
    from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import _load_strategy

    stack = backtest_stack
    specification = _current_specification(stack)
    with stack.pool.connection(read_only=True) as connection:
        original = _load_strategy(connection, specification.defaults.strategy.authority_id, lock=False)
        checkpoint_id, checkpoint_hash = connection.execute(
            "SELECT target_checkpoint_id, content_sha256 FROM mra.target_checkpoint WHERE target_definition_id=%s AND checkpoint_role='OUTCOME_OBSERVATION' ORDER BY ordinal LIMIT 1",
            (specification.target.authority_id,),
        ).fetchone()
    version_id = uuid4()
    strategy = replace(
        original, strategy=StrategyPlan(uuid4(), 'invalid_forecast_checkpoint', 'Exact commitment binding regression'),
        strategy_version_id=version_id, version=1, supersedes_strategy_version_id=None,
        context_requirements=tuple(replace(r, strategy_context_requirement_id=uuid4(), strategy_version_id=version_id) for r in original.context_requirements),
        signal_rule=replace(original.signal_rule, strategy_signal_rule_id=uuid4(), strategy_version_id=version_id),
        forecast_rules=tuple(replace(r, strategy_forecast_rule_id=uuid4(), strategy_version_id=version_id, target_checkpoint_id=checkpoint_id, target_checkpoint_sha256=checkpoint_hash) for r in original.forecast_rules),
    )
    StrategyCommands(PostgresStrategyUnitOfWorkProvider(stack.pool), PostgresStrategyQueryProvider(stack.pool)).register(strategy, _context('invalid-forecast-strategy'))
    binding = _authority(version_id, strategy.content_sha256)
    specification = replace(specification, defaults=replace(specification.defaults, strategy=binding), arms=tuple(replace(arm, strategy=binding) for arm in specification.arms))
    application = BacktestApplication(PostgresBacktestUnitOfWorkProvider(stack.pool), id_factory=uuid4)
    with pytest.raises(RuntimeStateConflictError, match='Forecast.*Decision reference'):
        application.predeclare(specification, _context('invalid-forecast-campaign'))
    with stack.pool.connection(read_only=True) as connection:
        assert connection.execute('SELECT count(*) FROM mra.exploratory_backtest_run').fetchone() == (0,)


def test_backtest_rejects_observational_label_with_gating_strategy(backtest_stack):
    from market_regime_alpha.research_qualification.domain.backtest import BacktestContextMode, BacktestBindingSource
    specification = _current_specification(backtest_stack)
    specification = replace(specification, arms=tuple(
        replace(arm, strategy=specification.defaults.strategy, strategy_binding_source=BacktestBindingSource.SHARED_DEFAULT)
        if arm.context_mode is BacktestContextMode.OBSERVATIONAL else arm
        for arm in specification.arms
    ))
    application = BacktestApplication(PostgresBacktestUnitOfWorkProvider(backtest_stack.pool), id_factory=uuid4)
    with pytest.raises(RuntimeStateConflictError, match='OBSERVATIONAL.*OBSERVE_ONLY'):
        application.predeclare(specification, _context('invalid-observational-gate'))
    with backtest_stack.pool.connection(read_only=True) as connection:
        assert connection.execute('SELECT count(*) FROM mra.exploratory_backtest_run').fetchone() == (0,)
