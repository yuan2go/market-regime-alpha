"""Real Generic fixture: complete members, owner report/replay and zero writes."""

import json

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.queries.backtest_diagnostics import PostgresBacktestDiagnosticsSourcePort
from market_regime_alpha.research_qualification.application.backtest_diagnostics import BacktestDiagnosticsApplication
from market_regime_alpha.research_qualification.domain.backtest import freeze_backtest_specification
from tests.refoundation.research_qualification.episode_campaign_fixture import funded_specification
from tests.refoundation.research_qualification.archive_campaign_fixture import _context
from tests.refoundation.research_qualification.test_episode_longitudinal_postgres import _business_snapshot


def test_complete_member_funnel_remains_read_only_across_repeated_reports_and_replay(target_database_url, tmp_path, monkeypatch):
    SchemaManager(target_database_url).bootstrap()
    with bootstrap_application(TargetSettings(target_database_url, (tmp_path / 'artifacts').resolve())) as app:
        spec = funded_specification(app, monkeypatch, multi_episode=True)
        app.backtests.predeclare(spec, _context('funnel-predeclare'))
        assert app.backtest_execution.run(freeze_backtest_specification(spec)).execution_state.value == 'COMPLETED'
        before = _business_snapshot(target_database_url)
        diagnose = BacktestDiagnosticsApplication(PostgresBacktestDiagnosticsSourcePort(app._pool), app.backtest_reports)
        first = diagnose.render_json(spec.exploratory_backtest_run_id)
        assert diagnose.render_json(spec.exploratory_backtest_run_id) == first
        result = json.loads(first)
        # Five cells (one FIT plus four Validation) with all 32 declared symbols; 60 explicitly ineligible
        # Validation members remain visible instead of disappearing from 68 candidates.
        assert result['summary']['declared_member_cell_count'] == 160
        assert result['summary']['candidate_member_cell_count'] == 100
        assert result['summary']['legal_eligibility_exclusion_count'] == 60
        assert result['summary']['unexplained_member_loss_count'] == 0
        assert result['summary']['independent_trading_session_count'] == 5
        assert len(result['member_roster']) == 160
        economics = result['canonical_report']['gross_net_economics']
        assert next(m for m in economics if m['metric_code'] == 'all-net')['decimal_value'] == '-0.00045'
        assert diagnose.render_markdown(spec.exploratory_backtest_run_id) == diagnose.render_markdown(spec.exploratory_backtest_run_id)
        assert app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched
        assert _business_snapshot(target_database_url) == before
