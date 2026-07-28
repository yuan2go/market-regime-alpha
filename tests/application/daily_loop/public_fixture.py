from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeProviderResult,
    PublicCompositeRequest,
    PublicQuote,
    TradingStatus,
    build_public_source_manifest,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.universe.daily_exploratory import (
    DailyUniversePolicy,
    SMOKE_POOL_SYMBOLS,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2025, 2, 3, 14, 55, tzinfo=SHANGHAI))
RETRIEVED = RetrievedAt(datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI))
AVAILABLE = AvailabilityTime(datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI))


def public_fixture(
    *,
    policy: DailyUniversePolicy,
    missing_price_symbol: str | None = None,
    suspended_symbol: str | None = None,
    include_outsider: bool = False,
) -> tuple[
    PublicCompositeRequest,
    PublicCompositeProviderResult,
    SourceManifest,
]:
    history_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-history",
        locator="archive://fixture/baostock",
        raw_payload=b"fixture-baostock-history",
        retrieved_time=RETRIEVED,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    quote_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-quotes",
        locator="archive://fixture/tencent",
        raw_payload=b"fixture-tencent-quotes",
        retrieved_time=RETRIEVED,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    symbols = (
        (*SMOKE_POOL_SYMBOLS, "000001.SZ")
        if include_outsider
        else SMOKE_POOL_SYMBOLS
    )
    start = date(2025, 1, 2)
    bars = tuple(
        PublicBar(
            symbol=symbol,
            event_time=datetime.combine(
                start + timedelta(days=index),
                datetime.min.time().replace(hour=14, minute=55),
                tzinfo=SHANGHAI,
            ),
            available_time=AvailabilityTime(
                datetime.combine(
                    start + timedelta(days=index),
                    datetime.min.time().replace(hour=15, minute=1),
                    tzinfo=SHANGHAI,
                )
            ),
            source_artifact_id=history_payload.source_artifact_id,
            open=10.0 + index / 100,
            high=10.2 + index / 100,
            low=9.9 + index / 100,
            close=10.1 + index / 100,
            volume=1_000_000.0,
            amount=20_000_000.0 + index,
            unit="CNY",
            adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
            finality=SourceFieldFinality.FINAL,
        )
        for symbol in symbols
        for index in range(21)
    )
    quotes = tuple(
        PublicQuote(
            symbol=symbol,
            event_time=datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI),
            available_time=AVAILABLE,
            source_artifact_id=quote_payload.source_artifact_id,
            price=None if symbol == missing_price_symbol else 10.5,
            trading_status=(
                TradingStatus.SUSPENDED
                if symbol == suspended_symbol
                else TradingStatus.TRADING
            ),
            unit="CNY",
            finality=SourceFieldFinality.PRELIMINARY,
        )
        for symbol in symbols
    )
    result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=DECISION,
        raw_payloads=(history_payload, quote_payload),
        bars=bars,
        quotes=quotes,
        source_conflicts=(),
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    request = PublicCompositeRequest(
        symbols=SMOKE_POOL_SYMBOLS,
        decision_time=DECISION,
        history_start=start,
        minimum_history_sessions=21,
    )
    declarations = tuple(
        SourceManifestField(
            field_id=fact.value.lower(),
            symbol=symbol,
            critical_fact=fact,
            provider_id=quote_payload.provider_id,
            source_artifact_id=quote_payload.source_artifact_id,
            event_time=DECISION.value,
            available_time=AVAILABLE,
            retrieved_time=RETRIEVED,
            decision_time=DECISION,
            unit="POLICY_DECLARATION",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
        )
        for symbol in SMOKE_POOL_SYMBOLS
        for fact in (
            CriticalSourceFact.UNIVERSE_MEMBERSHIP,
            CriticalSourceFact.ELIGIBILITY,
        )
    )
    manifest = build_public_source_manifest(
        result=result,
        request=request,
        declared_fields=declarations,
    )
    return request, result, manifest
