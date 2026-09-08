from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.research_qualification.domain.backtest import freeze_backtest_specification
from tests.contracts.research_qualification.episode_campaign_fixture import funded_specification
from tests.contracts.research_qualification.archive_campaign_fixture import _context


def test_generic_episode_canonical_completion_report_and_replay(target_database_url, tmp_path, monkeypatch):
    SchemaManager(target_database_url).bootstrap()
    with bootstrap_application(TargetSettings(target_database_url, (tmp_path / "episode-artifacts").resolve())) as app:
        spec = funded_specification(app, monkeypatch)
        app.backtests.predeclare(spec, _context("economic-predeclare"))
        frozen = freeze_backtest_specification(spec)
        result = app.backtest_execution.run(frozen)
        assert result.execution_state.value == "COMPLETED"
        replay = app.backtest_replay.verify(spec.exploratory_backtest_run_id)
        assert replay.matched and not replay.mismatch_codes
        with app._pool.connection(read_only=True) as c:
            rows = c.execute(
                """SELECT e.evaluation_run_id,m.decimal_value,m.estimable_count,m.reason_code
                FROM mra.backtest_evaluation_execution x JOIN mra.evaluation_run e USING(evaluation_run_id)
                JOIN mra.evaluation_metric m USING(evaluation_run_id)
                JOIN mra.evaluation_metric_formula f USING(evaluation_protocol_metric_id)
                WHERE x.exploratory_backtest_run_id=%s AND f.formula_version=2""",
                (spec.exploratory_backtest_run_id,),
            ).fetchall()
        assert len(rows) == 2
        assert all(row[1] is not None and row[2] == 1 and row[3] == "INDEPENDENT_EPISODES_V2" for row in rows)
        assert app.research_evaluation_verifier.verify_evaluation_run(rows[0][0]).matched
        before = app.backtest_reports.render_json(spec.exploratory_backtest_run_id)
        markdown = app.backtest_reports.render_markdown(spec.exploratory_backtest_run_id)
        assert app.backtest_execution.resume(frozen).execution_state.value == "COMPLETED"
        assert app.backtest_reports.render_json(spec.exploratory_backtest_run_id) == before
        assert app.backtest_reports.render_markdown(spec.exploratory_backtest_run_id) == markdown
        _root_corruption_qualification(app, spec, rows[0][0], target_database_url)
        _fault_qualification(app, spec, rows[0][0], target_database_url)
        _corruption_qualification(app, spec, rows[0][0], target_database_url)
        _changed_input_qualification(app, spec, rows[0][0], target_database_url)


