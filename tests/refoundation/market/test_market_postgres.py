from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.market import PostgresMarketQueries
from market_regime_alpha.infrastructure.postgres.repositories.artifacts import (
    PostgresArtifactRepository,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.domain import (
    BarTimeframe,
    CaptureStatus,
    ClassificationEvidenceStatus,
    ClassificationMembershipRevision,
    ClassificationRevision,
    CorporateActionRevision,
    CorporateActionType,
    GapFactKind,
    GapKind,
    GapReasonCode,
    EvidenceScope,
    Instrument,
    InstrumentFactKind,
    InstrumentFactRevision,
    InstrumentLifecycleFactRevision,
    InstrumentIdentifier,
    InstrumentType,
    MarketFactKind,
    MarketBarRevision,
    MarketEvidenceGapError,
    NormalizationBatch,
    NumericInstrumentFactKind,
    Provider,
    ProviderKind,
    ProviderProduct,
    PriceBasis,
    SecurityStatus,
    SecurityStatusFactRevision,
    MembershipStatus,
    ListingStatus,
    SourceAvailabilityStatus,
    SourceGap,
    SpecialTreatmentStatus,
    TradingSession,
)
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    NormalizerContract,
    ProviderResponse,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    IdempotencyKeyReusedError,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime


UTC = timezone.utc


def _cny(value: str) -> Money:
    return Money(Decimal(value), "CNY")


def _shares(value: str) -> Quantity:
    return Quantity(Decimal(value), QuantityUnit.SHARES)


def _context(key: str, reason: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="market-pit-test",
        reason_code=reason,
    )


class ExactBytesProvider:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls = 0

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(
            content=self.content,
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
        )


class AlwaysFailingProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        raise MarketProviderError("PROVIDER_UNAVAILABLE", "provider is unavailable")


class FixedNormalizer:
    contract = NormalizerContract(
        implementation="tests.fixed_normalizer",
        version="1",
        implementation_sha256="f" * 64,
    )

    def __init__(self, batch_factory) -> None:
        self._batch_factory = batch_factory
        self.seen_content: bytes | None = None

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        self.seen_content = content
        return self._batch_factory(capture)


class BarrierNormalizer(FixedNormalizer):
    def __init__(self, barrier: Barrier, batch_factory) -> None:
        super().__init__(batch_factory)
        self._barrier = barrier

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        batch = super().normalize(capture, content)
        self._barrier.wait(timeout=10)
        return batch


class PausingExactBarQueries(PostgresMarketQueries):
    def __init__(self, *args, after_session: Event, resume: Event, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._after_session = after_session
        self._resume = resume

    def exact_bar_as_of(self, **kwargs):
        bar = super().exact_bar_as_of(**kwargs)
        self._after_session.set()
        if not self._resume.wait(timeout=10):
            raise TimeoutError("test did not release the exact-bar query")
        return bar


@pytest.fixture
def market_stack(target_database_url: str, tmp_path):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    store = LocalArtifactStore(tmp_path / "market-artifacts")
    uow_provider = PostgresMarketUnitOfWorkProvider(pool)
    application = MarketApplication(
        store,
        uow_provider,
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
    application.register_provider(provider, _context("provider-1", "REGISTER_PROVIDER"))
    application.register_provider_product(
        product,
        _context("product-1", "REGISTER_PROVIDER_PRODUCT"),
    )
    queries = PostgresMarketQueries(pool, provider_product_id=product.provider_product_id)
    try:
        yield application, queries, store, pool, provider, product, target_database_url
    finally:
        pool.close()


def _capture(
    application: MarketApplication,
    product: ProviderProduct,
    key: str,
    content: bytes,
    *,
    expected_provider_calls: int = 1,
):
    provider = ExactBytesProvider(content)
    result = application.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key=key,
            resource=f"fixture://{key}",
            request_headers_hash="b" * 64,
        ),
        provider,
        _context(f"capture-{key}", "CAPTURE_PROVIDER_RESPONSE"),
    )
    assert provider.calls == expected_provider_calls
    return result


def _session(
    *,
    session_id,
    session_date: date,
    capture_id,
) -> TradingSession:
    end = datetime.combine(session_date, datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=6,
        minutes=55,
    )
    return TradingSession(
        session_id=session_id,
        exchange="XSHG",
        session_date=session_date,
        timezone_name="Asia/Shanghai",
        open_at=end - timedelta(hours=5, minutes=25),
        break_start_at=end - timedelta(hours=3, minutes=25),
        break_end_at=end - timedelta(hours=1, minutes=55),
        close_at=end + timedelta(minutes=5),
        decision_reference_at=end,
        source_capture_id=capture_id,
    )


def test_repeated_identical_reference_capture_reconciles_without_replacing_first_source(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    session_id = uuid4()
    session_date = date(2026, 1, 5)
    first = _capture(application, product, "reference-repeat-first", b'{"calendar":"same"}\n')
    second = _capture(application, product, "reference-repeat-second", b'{"calendar":"same"}\n')

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            trading_sessions=(
                _session(
                    session_id=session_id,
                    session_date=session_date,
                    capture_id=capture.capture_id,
                ),
            ),
        )

    application.normalize(
        first.capture.capture_id,
        FixedNormalizer(batch),
        _context("reference-repeat-normalize-first", "NORMALIZE_MARKET_PIT"),
    )
    normalized = application.normalize(
        second.capture.capture_id,
        FixedNormalizer(batch),
        _context("reference-repeat-normalize-second", "NORMALIZE_MARKET_PIT"),
    )
    replayed = application.normalize(
        second.capture.capture_id,
        FixedNormalizer(batch),
        _context("reference-repeat-normalize-second", "NORMALIZE_MARKET_PIT"),
    )

    assert normalized.replayed is False
    assert replayed.replayed is True
    assert replayed.decision_visible_at == normalized.decision_visible_at
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*), max(source_capture_id::text) FROM mra.trading_session WHERE session_id = %s",
            (session_id,),
        ).fetchone() == (1, str(first.capture.capture_id))
        assert connection.execute(
            """
            SELECT count(*) FROM mra.command_receipt
            WHERE command_kind = 'NORMALIZE_MARKET_PIT'
              AND scope_id IN (%s, %s)
              AND status = 'SUCCEEDED'
            """,
            (str(first.capture.capture_id), str(second.capture.capture_id)),
        ).fetchone() == (2,)
        disposition = connection.execute(
            """
            SELECT normalized_revision_count,
                   normalized_revision_roster_sha256
            FROM mra.market_capture_normalized_roster(%s)
            """,
            (second.capture.capture_id,),
        ).fetchone()
        assert disposition is not None
        assert disposition[0] == 1
        assert len(disposition[1]) == 64


def test_repeated_reference_capture_with_changed_business_fields_fails_closed(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    session_id = uuid4()
    session_date = date(2026, 1, 5)
    first = _capture(application, product, "reference-change-first", b'{"calendar":1}\n')
    changed = _capture(application, product, "reference-change-second", b'{"calendar":2}\n')
    canonical = _session(
        session_id=session_id,
        session_date=session_date,
        capture_id=first.capture.capture_id,
    )
    application.normalize(
        first.capture.capture_id,
        FixedNormalizer(
            lambda capture: NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                trading_sessions=(canonical,),
            )
        ),
        _context("reference-change-normalize-first", "NORMALIZE_MARKET_PIT"),
    )

    with pytest.raises(RuntimeStateConflictError):
        application.normalize(
            changed.capture.capture_id,
            FixedNormalizer(
                lambda capture: NormalizationBatch(
                    source_capture_id=capture.capture_id,
                    source_provider_product_id=capture.provider_product_id,
                    trading_sessions=(
                        TradingSession(
                            session_id=canonical.session_id,
                            exchange=canonical.exchange,
                            session_date=canonical.session_date,
                            timezone_name=canonical.timezone_name,
                            open_at=canonical.open_at,
                            break_start_at=canonical.break_start_at,
                            break_end_at=canonical.break_end_at,
                            close_at=canonical.close_at + timedelta(minutes=1),
                            decision_reference_at=canonical.decision_reference_at,
                            source_capture_id=capture.capture_id,
                        ),
                    ),
                )
            ),
            _context("reference-change-normalize-second", "NORMALIZE_MARKET_PIT"),
        )

    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*), max(close_at) FROM mra.trading_session WHERE session_id = %s",
            (session_id,),
        ).fetchone() == (1, canonical.close_at)


