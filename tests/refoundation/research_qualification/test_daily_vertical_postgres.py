from market_regime_alpha.bootstrap import TargetSettings, bootstrap_database, bootstrap_application
from tests.refoundation.research_qualification.daily_campaign_fixture import daily_baseline
from tests.refoundation.research_qualification.archive_campaign_fixture import _context


def test_generic_daily_target_fit_model_validation_and_replay(target_database_url, tmp_path):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        spec, catalog = daily_baseline(app)
        app.backtests.predeclare(spec, _context("daily-predeclare"))
        frozen = app.backtest_specifications.load(spec.exploratory_backtest_run_id)
        from market_regime_alpha.infrastructure.postgres.prospective_operation_session import prospective_operation_session, backtest_research_admission
        identity = app.evidence.inventory()["database"]
        with prospective_operation_session(target_database_url, database_name=identity["name"], database_oid=identity["oid"], cluster_identity=identity["cluster_identity"], series_code="daily-fixture"):
            with backtest_research_admission(backtest_run_id=spec.exploratory_backtest_run_id, specification_sha256=str(frozen.specification_sha256)):
                result = app.backtest_execution.run(frozen)
        assert result.execution_state.value == "COMPLETED", result
        assert app.backtest_replay.verify(spec.exploratory_backtest_run_id).matched
        report = app.backtest_reports.render_json(spec.exploratory_backtest_run_id)
        assert report == app.backtest_reports.render_json(spec.exploratory_backtest_run_id)
        with app._pool.connection(read_only=True) as c:
            assert c.execute("SELECT count(*) FROM mra.model_version WHERE model_id=%s", (catalog["model"].model_id,)).fetchone() == (1,)
            partition = c.execute("SELECT research_partition_id FROM mra.research_partition ORDER BY research_partition_id LIMIT 1").fetchone()[0]
            roster = tuple(row[0] for row in c.execute("SELECT commitment_id FROM mra.research_partition_member WHERE research_partition_id=%s ORDER BY commitment_id", (partition,)).fetchall())
        import pytest
        from market_regime_alpha.runtime.errors import ArtifactIntegrityError
        app.daily_prediction_reads.require_partition_roster(partition, roster)
        with pytest.raises(ArtifactIntegrityError, match="exact published commitment roster"):
            app.daily_prediction_reads.require_partition_roster(partition, roster[:-1])