def _root_corruption_qualification(app, spec, source_id, database_url):
    from uuid import uuid4
    import psycopg
    from psycopg import sql
    import pytest
    from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError

    columns = ("evaluation_metric_id", "evaluation_run_id", "evaluation_protocol_metric_id", "evaluation_protocol_id",
               "metric_state", "decimal_value", "boolean_value", "estimable_count", "acceptance_state", "reason_code", "content_sha256")
    with psycopg.connect(database_url) as c:
        saved = c.execute(
            sql.SQL("SELECT {} FROM mra.evaluation_metric WHERE evaluation_run_id=%s ORDER BY evaluation_metric_id LIMIT 1").format(
                sql.SQL(",").join(map(sql.Identifier, columns))
            ), (source_id,),
        ).fetchone()
        legacy = c.execute("""SELECT metric.evaluation_protocol_metric_id,metric.evaluation_protocol_id
            FROM mra.evaluation_protocol_metric metric JOIN mra.evaluation_metric_formula formula USING(evaluation_protocol_metric_id)
            WHERE formula.formula_version=1 LIMIT 1""").fetchone()
    original = dict(zip(columns, saved, strict=True))
    variants = (
        {"estimable_count": original["estimable_count"] + 1},
        {"boolean_value": True},
        {"acceptance_state": "REJECTED"},
        {"metric_state": "NOT_ESTIMABLE", "decimal_value": None, "boolean_value": None, "acceptance_state": "NOT_ESTIMABLE"},
        {"decimal_value": original["decimal_value"] + 1},
        {"reason_code": "DIFFERENT_REASON"},
        {"content_sha256": "f" * 64},
        {"evaluation_protocol_id": legacy[1]},
        {"evaluation_protocol_metric_id": legacy[0], "evaluation_protocol_id": legacy[1]},
        {"evaluation_metric_id": uuid4()},
        {"evaluation_run_id": uuid4()},
    )

    def snapshot():
        # Include result/input/source/Runtime/receipt bytes, not only row counts.
        names = ("evaluation_run", "evaluation_metric", "evaluation_observation", "evaluation_metric_observation",
                 "evaluation_portfolio_source", "evaluation_portfolio_cost_source", "command_receipt", "audit_event",
                 "runtime_run", "runtime_step", "runtime_attempt")
        with psycopg.connect(database_url) as c:
            c.execute("SET TRANSACTION READ ONLY")
            return {name: c.execute(sql.SQL("SELECT to_jsonb(fact)::text FROM mra.{} fact ORDER BY to_jsonb(fact)::text").format(sql.Identifier(name))).fetchall() for name in names}

    baseline = snapshot()
    for index, changes in enumerate(variants):
        with psycopg.connect(database_url) as c:
            c.execute("SET LOCAL session_replication_role='replica'")
            c.execute(sql.SQL("UPDATE mra.evaluation_metric SET {} WHERE evaluation_metric_id=%s").format(
                sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(name)) for name in changes)
            ), (*changes.values(), original["evaluation_metric_id"]))
        try:
            before = snapshot()
            verification = app.research_evaluation_verifier.verify_evaluation_run(source_id)
            assert not verification.matched and verification.mismatch_count > 0, changes
            assert not app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched, changes
            assert app.backtest_execution.inspect(freeze_backtest_specification(spec)).execution_state.value == "INTEGRITY_ERROR"
            with pytest.raises(BacktestReportIntegrityError):
                app.backtest_reports.publish(spec.exploratory_backtest_run_id, artifacts=app.artifacts,
                    bindings=app.backtests, context=_context("corrupt-root-report-" + str(index)))
            assert snapshot() == before
        finally:
            with psycopg.connect(database_url) as c:
                c.execute("SET LOCAL session_replication_role='replica'")
                c.execute(sql.SQL("UPDATE mra.evaluation_metric SET {} WHERE evaluation_metric_id=%s").format(
                    sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(name)) for name in columns)
                ), (*saved, changes.get("evaluation_metric_id", original["evaluation_metric_id"])))
        assert snapshot() == baseline
        assert app.research_evaluation_verifier.verify_evaluation_run(source_id).matched


def _new_acquired(app, spec, source_id, suffix):
    from uuid import uuid4
    from market_regime_alpha.research_qualification.domain.evaluation import EvaluationRunPlan

    with app._pool.connection(read_only=True) as c:
        source = c.execute(
            "SELECT experiment_run_id,evaluation_protocol_id,requested_knowledge_cutoff FROM mra.evaluation_run WHERE evaluation_run_id=%s",
            (source_id,),
        ).fetchone()
    plan = EvaluationRunPlan(
        uuid4(), source[0], source[1], source[2], "episode-" + suffix, spec.code_artifact, spec.config_artifact, "a" * 64
    )
    app.research_evaluations.open_run(plan, _context("episode-open-" + suffix))
    app.research_evaluations.acquire_outcome_inputs(plan.evaluation_run_id, _context("episode-acquire-" + suffix))
    return plan.evaluation_run_id


