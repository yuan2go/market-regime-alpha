"""Canonical full-parent economics across cash/trades, folds and months."""

from decimal import Decimal as D

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.research_qualification.domain.backtest import freeze_backtest_specification
from tests.refoundation.research_qualification.episode_campaign_fixture import funded_specification
from tests.refoundation.research_qualification.archive_campaign_fixture import _context


def _business_snapshot(database_url):
    import psycopg
    from psycopg import sql

    with psycopg.connect(database_url) as c:
        c.execute("SET TRANSACTION READ ONLY")
        names = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='mra' ORDER BY tablename")]
        return {name: c.execute(sql.SQL("""SELECT count(*),
            encode(sha256(convert_to(coalesce(string_agg(to_jsonb(fact)::text,'' ORDER BY to_jsonb(fact)::text),''),'UTF8')),'hex')
            FROM mra.{} fact""").format(sql.Identifier(name))).fetchone() for name in names}


def test_complete_parent_cash_and_trades_then_fold_and_month_projections(target_database_url, tmp_path, monkeypatch):
    import json

    SchemaManager(target_database_url).bootstrap()
    with bootstrap_application(TargetSettings(target_database_url, (tmp_path / "longitudinal-artifacts").resolve())) as app:
        spec = funded_specification(app, monkeypatch, multi_episode=True)
        app.backtests.predeclare(spec, _context("longitudinal-predeclare"))
        frozen = freeze_backtest_specification(spec)
        assert app.backtest_execution.run(frozen).execution_state.value == "COMPLETED"
        with app._pool.connection(read_only=True) as c:
            metrics = c.execute(
                """SELECT e.evaluation_run_id,p.metric_code,m.decimal_value,m.estimable_count
                FROM mra.backtest_evaluation_execution x JOIN mra.evaluation_run e USING(evaluation_run_id)
                JOIN mra.evaluation_metric m USING(evaluation_run_id)
                JOIN mra.evaluation_protocol_metric p USING(evaluation_protocol_metric_id)
                JOIN mra.evaluation_metric_formula f USING(evaluation_protocol_metric_id)
                WHERE x.exploratory_backtest_run_id=%s AND f.formula_version=2 ORDER BY p.ordinal""",
                (spec.exploratory_backtest_run_id,),
            ).fetchall()
        # Hand ledger: each episode has 1,000 capital. Two episodes stay in cash.
        # Five .16 allocations trade: +10% yields 880-800-.95=79.05;
        # -10% yields 720-800-.85=-80.85. Capital is shared by securities.
        expected = {
            "all-net": (D("-.00045"), 4),
            "all-turnover": (D(".8"), 4),
            "fold-a-net": (D(".039525"), 2),
            "fold-b-net": (D("-.040425"), 2),
            "january-net": (D("-.0006"), 3),
            "february-net": (D("0"), 1),
        }
        assert {code: (value, count) for _, code, value, count in metrics} == expected
        assert len({row[0] for row in metrics}) == 1
        with app._pool.connection(read_only=True) as c:
            # All selectors retain the same 68-member parent, including cash
            # episodes with two eligible instruments and traded episodes with 32.
            rosters = c.execute("""SELECT evaluation_protocol_metric_id,count(*),
                array_agg(ROW(portfolio_line_id,turnover,effective_weight,gross_return,net_return,cost_roster_sha256)::text
                          ORDER BY portfolio_line_id)
                FROM mra.evaluation_portfolio_source WHERE evaluation_run_id=%s
                GROUP BY evaluation_protocol_metric_id""", (metrics[0][0],)).fetchall()
            assert len(rosters) == 6 and {row[1] for row in rosters} == {68}
            assert all(row[2] == rosters[0][2] for row in rosters)
            proposals = c.execute("""SELECT session.session_date,source.risk_status,count(*),
                count(*) FILTER (WHERE source.proposed_weight>0),sum(source.proposed_weight),
                sum(source.turnover),sum(source.net_return)
                FROM mra.evaluation_portfolio_source source
                JOIN mra.evaluation_protocol_metric metric USING(evaluation_protocol_metric_id)
                JOIN mra.exploratory_retrospective_decision_run decision ON decision.decision_run_id=source.decision_run_id
                JOIN mra.exploratory_backtest_fold_session session USING(exploratory_backtest_fold_session_id)
                WHERE source.evaluation_run_id=%s AND metric.metric_code='all-net'
                GROUP BY session.session_date,source.risk_status ORDER BY session.session_date""", (metrics[0][0],)).fetchall()
            assert [(str(day), risk, count, positive, weight, turnover, net) for day, risk, count, positive, weight, turnover, net in proposals] == [
                ("2026-01-28", "REJECTED", 2, 2, D(".5"), D(0), D(0)),
                ("2026-01-29", "AUTHORIZED", 32, 5, D(".8"), D("1.68"), D(".07905")),
                ("2026-01-30", "AUTHORIZED", 32, 5, D(".8"), D("1.52"), D("-.08085")),
                ("2026-02-03", "REJECTED", 2, 2, D(".5"), D(0), D(0)),
            ]
            metric_ids = dict(c.execute("""SELECT p.metric_code,m.evaluation_metric_id
                FROM mra.evaluation_metric m JOIN mra.evaluation_protocol_metric p USING(evaluation_protocol_metric_id)
                WHERE m.evaluation_run_id=%s""", (metrics[0][0],)).fetchall())
        assert app.research_evaluation_verifier.verify_evaluation_run(metrics[0][0]).matched
        report = app.backtest_reports.publish(spec.exploratory_backtest_run_id, artifacts=app.artifacts,
            bindings=app.backtests, context=_context("longitudinal-report"))
        rendered = app.backtest_reports.render_json(spec.exploratory_backtest_run_id)
        markdown = app.backtest_reports.render_markdown(spec.exploratory_backtest_run_id)
        fold_a, fold_b = (str(f.exploratory_backtest_fold_id) for f in spec.folds[1:])
        scopes = {
            "all-net": ("AGGREGATE", None, None),
            "all-turnover": ("AGGREGATE", None, None),
            "fold-a-net": ("FOLD", fold_a, fold_a),
            "fold-b-net": ("FOLD", fold_b, fold_b),
            "january-net": ("TIME_MONTH", None, "2026-01"),
            "february-net": ("TIME_MONTH", None, "2026-02"),
        }
        projected = json.loads(rendered)["gross_net_economics"]
        assert len(projected) == len(expected)
        for item in projected:
            code = item["metric_code"]
            assert (D(item["decimal_value"]), item["estimable_count"]) == expected[code]
            assert (item["scope_kind"], item["fold_id"], item["slice_key"]) == scopes[code]
            assert item["evaluation_metric_id"] == str(metric_ids[code])
            assert item["evaluation_run_id"] == str(metrics[0][0])
            assert item["formula_version"] == 2 and item["result_state"] == "ESTIMABLE"
        before_resume = _business_snapshot(target_database_url)
        assert app.backtest_execution.resume(frozen).execution_state.value == "COMPLETED"
        assert app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched
        assert app.backtest_reports.render_json(spec.exploratory_backtest_run_id) == rendered
        assert app.backtest_reports.render_markdown(spec.exploratory_backtest_run_id) == markdown
        assert app.backtest_reports.publish(spec.exploratory_backtest_run_id, artifacts=app.artifacts,
            bindings=app.backtests, context=_context("longitudinal-report")) == report
        assert _business_snapshot(target_database_url) == before_resume
        # The same multi-episode protocol also exercises concurrent completion,
        # lost commit acknowledgement, partial rollback and live stale fencing.
        from tests.refoundation.research_qualification.test_episode_economics_postgres import _fault_qualification
        _fault_qualification(app, spec, metrics[0][0], target_database_url)


