from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
import time
from uuid import uuid4

import psycopg
import pytest

import market_regime_alpha.infrastructure.artifacts.local as local_artifacts
from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.market import PostgresMarketQueries
from market_regime_alpha.infrastructure.postgres.repositories.runtime import (
    PostgresCommandReceiptRepository,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.domain import (
    BarTimeframe,
    GapFactKind,
    GapKind,
    GapReasonCode,
    InstrumentFactKind,
    MarketFactKind,
    NormalizationBatch,
    Provider,
    ProviderKind,
    ProviderProduct,
    PriceBasis,
    SourceAvailabilityStatus,
    SourceGap,
)
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    ProviderResponse,
    NormalizerContract,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    ArtifactIntegrityError,
    CommandContext,
    RuntimeApplication,
    StaleFenceError,
)
from market_regime_alpha.runtime.errors import (
    CommandInProgressError,
    CommandPreviouslyFailedError,
    IdempotencyKeyReusedError,
)
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepDependency,
    StepSpec,
)
from market_regime_alpha.runtime.ports import ByteVerification
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.WORKER,
        actor_id="market-runtime-test",
        reason_code=reason,
    )


class ResponseProvider:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        return ProviderResponse(
            content=self.content,
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
        )


class CountingResponseProvider(ResponseProvider):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.calls = 0

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        self.calls += 1
        return super().capture(request)


class FailureProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        raise MarketProviderError(
            "PROVIDER_TEMPORARY_FAILURE",
            "test provider failure",
        )


class MalformedTemporalProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        return ProviderResponse(
            content=b"malformed temporal response",
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=datetime(2026, 8, 28, 6, 55),
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code=None,
        )


class CoordinatedResponseProvider(ResponseProvider):
    def __init__(self, content: bytes, ready: Barrier) -> None:
        super().__init__(content)
        self._ready = ready

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        self._ready.wait(timeout=5)
        return super().capture(request)


class CoordinatedMalformedTemporalProvider:
    def __init__(self, ready: Barrier, committed: Event) -> None:
        self._ready = ready
        self._committed = committed

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        self._ready.wait(timeout=5)
        assert self._committed.wait(timeout=5)
        return ProviderResponse(
            content=b"malformed temporal response",
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=datetime(2026, 8, 28, 6, 55),
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code=None,
        )


class CoordinatedVerificationStore:
    def __init__(
        self,
        delegate: LocalArtifactStore,
        ready: Barrier,
        committed: Event,
        *,
        fail_after_commit: bool,
    ) -> None:
        self._delegate = delegate
        self._ready = ready
        self._committed = committed
        self._fail_after_commit = fail_after_commit

    def verify(self, content_sha256, *, expected_size: int) -> ByteVerification:
        self._ready.wait(timeout=5)
        if self._fail_after_commit:
            assert self._committed.wait(timeout=5)
            return ByteVerification(
                result="SIZE_MISMATCH",
                observed_exists=True,
                observed_size_bytes=expected_size + 1,
                observed_sha256=None,
            )
        return self._delegate.verify(content_sha256, expected_size=expected_size)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class GapNormalizer:
    contract = NormalizerContract(
        implementation="tests.gap_normalizer",
        version="1",
        implementation_sha256="e" * 64,
    )

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        assert content
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            gaps=(
                SourceGap(
                    gap_id=uuid4(),
                    provider_product_id=capture.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=None,
                    session_id=None,
                    gap_kind=GapKind.MISSING,
                    reason_code=GapReasonCode.NO_ROWS_RETURNED,
                    fact_kind=GapFactKind.INSTRUMENT,
                    instrument_fact_kind=None,
                    timeframe=None,
                    price_basis=None,
                    event_start=None,
                    event_end=None,
                    detail="typed empty Provider result",
                    instrument_code="600000.XSHG",
                ),
            ),
        )


class AlternateGapNormalizer(GapNormalizer):
    contract = NormalizerContract(
        implementation="tests.alternate_gap_normalizer",
        version="1",
        implementation_sha256="d" * 64,
    )


@pytest.fixture
def runtime_market_stack(target_database_url: str, tmp_path):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    store = LocalArtifactStore(tmp_path / "runtime-market-artifacts")
    runtime_uow = PostgresUnitOfWorkProvider(pool)
    runtime = RuntimeApplication(runtime_uow)
    artifacts = ArtifactApplication(store, runtime_uow)
    market = MarketApplication(
        store,
        PostgresMarketUnitOfWorkProvider(pool),
        PostgresMarketDatabaseClock(pool),
    )
    provider = Provider(
        provider_id=uuid4(),
        provider_code="baostock",
        display_name="BaoStock",
        provider_kind=ProviderKind.PUBLIC_ENDPOINT,
    )
    product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="history_k_data_plus",
        revision=1,
        payload_family="HISTORICAL_BAR",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=tuple(MarketFactKind),
        instrument_fact_kinds=tuple(InstrumentFactKind),
        bar_timeframes=tuple(BarTimeframe),
        price_bases=tuple(PriceBasis),
    )
    market.register_provider(provider, _context("provider", "REGISTER_PROVIDER"))
    market.register_provider_product(
        product,
        _context("product", "REGISTER_PROVIDER_PRODUCT"),
    )
    try:
        yield runtime, artifacts, market, store, pool, product, target_database_url
    finally:
        pool.close()