def test_completed_model_is_consumed_without_backtest_and_publication_is_replayable(target_database_url, tmp_path):
    from dataclasses import replace
    from datetime import timedelta
    from decimal import Decimal as D
    from uuid import uuid4
    from zoneinfo import ZoneInfo
    from market_regime_alpha.market.domain import (
        NormalizationBatch,
        BarTimeframe,
        SecurityStatusFactRevision,
        SecurityStatus,
        EvidenceScope,
    )
    from market_regime_alpha.market.ports import CaptureRequest
    from market_regime_alpha.shared.financial import Money
    from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
    from market_regime_alpha.research_qualification.domain.experimental_model_use import ExperimentalModelUsePlan
    from market_regime_alpha.decision_support.domain.strategy import StrategyPlan
    from tests.refoundation.research_qualification.archive_campaign_fixture import _session, _bar
    from tests.refoundation.research_qualification import test_research_postgres as R

    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        spec, c = daily_baseline(app)
        app.backtests.predeclare(spec, _context("daily-predeclare"))
        frozen = app.backtest_specifications.load(spec.exploratory_backtest_run_id)
        assert app.backtest_execution.run(frozen).execution_state.value == "COMPLETED"
        with app._pool.connection(read_only=True) as connection:
            version = connection.execute(
                "SELECT model_version_id FROM mra.model_version WHERE model_id=%s", (c["model"].model_id,)
            ).fetchone()[0]
            now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        # Synthetic explicit calendar: a closed input session and a future Target.
        # No future price is inserted; these rows cannot be used as real research evidence.
        today = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
        capture = app.market.capture(
            CaptureRequest(c["product"].provider_product_id, "daily-input-fixture", "fixture://post-close", "d" * 64),
            R._BytesProvider(),
            _context("post-close-capture"),
        )
        cid = capture.capture.capture_id
        input_session = _session(today - timedelta(days=1), cid, "XSHG")
        target_session = _session(today + timedelta(days=1), cid, "XSHG")
        bars = []
        statuses = []
        for i, instrument in enumerate(c["instruments"]):
            bar = _bar(c["product"].provider_product_id, cid, instrument, input_session, "REFERENCE", i)
            bars.append(
                replace(
                    bar,
                    bar_revision_id=uuid4(),
                    timeframe=BarTimeframe.DAILY,
                    event_start=input_session.open_at,
                    event_end=input_session.close_at,
                    open=Money(D(10), "CNY"),
                    close=Money(D(10) + D(i + 1) / 1000, "CNY"),
                    high=Money(D(11), "CNY"),
                    low=Money(D(9), "CNY"),
                )
            )
            statuses.append(
                SecurityStatusFactRevision(
                    uuid4(),
                    c["product"].provider_product_id,
                    cid,
                    instrument,
                    input_session.session_id,
                    EvidenceScope.DECISION_SESSION,
                    SecurityStatus.ACTIVE,
                    input_session.open_at,
                    input_session.close_at,
                    1,
                    None,
                )
            )
        batch = NormalizationBatch(
            cid,
            c["product"].provider_product_id,
            trading_sessions=(input_session, target_session),
            bars=tuple(bars),
            security_status_facts=tuple(statuses),
        )
        app.market.normalize(cid, R._Normalizer(lambda _: batch), _context("post-close-normalize"))
        old = c["strategy"]
        sid = uuid4()
        model_strategy = replace(
            old,
            strategy=StrategyPlan(uuid4(), "daily_model_consumer", "Experimental model predictions only"),
            strategy_version_id=sid,
            context_requirements=tuple(
                replace(r, strategy_context_requirement_id=uuid4(), strategy_version_id=sid) for r in old.context_requirements
            ),
            signal_rule=replace(old.signal_rule, strategy_signal_rule_id=uuid4(), strategy_version_id=sid),
            forecast_rules=tuple(replace(r, strategy_forecast_rule_id=uuid4(), strategy_version_id=sid) for r in old.forecast_rules),
        )
        app.decision_strategies.register(model_strategy, _context("daily-model-consumer"))
        use = ExperimentalModelUsePlan(
            uuid4(),
            version,
            c["target"].metrics[0].target_metric_definition_id,
            str(c["model"].feature_roster_sha256),
            c["config"],
            now,
            now + timedelta(days=30),
            old.strategy_version_id,
        )
        app.research_models.register_experimental_use(use, _context("daily-use"))
        instant = app.daily_prediction_reads.now()
        plan = DailyPredictionPlan(
            uuid4(),
            use.experimental_model_use_id,
            version,
            c["product"].provider_product_id,
            c["universe"].universe_id,
            c["code"].__class__(c["scope"].artifact_id, c["scope"].content_sha256, c["scope"].size_bytes),
            "INDEX_MEMBERSHIP",
            "CSI300",
            tuple(sorted((i.value for i in c["instruments"]), key=str)),
            c["eligibility"].eligibility_policy_id,
            c["feature"].feature_definition_id,
            c["candidate"].candidate_policy_id,
            c["context"].context_policy_id,
            sid,
            c["target"].target_definition_id,
            input_session.session_id.value,
            target_session.session_id.value,
            instant,
            instant,
            "0" * 64,
            c["code"],
            c["config"],
            "f" * 40,
            old.strategy_version_id,
        )
        ready = app.daily_prediction_reads.observe(plan)
        assert ready.state == "READY"
        plan = replace(plan, input_content_sha256=ready.content_sha256)
        from market_regime_alpha.interfaces.daily_service import current_daily_plan

        plan = current_daily_plan(app, plan)
        app.daily_prediction_reads.validate_configuration(plan)
        trace = app.daily_research.execute(plan, worker_id="daily-fixture")
        assert trace.run_state == "SUCCEEDED", trace
        report = app.daily_prediction_reads.forecast_projection(plan)
        assert report["denominators"] == dict(
            sampled=32, eligible=32, feature_ready=32, model_prediction=32, baseline_prediction=32, common_prediction=32
        )
        assert len(report["predictions"]) == 32
        assert app.daily_research.settle_and_evaluate(plan, worker_id="daily-fixture")["state"] == "PENDING"
        assert app.daily_research.execute(plan, worker_id="daily-fixture").run_state == "SUCCEEDED"
        assert app.daily_research.replay(plan)["matched"]
        from market_regime_alpha.interfaces.daily_service import daily_tick
        from market_regime_alpha.infrastructure.postgres.prospective_operation_session import prospective_operation_session

        class NoProviderEffect:
            def capture(self, _):
                raise AssertionError("ready inputs and future targets require no Provider call")

        identity = app.evidence.inventory()["database"]
        with prospective_operation_session(
            target_database_url,
            database_name=identity["name"],
            database_oid=identity["oid"],
            cluster_identity=identity["cluster_identity"],
            series_code="daily-fixture",
        ) as session:

            def before():
                session.require_supervisor_lock("daily-fixture")
                assert not session.has_conflicting_attempts("daily-fixture")

            tick = daily_tick(app, plan, NoProviderEffect(), worker_id="daily-fixture", maximum_steps=2, before_action=before)
        assert tick["state"] == "PREDICTION_PROGRESS"
        assert tick["result"].run_state == "SUCCEEDED"
        assert tick["pending"][0]["state"] == "PENDING"
        app.research_models.revoke_experimental_use(use.experimental_model_use_id, _context("stop-daily-model"))
        assert app.daily_research.replay(plan)["matched"]  # Revocation stops new use, not historical evidence.
        abstention = replace(plan, prediction_id=uuid4())
        first = app.daily_research.abstain(abstention, reason="MODEL_USE_UNAVAILABLE", worker_id="daily-fixture")
        second = app.daily_research.abstain(abstention, reason="MODEL_USE_UNAVAILABLE", worker_id="daily-fixture")
        assert first == second
        assert first["runtime"].run_state == "SUCCEEDED"