def _fault_qualification(app, spec, source_id, database_url):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    import psycopg
    import pytest
    from market_regime_alpha.infrastructure.postgres.evaluation_uow import PostgresEvaluationUnitOfWorkProvider
    from market_regime_alpha.research_qualification.application.evaluations import EvaluationCommands
    from market_regime_alpha.research_qualification.errors import ResearchRetryableTransactionError
    from market_regime_alpha.runtime.errors import StaleFenceError
    from market_regime_alpha.shared.time import DecisionTime
    from tests.contracts.outcome.test_outcome_postgres import _outcome_claim
    from tests.contracts.research_qualification.test_evaluation_closure_postgres import _CommitAckLostOnce

    concurrent = _new_acquired(app, spec, source_id, "concurrent")
    context = _context("episode-concurrent-complete")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(app.research_evaluations.complete, concurrent, context) for _ in range(2)]
        results = [f.result(timeout=60) for f in futures]
    assert sorted(r.replayed for r in results) == [False, True]
    assert len({r.receipt_id for r in results}) == 1
    assert app.research_evaluation_verifier.verify_evaluation_run(concurrent).matched

    unknown = _new_acquired(app, spec, source_id, "unknown-commit")
    lost_ack = _CommitAckLostOnce(PostgresEvaluationUnitOfWorkProvider(app._pool, id_factory=uuid4))
    commands = EvaluationCommands(lost_ack, id_factory=uuid4, outcome_prices=app.outcome_queries)
    context = _context("episode-unknown-complete")
    recovered = commands.complete(unknown, context)
    assert lost_ack.lost and recovered.replayed
    assert commands.complete(unknown, context).replayed
    assert app.research_evaluation_verifier.verify_evaluation_run(unknown).matched

    failed = _new_acquired(app, spec, source_id, "mid-child-rollback")
    with psycopg.connect(database_url) as c:
        c.execute("""CREATE FUNCTION mra.episode_inject_failure() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'episode qualification child failure' USING ERRCODE='40001'; END; $$;
            CREATE TRIGGER episode_inject_failure BEFORE INSERT ON mra.evaluation_portfolio_source
            FOR EACH ROW EXECUTE FUNCTION mra.episode_inject_failure();""")
    context = _context("episode-rollback-complete")
    with pytest.raises(ResearchRetryableTransactionError):
        app.research_evaluations.complete(failed, context)
    with psycopg.connect(database_url) as c:
        counts = c.execute(
            """SELECT
            (SELECT count(*) FROM mra.evaluation_metric WHERE evaluation_run_id=%s),
            (SELECT count(*) FROM mra.evaluation_metric_observation WHERE evaluation_run_id=%s),
            (SELECT count(*) FROM mra.command_receipt WHERE idempotency_key=%s)""",
            (failed, failed, context.idempotency_key),
        ).fetchone()
        c.execute("DROP TRIGGER episode_inject_failure ON mra.evaluation_portfolio_source")
        c.execute("DROP FUNCTION mra.episode_inject_failure()")
    assert counts == (0, 0, 0)
    assert not app.research_evaluations.complete(failed, context).replayed
    assert app.research_evaluation_verifier.verify_evaluation_run(failed).matched

    fenced = _new_acquired(app, spec, source_id, "stale-fence")
    claim = _outcome_claim(SimpleNamespace(pool=app._pool, artifacts=app.artifacts, decision_time=DecisionTime(datetime.now(UTC))))
    context = _context("episode-stale-complete")
    counts_sql = """SELECT (SELECT count(*) FROM mra.evaluation_metric),
                           (SELECT count(*) FROM mra.command_receipt),
                           (SELECT count(*) FROM mra.audit_event)"""
    with psycopg.connect(database_url) as c:
        before = c.execute(counts_sql).fetchone()
    with pytest.raises(StaleFenceError):
        app.research_evaluations.complete(fenced, context, runtime_claim=replace(claim, fence_token=claim.fence_token + 1))
    with psycopg.connect(database_url) as c:
        assert c.execute(counts_sql).fetchone() == before


