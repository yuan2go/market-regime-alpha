from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import ArtifactStoreError, LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.market import PostgresMarketQueries
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.domain import (
    AdjustmentBasis,
    BarTimeframe,
    ClassificationMembershipRevision,
    ClassificationRevision,
    CorporateActionRevision,
    DecisionReferenceStatus,
    GapKind,
    Instrument,
    InstrumentFactRevision,
    InstrumentFactValueKind,
    InstrumentIdentifier,
    MarketBarRevision,
    NormalizationBatch,
    Provider,
    ProviderProduct,
    SecurityStatus,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    SourceGap,
    TradingSession,
)
from market_regime_alpha.market.ports import CaptureRequest, ProviderResponse
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    IdempotencyKeyReusedError,
)


UTC = timezone.utc


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


class FixedNormalizer:
    def __init__(self, batch_factory) -> None:
        self._batch_factory = batch_factory
        self.seen_content: bytes | None = None

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
        self.seen_content = content
        return self._batch_factory(capture)


@pytest.fixture
def market_stack(target_database_url: str, tmp_path):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    store = LocalArtifactStore(tmp_path / "market-artifacts")
    uow_provider = PostgresMarketUnitOfWorkProvider(pool)
    application = MarketApplication(store, uow_provider)
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


def _capture(application: MarketApplication, product: ProviderProduct, key: str, content: bytes):
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
    assert provider.calls == 1
    return result


def test_capture_binds_exact_artifact_temporal_axes_receipt_and_audit_atomically(
    market_stack,
) -> None:
    application, _, store, _, _, product, database_url = market_stack
    exact = b'{"code":"sh.601919","close":"15.32"}\n'

    result = _capture(application, product, "2026-08-28-1455", exact)
    replayed = _capture(application, product, "2026-08-28-1455", exact)

    assert result.replayed is False
    assert replayed.replayed is True
    assert replayed.capture.capture_id == result.capture.capture_id
    assert result.capture.temporal.source_available_at is None
    assert result.capture.temporal.decision_visible_at == result.capture.temporal.known_at
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
    assert row[:3] == ("CAPTURED", "UNKNOWN", None)
    assert row[3] == result.capture.temporal.capture_completed_at
    assert row[5] == max(row[3], row[4])
    assert row[5] == row[6] == result.capture.temporal.known_at
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
    assert len(store.list_objects()) == 2
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM mra.data_capture").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM mra.artifact").fetchone() == (1,)


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