def test_unselected_parent_member_missing_is_an_integrity_mismatch(target_database_url, tmp_path, monkeypatch):
    import json
    from uuid import uuid4
    import psycopg
    from psycopg import sql
    import pytest
    from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError

    # Separate canonical facts and a February-only metric. An ALL metric must
    # not mask an erroneous early slice that ignores a broken January member.
    SchemaManager(target_database_url).bootstrap()
    with bootstrap_application(TargetSettings(target_database_url, (tmp_path / "negative-artifacts").resolve())) as app:
        spec = funded_specification(app, monkeypatch, multi_episode=True, february_only=True)
        app.backtests.predeclare(spec, _context("negative-predeclare"))
        frozen = freeze_backtest_specification(spec)
        assert app.backtest_execution.run(frozen).execution_state.value == "COMPLETED"
        with psycopg.connect(target_database_url) as c:
            evaluation_id = c.execute("""SELECT m.evaluation_run_id FROM mra.evaluation_metric m
                JOIN mra.evaluation_protocol_metric p USING(evaluation_protocol_metric_id)
                WHERE p.metric_code='february-net'""").fetchone()[0]
            line, observation_id, revision_id, commitment_id = c.execute("""SELECT to_jsonb(line),input.evaluation_observation_id,
                input.market_target_outcome_revision_id,revision.commitment_id
                FROM mra.evaluation_portfolio_source source
                JOIN mra.portfolio_line line USING(portfolio_line_id)
                JOIN mra.evaluation_metric_observation input ON input.evaluation_metric_observation_id=source.evaluation_metric_observation_id
                JOIN mra.market_target_outcome_revision revision ON revision.market_target_outcome_revision_id=input.market_target_outcome_revision_id
                JOIN mra.exploratory_retrospective_decision_run decision ON decision.decision_run_id=source.decision_run_id
                JOIN mra.exploratory_backtest_fold_session session USING(exploratory_backtest_fold_session_id)
                WHERE source.evaluation_run_id=%s AND session.session_date='2026-01-29' AND source.proposed_weight>0
                ORDER BY line.portfolio_line_id LIMIT 1""", (evaluation_id,)).fetchone()
            price_id = c.execute("""SELECT market_target_outcome_observation_id
                FROM mra.market_target_outcome_observation WHERE market_target_outcome_revision_id=%s
                ORDER BY event_end OFFSET 1 LIMIT 1""", (revision_id,)).fetchone()[0]

        def snapshot():
            return _business_snapshot(target_database_url)

        def reject_without_writes(label):
            before = snapshot()
            verification = app.research_evaluation_verifier.verify_evaluation_run(evaluation_id)
            assert not verification.matched and verification.mismatch_count > 0, label
            assert not app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched, label
            assert app.backtest_execution.inspect(frozen).execution_state.value == "INTEGRITY_ERROR", label
            with pytest.raises(BacktestReportIntegrityError):
                app.backtest_reports.publish(spec.exploratory_backtest_run_id, artifacts=app.artifacts,
                    bindings=app.backtests, context=_context("negative-report-" + label))
            assert snapshot() == before

        baseline = snapshot()
        cases = (
            ("portfolio_line", "portfolio_line_id", line["portfolio_line_id"]),
            ("decision_run", "decision_run_id", line["decision_run_id"]),
            ("decision_target_commitment", "commitment_id", commitment_id),
            ("evaluation_observation", "evaluation_observation_id", observation_id),
        )
        for table, key, identity in cases:
            with psycopg.connect(target_database_url) as c:
                saved = c.execute(sql.SQL("SELECT to_jsonb(fact)::text FROM mra.{} fact WHERE {}=%s").format(
                    sql.Identifier(table), sql.Identifier(key)), (identity,)).fetchone()[0]
                c.execute("SET LOCAL session_replication_role='replica'")
                c.execute(sql.SQL("DELETE FROM mra.{} WHERE {}=%s").format(sql.Identifier(table), sql.Identifier(key)), (identity,))
            try:
                reject_without_writes(table)
            finally:
                with psycopg.connect(target_database_url) as c:
                    c.execute("SET LOCAL session_replication_role='replica'")
                    c.execute(sql.SQL("INSERT INTO mra.{} SELECT * FROM jsonb_populate_record(NULL::mra.{},%s::jsonb)").format(
                        sql.Identifier(table), sql.Identifier(table)), (saved,))
            assert snapshot() == baseline
            assert app.research_evaluation_verifier.verify_evaluation_run(evaluation_id).matched

        # An unselected January price still crosses the canonical Outcome owner.
        with psycopg.connect(target_database_url) as c:
            price = c.execute("SELECT close_value FROM mra.market_target_outcome_observation WHERE market_target_outcome_observation_id=%s", (price_id,)).fetchone()[0]
            c.execute("SET LOCAL session_replication_role='replica'")
            c.execute("UPDATE mra.market_target_outcome_observation SET close_value=close_value+.001 WHERE market_target_outcome_observation_id=%s", (price_id,))
        try:
            reject_without_writes("unselected-price")
        finally:
            with psycopg.connect(target_database_url) as c:
                c.execute("SET LOCAL session_replication_role='replica'")
                c.execute("UPDATE mra.market_target_outcome_observation SET close_value=%s WHERE market_target_outcome_observation_id=%s", (price, price_id))
        assert snapshot() == baseline

        # Duplicate capital lines cannot enter Authority even with append guards
        # bypassed: the exact proposal/ordinal constraint rejects them atomically.
        duplicate = dict(line, portfolio_line_id=str(uuid4()))
        with pytest.raises(psycopg.errors.UniqueViolation):
            with psycopg.connect(target_database_url) as c:
                c.execute("SET LOCAL session_replication_role='replica'")
                c.execute("INSERT INTO mra.portfolio_line SELECT * FROM jsonb_populate_record(NULL::mra.portfolio_line,%s::jsonb)", (json.dumps(duplicate),))
        assert snapshot() == baseline
        assert app.research_evaluation_verifier.verify_evaluation_run(evaluation_id).matched