def _corruption_qualification(app, spec, source_id, database_url):
    import psycopg
    import pytest
    from psycopg import sql
    from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError

    cases = (
        ("evaluation_portfolio_source", "turnover", "turnover + 0.01"),
        ("evaluation_metric_observation", "input_state", "'EXCLUDED'"),
        ("evaluation_portfolio_cost_source", "amount_bps", "amount_bps + 1"),
    )

    def operational_counts():
        with psycopg.connect(database_url) as c:
            return c.execute("""SELECT (SELECT count(*) FROM mra.command_receipt),
                (SELECT count(*) FROM mra.audit_event),(SELECT count(*) FROM mra.runtime_attempt),
                (SELECT count(*) FROM mra.evaluation_metric)""").fetchone()

    before = operational_counts()
    for table, column, corrupt_expression in cases:
        with psycopg.connect(database_url) as c:
            keys = c.execute(
                """SELECT input.evaluation_metric_observation_id FROM mra.evaluation_metric_observation input
                JOIN mra.evaluation_portfolio_source source USING(evaluation_metric_observation_id)
                WHERE input.evaluation_run_id=%s ORDER BY input.evaluation_metric_observation_id LIMIT 1""",
                (source_id,),
            ).fetchone()
            # All costs for this input are restored individually by exact IDs.
            saved = c.execute(
                sql.SQL("SELECT {}{} FROM mra.{} WHERE evaluation_metric_observation_id=%s").format(
                    sql.Identifier(column),
                    sql.SQL(", exploratory_backtest_cost_assumption_id") if table.endswith("cost_source") else sql.SQL(""),
                    sql.Identifier(table),
                ),
                keys,
            ).fetchall()
            c.execute("SET LOCAL session_replication_role='replica'")
            c.execute(
                sql.SQL("UPDATE mra.{} SET {}={} WHERE evaluation_metric_observation_id=%s").format(
                    sql.Identifier(table), sql.Identifier(column), sql.SQL(corrupt_expression)
                ),
                keys,
            )
        try:
            verification = app.research_evaluation_verifier.verify_evaluation_run(source_id)
            assert not verification.matched and verification.mismatch_count > 0
            assert not app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched
            with pytest.raises(BacktestReportIntegrityError):
                app.backtest_reports.render_json(spec.exploratory_backtest_run_id)
            assert app.backtest_execution.inspect(freeze_backtest_specification(spec)).execution_state.value == "INTEGRITY_ERROR"
        finally:
            with psycopg.connect(database_url) as c:
                c.execute("SET LOCAL session_replication_role='replica'")
                for saved_row in saved:
                    extra = sql.SQL(" AND exploratory_backtest_cost_assumption_id=%s") if table.endswith("cost_source") else sql.SQL("")
                    c.execute(
                        sql.SQL("UPDATE mra.{} SET {}=%s WHERE evaluation_metric_observation_id=%s").format(
                            sql.Identifier(table), sql.Identifier(column)
                        )
                        + extra,
                        (saved_row[0], keys[0], *saved_row[1:]),
                    )
        assert app.research_evaluation_verifier.verify_evaluation_run(source_id).matched
    assert operational_counts() == before


def _changed_input_qualification(app, spec, source_id, database_url):
    from uuid import uuid4
    import psycopg
    import pytest
    from market_regime_alpha.infrastructure.postgres.evaluation_uow import PostgresEvaluationUnitOfWorkProvider
    from market_regime_alpha.research_qualification.application.evaluations import EvaluationCommands
    from market_regime_alpha.research_qualification.errors import EvaluationReconciliationError

    acquired = _new_acquired(app, spec, source_id, "changed-price-after-read")
    saved = []

    class ChangedOwner:
        def episode_prices(self, identities, entry, exit):
            facts = app.outcome_queries.episode_prices(identities, entry, exit)
            with psycopg.connect(database_url) as c:
                saved.append(
                    c.execute(
                        "SELECT market_target_outcome_observation_id,close_value FROM mra.market_target_outcome_observation WHERE market_target_outcome_observation_id=%s",
                        (facts[0].entry_observation_id,),
                    ).fetchone()
                )
                c.execute("SET LOCAL session_replication_role='replica'")
                c.execute(
                    "UPDATE mra.market_target_outcome_observation SET close_value=close_value+0.001 WHERE market_target_outcome_observation_id=%s",
                    (saved[0][0],),
                )
            return facts

    commands = EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(app._pool, id_factory=uuid4), id_factory=uuid4, outcome_prices=ChangedOwner()
    )
    context = _context("episode-changed-price-complete")
    try:
        with pytest.raises(EvaluationReconciliationError, match="Outcome price Authority changed before commit"):
            commands.complete(acquired, context)
        with psycopg.connect(database_url) as c:
            assert c.execute("SELECT count(*) FROM mra.evaluation_metric WHERE evaluation_run_id=%s", (acquired,)).fetchone() == (0,)
    finally:
        with psycopg.connect(database_url) as c:
            c.execute("SET LOCAL session_replication_role='replica'")
            for identity, price in saved:
                c.execute(
                    "UPDATE mra.market_target_outcome_observation SET close_value=%s WHERE market_target_outcome_observation_id=%s",
                    (price, identity),
                )
    assert app.research_evaluation_verifier.verify_evaluation_run(source_id).matched