def test_concurrent_identical_reference_captures_converge_on_one_authority(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    first = _capture(application, product, "reference-race-first", b'{"calendar":"race"}\n')
    second = _capture(application, product, "reference-race-second", b'{"calendar":"race"}\n')
    session_id = uuid4()
    session_date = date(2026, 1, 5)
    barrier = Barrier(2)

    def normalize(captured, suffix: str):
        return application.normalize(
            captured.capture.capture_id,
            BarrierNormalizer(
                barrier,
                lambda capture: NormalizationBatch(
                    source_capture_id=capture.capture_id,
                    source_provider_product_id=capture.provider_product_id,
                    trading_sessions=(
                        _session(
                            session_id=session_id,
                            session_date=session_date,
                            capture_id=capture.capture_id,
                        ),
                    ),
                ),
            ),
            _context(f"reference-race-normalize-{suffix}", "NORMALIZE_MARKET_PIT"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            future.result(timeout=20)
            for future in (
                executor.submit(normalize, first, "first"),
                executor.submit(normalize, second, "second"),
            )
        )

    assert all(result.replayed is False for result in results)
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.trading_session WHERE session_id = %s",
            (session_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT count(*) FROM mra.command_receipt
            WHERE command_kind = 'NORMALIZE_MARKET_PIT'
              AND scope_id IN (%s, %s)
              AND status = 'SUCCEEDED'
            """,
            (str(first.capture.capture_id), str(second.capture.capture_id)),
        ).fetchone() == (2,)


def test_capture_binds_exact_artifact_temporal_axes_receipt_and_audit_atomically(
    market_stack,
) -> None:
    application, _, store, _, _, product, database_url = market_stack
    exact = b'{"code":"sh.601919","close":"15.32"}\n'

    result = _capture(application, product, "2026-08-28-1455", exact)
    replayed = _capture(
        application,
        product,
        "2026-08-28-1455",
        exact,
        expected_provider_calls=0,
    )

    assert result.replayed is False
    assert replayed.replayed is True
    assert replayed.capture.capture_id == result.capture.capture_id
    assert result.artifact is not None
    assert result.capture.temporal.source_available_at is None
    assert (
        result.capture.temporal.decision_visible_at.value
        == result.capture.temporal.known_at.value
    )
    assert store.read_bytes(
        result.artifact.content_sha256,
        expected_size=result.artifact.size_bytes,
    ) == exact

    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT capture.status, capture.source_availability_status,
                   capture.source_available_at, capture.capture_completed_at,
                   capture.recorded_at, capture.known_at,
                   capture.decision_visible_at, artifact.content_sha256,
                   artifact.integrity_state
            FROM mra.data_capture AS capture
            JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
            WHERE capture.capture_id = %s
            """,
            (result.capture.capture_id,),
        ).fetchone()
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.data_capture),
                (SELECT count(*) FROM mra.command_receipt WHERE command_kind = 'CAPTURE_MARKET_DATA'),
                (SELECT count(*) FROM mra.audit_event WHERE action = 'CAPTURE_MARKET_DATA')
            """
        ).fetchone()
    assert row is not None
    assert row[:3] == ("CAPTURED", "UNKNOWN", None)
    assert row[3] == result.capture.temporal.capture_completed_at
    assert row[5] == max(row[3], row[4])
    assert row[5] == row[6] == result.capture.temporal.known_at.value
    assert row[7:] == (result.artifact.content_sha256, "AVAILABLE")
    assert counts == (1, 1, 1)


def test_capture_idempotency_rejects_changed_request_and_leaves_new_bytes_unbound(
    market_stack,
) -> None:
    application, _, store, _, _, product, database_url = market_stack
    context = _context("same-capture-command", "CAPTURE_PROVIDER_RESPONSE")
    original = application.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="stable-capture",
            resource="fixture://original",
            request_headers_hash="b" * 64,
        ),
        ExactBytesProvider(b"original"),
        context,
    )
    with pytest.raises(IdempotencyKeyReusedError, match="IDEMPOTENCY_KEY_REUSED"):
        application.capture(
            CaptureRequest(
                provider_product_id=product.provider_product_id,
                capture_key="stable-capture",
                resource="fixture://changed",
                request_headers_hash="b" * 64,
            ),
            ExactBytesProvider(b"changed"),
            context,
        )

    assert original.artifact is not None
    assert len(store.list_objects()) == 1
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.data_capture").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM mra.artifact").fetchone() == (1,)


def test_exact_republish_refreshes_stale_existing_artifact_verification(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    content = b"same immutable provider bytes"
    first = _capture(application, product, "artifact-refresh-first", content)
    assert first.artifact is not None
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            UPDATE mra.artifact
            SET integrity_state = 'CORRUPT',
                last_verified_at = clock_timestamp() - interval '25 hours'
            WHERE artifact_id = %s
            """,
            (first.artifact.artifact_id,),
        )

    second = _capture(application, product, "artifact-refresh-second", content)
    assert second.artifact is not None
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert second.artifact.integrity_state == "AVAILABLE"
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT artifact.integrity_state,
                   artifact.last_verified_at >= clock_timestamp() - interval '1 minute',
                   count(verification.verification_id)
            FROM mra.artifact AS artifact
            JOIN mra.artifact_verification AS verification
              ON verification.artifact_id = artifact.artifact_id
            WHERE artifact.artifact_id = %s
            GROUP BY artifact.artifact_id
            """,
            (first.artifact.artifact_id,),
        ).fetchone()
    assert row == ("AVAILABLE", True, 2)


def test_authoritative_query_requires_recent_physical_artifact_verification(
    market_stack,
) -> None:
    application, queries, store, pool, _, product, database_url = market_stack
    captured = _capture(
        application,
        product,
        "authoritative-read-cadence",
        b"session authority bytes",
    )
    session = _session(
        session_id=uuid4(),
        session_date=date(2026, 8, 28),
        capture_id=captured.capture.capture_id,
    )
    normalized = application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(
            lambda capture: NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                trading_sessions=(session,),
            )
        ),
        _context("normalize-authoritative-read-cadence", "NORMALIZE_MARKET_PIT"),
    )
    assert queries.trading_session_as_of(
        exchange=session.exchange,
        session_date=session.session_date,
        decision_time=normalized.decision_visible_at,
    ) == session

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            UPDATE mra.artifact
            SET last_verified_at = clock_timestamp() - interval '25 hours'
            WHERE artifact_id = %s
            """,
            (captured.capture.artifact_id,),
        )
    with pytest.raises(ArtifactIntegrityError, match="TradingSession evidence"):
        queries.trading_session_as_of(
            exchange=session.exchange,
            session_date=session.session_date,
            decision_time=normalized.decision_visible_at,
        )

    ArtifactApplication(store, PostgresUnitOfWorkProvider(pool)).verify(
        captured.capture.artifact_id,
        verifier_id="market-query-cadence-test",
        context=_context("verify-authoritative-read-cadence", "AUTHORITATIVE_READ"),
    )
    assert queries.trading_session_as_of(
        exchange=session.exchange,
        session_date=session.session_date,
        decision_time=normalized.decision_visible_at,
    ) == session


def test_concurrent_identical_capture_commands_commit_one_canonical_fact(
    market_stack,
) -> None:
    application, _, store, _, _, product, database_url = market_stack
    request = CaptureRequest(
        provider_product_id=product.provider_product_id,
        capture_key="concurrent-capture",
        resource="fixture://concurrent",
        request_headers_hash="c" * 64,
    )
    context = _context("concurrent-capture", "CAPTURE_PROVIDER_RESPONSE")

    def execute(_worker: int):
        return application.capture(
            request,
            ExactBytesProvider(b"same concurrent bytes"),
            context,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(execute, (1, 2)))

    assert {item.capture.capture_id for item in results} == {
        results[0].capture.capture_id
    }
    assert sorted(item.replayed for item in results) == [False, True]
    assert len(store.list_objects()) == 1
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.data_capture").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM mra.command_receipt WHERE command_kind = 'CAPTURE_MARKET_DATA'"
        ).fetchone() == (1,)


def test_data_capture_reference_protects_artifact_from_orphan_gc(
    market_stack,
) -> None:
    application, _, store, pool, _, product, database_url = market_stack
    captured = _capture(application, product, "gc-protected", b"canonical capture")
    assert captured.artifact is not None
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))

    scan = artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="market-gc-test",
    )

    assert captured.artifact.content_sha256 in scan.protected
    assert captured.artifact.content_sha256 not in scan.observed
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.artifact_gc_candidate"
        ).fetchone() == (0,)


def test_artifact_registration_clears_prior_orphan_observation_atomically(
    market_stack,
) -> None:
    application, _, store, pool, _, product, database_url = market_stack
    exact_bytes = b"observed before canonical capture"
    physical = store.publish_bytes(exact_bytes, media_type="application/json")
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    assert artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(hours=1),
        actor_id="market-gc-inverse-race",
    ).observed == (physical.content_sha256,)

    captured = _capture(application, product, "gc-observed-first", exact_bytes)
    assert captured.artifact is not None
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT candidate.state, candidate.disposition_reason_code,
                   capture.capture_id
            FROM mra.artifact_gc_candidate AS candidate
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = candidate.artifact_id
            JOIN mra.data_capture AS capture
              ON capture.artifact_id = artifact.artifact_id
            WHERE candidate.content_sha256 = %s
            """,
            (physical.content_sha256,),
        ).fetchone() == (
            "CLEARED",
            "ARTIFACT_REGISTERED",
            captured.capture.capture_id,
        )


def test_artifact_registration_and_capture_binding_serialize_against_gc(
    market_stack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _, store, pool, _, product, database_url = market_stack
    exact_bytes = b"physical bytes becoming a canonical Capture"
    physical = store.publish_bytes(
        exact_bytes,
        media_type="application/json",
    )
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    first = artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="market-gc-race-test",
    )
    assert first.observed == (physical.content_sha256,)

    registration_locked = Event()
    release_registration = Event()
    original_register = PostgresArtifactRepository.register

    def pausing_register(repository, **kwargs):
        record = original_register(repository, **kwargs)
        registration_locked.set()
        if not release_registration.wait(timeout=10):
            raise TimeoutError("test did not release Artifact registration")
        return record

    monkeypatch.setattr(PostgresArtifactRepository, "register", pausing_register)
    request = CaptureRequest(
        provider_product_id=product.provider_product_id,
        capture_key="gc-registration-race",
        resource="fixture://gc-registration-race",
        request_headers_hash="d" * 64,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        capture_future = executor.submit(
            application.capture,
            request,
            ExactBytesProvider(exact_bytes),
            _context("capture-gc-registration-race", "CAPTURE_PROVIDER_RESPONSE"),
        )
        assert registration_locked.wait(timeout=10)
        gc_future = executor.submit(
            artifacts.scan_orphans,
            scan_id=uuid4(),
            grace=timedelta(0),
            actor_id="market-gc-race-test",
        )
        with pytest.raises(FutureTimeoutError):
            gc_future.result(timeout=0.2)
        release_registration.set()
        captured = capture_future.result(timeout=10)
        with pytest.raises(ArtifactIntegrityError, match="not eligible"):
            gc_future.result(timeout=10)

    assert captured.artifact is not None
    assert store.object_path(physical.content_sha256).exists()
    protected = artifacts.scan_orphans(
        scan_id=uuid4(),
        grace=timedelta(0),
        actor_id="market-gc-race-test",
    )
    assert physical.content_sha256 in protected.protected
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT capture.capture_id, artifact.integrity_state,
                   candidate.state
            FROM mra.data_capture AS capture
            JOIN mra.artifact AS artifact
              ON artifact.artifact_id = capture.artifact_id
            LEFT JOIN mra.artifact_gc_candidate AS candidate
              ON candidate.content_sha256 = artifact.content_sha256
            WHERE artifact.content_sha256 = %s
            """,
            (physical.content_sha256,),
        ).fetchone() == (captured.capture.capture_id, "AVAILABLE", "CLEARED")