def _schedule_run(runtime, artifacts, steps, dependencies=()):
    schedule = ScheduleSpec(
        schedule_id=uuid4(),
        schedule_code=f"market-pit-{uuid4().hex[:8]}",
        revision=1,
        runtime_mode=RuntimeMode.OPERATIONAL,
        schedule_expression=None,
        timezone_name="Asia/Shanghai",
        step_catalog_hash="c" * 64,
        enabled=True,
    )
    runtime.create_schedule(
        schedule,
        _context(f"schedule-{schedule.schedule_code}", "CREATE_RUNTIME_SCHEDULE"),
    )
    config = artifacts.publish(
        b'{"slice":"market-pit-test-only"}',
        media_type="application/json",
        context=_context(f"config-{schedule.schedule_code}", "REGISTER_RUNTIME_CONFIG"),
    )
    run_id = uuid4()
    runtime.schedule_run(
        RunSpec(
            run_id=run_id,
            schedule_id=schedule.schedule_id,
            fire_key=f"run-{uuid4().hex}",
            runtime_mode=RuntimeMode.OPERATIONAL,
            requested_at=datetime.now(timezone.utc),
            decision_time=None,
            code_sha="1" * 40,
            config_artifact_id=config.artifact_id,
            config_hash=config.content_sha256,
        ),
        steps,
        dependencies,
        _context(f"plan-{run_id}", "SCHEDULE_RUNTIME_RUN"),
    )
    runtime.start_run(run_id, _context(f"start-{run_id}", "START_RUNTIME_RUN"))
    return run_id, config


def _capture_step(*, max_attempts: int = 2) -> StepSpec:
    return StepSpec(
        step_key="capture",
        step_kind="CAPTURE",
        implementation="market.capture.test_slice",
        implementation_version="1",
        ordinal=1,
        required=True,
        request_hash="d" * 64,
        input_evidence_hash=None,
        retry_policy=RetryPolicy(
            max_attempts=max_attempts,
            backoff=tuple(timedelta(0) for _ in range(max_attempts - 1)),
            retryable_codes=frozenset({"PROVIDER_TEMPORARY_FAILURE"}),
        ),
        external_effect_class=ExternalEffectClass.CONTENT_PUT,
    )


def _normalize_step() -> StepSpec:
    return StepSpec(
        step_key="normalize-pit",
        step_kind="NORMALIZE_PIT",
        implementation="market.normalize.test_slice",
        implementation_version="1",
        ordinal=2,
        required=True,
        request_hash="e" * 64,
        input_evidence_hash=None,
        retry_policy=RetryPolicy(
            max_attempts=1,
            backoff=(),
            retryable_codes=frozenset(),
        ),
        external_effect_class=ExternalEffectClass.PURE_READ,
    )


