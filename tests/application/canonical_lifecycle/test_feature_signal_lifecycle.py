from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import json
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
from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.durable_replay import (
    run_durable_lifecycle_replay,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.feature_handoff import (
    OperationalFeatureHandoffRunner,
    UniverseFeatureScopeKind,
)
from market_regime_alpha.application.canonical_lifecycle.replay import (
    ReplayCheckStatus,
    LifecycleReplayStatus,
    verify_replay_reference,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
)
from tests.postgres_path_repositories import (
    PostgresFeatureMaterializationRunRepository,
    PostgresLifecycleRunRepository,
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
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.trading_calendar import (
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.features.materialization_run import (
    FeatureMaterializationExecutionMode,
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
from market_regime_alpha.market_data.minute_source import (
    CanonicalVolumeUnitPolicy,
    MinuteSourceRequest,
    MinuteSourceResponse,
    MinuteNormalizationResult,
    RawMinuteSourceArtifact,
    RawMinuteSourceReader,
    build_combined_market_data_dataset,
    normalize_tencent_minute_source,
    publish_raw_minute_source,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)
from market_regime_alpha.signals import (
    SignalRunArtifactV3,
    canonical_all_factors_required_policy,
    canonical_signal_freshness_policy,
    canonical_signal_input_mapping_v2,
    canonical_signal_model_configuration_v2,
    load_verified_signal_run_v3,
    replay_signal_run_v3,
)
from tests.application.canonical_lifecycle.test_research_stages import (
    _context,
    _stage_fixture,
)
from tests.application.canonical_lifecycle.test_decision_risk_stages import (
    _NeverCalledHandler,
)
from tests.application.canonical_lifecycle.test_lifecycle_integration import (
    _TickingClock,
)


UTC = timezone.utc
SOURCE_HASH = "sha256:" + "1" * 64


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
    daily_reference = next(item for item in fixture.initial_references if item.object_type is LifecycleObjectType.DAILY_DECISION_ARTIFACT)
    daily = load_verified_daily_decision_artifact(Path(daily_reference.locator or ""))
    assert daily.bundle.universe_snapshot is not None
    universe_symbols = _universe_of_size_100(daily.bundle.universe_snapshot.member_symbols)
    bundle, dataset = _materialize_bundle(
        tmp_path=tmp_path,
        symbols=universe_symbols,
        decision_time=fixture.as_of_time,
        source_manifest_reference=(
            daily.bundle.source_manifest.source_manifest_id,
            daily.bundle.source_manifest.content_hash,
        ),
    )
    assert len(bundle.artifact.symbols) == 100
    assert "RECORDED_TENCENT_PROVIDER_FIXTURE" in dataset.artifact.limitations
    assert len(dataset.artifact.source_manifest_references) == 2
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
    research_reference = next(
        item for item in results[-1].output_references if item.object_type is LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT
    )
    research = load_verified_research_artifact(Path(research_reference.locator or ""))
    symbols = tuple(sorted(item.symbol for item in research.artifact.candidate_set.selected))
    assert len(symbols) >= 5
    assert "CANDIDATE_BOUNDARY_TIE_EXPANDED" in (
        research.artifact.candidate_set.reason_codes
    )
    assert set(symbols).issubset(universe_symbols)
    mapping = canonical_signal_input_mapping_v2(effective_from=fixture.as_of_time - timedelta(days=30))
    requirement_policy = canonical_all_factors_required_policy()
    calendar = _trading_calendar(dataset)
    freshness_policy = canonical_signal_freshness_policy(trading_calendar=calendar)
    signal_configuration = canonical_signal_model_configuration_v2()
    calendar_path = tmp_path / "trading-calendar.json"
    calendar_path.write_text(canonical_json(calendar.to_canonical_dict()), encoding="utf-8")
    feature_reference = LifecycleObjectReference(
        object_type=LifecycleObjectType.FEATURE_BUNDLE,
        object_id=LifecycleObjectId(str(bundle.artifact.bundle_id)),
        content_hash=bundle.artifact.content_hash,
        reader_kind=LifecycleReaderKind.FEATURE_BUNDLE_READER,
        locator=str(bundle.root),
        available_at=bundle.artifact.available_at,
    )
    dataset_reference = LifecycleObjectReference(
        object_type=LifecycleObjectType.MARKET_DATA_DATASET,
        object_id=LifecycleObjectId(str(dataset.artifact.dataset_id)),
        content_hash=dataset.artifact.content_hash,
        reader_kind=LifecycleReaderKind.MARKET_DATA_DATASET_READER,
        locator=str(dataset.root),
        available_at=dataset.artifact.available_at,
    )
    calendar_reference = LifecycleObjectReference(
        object_type=LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
        object_id=LifecycleObjectId(str(calendar.artifact_id)),
        content_hash=calendar.content_hash,
        reader_kind=LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
        locator=str(calendar_path),
        available_at=fixture.as_of_time,
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
    requirement_reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.SIGNAL_FACTOR_REQUIREMENT,
        configuration_id=requirement_policy.policy_id,
        configuration_version=requirement_policy.policy_version,
        content_hash=requirement_policy.policy_hash,
        locator=str(tmp_path / "requirement-policy.json"),
    )
    freshness_reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.SIGNAL_FACTOR_FRESHNESS,
        configuration_id=freshness_policy.policy_id,
        configuration_version=freshness_policy.policy_version,
        content_hash=freshness_policy.policy_hash,
        locator=str(tmp_path / "freshness-policy.json"),
    )
    signal_configuration_reference = LifecycleConfigurationReference(
        configuration_kind=LifecycleConfigurationKind.SIGNAL_MODEL,
        configuration_id=signal_configuration.configuration_id,
        configuration_version=signal_configuration.configuration_version,
        content_hash=signal_configuration.configuration_hash,
        locator=str(tmp_path / "signal-model-v2.json"),
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
            (
                *fixture.initial_references,
                calendar_reference,
                dataset_reference,
                feature_reference,
            )
        ),
        configuration_references=tuple(
            sorted(
                (
                    *(
                        item
                        for item in fixture.configuration_references
                        if item.configuration_kind is not LifecycleConfigurationKind.SIGNAL_MODEL
                    ),
                    feature_set_reference,
                    mapping_reference,
                    requirement_reference,
                    freshness_reference,
                    signal_configuration_reference,
                ),
                key=lambda item: item.sort_key,
            )
        ),
        model_references=tuple(
            sorted(
                {
                    *(item for item in fixture.model_references if item.model_id != fixture.signal_configuration.model_id),
                    *feature_models,
                    LifecycleModelVersionReference(
                        model_id=signal_configuration.model_id,
                        model_version=signal_configuration.model_version,
                        content_hash=canonical_hash(
                            {
                                "model_id": str(signal_configuration.model_id),
                                "model_version": signal_configuration.model_version,
                            }
                        ),
                    ),
                },
                key=lambda item: item.sort_key,
            )
        ),
    )

    signal_result = SignalStageHandler(
        configuration=signal_configuration,
        mapping_configuration=mapping,
        feature_set_configuration=bundle.artifact.feature_set,
        requirement_policy=requirement_policy,
        freshness_policy=freshness_policy,
        output_root=tmp_path / "runtime" / "signals",
    ).execute(_context(fixture, LifecycleStageName.SIGNAL, tuple(results)))
    results.append(signal_result)
    signal_reference = next(item for item in signal_result.output_references if item.object_type is LifecycleObjectType.SIGNAL_ARTIFACT)
    view_reference = next(
        item for item in signal_result.output_references if item.object_type is LifecycleObjectType.CANDIDATE_FEATURE_VIEW
    )
    signal = load_verified_signal_run_v3(Path(signal_reference.locator or ""))
    assert isinstance(signal.artifact, SignalRunArtifactV3)
    assert signal.artifact.feature_bundle_id == bundle.artifact.bundle_id
    assert signal.artifact.candidate_feature_view.universe_symbols == universe_symbols
    assert signal.artifact.candidate_feature_view.candidate_symbols == symbols
    assert len(signal.artifact.snapshots) == len(symbols)
    assert any(factor.value is not None for observation in signal.artifact.observations for factor in observation.factors)
    assert "H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE" not in signal_result.reason_codes
    assert feature_reference in signal_result.input_references
    assert dataset_reference in signal_result.input_references
    assert calendar_reference in signal_result.input_references
    candidate_reference = next(item for item in signal_result.input_references if item.object_type is LifecycleObjectType.CANDIDATE_SET)
    assert candidate_reference.content_hash == research.artifact.candidate_set.envelope.content_hash
    assert (
        replay_signal_run_v3(
            signal.root,
            feature_bundle=bundle,
            verified_dataset=dataset,
            trading_calendar=calendar,
        ).artifact
        == signal.artifact
    )
    replay_references = (
        calendar_reference,
        candidate_reference,
        dataset_reference,
        feature_reference,
        signal_reference,
        view_reference,
    )
    replay_checks = {
        reference.object_type: verify_replay_reference(reference, all_references=replay_references) for reference in replay_references
    }
    assert all(
        replay_checks[item].status is ReplayCheckStatus.REPLAY_STABLE
        for item in (
            LifecycleObjectType.MARKET_DATA_DATASET,
            LifecycleObjectType.FEATURE_BUNDLE,
            LifecycleObjectType.CANDIDATE_SET,
            LifecycleObjectType.SIGNAL_ARTIFACT,
        )
    )
    assert all(
        replay_checks[item].status is ReplayCheckStatus.VERIFIED_READ_ONLY
        for item in (
            LifecycleObjectType.CANDIDATE_FEATURE_VIEW,
            LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
        )
    )

    forecast_result = PathForecastStageHandler(
        configuration=fixture.forecast_configuration,
        output_root=tmp_path / "runtime" / "forecast",
    ).execute(_context(fixture, LifecycleStageName.PATH_FORECAST, tuple(results)))
    results.append(forecast_result)
    forecasts = tuple(load_verified_path_forecast(Path(item.locator or "")) for item in forecast_result.output_references)
    assert forecasts
    assert all(item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT for item in forecasts)
    assert all(item.artifact.forecast.calibration_status is CalibrationStatus.DATA_INSUFFICIENT for item in forecasts)
    assert "FORMAL_PATH_SAMPLE_PROVIDER_NOT_CONFIGURED" in forecast_result.reason_codes
    assert all(item.artifact.signal_snapshot in signal.artifact.snapshots for item in forecasts)

    entry_result = EntryAssessmentStageHandler(authority_ceiling=LifecycleAuthorityCeiling()).execute(
        _context(fixture, LifecycleStageName.ENTRY_ASSESSMENT, tuple(results))
    )
    assert entry_result.run_status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    assert entry_result.output_references == ()
    assert "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE" in entry_result.reason_codes

    configuration_values = {
        LifecycleConfigurationKind.RESEARCH_PIPELINE: fixture.research_configuration,
        LifecycleConfigurationKind.SIGNAL_MODEL: signal_configuration,
        LifecycleConfigurationKind.PATH_FORECAST: fixture.forecast_configuration,
        LifecycleConfigurationKind.FEATURE_SET: bundle.artifact.feature_set,
        LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING: mapping,
        LifecycleConfigurationKind.SIGNAL_FACTOR_REQUIREMENT: requirement_policy,
        LifecycleConfigurationKind.SIGNAL_FACTOR_FRESHNESS: freshness_policy,
    }
    persisted_configuration_references = []
    for reference in fixture.configuration_references:
        configuration = configuration_values[reference.configuration_kind]
        configuration_path = tmp_path / "journal-configurations" / f"{reference.configuration_id}.json"
        configuration_path.parent.mkdir(parents=True, exist_ok=True)
        configuration_path.write_text(canonical_json(configuration.to_canonical_dict()), encoding="utf-8")
        persisted_configuration_references.append(replace(reference, locator=str(configuration_path.resolve())))
    fixture = replace(
        fixture,
        configuration_references=tuple(
            sorted(
                persisted_configuration_references,
                key=lambda item: item.sort_key,
            )
        ),
    )
    manifest = CanonicalLifecycleInputManifest.create(
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        created_at=fixture.as_of_time + timedelta(seconds=1),
        input_references=fixture.initial_references,
        configuration_references=fixture.configuration_references,
        model_references=fixture.model_references,
        authority_ceiling=LifecycleAuthorityCeiling(),
        limitations=("ENTRY_MODEL_NOT_EMPIRICALLY_VALIDATED",),
    )
    manifest_path = tmp_path / "journal-input-manifest.json"
    manifest_path.write_text(canonical_json(manifest.to_canonical_dict()), encoding="utf-8")
    output_root = tmp_path / "journal-runtime"
    command = CanonicalLifecycleCommand(
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        idempotency_key="feature-signal-durable-journal",
        input_manifest_id=manifest.manifest_id,
        input_content_hash=manifest.content_hash,
        input_manifest_locator=manifest_path,
        input_references=fixture.initial_references,
        configuration_references=fixture.configuration_references,
        model_references=fixture.model_references,
        stop_after_stage=None,
        output_directory=output_root,
    )
    configured_handlers = {
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE: (VerifiedCompositeEvidenceStageHandler()),
        LifecycleStageName.PLATFORM_RESEARCH: PlatformResearchStageHandler(
            configuration=fixture.research_configuration,
            output_root=output_root / "research",
        ),
        LifecycleStageName.SIGNAL: SignalStageHandler(
            configuration=signal_configuration,
            mapping_configuration=mapping,
            feature_set_configuration=bundle.artifact.feature_set,
            requirement_policy=requirement_policy,
            freshness_policy=freshness_policy,
            output_root=output_root / "signals",
        ),
        LifecycleStageName.PATH_FORECAST: PathForecastStageHandler(
            configuration=fixture.forecast_configuration,
            output_root=output_root / "forecasts",
        ),
        LifecycleStageName.ENTRY_ASSESSMENT: EntryAssessmentStageHandler(authority_ceiling=LifecycleAuthorityCeiling()),
    }
    handlers = tuple(configured_handlers.get(stage, _NeverCalledHandler(stage)) for stage in LIFECYCLE_STAGE_ORDER)
    repository = PostgresLifecycleRunRepository(tmp_path / "lifecycle.postgres-scope")
    runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=_TickingClock(fixture.as_of_time + timedelta(hours=1)),
    )
    first = runner.run(command)
    assert first.run.status is LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION
    signal_receipt = next(receipt for receipt in first.receipts if receipt.stage_name is LifecycleStageName.SIGNAL)
    journal_history = repository.history(first.run.run_id)
    journal_research_stage = next(stage for stage in journal_history.stages if stage.stage_name is LifecycleStageName.PLATFORM_RESEARCH)
    journal_signal_stage = next(stage for stage in journal_history.stages if stage.stage_name is LifecycleStageName.SIGNAL)
    journal_candidate_output = next(
        reference for reference in journal_research_stage.output_references if reference.object_type is LifecycleObjectType.CANDIDATE_SET
    )
    journal_candidate_input = next(
        reference for reference in journal_signal_stage.input_references if reference.object_type is LifecycleObjectType.CANDIDATE_SET
    )
    journal_view_output = next(
        reference
        for reference in journal_signal_stage.output_references
        if reference.object_type is LifecycleObjectType.CANDIDATE_FEATURE_VIEW
    )
    assert journal_candidate_input == journal_candidate_output
    assert bundle.artifact.content_hash in signal_receipt.input_hashes
    assert dataset.artifact.content_hash in signal_receipt.input_hashes
    assert calendar.content_hash in signal_receipt.input_hashes
    assert journal_candidate_input.content_hash in signal_receipt.input_hashes
    assert journal_view_output.content_hash in signal_receipt.output_hashes
    assert {
        signal_configuration.configuration_hash,
        mapping.configuration_hash,
        bundle.artifact.feature_set.content_hash,
        requirement_policy.policy_hash,
        freshness_policy.policy_hash,
    }.issubset(signal_receipt.configuration_hashes)
    signal_packages = tuple(sorted((output_root / "signals").iterdir()))

    repeated = runner.run(command)
    assert repeated.run.run_id == first.run.run_id
    assert repeated.attempted_stages == ()
    assert tuple(sorted((output_root / "signals").iterdir())) == signal_packages

    durable_replay = run_durable_lifecycle_replay(
        repository=repository,
        source_run_id=first.run.run_id,
        idempotency_key="feature-signal-durable-replay",
        clock=_TickingClock(first.run.updated_at + timedelta(seconds=1)),
        output_directory=tmp_path / "durable-replay",
    )
    assert durable_replay.report.status is LifecycleReplayStatus.STABLE
    assert any(item.detail == "FEATURE_BUNDLE_PURE_RECOMPUTATION_STABLE" for item in durable_replay.report.checks)
    assert any(item.detail == "SIGNAL_V3_FULL_FEATURE_FRESHNESS_RECOMPUTATION_STABLE" for item in durable_replay.report.checks)


def _universe_of_size_100(candidate_symbols: tuple[str, ...]) -> tuple[str, ...]:
    values = set(candidate_symbols)
    code = 600000
    while len(values) < 100:
        values.add(f"{code:06d}.SH")
        code += 1
    return tuple(sorted(values))


def _trading_calendar(dataset):
    market_dates = tuple(sorted({item.market_date for item in dataset.bars}))
    local_zone = timezone(timedelta(hours=8))
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId(str(dataset.artifact.dataset_id)),
        market="A_SHARE",
        calendar_version="lifecycle-signal-freshness-test-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                trade_date=market_date,
                session_close=datetime.combine(market_date, time(15), tzinfo=local_zone),
            )
            for market_date in market_dates
        ),
    )


