from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

import psycopg

from market_regime_alpha.bootstrap import (
    TargetSettings,
    bootstrap_application,
)
from market_regime_alpha.infrastructure.postgres.schema import SchemaManager
from market_regime_alpha.interfaces.wp17p_authorities import (
    build_wp17p_authority_catalog,
)
from market_regime_alpha.interfaces.wp17p_campaign import Wp17pCampaignOperations
from market_regime_alpha.market.domain import (
    ArchiveLane,
    ArchiveSealDisposition,
    BarTimeframe,
    ClassificationMembershipRevision,
    ClassificationRevision,
    EvidenceScope,
    Instrument,
    InstrumentFactKind,
    InstrumentLifecycleFactRevision,
    InstrumentType,
    ListingStatus,
    MarketBarRevision,
    MarketFactKind,
    MembershipStatus,
    NormalizationBatch,
    PriceBasis,
    Provider,
    ProviderKind,
    ProviderProduct,
    SecurityStatus,
    SecurityStatusFactRevision,
    SourceAvailabilityStatus,
    SpecialTreatmentStatus,
    TradingSession,
)
from market_regime_alpha.market.application import (
    ArchiveSlicePlan,
    RecordArchiveCaptureObservationRequest,
    StartMarketArchiveRequest,
)
from market_regime_alpha.market.ports import CaptureRequest
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import InstrumentId

