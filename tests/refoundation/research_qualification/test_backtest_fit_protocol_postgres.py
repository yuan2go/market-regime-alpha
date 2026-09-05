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
