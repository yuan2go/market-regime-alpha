"""Synthetic future Session, real disposable owner Capture/Runtime receipts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest

from market_regime_alpha.infrastructure.postgres.archive_uow import PostgresArchiveUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.market_uow import PostgresMarketDatabaseClock
from market_regime_alpha.infrastructure.postgres.queries.archive_acquisition_readiness import PostgresArchiveAcquisitionReadinessReads
from market_regime_alpha.infrastructure.postgres.queries.archive_inspection import PostgresArchiveInspectionPort
from market_regime_alpha.infrastructure.postgres.queries.archive_operations import PostgresArchiveOperationsReadPort
from market_regime_alpha.infrastructure.postgres.queries.archive_sessions import PostgresArchiveTradingSessionReadPort
from market_regime_alpha.infrastructure.providers.baostock_acquisition_readiness import BaoStockProspectiveAcquisitionNormalizer
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockArchiveNormalizer, BaoStockProspectiveNormalizer
from market_regime_alpha.market.application import ArchiveCommands
from market_regime_alpha.market.application.archive_operations import ArchiveSliceExecutionRequest, MarketArchiveOperations
from market_regime_alpha.market.domain import ArchiveLane
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.runtime.errors import StaleFenceError
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from tests.contracts.market.test_archive_postgres import _request
from tests.contracts.market.test_baostock_acquisition_readiness import FIELDS
from tests.contracts.market.test_baostock_archive_normalizer import _payload
from tests.contracts.market.test_runtime_vertical_slice import (
    CountingResponseProvider, _capture_step, _context, _schedule_run,
    runtime_market_stack,  # noqa: F401
)


def _fixture(stack, *, mature=False, corrupt=False):
    runtime, artifacts, market, store, pool, product, _ = stack
    day = datetime.now(UTC).date() + timedelta(days=-1 if mature else 1)
    calendar = BaoStockArchiveQuery(BaoStockArchiveQueryKind.TRADE_DATES, day, day)
    calendar_source = market.capture(CaptureRequest(product.provider_product_id, "fixture-calendar", calendar.resource, ContentHash("0"*64)),
        CountingResponseProvider(_payload(calendar, ["calendar_date", "is_trading_day"], [[day.isoformat(), "1"]])), _context("calendar", "SYNTHETIC_CALENDAR"))
    market.normalize(calendar_source.capture.capture_id, BaoStockArchiveNormalizer(expected_query=calendar), _context("calendar-normalize", "SYNTHETIC_CALENDAR"))
    master = BaoStockArchiveQuery(BaoStockArchiveQueryKind.STOCK_BASIC, code="sh.600000")
    master_source = market.capture(CaptureRequest(product.provider_product_id, "fixture-master", master.resource, ContentHash("0"*64)),
        CountingResponseProvider(_payload(master, ["code", "code_name", "ipoDate", "outDate", "type", "status"],
            [["sh.600000", "Synthetic", "1999-01-01", "", "1", "1"]])), _context("master", "SYNTHETIC_MASTER"))
    market.normalize(master_source.capture.capture_id, BaoStockArchiveNormalizer(expected_query=master), _context("master-normalize", "SYNTHETIC_MASTER"))
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.HISTORY_5M_RAW, day, day, "sh.600000")
    capture = CaptureRequest(product.provider_product_id, "fixture-preopen", query.resource, ContentHash(canonical_json_sha256({"headers": {}})))
    code = artifacts.publish(b"readiness fixture code", media_type="text/plain", context=_context("code", "FIXTURE_CODE"))
    config = artifacts.publish(b"readiness fixture config", media_type="text/plain", context=_context("config", "FIXTURE_CONFIG"))
    now = PostgresMarketDatabaseClock(pool).now()
    start, end = now+timedelta(seconds=1), now+timedelta(seconds=60)
    root = _request(product, code, config)
    root = replace(root, lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS, event_window_start=start, event_window_end=end,
        slices=(replace(root.slices[0], request_sha256=canonical_json_sha256(capture), event_window_start=start, event_window_end=end),))
    archives = ArchiveCommands(PostgresArchiveUnitOfWorkProvider(pool), id_factory=uuid4)
    archives.start(root, _context("archive", "START_ARCHIVE"))
    execution = ArchiveSliceExecutionRequest(root.market_archive_id, root.slices[0].market_archive_slice_id, capture, "OUTCOME_PRE_OPEN")
    run_id, _ = _schedule_run(runtime, artifacts, (replace(_capture_step(max_attempts=1), request_hash=canonical_json_sha256(execution)),))
    claim = runtime.claim_next(run_id=run_id, worker_id="readiness-fixture", lease_duration=timedelta(seconds=30), context=_context("claim", "CLAIM_CAPTURE"))
    runtime.start_attempt(claim, _context("start", "START_CAPTURE"))
    sleep(max(0, (start-PostgresMarketDatabaseClock(pool).now()).total_seconds()))
    normalizer = BaoStockProspectiveAcquisitionNormalizer(expected_query=query, trading_sessions=PostgresArchiveTradingSessionReadPort(pool))
    operations = MarketArchiveOperations(market, archives, PostgresArchiveOperationsReadPort(pool), SimpleNamespace(available_bytes=lambda: 10**12), PostgresMarketDatabaseClock(pool), byte_store=store)
    prefix = f"archive:{root.market_archive_id}:runtime:{root.slices[0].market_archive_slice_id}"
    return SimpleNamespace(runtime=runtime, market=market, store=store, pool=pool, root=root, run_id=run_id, claim=claim,
        execution=execution, operations=operations, normalizer=normalizer,
        provider=CountingResponseProvider(_payload(query, FIELDS, [["corrupt"]] if corrupt else [])), context=_context(prefix, "SYNTHETIC_ARCHIVE"))


def _facts(fixture):
    with fixture.pool.connection(read_only=True) as connection:
        return {name: connection.execute(f"SELECT to_jsonb(r) FROM mra.{name} r ORDER BY to_jsonb(r)::text").fetchall()
            for name in ("runtime_run", "runtime_step", "runtime_attempt", "command_receipt", "data_capture", "source_gap", "market_archive_capture_observation")}


def test_no_mature_capture_closes_original_fence_once_and_readonly_report(runtime_market_stack):  # noqa: F811
    f = _fixture(runtime_market_stack)
    before_report = PostgresArchiveInspectionPort(f.pool).inspect(f.root.market_archive_id)
    result = f.operations.execute_slice(f.execution, provider=f.provider, normalizer=f.normalizer, context=f.context, runtime_claim=f.claim)
    assert result.status == "NO_MATURE_INTERVAL" and result.acquisition_readiness.state == "NO_MATURE_INTERVAL"
    assert f.provider.calls == 1
    trace = f.runtime.inspect_run(f.run_id)
    assert trace.run_state == "SUCCEEDED" and trace.steps[0].state == "SUCCEEDED"
    assert f.runtime.claim_next(run_id=f.run_id, worker_id="next-tick", lease_duration=timedelta(seconds=30), context=_context("next-tick", "CLAIM_CAPTURE")) is None
    facts = _facts(f)
    projection = PostgresArchiveAcquisitionReadinessReads(f.pool, f.store)
    report = projection.project(f.root.market_archive_id)
    assert len(report) == 1 and report[0]["capture_id"] == result.capture_id
    assert report[0]["raw_capture_occurred"] and report[0]["normalized_observation_count"] == 0
    assert report[0]["business_writes"] == 0
    assert report == projection.project(f.root.market_archive_id) and _facts(f) == facts
    # Existing Archive report identity remains unchanged: no qualified normalized observation.
    assert PostgresArchiveInspectionPort(f.pool).inspect(f.root.market_archive_id) == before_report
    with f.pool.connection(read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM mra.source_gap WHERE capture_id=%s", (result.capture_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM mra.command_receipt WHERE command_kind='NORMALIZE_MARKET_PIT' AND scope_id=%s", (str(result.capture_id),)).fetchone()[0] == 0
    # A stale worker cannot normalize or repeat Provider I/O on the completed fence.
    with pytest.raises(StaleFenceError):
        f.operations.execute_slice(f.execution, provider=f.provider, normalizer=f.normalizer, context=f.context, runtime_claim=f.claim)
    assert f.provider.calls == 1 and f.runtime.inspect_run(f.run_id) == trace


def test_mature_empty_capture_keeps_v3_sourcegap_and_normalized_receipt(runtime_market_stack):  # noqa: F811
    f = _fixture(runtime_market_stack, mature=True)
    result = f.operations.execute_slice(f.execution, provider=f.provider, normalizer=f.normalizer, context=f.context, runtime_claim=f.claim)
    assert result.status == "CAPTURED" and result.acquisition_readiness is None
    with f.pool.connection(read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM mra.source_gap WHERE capture_id=%s AND reason_code='NO_ROWS_RETURNED'", (result.capture_id,)).fetchone()[0] == 48
    assert f.runtime.inspect_run(f.run_id).run_state == "SUCCEEDED" and f.provider.calls == 1
    assert PostgresArchiveAcquisitionReadinessReads(f.pool, f.store).project(f.root.market_archive_id) == ()


def test_corrupt_nonempty_capture_still_terminally_rejected_under_original_v3(runtime_market_stack):  # noqa: F811
    f = _fixture(runtime_market_stack, corrupt=True)
    assert f.normalizer.contract == BaoStockProspectiveNormalizer.contract
    with pytest.raises(ValueError, match="malformed"):
        f.operations.execute_slice(f.execution, provider=f.provider, normalizer=f.normalizer, context=f.context, runtime_claim=f.claim)
    trace = f.runtime.inspect_run(f.run_id)
    assert trace.run_state == "FAILED" and trace.steps[0].latest_attempt_error_code == "NORMALIZER_OUTPUT_REJECTED"
    assert f.provider.calls == 1
    assert PostgresArchiveAcquisitionReadinessReads(f.pool, f.store).project(f.root.market_archive_id) == ()