def test_target_runtime_executes_test_only_capture_to_normalize_pit_vertical_slice(
    runtime_market_stack,
) -> None:
    runtime, _, market, _, _, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(
        runtime,
        runtime_market_stack[1],
        (_capture_step(), _normalize_step()),
        (
            StepDependency(
                predecessor_key="capture",
                successor_key="normalize-pit",
                dependency_kind="REQUIRED_SUCCESS",
            ),
        ),
    )
    capture_claim = runtime.claim_next(
        worker_id="capture-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-capture", "WORKER_CLAIM"),
    )
    assert capture_claim is not None
    runtime.start_attempt(capture_claim, _context("start-capture", "WORKER_START"))
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="vertical-slice-capture",
            resource="fixture://vertical-slice",
            request_headers_hash="f" * 64,
        ),
        ResponseProvider(b'{"rows":[]}\n'),
        _context("market-capture", "CAPTURE_PROVIDER_RESPONSE"),
        runtime_claim=capture_claim,
    )

    normalize_claim = runtime.claim_next(
        worker_id="normalize-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-normalize", "WORKER_CLAIM"),
    )
    assert normalize_claim is not None
    assert normalize_claim.step_key == "normalize-pit"
    runtime.start_attempt(normalize_claim, _context("start-normalize", "WORKER_START"))
    normalized = market.normalize(
        captured.capture.capture_id,
        GapNormalizer(),
        _context("market-normalize", "NORMALIZE_MARKET_PIT"),
        runtime_claim=normalize_claim,
    )

    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "SUCCEEDED"
    assert tuple(step.state for step in trace.steps) == ("SUCCEEDED", "SUCCEEDED")
    with psycopg.connect(database_url) as connection:
        atomic_rows = connection.execute(
            """
            SELECT receipt.command_kind, receipt.fence_token,
                   audit.fence_token, attempt.state
            FROM mra.command_receipt AS receipt
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            WHERE receipt.command_kind IN ('CAPTURE_MARKET_DATA', 'NORMALIZE_MARKET_PIT')
            ORDER BY receipt.command_kind
            """
        ).fetchall()
    assert atomic_rows == [
        ("CAPTURE_MARKET_DATA", 1, 1, "SUCCEEDED"),
        ("NORMALIZE_MARKET_PIT", 1, 1, "SUCCEEDED"),
    ]

    replay_run_id, _ = _schedule_run(
        runtime,
        runtime_market_stack[1],
        (_normalize_step(),),
    )
    replay_claim = runtime.claim_next(
        worker_id="normalize-replay-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-normalize-replay", "WORKER_CLAIM"),
    )
    assert replay_claim is not None
    runtime.start_attempt(
        replay_claim,
        _context("start-normalize-replay", "WORKER_START"),
    )
    replayed = market.normalize(
        captured.capture.capture_id,
        GapNormalizer(),
        _context("market-normalize", "NORMALIZE_MARKET_PIT"),
        runtime_claim=replay_claim,
    )
    assert replayed.replayed is True
    assert replayed.decision_visible_at == normalized.decision_visible_at
    assert runtime.inspect_run(replay_run_id).run_state == "SUCCEEDED"


@pytest.mark.parametrize(
    ("failure_kind", "expected_verification"),
    (("size", "SIZE_MISMATCH"), ("dual-location", "INTEGRITY_ERROR")),
)
def test_normalization_artifact_failure_is_audited_and_terminal_atomically(
    runtime_market_stack,
    failure_kind: str,
    expected_verification: str,
) -> None:
    runtime, artifacts, market, store, _, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(
        runtime,
        artifacts,
        (_capture_step(), _normalize_step()),
        (
            StepDependency(
                predecessor_key="capture",
                successor_key="normalize-pit",
                dependency_kind="REQUIRED_SUCCESS",
            ),
        ),
    )
    capture_claim = runtime.claim_next(
        worker_id="integrity-capture-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-integrity-capture", "WORKER_CLAIM"),
    )
    assert capture_claim is not None
    runtime.start_attempt(
        capture_claim,
        _context("start-integrity-capture", "WORKER_START"),
    )
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="integrity-failure-capture",
            resource="fixture://integrity-failure",
            request_headers_hash="8" * 64,
        ),
        ResponseProvider(b"canonical source bytes"),
        _context("capture-integrity-source", "CAPTURE_PROVIDER_RESPONSE"),
        runtime_claim=capture_claim,
    )
    assert captured.artifact is not None
    normalize_claim = runtime.claim_next(
        worker_id="integrity-normalize-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-integrity-normalize", "WORKER_CLAIM"),
    )
    assert normalize_claim is not None
    runtime.start_attempt(
        normalize_claim,
        _context("start-integrity-normalize", "WORKER_START"),
    )
    if failure_kind == "dual-location":
        store.quarantine_path(captured.artifact.content_sha256).write_bytes(
            b"duplicate physical identity"
        )
    else:
        store.object_path(captured.artifact.content_sha256).write_bytes(b"corrupt")

    with pytest.raises(ArtifactIntegrityError, match="failed authoritative"):
        market.normalize(
            captured.capture.capture_id,
            GapNormalizer(),
            _context("normalize-integrity-failure", "NORMALIZE_MARKET_PIT"),
            runtime_claim=normalize_claim,
        )

    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[1].state == "FAILED"
    assert trace.steps[1].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.source_gap"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT integrity_state FROM mra.artifact WHERE artifact_id = %s",
            (captured.artifact.artifact_id,),
        ).fetchone() == ("CORRUPT",)
        assert connection.execute(
            """
            SELECT verification.result, receipt.status, audit.action
            FROM mra.artifact_verification AS verification
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = verification.command_receipt_id
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            WHERE verification.artifact_id = %s
              AND verification.result <> 'VERIFIED'
            """,
            (captured.artifact.artifact_id,),
        ).fetchone() == (
            expected_verification,
            "SUCCEEDED",
            "VERIFY_MARKET_SOURCE_ARTIFACT",
        )
        assert connection.execute(
            """
            SELECT receipt.command_kind, receipt.status, receipt.error_code,
                   attempt.state, audit.action
            FROM mra.runtime_attempt AS attempt
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = attempt.result_receipt_id
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            WHERE attempt.attempt_id = %s
            """,
            (normalize_claim.attempt_id,),
        ).fetchone() == (
            "NORMALIZE_MARKET_PIT",
            "FAILED",
            "ARTIFACT_INTEGRITY_FAILED",
            "FAILED_TERMINAL",
            "MARKET_COMMAND_FAILED",
        )


