from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    ReplayCheckStatus,
    verify_replay_reference,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    VerifiedCompositeEvidenceStageHandler,
    ordered_references,
)
from market_regime_alpha.application.canonical_lifecycle.stages.research import (
    PlatformResearchStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.materialization_v2 import (
    FeatureMaterializationRunner,
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.technical.catalog import (
    canonical_technical_feature_set,
)
from market_regime_alpha.forecasting import (
    CalibrationStatus,
    PathForecastStatus,
    load_verified_path_forecast,
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
    publish_market_data_dataset,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)
from market_regime_alpha.signals import (
    SignalRunArtifactV2,
    canonical_signal_input_mapping,
    load_verified_signal_run_v2,
    replay_signal_run_v2,
)
from tests.application.canonical_lifecycle.test_research_stages import (
    _context,
    _stage_fixture,
)


UTC = timezone.utc
SOURCE_HASH = "sha256:" + "1" * 64
MANIFEST_HASH = "sha256:" + "2" * 64


def test_verified_feature_bundle_drives_signal_forecast_and_blocked_entry(
    tmp_path: Path,
) -> None:
    fixture = _stage_fixture(tmp_path / "h6", ranked_percentiles=True)
    results = []
    results.append(
        VerifiedCompositeEvidenceStageHandler().execute(
            _context(
                fixture,
                LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
                tuple(results),
            )
        )
    )
    results.append(
        PlatformResearchStageHandler(
            configuration=fixture.research_configuration,
            output_root=tmp_path / "runtime" / "research",
        ).execute(
            _context(
                fixture,
                LifecycleStageName.PLATFORM_RESEARCH,
                tuple(results),
            )
        )
    )
    research = load_verified_research_artifact(
        Path(results[-1].output_references[0].locator or "")
    )
    symbols = tuple(sorted(item.symbol for item in research.artifact.candidate_set.selected))
    assert symbols
    bundle, dataset = _materialize_bundle(
        tmp_path=tmp_path,
        symbols=symbols,
        decision_time=fixture.as_of_time,
    )
    mapping = canonical_signal_input_mapping(
        effective_from=fixture.as_of_time - timedelta(days=30)
    )
    feature_reference = LifecycleObjectReference(
        object_type=LifecycleObjectType.FEATURE_BUNDLE,
        object_id=LifecycleObjectId(str(bundle.artifact.bundle_id)),
        content_hash=bundle.artifact.content_hash,
        reader_kind=LifecycleReaderKind.FEATURE_BUNDLE_READER,
        locator=str(bundle.root),
        available_at=bundle.artifact.created_at,
    )
    dataset_reference = LifecycleObjectReference(
        object_type=LifecycleObjectType.MARKET_DATA_DATASET,
        object_id=LifecycleObjectId(str(dataset.artifact.dataset_id)),
        content_hash=dataset.artifact.content_hash,
        reader_kind=LifecycleReaderKind.MARKET_DATA_DATASET_READER,
        locator=str(dataset.root),
        available_at=dataset.artifact.created_at,
    )
    mapping_reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING,
        configuration_id=mapping.configuration_id,
        configuration_version=mapping.configuration_version,
        content_hash=mapping.configuration_hash,
        locator=str(tmp_path / "mapping.json"),
    )
    feature_set_reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.FEATURE_SET,
        configuration_id=bundle.artifact.feature_set.feature_set_id,
        configuration_version=bundle.artifact.feature_set.feature_set_version,
        content_hash=bundle.artifact.feature_set.content_hash,
        locator=str(tmp_path / "feature-set.json"),
    )
    feature_models = tuple(
        LifecycleModelVersionReference(
            model_id=item.artifact.model_id,
            model_version=item.artifact.model_version,
            content_hash=canonical_hash(
                {
                    "model_id": str(item.artifact.model_id),
                    "model_version": item.artifact.model_version,
                }
            ),
        )
        for item in bundle.artifacts
    )
    fixture = replace(
        fixture,
        initial_references=ordered_references(
            (*fixture.initial_references, dataset_reference, feature_reference)
        ),
        configuration_references=tuple(
            sorted(
                (
                    *fixture.configuration_references,
                    feature_set_reference,
                    mapping_reference,
                ),
                key=lambda item: item.sort_key,
            )
        ),
        model_references=tuple(
            sorted(
                {*fixture.model_references, *feature_models},
                key=lambda item: item.sort_key,
            )
        ),
    )

    signal_result = SignalStageHandler(
        configuration=fixture.signal_configuration,
        mapping_configuration=mapping,
        feature_set_configuration=bundle.artifact.feature_set,
        output_root=tmp_path / "runtime" / "signals",
    ).execute(
        _context(fixture, LifecycleStageName.SIGNAL, tuple(results))
    )
    results.append(signal_result)
    signal = load_verified_signal_run_v2(
        Path(signal_result.output_references[0].locator or "")
    )
    assert isinstance(signal.artifact, SignalRunArtifactV2)
    assert signal.artifact.feature_bundle_id == bundle.artifact.bundle_id
    assert any(
        factor.value is not None
        for observation in signal.artifact.observations
        for factor in observation.factors
    )
    assert "H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE" not in signal_result.reason_codes
    assert feature_reference in signal_result.input_references
    assert replay_signal_run_v2(
        signal.root, feature_bundle=bundle
    ).artifact == signal.artifact
    replay_references = (
        dataset_reference,
        feature_reference,
        signal_result.output_references[0],
    )
    assert all(
        verify_replay_reference(
            reference, all_references=replay_references
        ).status
        is ReplayCheckStatus.REPLAY_STABLE
        for reference in replay_references
    )

    forecast_result = PathForecastStageHandler(
        configuration=fixture.forecast_configuration,
        output_root=tmp_path / "runtime" / "forecast",
    ).execute(
        _context(fixture, LifecycleStageName.PATH_FORECAST, tuple(results))
    )
    results.append(forecast_result)
    forecasts = tuple(
        load_verified_path_forecast(Path(item.locator or ""))
        for item in forecast_result.output_references
    )
    assert forecasts
    assert all(
        item.artifact.forecast.forecast_status
        is PathForecastStatus.DATA_INSUFFICIENT
        for item in forecasts
    )
    assert all(
        item.artifact.forecast.calibration_status
        is CalibrationStatus.DATA_INSUFFICIENT
        for item in forecasts
    )
    assert all(
        item.artifact.signal_snapshot in signal.artifact.snapshots
        for item in forecasts
    )

    entry_result = EntryAssessmentStageHandler(
        authority_ceiling=LifecycleAuthorityCeiling()
    ).execute(
        _context(fixture, LifecycleStageName.ENTRY_ASSESSMENT, tuple(results))
    )
    assert entry_result.run_status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert entry_result.output_references == ()
    assert "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE" in entry_result.reason_codes


