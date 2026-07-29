from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
    PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeProviderResult,
    PublicCompositeRequest,
    PublicQuote,
    TradingStatus,
    build_daily_control_source_evidence,
    build_public_source_manifest,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)
from market_regime_alpha.universe.daily_exploratory import (
    DailyUniversePolicy,
    SMOKE_POOL_SYMBOLS,
    build_daily_eligibility_source_evidence,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2025, 2, 3, 14, 55, tzinfo=SHANGHAI))
RETRIEVED = RetrievedAt(datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI))
AVAILABLE = AvailabilityTime(datetime(2025, 2, 3, 14, 54, tzinfo=SHANGHAI))


def public_fixture(
    *,
    policy: DailyUniversePolicy,
    decision_time: DecisionTime = DECISION,
    missing_price_symbol: str | None = None,
    suspended_symbol: str | None = None,
    suspended_symbols: tuple[str, ...] = (),
    include_outsider: bool = False,
    history_session_count: int = 21,
    quote_age_minutes: int = 1,
    exploratory_daily_history: bool = False,
) -> tuple[
    PublicCompositeRequest,
    PublicCompositeProviderResult,
    SourceManifest,
]:
    local_decision = decision_time.value.astimezone(SHANGHAI)
    retrieved = RetrievedAt(local_decision - timedelta(minutes=1))
    available = AvailabilityTime(local_decision - timedelta(minutes=1))
    date_suffix = (
        b""
        if decision_time == DECISION
        else f":{local_decision.date().isoformat()}".encode()
    )
    history_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-history",
        locator="archive://fixture/baostock",
        raw_payload=b"fixture-baostock-history" + date_suffix,
        retrieved_time=retrieved,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    quote_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-tencent-public"),
        product="fixture-quotes",
        locator="archive://fixture/tencent",
        raw_payload=b"fixture-tencent-quotes" + date_suffix,
        retrieved_time=retrieved,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    symbols = (
        (*SMOKE_POOL_SYMBOLS, "000001.SZ")
        if include_outsider
        else SMOKE_POOL_SYMBOLS
    )
    start = local_decision.date() - timedelta(days=32)
    bars = tuple(
        PublicBar(
            symbol=symbol,
            event_time=datetime.combine(
                start + timedelta(days=index),
                datetime.min.time().replace(hour=14, minute=55),
                tzinfo=SHANGHAI,
            ),
            available_time=(
                None
                if exploratory_daily_history
                else AvailabilityTime(
                    datetime.combine(
                        start + timedelta(days=index),
                        datetime.min.time().replace(hour=15, minute=1),
                        tzinfo=SHANGHAI,
                    )
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
            finality=(
                SourceFieldFinality.UNKNOWN
                if exploratory_daily_history
                else SourceFieldFinality.FINAL
            ),
        )
        for symbol in symbols
        for index in range(history_session_count)
    )
    quotes = tuple(
        PublicQuote(
            symbol=symbol,
            event_time=local_decision - timedelta(minutes=quote_age_minutes),
            available_time=available,
            source_artifact_id=quote_payload.source_artifact_id,
            price=None if symbol == missing_price_symbol else 10.5,
            trading_status=(
                TradingStatus.SUSPENDED
                if symbol
                in {
                    *suspended_symbols,
                    *((suspended_symbol,) if suspended_symbol is not None else ()),
                }
                else TradingStatus.TRADING
            ),
            unit="CNY",
            finality=SourceFieldFinality.PRELIMINARY,
        )
        for symbol in symbols
    )
    result = PublicCompositeProviderResult(
        profile_id=PUBLIC_COMPOSITE_REPLAY_PROFILE_ID,
        decision_time=decision_time,
        raw_payloads=(history_payload, quote_payload),
        bars=bars,
        quotes=quotes,
        source_conflicts=(),
        limitations=(
            "FIXTURE_REPLAY_ONLY",
            *(
                (HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,)
                if exploratory_daily_history
                else ()
            ),
        ),
    )
    request = PublicCompositeRequest(
        symbols=SMOKE_POOL_SYMBOLS,
        decision_time=decision_time,
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
            event_time=decision_time.value,
            available_time=available,
            retrieved_time=retrieved,
            decision_time=decision_time,
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


def public_v2_fixture(
    *,
    policy: DailyUniversePolicy,
    unknown_trading_symbol: str | None = None,
) -> tuple[
    PublicCompositeRequest,
    PublicCompositeProviderResult,
    SourceManifest,
]:
    """Fixture-only v2 Archive with explicit independent status evidence."""

    request, base_result, _ = public_fixture(policy=policy)
    result = replace(
        base_result,
        quotes=tuple(
            replace(item, trading_status=TradingStatus.UNKNOWN)
            if item.symbol == unknown_trading_symbol
            else item
            for item in base_result.quotes
        ),
    )
    control = build_daily_control_source_evidence(
        request=request,
        retrieved_time=RETRIEVED,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        policy_version=policy.policy_version,
        instrument_scope=policy.instrument_scope,
        symbols=policy.symbols,
    )
    status_payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-fixture-security-status"),
        product="fixture-security-status",
        locator="archive://fixture/security-status",
        raw_payload=b"fixture-explicit-not-st-and-listed-status",
        retrieved_time=RETRIEVED,
        limitations=("FIXTURE_REPLAY_ONLY",),
    )
    status_fields = tuple(
        SourceManifestField(
            field_id=field_id,
            symbol=symbol,
            critical_fact=fact,
            provider_id=status_payload.provider_id,
            source_artifact_id=status_payload.source_artifact_id,
            event_time=DECISION.value,
            available_time=AVAILABLE,
            retrieved_time=RETRIEVED,
            decision_time=DECISION,
            unit="STATUS",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
            schema_version=SourceManifestField.SCHEMA_V2,
            authority_kind=SourceAuthorityKind.PROVIDER,
            value=value,
        )
        for symbol in policy.symbols
        for fact, field_id, value in (
            (CriticalSourceFact.ST_STATUS, "st_status", "NOT_ST"),
            (CriticalSourceFact.LISTING_STATUS, "listing_status", "LISTED"),
        )
    )
    control_bound = replace(
        result,
        raw_payloads=(
            *result.raw_payloads,
            *control.raw_payloads,
            status_payload,
        ),
    )
    control_manifest = build_public_source_manifest(
        result=control_bound,
        request=request,
        declared_fields=(*control.fields, *status_fields),
    )
    eligibility = build_daily_eligibility_source_evidence(
        policy=policy,
        source_manifest=control_manifest,
        provider_result=control_bound,
        retrieved_time=RETRIEVED,
    )
    final_result = replace(
        control_bound,
        raw_payloads=(
            *control_bound.raw_payloads,
            *eligibility.raw_payloads,
        ),
    )
    manifest = build_public_source_manifest(
        result=final_result,
        request=request,
        declared_fields=(
            *control.fields,
            *status_fields,
            *eligibility.fields,
        ),
    )
    return request, final_result, manifest