def test_capture_artifact_publish_failure_is_terminal_and_audited(
    runtime_market_stack,
) -> None:
    runtime, artifacts, market, store, _, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(),))
    claim = runtime.claim_next(
        worker_id="capture-artifact-failure-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-capture-artifact-failure", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(
        claim,
        _context("start-capture-artifact-failure", "WORKER_START"),
    )
    content = b"provider bytes whose identity is already corrupt"
    orphan = store.publish_bytes(content, media_type="application/json")
    store.object_path(orphan.content_sha256).write_bytes(b"corrupt preexisting bytes")

    with pytest.raises(ArtifactIntegrityError, match="safe Artifact identity"):
        market.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="capture-artifact-failure",
                resource="fixture://capture-artifact-failure",
                request_headers_hash="9" * 64,
            ),
            ResponseProvider(content),
            _context("capture-artifact-failure", "CAPTURE_PROVIDER_RESPONSE"),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.data_capture").fetchone() == (0,)
        assert connection.execute(
            """
            SELECT receipt.command_kind, receipt.status, attempt.error_code,
                   audit.action
            FROM mra.command_receipt AS receipt
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
            WHERE receipt.command_kind = 'CAPTURE_MARKET_DATA'
            """
        ).fetchone() == (
            "CAPTURE_MARKET_DATA",
            "FAILED",
            "ARTIFACT_PUBLISH_FAILED",
            "MARKET_COMMAND_FAILED",
        )