from tests.refoundation.research_qualification import (
    test_research_postgres as _research,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_canonical_wp17p_fit_model_validation_chain(target_database_url, tmp_path) -> None:
    SchemaManager(target_database_url).bootstrap()
    settings = TargetSettings(
        database_url=target_database_url,
        artifact_root=(tmp_path / "wp17p-campaign-artifacts").resolve(),
        pool_min_size=0,
        pool_max_size=8,
    )
    with bootstrap_application(settings) as application:
        provider = Provider(
            uuid4(),
            "wp17p_fixture",
            "WP-17P fixture",
            ProviderKind.PUBLIC_ENDPOINT,
        )
        product = ProviderProduct(
            uuid4(),
            provider.provider_id,
            "wp17p_complete_facts",
            1,
            "WP17P_COMPLETE_FACTS",
            "application/json",
            "UTF-8",
            SourceAvailabilityStatus.UNKNOWN,
            tuple(MarketFactKind),
            tuple(InstrumentFactKind),
            tuple(BarTimeframe),
            tuple(PriceBasis),
        )
        application.market.register_provider(provider, _context("provider"))
        application.market.register_provider_product(product, _context("product"))
        captured = application.market.capture(
            CaptureRequest(
                product.provider_product_id,
                "wp17p-complete-fixture",
                "fixture://wp17p/complete",
                "a" * 64,
            ),
            _research._BytesProvider(),
            _context("capture"),
        )
        capture_id = captured.capture.capture_id
        session_dates = (
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 9),
            date(2026, 1, 12),
            date(2026, 1, 13),
            date(2026, 1, 14),
            date(2026, 1, 15),
            date(2026, 1, 16),
            date(2026, 1, 19),
        )
        sessions = tuple(_session(item, capture_id) for item in session_dates)
        session_by_date = {item.session_date: item for item in sessions}
        instrument_ids = tuple(
            InstrumentId(uuid5(NAMESPACE_URL, f"wp17p-fixture:{index}"))
            for index in range(32)
        )
        classification_id = uuid4()
        batch = NormalizationBatch(
            capture_id,
            product.provider_product_id,
            instruments=tuple(
                Instrument(
                    instrument_id,
                    f"{600000 + index}.XSHG",
                    "XSHG",
                    InstrumentType.EQUITY,
                    "CNY",
                    capture_id,
                )
                for index, instrument_id in enumerate(instrument_ids)
            ),
            trading_sessions=sessions,
            classifications=(
                ClassificationRevision(
                    classification_id,
                    "INDEX_MEMBERSHIP",
                    "CSI300",
                    "CSI 300 fixture",
                    1,
                    datetime(2020, 1, 1, tzinfo=UTC),
                    None,
                    None,
                    capture_id,
                ),
            ),
            classification_memberships=tuple(
                ClassificationMembershipRevision(
                    uuid4(),
                    classification_id,
                    instrument_id,
                    capture_id,
                    MembershipStatus.MEMBER,
                    datetime(2020, 1, 1, tzinfo=UTC),
                    None,
                    1,
                    None,
                )
                for instrument_id in instrument_ids
            ),
            bars=tuple(
                _bar(
                    product.provider_product_id,
                    capture_id,
                    instrument_id,
                    session_by_date[session_date],
                    checkpoint,
                    index,
                )
                for index, instrument_id in enumerate(instrument_ids)
                for session_date, checkpoint in (
                    (date(2026, 1, 5), "REFERENCE"),
                    (date(2026, 1, 6), "OUTCOME"),
                    (date(2026, 1, 14), "REFERENCE"),
                    (date(2026, 1, 15), "OUTCOME"),
                )
            ),
            security_status_facts=tuple(
                SecurityStatusFactRevision(
                    uuid4(),
                    product.provider_product_id,
                    capture_id,
                    instrument_id,
                    session_by_date[session_date].session_id,
                    EvidenceScope.DECISION_SESSION,
                    SecurityStatus.ACTIVE,
                    session_by_date[session_date].open_at,
                    session_by_date[session_date].close_at,
                    1,
                    None,
                )
                for instrument_id in instrument_ids
                for session_date in (date(2026, 1, 5), date(2026, 1, 14))
            ),
            lifecycle_status_facts=tuple(
                fact
                for instrument_id in instrument_ids
                for fact in (
                    InstrumentLifecycleFactRevision(
                        uuid4(),
                        product.provider_product_id,
                        capture_id,
                        instrument_id,
                        InstrumentFactKind.LISTING_STATUS,
                        ListingStatus.LISTED,
                        datetime(2020, 1, 1, tzinfo=UTC),
                        None,
                        1,
                        None,
                    ),
                    InstrumentLifecycleFactRevision(
                        uuid4(),
                        product.provider_product_id,
                        capture_id,
                        instrument_id,
                        InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
                        SpecialTreatmentStatus.NORMAL,
                        datetime(2020, 1, 1, tzinfo=UTC),
                        None,
                        1,
                        None,
                    ),
                )
            ),
        )
        application.market.normalize(
            capture_id,
            _research._Normalizer(lambda _: batch),
            _context("normalize"),
        )
        code = application.artifacts.publish(
            b"wp17p complete pipeline\n",
            media_type="text/plain",
            context=_context("code"),
        )
        config = application.artifacts.publish(
            b'{"pilot":"WP17P_ENGINEERING_EXPLORATORY_32"}\n',
            media_type="application/json",
            context=_context("config"),
        )
        archive_id = uuid4()
        slice_id = uuid4()
        application.market_archives.start(
            StartMarketArchiveRequest(
                archive_id,
                f"wp17p-fixture-{archive_id.hex[:10]}",
                ArchiveLane.RETROSPECTIVE_BACKFILL,
                product.provider_product_id,
                "SSE",
                BarTimeframe.MINUTE_5,
                PriceBasis.RAW_UNADJUSTED,
                "ENGINEERING_EXPLORATORY_PILOT_32",
                canonical_json_sha256(tuple(str(item) for item in instrument_ids)),
                sessions[0].open_at,
                sessions[-1].close_at,
                1,
                10_000_000,
                10_000_000,
                code.artifact_id,
                config.artifact_id,
                "d" * 64,
                (
                    ArchiveSlicePlan(
                        slice_id,
                        1,
                        "xshg:fixture",
                        sessions[0].open_at,
                        sessions[-1].close_at,
                        "e" * 64,
                        "MARKET_BAR",
                    ),
                ),
            ),
            _context("archive-start"),
        )
        application.market_archives.record_capture_observation(
            RecordArchiveCaptureObservationRequest(
                archive_id,
                slice_id,
                capture_id,
                "RETROSPECTIVE_BATCH",
                captured.capture.temporal.capture_started_at,
            ),
            _context("archive-observe"),
        )
        seal = application.market_archives.seal_retrospective(
            market_archive_id=archive_id,
            disposition=ArchiveSealDisposition.COMPLETE,
            context=_context("archive-seal"),
        )
        selected_dates = {
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
            date(2026, 1, 12),
            date(2026, 1, 13),
            date(2026, 1, 14),
            date(2026, 1, 15),
        }
        catalog = build_wp17p_authority_catalog(
            provider_product_id=product.provider_product_id,
            market_archive_id=archive_id,
            market_archive_seal_id=seal.market_archive_seal_id,
            sessions=tuple(
                item
                for item in application.archive_trading_sessions.sessions(
                    exchange="XSHG",
                    start_date=min(selected_dates),
                    end_date=max(selected_dates),
                )
                if item.session_date in selected_dates
            ),
            code_artifact=_binding(code),
            config_artifact=_binding(config),
            provenance_sha256="f" * 64,
        )

        campaign = Wp17pCampaignOperations(
            application,
            code_sha="a" * 40,
        )
        result = campaign.run(
            catalog=catalog,
            pilot_instrument_ids=instrument_ids,
        )

        assert application.research_evaluation_verifier.verify_evaluation_run(
            result.fit_evaluation_run_id
        ).matched
        assert application.research_evaluation_verifier.verify_evaluation_run(
            result.validation_evaluation_run_id
        ).matched
        replayed = campaign.run(
            catalog=catalog,
            pilot_instrument_ids=instrument_ids,
        )
        assert replayed == result
    with psycopg.connect(target_database_url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.dataset),
              (SELECT count(*) FROM mra.decision_run),
              (SELECT count(*) FROM mra.market_target_outcome_revision),
              (SELECT count(*) FROM mra.research_partition),
              (SELECT count(*) FROM mra.evaluation_run),
              (SELECT count(*) FROM mra.model_version)
            """
        ).fetchone()
    assert counts == (3, 3, 96, 2, 2, 1)


def _session(session_date: date, capture_id):
    def at(hour: int, minute: int) -> datetime:
        return datetime.combine(
            session_date,
            time(hour, minute),
            SHANGHAI,
        ).astimezone(UTC)

    return TradingSession(
        uuid5(NAMESPACE_URL, f"wp17p-session:{session_date}"),
        "XSHG",
        session_date,
        "Asia/Shanghai",
        at(9, 30),
        at(11, 30),
        at(13, 0),
        at(15, 0),
        at(14, 55),
        capture_id,
    )


def _bar(product_id, capture_id, instrument_id, session, checkpoint, index):
    local_time = time(14, 55) if checkpoint == "REFERENCE" else time(10, 30)
    event_end = datetime.combine(session.session_date, local_time, SHANGHAI).astimezone(UTC)
    event_start = event_end.replace(minute=event_end.minute - 5)
    base = Decimal("10") + Decimal(index) / Decimal("100")
    move = Decimal(index - 15) / Decimal("10000")
    close = base * (Decimal("1") + move)
    return MarketBarRevision(
        uuid5(NAMESPACE_URL, f"wp17p-bar:{instrument_id}:{event_end}"),
        product_id,
        capture_id,
        instrument_id,
        session.session_id,
        BarTimeframe.MINUTE_5,
        PriceBasis.RAW_UNADJUSTED,
        event_start,
        event_end,
        1,
        None,
        Money(base, "CNY"),
        Money(max(base, close) + Decimal("0.01"), "CNY"),
        Money(min(base, close) - Decimal("0.01"), "CNY"),
        Money(close, "CNY"),
        Quantity(Decimal("10000"), QuantityUnit.SHARES),
        Money(close * Decimal("10000"), "CNY"),
    )


def _binding(record) -> ArtifactBinding:
    return ArtifactBinding(record.artifact_id, record.content_sha256, record.size_bytes)


def _context(suffix: str) -> CommandContext:
    return CommandContext(
        f"wp17p-campaign-test:{suffix}",
        ActorType.OPERATOR,
        "wp17p-campaign-test",
        "WP17P_EXPLORATORY_PILOT",
    )
