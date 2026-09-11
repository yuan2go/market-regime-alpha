from market_regime_alpha.bootstrap import TargetSettings, bootstrap_database, bootstrap_application
from tests.contracts.research_qualification.daily_campaign_fixture import daily_baseline
from tests.contracts.research_qualification.archive_campaign_fixture import _context
import pytest


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


@pytest.mark.parametrize("missing_membership,mature_prices", [(False, False), (False, True), (True, False)])
def test_completed_model_is_consumed_without_backtest_and_publication_is_replayable(
    target_database_url, tmp_path, missing_membership, mature_prices, monkeypatch, record_property
):
    from dataclasses import replace
    from datetime import timedelta
    from decimal import Decimal as D
    import json
    from types import SimpleNamespace
    from uuid import uuid4, uuid5
    from zoneinfo import ZoneInfo
    from market_regime_alpha.market.domain import (
        NormalizationBatch,
        BarTimeframe,
        SecurityStatusFactRevision,
        SecurityStatus,
        EvidenceScope,
        GapFactKind,
        GapKind,
        GapReasonCode,
        PriceBasis,
        SourceGap,
    )
    from market_regime_alpha.market.ports import CaptureRequest
    from market_regime_alpha.shared.financial import Money
    from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
    from market_regime_alpha.research_qualification.domain.daily_inputs import (
        DailyInputState,
    )
    from market_regime_alpha.research_qualification.domain.experimental_model_use import ExperimentalModelUsePlan
    from market_regime_alpha.decision_support.domain.strategy import StrategyPlan
    from tests.contracts.research_qualification.archive_campaign_fixture import _session, _bar
    from tests.contracts.research_qualification import test_research_postgres as R

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
        # Fresh data for another session or security cannot hide this plan's
        # stale input. Exercise both exclusions through canonical normalization.
        from market_regime_alpha.market.domain import Instrument, InstrumentType
        from market_regime_alpha.shared.identity import InstrumentId
        with app._pool.connection(read_only=True) as connection:
            expected_freshness = connection.execute(
                'SELECT max(recorded_at) FROM mra.market_bar_revision WHERE bar_revision_id=ANY(%s::uuid[])',
                ([b.bar_revision_id for b in bars],),
            ).fetchone()[0]
        for outside in ('session', 'instrument'):
            extra_capture = app.market.capture(
                CaptureRequest(c['product'].provider_product_id, 'unrelated-freshness-' + outside, 'fixture://unrelated', 'e' * 64),
                R._BytesProvider(), _context('freshness-capture-' + outside),
            ).capture.capture_id
            extra_session = _session(today - timedelta(days=20), extra_capture, 'XSHG') if outside == 'session' else input_session
            extra_instrument = InstrumentId(uuid4()) if outside == 'instrument' else c['instruments'][0]
            extra_bar = replace(
                bars[0], bar_revision_id=uuid4(), capture_id=extra_capture,
                instrument_id=extra_instrument, session_id=extra_session.session_id,
                event_start=extra_session.open_at, event_end=extra_session.close_at,
            )
            extra_batch = NormalizationBatch(
                extra_capture, c['product'].provider_product_id,
                instruments=(Instrument(extra_instrument, 'FRESHNESS.XSHG', 'XSHG', InstrumentType.EQUITY, 'CNY', extra_capture),) if outside == 'instrument' else (),
                trading_sessions=(extra_session,) if outside == 'session' else (), bars=(extra_bar,),
            )
            app.market.normalize(extra_capture, R._Normalizer(lambda _, batch=extra_batch: batch), _context('freshness-normalize-' + outside))
            with app._pool.connection(read_only=True) as connection:
                assert connection.execute('SELECT recorded_at>%s FROM mra.market_bar_revision WHERE bar_revision_id=%s', (expected_freshness, extra_bar.bar_revision_id)).fetchone() == (True,)
            freshness = app.daily_prediction_reads.operational_health(plan)['data_freshness']
            assert freshness['last_bar_recorded_at'] == expected_freshness
        if missing_membership:
            scope_bytes = json.dumps({"classification_code":"ABSENT_CURRENT_MEMBERSHIP","classification_scheme":plan.classification_scheme,"instrument_ids":[str(i) for i in plan.instrument_ids],"market_provider_product_id":str(plan.provider_product_id),"schema":"selection-universe-scope-v1"}, sort_keys=True,separators=(",",":")).encode()
            scope_artifact=app.artifacts.publish(scope_bytes,media_type="application/json",context=_context("missing-membership-scope"))
            plan = replace(plan, classification_code="ABSENT_CURRENT_MEMBERSHIP",universe_scope=plan.universe_scope.__class__(scope_artifact.artifact_id,scope_artifact.content_sha256,scope_artifact.size_bytes))
        ready = app.daily_prediction_reads.observe(plan)
        assert ready.state == "READY"
        plan = replace(plan, input_content_sha256=ready.content_sha256)
        from market_regime_alpha.interfaces.daily_service import current_daily_plan

        plan = current_daily_plan(app, plan)
        app.daily_prediction_reads.validate_configuration(plan)
        trace = app.daily_research.execute(plan, worker_id="daily-fixture")
        assert trace.run_state == "SUCCEEDED", trace
        report = app.daily_prediction_reads.forecast_projection(plan)
        if missing_membership:
            assert report["denominators"] == dict(sampled=32, eligible=0, feature_ready=0, model_prediction=0, baseline_prediction=0, common_prediction=0)
            assert report["model_inference_state"] == "NOT_RUN_EMPTY_POPULATION"
            assert len(report["population"]) == 32
            assert report["predictions"] == []
            assert app.daily_research.replay(plan)["matched"]
            with app._pool.connection(read_only=True) as connection:
                assert connection.execute("SELECT count(*) FROM mra.forecast_model_binding WHERE experimental_model_use_id=%s", (use.experimental_model_use_id,)).fetchone() == (0,)
            return
        assert report["denominators"] == dict(
            sampled=32, eligible=32, feature_ready=32, model_prediction=32, baseline_prediction=32, common_prediction=32
        )
        assert len(report["predictions"]) == 32
        if mature_prices:
            # A restart must re-observe exact algorithm/config bytes before a
            # first settlement claim; publication identities remain immutable.
            import importlib.util
            from pathlib import Path
            template_path = Path(__file__).resolve().parents[3] / 'docs/operations/templates/verify_prospective_artifacts.py'
            module_spec = importlib.util.spec_from_file_location('daily_execution_integrity', template_path)
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            outcome_run = uuid5(plan.prediction_id, 'outcome-evaluation-runtime')
            with app._pool.connection() as connection:
                runtime_config, = connection.execute('SELECT config_artifact_id FROM mra.runtime_run WHERE run_id=%s', (outcome_run,)).fetchone()
                expected = {runtime_config, plan.code_artifact.artifact_id, plan.config_artifact.artifact_id,
                            c['target'].algorithm.code_artifact.artifact_id, c['target'].algorithm.config_artifact.artifact_id}
                connection.execute("UPDATE mra.artifact SET last_verified_at=clock_timestamp()-interval '25 hours' WHERE artifact_id=ANY(%s::uuid[])", (list(expected),))
                connection.commit()
                before = connection.execute('SELECT to_jsonb(r) FROM mra.runtime_run r WHERE run_id=ANY(%s::uuid[]) ORDER BY run_id', ([plan.runtime_run_id, outcome_run],)).fetchall()
                references = module._daily_execution_artifacts(connection, plan)
                assert expected <= {row[0] for row in references}
            for artifact_id, in references:
                verified = app.artifacts.verify(artifact_id, verifier_id='fixture-operator', context=_context('restart-integrity:' + str(artifact_id)))
                assert verified.result == 'VERIFIED'
            with app._pool.connection(read_only=True) as connection:
                assert connection.execute('SELECT to_jsonb(r) FROM mra.runtime_run r WHERE run_id=ANY(%s::uuid[]) ORDER BY run_id', ([plan.runtime_run_id, outcome_run],)).fetchall() == before
        assert app.daily_research.settle_and_evaluate(plan, worker_id="daily-fixture")["state"] == "PENDING"
        assert app.daily_research.execute(plan, worker_id="daily-fixture").run_state == "SUCCEEDED"
        assert app.daily_research.replay(plan)["matched"]
        from market_regime_alpha.interfaces.daily_service import daily_tick
        from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
            daily_delivery_admission,
            prospective_operation_session,
        )
        from market_regime_alpha.interfaces.daily_delivery import (
            DailyDeliveryAttempt,
            DailyReportDelivery,
        )

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

            def delivery_scope(delivery_plan):
                return daily_delivery_admission(
                    prediction_id=delivery_plan.prediction_id,
                    experimental_model_use_id=(
                        delivery_plan.experimental_model_use_id
                    ),
                    code_sha=delivery_plan.code_sha,
                    config_sha256=delivery_plan.content_sha256,
                    channel=delivery_plan.channel,
                )

            class SequencedDelivery:
                channel = "fixture"

                def __init__(self):
                    self.keys = []
                    self.responses = [
                        DailyDeliveryAttempt(
                            "PROVEN_NOT_SENT", "FIXTURE_PROVEN_NOT_SENT"
                        ),
                        DailyDeliveryAttempt(
                            "DELIVERED", "FIXTURE_ACKNOWLEDGED", "receipt-1"
                        ),
                    ]

                def deliver(self, _content, *, idempotency_key):
                    self.keys.append(idempotency_key)
                    return self.responses.pop(0)

            adapter = SequencedDelivery()
            delivery_tick = daily_tick(
                app,
                plan,
                NoProviderEffect(),
                worker_id="daily-fixture",
                maximum_steps=2,
                before_action=before,
                delivery_adapter=adapter,
            )
            assert delivery_tick["state"] == "PREDICTION_PUBLISHED"
            assert delivery_tick["delivery"]["state"] == "RETRY_PENDING"
            assert not delivery_tick["delivery"][
                "prediction_and_settlement_blocked"
            ]
            delivery = DailyReportDelivery(
                app,
                app.daily_prediction_reads,
                admission_scope=delivery_scope,
                before_action=before,
            )
            delivered = delivery.deliver(
                plan,
                adapter,
                worker_id="daily-fixture",
                maximum_attempts=2,
            )
            replayed_delivery = delivery.deliver(
                plan,
                adapter,
                worker_id="daily-fixture",
                maximum_attempts=2,
            )
            assert delivered["state"] == "DELIVERED"
            assert replayed_delivery["state"] == "DELIVERED"
            assert adapter.keys == [adapter.keys[0], adapter.keys[0]]
            assert delivered["response"]["remote_receipt_id"] == "receipt-1"

            with app._pool.connection(read_only=True) as connection:
                before_counts = connection.execute(
                    "SELECT (SELECT count(*) FROM mra.runtime_run), "
                    "(SELECT count(*) FROM mra.artifact)"
                ).fetchone()
            assert delivery.deliver(
                plan, None, worker_id="daily-fixture"
            )["state"] == "NOT_CONFIGURED"
            with app._pool.connection(read_only=True) as connection:
                after_counts = connection.execute(
                    "SELECT (SELECT count(*) FROM mra.runtime_run), "
                    "(SELECT count(*) FROM mra.artifact)"
                ).fetchone()
            assert after_counts == before_counts

            class UnknownDelivery:
                channel = "fixture-unknown"

                def __init__(self):
                    self.calls = 0

                def deliver(self, _content, *, idempotency_key):
                    del idempotency_key
                    self.calls += 1
                    return DailyDeliveryAttempt("UNKNOWN", "FIXTURE_UNKNOWN")

            unknown_adapter = UnknownDelivery()
            unknown = delivery.deliver(
                plan, unknown_adapter, worker_id="daily-fixture"
            )
            unknown_replay = delivery.deliver(
                plan, unknown_adapter, worker_id="daily-fixture"
            )
            assert unknown["state"] == "DELIVERY_UNKNOWN"
            assert unknown_replay["state"] == "DELIVERY_UNKNOWN"
            assert unknown_adapter.calls == 1

            class ProvenAbsentDelivery:
                channel = "fixture-expired"

                def __init__(self):
                    self.calls = 0

                def deliver(self, _content, *, idempotency_key):
                    del idempotency_key
                    self.calls += 1
                    return DailyDeliveryAttempt(
                        "PROVEN_NOT_SENT", "FIXTURE_PROVEN_NOT_SENT"
                    )

            expiring_adapter = ProvenAbsentDelivery()
            expiring = delivery.deliver(
                plan,
                expiring_adapter,
                worker_id="daily-fixture",
                expires_at=(
                    app.daily_prediction_reads.now()
                    + timedelta(seconds=1)
                ),
            )
            assert expiring["state"] == "RETRY_PENDING"

            class CrashAfterEffect:
                channel = "fixture-crash"

                def __init__(self):
                    self.calls = 0

                def deliver(self, _content, *, idempotency_key):
                    del idempotency_key
                    self.calls += 1
                    raise SystemExit("simulated crash after external effect")

            crash_adapter = CrashAfterEffect()
            short_lease_delivery = DailyReportDelivery(
                app,
                app.daily_prediction_reads,
                admission_scope=delivery_scope,
                before_action=before,
                lease_duration=timedelta(seconds=1),
            )
            with pytest.raises(SystemExit, match="simulated crash"):
                short_lease_delivery.deliver(
                    plan, crash_adapter, worker_id="daily-fixture"
                )
            import time

            time.sleep(1.05)
            expired = delivery.deliver(
                plan, expiring_adapter, worker_id="daily-fixture"
            )
            assert expired["state"] == "EXPIRED"
            assert expired["runtime_state"] == "FAILED"
            assert expiring_adapter.calls == 1
            crash_recovery = short_lease_delivery.deliver(
                plan, crash_adapter, worker_id="daily-fixture"
            )
            assert crash_recovery["state"] == "DELIVERY_UNKNOWN"
            assert crash_recovery["runtime_state"] == "WAITING"
            assert crash_adapter.calls == 1
        assert tick["state"] == "PREDICTION_PUBLISHED"
        assert tick["result"].run_state == "SUCCEEDED"
        assert tick["pending"][0]["state"] == "PENDING_MATURITY"
        assert tick["health"]["last_successful_publication_at"] is not None
        assert tick["health"]["outcome_backlog"][
            "pending_maturity_count"
        ] == 1
        assert tick["health"]["calendar"][
            "future_captured_session_count"
        ] >= 1
        assert tick["health"]["data_freshness"][
            "last_capture_recorded_at"
        ] is not None

        # Freeze a second Run through the rule baseline, then revoke the use.
        # Recovery must terminalize the still-unpublished model step while the
        # already-published first Run remains eligible for historical outcome.
        partial = replace(
            plan,
            prediction_id=uuid4(),
            input_content_sha256="0" * 64,
        )
        partial = replace(
            partial,
            input_content_sha256=app.daily_prediction_reads.observe(
                partial
            ).content_sha256,
        )
        partial_trace = app.daily_research.execute(
            partial,
            worker_id="daily-fixture",
            maximum_steps=7,
        )
        assert next(
            step for step in partial_trace.steps if step.step_key == "model-forecast"
        ).state == "READY"
        app.research_models.revoke_experimental_use(use.experimental_model_use_id, _context("stop-daily-model"))
        stopped = app.daily_research.execute(
            partial,
            worker_id="daily-fixture",
        )
        stopped_model = next(
            step for step in stopped.steps if step.step_key == "model-forecast"
        )
        assert stopped.run_state == "FAILED"
        assert stopped_model.state == "FAILED"
        assert (
            stopped_model.latest_attempt_error_code
            == "MODEL_USE_UNAVAILABLE_FOR_NEW_PREDICTION"
        )
        with app._pool.connection(read_only=True) as connection:
            assert connection.execute(
                "SELECT count(*) FROM mra.forecast_model_binding "
                "WHERE decision_run_id=%s AND experimental_model_use_id=%s",
                (
                    app.daily_prediction_reads.decision_run(partial),
                    partial.experimental_model_use_id,
                ),
            ).fetchone() == (0,)
        assert app.daily_research.replay(plan)["matched"]  # Revocation stops new use, not historical evidence.
        assert app.daily_prediction_reads.operational_health(plan)[
            "model_use"
        ]["state"] == "REVOKED"
        assert app.daily_prediction_reads.operational_health(plan)["runtime"][
            "failed_count"
        ] >= 1
        from market_regime_alpha.interfaces.daily_research import decode_daily_plan
        from market_regime_alpha.runtime.errors import RuntimeStateConflictError

        historical = app.daily_prediction_reads.outcome_work_items()
        old_item = next(
            item
            for item in historical
            if item.run_id == uuid5(plan.prediction_id, "outcome-evaluation-runtime")
        )
        assert old_item.plan_content is not None
        assert decode_daily_plan(old_item.plan_content) == plan
        with pytest.raises(RuntimeStateConflictError, match="MODEL_USE_UNAVAILABLE"):
            app.daily_research.execute(
                replace(plan, prediction_id=uuid4()), worker_id="daily-fixture"
            )
        abstention = replace(plan, prediction_id=uuid4())
        first = app.daily_research.abstain(abstention, reason="MODEL_USE_UNAVAILABLE", worker_id="daily-fixture")
        second = app.daily_research.abstain(abstention, reason="MODEL_USE_UNAVAILABLE", worker_id="daily-fixture")
        assert first == second
        assert first["runtime"].run_state == "SUCCEEDED"

        simulated_now = target_session.close_at + timedelta(hours=8, minutes=1)
        with monkeypatch.context() as clock:
            from market_regime_alpha.infrastructure.postgres.repositories.outcomes import (
                PostgresOutcomeRepository,
            )
            from market_regime_alpha.infrastructure.postgres.repositories.research_evaluation_inputs import (
                PostgresTransactionalOutcomeAcquisition,
            )
            from market_regime_alpha.infrastructure.postgres.repositories.research_evaluations import (
                PostgresEvaluationRepository,
            )

            clock.setattr(app.daily_prediction_reads, "now", lambda: simulated_now)
            clock.setattr(
                app.daily_prediction_reads,
                "first_attempt_at",
                lambda _step_id: simulated_now,
            )
            clock.setattr(
                app.market,
                "_database_clock",
                SimpleNamespace(now=lambda: simulated_now),
            )
            clock.setattr(
                PostgresOutcomeRepository,
                "authoritative_settled_at",
                lambda _repository: simulated_now,
            )
            clock.setattr(
                PostgresEvaluationRepository,
                "authoritative_opened_at",
                lambda _repository: simulated_now,
            )
            clock.setattr(
                PostgresTransactionalOutcomeAcquisition,
                "authoritative_accessed_at",
                lambda _repository: simulated_now + timedelta(microseconds=1),
            )
            clock.setattr(
                PostgresEvaluationRepository,
                "authoritative_completed_at",
                lambda _repository: simulated_now + timedelta(microseconds=2),
            )
            outcome_capture = app.market.capture(
                CaptureRequest(
                    plan.provider_product_id,
                    "daily-outcome-time-advance-fixture",
                    "fixture://simulated-mature-outcome",
                    "e" * 64,
                ),
                R._BytesProvider(),
                _context("daily-outcome-time-advance-capture"),
            )
            outcome_capture_id = outcome_capture.capture.capture_id
            app.market.normalize(
                outcome_capture_id,
                R._Normalizer(
                    lambda _: NormalizationBatch(
                        outcome_capture_id,
                        plan.provider_product_id,
                        bars=tuple(
                            replace(
                                _bar(plan.provider_product_id, outcome_capture_id, instrument, target_session, "REFERENCE", i),
                                bar_revision_id=uuid4(), timeframe=BarTimeframe.DAILY,
                                event_start=target_session.open_at, event_end=target_session.close_at,
                                open=Money(D(10), "CNY"), close=Money(D(10) + D(i + 1) / 100, "CNY"),
                                high=Money(D(11), "CNY"), low=Money(D(9), "CNY"),
                            ) for i, instrument in enumerate(c["instruments"])
                        ) if mature_prices else (),
                        gaps=() if mature_prices else tuple(
                            SourceGap(
                                uuid4(),
                                plan.provider_product_id,
                                outcome_capture_id,
                                instrument,
                                target_session.session_id,
                                GapKind.MISSING,
                                GapReasonCode.NO_ROWS_RETURNED,
                                GapFactKind.MARKET_BAR,
                                None,
                                BarTimeframe.DAILY,
                                PriceBasis.RAW_UNADJUSTED,
                                target_session.open_at,
                                target_session.close_at,
                                "synthetic time-advance fixture has no target bar",
                            )
                            for instrument in c["instruments"]
                        ),
                    )
                ),
                _context("daily-outcome-time-advance-normalize"),
            )
            with app._pool.connection(read_only=True) as connection:
                gap_ids = dict(connection.execute(
                    "SELECT instrument_id,gap_id FROM mra.source_gap WHERE capture_id=%s",
                    (outcome_capture_id,),
                ).fetchall())
            assert len(gap_ids) == (0 if mature_prices else len(plan.instrument_ids))
            clock.setattr(app.daily_prediction_reads, "target_price_members", lambda _plan: tuple(
                SimpleNamespace(state=DailyInputState.AVAILABLE if mature_prices else DailyInputState.MISSING,
                                source_gap_id=gap_ids.get(instrument))
                for instrument in plan.instrument_ids))
            if mature_prices:
                complete = app.research_evaluations.complete
                def committed_reply_lost(*args, **kwargs):
                    complete(*args, **kwargs)
                    raise SystemExit("simulated lost Evaluation completion reply")
                monkeypatch.setattr(app.research_evaluations, "complete", committed_reply_lost)
            with prospective_operation_session(
                target_database_url,
                database_name=identity["name"],
                database_oid=identity["oid"],
                cluster_identity=identity["cluster_identity"],
                series_code="daily-fixture",
            ) as supervisor:

                def settlement_guard():
                    supervisor.require_supervisor_lock("daily-fixture")
                    assert not supervisor.has_conflicting_attempts(
                        "daily-fixture"
                    )

                def tick(application):
                    return daily_tick(application, plan, NoProviderEffect(), worker_id="daily-fixture",
                                      maximum_steps=128, before_action=settlement_guard)
                if mature_prices:
                    with pytest.raises(SystemExit, match="lost Evaluation completion reply"):
                        tick(app)
                else:
                    settlement_tick = tick(app)
            if mature_prices:
                with bootstrap_application(settings) as restarted:
                    clock.setattr(restarted.daily_prediction_reads, "now", lambda: simulated_now)
                    clock.setattr(restarted.daily_prediction_reads, "first_attempt_at", lambda _: simulated_now)
                    with prospective_operation_session(target_database_url,
                            database_name=identity["name"], database_oid=identity["oid"],
                            cluster_identity=identity["cluster_identity"], series_code="daily-fixture") as supervisor:
                        from market_regime_alpha.interfaces.daily_service import prepare_pending_daily_recovery
                        prepare_pending_daily_recovery(restarted, supervisor)
                        settlement_tick = tick(restarted)
                        trace = restarted.runtime.inspect_run(uuid5(plan.prediction_id, "outcome-evaluation-runtime"))
                        evaluation_step = next(step for step in trace.steps if step.step_key == "evaluate")
                        assert evaluation_step.attempt_states == ("SUCCEEDED",)
        assert settlement_tick["state"] == "OUTCOME_PROGRESS", [
            (item["state"], item.get("reason_code"))
            for item in settlement_tick["pending"]
        ]
        assert settlement_tick["outcomes"][0]["state"] == "SETTLEMENT_PROGRESS"
        assert settlement_tick["outcomes"][0]["result"].run_state == "SUCCEEDED"

        outcome_run_id = uuid5(plan.prediction_id, "outcome-evaluation-runtime")
        evaluation_id = uuid5(plan.prediction_id, "evaluation")
        partition_id = uuid5(plan.prediction_id, "evaluation-partition")
        with app._pool.connection(read_only=True) as connection:
            assert connection.execute(
                "SELECT source_decision_run_id FROM mra.research_partition "
                "WHERE research_partition_id=%s",
                (partition_id,),
            ).fetchone() == (app.daily_prediction_reads.decision_run(plan),)
            assert connection.execute(
                "SELECT count(*) FROM mra.market_target_outcome_revision "
                "WHERE runtime_run_id=%s",
                (outcome_run_id,),
            ).fetchone() == (len(plan.instrument_ids),)
            assert connection.execute(
                "SELECT status FROM mra.evaluation_run "
                "WHERE evaluation_run_id=%s",
                (evaluation_id,),
            ).fetchone() == ("COMPLETED",)
            if mature_prices:
                labels = connection.execute(
                    "SELECT metric.decimal_value FROM mra.market_target_outcome_metric metric "
                    "JOIN mra.market_target_outcome_revision revision USING(market_target_outcome_revision_id) "
                    "WHERE revision.runtime_run_id=%s ORDER BY metric.decimal_value",
                    (outcome_run_id,),
                ).fetchall()
                # Each open is 10 CNY; close is 10 + i/100 CNY. The target is
                # an observed price ratio, not an account/tradability return.
                assert labels == [(D(i) / 1000,) for i in range(1, 33)]
                metrics = connection.execute(
                    "SELECT metric_state, estimable_count FROM mra.evaluation_metric WHERE evaluation_run_id=%s",
                    (evaluation_id,),
                ).fetchall()
                assert metrics and all(row == ("ESTIMATED", 32) for row in metrics)
            before_replay = connection.execute(
                "SELECT (SELECT count(*) FROM mra.command_receipt), "
                "(SELECT count(*) FROM mra.artifact), "
                "(SELECT count(*) FROM mra.market_target_outcome_revision)"
            ).fetchone()
        cycle = app.daily_research.replay_completed_cycle(plan)
        assert cycle["matched"] and cycle["business_writes"] == 0
        assert cycle["model_version_id"] == plan.model_version_id
        assert cycle["experimental_model_use_id"] == plan.experimental_model_use_id
        assert cycle["research_dispositions"] == ()
        record_property("cycle", json.dumps(cycle, default=str, sort_keys=True))
        record_property("database", json.dumps(identity, default=str, sort_keys=True))
        record_property("scope", "DISPOSABLE_SYNTHETIC_CLOCK_NOT_PROSPECTIVE_PROOF")
        from io import StringIO
        from market_regime_alpha.interfaces.cli import main
        plan_path = tmp_path / "replay-plan.json"
        from market_regime_alpha.interfaces.daily_research import encode_daily_plan
        plan_path.write_bytes(encode_daily_plan(plan))
        for command in ("report", "replay", "replay"):
            output, errors = StringIO(), StringIO()
            assert main(["research", "daily", command, "--plan", str(plan_path)],
                        environ={"MRA_DATABASE_URL": settings.database_url, "MRA_ARTIFACT_ROOT": str(settings.artifact_root)},
                        stdout=output, stderr=errors) == 0, errors.getvalue()
            result = json.loads(output.getvalue())
            assert result["state"] == "COMPLETED"
            assert result["reconciliation"]["evaluation_id"] == str(evaluation_id)
            assert result["reconciliation"]["matched"] and result["reconciliation"]["mismatch_count"] == 0
        from market_regime_alpha.interfaces.daily_health import daily_health
        ledger = daily_health(app, cutover_at=plan.decision_time, replay=True)
        entry = next(row for row in ledger["ledger"] if row.get("prediction_id") == plan.prediction_id)
        assert entry["state"] == "COMPLETED", entry
        assert entry["model_version_id"] == plan.model_version_id
        assert entry["evaluation_id"] == evaluation_id
        assert entry["denominators"]["sampled"] == len(plan.instrument_ids)
        assert entry["replay"]["matched"] and entry["replay"]["mismatch_count"] == 0
        assert ledger["business_writes"] == 0
        from market_regime_alpha.interfaces.daily_observations import daily_observations
        from market_regime_alpha.runtime.errors import ArtifactIntegrityError
        observation = daily_observations(app, target_session_date=target_session.session_date,
                                         model_version_id=plan.model_version_id,
                                         target_definition_id=plan.target_definition_id)
        observed = next(row for row in observation["cycles"] if row["prediction_id"] == plan.prediction_id)
        expected_commitments = {row["commitment_id"] for row in app.daily_prediction_reads.forecast_projection(plan)["predictions"] if row["commitment_id"] is not None}
        assert {row["commitment_id"] for row in observed["observations"]} == expected_commitments
        assert {row["commitment_id"] for row in observed["labels"]} == expected_commitments
        assert observed["publication"]["denominators"]["sampled"] == len(plan.instrument_ids)
        assert observed["evaluation"] == app.daily_prediction_reads.evaluation_projection(evaluation_id)
        assert observed["frozen_plan_content"].encode() == encode_daily_plan(plan)
        assert observed["frozen_identities"]["model"]["model_version_id"] == plan.model_version_id
        assert observed["frozen_identities"]["experimental_model_use"]["experimental_model_use_id"] == plan.experimental_model_use_id
        assert observed["frozen_identities"]["dataset"]["dataset_id"] == plan.dataset_id
        assert {member["commitment_id"] for member in observed["commitments"]} == expected_commitments
        assert {member["commitment_id"] for member in observed["temporal_facts"]["outcome_observations"]} == expected_commitments
        assert all(member["source_role"] == "OUTCOME_OBSERVATION" for member in observed["temporal_facts"]["outcome_observations"])
        assert all(member["checkpoint_role"] == "OUTCOME_OBSERVATION" for member in observed["temporal_facts"]["outcome_observations"])
        assert all(member["capture_requested_at"] is not None for member in observed["temporal_facts"]["outcome_observations"])
        assert observed["temporal_facts"]["target_start"] == target_session.open_at
        assert observed["temporal_facts"]["target_end"] == target_session.close_at
        filtered = daily_observations(app, target_session_from=target_session.session_date,
            target_session_to=target_session.session_date, dataset_id=plan.dataset_id,
            experimental_model_use_id=plan.experimental_model_use_id,
            decision_run_id=observed["decision_run_id"], completed_only=True)
        assert [cycle["prediction_id"] for cycle in filtered["cycles"]] == [plan.prediction_id]
        assert filtered["unavailable"] == []
        calendar = app.daily_prediction_reads.validity_calendar()
        assert target_session.session_id.value in {row["session_id"] for row in calendar}
        assert [row["session_date"] for row in calendar] == sorted({row["session_date"] for row in calendar})
        assert observation["business_writes"] == 0
        assert not daily_observations(app, model_version_id=uuid4())["cycles"]
        with monkeypatch.context() as patch:
            original_observations = app.daily_prediction_reads.evaluation_observations
            def missing_acquisition(identity):
                result = original_observations(identity)
                result["observations"] = result["observations"][1:]
                return result
            patch.setattr(app.daily_prediction_reads, "evaluation_observations", missing_acquisition)
            with pytest.raises(ArtifactIntegrityError, match="acquisition roster differs"):
                daily_observations(app, model_version_id=plan.model_version_id)
        completed_health = app.daily_prediction_reads.operational_health(plan)
        assert completed_health["outcome_backlog"]["observed_count"] == 0
        assert completed_health["human_research_disposition"][
            "pending_review_count"
        ] == 1
        with app._pool.connection(read_only=True) as connection:
            after_replay = connection.execute(
                "SELECT (SELECT count(*) FROM mra.command_receipt), "
                "(SELECT count(*) FROM mra.artifact), "
                "(SELECT count(*) FROM mra.market_target_outcome_revision)"
            ).fetchone()
        assert after_replay == before_replay

        review_id = uuid4()
        disposition = app.daily_research.record_research_disposition(
            plan,
            review_id=review_id,
            reviewer_id="fixture-reviewer",
            disposition="INVESTIGATE",
            reason_code="SYNTHETIC_MISSING_OUTCOMES",
        )
        assert app.daily_research.record_research_disposition(
            plan,
            review_id=review_id,
            reviewer_id="fixture-reviewer",
            disposition="INVESTIGATE",
            reason_code="SYNTHETIC_MISSING_OUTCOMES",
        ) == disposition
        with pytest.raises(
            RuntimeError, match="disposition idempotency key was reused"
        ):
            app.daily_research.record_research_disposition(
                plan,
                review_id=review_id,
                reviewer_id="fixture-reviewer",
                disposition="NO_DECISION",
                reason_code="SYNTHETIC_MISSING_OUTCOMES",
            )
        reviewed_cycle = app.daily_research.replay_completed_cycle(plan)
        assert len(reviewed_cycle["research_dispositions"]) == 1
        review = reviewed_cycle["research_dispositions"][0]
        assert review["artifact"] == disposition
        assert review["disposition"] == "INVESTIGATE"
        assert not review["automatic_model_change"]
        assert not review["automatic_qualification_change"]
        reviewed_health = app.daily_prediction_reads.operational_health(plan)
        assert reviewed_health["human_research_disposition"] == {
            "pending_review_count": 0,
            "reviewed_count": 1,
            "automatic_model_change": False,
            "automatic_qualification_change": False,
        }
        assert reviewed_health["delivery"]["delivered_count"] == 1
        assert reviewed_health["delivery"]["failed_count"] == 1
        assert reviewed_health["delivery"][
            "reconciliation_required_count"
        ] == 2