def test_capture_filesystem_os_error_is_typed_and_terminal(
    runtime_market_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, artifacts, market, _, _, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(),))
    claim = runtime.claim_next(
        worker_id="capture-os-error-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-capture-os-error", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(claim, _context("start-capture-os-error", "WORKER_START"))

    def fail_link(_source, _destination) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(local_artifacts.os, "link", fail_link)
    with pytest.raises(ArtifactIntegrityError, match="safe Artifact identity"):
        market.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="capture-os-error",
                resource="fixture://capture-os-error",
                request_headers_hash="2" * 64,
            ),
            ResponseProvider(b"new bytes that require object publication"),
            _context("capture-os-error", "CAPTURE_PROVIDER_RESPONSE"),
            runtime_claim=claim,
        )

    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT receipt.status, receipt.error_code, attempt.error_code
            FROM mra.runtime_attempt AS attempt
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = attempt.result_receipt_id
            WHERE attempt.attempt_id = %s
            """,
            (claim.attempt_id,),
        ).fetchone() == (
            "FAILED",
            "ARTIFACT_PUBLISH_FAILED",
            "ARTIFACT_PUBLISH_FAILED",
        )


def test_malformed_provider_temporal_output_is_terminal_before_artifact_publish(
    runtime_market_stack,
) -> None:
    runtime, artifacts, market, store, _, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(),))
    claim = runtime.claim_next(
        worker_id="malformed-provider-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-malformed-provider", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(
        claim,
        _context("start-malformed-provider", "WORKER_START"),
    )

    with pytest.raises(ValueError, match="provider_time must be timezone-aware"):
        market.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="malformed-provider-time",
                resource="fixture://malformed-provider-time",
                request_headers_hash="3" * 64,
            ),
            MalformedTemporalProvider(),
            _context("capture-malformed-provider", "CAPTURE_PROVIDER_RESPONSE"),
            runtime_claim=claim,
        )

    assert len(store.list_objects()) == 1  # only the Runtime config Artifact
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.data_capture").fetchone() == (0,)
        assert connection.execute(
            """
            SELECT receipt.status, receipt.error_code, attempt.error_code
            FROM mra.runtime_attempt AS attempt
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = attempt.result_receipt_id
            WHERE attempt.attempt_id = %s
            """,
            (claim.attempt_id,),
        ).fetchone() == (
            "FAILED",
            "PROVIDER_RESPONSE_REJECTED",
            "PROVIDER_RESPONSE_REJECTED",
        )


def test_stale_capture_worker_leaves_safe_physical_orphan_and_no_market_fact(
    runtime_market_stack,
) -> None:
    runtime, artifacts, market, store, pool, product, database_url = runtime_market_stack
    _, config = _schedule_run(runtime, artifacts, (_capture_step(),))
    stale = runtime.claim_next(
        worker_id="stale-worker",
        # Leave enough time for start_attempt() under a loaded PostgreSQL suite;
        # expiry is exercised during the deliberately slower Provider call.
        lease_duration=timedelta(seconds=1),
        context=_context("claim-stale", "WORKER_CLAIM"),
    )
    assert stale is not None
    runtime.start_attempt(stale, _context("start-stale", "WORKER_START"))

    class RecoveringProvider(ResponseProvider):
        def capture(self, request: CaptureRequest) -> ProviderResponse:
            time.sleep(1.1)
            assert runtime.recover_expired(
                actor_id="market-recovery",
                reason_code="LEASE_EXPIRED",
            ) == (stale.attempt_id,)
            return super().capture(request)

    raw = b'{"stale":"provider-result"}\n'
    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        market.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="stale-capture",
                resource="fixture://stale",
                request_headers_hash="a" * 64,
            ),
            RecoveringProvider(raw),
            _context("stale-market-capture", "CAPTURE_PROVIDER_RESPONSE"),
            runtime_claim=stale,
        )

    objects = {item.content_sha256 for item in store.list_objects()}
    assert config.content_sha256 in objects
    assert len(objects) == 2
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.data_capture").fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM mra.artifact WHERE artifact_id <> %s",
            (config.artifact_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM mra.command_receipt WHERE command_kind = 'CAPTURE_MARKET_DATA'"
        ).fetchone() == (0,)
    scan = artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(minutes=5),
        actor_id="stale-orphan-scanner",
    )
    assert scan.observed == (sha256_bytes(raw),)
    assert config.content_sha256 in scan.protected


def test_market_command_locks_runtime_fence_before_receipt_and_market_roots(
    runtime_market_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, artifacts, market, _, _, product, database_url = runtime_market_stack
    _schedule_run(runtime, artifacts, (_capture_step(),))
    claim = runtime.claim_next(
        worker_id="lock-order-worker",
        lease_duration=timedelta(seconds=10),
        context=_context("claim-lock-order", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(claim, _context("start-lock-order", "WORKER_START"))
    reached_receipt = Event()
    release_receipt = Event()
    original_start = PostgresCommandReceiptRepository.start

    def pausing_start(repository, **kwargs):
        reached_receipt.set()
        if not release_receipt.wait(timeout=10):
            raise TimeoutError("test did not release receipt insertion")
        return original_start(repository, **kwargs)

    monkeypatch.setattr(PostgresCommandReceiptRepository, "start", pausing_start)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            market.capture,
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="runtime-lock-order",
                resource="fixture://runtime-lock-order",
                request_headers_hash="9" * 64,
            ),
            ResponseProvider(b"runtime lock order"),
            _context("capture-lock-order", "CAPTURE_PROVIDER_RESPONSE"),
            runtime_claim=claim,
        )
        assert reached_receipt.wait(timeout=10)
        try:
            with psycopg.connect(database_url) as contender:
                contender.execute("SET LOCAL lock_timeout = '100ms'")
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    contender.execute(
                        "SELECT run_id FROM mra.runtime_run WHERE run_id = %s FOR UPDATE",
                        (claim.run_id,),
                    )
        finally:
            release_receipt.set()
        result = pending.result(timeout=10)

    assert result.capture.provider_product_id == product.provider_product_id


def test_provider_failure_is_typed_and_runtime_retry_can_capture_success(
    runtime_market_stack,
) -> None:
    runtime, artifacts, market, store, pool, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(),))
    claim = runtime.claim_next(
        worker_id="failure-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-failure", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(claim, _context("start-failure", "WORKER_START"))

    recorded = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="provider-failure",
            resource="fixture://failure",
            request_headers_hash="b" * 64,
        ),
        FailureProvider(),
        _context("record-provider-failure", "CAPTURE_PROVIDER_RESPONSE"),
        runtime_claim=claim,
    )

    assert recorded.capture.status.value == "PROVIDER_FAILURE"
    assert len(store.list_objects()) == 1  # only the Runtime config Artifact
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "RUNNING"
    assert trace.steps[0].state == "READY"
    assert trace.steps[0].attempt_states == ("FAILED_RETRYABLE",)
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT capture.status, capture.error_code, gap.gap_kind,
                   gap.reason_code, receipt.status, attempt.state
            FROM mra.data_capture AS capture
            JOIN mra.source_gap AS gap ON gap.capture_id = capture.capture_id
            JOIN mra.command_receipt AS receipt
              ON receipt.result_aggregate_id = capture.capture_id::text
            JOIN mra.runtime_attempt AS attempt
              ON attempt.result_receipt_id = receipt.receipt_id
            """
        ).fetchone()
    assert row == (
        "PROVIDER_FAILURE",
        "PROVIDER_TEMPORARY_FAILURE",
        "PROVIDER_FAILURE",
        "PROVIDER_FAILURE",
        "SUCCEEDED",
        "FAILED_RETRYABLE",
    )
    gaps = PostgresMarketQueries(
        pool,
        provider_product_id=product.provider_product_id,
    ).source_gaps_as_of(
        decision_time=datetime.now(timezone.utc),
        capture_id=recorded.capture.capture_id,
        fact_kind=GapFactKind.DATA_CAPTURE,
    )
    assert len(gaps) == 1
    assert gaps[0].reason_code is GapReasonCode.PROVIDER_FAILURE

    retry = runtime.claim_next(
        worker_id="failure-replay-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-failure-replay", "WORKER_CLAIM"),
    )
    assert retry is not None
    runtime.start_attempt(retry, _context("start-failure-replay", "WORKER_START"))
    succeeded = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="provider-failure",
            resource="fixture://failure",
            request_headers_hash="b" * 64,
        ),
        ResponseProvider(b'{"recovered":true}'),
        _context("record-provider-success-retry", "CAPTURE_PROVIDER_RESPONSE"),
        runtime_claim=retry,
    )
    assert succeeded.replayed is False
    assert succeeded.capture.status.value == "CAPTURED"
    replay_trace = runtime.inspect_run(run_id)
    assert replay_trace.run_state == "SUCCEEDED"
    assert replay_trace.steps[0].state == "SUCCEEDED"
    assert replay_trace.steps[0].attempt_states == (
        "FAILED_RETRYABLE",
        "SUCCEEDED",
    )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT status FROM mra.data_capture
            WHERE provider_product_id = %s AND capture_key = 'provider-failure'
            ORDER BY decision_visible_at
            """,
            (product.provider_product_id,),
        ).fetchall() == [("PROVIDER_FAILURE",), ("CAPTURED",)]


@pytest.mark.parametrize(
    ("existing_status", "different_hash", "expected_error", "expected_code"),
    (
        ("PENDING", True, IdempotencyKeyReusedError, "IDEMPOTENCY_KEY_REUSED"),
        ("PENDING", False, CommandInProgressError, "COMMAND_IN_PROGRESS"),
        ("FAILED", False, CommandPreviouslyFailedError, "EXISTING_FAILURE"),
    ),
)
def test_pre_io_idempotency_rejection_terminalizes_attempt_without_taking_over_key(
    runtime_market_stack,
    existing_status: str,
    different_hash: bool,
    expected_error: type[Exception],
    expected_code: str,
) -> None:
    runtime, artifacts, market, _, _, product, database_url = runtime_market_stack
    run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(),))
    claim = runtime.claim_next(
        worker_id="idempotency-rejection-worker",
        lease_duration=timedelta(seconds=5),
        context=_context("claim-idempotency-rejection", "WORKER_CLAIM"),
    )
    assert claim is not None
    runtime.start_attempt(
        claim,
        _context("start-idempotency-rejection", "WORKER_START"),
    )
    request = CaptureRequest(
        provider_product_id=product.provider_product_id,
        capture_key="idempotency-rejection",
        resource="fixture://idempotency-rejection",
        request_headers_hash="1" * 64,
    )
    command_context = _context(
        "occupied-market-command-key",
        "CAPTURE_PROVIDER_RESPONSE",
    )
    request_hash = canonical_json_sha256(request)
    stored_hash = "0" * 64 if different_hash else request_hash
    original_receipt_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO mra.command_receipt (
                receipt_id, command_kind, scope_id, idempotency_key,
                request_hash, status, error_code, completed_at
            )
            VALUES (%s, 'CAPTURE_MARKET_DATA', %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'FAILED' THEN clock_timestamp() ELSE NULL END)
            """,
            (
                original_receipt_id,
                str(product.provider_product_id),
                command_context.idempotency_key,
                stored_hash,
                existing_status,
                "EXISTING_FAILURE" if existing_status == "FAILED" else None,
                existing_status,
            ),
        )
    provider = CountingResponseProvider(b"provider must not be called")

    with pytest.raises(expected_error):
        market.capture(
            request,
            provider,
            command_context,
            runtime_claim=claim,
        )

    assert provider.calls == 0
    trace = runtime.inspect_run(run_id)
    assert trace.run_state == "FAILED"
    assert trace.steps[0].attempt_states == ("FAILED_TERMINAL",)
    with psycopg.connect(database_url) as connection:
        original = connection.execute(
            """
            SELECT status, request_hash, error_code
            FROM mra.command_receipt
            WHERE receipt_id = %s
            """,
            (original_receipt_id,),
        ).fetchone()
        result = connection.execute(
            """
            SELECT receipt.command_kind, receipt.status, receipt.error_code,
                   attempt.error_code
            FROM mra.runtime_attempt AS attempt
            JOIN mra.command_receipt AS receipt
              ON receipt.receipt_id = attempt.result_receipt_id
            WHERE attempt.attempt_id = %s
            """,
            (claim.attempt_id,),
        ).fetchone()
    assert original == (
        existing_status,
        stored_hash,
        "EXISTING_FAILURE" if existing_status == "FAILED" else None,
    )
    expected_receipt_kind = (
        "CAPTURE_MARKET_DATA"
        if existing_status == "FAILED"
        else "MARKET_COMMAND_REJECTION"
    )
    assert result == (
        expected_receipt_kind,
        "FAILED",
        expected_code,
        expected_code,
    )


