"""Project normalized public data into the canonical SourceManifest."""

from __future__ import annotations

from datetime import timedelta

from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.contracts import (
    DataEligibility,
    SourceArtifactReference,
)
from market_regime_alpha.data.providers.public_composite.contracts import (
    PublicCompositeProviderResult,
    PublicCompositeRequest,
    TradingStatus,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceFieldFinality,
    SourceFieldQualityStatus,
    SourceManifest,
    SourceManifestField,
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
    default_reference = provider_references[-1]
    fields: list[SourceManifestField] = [
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
        )
    ]
    quote_by_symbol = {item.symbol: item for item in result.quotes}
    bars_by_symbol = {
        symbol: tuple(item for item in result.bars if item.symbol == symbol)
        for symbol in request.symbols
    }
    payload_by_id = {
        item.source_artifact_id: item for item in result.raw_payloads
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
        if not symbol_bars or any(
            item.available_time is None for item in symbol_bars
        ):
            history_reasons.append("HISTORY_AVAILABLE_TIME_UNKNOWN")
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
                unit="FIVE_MINUTE_BAR_WINDOW",
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
                    else SourceFieldQualityStatus.INSUFFICIENT
                ),
                reason_codes=tuple(history_reasons),
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
    )
