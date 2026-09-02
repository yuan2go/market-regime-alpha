from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.archive_uow import (
    PostgresArchiveUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.archive_operations import (
    PostgresArchiveOperationsReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.archive_inspection import (
    PostgresArchiveInspectionPort,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.market.application import (
    ArchiveCommands,
    ArchiveSlicePlan,
    MarketApplication,
    RecordArchiveCaptureObservationRequest,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.domain import (
    ArchiveLane,
    ArchiveSealDisposition,
    BarTimeframe,
    GapFactKind,
    GapKind,
    GapReasonCode,
    MarketFactKind,
    NormalizationBatch,
    PriceBasis,
    Provider,
    ProviderKind,
    ProviderProduct,
    SourceAvailabilityStatus,
    SourceGap,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
)
from market_regime_alpha.runtime.errors import (
    IdempotencyKeyReusedError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.market.ports import (
    CaptureRequest,
    MarketProviderError,
    NormalizerContract,
    ProviderResponse,
)


UTC = timezone.utc


class _BytesProvider:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        return ProviderResponse(
            content=self._content,
            media_type="application/json",
            payload_encoding="UTF-8",
            provider_time=None,
            source_availability_status=SourceAvailabilityStatus.UNKNOWN,
            source_available_at=None,
            limitation_code="HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
        )


class _FailingProvider:
    def capture(self, request: CaptureRequest) -> ProviderResponse:
        raise MarketProviderError("PROVIDER_UNAVAILABLE", "fixture provider unavailable")


class _CapturedGapNormalizer:
    contract = NormalizerContract(
        implementation="tests.wp17p_captured_gap",
        version="1",
        implementation_sha256="f" * 64,
    )

    def normalize(self, capture, content: bytes) -> NormalizationBatch:
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
                    fact_kind=GapFactKind.DATA_CAPTURE,
                    instrument_fact_kind=None,
                    timeframe=None,
                    price_basis=None,
                    event_start=None,
                    event_end=None,
                    detail="fixture normalization disposition",
                ),
            ),
        )


def _context(key: str) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=ActorType.OPERATOR,
        actor_id="wp17p-archive-test",
        reason_code="WP17P_ARCHIVE_TEST",
    )


@pytest.fixture
def archive_stack(target_database_url: str, tmp_path):
    SchemaManager(target_database_url).bootstrap()
    pool = TargetPostgresPool(target_database_url, min_size=0, max_size=8)
    store = LocalArtifactStore(tmp_path / "archive-artifacts")
    artifacts = ArtifactApplication(store, PostgresUnitOfWorkProvider(pool))
    market = MarketApplication(
        store,
        PostgresMarketUnitOfWorkProvider(pool),
        PostgresMarketDatabaseClock(pool),
    )
    provider = Provider(
        provider_id=uuid4(),
        provider_code="wp17p-fixture",
        display_name="WP-17P Fixture",
        provider_kind=ProviderKind.PUBLIC_ENDPOINT,
    )
    product = ProviderProduct(
        provider_product_id=uuid4(),
        provider_id=provider.provider_id,
        product_code="archive_5m_raw",
        revision=1,
        payload_family="HISTORICAL_BAR",
        media_type="application/json",
        payload_encoding="UTF-8",
        source_availability_policy=SourceAvailabilityStatus.UNKNOWN,
        fact_kinds=(MarketFactKind.MARKET_BAR,),
        instrument_fact_kinds=(),
        bar_timeframes=(BarTimeframe.MINUTE_5,),
        price_bases=(PriceBasis.RAW_UNADJUSTED,),
    )
    market.register_provider(provider, _context("provider"))
    market.register_provider_product(product, _context("product"))
    code = artifacts.publish(
        b"wp17p archive code",
        media_type="text/plain",
        context=_context("code-artifact"),
    )
    config = artifacts.publish(
        b'{"scope":"pilot-32"}',
        media_type="application/json",
        context=_context("config-artifact"),
    )
    commands = ArchiveCommands(
        PostgresArchiveUnitOfWorkProvider(pool),
        id_factory=uuid4,
    )
    try:
        yield commands, market, product, code, config, target_database_url
    finally:
        pool.close()


def _request(product, code, config) -> StartMarketArchiveRequest:
    archive_id = UUID("20000000-0000-0000-0000-000000000001")
    return StartMarketArchiveRequest(
        market_archive_id=archive_id,
        archive_code="wp17p-retrospective-pilot",
        lane=ArchiveLane.RETROSPECTIVE_BACKFILL,
        provider_product_id=product.provider_product_id,
        exchange_code="SSE",
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        instrument_scope="ENGINEERING_EXPLORATORY_PILOT_32",
        instrument_scope_sha256=canonical_json_sha256({"salt": "wp17p", "size": 32}),
        event_window_start=datetime(2026, 1, 1, tzinfo=UTC),
        event_window_end=datetime(2026, 9, 2, 23, 59, tzinfo=UTC),
        reserved_free_bytes=2_000_000_000,
        maximum_archive_bytes=2_000_000_000,
        maximum_slice_bytes=50_000_000,
        code_artifact_id=code.artifact_id,
        config_artifact_id=config.artifact_id,
        provenance_sha256="a" * 64,
        slices=(
            ArchiveSlicePlan(
                market_archive_slice_id=UUID("20000000-0000-0000-0000-000000000011"),
                ordinal=1,
                scope_key="sh.600000:2026-01-05",
                event_window_start=datetime(2026, 1, 5, tzinfo=UTC),
                event_window_end=datetime(2026, 1, 5, 23, 59, tzinfo=UTC),
                request_sha256=canonical_json_sha256({"code": "sh.600000", "date": "2026-01-05"}),
                expected_fact_kind="MARKET_BAR",
            ),
            ArchiveSlicePlan(
                market_archive_slice_id=UUID("20000000-0000-0000-0000-000000000012"),
                ordinal=2,
                scope_key="sh.600001:2026-01-05",
                event_window_start=datetime(2026, 1, 5, tzinfo=UTC),
                event_window_end=datetime(2026, 1, 5, 23, 59, tzinfo=UTC),
                request_sha256=canonical_json_sha256({"code": "sh.600001", "date": "2026-01-05"}),
                expected_fact_kind="MARKET_BAR",
            ),
        ),
    )


def test_start_archive_uses_database_time_and_atomically_freezes_full_roster(
    archive_stack,
) -> None:
    commands, _, product, code, config, database_url = archive_stack
    request = _request(product, code, config)
    before = datetime.now(UTC) - timedelta(seconds=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(
                lambda _: commands.start(request, _context("start-archive")),
                range(2),
            )
        )

    after = datetime.now(UTC) + timedelta(seconds=1)
    assert {item.market_archive_id for item in results} == {request.market_archive_id}
    assert {item.replayed for item in results} == {False, True}
    assert {item.slice_count for item in results} == {2}
    assert all(before <= item.archive_start_at <= after for item in results)

    with psycopg.connect(database_url) as connection:
        root = connection.execute(
            """
            SELECT lane, evidence_class, archive_start_at, slice_count,
                   slice_roster_sha256
            FROM mra.market_archive WHERE market_archive_id = %s
            """,
            (request.market_archive_id,),
        ).fetchone()
        slices = connection.execute(
            """
            SELECT ordinal, scope_key FROM mra.market_archive_slice
            WHERE market_archive_id = %s ORDER BY ordinal
            """,
            (request.market_archive_id,),
        ).fetchall()
    assert root is not None
    assert root[:2] == ("RETROSPECTIVE_BACKFILL", "EXPLORATORY_RETROSPECTIVE")
    assert root[3] == 2
    assert slices == [(1, "sh.600000:2026-01-05"), (2, "sh.600001:2026-01-05")]
    inspection_pool = TargetPostgresPool(database_url, min_size=0, max_size=1)
    try:
        contract = PostgresArchiveOperationsReadPort(inspection_pool).load_slice_contract(
            request.market_archive_id,
            request.slices[0].market_archive_slice_id,
        )
    finally:
        inspection_pool.close()
    assert contract.request_sha256 == request.slices[0].request_sha256
    assert contract.terminal_status is None


def test_changed_archive_request_fails_closed_without_partial_roster(archive_stack) -> None:
    commands, _, product, code, config, database_url = archive_stack
    request = _request(product, code, config)
    commands.start(request, _context("changed-start"))

    with pytest.raises(IdempotencyKeyReusedError):
        commands.start(
            replace(request, maximum_archive_bytes=1_900_000_000),
            _context("changed-start"),
        )

    with psycopg.connect(database_url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM mra.market_archive"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM mra.market_archive_slice"
        ).fetchone() == (2,)


def test_prospective_archive_cannot_package_a_historical_window(archive_stack) -> None:
    commands, _, product, code, config, _ = archive_stack
    request = replace(
        _request(product, code, config),
        market_archive_id=uuid4(),
        archive_code="wp17p-prospective-invalid",
        lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS,
    )

    with pytest.raises(ValueError, match="prospective event window cannot precede archive start"):
        commands.start(request, _context("prospective-invalid"))


def test_prospective_slice_remains_open_for_repeated_observations(archive_stack) -> None:
    commands, market, product, code, config, database_url = archive_stack
    future_start = datetime.now(UTC) + timedelta(days=1)
    base = _request(product, code, config)
    archive_id = uuid4()
    slice_plan = replace(
        base.slices[0],
        market_archive_slice_id=uuid4(),
        event_window_start=future_start,
        event_window_end=future_start + timedelta(hours=1),
    )
    capture_request = CaptureRequest(
        provider_product_id=product.provider_product_id,
        capture_key="wp17p-prospective-repeat",
        resource="fixture://wp17p-prospective-repeat",
        request_headers_hash="d" * 64,
    )
    slice_plan = replace(
        slice_plan,
        request_sha256=canonical_json_sha256(capture_request),
    )
    request = replace(
        base,
        market_archive_id=archive_id,
        archive_code="wp17p-prospective-repeat",
        lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS,
        event_window_start=slice_plan.event_window_start,
        event_window_end=slice_plan.event_window_end,
        slices=(slice_plan,),
    )
    started = commands.start(request, _context("prospective-repeat-start"))

    for ordinal in (1, 2):
        captured = market.capture(
            capture_request,
            _BytesProvider(f'{{"observation":{ordinal}}}'.encode()),
            _context(f"prospective-repeat-capture-{ordinal}"),
        )
        market.normalize(
            captured.capture.capture_id,
            _CapturedGapNormalizer(),
            _context(f"prospective-repeat-normalize-{ordinal}"),
        )
        result = commands.record_capture_observation(
            RecordArchiveCaptureObservationRequest(
                market_archive_id=started.market_archive_id,
                market_archive_slice_id=slice_plan.market_archive_slice_id,
                capture_id=captured.capture.capture_id,
                schedule_slot="POST_CLOSE" if ordinal == 1 else "LATER_VERIFICATION",
                requested_at=captured.capture.temporal.capture_started_at
                - timedelta(microseconds=1),
            ),
            _context(f"prospective-repeat-observe-{ordinal}"),
        )
        assert result.observation_ordinal == ordinal

    pool = TargetPostgresPool(database_url, min_size=0, max_size=1)
    try:
        contract = PostgresArchiveOperationsReadPort(pool).load_slice_contract(
            request.market_archive_id,
            slice_plan.market_archive_slice_id,
        )
    finally:
        pool.close()
    assert contract.terminal_status is None


def test_observation_gap_and_seal_preserve_complete_terminal_roster(archive_stack) -> None:
    commands, market, product, code, config, database_url = archive_stack
    request = _request(product, code, config)
    started = commands.start(request, _context("terminal-start"))
    success = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="wp17p-success-slice",
            resource="fixture://wp17p-success-slice",
            request_headers_hash="b" * 64,
        ),
        _BytesProvider(b'{"rows":[["sh.600000","10.00"]]}'),
        _context("success-capture"),
    )
    observation_request = RecordArchiveCaptureObservationRequest(
        market_archive_id=started.market_archive_id,
        market_archive_slice_id=request.slices[0].market_archive_slice_id,
        capture_id=success.capture.capture_id,
        schedule_slot="RETROSPECTIVE_BATCH",
        requested_at=success.capture.temporal.capture_started_at - timedelta(microseconds=1),
    )
    with pytest.raises(RuntimeStateConflictError, match="canonical normalization"):
        commands.record_capture_observation(
            observation_request,
            _context("record-before-normalize"),
        )
    market.normalize(
        success.capture.capture_id,
        _CapturedGapNormalizer(),
        _context("success-normalize"),
    )
    observation = commands.record_capture_observation(
        observation_request,
        _context("record-observation"),
    )
    with pytest.raises(RuntimeStateConflictError):
        commands.record_capture_observation(
            observation_request,
            _context("record-second-retrospective-observation"),
        )
    failure = market.capture(
        CaptureRequest(
            provider_product_id=product.provider_product_id,
            capture_key="wp17p-failed-slice",
            resource="fixture://wp17p-failed-slice",
            request_headers_hash="c" * 64,
        ),
        _FailingProvider(),
        _context("failed-capture"),
    )
    with psycopg.connect(database_url) as connection:
        gap_id = connection.execute(
            "SELECT gap_id FROM mra.source_gap WHERE capture_id = %s",
            (failure.capture.capture_id,),
        ).fetchone()[0]
    gap = commands.record_slice_gap(
        market_archive_id=started.market_archive_id,
        market_archive_slice_id=request.slices[1].market_archive_slice_id,
        gap_id=gap_id,
        terminal_status="GAP_RECORDED",
        context=_context("record-gap"),
    )
    seal = commands.seal_retrospective(
        market_archive_id=started.market_archive_id,
        disposition=ArchiveSealDisposition.PARTIAL_WITH_GAPS,
        context=_context("seal-archive"),
    )

    assert observation.observation_ordinal == 1
    assert observation.relation == "FIRST"
    assert observation.timeliness == "NOT_APPLICABLE"
    assert gap.gap_id == gap_id
    assert seal.knowledge_cutoff == seal.sealed_at
    assert seal.capture_count == 1
    assert seal.gap_count == 1

    pool = TargetPostgresPool(database_url, min_size=0, max_size=1)
    try:
        inspection = PostgresArchiveInspectionPort(pool).inspect(
            started.market_archive_id
        )
    finally:
        pool.close()
    assert inspection.slice_count == 2
    assert inspection.captured_slice_count == 1
    assert inspection.gap_slice_count == 1
    assert inspection.pending_slice_count == 0
    assert inspection.observation_count == 1
    assert inspection.artifact_count == 1
    assert inspection.seal_disposition == "PARTIAL_WITH_GAPS"
    assert [item.status for item in inspection.slices] == [
        "CAPTURED",
        "GAP_RECORDED",
    ]

    replay = commands.seal_retrospective(
        market_archive_id=started.market_archive_id,
        disposition=ArchiveSealDisposition.PARTIAL_WITH_GAPS,
        context=_context("seal-archive"),
    )
    assert replay.replayed is True
    assert replay.market_archive_seal_id == seal.market_archive_seal_id


def test_resource_limit_is_terminal_append_only_evidence_and_seals_partial(archive_stack) -> None:
    commands, _, product, code, config, _ = archive_stack
    request = replace(
        _request(product, code, config),
        market_archive_id=uuid4(),
        archive_code="wp17p-resource-limited",
        slices=tuple(
            replace(item, market_archive_slice_id=uuid4())
            for item in _request(product, code, config).slices
        ),
    )
    started = commands.start(request, _context("resource-start"))

    for item in request.slices:
        result = commands.record_resource_stop(
            market_archive_id=started.market_archive_id,
            market_archive_slice_id=item.market_archive_slice_id,
            observed_free_bytes=1_000_000,
            context=_context(f"resource-stop-{item.ordinal}"),
        )
        assert result.reason_code == "DISK_RESERVED_FLOOR"
        assert result.required_free_bytes == 2_050_000_000

    seal = commands.seal_retrospective(
        market_archive_id=started.market_archive_id,
        disposition=ArchiveSealDisposition.PARTIAL_WITH_RESOURCE_LIMIT,
        context=_context("resource-seal"),
    )
    assert seal.gap_count == 2
    assert seal.disposition == "PARTIAL_WITH_RESOURCE_LIMIT"
