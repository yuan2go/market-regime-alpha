"""Canonical Archive test facts retained byte-for-byte below the import section."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

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

from tests.contracts.research_qualification import (
    test_research_postgres as _research,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def seed_complete_archive(application, *, episode_entry=False, multi_episode=False, daily_bars=False):
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
    decision_dates = (date(2026, 1, 5), date(2026, 1, 14))
    outcome_dates = (date(2026, 1, 6), date(2026, 1, 15))
    if multi_episode:
        session_dates = tuple(date(2026, month, day) for month, day in ((1, 26), (1, 27), (1, 28), (1, 29), (1, 30), (2, 2), (2, 3), (2, 4)))
        decision_dates = tuple(date(2026, month, day) for month, day in ((1, 26), (1, 28), (1, 29), (1, 30), (2, 3)))
        outcome_dates = tuple(date(2026, month, day) for month, day in ((1, 27), (1, 29), (1, 30), (2, 2), (2, 4)))
    fact_dates = session_dates if multi_episode else decision_dates

    def fixture_bar(product_id, capture_id, instrument_id, session, checkpoint, index):
        from dataclasses import replace
        bar = _bar(product_id, capture_id, instrument_id, session, checkpoint, index)
        if not multi_episode:
            return bar
        close = (Decimal(10) + Decimal(index + 1) / 100 if checkpoint == "REFERENCE"
                 else {date(2026, 1, 30): Decimal(11), date(2026, 2, 2): Decimal(9)}.get(session.session_date, Decimal(10)))
        return replace(bar, open=Money(Decimal(10), "CNY"), close=Money(close, "CNY"),
            high=Money(max(Decimal(10), close) + Decimal(".01"), "CNY"),
            low=Money(min(Decimal(10), close) - Decimal(".01"), "CNY"), turnover=Money(close * 10000, "CNY"))

    sessions = tuple(
        _session(item, capture_id, exchange)
        for exchange in ("XSHG",)
        for item in session_dates
    )
    session_by_exchange_date = {
        (item.exchange, item.session_date): item for item in sessions
    }
    instrument_ids = tuple(
        InstrumentId(uuid5(NAMESPACE_URL, f"wp17p-fixture:{index}"))
        for index in range(32)
    )
    instrument_exchange = {
        instrument_id: "XSHG"
        for index, instrument_id in enumerate(instrument_ids)
    }
    classification_id = uuid4()
    batch = NormalizationBatch(
        capture_id,
        product.provider_product_id,
        instruments=tuple(
            Instrument(
                instrument_id,
                (
                    f"{600000 + index}.XSHG"
                    if instrument_exchange[instrument_id] == "XSHG"
                    else f"{index:06d}.XSHE"
                ),
                instrument_exchange[instrument_id],
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
            fixture_bar(
                product.provider_product_id,
                capture_id,
                instrument_id,
                session_by_exchange_date[
                    (instrument_exchange[instrument_id], session_date)
                ],
                checkpoint,
                index,
            )
            for index, instrument_id in enumerate(instrument_ids)
            for session_date, checkpoint in tuple(
                item for decision, outcome in zip(decision_dates, outcome_dates, strict=True)
                for item in ((decision, "REFERENCE"), (outcome, "OUTCOME"))
            )
        ),
        security_status_facts=tuple(
            SecurityStatusFactRevision(
                uuid4(),
                product.provider_product_id,
                capture_id,
                instrument_id,
                session_by_exchange_date[
                    (instrument_exchange[instrument_id], session_date)
                ].session_id,
                EvidenceScope.DECISION_SESSION,
                (SecurityStatus.SUSPENDED if multi_episode and instrument_id not in instrument_ids[:2]
                 and session_date in {date(2026, 1, 28), date(2026, 2, 3)} else SecurityStatus.ACTIVE),
                session_by_exchange_date[
                    (instrument_exchange[instrument_id], session_date)
                ].open_at,
                session_by_exchange_date[
                    (instrument_exchange[instrument_id], session_date)
                ].close_at,
                1,
                None,
            )
            for instrument_id in instrument_ids
            for session_date in fact_dates
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
                *(
                    InstrumentLifecycleFactRevision(
                        uuid4(),
                        product.provider_product_id,
                        capture_id,
                        instrument_id,
                        InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
                        SpecialTreatmentStatus.NORMAL,
                        session_by_exchange_date[
                            (instrument_exchange[instrument_id], session_date)
                        ].open_at,
                        session_by_exchange_date[
                            (instrument_exchange[instrument_id], session_date)
                        ].close_at,
                        1,
                        None,
                    )
                    for session_date in fact_dates
                ),
            )
        ),
    )
    if daily_bars:
        from dataclasses import replace
        daily=[]
        for index,instrument in enumerate(instrument_ids):
            for offset,session in enumerate(sessions):
                value=Decimal(10)+(Decimal(index+1)*Decimal(".001")*(1 if offset%2 else -1))
                bar=_bar(product.provider_product_id,capture_id,instrument,session,"REFERENCE",index)
                daily.append(replace(bar,bar_revision_id=uuid4(),timeframe=BarTimeframe.DAILY,
                    event_start=session.open_at,event_end=session.close_at,open=Money(Decimal(10),"CNY"),
                    close=Money(value,"CNY"),high=Money(Decimal(11),"CNY"),low=Money(Decimal(9),"CNY")))
        batch=replace(batch,bars=(*batch.bars,*daily))
    if episode_entry:
        from dataclasses import replace
        entry_bars = []
        for index, instrument_id in enumerate(instrument_ids):
            for session_date in outcome_dates:
                bar = fixture_bar(product.provider_product_id, capture_id, instrument_id,
                           session_by_exchange_date[("XSHG", session_date)], "OUTCOME", index)
                entry_end = datetime.combine(session_date, time(9, 35), SHANGHAI).astimezone(UTC)
                entry_bars.append(replace(bar, bar_revision_id=uuid4(), event_start=entry_end.replace(minute=30),
                                          event_end=entry_end, close=bar.open))
        batch = replace(batch, bars=(*batch.bars, *entry_bars))
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
    return product, instrument_ids, sessions, code, config, archive_id, seal


def _session(session_date: date, capture_id, exchange: str):
    def at(hour: int, minute: int) -> datetime:
        return datetime.combine(
            session_date,
            time(hour, minute),
            SHANGHAI,
        ).astimezone(UTC)

    return TradingSession(
        uuid5(NAMESPACE_URL, f"wp17p-session:{exchange}:{session_date}"),
        exchange,
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