def test_corrupt_capture_artifact_blocks_normalization_before_database_mutation(
    market_stack,
) -> None:
    application, _, store, _, _, product, database_url = market_stack
    captured = _capture(application, product, "corrupt-before-normalize", b"exact bytes")
    assert captured.artifact is not None
    store.object_path(captured.artifact.content_sha256).write_bytes(b"tampered")

    with pytest.raises(ArtifactStoreError, match="cannot be read"):
        application.normalize(
            captured.capture.capture_id,
            FixedNormalizer(
                lambda capture: NormalizationBatch(
                    source_capture_id=capture.capture_id
                )
            ),
            _context("normalize-corrupt", "NORMALIZE_MARKET_PIT"),
        )

    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.command_receipt WHERE command_kind = 'NORMALIZE_MARKET_PIT'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM mra.market_bar_revision"
        ).fetchone() == (0,)


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
            instrument_type="EQUITY",
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
                    membership_status="MEMBER",
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
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=event_end - timedelta(minutes=5),
                    event_end=event_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("15.10"),
                    high=Decimal("15.40"),
                    low=Decimal("15.00"),
                    close=Decimal("15.32"),
                    volume=Decimal("0"),
                    turnover=Decimal("0"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope="DECISION_SESSION",
                    status=SecurityStatus.ACTIVE,
                    event_start=session.open_at,
                    event_end=session.close_at,
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
                    fact_kind="TOTAL_SHARES",
                    evidence_scope="EFFECTIVE_INTERVAL",
                    event_start=datetime(2026, 1, 1, tzinfo=UTC),
                    event_end=datetime(2027, 1, 1, tzinfo=UTC),
                    value_kind=InstrumentFactValueKind.DECIMAL,
                    status_value=None,
                    numeric_value=Decimal("12259652922"),
                    text_value=None,
                    unit_code="SHARES",
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
                    action_type="CASH_DIVIDEND",
                    ex_session_id=session_id,
                    payable_at=datetime(2026, 9, 1, tzinfo=UTC),
                    cash_amount=Decimal("0.19"),
                    ratio_factor=None,
                    currency="CNY",
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

    bar = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert bar is not None
    assert bar.close == Decimal("15.3200000000")
    assert bar.volume == Decimal("0E-10")
    assert queries.instrument_for_identifier_as_of(
        identifier_scheme="TICKER",
        identifier_value="sh.601919",
        effective_time=event_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    ) == instrument_id
    assert queries.classification_members_as_of(
        classification_scheme="INDUSTRY",
        classification_code="MARINE_TRANSPORT",
        effective_time=event_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    ) == (instrument_id,)
    reference = queries.decision_reference_1455(
        instrument_id=instrument_id,
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert reference.status is DecisionReferenceStatus.AVAILABLE
    assert reference.bar == bar
    actions = queries.corporate_actions_as_of(
        instrument_id=instrument_id,
        ex_session_id=session_id,
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert len(actions) == 1
    assert actions[0].cash_amount == Decimal("0.1900000000")
    shares = queries.instrument_fact_as_of(
        instrument_id=instrument_id,
        fact_kind="TOTAL_SHARES",
        evidence_scope="EFFECTIVE_INTERVAL",
        event_time=event_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert shares is not None
    assert shares.numeric_value == Decimal("12259652922.0000000000")

    exact_plan = queries.explain_exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert {"market_bar_revision", "data_capture", "artifact"} <= _plan_relations(
        exact_plan["Plan"]
    )
    assert exact_plan["Execution Time"] >= 0

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
        session_plan = connection.execute(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT session_id FROM mra.trading_session
            WHERE exchange = 'XSHG' AND session_date = DATE '2026-08-28'
            """
        ).fetchone()[0][0]
        classification_plan = connection.execute(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT membership.instrument_id
            FROM mra.classification AS classification
            JOIN mra.classification_membership_revision AS membership
              ON membership.classification_id = classification.classification_id
            WHERE classification.classification_scheme = 'INDUSTRY'
              AND classification.classification_code = 'MARINE_TRANSPORT'
              AND membership.effective_from <= %s
            """,
            (event_end,),
        ).fetchone()[0][0]
    assert counts == (1, 1, 1, 1, 1, 1, 2, 1)
    assert set(index_definitions) == {
        "market_bar_exact_asof_idx",
        "trading_session_calendar_idx",
        "classification_asof_idx",
        "classification_membership_classification_idx",
        "instrument_identifier_asof_idx",
    }
    assert "adjustment_basis" in index_definitions["market_bar_exact_asof_idx"]
    assert "decision_visible_at" not in index_definitions["market_bar_exact_asof_idx"]
    assert _plan_relations(session_plan["Plan"]) == {"trading_session"}
    assert {
        "classification",
        "classification_membership_revision",
    } <= _plan_relations(classification_plan["Plan"])


def test_decision_reference_does_not_infer_suspension_from_zero_volume_or_flat_price(
    market_stack,
) -> None:
    application, queries, _, _, _, product, _ = market_stack
    captured = _capture(application, product, "flat-zero", b"flat")
    instrument_id = uuid4()
    session_id = uuid4()
    end = datetime(2026, 8, 28, 6, 55, tzinfo=UTC)

    def batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="510300.XSHG",
                    exchange="XSHG",
                    instrument_type="ETF",
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
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("4.000"),
                    high=Decimal("4.000"),
                    low=Decimal("4.000"),
                    close=Decimal("4.000"),
                    volume=Decimal("0"),
                    turnover=Decimal("0"),
                ),
            ),
        )

    application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(batch),
        _context("normalize-flat-zero", "NORMALIZE_MARKET_PIT"),
    )
    reference = queries.decision_reference_1455(
        instrument_id=instrument_id,
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert reference.status is DecisionReferenceStatus.AVAILABLE


def test_exact_1455_placeholder_blocks_previous_session_and_daily_fallbacks(
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
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="601919.XSHG",
                    exchange="XSHG",
                    instrument_type="EQUITY",
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
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=prior_end - timedelta(minutes=5),
                    event_end=prior_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("15"),
                    high=Decimal("15"),
                    low=Decimal("15"),
                    close=Decimal("15"),
                    volume=Decimal("0"),
                    turnover=None,
                ),
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=current_session_id,
                    timeframe=BarTimeframe.DAILY,
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=current.open_at,
                    event_end=current.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("15"),
                    high=Decimal("15"),
                    low=Decimal("15"),
                    close=Decimal("15"),
                    volume=Decimal("0"),
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
                    evidence_scope="PRIOR_SESSION",
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
                    reason_code="NULL_OHLC_PLACEHOLDER",
                    fact_kind="MARKET_BAR",
                    timeframe=BarTimeframe.MINUTE_5,
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=current_end - timedelta(minutes=5),
                    event_end=current_end,
                    detail="raw bytes retained; no legal bar emitted",
                ),
            ),
        )

    application.normalize(
        captured.capture.capture_id,
        FixedNormalizer(batch),
        _context("normalize-placeholder", "NORMALIZE_MARKET_PIT"),
    )
    assert queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=current_session_id,
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
        event_start=current_end - timedelta(minutes=5),
        event_end=current_end,
        decision_time=captured.capture.temporal.decision_visible_at,
    ) is None
    reference = queries.decision_reference_1455(
        instrument_id=instrument_id,
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=captured.capture.temporal.decision_visible_at,
    )
    assert reference.status is DecisionReferenceStatus.UNAVAILABLE
    assert reference.reason_code == "NULL_OHLC_PLACEHOLDER"
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
            bars=(
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=current_session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=current_end - timedelta(minutes=5),
                    event_end=current_end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("15.10"),
                    high=Decimal("15.20"),
                    low=Decimal("15.00"),
                    close=Decimal("15.15"),
                    volume=Decimal("100"),
                    turnover=Decimal("1515"),
                ),
            ),
        )

    application.normalize(
        corrected.capture.capture_id,
        FixedNormalizer(corrected_batch),
        _context("normalize-placeholder-corrected", "NORMALIZE_MARKET_PIT"),
    )
    corrected_reference = queries.decision_reference_1455(
        instrument_id=instrument_id,
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=corrected.capture.temporal.decision_visible_at,
    )
    assert corrected_reference.status is DecisionReferenceStatus.AVAILABLE


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
            instruments=(
                Instrument(
                    instrument_id=instrument_id,
                    canonical_code="510300.XSHG",
                    exchange="XSHG",
                    instrument_type="ETF",
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
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("4.00"),
                    high=Decimal("4.00"),
                    low=Decimal("4.00"),
                    close=Decimal("4.00"),
                    volume=Decimal("0"),
                    turnover=Decimal("0"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=first_fact_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope="DECISION_SESSION",
                    status=SecurityStatus.ACTIVE,
                    event_start=session.open_at,
                    event_end=session.close_at,
                    revision=1,
                    supersedes_revision_id=None,
                ),
            ),
        )

    application.normalize(
        first.capture.capture_id,
        FixedNormalizer(first_batch),
        _context("normalize-revision-1", "NORMALIZE_MARKET_PIT"),
    )
    second = _capture(application, product, "revision-2", b"revision 2")
    second_bar_id = uuid4()

    def second_batch(capture) -> NormalizationBatch:
        return NormalizationBatch(
            source_capture_id=capture.capture_id,
            bars=(
                MarketBarRevision(
                    bar_revision_id=second_bar_id,
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=2,
                    supersedes_revision_id=first_bar_id,
                    open=Decimal("4.01"),
                    high=Decimal("4.02"),
                    low=Decimal("4.00"),
                    close=Decimal("4.02"),
                    volume=Decimal("100"),
                    turnover=Decimal("402"),
                ),
                MarketBarRevision(
                    bar_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    timeframe=BarTimeframe.MINUTE_5,
                    adjustment_basis=AdjustmentBasis.FORWARD_ADJUSTED,
                    event_start=end - timedelta(minutes=5),
                    event_end=end,
                    revision=1,
                    supersedes_revision_id=None,
                    open=Decimal("3.90"),
                    high=Decimal("3.91"),
                    low=Decimal("3.89"),
                    close=Decimal("3.91"),
                    volume=Decimal("100"),
                    turnover=Decimal("391"),
                ),
            ),
            security_status_facts=(
                SecurityStatusFactRevision(
                    fact_revision_id=uuid4(),
                    provider_product_id=product.provider_product_id,
                    capture_id=capture.capture_id,
                    instrument_id=instrument_id,
                    session_id=session_id,
                    evidence_scope="DECISION_SESSION",
                    status=SecurityStatus.SUSPENDED,
                    event_start=datetime(2026, 8, 28, 1, 30, tzinfo=UTC),
                    event_end=datetime(2026, 8, 28, 7, tzinfo=UTC),
                    revision=2,
                    supersedes_revision_id=first_fact_id,
                ),
            ),
        )

    application.normalize(
        second.capture.capture_id,
        FixedNormalizer(second_batch),
        _context("normalize-revision-2", "NORMALIZE_MARKET_PIT"),
    )
    first_visible = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=first.capture.temporal.decision_visible_at,
    )
    second_visible = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=second.capture.temporal.decision_visible_at,
    )
    forward = queries.exact_bar_as_of(
        instrument_id=instrument_id,
        session_id=session_id,
        timeframe=BarTimeframe.MINUTE_5,
        adjustment_basis=AdjustmentBasis.FORWARD_ADJUSTED,
        event_start=end - timedelta(minutes=5),
        event_end=end,
        decision_time=second.capture.temporal.decision_visible_at,
    )
    assert first_visible is not None and first_visible.bar_revision_id == first_bar_id
    assert second_visible is not None and second_visible.bar_revision_id == second_bar_id
    assert forward is not None and forward.close == Decimal("3.9100000000")
    before = queries.decision_reference_1455(
        instrument_id=instrument_id,
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=first.capture.temporal.decision_visible_at,
    )
    after = queries.decision_reference_1455(
        instrument_id=instrument_id,
        exchange="XSHG",
        session_date=date(2026, 8, 28),
        decision_time=second.capture.temporal.decision_visible_at,
    )
    assert before.status is DecisionReferenceStatus.AVAILABLE
    assert after.status is DecisionReferenceStatus.UNAVAILABLE
    assert after.reason_code == "CURRENT_SESSION_SUSPENDED"

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="append-only"):
            connection.execute(
                "UPDATE mra.market_bar_revision SET close_value = 5 WHERE bar_revision_id = %s",
                (first_bar_id,),
            )


def _plan_relations(plan: dict) -> set[str]:
    relations = {str(plan["Relation Name"])} if "Relation Name" in plan else set()
    for child in plan.get("Plans", ()):
        relations.update(_plan_relations(child))
    return relations