def _materialize_bundle(
    *,
    tmp_path: Path,
    symbols: tuple[str, ...],
    decision_time: datetime,
    source_manifest_reference: tuple[ArtifactId, str],
):
    created_at = decision_time + timedelta(minutes=5)
    daily_bars = tuple(
        bar
        for symbol_index, symbol in enumerate(symbols)
        for bar in _bars(
            symbol=symbol,
            symbol_index=symbol_index,
            decision_time=decision_time,
        )
        if bar.timeframe is Timeframe.DAILY
    )
    normalized = _recorded_tencent_minutes(
        tmp_path=tmp_path,
        symbol=symbols[0],
        decision_time=decision_time,
    )
    adjustment_policy = PriceAdjustmentPolicy.create(
        policy_version="1.0.0",
        mode=AdjustmentMode.RAW,
        factors=(),
        limitations=(),
    )
    daily_dataset = MarketDataDatasetArtifact.create(
        decision_time=decision_time,
        created_at=created_at,
        bars=daily_bars,
        expected_symbols=symbols,
        expected_timeframes=(Timeframe.DAILY,),
        adjustment_policy=adjustment_policy,
        source_manifest_references=(source_manifest_reference,),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )
    minute_dataset = MarketDataDatasetArtifact.create(
        decision_time=decision_time,
        created_at=created_at,
        bars=(*normalized.one_minute_bars, *normalized.five_minute_bars),
        expected_symbols=symbols,
        expected_timeframes=(Timeframe.MINUTE_1, Timeframe.MINUTE_5),
        adjustment_policy=adjustment_policy,
        source_manifest_references=(
            (
                normalized.source_manifest.source_manifest_id,
                normalized.source_manifest.content_hash,
            ),
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("RECORDED_TENCENT_PROVIDER_FIXTURE",),
    )
    dataset = build_combined_market_data_dataset(
        daily=daily_dataset,
        minute=minute_dataset,
        created_at=created_at,
    )
    dataset_package = publish_market_data_dataset(root=tmp_path / "market-data", artifact=dataset)
    verified_dataset = load_verified_market_data_dataset(dataset_package)
    feature_set = canonical_technical_feature_set(effective_from=decision_time - timedelta(days=365))
    feature_scope = tmp_path / "feature-run.postgres-scope"
    handoff = OperationalFeatureHandoffRunner(
        max_workers=2,
        repository_factory=lambda clock, lease: (
            PostgresFeatureMaterializationRunRepository(
                feature_scope,
                clock=clock or (lambda: created_at),
                lease_duration=lease,
            )
        ),
    ).materialize_universe(
        verified_dataset=verified_dataset,
        feature_set=feature_set,
        universe_symbols=symbols,
        scope_kind=UniverseFeatureScopeKind.CONTROLLED_EXPLORATORY_UNIVERSE,
        decision_time=decision_time,
        created_at=created_at,
        code_revision="lifecycle-feature-signal-test",
        output_root=tmp_path / "feature-run",
        idempotency_key="lifecycle-feature-signal-test",
        execution_mode=FeatureMaterializationExecutionMode.START_NEW,
    )
    return (
        handoff.feature_bundle,
        verified_dataset,
    )


def _recorded_tencent_minutes(
    *,
    tmp_path: Path,
    symbol: str,
    decision_time: datetime,
) -> MinuteNormalizationResult:
    local = decision_time.astimezone(timezone(timedelta(hours=8)))
    first = local - timedelta(minutes=10)
    cumulative_amount = Decimal("0")
    rows = []
    for index in range(10):
        price = Decimal("10") + Decimal(index) / Decimal("100")
        cumulative_amount += price * Decimal("100")
        rows.append(f"{(first + timedelta(minutes=index)).strftime('%H%M')} {price} {index + 1} {cumulative_amount}")
    code = f"{symbol[-2:].lower()}{symbol[:6]}"
    raw = json.dumps(
        {
            "code": 0,
            "data": {
                code: {
                    "data": {
                        "date": local.strftime("%Y%m%d"),
                        "data": rows,
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    request = MinuteSourceRequest(
        symbols=(symbol,),
        timeframe=Timeframe.MINUTE_1,
        decision_time=decision_time,
    )
    artifact = RawMinuteSourceArtifact.from_response(
        MinuteSourceResponse(
            request=request,
            request_started_at=decision_time - timedelta(seconds=30),
            response_received_at=decision_time,
            http_status=200,
            content_type="application/json",
            raw_payload=raw,
            provider_timestamp=local.strftime("%Y%m%d"),
            limitations=(
                "PUBLIC_TENCENT_EXPLORATORY_ONLY",
                "RECORDED_PROVIDER_FIXTURE_NO_NETWORK",
            ),
        )
    )
    package = publish_raw_minute_source(tmp_path / "minute-source", artifact)
    verified = RawMinuteSourceReader().read(package)
    return normalize_tencent_minute_source(
        artifact=verified,
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )


def _bars(*, symbol: str, symbol_index: int, decision_time: datetime) -> tuple[CanonicalMarketBar, ...]:
    exchange = Exchange.SH if symbol.endswith(".SH") else Exchange.SZ
    daily = []
    first_date = decision_time.date() - timedelta(days=70)
    for index in range(70):
        market_date = first_date + timedelta(days=index)
        close = Decimal("10") + Decimal(symbol_index) + Decimal(index) / Decimal("100")
        event_end = datetime.combine(market_date, datetime.min.time(), tzinfo=UTC) + timedelta(hours=6)
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
                source_artifact_id=ArtifactId(f"lifecycle-daily-source-{symbol_index}-{index}"),
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
                source_artifact_id=ArtifactId(f"lifecycle-minute-source-{symbol_index}-{index}"),
                source_content_hash=SOURCE_HASH,
            )
        )
    return (*daily, *minute)