@pytest.mark.parametrize("same_request", (True, False))
def test_post_preflight_command_race_replays_success_or_rejects_changed_request(
    runtime_market_stack,
    same_request: bool,
) -> None:
    runtime, artifacts, market, _, _, product, database_url = runtime_market_stack
    run_ids: list = []
    claims = []
    for worker in ("fast", "slow"):
        run_id, _ = _schedule_run(runtime, artifacts, (_capture_step(),))
        claim = runtime.claim_next(
            worker_id=f"{worker}-post-preflight-worker",
            lease_duration=timedelta(seconds=10),
            context=_context(f"claim-{worker}-post-preflight", "WORKER_CLAIM"),
        )
        assert claim is not None
        runtime.start_attempt(
            claim,
            _context(f"start-{worker}-post-preflight", "WORKER_START"),
        )
        run_ids.append(run_id)
        claims.append(claim)

    command_context = _context(
        "post-preflight-shared-key",
        "CAPTURE_PROVIDER_RESPONSE",
    )
    fast_request = CaptureRequest(
        provider_product_id=product.provider_product_id,
        capture_key="post-preflight-fast",
        resource="fixture://post-preflight-fast",
        request_headers_hash="1" * 64,
    )
    slow_request = (
        fast_request
        if same_request
        else CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="post-preflight-slow",
            resource="fixture://post-preflight-slow",
            request_headers_hash="2" * 64,
        )
    )
    ready = Barrier(2)
    committed = Event()

    def commit_fast():
        result = market.capture(
            fast_request,
            CoordinatedResponseProvider(b"committed canonical bytes", ready),
            command_context,
            runtime_claim=claims[0],
        )
        committed.set()
        return result

    def finish_slow():
        return market.capture(
            slow_request,
            CoordinatedMalformedTemporalProvider(ready, committed),
            command_context,
            runtime_claim=claims[1],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        fast_future = executor.submit(commit_fast)
        slow_future = executor.submit(finish_slow)
        fast_result = fast_future.result(timeout=10)
        if same_request:
            slow_result = slow_future.result(timeout=10)
            assert slow_result.replayed is True
            assert slow_result.capture.capture_id == fast_result.capture.capture_id
        else:
            with pytest.raises(IdempotencyKeyReusedError):
                slow_future.result(timeout=10)

    assert runtime.inspect_run(run_ids[0]).run_state == "SUCCEEDED"
    slow_trace = runtime.inspect_run(run_ids[1])
    assert slow_trace.run_state == ("SUCCEEDED" if same_request else "FAILED")
    assert slow_trace.steps[0].attempt_states == (
        "SUCCEEDED" if same_request else "FAILED_TERMINAL",
    )
    with psycopg.connect(database_url) as connection:
        receipts = connection.execute(
            """
            SELECT command_kind, status, request_hash
            FROM mra.command_receipt
            WHERE idempotency_key = %s
               OR idempotency_key = %s
            ORDER BY command_kind
            """,
            (
                command_context.idempotency_key,
                f"market-command-rejection:{claims[1].attempt_id}",
            ),
        ).fetchall()
    assert receipts[0][:2] == ("CAPTURE_MARKET_DATA", "SUCCEEDED")
    assert len(receipts) == (1 if same_request else 2)


@pytest.mark.parametrize("same_contract", (True, False))
def test_concurrent_normalize_success_wins_or_rejects_changed_contract(
    runtime_market_stack,
    same_contract: bool,
) -> None:
    runtime, artifacts, market, store, pool, product, database_url = runtime_market_stack
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="normalize-race-source",
            resource="fixture://normalize-race-source",
            request_headers_hash="3" * 64,
        ),
        ResponseProvider(b'{"rows":[]}'),
        _context("normalize-race-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    assert captured.artifact is not None

    run_ids: list = []
    claims = []
    for worker in ("fast", "slow"):
        run_id, _ = _schedule_run(runtime, artifacts, (_normalize_step(),))
        claim = runtime.claim_next(
            worker_id=f"{worker}-normalize-race-worker",
            lease_duration=timedelta(seconds=10),
            context=_context(f"claim-{worker}-normalize-race", "WORKER_CLAIM"),
        )
        assert claim is not None
        runtime.start_attempt(
            claim,
            _context(f"start-{worker}-normalize-race", "WORKER_START"),
        )
        run_ids.append(run_id)
        claims.append(claim)

    ready = Barrier(2)
    committed = Event()
    uow_provider = PostgresMarketUnitOfWorkProvider(pool)
    clock = PostgresMarketDatabaseClock(pool)
    fast_market = MarketApplication(
        CoordinatedVerificationStore(
            store,
            ready,
            committed,
            fail_after_commit=False,
        ),
        uow_provider,
        clock,
    )
    slow_market = MarketApplication(
        CoordinatedVerificationStore(
            store,
            ready,
            committed,
            fail_after_commit=True,
        ),
        uow_provider,
        clock,
    )
    command_context = _context("normalize-race-key", "NORMALIZE_MARKET_PIT")

    def commit_fast():
        result = fast_market.normalize(
            captured.capture.capture_id,
            GapNormalizer(),
            command_context,
            runtime_claim=claims[0],
        )
        committed.set()
        return result

    def finish_slow():
        return slow_market.normalize(
            captured.capture.capture_id,
            GapNormalizer() if same_contract else AlternateGapNormalizer(),
            command_context,
            runtime_claim=claims[1],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        fast_future = executor.submit(commit_fast)
        slow_future = executor.submit(finish_slow)
        fast_result = fast_future.result(timeout=10)
        if same_contract:
            slow_result = slow_future.result(timeout=10)
            assert slow_result.replayed is True
            assert slow_result.result_hash == fast_result.result_hash
        else:
            with pytest.raises(IdempotencyKeyReusedError):
                slow_future.result(timeout=10)

    assert fast_result.replayed is False
    assert tuple(runtime.inspect_run(run_id).run_state for run_id in run_ids) == (
        "SUCCEEDED",
        "SUCCEEDED" if same_contract else "FAILED",
    )
    with psycopg.connect(database_url) as connection:
        artifact_state = connection.execute(
            "SELECT integrity_state FROM mra.artifact WHERE artifact_id = %s",
            (captured.artifact.artifact_id,),
        ).fetchone()
        command_receipts = connection.execute(
            """
            SELECT count(*)
            FROM mra.command_receipt
            WHERE command_kind = 'NORMALIZE_MARKET_PIT'
              AND scope_id = %s
              AND idempotency_key = %s
            """,
            (str(captured.capture.capture_id), command_context.idempotency_key),
        ).fetchone()
    assert artifact_state == ("CORRUPT",)
    assert command_receipts == (1,)


def test_direct_normalize_collision_keeps_artifact_failure_observation(
    runtime_market_stack,
) -> None:
    _, _, market, store, pool, product, database_url = runtime_market_stack
    captured = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="direct-normalize-race-source",
            resource="fixture://direct-normalize-race-source",
            request_headers_hash="4" * 64,
        ),
        ResponseProvider(b'{"rows":[]}'),
        _context("direct-normalize-race-capture", "CAPTURE_PROVIDER_RESPONSE"),
    )
    assert captured.artifact is not None
    ready = Barrier(2)
    committed = Event()
    uow_provider = PostgresMarketUnitOfWorkProvider(pool)
    clock = PostgresMarketDatabaseClock(pool)
    fast_market = MarketApplication(
        CoordinatedVerificationStore(
            store,
            ready,
            committed,
            fail_after_commit=False,
        ),
        uow_provider,
        clock,
    )
    slow_market = MarketApplication(
        CoordinatedVerificationStore(
            store,
            ready,
            committed,
            fail_after_commit=True,
        ),
        uow_provider,
        clock,
    )
    context = _context("direct-normalize-race-key", "NORMALIZE_MARKET_PIT")

    def commit_fast():
        result = fast_market.normalize(
            captured.capture.capture_id,
            GapNormalizer(),
            context,
        )
        committed.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        fast_future = executor.submit(commit_fast)
        slow_future = executor.submit(
            slow_market.normalize,
            captured.capture.capture_id,
            AlternateGapNormalizer(),
            context,
        )
        assert fast_future.result(timeout=10).replayed is False
        with pytest.raises(IdempotencyKeyReusedError):
            slow_future.result(timeout=10)

    with psycopg.connect(database_url) as connection:
        state_and_failure = connection.execute(
            """
            SELECT artifact.integrity_state, verification.result
            FROM mra.artifact AS artifact
            JOIN mra.artifact_verification AS verification
              ON verification.artifact_id = artifact.artifact_id
            WHERE artifact.artifact_id = %s
              AND verification.verification_policy =
                  'MARKET_NORMALIZATION_SOURCE_READ'
              AND verification.result <> 'VERIFIED'
            """,
            (captured.artifact.artifact_id,),
        ).fetchone()
    assert state_and_failure == ("CORRUPT", "SIZE_MISMATCH")
