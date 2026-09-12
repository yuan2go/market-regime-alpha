from dataclasses import replace
from datetime import timedelta, datetime, UTC
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import psycopg

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_database, bootstrap_application
from market_regime_alpha.market.domain import (
    Provider,
    ProviderKind,
    ProviderProduct,
    SourceAvailabilityStatus,
    MarketFactKind,
    InstrumentFactKind,
    BarTimeframe,
    PriceBasis,
    NormalizationBatch,
    Instrument,
    InstrumentType,
    InstrumentIdentifier,
)
from market_regime_alpha.market.ports import CaptureRequest, ProviderResponse
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import a_share_instrument_id
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
    prospective_operation_session,
    daily_research_admission,
)
from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan, collect_daily
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from tests.contracts.research_qualification.archive_campaign_fixture import _session, _context
from tests.contracts.research_qualification import test_research_postgres as R
from tests.contracts.research_qualification.test_daily_prediction import plan as template


class DailyProvider:
    def __init__(self):
        self.calls = []

    def capture(self, request):
        query = BaoStockArchiveQuery.from_resource(request.resource)
        self.calls.append(query)
        payload = {
            "error_code": "0",
            "error_message": "success",
            "fields": ["date", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag", "tradestatus", "isST"],
            "rows": [[str(query.start_date), query.code, "100", "106", "99", "105", "1000", "105000", "3", "1", "0"]],
            "query": json.loads(query.resource),
        }
        if query.kind == BaoStockArchiveQueryKind.CSI300_MEMBERS:
            payload["fields"] = ["updateDate", "code", "code_name"]
            payload["rows"] = [[str(query.start_date), code, "Fixture"] for code in ("sh.600000", "sh.600001")]
        return ProviderResponse(
            json.dumps(payload).encode(), "application/json", "UTF-8", None, SourceAvailabilityStatus.UNKNOWN, None, "SYNTHETIC_FIXTURE"
        )


@pytest.mark.parametrize("repair_failed_population", [False, True])
def test_collection_claim_capture_normalize_and_restart_keep_exact_bytes(target_database_url, tmp_path, monkeypatch, repair_failed_population):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        provider = Provider(uuid4(), "daily_collection_fixture", "Synthetic test Provider", ProviderKind.PUBLIC_ENDPOINT)
        product = ProviderProduct(
            uuid4(),
            provider.provider_id,
            "daily_collection_raw",
            1,
            "DAILY_RAW",
            "application/json",
            "UTF-8",
            SourceAvailabilityStatus.UNKNOWN,
            tuple(MarketFactKind),
            tuple(InstrumentFactKind),
            tuple(BarTimeframe),
            tuple(PriceBasis),
        )
        app.market.register_provider(provider, _context("collection-provider"))
        app.market.register_provider_product(product, _context("collection-product"))
        capture = app.market.capture(
            CaptureRequest(product.provider_product_id, "foundation", "fixture://foundation", "1" * 64),
            R._BytesProvider(),
            _context("collection-foundation"),
        )
        cid = capture.capture.capture_id
        now = app.daily_prediction_reads.now()
        today = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
        input_session, target_session = (_session(today + timedelta(days=offset), cid, "XSHG") for offset in (-1, 1))
        codes = ("sh.600000", "sh.600001")
        instruments = tuple(a_share_instrument_id(code) for code in codes)
        batch = NormalizationBatch(
            cid,
            product.provider_product_id,
            trading_sessions=(input_session, target_session),
            instruments=tuple(
                Instrument(i, code.split(".")[1] + ".XSHG", "XSHG", InstrumentType.EQUITY, "CNY", cid)
                for i, code in zip(instruments, codes)
            ),
            instrument_identifiers=tuple(
                InstrumentIdentifier(uuid4(), i, "BAOSTOCK", code, datetime(2000, 1, 1, tzinfo=UTC), None, 1, None, cid)
                for i, code in zip(instruments, codes)
            ),
        )
        app.market.normalize(cid, R._Normalizer(lambda _: batch), _context("collection-normalize-foundation"))
        code = app.artifacts.publish(b"daily collection fixture", media_type="text/plain", context=_context("collection-code"))
        artifact = ArtifactBinding(code.artifact_id, code.content_sha256, code.size_bytes)
        instant = app.daily_prediction_reads.now()
        frozen = replace(
            template(),
            prediction_id=uuid4(),
            provider_product_id=product.provider_product_id,
            classification_scheme="INDEX_MEMBERSHIP",
            instrument_ids=tuple(sorted((i.value for i in instruments), key=str)),
            input_session_id=input_session.session_id.value,
            target_session_id=target_session.session_id.value,
            input_cutoff=instant,
            decision_time=instant,
            code_artifact=artifact,
            config_artifact=artifact,
        )
        import json
        scope = app.artifacts.publish(json.dumps({"schema": "selection-universe-scope-v1",
            "classification_code": frozen.classification_code, "classification_scheme": frozen.classification_scheme,
            "instrument_ids": [str(identity) for identity in frozen.instrument_ids],
            "market_provider_product_id": str(frozen.provider_product_id)}, sort_keys=True,
            separators=(",", ":")).encode(), media_type="application/json", context=_context("collection-scope"))
        frozen = replace(frozen, universe_scope=ArtifactBinding(scope.artifact_id, scope.content_sha256, scope.size_bytes))
        collection = DailyCollectionPlan(frozen, "input", 1, instant)
        identity = app.evidence.inventory()["database"]
        fake = DailyProvider()
        with prospective_operation_session(
            target_database_url,
            database_name=identity["name"],
            database_oid=identity["oid"],
            cluster_identity=identity["cluster_identity"],
            series_code="daily-fixture",
        ) as supervisor:

            def guard():
                supervisor.require_supervisor_lock("daily-fixture")
                assert not supervisor.has_conflicting_attempts("daily-fixture")

            with daily_research_admission(
                prediction_id=frozen.prediction_id,
                code_sha=frozen.code_sha,
                config_sha256=collection.content_sha256,
                collection_phase="input",
                collection_round=1,
            ):
                result = collect_daily(app, collection, fake, worker_id="daily-fixture", maximum_steps=1, before_action=guard)
                assert result.steps[0].state == "SUCCEEDED"
                result = collect_daily(app, collection, fake, worker_id="daily-fixture", maximum_steps=4, before_action=guard)
                assert result.run_state == "SUCCEEDED", result
                assert len(fake.calls) == 2
                again = collect_daily(app, collection, fake, worker_id="daily-fixture", maximum_steps=4, before_action=guard)
                assert again == result and len(fake.calls) == 2
                with monkeypatch.context() as clock:
                    clock.setattr(app.daily_prediction_reads, "now", lambda: target_session.open_at + timedelta(seconds=1))
                    assert collect_daily(app, collection, fake, worker_id="daily-fixture", maximum_steps=4, before_action=guard) == result
                    assert len(fake.calls) == 2

        updated = app.daily_prediction_reads.now()
        ready = app.daily_prediction_reads.observe(replace(frozen, input_cutoff=updated, decision_time=updated))
        assert ready.state == "READY"
        assert [value for _, value in ready.feature_values] == [R.Decimal(".05")] * 2
        assert app.daily_prediction_reads.collection_rounds(frozen.prediction_id, "input")[0][1] == "SUCCEEDED"
        assert not app.daily_prediction_reads.population_source_ready(frozen)
        population = DailyCollectionPlan(frozen, "population", 1, updated)
        with prospective_operation_session(target_database_url, database_name=identity["name"], database_oid=identity["oid"], cluster_identity=identity["cluster_identity"], series_code="daily-fixture") as supervisor:
            with daily_research_admission(prediction_id=frozen.prediction_id, code_sha=frozen.code_sha, config_sha256=population.content_sha256, collection_phase="population"):
                if repair_failed_population:
                    collect_daily(app, population, fake, worker_id="daily-fixture", maximum_steps=1, before_action=guard)
                    with psycopg.connect(target_database_url) as connection:
                        connection.execute("UPDATE mra.artifact SET last_verified_at=clock_timestamp()-interval '25 hours' WHERE artifact_id=%s", (capture.artifact.artifact_id,))
                        connection.commit()
                    with pytest.raises(RuntimeError, match="canonical invariants"):
                        collect_daily(app, population, fake, worker_id="daily-fixture", maximum_steps=1, before_action=guard)
                    failed = app.runtime.inspect_run(population.run_id)
                    assert failed.run_state == "FAILED"
                    assert failed.steps[1].latest_attempt_error_code == "NORMALIZATION_BINDING_REJECTED"
                    app.artifacts.verify(capture.artifact.artifact_id, verifier_id="fixture", context=_context("refresh-population-reference"))
                else:
                    captured = collect_daily(app, population, fake, worker_id="daily-fixture", maximum_steps=2, before_action=guard)
                    assert captured.run_state == "SUCCEEDED"
                    assert collect_daily(app, population, fake, worker_id="daily-fixture", maximum_steps=2, before_action=guard) == captured
            if repair_failed_population:
                from market_regime_alpha.interfaces.daily_collection import retry_failed_population_collection

                kwargs = dict(worker_id="daily-fixture", maximum_steps=2, before_action=guard)
                recovered = retry_failed_population_collection(app, population, fake, **kwargs)
                assert recovered.run_state == "SUCCEEDED" and recovered.run_id != failed.run_id
                assert retry_failed_population_collection(app, population, fake, **kwargs) == recovered
                assert app.runtime.inspect_run(population.run_id) == failed
                with pytest.raises(RuntimeError, match="EXACT_FAILED_POPULATION"):
                    retry_failed_population_collection(app, replace(population, prediction=replace(frozen, model_version_id=uuid4())), fake, **kwargs)
        assert len(fake.calls) == (4 if repair_failed_population else 3)
        assert fake.calls[-1].start_date == today
        assert not app.daily_prediction_reads.population_source_ready(frozen)  # No retroactive visibility.
        observed = app.daily_prediction_reads.now()
        assert app.daily_prediction_reads.population_source_ready(replace(frozen, decision_time=observed, input_cutoff=observed))
        assert app.daily_prediction_reads.collection_rounds(frozen.prediction_id, "population")[-1][1] == "SUCCEEDED"