def test_corrupt_capture_artifact_blocks_normalization_before_database_mutation(
    market_stack,
) -> None:
    application, _, store, _, _, product, database_url = market_stack
    captured = _capture(application, product, "corrupt-before-normalize", b"exact bytes")
    assert captured.artifact is not None
    store.object_path(captured.artifact.content_sha256).write_bytes(b"tampered")

    with pytest.raises(ArtifactIntegrityError, match="failed authoritative verification"):
        application.normalize(
            captured.capture.capture_id,
            FixedNormalizer(
                lambda capture: NormalizationBatch(
                    source_capture_id=capture.capture_id,
                    source_provider_product_id=capture.provider_product_id,
                )
            ),
            _context("normalize-corrupt", "NORMALIZE_MARKET_PIT"),
        )

    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.command_receipt WHERE command_kind = 'NORMALIZE_MARKET_PIT'"
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT status, error_code FROM mra.command_receipt
            WHERE command_kind = 'NORMALIZE_MARKET_PIT'
            """
        ).fetchone() == ("FAILED", "ARTIFACT_INTEGRITY_FAILED")
        assert connection.execute(
            "SELECT count(*) FROM mra.market_bar_revision"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT integrity_state FROM mra.artifact WHERE artifact_id = %s",
            (captured.capture.artifact_id,),
        ).fetchone() == ("CORRUPT",)
        assert connection.execute(
            """
            SELECT result FROM mra.artifact_verification
            WHERE artifact_id = %s
            ORDER BY verified_at DESC
            LIMIT 1
            """,
            (captured.capture.artifact_id,),
        ).fetchone() == ("SIZE_MISMATCH",)
        assert connection.execute(
            """
            SELECT count(*) FROM mra.command_receipt
            WHERE command_kind = 'VERIFY_MARKET_SOURCE_ARTIFACT'
              AND status = 'SUCCEEDED'
            """
        ).fetchone() == (1,)


def test_capture_product_lineage_and_nullable_gap_identity_fail_closed(
    market_stack,
) -> None:
    application, _, _, _, provider, product, database_url = market_stack
    other_product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="other_market_product",
        revision=1,
        payload_family="OTHER_MARKET_PAYLOAD",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=tuple(MarketFactKind),
        instrument_fact_kinds=tuple(InstrumentFactKind),
        bar_timeframes=tuple(BarTimeframe),
        price_bases=tuple(PriceBasis),
    )
    application.register_provider_product(
        other_product,
        _context("product-lineage-other", "REGISTER_PROVIDER_PRODUCT"),
    )
    captured = _capture(application, product, "lineage-gap", b"no rows")

    def gap_batch(capture) -> NormalizationBatch:
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
                    detail=None,
                    instrument_code="MISSING.XSHG",
                ),
            ),
        )

    application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(gap_batch),
        _context("normalize-lineage-gap", "NORMALIZE_MARKET_PIT"),
    )
    copy_sql = """
        INSERT INTO mra.source_gap (
            gap_id, provider_product_id, capture_id, instrument_id,
            session_id, instrument_code, identifier_scheme, identifier_value,
            exchange, session_date, classification_scheme, classification_code,
            action_key, gap_kind, reason_code, fact_kind, timeframe,
            instrument_fact_kind, evidence_scope, price_basis,
            event_start, event_end, effective_from, effective_to, detail,
            recorded_at, known_at, decision_visible_at
        )
        SELECT %s, %s, capture_id, instrument_id, session_id,
               %s, identifier_scheme, identifier_value,
               exchange, session_date, classification_scheme,
               classification_code, action_key, %s, %s, fact_kind, timeframe,
               instrument_fact_kind, evidence_scope, price_basis,
               event_start, event_end, effective_from, effective_to, detail,
               recorded_at, known_at,
               decision_visible_at
        FROM mra.source_gap
        WHERE capture_id = %s
    """
    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                copy_sql,
                (
                    uuid4(),
                    other_product.provider_product_id,
                    "OTHER.XSHG",
                    GapKind.CONFLICT.value,
                    GapReasonCode.CONFLICTING_SOURCE_REVISIONS.value,
                    captured.capture.capture_id,
                ),
            )
    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                copy_sql,
                (
                    uuid4(),
                    product.provider_product_id,
                    "MISSING.XSHG",
                    GapKind.CONFLICT.value,
                    GapReasonCode.CONFLICTING_SOURCE_REVISIONS.value,
                    captured.capture.capture_id,
                ),
            )
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.source_gap").fetchone() == (1,)


def test_market_bar_gap_requires_exact_instrument_session_and_grid(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    captured = _capture(application, product, "gap-session-grid", b"gap scope")
    instrument_id = uuid4()
    xshg_session_id = uuid4()
    xshe_session_id = uuid4()
    session_date = date(2026, 8, 28)
    xshg_session = _session(
        session_id=xshg_session_id,
        session_date=session_date,
        capture_id=captured.capture.capture_id,
    )
    xshe_session = TradingSession(
        session_id=xshe_session_id,
        exchange="XSHE",
        session_date=session_date,
        timezone_name="Asia/Shanghai",
        open_at=xshg_session.open_at,
        break_start_at=xshg_session.break_start_at,
        break_end_at=xshg_session.break_end_at,
        close_at=xshg_session.close_at,
        decision_reference_at=xshg_session.decision_reference_at,
        source_capture_id=captured.capture.capture_id,
    )

    def setup_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="600001.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(xshg_session, xshe_session),
        )

    application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(setup_batch),
        _context("normalize-gap-session-grid", "NORMALIZE_MARKET_PIT"),
    )
    reason_contract_capture = _capture(
        application,
        product,
        "gap-reason-contract",
        b"gap reason contract",
    )
    insert_gap_sql = """
        WITH database_clock AS (
            SELECT clock_timestamp() AS observed_at
        )
            INSERT INTO mra.source_gap (
                gap_id, provider_product_id, capture_id, instrument_id,
                session_id, gap_kind, reason_code, fact_kind,
                instrument_code, instrument_fact_kind, timeframe, price_basis,
                event_start, event_end, detail,
                recorded_at, known_at, decision_visible_at
            )
            SELECT %s, %s, %s, %s, %s,
                   'MISSING', 'EXACT_BAR_MISSING', 'MARKET_BAR', NULL, NULL,
                   'MINUTE_5', 'RAW_UNADJUSTED', %s, %s, NULL,
               observed_at, observed_at, observed_at
        FROM database_clock
    """
    event_end = xshg_session.decision_reference_at
    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation, match="exchanges differ"):
            with connection.transaction():
                connection.execute(
                    insert_gap_sql,
                    (
                        uuid4(),
                        product.provider_product_id,
                        captured.capture.capture_id,
                        instrument_id,
                        xshe_session_id,
                        event_end - timedelta(minutes=5),
                        event_end,
                    ),
                )
        with pytest.raises(psycopg.errors.CheckViolation, match="Session grid"):
            with connection.transaction():
                connection.execute(
                    insert_gap_sql,
                    (
                        uuid4(),
                        product.provider_product_id,
                        captured.capture.capture_id,
                        instrument_id,
                        xshg_session_id,
                        event_end - timedelta(minutes=6),
                        event_end - timedelta(minutes=1),
                    ),
                )
        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="source_gap_reason_fact_ck",
        ):
            with connection.transaction():
                connection.execute(
                    """
                    WITH database_clock AS (
                        SELECT clock_timestamp() AS observed_at
                    )
                    INSERT INTO mra.source_gap (
                        gap_id, provider_product_id, capture_id,
                        instrument_code, gap_kind, reason_code, fact_kind,
                        recorded_at, known_at, decision_visible_at
                    )
                    SELECT %s, %s, %s, '600001.XSHG', 'PLACEHOLDER',
                           'NULL_OHLC_PLACEHOLDER', 'INSTRUMENT',
                           observed_at, observed_at, observed_at
                    FROM database_clock
                    """,
                    (
                        uuid4(),
                        product.provider_product_id,
                        reason_contract_capture.capture.capture_id,
                    ),
                )


def test_provider_product_capability_contract_rejects_undeclared_bar_scope(
    market_stack,
) -> None:
    application, _, _, _, provider, _, database_url = market_stack
    gap_only = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="gap_only_product",
        revision=1,
        payload_family="GAP_REPORT",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=(MarketFactKind.INSTRUMENT,),
        instrument_fact_kinds=(),
        bar_timeframes=(),
        price_bases=(),
    )
    application.register_provider_product(
        gap_only,
        _context("product-gap-only", "REGISTER_PROVIDER_PRODUCT"),
    )
    captured = _capture(application, gap_only, "gap-only-capture", b"bar missing")

    def undeclared_bar_gap(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            gaps=(
                SourceGap(
                    gap_id=uuid4(),
                    provider_product_id=capture.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=uuid4(),
                    session_id=uuid4(),
                    gap_kind=GapKind.MISSING,
                    reason_code=GapReasonCode.EXPECTED_OBSERVATION_MISSING,
                    fact_kind=GapFactKind.MARKET_BAR,
                    instrument_fact_kind=None,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=datetime(2026, 8, 28, 6, 50, tzinfo=UTC),
                    event_end=datetime(2026, 8, 28, 6, 55, tzinfo=UTC),
                    detail=None,
                ),
            ),
        )

    with pytest.raises(RuntimeStateConflictError, match="fact capabilities"):
        application.normalize(
            captured.capture.capture_id,
            FixedNormalizer(undeclared_bar_gap),
            _context("normalize-undeclared-bar-gap", "NORMALIZE_MARKET_PIT"),
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.source_gap").fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM mra.command_receipt WHERE command_kind = 'NORMALIZE_MARKET_PIT'"
        ).fetchone() == (1,)
        assert connection.execute(
            """
            SELECT status, error_code FROM mra.command_receipt
            WHERE command_kind = 'NORMALIZE_MARKET_PIT'
            """
        ).fetchone() == ("FAILED", "NORMALIZATION_BINDING_REJECTED")


def test_normalize_writes_reference_lineage_and_exact_asof_market_authority(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    captured = _capture(application, product, "normalize-1", b'{"rows":[]}\n')
    capture_id = captured.capture.capture_id
    instrument_id = uuid4()
    session_id = uuid4()
    classification_id = uuid4()
    event_end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)

    def batch_factory(capture) -> NormalizationBatch:
        instrument = Instrument(
            instrument_id=instrument_id,
            canonical_code="601919.XSHG",
            exchange="XSHG",
            instrument_type=InstrumentType.EQUITY,
            currency="CNY",
            source_capture_id=capture.capture_id,
        )
        session = TradingSession(
            session_id=session_id,
            exchange="XSHG",
            session_date=date(2026, 8, 28),
            timezone_name="Asia/Shanghai",
            open_at=datetime(2026, 8, 28, 1, 30, tzinfo=UTC),
            break_start_at=datetime(2026, 8, 28, 3, 30, tzinfo=UTC),
            break_end_at=datetime(2026, 8, 28, 5, 0, tzinfo=UTC),
            close_at=datetime(2026, 8, 28, 7, 0, tzinfo=UTC),
            decision_reference_at=event_end,
            source_capture_id=capture.capture_id,
        )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(instrument,),
            instrument_identifiers=(
                InstrumentIdentifier(
                    instrument_identifier_id=uuid4(),
                    instrument_id=instrument_id,
                    identifier_scheme="TICKER",
                    identifier_value="sh.601919",
                    effective_from=datetime(2007, 6, 26, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_identifier_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(session,),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_id,
                    classification_scheme="INDUSTRY",
                    classification_code="MARINE_TRANSPORT",
                    display_name="Marine Transport",
                    revision=1,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
                    classification_id=classification_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
            ),
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=event_end - timedelta(minutes=5),
                    event_end=event_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("15.10"),
                    high=_cny("15.40"),
                    low=_cny("15.00"),
                    close=_cny("15.32"),
                    volume=_shares("0"),
                    turnover=_cny("0"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.ACTIVE,
                    event_start=session.open_at,
                    event_end=session.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.LISTED,
                    effective_from=datetime(2007, 6, 26, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
                    status=SpecialTreatmentStatus.NORMAL,
                    effective_from=datetime(2007, 6, 26, tzinfo=UTC),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            instrument_facts=(
                InstrumentFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=None,
                    fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
                    evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
                    event_start=datetime(2026, 1, 1, tzinfo=UTC),
                    event_end=datetime(2027, 1, 1, tzinfo=UTC),
                    value=_shares("12259652922"),
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            corporate_actions=(
                CorporateActionRevision(
                    corporate_action_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    action_key="601919:2026:CASH_DIVIDEND",
                    action_type=CorporateActionType.CASH_DIVIDEND,
                    ex_session_id=session_id,
                    record_session_id=session_id,
                    pay_session_id=session_id,
                    cash_amount_per_share=_cny("0.19"),
                    ratio_factor=None,
                    subscription_price=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    normalizer = FixedNormalizer(batch_factory)
    normalized = application.normalize(
        capture_id,
        normalizer,
        _context("normalize-1", "NORMALIZE_MARKET_PIT"),
    )
    assert normalizer.seen_content == b'{"rows":[]}\n'
    assert normalized.replayed is False
    assert normalized.decision_visible_at is not None
    assert (
        normalized.decision_visible_at
        > captured.capture.temporal.decision_visible_at
    )
    assert queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    ) is None

    bar = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        decision_time=normalized.decision_visible_at,
    )
    assert bar is not None
    assert bar.close == _cny("15.32")
    assert bar.volume == _shares("0")
    assert queries.instrument_for_identifier_as_of(
        identifier_scheme="TICKER",
        identifier_value="sh.601919",
        effective_time=event_end,
        decision_time=normalized.decision_visible_at,
    ) == InstrumentId.parse(instrument_id)
    classification_members = queries.classification_members_as_of(
        classification_scheme="INDUSTRY",
        classification_code="MARINE_TRANSPORT",
        effective_time=event_end,
        decision_time=normalized.decision_visible_at,
    )
    assert classification_members.status is ClassificationEvidenceStatus.AVAILABLE
    assert classification_members.members == (InstrumentId.parse(instrument_id),)
    assert (
        queries.security_status_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            evidence_scope=EvidenceScope.DECISION_SESSION,
            decision_time=normalized.decision_visible_at,
        )
        is SecurityStatus.ACTIVE
    )
    actions = queries.corporate_actions_as_of(
        instrument_id=instrument_id,
        ex_session_id=session_id,
        decision_time=normalized.decision_visible_at,
    )
    assert len(actions) == 1
    assert actions[0].cash_amount_per_share == _cny("0.19")
    shares = queries.instrument_fact_as_of(
        instrument_id=instrument_id,
        fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
        evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
        event_time=event_end,
        decision_time=normalized.decision_visible_at,
    )
    assert shares is not None
    assert shares.numeric_value == Decimal("12259652922.0000000000")
    assert queries.listing_status_as_of(
        instrument_id=instrument_id,
        effective_time=event_end,
        decision_time=normalized.decision_visible_at,
    ) is ListingStatus.LISTED
    assert queries.special_treatment_status_as_of(
        instrument_id=instrument_id,
        effective_time=event_end,
        decision_time=normalized.decision_visible_at,
    ) is SpecialTreatmentStatus.NORMAL

    exact_plan = queries.explain_exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        decision_time=normalized.decision_visible_at,
    )
    assert {"market_bar_revision", "data_capture", "artifact"} <= _plan_relations(
        exact_plan["Plan"]
    )
    assert exact_plan["Execution Time"] >= 0
    session_plan = queries.explain_trading_session_as_of(
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=normalized.decision_visible_at,
    )
    identifier_plan = queries.explain_instrument_identifier_as_of(
        identifier_scheme="TICKER",
        identifier_value="sh.601919",
        effective_time=event_end,
        decision_time=normalized.decision_visible_at,
    )
    classification_plan = queries.explain_classification_members_as_of(
        classification_scheme="INDUSTRY",
        classification_code="MARINE_TRANSPORT",
        effective_time=event_end,
        decision_time=normalized.decision_visible_at,
    )

    with psycopg.connect(database_url) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM mra.instrument),
                (SELECT count(*) FROM mra.instrument_identifier),
                (SELECT count(*) FROM mra.trading_session),
                (SELECT count(*) FROM mra.classification),
                (SELECT count(*) FROM mra.classification_membership_revision),
                (SELECT count(*) FROM mra.market_bar_revision),
                (SELECT count(*) FROM mra.instrument_fact_revision),
                (SELECT count(*) FROM mra.corporate_action_revision)
            """
        ).fetchone()
        index_definitions = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT indexname, indexdef FROM pg_indexes
                WHERE schemaname = 'mra'
                  AND indexname IN (
                      'market_bar_exact_asof_idx',
                      'trading_session_calendar_idx',
                      'classification_asof_idx',
                      'classification_membership_classification_idx',
                      'instrument_identifier_asof_idx'
                  )
                """
            ).fetchall()
        }
    assert counts == (1, 1, 1, 1, 1, 1, 4, 1)
    assert set(index_definitions) == {
        "market_bar_exact_asof_idx",
        "trading_session_calendar_idx",
        "classification_asof_idx",
        "classification_membership_classification_idx",
        "instrument_identifier_asof_idx",
    }
    assert "price_basis" in index_definitions["market_bar_exact_asof_idx"]
    assert "decision_visible_at" in index_definitions["market_bar_exact_asof_idx"]
    assert {"trading_session", "data_capture", "artifact"} <= _plan_relations(
        session_plan["Plan"]
    )
    assert {"instrument_identifier", "data_capture", "artifact"} <= _plan_relations(
        identifier_plan["Plan"]
    )
    assert {
        "classification",
        "classification_membership_revision",
        "data_capture",
        "artifact",
    } <= _plan_relations(classification_plan["Plan"])


def test_global_session_and_classification_can_feed_another_product(
    market_stack,
) -> None:
    application, _, _, pool, provider, reference_product, _ = market_stack
    reference_capture = _capture(
        application,
        reference_product,
        "cross-product-reference",
        b"global references",
    )
    instrument_id = uuid4()
    session_id = uuid4()
    classification_id = uuid4()
    event_end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)
    effective_from = datetime(2020, 1, 1, tzinfo=UTC)

    def reference_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="600000.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(
                _session(
                    session_id=session_id,
                    session_date=date(2026, 8, 28),
                    capture_id=capture.capture_id,
                ),
            ),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_id,
                    classification_scheme="INDEX",
                    classification_code="CROSS_PRODUCT",
                    display_name="Cross-product reference",
                    revision=1,
                    effective_from=effective_from,
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
        )

    application.normalize(
        reference_capture.capture.capture_id,
        FixedNormalizer(reference_batch),
        _context("normalize-cross-product-reference", "NORMALIZE_MARKET_PIT"),
    )
    fact_product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="cross_product_facts",
        revision=1,
        payload_family="CROSS_PRODUCT_FACTS",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=(
            MarketFactKind.TRADING_SESSION,
            MarketFactKind.CLASSIFICATION,
            MarketFactKind.CLASSIFICATION_MEMBERSHIP,
            MarketFactKind.MARKET_BAR,
        ),
        instrument_fact_kinds=(),
        bar_timeframes=(BarTimeframe.MINUTE_5,),
        price_bases=(PriceBasis.RAW_UNADJUSTED,),
    )
    application.register_provider_product(
        fact_product,
        _context("register-cross-product-facts", "REGISTER_PROVIDER_PRODUCT"),
    )
    fact_capture = _capture(
        application,
        fact_product,
        "cross-product-facts",
        b"product-specific facts",
    )

    def fact_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
                    classification_id=classification_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=effective_from,
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
            ),
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=fact_product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=event_end - timedelta(minutes=5),
                    event_end=event_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("10"),
                    high=_cny("10.2"),
                    low=_cny("9.9"),
                    close=_cny("10.1"),
                    volume=_shares("100"),
                    turnover=_cny("1010"),
                ),
            ),
        )

    fact_result = application.normalize(
        fact_capture.capture.capture_id,
        FixedNormalizer(fact_batch),
        _context("normalize-cross-product-facts", "NORMALIZE_MARKET_PIT"),
    )
    fact_queries = PostgresMarketQueries(
        pool,
        provider_product_id=fact_product.provider_product_id,
    )
    session = fact_queries.trading_session_as_of(
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=fact_result.decision_visible_at,
    )
    assert session is not None
    assert session.source_capture_id == reference_capture.capture.capture_id
    exact_bar = fact_queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        decision_time=fact_result.decision_visible_at,
    )
    assert exact_bar is not None and exact_bar.close == _cny("10.1")
    members = fact_queries.classification_members_as_of(
        classification_scheme="INDEX",
        classification_code="CROSS_PRODUCT",
        effective_time=event_end,
        decision_time=fact_result.decision_visible_at,
    )
    assert members.status is ClassificationEvidenceStatus.AVAILABLE
    assert members.members == (InstrumentId.parse(instrument_id),)

    unrelated_gap_capture = _capture(
        application,
        fact_product,
        "cross-product-unrelated-gaps",
        b"unrelated global gaps",
    )

    def unrelated_gap_batch(capture) -> NormalizationBatch:
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
                    reason_code=GapReasonCode.EXPECTED_OBSERVATION_MISSING,
                    fact_kind=GapFactKind.TRADING_SESSION,
                    instrument_fact_kind=None,
                    timeframe=None,
                    price_basis=None,
                    event_start=None,
                    event_end=None,
                    detail="Product-local absence cannot poison global Session",
                    exchange="XSHG",
                    session_date=date(2026, 8, 28),
                ),
                SourceGap(
                    gap_id=uuid4(),
                    provider_product_id=capture.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=None,
                    session_id=None,
                    gap_kind=GapKind.MISSING,
                    reason_code=GapReasonCode.EXPECTED_OBSERVATION_MISSING,
                    fact_kind=GapFactKind.CLASSIFICATION,
                    instrument_fact_kind=None,
                    timeframe=None,
                    price_basis=None,
                    event_start=None,
                    event_end=None,
                    effective_from=effective_from,
                    detail="Product-local absence cannot poison global Classification",
                    classification_scheme="INDEX",
                    classification_code="CROSS_PRODUCT",
                ),
            ),
        )

    gap_result = application.normalize(
        unrelated_gap_capture.capture.capture_id,
        FixedNormalizer(unrelated_gap_batch),
        _context("normalize-cross-product-unrelated-gaps", "NORMALIZE_MARKET_PIT"),
    )
    assert fact_queries.trading_session_as_of(
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=gap_result.decision_visible_at,
    ) is not None
    members_after_unrelated_gap = fact_queries.classification_members_as_of(
        classification_scheme="INDEX",
        classification_code="CROSS_PRODUCT",
        effective_time=event_end,
        decision_time=gap_result.decision_visible_at,
    )
    assert members_after_unrelated_gap.status is ClassificationEvidenceStatus.AVAILABLE
    assert members_after_unrelated_gap.members == (InstrumentId.parse(instrument_id),)


def test_absent_classification_is_not_a_verified_empty_membership(
    market_stack,
) -> None:
    _, queries, _, _, _, _, _ = market_stack
    result = queries.classification_members_as_of(
        classification_scheme="INDEX",
        classification_code="ABSENT",
        effective_time=datetime(2026, 8, 28, tzinfo=UTC),
        decision_time=DecisionTime(datetime.now(UTC)),
    )
    assert result.status is ClassificationEvidenceStatus.MISSING
    assert result.members == ()


def test_generic_market_facts_do_not_infer_suspension_from_flat_zero_volume_bar(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    captured = _capture(application, product, "flat-zero", b"flat")
    instrument_id = uuid4()
    session_id = uuid4()
    end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="510300.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.ETF,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(
                TradingSession(
                    session_id=session_id,
                    exchange="XSHG",
                    session_date=date(2026, 8, 28),
                    timezone_name="Asia/Shanghai",
                    open_at=datetime(2026, 8, 28, 1, 30, tzinfo=UTC),
                    break_start_at=datetime(2026, 8, 28, 3, 30, tzinfo=UTC),
                    break_end_at=datetime(2026, 8, 28, 5, tzinfo=UTC),
                    close_at=datetime(2026, 8, 28, 7, tzinfo=UTC),
                    decision_reference_at=end,
                    source_capture_id=capture.capture_id,
                ),
            ),
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("4.000"),
                    high=_cny("4.000"),
                    low=_cny("4.000"),
                    close=_cny("4.000"),
                    volume=_shares("0"),
                    turnover=_cny("0"),
                ),
            ),
        )

    normalized = application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(batch),
        _context("normalize-flat-zero", "NORMALIZE_MARKET_PIT"),
    )
    bar = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=normalized.decision_visible_at,
    )
    assert bar is not None and bar.close == _cny("4.000")
    assert bar.volume == _shares("0")
    assert (
        queries.security_status_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            evidence_scope=EvidenceScope.DECISION_SESSION,
            decision_time=normalized.decision_visible_at,
        )
        is None
    )


def test_completed_exact_bar_query_is_not_retroactively_changed_by_later_gap(
    market_stack,
) -> None:
    application, queries, _, pool, _, product, _ = market_stack
    captured = _capture(application, product, "snapshot-bar", b"valid bar")
    instrument_id = uuid4()
    session_id = uuid4()
    event_end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)

    def initial_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="510500.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.ETF,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(
                TradingSession(
                    session_id=session_id,
                    exchange="XSHG",
                    session_date=date(2026, 8, 28),
                    timezone_name="Asia/Shanghai",
                    open_at=datetime(2026, 8, 28, 1, 30, tzinfo=UTC),
                    break_start_at=datetime(2026, 8, 28, 3, 30, tzinfo=UTC),
                    break_end_at=datetime(2026, 8, 28, 5, tzinfo=UTC),
                    close_at=datetime(2026, 8, 28, 7, tzinfo=UTC),
                    decision_reference_at=event_end,
                    source_capture_id=capture.capture_id,
                ),
            ),
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=event_end - timedelta(minutes=5),
                    event_end=event_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("5"),
                    high=_cny("5"),
                    low=_cny("5"),
                    close=_cny("5"),
                    volume=_shares("1"),
                    turnover=_cny("5"),
                ),
            ),
        )

    initial = application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(initial_batch),
        _context("normalize-snapshot-bar", "NORMALIZE_MARKET_PIT"),
    )
    assert initial.decision_visible_at is not None
    after_session = Event()
    resume = Event()
    snapshot_queries = PausingExactBarQueries(
        pool,
        provider_product_id=product.provider_product_id,
        after_session=after_session,
        resume=resume,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            snapshot_queries.exact_bar_as_of,
            instrument_id=instrument_id,
            session_id=session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=event_end - timedelta(minutes=5),
            event_end=event_end,
            decision_time=DecisionTime(initial.decision_visible_at.value + timedelta(minutes=1)),
        )
        assert after_session.wait(timeout=10)
        missing_capture = _capture(
            application,
            product,
            "snapshot-gap",
            b"missing exact observation",
        )

        def gap_batch(capture) -> NormalizationBatch:
            return NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                gaps=(
                    SourceGap(
                        gap_id=uuid4(),
                        provider_product_id=product.provider_product_id,
                        capture_id=capture.capture_id,
                        instrument_id=instrument_id,
                        session_id=session_id,
                        gap_kind=GapKind.MISSING,
                        reason_code=GapReasonCode.EXACT_BAR_MISSING,
                        fact_kind=GapFactKind.MARKET_BAR,
                        instrument_fact_kind=None,
                        timeframe=BarTimeframe.MINUTE_5,
                        price_basis=PriceBasis.RAW_UNADJUSTED,
                        event_start=event_end - timedelta(minutes=5),
                        event_end=event_end,
                        detail=None,
                    ),
                ),
            )

        try:
            missing = application.normalize(
                missing_capture.capture.capture_id,
                FixedNormalizer(gap_batch),
                _context("normalize-snapshot-gap", "NORMALIZE_MARKET_PIT"),
            )
        finally:
            resume.set()
        in_flight = pending.result(timeout=10)

    assert in_flight is not None and in_flight.close == _cny("5")
    assert missing.decision_visible_at is not None
    with pytest.raises(MarketEvidenceGapError) as gap_error:
        queries.exact_bar_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=event_end - timedelta(minutes=5),
            event_end=event_end,
            decision_time=missing.decision_visible_at,
        )
    assert gap_error.value.gap.reason_code is GapReasonCode.EXACT_BAR_MISSING


def test_exact_bar_placeholder_blocks_previous_session_and_daily_fallbacks(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    captured = _capture(application, product, "placeholder-1455", b"null OHLC")
    instrument_id = uuid4()
    prior_session_id = uuid4()
    current_session_id = uuid4()
    prior_end = datetime(2026, 8, 27, 6, 55, tzinfo=UTC)
    current_end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)

    def session(session_id, session_date, end, capture_id):
        return TradingSession(
            session_id=session_id,
            exchange="XSHG",
            session_date=session_date,
            timezone_name="Asia/Shanghai",
            open_at=end - timedelta(hours=5, minutes=25),
            break_start_at=end - timedelta(hours=3, minutes=25),
            break_end_at=end - timedelta(hours=1, minutes=55),
            close_at=end + timedelta(minutes=5),
            decision_reference_at=end,
            source_capture_id=capture_id,
        )

    def batch(capture) -> NormalizationBatch:
        prior = session(
            prior_session_id,
            date(2026, 8, 27),
            prior_end,
            capture.capture_id,
        )
        current = session(
            current_session_id,
            date(2026, 8, 28),
            current_end,
            capture.capture_id,
        )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="601919.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(prior, current),
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=prior_session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=prior_end - timedelta(minutes=5),
                    event_end=prior_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("15"),
                    high=_cny("15"),
                    low=_cny("15"),
                    close=_cny("15"),
                    volume=_shares("0"),
                    turnover=None,
                ),
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=current_session_id,
                    timeframe=BarTimeframe.DAILY,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=current.open_at,
                    event_end=current.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("15"),
                    high=_cny("15"),
                    low=_cny("15"),
                    close=_cny("15"),
                    volume=_shares("0"),
                    turnover=None,
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=prior_session_id,
                    evidence_scope=EvidenceScope.PRIOR_SESSION,
                    status=SecurityStatus.SUSPENDED,
                    event_start=prior.open_at,
                    event_end=prior.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            gaps=(
                SourceGap(
                    gap_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=current_session_id,
                    gap_kind=GapKind.PLACEHOLDER,
                    reason_code=GapReasonCode.NULL_OHLC_PLACEHOLDER,
                    fact_kind=GapFactKind.MARKET_BAR,
                    instrument_fact_kind=None,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=current_end - timedelta(minutes=5),
                    event_end=current_end,
                    detail="raw bytes retained; no legal bar emitted",
                ),
            ),
        )

    placeholder_normalized = application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(batch),
        _context("normalize-placeholder", "NORMALIZE_MARKET_PIT"),
    )
    with pytest.raises(MarketEvidenceGapError) as gap_error:
        queries.exact_bar_as_of(
            instrument_id=instrument_id,
            session_id=current_session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=current_end - timedelta(minutes=5),
            event_end=current_end,
            decision_time=placeholder_normalized.decision_visible_at,
        )
    assert gap_error.value.gap.reason_code is GapReasonCode.NULL_OHLC_PLACEHOLDER
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            """
            SELECT count(*) FROM mra.market_bar_revision
            WHERE session_id = %s AND timeframe = 'MINUTE_5'
              AND event_end = %s
            """,
            (current_session_id, current_end),
        ).fetchone() == (0,)

    corrected = _capture(application, product, "placeholder-corrected", b"valid OHLC")

    def corrected_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=current_session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=current_end - timedelta(minutes=5),
                    event_end=current_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("15.10"),
                    high=_cny("15.20"),
                    low=_cny("15.00"),
                    close=_cny("15.15"),
                    volume=_shares("100"),
                    turnover=_cny("1515"),
                ),
            ),
        )

    corrected_normalized = application.normalize(
        corrected.capture.capture_id,
        FixedNormalizer(corrected_batch),
        _context("normalize-placeholder-corrected", "NORMALIZE_MARKET_PIT"),
    )
    corrected_bar = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=current_session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=current_end - timedelta(minutes=5),
        event_end=current_end,
        decision_time=corrected_normalized.decision_visible_at,
    )
    assert corrected_bar is not None and corrected_bar.close == _cny("15.15")


def test_exact_bar_gap_precedence_never_downgrades_conflict_to_missing(
    market_stack,
) -> None:
    application, queries, _, _, _, product, _ = market_stack
    instrument_id = uuid4()
    session_id = uuid4()
    session_date = date(2026, 8, 28)
    base_capture = _capture(application, product, "gap-precedence-base", b"base")
    session = _session(
        session_id=session_id,
        session_date=session_date,
        capture_id=base_capture.capture.capture_id,
    )
    application.normalize(
        base_capture.capture.capture_id,
        FixedNormalizer(
            lambda capture: NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                instruments=(
                    Instrument(
                        instrument_id=instrument_id,
                        canonical_code="600003.XSHG",
                        exchange="XSHG",
                        instrument_type=InstrumentType.EQUITY,
                        currency="CNY",
                        source_capture_id=capture.capture_id,
                    ),
                ),
                trading_sessions=(session,),
            )
        ),
        _context("normalize-gap-precedence-base", "NORMALIZE_MARKET_PIT"),
    )

    bar_gap_capture = _capture(
        application,
        product,
        "gap-precedence-conflict",
        b"conflicting bar",
    )
    application.normalize(
        bar_gap_capture.capture.capture_id,
        FixedNormalizer(
            lambda capture: NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                gaps=(
                    SourceGap(
                        gap_id=uuid4(),
                        provider_product_id=capture.provider_product_id,
                        capture_id=capture.capture_id,
                        instrument_id=instrument_id,
                        session_id=session_id,
                        gap_kind=GapKind.CONFLICT,
                        reason_code=GapReasonCode.CONFLICTING_SOURCE_REVISIONS,
                        fact_kind=GapFactKind.MARKET_BAR,
                        instrument_fact_kind=None,
                        timeframe=BarTimeframe.MINUTE_5,
                        price_basis=PriceBasis.RAW_UNADJUSTED,
                        event_start=session.decision_reference_at - timedelta(minutes=5),
                        event_end=session.decision_reference_at,
                        detail="two incompatible exact bars",
                    ),
                ),
            )
        ),
        _context("normalize-gap-precedence-conflict", "NORMALIZE_MARKET_PIT"),
    )

    status_gap_capture = _capture(
        application,
        product,
        "gap-precedence-status-missing",
        b"status missing",
    )
    latest = application.normalize(
        status_gap_capture.capture.capture_id,
        FixedNormalizer(
            lambda capture: NormalizationBatch(
                source_capture_id=capture.capture_id,
                source_provider_product_id=capture.provider_product_id,
                gaps=(
                    SourceGap(
                        gap_id=uuid4(),
                        provider_product_id=capture.provider_product_id,
                        capture_id=capture.capture_id,
                        instrument_id=instrument_id,
                        session_id=session_id,
                        gap_kind=GapKind.MISSING,
                        reason_code=GapReasonCode.EXPECTED_OBSERVATION_MISSING,
                        fact_kind=GapFactKind.INSTRUMENT_FACT,
                        instrument_fact_kind=InstrumentFactKind.SECURITY_STATUS,
                        evidence_scope=EvidenceScope.DECISION_SESSION,
                        timeframe=None,
                        price_basis=None,
                        event_start=session.open_at,
                        event_end=session.close_at,
                        detail="decision-session status was not observed",
                    ),
                ),
            )
        ),
        _context("normalize-gap-precedence-status", "NORMALIZE_MARKET_PIT"),
    )

    with pytest.raises(MarketEvidenceGapError) as gap_error:
        queries.exact_bar_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=session.decision_reference_at - timedelta(minutes=5),
            event_end=session.decision_reference_at,
            decision_time=latest.decision_visible_at,
        )
    assert gap_error.value.gap.reason_code is GapReasonCode.CONFLICTING_SOURCE_REVISIONS


def test_revision_visibility_basis_separation_and_typed_current_suspension(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    first = _capture(application, product, "revision-1", b"revision 1")
    instrument_id = uuid4()
    session_id = uuid4()
    end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)
    first_bar_id = uuid4()
    first_fact_id = uuid4()

    def first_batch(capture) -> NormalizationBatch:
        session = TradingSession(
            session_id=session_id,
            exchange="XSHG",
            session_date=date(2026, 8, 28),
            timezone_name="Asia/Shanghai",
            open_at=datetime(2026, 8, 28, 1, 30, tzinfo=UTC),
            break_start_at=datetime(2026, 8, 28, 3, 30, tzinfo=UTC),
            break_end_at=datetime(2026, 8, 28, 5, tzinfo=UTC),
            close_at=datetime(2026, 8, 28, 7, tzinfo=UTC),
            decision_reference_at=end,
            source_capture_id=capture.capture_id,
        )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="510300.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.ETF,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(session,),
            bars=(
                MarketBarRevision(
                    bar_revision_id=first_bar_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("4.00"),
                    high=_cny("4.00"),
                    low=_cny("4.00"),
                    close=_cny("4.00"),
                    volume=_shares("0"),
                    turnover=_cny("0"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=first_fact_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.ACTIVE,
                    event_start=session.open_at,
                    event_end=session.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    first_normalized = application.normalize(
        first.capture.capture_id,
        FixedNormalizer(first_batch),
        _context("normalize-revision-1", "NORMALIZE_MARKET_PIT"),
    )
    second = _capture(application, product, "revision-2", b"revision 2")
    second_bar_id = uuid4()

    def second_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=(
                MarketBarRevision(
                    bar_revision_id=second_bar_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=2,
                    supersedes_revision_id=first_bar_id,
                    open=_cny("4.01"),
                    high=_cny("4.02"),
                    low=_cny("4.00"),
                    close=_cny("4.02"),
                    volume=_shares("100"),
                    turnover=_cny("402"),
                ),
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.FORWARD_ADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("3.90"),
                    high=_cny("3.91"),
                    low=_cny("3.89"),
                    close=_cny("3.91"),
                    volume=_shares("100"),
                    turnover=_cny("391"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.SUSPENDED,
                    event_start=datetime(2026, 8, 28, 1, 30, tzinfo=UTC),
                    event_end=datetime(2026, 8, 28, 7, tzinfo=UTC),
                    revision=2,
                    supersedes_revision_id=first_fact_id,
                ),
            ),
        )

    second_normalized = application.normalize(
        second.capture.capture_id,
        FixedNormalizer(second_batch),
        _context("normalize-revision-2", "NORMALIZE_MARKET_PIT"),
    )
    first_visible = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=first_normalized.decision_visible_at,
    )
    second_visible = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=second_normalized.decision_visible_at,
    )
    forward = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.FORWARD_ADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=second_normalized.decision_visible_at,
    )
    assert first_visible is not None and first_visible.bar_revision_id == first_bar_id
    assert second_visible is not None and second_visible.bar_revision_id == second_bar_id
    assert forward is not None and forward.close == _cny("3.91")
    before = queries.security_status_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        evidence_scope=EvidenceScope.DECISION_SESSION,
        decision_time=first_normalized.decision_visible_at,
    )
    after = queries.security_status_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        evidence_scope=EvidenceScope.DECISION_SESSION,
        decision_time=second_normalized.decision_visible_at,
    )
    assert before is SecurityStatus.ACTIVE
    assert after is SecurityStatus.SUSPENDED

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="append-only"):
            connection.execute(
                "UPDATE mra.market_bar_revision SET close_value = 5 WHERE bar_revision_id = %s",
                (first_bar_id,),
            )

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE mra.artifact SET integrity_state = 'CORRUPT' "
            "WHERE artifact_id = %s",
            (second.capture.artifact_id,),
        )
    with pytest.raises(ArtifactIntegrityError, match="MarketBar evidence"):
        queries.exact_bar_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=end - timedelta(minutes=5),
            event_end=end,
            decision_time=second_normalized.decision_visible_at,
        )
    with pytest.raises(ArtifactIntegrityError, match="SecurityStatus evidence"):
        queries.security_status_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            evidence_scope=EvidenceScope.DECISION_SESSION,
            decision_time=second_normalized.decision_visible_at,
        )


def test_corrupt_independent_security_status_does_not_invalidate_exact_bar(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    market_capture = _capture(application, product, "split-status-market", b"bar")
    instrument_id = uuid4()
    session_id = uuid4()
    session = _session(
        session_id=session_id,
        session_date=date(2026, 8, 28),
        capture_id=market_capture.capture.capture_id,
    )

    def market_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="600002.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(session,),
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=session.decision_reference_at - timedelta(minutes=5),
                    event_end=session.decision_reference_at,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("10"),
                    high=_cny("10.1"),
                    low=_cny("9.9"),
                    close=_cny("10"),
                    volume=_shares("100"),
                    turnover=_cny("1000"),
                ),
            ),
        )

    application.normalize(
        market_capture.capture.capture_id,
        FixedNormalizer(market_batch),
        _context("normalize-split-status-market", "NORMALIZE_MARKET_PIT"),
    )
    status_capture = _capture(
        application,
        product,
        "split-status-fact",
        b"active status",
    )

    def status_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    status=SecurityStatus.ACTIVE,
                    event_start=session.open_at,
                    event_end=session.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    status_result = application.normalize(
        status_capture.capture.capture_id,
        FixedNormalizer(status_batch),
        _context("normalize-split-status-fact", "NORMALIZE_MARKET_PIT"),
    )
    exact_bar = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=session.decision_reference_at - timedelta(minutes=5),
        event_end=session.decision_reference_at,
        decision_time=status_result.decision_visible_at,
    )
    assert exact_bar is not None
    assert (
        queries.security_status_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            evidence_scope=EvidenceScope.DECISION_SESSION,
            decision_time=status_result.decision_visible_at,
        )
        is SecurityStatus.ACTIVE
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE mra.artifact SET integrity_state = 'CORRUPT' WHERE artifact_id = %s",
            (status_capture.capture.artifact_id,),
        )
    with pytest.raises(ArtifactIntegrityError, match="SecurityStatus evidence"):
        queries.security_status_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            evidence_scope=EvidenceScope.DECISION_SESSION,
            decision_time=status_result.decision_visible_at,
        )
    assert (
        queries.exact_bar_as_of(
            instrument_id=instrument_id,
            session_id=session_id,
            timeframe=BarTimeframe.MINUTE_5,
            price_basis=PriceBasis.RAW_UNADJUSTED,
            event_start=session.decision_reference_at - timedelta(minutes=5),
            event_end=session.decision_reference_at,
            decision_time=status_result.decision_visible_at,
        )
        == exact_bar
    )


def test_effective_dated_identifier_and_membership_close_then_replace(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    instrument_id = uuid4()
    classification_v1_id = uuid4()
    classification_v2_id = uuid4()
    identifier_v1_id = uuid4()
    membership_v1_id = uuid4()
    effective_from = datetime(2020, 1, 1, tzinfo=UTC)
    cutover_at = datetime(2026, 8, 29, tzinfo=UTC)

    first = _capture(application, product, "effective-root-1", b"root 1")

    def first_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="601919.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            instrument_identifiers=(
                InstrumentIdentifier(
                    instrument_identifier_id=identifier_v1_id,
                    instrument_id=instrument_id,
                    identifier_scheme="TICKER",
                    identifier_value="sh.601919",
                    effective_from=effective_from,
                    effective_to=None,
                    revision=1,
                    supersedes_identifier_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_v1_id,
                    classification_scheme="INDEX",
                    classification_code="CSI300",
                    display_name="CSI 300",
                    revision=1,
                    effective_from=effective_from,
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=membership_v1_id,
                    classification_id=classification_v1_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=effective_from,
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
            ),
        )

    first_result = application.normalize(
        first.capture.capture_id,
        FixedNormalizer(first_batch),
        _context("normalize-effective-root-1", "NORMALIZE_MARKET_PIT"),
    )
    first_members = queries.classification_members_as_of(
        classification_scheme="INDEX",
        classification_code="CSI300",
        effective_time=cutover_at + timedelta(seconds=1),
        decision_time=first_result.decision_visible_at,
    )
    assert first_members.status is ClassificationEvidenceStatus.AVAILABLE
    assert first_members.members == (InstrumentId.parse(instrument_id),)

    closed = _capture(application, product, "effective-root-close", b"close root")
    identifier_v2_id = uuid4()
    membership_v2_id = uuid4()

    def closing_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instrument_identifiers=(
                InstrumentIdentifier(
                    instrument_identifier_id=identifier_v2_id,
                    instrument_id=instrument_id,
                    identifier_scheme="TICKER",
                    identifier_value="sh.601919",
                    effective_from=effective_from,
                    effective_to=cutover_at,
                    revision=2,
                    supersedes_identifier_id=identifier_v1_id,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_v2_id,
                    classification_scheme="INDEX",
                    classification_code="CSI300",
                    display_name="CSI 300 corrected",
                    revision=2,
                    effective_from=effective_from,
                    effective_to=None,
                    supersedes_classification_id=classification_v1_id,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=membership_v2_id,
                    classification_id=classification_v2_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=effective_from,
                    effective_to=cutover_at,
                    revision=2,
                    supersedes_membership_revision_id=membership_v1_id,
                ),
            ),
        )

    closed_result = application.normalize(
        closed.capture.capture_id,
        FixedNormalizer(closing_batch),
        _context("normalize-effective-root-close", "NORMALIZE_MARKET_PIT"),
    )
    after_cutover = cutover_at + timedelta(seconds=1)
    assert queries.instrument_for_identifier_as_of(
        identifier_scheme="TICKER",
        identifier_value="sh.601919",
        effective_time=after_cutover,
        decision_time=closed_result.decision_visible_at,
    ) is None
    closed_members = queries.classification_members_as_of(
        classification_scheme="INDEX",
        classification_code="CSI300",
        effective_time=after_cutover,
        decision_time=closed_result.decision_visible_at,
    )
    assert closed_members.status is ClassificationEvidenceStatus.AVAILABLE
    assert closed_members.members == ()

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE mra.artifact SET integrity_state = 'CORRUPT' "
            "WHERE artifact_id = %s",
            (closed.capture.artifact_id,),
        )
    with pytest.raises(ArtifactIntegrityError):
        queries.instrument_for_identifier_as_of(
            identifier_scheme="TICKER",
            identifier_value="sh.601919",
            effective_time=after_cutover,
            decision_time=closed_result.decision_visible_at,
        )
    with pytest.raises(ArtifactIntegrityError, match="Classification evidence"):
        queries.classification_members_as_of(
            classification_scheme="INDEX",
            classification_code="CSI300",
            effective_time=after_cutover,
            decision_time=closed_result.decision_visible_at,
        )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE mra.artifact SET integrity_state = 'AVAILABLE' "
            "WHERE artifact_id = %s",
            (closed.capture.artifact_id,),
        )

    fork = _capture(application, product, "effective-root-fork", b"fork")

    def fork_batch(capture) -> NormalizationBatch:
        classification_v3_id = uuid4()
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            classifications=(
                ClassificationRevision(
                    classification_id=classification_v3_id,
                    classification_scheme="INDEX",
                    classification_code="CSI300",
                    display_name="CSI 300 third metadata revision",
                    revision=3,
                    effective_from=effective_from,
                    effective_to=None,
                    supersedes_classification_id=classification_v2_id,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
                    classification_id=classification_v3_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.NOT_MEMBER,
                    effective_from=effective_from,
                    effective_to=cutover_at,
                    revision=2,
                    supersedes_membership_revision_id=membership_v1_id,
                ),
            ),
        )

    with pytest.raises(RuntimeStateConflictError, match="canonical invariants"):
        application.normalize(
            fork.capture.capture_id,
            FixedNormalizer(fork_batch),
            _context("normalize-effective-root-fork", "NORMALIZE_MARKET_PIT"),
        )

    replacement = _capture(
        application,
        product,
        "effective-root-replacement",
        b"replacement root",
    )

    def replacement_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instrument_identifiers=(
                InstrumentIdentifier(
                    instrument_identifier_id=uuid4(),
                    instrument_id=instrument_id,
                    identifier_scheme="TICKER",
                    identifier_value="sh.601920",
                    effective_from=cutover_at,
                    effective_to=None,
                    revision=1,
                    supersedes_identifier_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
            classification_memberships=(
                ClassificationMembershipRevision(
                    membership_revision_id=uuid4(),
                    classification_id=classification_v2_id,
                    instrument_id=instrument_id,
                    source_capture_id=capture.capture_id,
                    membership_status=MembershipStatus.MEMBER,
                    effective_from=cutover_at,
                    effective_to=None,
                    revision=1,
                    supersedes_membership_revision_id=None,
                ),
            ),
        )

    replacement_result = application.normalize(
        replacement.capture.capture_id,
        FixedNormalizer(replacement_batch),
        _context("normalize-effective-root-replacement", "NORMALIZE_MARKET_PIT"),
    )
    assert queries.instrument_for_identifier_as_of(
        identifier_scheme="TICKER",
        identifier_value="sh.601920",
        effective_time=after_cutover,
        decision_time=replacement_result.decision_visible_at,
    ) == InstrumentId.parse(instrument_id)
    replacement_members = queries.classification_members_as_of(
        classification_scheme="INDEX",
        classification_code="CSI300",
        effective_time=after_cutover,
        decision_time=replacement_result.decision_visible_at,
    )
    assert replacement_members.status is ClassificationEvidenceStatus.AVAILABLE
    assert replacement_members.members == (InstrumentId.parse(instrument_id),)


def test_corporate_action_revision_selects_current_ex_session_before_filtering(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    instrument_id = uuid4()
    old_session_id = uuid4()
    new_session_id = uuid4()
    action_v1_id = uuid4()
    first = _capture(application, product, "action-date-v1", b"action v1")

    def first_batch(capture) -> NormalizationBatch:
        old_session = _session(
            session_id=old_session_id,
            session_date=date(2026, 8, 28),
            capture_id=capture.capture_id,
        )
        new_session = _session(
            session_id=new_session_id,
            session_date=date(2026, 8, 29),
            capture_id=capture.capture_id,
        )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="510300.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.ETF,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(old_session, new_session),
            corporate_actions=(
                CorporateActionRevision(
                    corporate_action_revision_id=action_v1_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    action_key="510300:2026:CASH_DIVIDEND",
                    action_type=CorporateActionType.CASH_DIVIDEND,
                    ex_session_id=old_session_id,
                    record_session_id=old_session_id,
                    pay_session_id=old_session_id,
                    cash_amount_per_share=_cny("0.10"),
                    ratio_factor=None,
                    subscription_price=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    first_result = application.normalize(
        first.capture.capture_id,
        FixedNormalizer(first_batch),
        _context("normalize-action-date-v1", "NORMALIZE_MARKET_PIT"),
    )
    assert len(
        queries.corporate_actions_as_of(
            instrument_id=instrument_id,
            ex_session_id=old_session_id,
            decision_time=first_result.decision_visible_at,
        )
    ) == 1

    correction = _capture(application, product, "action-date-v2", b"action v2")
    action_v2_id = uuid4()

    def correction_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            corporate_actions=(
                CorporateActionRevision(
                    corporate_action_revision_id=action_v2_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    action_key="510300:2026:CASH_DIVIDEND",
                    action_type=CorporateActionType.CASH_DIVIDEND,
                    ex_session_id=new_session_id,
                    record_session_id=old_session_id,
                    pay_session_id=new_session_id,
                    cash_amount_per_share=_cny("0.10"),
                    ratio_factor=None,
                    subscription_price=None,
                    revision=2,
                    supersedes_revision_id=action_v1_id,
                ),
            ),
        )

    correction_result = application.normalize(
        correction.capture.capture_id,
        FixedNormalizer(correction_batch),
        _context("normalize-action-date-v2", "NORMALIZE_MARKET_PIT"),
    )
    assert queries.corporate_actions_as_of(
        instrument_id=instrument_id,
        ex_session_id=old_session_id,
        decision_time=correction_result.decision_visible_at,
    ) == ()
    corrected = queries.corporate_actions_as_of(
        instrument_id=instrument_id,
        ex_session_id=new_session_id,
        decision_time=correction_result.decision_visible_at,
    )
    assert len(corrected) == 1
    assert corrected[0].corporate_action_revision_id == action_v2_id
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE mra.artifact SET integrity_state = 'CORRUPT' "
            "WHERE artifact_id = %s",
            (correction.capture.artifact_id,),
        )
    with pytest.raises(ArtifactIntegrityError, match="CorporateAction evidence"):
        queries.corporate_actions_as_of(
            instrument_id=instrument_id,
            ex_session_id=old_session_id,
            decision_time=correction_result.decision_visible_at,
        )
    with pytest.raises(ArtifactIntegrityError, match="CorporateAction evidence"):
        queries.corporate_actions_as_of(
            instrument_id=instrument_id,
            ex_session_id=new_session_id,
            decision_time=correction_result.decision_visible_at,
        )


def test_provider_reported_product_failure_records_unknown_availability(
    market_stack,
) -> None:
    application, _, _, pool, provider, _, _ = market_stack
    product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="reported_availability_product",
        revision=1,
        payload_family="REPORTED_MARKET_SOURCE",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.PROVIDER_REPORTED,
        fact_kinds=(MarketFactKind.INSTRUMENT,),
        instrument_fact_kinds=(),
        bar_timeframes=(),
        price_bases=(),
    )
    application.register_provider_product(
        product,
        _context("register-reported-product", "REGISTER_PROVIDER_PRODUCT"),
    )
    failed = application.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="reported-product-failure",
            resource="fixture://reported-product-failure",
            request_headers_hash="c" * 64,
        ),
        AlwaysFailingProvider(),
        _context("capture-reported-product-failure", "CAPTURE_PROVIDER_RESPONSE"),
    )
    assert failed.capture.status is CaptureStatus.PROVIDER_FAILURE
    assert (
        failed.capture.temporal.source_availability_status
        is SourceAvailabilityStatus.UNKNOWN
    )
    assert failed.capture.temporal.source_available_at is None
    gaps = PostgresMarketQueries(
        pool,
        provider_product_id=product.provider_product_id,
    ).source_gaps_as_of(
        capture_id=failed.capture.capture_id,
        fact_kind=GapFactKind.DATA_CAPTURE,
        decision_time=failed.capture.temporal.decision_visible_at,
    )
    assert len(gaps) == 1
    assert gaps[0].gap_kind is GapKind.PROVIDER_FAILURE


def test_reverse_order_multi_root_normalizations_use_one_global_lock_order(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    instrument_a = uuid4()
    instrument_b = uuid4()
    classification_id = uuid4()
    setup = _capture(application, product, "lock-order-setup", b"setup")

    def setup_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_a,
                    canonical_code="600000.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
                Instrument(
                    instrument_id=instrument_b,
                    canonical_code="600001.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            classifications=(
                ClassificationRevision(
                    classification_id=classification_id,
                    classification_scheme="INDEX",
                    classification_code="LOCK_ORDER",
                    display_name="Lock order fixture",
                    revision=1,
                    effective_from=datetime(2010, 1, 1, tzinfo=UTC),
                    effective_to=None,
                    supersedes_classification_id=None,
                    source_capture_id=capture.capture_id,
                ),
            ),
        )

    application.normalize(
        setup.capture.capture_id,
        FixedNormalizer(setup_batch),
        _context("normalize-lock-order-setup", "NORMALIZE_MARKET_PIT"),
    )
    capture_a = _capture(application, product, "lock-order-a", b"batch a")
    capture_b = _capture(application, product, "lock-order-b", b"batch b")
    barrier = Barrier(2)

    def batch_for(
        capture,
        *,
        instrument_id,
        interval_start: datetime,
        reverse: bool,
    ) -> NormalizationBatch:
        interval_end = interval_start + timedelta(days=365)
        identifiers = (
            InstrumentIdentifier(
                instrument_identifier_id=uuid4(),
                instrument_id=instrument_id,
                identifier_scheme="EXCHANGE_CODE",
                identifier_value=f"exchange-{instrument_id}",
                effective_from=interval_start,
                effective_to=interval_end,
                revision=1,
                supersedes_identifier_id=None,
                source_capture_id=capture.capture_id,
            ),
            InstrumentIdentifier(
                instrument_identifier_id=uuid4(),
                instrument_id=instrument_id,
                identifier_scheme="PROVIDER_CODE",
                identifier_value=f"provider-{instrument_id}",
                effective_from=interval_start,
                effective_to=interval_end,
                revision=1,
                supersedes_identifier_id=None,
                source_capture_id=capture.capture_id,
            ),
        )
        memberships = tuple(
            ClassificationMembershipRevision(
                membership_revision_id=uuid4(),
                classification_id=classification_id,
                instrument_id=item,
                source_capture_id=capture.capture_id,
                membership_status=MembershipStatus.MEMBER,
                effective_from=interval_start,
                effective_to=interval_end,
                revision=1,
                supersedes_membership_revision_id=None,
            )
            for item in (instrument_a, instrument_b)
        )
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instrument_identifiers=tuple(reversed(identifiers)) if reverse else identifiers,
            classification_memberships=(
                tuple(reversed(memberships)) if reverse else memberships
            ),
        )

    normalizer_a = BarrierNormalizer(
        barrier,
        lambda capture: batch_for(
            capture,
            instrument_id=instrument_a,
            interval_start=datetime(2020, 1, 1, tzinfo=UTC),
            reverse=True,
        ),
    )
    normalizer_b = BarrierNormalizer(
        barrier,
        lambda capture: batch_for(
            capture,
            instrument_id=instrument_b,
            interval_start=datetime(2022, 1, 1, tzinfo=UTC),
            reverse=False,
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(
                application.normalize,
                capture_a.capture.capture_id,
                normalizer_a,
                _context("normalize-lock-order-a", "NORMALIZE_MARKET_PIT"),
            ),
            executor.submit(
                application.normalize,
                capture_b.capture.capture_id,
                normalizer_b,
                _context("normalize-lock-order-b", "NORMALIZE_MARKET_PIT"),
            ),
        )
        results = tuple(future.result(timeout=10) for future in futures)
    assert all(result.aggregate_kind == "MARKET_NORMALIZATION" for result in results)
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.instrument_identifier "
            "WHERE source_capture_id IN (%s, %s)",
            (capture_a.capture.capture_id, capture_b.capture.capture_id),
        ).fetchone() == (4,)
        assert connection.execute(
            "SELECT count(*) FROM mra.classification_membership_revision "
            "WHERE source_capture_id IN (%s, %s)",
            (capture_a.capture.capture_id, capture_b.capture.capture_id),
        ).fetchone() == (4,)


def test_same_capture_concurrent_bar_and_gap_cannot_both_commit(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    instrument_id = uuid4()
    session_id = uuid4()
    end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)
    setup = _capture(application, product, "bar-gap-setup", b"setup")

    def setup_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="600000.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(
                _session(
                    session_id=session_id,
                    session_date=date(2026, 8, 28),
                    capture_id=capture.capture_id,
                ),
            ),
        )

    application.normalize(
        setup.capture.capture_id,
        FixedNormalizer(setup_batch),
        _context("normalize-bar-gap-setup", "NORMALIZE_MARKET_PIT"),
    )
    target = _capture(application, product, "bar-gap-target", b"one observation")
    barrier = Barrier(2)

    def bar_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=_cny("10"),
                    high=_cny("10"),
                    low=_cny("10"),
                    close=_cny("10"),
                    volume=_shares("0"),
                    turnover=None,
                ),
            ),
        )

    def gap_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            gaps=(
                SourceGap(
                    gap_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    gap_kind=GapKind.MISSING,
                    reason_code=GapReasonCode.EXACT_BAR_MISSING,
                    fact_kind=GapFactKind.MARKET_BAR,
                    instrument_fact_kind=None,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    detail=None,
                ),
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(
                application.normalize,
                target.capture.capture_id,
                BarrierNormalizer(barrier, bar_batch),
                _context("normalize-bar-gap-bar", "NORMALIZE_MARKET_PIT"),
            ),
            executor.submit(
                application.normalize,
                target.capture.capture_id,
                BarrierNormalizer(barrier, gap_batch),
                _context("normalize-bar-gap-gap", "NORMALIZE_MARKET_PIT"),
            ),
        )
        outcomes: list[object] = []
        for future in futures:
            try:
                outcomes.append(future.result(timeout=10))
            except RuntimeStateConflictError as exc:
                outcomes.append(exc)
    assert sum(isinstance(item, RuntimeStateConflictError) for item in outcomes) == 1
    with psycopg.connect(database_url) as connection:
        bar_count = connection.execute(
            "SELECT count(*) FROM mra.market_bar_revision WHERE capture_id = %s",
            (target.capture.capture_id,),
        ).fetchone()
        gap_count = connection.execute(
            "SELECT count(*) FROM mra.source_gap WHERE capture_id = %s",
            (target.capture.capture_id,),
        ).fetchone()
        assert bar_count is not None and gap_count is not None
        assert int(bar_count[0]) + int(gap_count[0]) == 1


def test_financial_boundary_commits_exactly_and_postgres_rejects_rounding(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    captured = _capture(application, product, "financial-boundary", b"bounded numerics")
    instrument_id = uuid4()
    session_id = uuid4()
    bar_id = uuid4()
    end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)
    max_money = _cny("99999999999999999999.1234567890")
    max_quantity = _shares("9999999999999999999999999999.1234567890")

    def batch_factory(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="600000.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(
                _session(
                    session_id=session_id,
                    session_date=date(2026, 8, 28),
                    capture_id=capture.capture_id,
                ),
            ),
            bars=(
                MarketBarRevision(
                    bar_revision_id=bar_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    price_basis=PriceBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=max_money,
                    high=max_money,
                    low=max_money,
                    close=max_money,
                    volume=max_quantity,
                    turnover=None,
                ),
            ),
        )

    normalized = application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(batch_factory),
        _context("normalize-financial-boundary", "NORMALIZE_MARKET_PIT"),
    )
    stored = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=normalized.decision_visible_at,
    )
    assert stored is not None
    assert stored.close == max_money
    assert stored.volume == max_quantity

    rounded = Decimal("99999999999999999999.12345678901")
    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation, match="money_bounds"):
            with connection.transaction():
                connection.execute(
                    """
                    WITH database_clock AS (
                        SELECT clock_timestamp() AS observed_at
                    )
                    INSERT INTO mra.market_bar_revision (
                        bar_revision_id, provider_product_id, capture_id,
                        instrument_id, session_id, timeframe, price_basis,
                        event_start, event_end, revision,
                        supersedes_revision_id, open_value, high_value,
                        low_value, close_value, volume_value, turnover_value,
                        recorded_at, known_at, decision_visible_at
                    )
                    SELECT %s, prior.provider_product_id, prior.capture_id,
                           prior.instrument_id, prior.session_id, prior.timeframe,
                           prior.price_basis, prior.event_start, prior.event_end,
                           2, prior.bar_revision_id, %s, %s, %s, %s,
                           prior.volume_value, NULL, observed_at, observed_at,
                           observed_at
                    FROM mra.market_bar_revision AS prior
                    CROSS JOIN database_clock
                    WHERE prior.bar_revision_id = %s
                    """,
                    (uuid4(), rounded, rounded, rounded, rounded, bar_id),
                )


def test_effective_fact_timeline_closes_replaces_and_rejects_overlap(
    market_stack,
) -> None:
    application, queries, _, _, _, product, database_url = market_stack
    instrument_id = uuid4()
    listing_v1_id = uuid4()
    shares_v1_id = uuid4()
    effective_from = datetime(2020, 1, 1, tzinfo=UTC)
    cutover_at = datetime(2026, 8, 31, tzinfo=UTC)
    first = _capture(application, product, "fact-timeline-v1", b"timeline v1")

    def first_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="601919.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.EQUITY,
                    currency="CNY",
                    source_capture_id=capture.capture_id,
                ),
            ),
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=listing_v1_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.LISTED,
                    effective_from=effective_from,
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            instrument_facts=(
                InstrumentFactRevision(
                    fact_revision_id=shares_v1_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=None,
                    fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
                    evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
                    event_start=effective_from,
                    event_end=None,
                    value=_shares("1000"),
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    first_result = application.normalize(
        first.capture.capture_id,
        FixedNormalizer(first_batch),
        _context("normalize-fact-timeline-v1", "NORMALIZE_MARKET_PIT"),
    )
    after_cutover = cutover_at + timedelta(seconds=1)
    assert queries.listing_status_as_of(
        instrument_id=instrument_id,
        effective_time=after_cutover,
        decision_time=first_result.decision_visible_at,
    ) is ListingStatus.LISTED

    closing = _capture(application, product, "fact-timeline-close", b"timeline close")
    listing_v2_id = uuid4()
    shares_v2_id = uuid4()

    def closing_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=listing_v2_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.LISTED,
                    effective_from=effective_from,
                    effective_to=cutover_at,
                    revision=2,
                    supersedes_revision_id=listing_v1_id,
                ),
            ),
            instrument_facts=(
                InstrumentFactRevision(
                    fact_revision_id=shares_v2_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=None,
                    fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
                    evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
                    event_start=effective_from,
                    event_end=cutover_at,
                    value=_shares("1000"),
                    revision=2,
                    supersedes_revision_id=shares_v1_id,
                ),
            ),
        )

    closing_result = application.normalize(
        closing.capture.capture_id,
        FixedNormalizer(closing_batch),
        _context("normalize-fact-timeline-close", "NORMALIZE_MARKET_PIT"),
    )
    assert queries.listing_status_as_of(
        instrument_id=instrument_id,
        effective_time=after_cutover,
        decision_time=closing_result.decision_visible_at,
    ) is None
    assert queries.instrument_fact_as_of(
        instrument_id=instrument_id,
        fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
        evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
        event_time=after_cutover,
        decision_time=closing_result.decision_visible_at,
    ) is None

    replacement = _capture(
        application,
        product,
        "fact-timeline-replacement",
        b"timeline replacement",
    )

    def replacement_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.DELISTED,
                    effective_from=cutover_at,
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
            instrument_facts=(
                InstrumentFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=None,
                    fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
                    evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
                    event_start=cutover_at,
                    event_end=None,
                    value=_shares("900"),
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    replacement_result = application.normalize(
        replacement.capture.capture_id,
        FixedNormalizer(replacement_batch),
        _context("normalize-fact-timeline-replacement", "NORMALIZE_MARKET_PIT"),
    )
    assert queries.listing_status_as_of(
        instrument_id=instrument_id,
        effective_time=after_cutover,
        decision_time=replacement_result.decision_visible_at,
    ) is ListingStatus.DELISTED
    shares = queries.instrument_fact_as_of(
        instrument_id=instrument_id,
        fact_kind=NumericInstrumentFactKind.TOTAL_SHARES,
        evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
        event_time=after_cutover,
        decision_time=replacement_result.decision_visible_at,
    )
    assert shares is not None and shares.value == _shares("900")

    overlap = _capture(application, product, "fact-timeline-overlap", b"overlap")

    def overlap_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            lifecycle_status_facts=(
                InstrumentLifecycleFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    fact_kind=InstrumentFactKind.LISTING_STATUS,
                    status=ListingStatus.UNKNOWN,
                    effective_from=cutover_at - timedelta(days=1),
                    effective_to=None,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    with pytest.raises(RuntimeStateConflictError, match="canonical invariants"):
        application.normalize(
            overlap.capture.capture_id,
            FixedNormalizer(overlap_batch),
            _context("normalize-fact-timeline-overlap", "NORMALIZE_MARKET_PIT"),
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.instrument_fact_revision "
            "WHERE capture_id = %s",
            (overlap.capture.capture_id,),
        ).fetchone() == (0,)


def test_instrument_fact_money_must_match_canonical_instrument_currency(
    market_stack,
) -> None:
    application, _, _, _, _, product, database_url = market_stack
    setup = _capture(application, product, "fact-currency-setup", b"currency setup")
    instrument_id = uuid4()
    session_id = uuid4()
    session = _session(
        session_id=session_id,
        session_date=date(2026, 8, 28),
        capture_id=setup.capture.capture_id,
    )

    def setup_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="USD_TEST.XSHG",
                    exchange="XSHG",
                    instrument_type=InstrumentType.INDEX,
                    currency="USD",
                    source_capture_id=capture.capture_id,
                ),
            ),
            trading_sessions=(session,),
        )

    application.normalize(
        setup.capture.capture_id,
        FixedNormalizer(setup_batch),
        _context("normalize-fact-currency-setup", "NORMALIZE_MARKET_PIT"),
    )
    captured = _capture(application, product, "fact-currency", b"currency mismatch")

    def mismatched_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            source_provider_product_id=capture.provider_product_id,
            instrument_facts=(
                InstrumentFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    fact_kind=NumericInstrumentFactKind.REFERENCE_PRICE,
                    evidence_scope=EvidenceScope.DECISION_SESSION,
                    event_start=session.open_at,
                    event_end=session.close_at,
                    value=_cny("10"),
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    with pytest.raises(RuntimeStateConflictError, match="currency differs"):
        application.normalize(
            captured.capture.capture_id,
            FixedNormalizer(mismatched_batch),
            _context("normalize-fact-currency", "NORMALIZE_MARKET_PIT"),
        )
    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.instrument_fact_revision WHERE capture_id = %s",
            (captured.capture.capture_id,),
        ).fetchone() == (0,)
        with pytest.raises(psycopg.errors.CheckViolation, match="currency does not match"):
            with connection.transaction():
                connection.execute(
                    """
                    WITH database_clock AS (
                        SELECT clock_timestamp() AS observed_at
                    )
                    INSERT INTO mra.instrument_fact_revision (
                        fact_revision_id, provider_product_id, capture_id,
                        instrument_id, session_id, fact_kind, evidence_scope,
                        event_start, event_end, value_kind, numeric_value,
                        unit_code, revision, supersedes_revision_id,
                        recorded_at, known_at, decision_visible_at
                    )
                    SELECT %s, %s, %s, %s, %s, 'REFERENCE_PRICE',
                           'DECISION_SESSION', %s, %s, 'DECIMAL', 10,
                           'CNY', 1, NULL, observed_at, observed_at, observed_at
                    FROM database_clock
                    """,
                    (
                        uuid4(),
                        product.provider_product_id,
                        captured.capture.capture_id,
                        instrument_id,
                        session_id,
                        session.open_at,
                        session.close_at,
                    ),
                )


def _plan_relations(plan: dict) -> set[str]:
    relations = {str(plan["Relation Name"])} if "Relation Name" in plan else set()
    for child in plan.get("Plans", ()):
        relations.update(_plan_relations(child))
    return relations
