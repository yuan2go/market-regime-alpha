"""Controlled adapters from verified provider evidence into canonical market data."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite.stage_artifact import (
    PublicSourceAcquisitionStage,
    VerifiedPublicSourceStageArtifact,
)
from market_regime_alpha.evidence.canonical import normalize_canonical_datetime
from market_regime_alpha.market_data.adjustment import PriceAdjustmentPolicy
from market_regime_alpha.market_data.contracts import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
)
from market_regime_alpha.market_data.dataset import (
    FormalPitStatus,
    MarketDataDatasetArtifact,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_SUPPORTED_RAW_ADJUSTMENT_BASES = frozenset(
    {"BAOSTOCK_ADJUSTFLAG_3", "RAW", "RAW_UNADJUSTED"}
)


def normalize_public_history_stage(
    *,
    verified: VerifiedPublicSourceStageArtifact,
    decision_time: datetime,
    created_at: datetime,
    expected_symbols: tuple[str, ...],
    source_manifest: SourceManifest,
    asset_types: Mapping[str, AssetType],
) -> MarketDataDatasetArtifact:
    if verified.stage is not PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN:
        raise ValueError("only verified frozen history can produce a Market Data Dataset")
    if not isinstance(source_manifest, SourceManifest):
        raise TypeError("source_manifest must be a verified SourceManifest")
    if source_manifest.decision_time != DecisionTime(decision_time):
        raise ValueError("SourceManifest DecisionTime mismatch")
    if source_manifest.source_conflicts:
        raise ValueError("SourceManifest conflicts cannot enter canonical market data")
    if verified.batch.source_conflicts:
        raise ValueError("public history source conflicts cannot enter canonical market data")
    archived_references = tuple(
        sorted((item.reference for item in verified.batch.raw_payloads), key=str)
    )
    manifest_references = tuple(sorted(source_manifest.source_artifacts, key=str))
    if manifest_references != archived_references:
        raise ValueError("SourceManifest source scope mismatch")
    expected_symbols = tuple(sorted(expected_symbols))
    if tuple(sorted(asset_types)) != expected_symbols:
        raise ValueError("asset type authority must exactly cover expected symbols")
    raw_by_id = {item.source_artifact_id: item for item in verified.batch.raw_payloads}
    previous_close: dict[str, Decimal] = {}
    bars: list[CanonicalMarketBar] = []
    for source_bar in sorted(
        verified.batch.bars,
        key=lambda item: (item.symbol, item.event_time),
    ):
        if source_bar.symbol not in expected_symbols:
            raise ValueError("source history contains a symbol outside declared scope")
        if source_bar.adjustment_basis not in _SUPPORTED_RAW_ADJUSTMENT_BASES:
            raise ValueError(
                f"unsupported adjustment basis: {source_bar.adjustment_basis}"
            )
        if source_bar.unit != "CNY":
            raise ValueError("public history price unit must be CNY")
        source = raw_by_id.get(source_bar.source_artifact_id)
        if source is None:
            raise ValueError("public history bar references unarchived source bytes")
        market_date = source_bar.event_time.astimezone(_SHANGHAI).date()
        event_start = normalize_canonical_datetime(
            datetime.combine(market_date, time(9, 30), tzinfo=_SHANGHAI)
        )
        event_end = normalize_canonical_datetime(source_bar.event_time)
        available_at = normalize_canonical_datetime(
            source_bar.available_time.value
            if source_bar.available_time is not None
            else source.retrieved_time.value
        )
        close = Decimal(str(source_bar.close))
        exchange = Exchange(source_bar.symbol[-2:])
        bars.append(
            CanonicalMarketBar.create(
                symbol=source_bar.symbol,
                exchange=exchange,
                asset_type=asset_types[source_bar.symbol],
                timeframe=Timeframe.DAILY,
                market_date=market_date,
                event_start=event_start,
                event_end=event_end,
                available_at=available_at,
                open=Decimal(str(source_bar.open)),
                high=Decimal(str(source_bar.high)),
                low=Decimal(str(source_bar.low)),
                close=close,
                previous_close=previous_close.get(source_bar.symbol),
                volume=Decimal(str(source_bar.volume)),
                volume_unit=VolumeUnit.SHARES,
                amount=Decimal(str(source_bar.amount)),
                turnover_rate=None,
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=TradingStatus.UNKNOWN,
                price_limit_state=PriceLimitState.UNKNOWN,
                source_artifact_id=source.source_artifact_id,
                source_content_hash=source.raw_hash,
            )
        )
        previous_close[source_bar.symbol] = close
    limitations = tuple(
        sorted(
            {
                *verified.batch.limitations,
                "FORMAL_PIT_NOT_ESTABLISHED",
                "PUBLIC_DATA_EXPLORATORY_ONLY",
                "SOURCE_FLOAT_NORMALIZED_TO_DECIMAL",
                "TRADING_AND_LIMIT_STATUS_NOT_ESTABLISHED_BY_HISTORY_SOURCE",
                "TURNOVER_RATE_NOT_PROVIDED",
            }
        )
    )
    return MarketDataDatasetArtifact.create(
        decision_time=normalize_canonical_datetime(decision_time),
        created_at=normalize_canonical_datetime(created_at),
        bars=tuple(bars),
        expected_symbols=expected_symbols,
        expected_timeframes=(Timeframe.DAILY,),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="public-history-raw-v1",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (source_manifest.source_manifest_id, source_manifest.content_hash),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=limitations,
    )
