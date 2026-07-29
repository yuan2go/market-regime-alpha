"""Project normalized public data into the canonical SourceManifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    AcquiredSourcePayload,
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
    PublicCompositeProviderResult,
    PublicCompositeRequest,
    TENCENT_PUBLIC_PROVIDER_ID,
    TradingStatus,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
)

DAILY_RUN_PROTOCOL_AUTHORITY_ID = ProviderId("provider-daily-run-protocol")
DAILY_UNIVERSE_POLICY_AUTHORITY_ID = ProviderId(
    "authority-daily-universe-policy"
)
DAILY_ELIGIBILITY_POLICY_AUTHORITY_ID = ProviderId(
    "authority-daily-eligibility-policy"
)


@dataclass(frozen=True, slots=True)
class DailyControlSourceEvidence:
    """Archived protocol and Universe-policy facts declared outside Providers."""

    raw_payloads: tuple[AcquiredSourcePayload, ...]
    fields: tuple[SourceManifestField, ...]


def build_daily_control_source_evidence(
    *,
    request: PublicCompositeRequest,
    retrieved_time: RetrievedAt,
    policy_id: ArtifactId,
    policy_hash: str,
    policy_version: str,
    instrument_scope: str,
    symbols: tuple[str, ...],
) -> DailyControlSourceEvidence:
    """Bind Decision Time and fixed membership to their actual authorities."""

    if symbols != request.symbols:
        raise ValueError("control evidence symbols must match Provider request")
    protocol_payload = AcquiredSourcePayload(
        provider_id=DAILY_RUN_PROTOCOL_AUTHORITY_ID,
        product="daily-run-decision-protocol-v1",
        locator="protocol://daily-loop/decision-time",
        raw_payload=json.dumps(
            {
                "schema_version": "daily-run-decision-protocol-evidence-v1",
                "decision_time": request.decision_time.isoformat(),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        retrieved_time=retrieved_time,
        limitations=("PROTOCOL_FACT_NOT_PROVIDER_MARKET_DATA",),
    )
    policy_payload = AcquiredSourcePayload(
        provider_id=DAILY_UNIVERSE_POLICY_AUTHORITY_ID,
        product="daily-universe-policy-evidence-v1",
        locator=f"policy://{policy_version}",
        raw_payload=json.dumps(
            {
                "schema_version": "daily-universe-policy-evidence-v1",
                "policy_id": str(policy_id),
                "policy_hash": policy_hash,
                "policy_version": policy_version,
                "decision_date": request.decision_time.value.date().isoformat(),
                "instrument_scope": instrument_scope,
                "symbols": list(symbols),
                "data_eligibility": DataEligibility.EXPLORATORY.value,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        retrieved_time=retrieved_time,
        limitations=(
            "FIXED_POLICY_MEMBERSHIP_EXPLORATORY_ONLY",
            "FORMAL_PIT_NOT_ESTABLISHED",
        ),
    )
    fields = [
        SourceManifestField(
            field_id="decision_time",
            symbol=None,
            critical_fact=CriticalSourceFact.DECISION_TIME,
            provider_id=protocol_payload.provider_id,
            source_artifact_id=protocol_payload.source_artifact_id,
            event_time=request.decision_time.value,
            available_time=AvailabilityTime(request.decision_time.value),
            retrieved_time=retrieved_time,
            decision_time=request.decision_time,
            unit="ASIA_SHANGHAI_TIMESTAMP",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
            schema_version=SourceManifestField.SCHEMA_V2,
            authority_kind=SourceAuthorityKind.PROTOCOL,
            value=request.decision_time.isoformat(),
        )
    ]
    fields.extend(
        SourceManifestField(
            field_id="universe_membership",
            symbol=symbol,
            critical_fact=CriticalSourceFact.UNIVERSE_MEMBERSHIP,
            provider_id=policy_payload.provider_id,
            source_artifact_id=policy_payload.source_artifact_id,
            event_time=request.decision_time.value,
            available_time=AvailabilityTime(request.decision_time.value),
            retrieved_time=retrieved_time,
            decision_time=request.decision_time,
            unit="BOOLEAN",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
            schema_version=SourceManifestField.SCHEMA_V2,
            authority_kind=SourceAuthorityKind.UNIVERSE_POLICY,
            value=True,
        )
        for symbol in symbols
    )
    return DailyControlSourceEvidence(
        raw_payloads=(protocol_payload, policy_payload),
        fields=tuple(fields),
    )


def build_public_source_manifest(
    *,
    result: PublicCompositeProviderResult,
    request: PublicCompositeRequest,
    declared_fields: tuple[SourceManifestField, ...] = (),
    declared_source_artifacts: tuple[SourceArtifactReference, ...] = (),
    maximum_quote_age: timedelta = timedelta(minutes=5),
) -> SourceManifest:
    """Build source facts without inventing unavailable provider semantics."""

    if result.decision_time != request.decision_time:
        raise ValueError("ProviderResult and request Decision Time mismatch")
    provider_references = result.source_artifact_references
    references = (
        *provider_references,
        *declared_source_artifacts,
    )
    if not references:
        raise ValueError("ProviderResult has no source artifacts")
    provider_payloads = tuple(
        item
        for item in result.raw_payloads
        if item.provider_id
        not in {
            DAILY_RUN_PROTOCOL_AUTHORITY_ID,
            DAILY_UNIVERSE_POLICY_AUTHORITY_ID,
            DAILY_ELIGIBILITY_POLICY_AUTHORITY_ID,
        }
    )
    if not provider_payloads:
        raise ValueError("SourceManifest has no Provider-owned source Artifact")
    default_payload = next(
        (
            item
            for provider_id in (
                TENCENT_PUBLIC_PROVIDER_ID,
                BAOSTOCK_PUBLIC_PROVIDER_ID,
            )
            for item in reversed(provider_payloads)
            if item.provider_id == provider_id
        ),
        provider_payloads[-1],
    )
    default_reference = default_payload.reference
    use_v2 = any(
        item.schema_version == SourceManifestField.SCHEMA_V2
        for item in declared_fields
    )
    field_schema = (
        SourceManifestField.SCHEMA_V2
        if use_v2
        else SourceManifestField.SCHEMA_V1
    )
    fields: list[SourceManifestField] = []
    if not any(
        item.symbol is None
        and item.critical_fact is CriticalSourceFact.DECISION_TIME
        for item in declared_fields
    ):
        fields.append(
            SourceManifestField(
            field_id="decision_time",
            symbol=None,
            critical_fact=CriticalSourceFact.DECISION_TIME,
            provider_id=default_reference.provider_id,
            source_artifact_id=default_reference.artifact_id,
            event_time=request.decision_time.value,
            available_time=AvailabilityTime(default_reference.retrieved_at.value),
            retrieved_time=default_reference.retrieved_at,
            decision_time=request.decision_time,
            unit="ASIA_SHANGHAI_TIMESTAMP",
            adjustment_basis="NONE",
            finality=SourceFieldFinality.FINAL,
            data_eligibility=DataEligibility.EXPLORATORY,
            quality_status=SourceFieldQualityStatus.COMPLETE,
            reason_codes=(),
            schema_version=field_schema,
            authority_kind=SourceAuthorityKind.PROVIDER,
            value=(
                request.decision_time.isoformat() if use_v2 else None
            ),
        )
        )
    quote_by_symbol = {item.symbol: item for item in result.quotes}
    bars_by_symbol = {
        symbol: tuple(item for item in result.bars if item.symbol == symbol)
        for symbol in request.symbols
    }
    payload_by_id = {
        item.source_artifact_id: item for item in result.raw_payloads
    }
    declared_keys = {
        (item.symbol, item.critical_fact) for item in declared_fields
    }
    for symbol in request.symbols:
        quote = quote_by_symbol.get(symbol)
        quote_source = (
            payload_by_id[quote.source_artifact_id].reference
            if quote is not None
            else default_reference
        )
        price_reasons: list[str] = []
        if quote is None or quote.price is None:
            price_reasons.append("PRICE_UNAVAILABLE")
        if quote is not None and quote.event_time is None:
            price_reasons.append("QUOTE_EVENT_TIME_UNKNOWN")
        elif (
            quote is not None
            and quote.event_time is not None
            and request.decision_time.value - quote.event_time > maximum_quote_age
        ):
            price_reasons.append("QUOTE_STALE")
        fields.append(
            SourceManifestField(
                field_id="price",
                symbol=symbol,
                critical_fact=CriticalSourceFact.PRICE,
                provider_id=quote_source.provider_id,
                source_artifact_id=quote_source.artifact_id,
                event_time=quote.event_time if quote is not None else None,
                available_time=(
                    quote.available_time if quote is not None else None
                ),
                retrieved_time=quote_source.retrieved_at,
                decision_time=request.decision_time,
                unit=quote.unit if quote is not None else "CNY",
                adjustment_basis="NONE",
                finality=(
                    quote.finality
                    if quote is not None
                    else SourceFieldFinality.UNKNOWN
                ),
                data_eligibility=DataEligibility.EXPLORATORY,
                quality_status=(
                    SourceFieldQualityStatus.COMPLETE
                    if not price_reasons
                    else SourceFieldQualityStatus.INSUFFICIENT
                ),
                reason_codes=tuple(price_reasons),
                schema_version=field_schema,
                authority_kind=SourceAuthorityKind.PROVIDER,
                value=(
                    quote.price
                    if use_v2 and quote is not None
                    else None
                ),
            )
        )
        trading_reasons = (
            ()
            if quote is not None
            and quote.trading_status is not TradingStatus.UNKNOWN
            else ("TRADING_STATUS_UNKNOWN",)
        )
        fields.append(
            SourceManifestField(
                field_id="trading_status",
                symbol=symbol,
                critical_fact=CriticalSourceFact.TRADING_STATUS,
                provider_id=quote_source.provider_id,
                source_artifact_id=quote_source.artifact_id,
                event_time=quote.event_time if quote is not None else None,
                available_time=(
                    quote.available_time if quote is not None else None
                ),
                retrieved_time=quote_source.retrieved_at,
                decision_time=request.decision_time,
                unit="STATUS",
                adjustment_basis="NONE",
                finality=(
                    quote.finality
                    if quote is not None
                    else SourceFieldFinality.UNKNOWN
                ),
                data_eligibility=DataEligibility.EXPLORATORY,
                quality_status=(
                    SourceFieldQualityStatus.COMPLETE
                    if not trading_reasons
                    else SourceFieldQualityStatus.INSUFFICIENT
                ),
                reason_codes=trading_reasons,
                schema_version=field_schema,
                authority_kind=SourceAuthorityKind.PROVIDER,
                value=(
                    quote.trading_status.value
                    if use_v2 and quote is not None
                    else None
                ),
            )
        )
        if use_v2:
            for fact, field_id, reason_code in (
                (
                    CriticalSourceFact.ST_STATUS,
                    "st_status",
                    "ST_STATUS_UNKNOWN",
                ),
                (
                    CriticalSourceFact.LISTING_STATUS,
                    "listing_status",
                    "LISTING_STATUS_UNKNOWN",
                ),
            ):
                if (symbol, fact) in declared_keys:
                    continue
                fields.append(
                    SourceManifestField(
                        field_id=field_id,
                        symbol=symbol,
                        critical_fact=fact,
                        provider_id=quote_source.provider_id,
                        source_artifact_id=quote_source.artifact_id,
                        event_time=(
                            quote.event_time if quote is not None else None
                        ),
                        available_time=(
                            quote.available_time if quote is not None else None
                        ),
                        retrieved_time=quote_source.retrieved_at,
                        decision_time=request.decision_time,
                        unit="STATUS",
                        adjustment_basis="NONE",
                        finality=SourceFieldFinality.UNKNOWN,
                        data_eligibility=DataEligibility.EXPLORATORY,
                        quality_status=SourceFieldQualityStatus.INSUFFICIENT,
                        reason_codes=(reason_code,),
                        schema_version=SourceManifestField.SCHEMA_V2,
                        authority_kind=SourceAuthorityKind.PROVIDER,
                        value="UNKNOWN",
                    )
                )
        symbol_bars = bars_by_symbol[symbol]
        history_source = (
            payload_by_id[symbol_bars[-1].source_artifact_id].reference
            if symbol_bars
            else default_reference
        )
        history_sessions = {item.event_time.date() for item in symbol_bars}
        history_reasons: list[str] = []
        if len(history_sessions) < request.minimum_history_sessions:
            history_reasons.append("INSUFFICIENT_HISTORY")
        exploratory_history = (
            HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
            in result.limitations
        )
        if not symbol_bars or any(
            item.available_time is None for item in symbol_bars
        ):
            history_reasons.append(
                HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
                if exploratory_history and symbol_bars
                else "HISTORY_AVAILABLE_TIME_UNKNOWN"
            )
            history_available = None
        else:
            available_values = [
                item.available_time
                for item in symbol_bars
                if item.available_time is not None
            ]
            history_available = max(
                available_values,
                key=lambda item: item.as_utc(),
            )
        fields.append(
            SourceManifestField(
                field_id="history_window",
                symbol=symbol,
                critical_fact=CriticalSourceFact.HISTORY_WINDOW,
                provider_id=history_source.provider_id,
                source_artifact_id=history_source.artifact_id,
                event_time=(
                    max(item.event_time for item in symbol_bars)
                    if symbol_bars
                    else None
                ),
                available_time=history_available,
                retrieved_time=history_source.retrieved_at,
                decision_time=request.decision_time,
                unit=(
                    "DAILY_BAR_WINDOW"
                    if exploratory_history
                    else "FIVE_MINUTE_BAR_WINDOW"
                ),
                adjustment_basis=(
                    symbol_bars[-1].adjustment_basis
                    if symbol_bars
                    else "UNKNOWN"
                ),
                finality=(
                    symbol_bars[-1].finality
                    if symbol_bars
                    else SourceFieldFinality.UNKNOWN
                ),
                data_eligibility=DataEligibility.EXPLORATORY,
                quality_status=(
                    SourceFieldQualityStatus.COMPLETE
                    if not history_reasons
                    else (
                        SourceFieldQualityStatus.DEGRADED
                        if history_reasons
                        == [HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1]
                        else SourceFieldQualityStatus.INSUFFICIENT
                    )
                ),
                reason_codes=tuple(history_reasons),
                schema_version=field_schema,
                authority_kind=SourceAuthorityKind.PROVIDER,
                value=(len(history_sessions) if use_v2 else None),
            )
        )
    fields.extend(declared_fields)
    return SourceManifest(
        provider_profile_id=result.profile_id,
        decision_time=request.decision_time,
        source_artifacts=references,
        fields=tuple(fields),
        source_conflicts=result.source_conflicts,
        limitations=result.limitations,
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=(
            SourceManifest.SCHEMA_V2 if use_v2 else SourceManifest.SCHEMA_V1
        ),
    )
