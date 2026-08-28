from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.domain import (
    GapKind,
    NormalizationBatch,
    Provider,
    ProviderProduct,
    SourceAvailabilityStatus,
    SourceGap,
)
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    ProviderResponse,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
    StaleFenceError,
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
from market_regime_alpha.shared.hashing import sha256_bytes


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


class FailureProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        raise MarketProviderError(
            "PROVIDER_TEMPORARY_FAILURE",
            "test provider failure",
            retryable=True,
        )


class GapNormalizer:
    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        assert content
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            gaps=(
                SourceGap(
                    gap_id=uuid4(),
                    provider_product_id=capture.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=None,
                    session_id=None,
                    gap_kind=GapKind.MISSING,
                    reason_code="NO_ROWS_RETURNED",
                    fact_kind="MARKET_DATASET",
                    timeframe=None,
                    adjustment_basis=None,
                    event_start=None,
                    event_end=None,
                    detail="typed empty Provider result",
                ),
            ),
        )


@pytest.fixture
def runtime_market_stack(target_database_url: str, tmp_path):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    store = LocalArtifactStore(tmp_path / "runtime-market-artifacts")
    runtime_uow = PostgresUnitOfWorkProvider(pool)
    runtime = RuntimeApplication(runtime_uow)
    artifacts = ArtifactApplication(store, runtime_uow)
    market = MarketApplication(store, PostgresMarketUnitOfWorkProvider(pool))
    provider = Provider(
        provider_id=uuid4(),
        provider_code="baostock",
        display_name="BaoStock",
        provider_kind="PUBLIC_ENDPOINT",
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
        contract_sha256="a" * 64,
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
    market.normalize(
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


def test_stale_capture_worker_leaves_safe_physical_orphan_and_no_market_fact(
    runtime_market_stack,
) -> None:
    runtime, artifacts, market, store, _, product, database_url = runtime_market_stack
    _, config = _schedule_run(runtime, artifacts, (_capture_step(),))
    stale = runtime.claim_next(
        worker_id="stale-worker",
        lease_duration=timedelta(milliseconds=20),
        context=_context("claim-stale", "WORKER_CLAIM"),
    )
    assert stale is not None
    runtime.start_attempt(stale, _context("start-stale", "WORKER_START"))
    time.sleep(0.05)
    assert runtime.recover_expired(
        actor_id="market-recovery",
        reason_code="LEASE_EXPIRED",
    ) == (stale.attempt_id,)

    raw = b'{"stale":"provider-result"}\n'
    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        market.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="stale-capture",
                resource="fixture://stale",
                request_headers_hash="a" * 64,
            ),
            ResponseProvider(raw),
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


def test_provider_failure_is_typed_and_runtime_retry_state_is_atomic(
    runtime_market_stack,
) -> None:
    runtime, artifacts, market, store, _, product, database_url = runtime_market_stack
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
        "PROVIDER_TEMPORARY_FAILURE",
        "SUCCEEDED",
        "FAILED_RETRYABLE",
    )