def _materialize_bundle(
    *, tmp_path: Path, symbols: tuple[str, ...], decision_time: datetime
):
    created_at = decision_time + timedelta(minutes=5)
    bars = tuple(
        bar
        for symbol_index, symbol in enumerate(symbols)
        for bar in _bars(
            symbol=symbol,
            symbol_index=symbol_index,
            decision_time=decision_time,
        )
    )
    dataset = MarketDataDatasetArtifact.create(
        decision_time=decision_time,
        created_at=created_at,
        bars=bars,
        expected_symbols=symbols,
        expected_timeframes=(Timeframe.DAILY, Timeframe.MINUTE_5),
        adjustment_policy=PriceAdjustmentPolicy.create(
            policy_version="1.0.0",
            mode=AdjustmentMode.RAW,
            factors=(),
            limitations=(),
        ),
        source_manifest_references=(
            (ArtifactId("lifecycle-feature-source-manifest"), MANIFEST_HASH),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    dataset_package = publish_market_data_dataset(
        root=tmp_path / "market-data", artifact=dataset
    )
    verified_dataset = load_verified_market_data_dataset(dataset_package)
    feature_set = canonical_technical_feature_set(
        effective_from=decision_time - timedelta(days=365)
    )
    receipt = FeatureMaterializationRunner(max_workers=2).run(
        verified_dataset=verified_dataset,
        feature_set=feature_set,
        decision_time=decision_time,
        created_at=created_at,
        selected_symbols=symbols,
        code_revision="lifecycle-feature-signal-test",
        output_root=tmp_path / "feature-run",
        idempotency_key="lifecycle-feature-signal-test",
        resume=True,
    )
    return (
        load_verified_feature_bundle_v2(
            tmp_path / "feature-run" / receipt.bundle_locator,
            artifact_root=tmp_path / "feature-run" / "feature-artifacts",
        ),
        verified_dataset,
    )


def _bars(
    *, symbol: str, symbol_index: int, decision_time: datetime
) -> tuple[CanonicalMarketBar, ...]:
    exchange = Exchange.SH if symbol.endswith(".SH") else Exchange.SZ
    daily = []
    first_date = decision_time.date() - timedelta(days=70)
    for index in range(70):
        market_date = first_date + timedelta(days=index)
        close = Decimal("10") + Decimal(symbol_index) + Decimal(index) / Decimal("100")
        event_end = datetime.combine(
            market_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=6)
        daily.append(
            CanonicalMarketBar.create(
                symbol=symbol,
                exchange=exchange,
                asset_type=AssetType.A_SHARE,
                timeframe=Timeframe.DAILY,
                market_date=market_date,
                event_start=event_end - timedelta(hours=6),
                event_end=event_end,
                available_at=event_end,
                open=close - Decimal("0.02"),
                high=close + Decimal("0.1"),
                low=close - Decimal("0.1"),
                close=close,
                previous_close=(close - Decimal("0.01") if index else None),
                volume=Decimal(100000 + index * 100),
                volume_unit=VolumeUnit.SHARES,
                amount=close * Decimal(100000 + index * 100),
                turnover_rate=Decimal("0.01"),
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=TradingStatus.TRADING,
                price_limit_state=PriceLimitState.NORMAL,
                source_artifact_id=ArtifactId(
                    f"lifecycle-daily-source-{symbol_index}-{index}"
                ),
                source_content_hash=SOURCE_HASH,
            )
        )
    minute = []
    for index in range(2):
        event_end = decision_time - timedelta(minutes=5 * (1 - index))
        price = Decimal("11") + Decimal(symbol_index) + Decimal(index) / Decimal("10")
        minute.append(
            CanonicalMarketBar.create(
                symbol=symbol,
                exchange=exchange,
                asset_type=AssetType.A_SHARE,
                timeframe=Timeframe.MINUTE_5,
                market_date=decision_time.date(),
                event_start=event_end - timedelta(minutes=5),
                event_end=event_end,
                available_at=event_end,
                open=price,
                high=price,
                low=price,
                close=price,
                previous_close=price - Decimal("0.1"),
                volume=Decimal(100 + index * 100),
                volume_unit=VolumeUnit.SHARES,
                amount=price * Decimal(100 + index * 100),
                turnover_rate=None,
                adjustment_mode=AdjustmentMode.RAW,
                adjustment_factor=Decimal("1"),
                trading_status=TradingStatus.TRADING,
                price_limit_state=PriceLimitState.NORMAL,
                source_artifact_id=ArtifactId(
                    f"lifecycle-minute-source-{symbol_index}-{index}"
                ),
                source_content_hash=SOURCE_HASH,
            )
        )
    return (*daily, *minute)
