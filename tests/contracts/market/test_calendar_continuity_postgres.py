"""Calendar owner/restart claims use only the explicitly disposable fixture DB."""

from datetime import timedelta
import json
from uuid import uuid4

import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.infrastructure.postgres.prospective_operation_session import prospective_operation_session
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockArchiveNormalizer
from market_regime_alpha.interfaces.calendar_continuity import refresh_calendar
from market_regime_alpha.market.domain import Provider, ProviderKind, ProviderProduct, SourceAvailabilityStatus, MarketFactKind
from market_regime_alpha.market.ports import CaptureRequest, ProviderResponse, MarketProviderError
from market_regime_alpha.runtime.errors import RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from tests.contracts.research_qualification.archive_campaign_fixture import _context


class CalendarProvider:
    def __init__(self, missing=False, failure=False):
        self.missing = missing
        self.failure = failure
        self.calls = []

    def capture(self, request):
        self.calls.append(request)
        if self.failure:
            raise MarketProviderError("FIXTURE_PROVIDER_UNAVAILABLE", "Synthetic known Provider failure")
        query = BaoStockArchiveQuery.from_resource(request.resource)
        count = (query.end_date - query.start_date).days + 1
        rows = [] if self.missing else [[str(query.start_date + timedelta(days=index)), "1"] for index in range(count)]
        return ProviderResponse(json.dumps({"error_code": "0", "error_message": "fixture", "fields": ["calendar_date", "is_trading_day"],
            "rows": rows, "query": json.loads(query.resource)}).encode(), "application/json", "UTF-8", None, SourceAvailabilityStatus.UNKNOWN,
            None, "SYNTHETIC_FIXTURE")


def _product(app):
    provider = Provider(uuid4(), "calendar_fixture", "Synthetic explicit calendar", ProviderKind.PUBLIC_ENDPOINT)
    product = ProviderProduct(uuid4(), provider.provider_id, "calendar_fixture", 1, "CALENDAR", "application/json", "UTF-8",
        SourceAvailabilityStatus.UNKNOWN, (MarketFactKind.TRADING_SESSION,), (), (), ())
    app.market.register_provider(provider, _context("calendar-provider"))
    app.market.register_provider_product(product, _context("calendar-product"))
    return product


@pytest.mark.parametrize("mode", ["complete", "missing", "resume_normalization", "provider_failure"])
def test_calendar_claim_capture_normalize_and_repeated_observation_preserve_receipts(target_database_url, tmp_path, mode):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        product = _product(app)
        identity = app.evidence.inventory()["database"]
        provider = CalendarProvider(missing=mode == "missing", failure=mode == "provider_failure")
        interrupted = False
        expires_at = app.daily_prediction_reads.now() + timedelta(days=2)
        with prospective_operation_session(target_database_url, database_name=identity["name"], database_oid=identity["oid"],
                cluster_identity=identity["cluster_identity"], series_code="calendar-fixture") as supervisor:
            def guard():
                nonlocal interrupted
                supervisor.require_supervisor_lock("calendar-fixture")
                assert not supervisor.has_conflicting_attempts("calendar-fixture")
                if mode == "resume_normalization" and provider.calls and not interrupted:
                    interrupted = True
                    raise RuntimeStateConflictError("FIXTURE_STOP_AFTER_COMMITTED_CAPTURE")

            def refresh():
                return refresh_calendar(app, provider_product_id=product.provider_product_id, code_sha="a" * 40,
                    provider=provider, worker_id="calendar-fixture", before_action=guard, expires_at=expires_at)

            if mode == "resume_normalization":
                with pytest.raises(RuntimeStateConflictError, match="FIXTURE_STOP"):
                    refresh()
            result = refresh()
            run_id = result["run_id"]
            trace = app.runtime.inspect_run(run_id)
            if mode == "provider_failure":
                assert trace.run_state == "FAILED"
                assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
            else:
                assert trace.run_state == "SUCCEEDED"
                assert all(step.attempt_states == ("SUCCEEDED",) for step in trace.steps)
                assert result["coverage"]["state"] == ("SOURCE_GAP" if mode == "missing" else "VERIFIED")
                assert len(result["coverage"]["session_ids"]) == (0 if mode == "missing" else 3)
            with app._pool.connection(read_only=True) as connection:
                before = connection.execute("SELECT (SELECT count(*) FROM mra.data_capture), (SELECT count(*) FROM mra.command_receipt), (SELECT count(*) FROM mra.runtime_attempt)").fetchone()
                receipts = connection.execute("SELECT command_kind,status,fence_token FROM mra.command_receipt WHERE runtime_step_id IN (SELECT step_id FROM mra.runtime_step WHERE run_id=%s) ORDER BY command_kind", (run_id,)).fetchall()
            repeated = refresh()
            assert repeated["state"] in {"NOT_DUE", "OBSERVATION_RECORDED", "BLOCKED"}
            with app._pool.connection(read_only=True) as connection:
                after = connection.execute("SELECT (SELECT count(*) FROM mra.data_capture), (SELECT count(*) FROM mra.command_receipt), (SELECT count(*) FROM mra.runtime_attempt)").fetchone()
            assert before == after
            assert len(provider.calls) == 1
            assert receipts and all(row[2] == 1 for row in receipts)
            assert any(row[0] == "CAPTURE_MARKET_DATA" for row in receipts)


def test_initial_legacy_calendar_capture_is_verified_without_second_observation(target_database_url, tmp_path):
    from market_regime_alpha.interfaces.calendar_continuity import CalendarRefreshPlan
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        product = _product(app)
        now = app.daily_prediction_reads.now()
        from zoneinfo import ZoneInfo
        plan = CalendarRefreshPlan(product.provider_product_id, now, now.astimezone(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=2), "a" * 40)
        provider = CalendarProvider()
        captured = app.market.capture(CaptureRequest(product.provider_product_id, "calendar-continuity:initial-legacy", plan.query.resource,
            canonical_json_sha256({"headers": {}})), provider, _context("legacy-calendar-capture"))
        app.market.normalize(captured.capture.capture_id, BaoStockArchiveNormalizer(plan.query), _context("legacy-calendar-normalize"))
        coverage = app.calendar_continuity_reads.calendar_coverage(product.provider_product_id, app.daily_prediction_reads.now())
        assert coverage["state"] == "VERIFIED" and coverage["normalizer"] == "market.baostock_archive:2"
        assert len(coverage["session_ids"]) == 3
        assert coverage["business_writes"] == 0
        assert len(provider.calls) == 1
