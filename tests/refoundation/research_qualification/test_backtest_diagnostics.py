from dataclasses import replace
from datetime import date
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.backtest_diagnostics import (
    FunnelCell, FunnelMember, FunnelSnapshot, summarize_funnel,
)


def _snapshot():
    cell = FunnelCell('arm', 'fold', 'session', date(2026, 2, 25), 'EVALUATION', 'dataset', 'decision', 1, 0, 0, 0, 0)
    eligible = FunnelMember('arm', 'session', 'instrument-a', 'INCLUDED', 'ELIGIBLE', (), 'candidate-a', 'SELECTED', 'SELECTED', (), (), (), (), (), (), (), ('AVAILABLE',))
    excluded = replace(eligible, instrument_id='instrument-b', eligibility='INELIGIBLE', eligibility_reasons=('FAIL:EXPLICIT_CRITERION_FAILED:TRADING_STATUS:SUSPENDED',), candidate_id=None, candidate_disposition=None, candidate_reason=None, outcome_states=())
    return FunnelSnapshot(UUID(int=1), 'a' * 64, 'test', 12, 'cluster', ('instrument-a', 'instrument-b'), (cell,), (eligible, excluded), (), ())


def test_legitimate_exclusion_preserves_frozen_denominator_and_is_not_a_source_gap():
    summary = summarize_funnel(_snapshot())
    assert summary['declared_member_cell_count'] == 2
    assert summary['candidate_member_cell_count'] == 1
    assert summary['legal_eligibility_exclusion_count'] == 1
    assert summary['unexplained_member_loss_count'] == 0
    assert summary['feature_source_gap_reason_member_count'] == 0
    assert summary['eligible_denominator_count'] == 1


def test_duplicate_or_missing_member_is_not_silently_deduplicated():
    source = _snapshot()
    with pytest.raises(ValueError, match='complete.*roster'):
        summarize_funnel(replace(source, members=source.members[:1]))
    with pytest.raises(ValueError, match='duplicate'):
        summarize_funnel(replace(source, members=(*source.members, source.members[0])))


def test_missing_eligible_candidate_remains_unexplained():
    source = _snapshot()
    damaged = replace(source.members[0], candidate_id=None, candidate_disposition=None)
    summary = summarize_funnel(replace(source, members=(damaged, source.members[1])))
    assert summary['unexplained_member_loss_count'] == 1
    assert summary['legal_eligibility_exclusion_count'] == 1


def _application(snapshot=None, *, matched=True, report_source=None):
    from market_regime_alpha.research_qualification.application.backtest_diagnostics import BacktestDiagnosticsApplication
    from market_regime_alpha.research_qualification.application.backtest_reports import BacktestReportApplication
    from market_regime_alpha.research_qualification.domain.backtest_diagnostics import FunnelMetricInput
    from tests.refoundation.research_qualification.test_backtest_reports import _source, _Source, _Verifier
    source = report_source or _source()
    observed = snapshot or replace(_snapshot(), run_id=source.run.exploratory_backtest_run_id,
        specification_sha256=str(source.run.specification_sha256),
        metric_inputs=tuple(FunnelMetricInput(str(m.evaluation_metric_id), 2, None, 1, 1, 1, 1, (('INCLUDED', 1),)) for m in source.metrics))
    class Facts:
        def load(self, run_id):
            return observed
    reports = BacktestReportApplication(_Source({source.run.exploratory_backtest_run_id: source}), _Verifier(matched=matched))
    return BacktestDiagnosticsApplication(Facts(), reports), source.run.exploratory_backtest_run_id


def test_diagnostics_preserve_canonical_metric_values_and_are_byte_stable():
    import json
    app, run_id = _application()
    first = app.render_json(run_id)
    assert app.render_json(run_id) == first
    result = json.loads(first)
    assert result['canonical_report']['gross_net_economics'][0]['decimal_value'] == '0.06'
    assert result['summary']['declared_member_cell_count'] == 2
    assert result['alpha_bottleneck'] == result['model_superiority'] == 'NOT_DETERMINED'
    assert len(result['member_roster']) == 2
    assert app.render_markdown(run_id) == app.render_markdown(run_id)


def test_unreconciled_results_or_wrong_scope_cannot_borrow_report_pass():
    from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError
    app, run_id = _application(matched=False)
    with pytest.raises(BacktestReportIntegrityError):
        app.project(run_id)
    app, run_id = _application(_snapshot())
    with pytest.raises(BacktestReportIntegrityError, match='identity'):
        app.project(run_id)


def test_missing_metric_input_roster_fails_closed():
    from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError
    from tests.refoundation.research_qualification.test_backtest_reports import _source
    report = _source()
    app, run_id = _application(replace(_snapshot(), run_id=report.run.exploratory_backtest_run_id,
        specification_sha256=str(report.run.specification_sha256)))
    with pytest.raises(BacktestReportIntegrityError, match='metric input roster'):
        app.project(run_id)


def test_fit_downstream_absence_is_planned_and_is_not_a_capture_failure():
    source = _snapshot()
    fit = replace(source, cells=(replace(source.cells[0], role='FIT_INPUT'),))
    summary = summarize_funnel(fit)
    assert summary['stages']['Signal'] == {'NOT_PLANNED_FIT': 2}
    assert summary['stages']['Risk'] == {'NOT_PLANNED_FIT': 2}


def test_frozen_population_denominator_mismatch_has_narrow_proven_diagnosis():
    from market_regime_alpha.research_qualification.domain.evaluation_formula import FormulaResultState
    from tests.refoundation.research_qualification.test_backtest_reports import _source
    report = _source()
    metric = replace(report.metrics[0], arm_id='arm', result_state=FormulaResultState.NOT_ESTIMABLE,
        decimal_value=None, reason_code='EXPECTED_ROSTER_MISMATCH', estimable_count=0, acceptance_state='NOT_ESTIMABLE')
    app, run_id = _application(report_source=replace(report, metrics=(metric, *report.metrics[1:])))
    result = app.project(run_id)
    assert result['diagnosis_counts'] == {'DECLARED_PRE_ELIGIBILITY_DENOMINATOR_WITH_LEGAL_EXCLUSIONS': 1}
    assert result['canonical_report']['data_coverage'][0]['decimal_value'] is None


def test_complete_but_unestimable_inputs_are_not_called_an_empty_partition():
    from market_regime_alpha.research_qualification.domain.backtest_diagnostics import FunnelMetricInput
    from market_regime_alpha.research_qualification.domain.evaluation_formula import FormulaResultState
    from tests.refoundation.research_qualification.test_backtest_reports import _source
    report = _source()
    metric = replace(report.metrics[0], result_state=FormulaResultState.NOT_ESTIMABLE,
        decimal_value=None, reason_code='INSUFFICIENT_OBSERVATIONS', estimable_count=0, acceptance_state='NOT_ESTIMABLE')
    report = replace(report, metrics=(metric, *report.metrics[1:]))
    snapshot = replace(_snapshot(), run_id=report.run.exploratory_backtest_run_id,
        specification_sha256=str(report.run.specification_sha256),
        metric_inputs=tuple(FunnelMetricInput(str(m.evaluation_metric_id), None, None, 1, 0, 1, 1, (('NOT_ESTIMABLE', 1),)) for m in report.metrics))
    app, run_id = _application(snapshot, report_source=report)
    assert app.project(run_id)['diagnosis_counts'] == {'NO_ESTIMABLE_CANONICAL_METRIC_INPUTS': 1}
