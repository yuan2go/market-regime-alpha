"""Disposable PostgreSQL owner receipts prove a known failed external effect."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.postgres.archive_uow import PostgresArchiveUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.queries.archive_operations import PostgresArchiveOperationsReadPort
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery, BaoStockArchiveQueryKind
from market_regime_alpha.infrastructure.providers.baostock_archive_normalizer import BaoStockProspectiveNormalizer
from market_regime_alpha.market.application import ArchiveCommands
from market_regime_alpha.market.ports import ArchiveTradingSession, CaptureRequest
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash, TradingSessionId
from tests.contracts.market.test_archive_postgres import _request
from tests.contracts.market.test_runtime_vertical_slice import (
    CountingResponseProvider, _capture_step, _context, _schedule_run,
    runtime_market_stack,  # noqa: F401
)


def test_terminal_reconciliation_uses_real_market_failure_receipt_and_zero_writes(runtime_market_stack):  # noqa: F811
    runtime, artifacts, market, store, pool, product, database_url = runtime_market_stack
    now = datetime.now(UTC)
    query = BaoStockArchiveQuery(BaoStockArchiveQueryKind.HISTORY_5M_RAW,
                                 code="sh.600000", start_date=now.date(), end_date=now.date())
    capture_request = CaptureRequest(product.provider_product_id, "preopen-empty/0001", query.resource, ContentHash("a" * 64))
    code = artifacts.publish(b"reconciliation fixture code", media_type="text/plain", context=_context("code", "FIXTURE_CODE"))
    config = artifacts.publish(b"reconciliation fixture config", media_type="text/plain", context=_context("config", "FIXTURE_CONFIG"))
    root = _request(product, code, config)
    root = replace(root, event_window_start=now-timedelta(hours=1), event_window_end=now+timedelta(hours=1),
        slices=(replace(root.slices[0], request_sha256=canonical_json_sha256(capture_request),
                        event_window_start=now-timedelta(minutes=1), event_window_end=now+timedelta(minutes=1)),))
    ArchiveCommands(PostgresArchiveUnitOfWorkProvider(pool), id_factory=uuid4).start(root, _context("archive", "START_ARCHIVE"))
    run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(max_attempts=1),))
    claim = runtime.claim_next(run_id=run_id, worker_id="terminal-proof", lease_duration=timedelta(seconds=30),
                               context=_context("claim", "CLAIM_CAPTURE"))
    runtime.start_attempt(claim, _context("start", "START_CAPTURE"))
    payload = {"error_code": "0", "error_message": "success", "query": json.loads(query.resource), "rows": [],
               "fields": ["date", "time", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]}
    content = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    provider = CountingResponseProvider(content)
    prefix = f"archive:{root.market_archive_id}:runtime:{root.slices[0].market_archive_slice_id}"
    capture = market.capture(capture_request, provider, _context(f"{prefix}:capture", "CAPTURE_ARCHIVE"),
                             runtime_claim=claim, complete_runtime_attempt=False)
    session = ArchiveTradingSession(TradingSessionId(uuid4()), "XSHG", now.date(), now+timedelta(hours=1),
        now+timedelta(hours=3), now+timedelta(hours=4), now+timedelta(hours=6))
    normalizer = BaoStockProspectiveNormalizer(expected_query=query,
        trading_sessions=SimpleNamespace(sessions=lambda **_: (session,)))
    with pytest.raises(ValueError, match="normalization must record"):
        market.normalize(capture.capture.capture_id, normalizer, _context(f"{prefix}:normalize", "NORMALIZE_ARCHIVE"),
                         runtime_claim=claim, complete_runtime_attempt=False)
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].latest_attempt_error_code == "NORMALIZER_OUTPUT_REJECTED"

    def facts():
        with psycopg.connect(database_url) as connection:
            return {table: connection.execute(f"SELECT to_jsonb(r) FROM mra.{table} AS r ORDER BY to_jsonb(r)::text").fetchall()
                for table in ("runtime_run", "runtime_step", "runtime_attempt", "command_receipt", "audit_event",
                              "artifact", "artifact_verification", "data_capture", "source_gap", "market_archive_capture_observation")}

    before = facts()
    reader = PostgresArchiveOperationsReadPort(pool)
    arguments = dict(run_id=run_id, step_id=claim.step_id, market_archive_id=root.market_archive_id,
                     market_archive_slice_id=root.slices[0].market_archive_slice_id, fence_token=claim.fence_token)
    first = reader.terminal_normalizer_failure(**arguments)
    assert first is not None and first.capture == capture.capture and first.artifact == capture.artifact
    assert first == reader.terminal_normalizer_failure(**arguments)
    for field, wrong in (("run_id", uuid4()), ("step_id", uuid4()), ("market_archive_id", uuid4()),
                         ("market_archive_slice_id", uuid4()), ("fence_token", claim.fence_token+1)):
        assert reader.terminal_normalizer_failure(**{**arguments, field: wrong}) is None
    assert facts() == before
    assert runtime.inspect_run(run_id) == trace and provider.calls == 1
    assert store.read_bytes(ContentHash(first.artifact.content_sha256), expected_size=first.artifact.size_bytes) == content
