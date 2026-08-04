from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    AcquiredSourcePayload,
    PublicBar,
    PublicCompositeBatch,
    PublicSourceAcquisitionStage,
    load_verified_public_source_stage_artifact,
    publish_public_source_stage_artifact,
)
from market_regime_alpha.data.providers.public_composite.contracts import (
    SourceFieldFinality,
)
from market_regime_alpha.market_data import (
    AdjustmentMode,
    AssetType,
    CanonicalMarketBar,
    Exchange,
    FormalPitStatus,
    MarketDataDatasetArtifact,
    PriceAdjustmentPolicy,
    PriceLimitState,
    Timeframe,
    TradingStatus,
    VolumeUnit,
    load_verified_market_data_dataset,
    normalize_public_history_stage,
    publish_market_data_dataset,
    replay_market_data_dataset,
)


UTC = timezone.utc
DECISION_TIME = datetime(2026, 8, 4, 2, 30, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
SOURCE_HASH = "sha256:" + "1" * 64
MANIFEST_HASH = "sha256:" + "2" * 64


def _bar(
    *,
    symbol: str = "600000.SH",
    market_date: date = date(2026, 8, 3),
    available_at: datetime = datetime(2026, 8, 3, 7, 1, tzinfo=UTC),
    amount: Decimal | None = Decimal("1050000"),
) -> CanonicalMarketBar:
    exchange = Exchange(symbol[-2:])
    start = datetime.combine(
        market_date,
        datetime.min.time(),
        tzinfo=UTC,
    ) + timedelta(hours=1, minutes=30)
    end = start + timedelta(hours=5, minutes=30)
    return CanonicalMarketBar.create(
        symbol=symbol,
        exchange=exchange,
        asset_type=AssetType.A_SHARE,
        timeframe=Timeframe.DAILY,
        market_date=market_date,
        event_start=start,
        event_end=end,
        available_at=available_at,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9.8"),
        close=Decimal("10.5"),
        previous_close=Decimal("9.9"),
        volume=Decimal("100000"),
        volume_unit=VolumeUnit.SHARES,
        amount=amount,
        turnover_rate=None,
        adjustment_mode=AdjustmentMode.RAW,
        adjustment_factor=Decimal("1"),
        trading_status=TradingStatus.TRADING,
        price_limit_state=PriceLimitState.NORMAL,
        source_artifact_id=ArtifactId(f"source-{symbol}-{market_date}"),
        source_content_hash=SOURCE_HASH,
    )


def _dataset(
    *,
    bars: tuple[CanonicalMarketBar, ...] | None = None,
) -> MarketDataDatasetArtifact:
    return MarketDataDatasetArtifact.create(
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        bars=bars or (
            _bar(market_date=date(2026, 8, 1)),
            _bar(market_date=date(2026, 8, 3)),
            _bar(symbol="000001.SZ", market_date=date(2026, 8, 3), amount=None),
        ),
        expected_symbols=("000001.SZ", "600000.SH"),
        expected_timeframes=(Timeframe.DAILY,),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="1.0.0",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (ArtifactId("source-manifest-1"), MANIFEST_HASH),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )


def test_dataset_is_deterministic_partitioned_and_content_addressed() -> None:
    forward = _dataset()
    reverse = _dataset(bars=tuple(reversed(tuple(forward.iter_bars()))))

    assert reverse.dataset_id == forward.dataset_id
    assert reverse.content_hash == forward.content_hash
    assert reverse.bar_count == 3
    assert tuple(item.symbol for item in forward.partitions) == (
        "000001.SZ",
        "600000.SH",
    )
    assert forward.coverage.missing_field_counts == (
        ("amount", 1),
        ("turnover_rate", 3),
    )


def test_dataset_rejects_duplicate_or_future_bar() -> None:
    bar = _bar()
    with pytest.raises(ValueError, match="duplicate market bar"):
        _dataset(bars=(bar, bar))
    with pytest.raises(ValueError, match="available after DecisionTime"):
        _dataset(
            bars=(
                _bar(
                    available_at=DECISION_TIME + timedelta(seconds=1),
                ),
            )
        )


def test_dataset_publish_read_select_and_replay(tmp_path: Path) -> None:
    artifact = _dataset()
    package = publish_market_data_dataset(root=tmp_path, artifact=artifact)

    verified = load_verified_market_data_dataset(
        package,
        symbols=("600000.SH",),
        timeframes=(Timeframe.DAILY,),
    )
    replayed = replay_market_data_dataset(package)

    assert verified.artifact == artifact
    assert {item.symbol for item in verified.bars} == {"600000.SH"}
    assert len(verified.bars) == 2
    assert replayed.artifact.content_hash == artifact.content_hash
    assert publish_market_data_dataset(root=tmp_path, artifact=artifact) == package


def test_dataset_reader_detects_missing_or_tampered_partition(tmp_path: Path) -> None:
    artifact = _dataset()
    package = publish_market_data_dataset(root=tmp_path, artifact=artifact)
    partition = package / artifact.partitions[0].relative_path
    original = partition.read_bytes()

    partition.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_market_data_dataset(package)

    partition.write_bytes(original)
    partition.unlink()
    with pytest.raises(ValueError, match="exact file set mismatch"):
        load_verified_market_data_dataset(package)


def test_dataset_publication_failure_cleans_staging_and_leaves_no_final(
    tmp_path: Path,
) -> None:
    artifact = _dataset()

    def fail(stage: str) -> None:
        if stage == "AFTER_STAGING_VALIDATED":
            raise RuntimeError("injected publish failure")

    with pytest.raises(RuntimeError, match="injected publish failure"):
        publish_market_data_dataset(
            root=tmp_path,
            artifact=artifact,
            failure_injector=fail,
        )

    assert not (tmp_path / str(artifact.dataset_id)).exists()
    assert tuple(tmp_path.iterdir()) == ()


def test_normalize_verified_public_history_uses_archived_source_bytes(
    tmp_path: Path,
) -> None:
    retrieved_at = datetime(2026, 8, 4, 2, 0, tzinfo=UTC)
    raw = AcquiredSourcePayload(
        provider_id=ProviderId("baostock-public"),
        product="query_history_k_data_plus:daily:adjustflag=3",
        locator="baostock://history/600000.SH",
        raw_payload=b"date,open,high,low,close,volume,amount",
        retrieved_time=RetrievedAt(retrieved_at),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    source_bar = PublicBar(
        symbol="600000.SH",
        event_time=datetime(2026, 8, 3, 15, 0, tzinfo=timezone(timedelta(hours=8))),
        available_time=None,
        source_artifact_id=raw.source_artifact_id,
        open=10.0,
        high=11.0,
        low=9.8,
        close=10.5,
        volume=100000.0,
        amount=1050000.0,
        unit="CNY",
        adjustment_basis="BAOSTOCK_ADJUSTFLAG_3",
        finality=SourceFieldFinality.UNKNOWN,
    )
    source_package = publish_public_source_stage_artifact(
        root=tmp_path / "source",
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=PublicCompositeBatch(
            raw_payloads=(raw,),
            bars=(source_bar,),
            quotes=(),
            source_conflicts=(),
            limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
        ),
    )
    verified_source = load_verified_public_source_stage_artifact(source_package)

    normalized = normalize_public_history_stage(
        verified=verified_source,
        decision_time=DECISION_TIME,
        created_at=CREATED_AT,
        expected_symbols=("600000.SH",),
        source_manifest_id=ArtifactId("source-manifest-1"),
        source_manifest_hash=MANIFEST_HASH,
        asset_types={"600000.SH": AssetType.A_SHARE},
    )
    bar = next(normalized.iter_bars())

    assert bar.available_at == retrieved_at
    assert bar.source_artifact_id == raw.source_artifact_id
    assert bar.source_content_hash == raw.raw_hash
    assert bar.open == Decimal("10.0")
    assert bar.turnover_rate is None
    assert "SOURCE_FLOAT_NORMALIZED_TO_DECIMAL" in normalized.limitations


def test_normalizer_rejects_non_raw_adjustment_basis(tmp_path: Path) -> None:
    raw = AcquiredSourcePayload(
        provider_id=ProviderId("provider"),
        product="adjusted-history",
        locator="provider://adjusted",
        raw_payload=b"adjusted",
        retrieved_time=RetrievedAt(datetime(2026, 8, 4, 2, 0, tzinfo=UTC)),
        limitations=(),
    )
    source_bar = PublicBar(
        symbol="600000.SH",
        event_time=datetime(2026, 8, 3, 15, 0, tzinfo=timezone(timedelta(hours=8))),
        available_time=None,
        source_artifact_id=raw.source_artifact_id,
        open=10.0,
        high=11.0,
        low=9.8,
        close=10.5,
        volume=100000.0,
        amount=1050000.0,
        unit="CNY",
        adjustment_basis="QFQ_LATEST_FACTOR",
        finality=SourceFieldFinality.UNKNOWN,
    )
    package = publish_public_source_stage_artifact(
        root=tmp_path / "source",
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=PublicCompositeBatch(
            raw_payloads=(raw,),
            bars=(source_bar,),
            quotes=(),
            source_conflicts=(),
            limitations=(),
        ),
    )

    with pytest.raises(ValueError, match="unsupported adjustment basis"):
        normalize_public_history_stage(
            verified=load_verified_public_source_stage_artifact(package),
            decision_time=DECISION_TIME,
            created_at=CREATED_AT,
            expected_symbols=("600000.SH",),
            source_manifest_id=ArtifactId("source-manifest-1"),
            source_manifest_hash=MANIFEST_HASH,
            asset_types={"600000.SH": AssetType.A_SHARE},
        )
