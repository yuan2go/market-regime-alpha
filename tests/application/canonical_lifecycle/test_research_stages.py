from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleAttempt,
    LifecycleAttemptId,
    LifecycleAttemptResult,
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRetryState,
    LifecycleRun,
    LifecycleRunId,
    LifecycleStage,
    configuration_manifest_hash,
    model_version_manifest_hash,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    VerifiedCompositeEvidenceStageHandler,
    ordered_references,
)
from market_regime_alpha.application.canonical_lifecycle.stages.research import (
    PlatformResearchStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    publish_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalManifestBuilder,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    publish_supplemental_research_evidence,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting import (
    PATH_FORECAST_CONFIG_SCHEMA,
    PathForecastConfig,
    PathForecastStatus,
    load_verified_path_forecast,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
    default_research_pipeline_config,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)
from market_regime_alpha.signals import (
    SIGNAL_MODEL_CONFIG_SCHEMA,
    SignalFamily,
    SignalModelConfig,
    SignalState,
    load_verified_signal_run,
)
from market_regime_alpha.strategies.entry import (
    EntryBarrierSpec,
    build_entry_path_target_contract,
)
from market_regime_alpha.daily_decision.artifact import (
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from tests.application.operational_research.test_bridge import (
    _daily_bundle,
    _supplemental,
)
from tests.application.operational_research.test_composite_manifest_builder import (
    _policy,
)
from tests.daily_decision.conftest import daily_decision_fixture


UTC = timezone.utc


@dataclass(frozen=True)
class StageFixture:
    initial_references: tuple[LifecycleObjectReference, ...]
    research_configuration: ResearchPipelineConfig
    signal_configuration: SignalModelConfig
    forecast_configuration: PathForecastConfig
    configuration_references: tuple[LifecycleConfigurationReference, ...]
    model_references: tuple[LifecycleModelVersionReference, ...]
    decision_date: date
    as_of_time: datetime


def _signal_configuration() -> SignalModelConfig:
    return SignalModelConfig(
        profile_id="canonical-lifecycle-signal-v1",
        model_id=ModelId("signal-five-confirmation-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-1455-v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        signal_family=SignalFamily.TREND_CONTINUATION,
        price_action_min_return=0.01,
        volume_confirmation_min_ratio=1.2,
        trend_confirmation_min_return=0.02,
        vwap_min_relative_return=0.0,
        overheat_max_return=0.08,
        minimum_confirmations=3,
        scoring_method="EQUAL_CONFIRMATION_MEAN_V1",
        schema_version=SIGNAL_MODEL_CONFIG_SCHEMA,
    )


def _forecast_configuration() -> PathForecastConfig:
    return PathForecastConfig(
        profile_id="canonical-lifecycle-path-v1",
        model_id=ModelId("empirical-path-forecast-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a-share-1455-v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        target_contract=build_entry_path_target_contract(
            EntryBarrierSpec(
                upper_return=0.03,
                lower_return=-0.02,
                horizon_sessions=5,
                price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
            )
        ),
        horizon_label="5_TRADING_SESSIONS",
        return_quantile_levels=(0.25, 0.5, 0.75),
        minimum_usable_samples=2,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def _model_reference(model_id: ModelId, model_version: str) -> LifecycleModelVersionReference:
    return LifecycleModelVersionReference(
        model_id=model_id,
        model_version=model_version,
        content_hash=canonical_hash({"model_id": str(model_id), "model_version": model_version}),
    )


def _configuration_reference(configuration: object, version: str) -> LifecycleConfigurationReference:
    configuration_id = getattr(configuration, "configuration_id")
    configuration_hash = getattr(configuration, "configuration_hash")
    assert isinstance(configuration_id, ArtifactId)
    assert isinstance(configuration_hash, str)
    return LifecycleConfigurationReference(
        configuration_id=configuration_id,
        configuration_version=version,
        content_hash=configuration_hash,
    )


def _stage_fixture(tmp_path: Path, *, ranked_percentiles: bool = False) -> StageFixture:
    fixture = daily_decision_fixture.__wrapped__()
    if ranked_percentiles:
        fixture = replace(
            fixture,
            prediction_runs=tuple(
                replace(
                    run,
                    predictions=tuple(
                        replace(
                            prediction,
                            percentile=(1.0 if run.population_size == 1 else 1.0 - (prediction.rank - 1) / (run.population_size - 1)),
                        )
                        for prediction in run.predictions
                    ),
                )
                for run in fixture.prediction_runs
            ),
        )
    daily_path = publish_phase_d_daily_decision_artifact(root=tmp_path / "daily", bundle=_daily_bundle(fixture))
    supplemental_bundle = _supplemental(fixture)
    supplemental_path = publish_supplemental_research_evidence(root=tmp_path / "supplemental", bundle=supplemental_bundle)
    daily = load_verified_daily_decision_artifact(daily_path)
    from market_regime_alpha.application.operational_research.supplemental_artifact import (
        load_verified_supplemental_research_evidence,
    )

    supplemental = load_verified_supplemental_research_evidence(supplemental_path)
    composite = CompositeOperationalManifestBuilder().build(
        daily=daily,
        supplemental=supplemental,
        composition_policy=_policy(),
        created_at=daily.bundle.source_manifest.decision_time.value + timedelta(minutes=10),
    )
    composite_path = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=composite,
        composition_policy=_policy(),
    )
    available_at = daily.bundle.source_manifest.decision_time.value.astimezone(UTC)
    initial = ordered_references(
        (
            LifecycleObjectReference(
                object_type=LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST,
                object_id=LifecycleObjectId(str(composite.manifest_id)),
                content_hash=composite.content_hash,
                reader_kind=LifecycleReaderKind.COMPOSITE_OPERATIONAL_ARTIFACT_READER,
                locator=str(composite_path),
                available_at=available_at,
            ),
            LifecycleObjectReference(
                object_type=LifecycleObjectType.DAILY_DECISION_ARTIFACT,
                object_id=LifecycleObjectId(daily.artifact_id),
                content_hash=daily.bundle.content_hash,
                reader_kind=LifecycleReaderKind.DAILY_DECISION_ARTIFACT_READER,
                locator=str(daily_path),
                available_at=available_at,
            ),
            LifecycleObjectReference(
                object_type=LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE,
                object_id=LifecycleObjectId(str(supplemental.bundle.bundle_id)),
                content_hash=supplemental.bundle.content_hash,
                reader_kind=LifecycleReaderKind.SUPPLEMENTAL_RESEARCH_EVIDENCE_READER,
                locator=str(supplemental_path),
                available_at=available_at,
            ),
            LifecycleObjectReference(
                object_type=LifecycleObjectType.SOURCE_MANIFEST,
                object_id=LifecycleObjectId(str(daily.bundle.source_manifest.source_manifest_id)),
                content_hash=daily.bundle.source_manifest.content_hash,
                reader_kind=LifecycleReaderKind.SOURCE_MANIFEST_READER,
                locator=str(daily_path / "source_manifest.json"),
                available_at=available_at,
            ),
            LifecycleObjectReference(
                object_type=LifecycleObjectType.SOURCE_MANIFEST,
                object_id=LifecycleObjectId(str(supplemental.bundle.source_manifest.source_manifest_id)),
                content_hash=supplemental.bundle.source_manifest.content_hash,
                reader_kind=LifecycleReaderKind.SOURCE_MANIFEST_READER,
                locator=str(supplemental_path / "bundle.json"),
                available_at=available_at,
            ),
        )
    )
    research = default_research_pipeline_config()
    signal = _signal_configuration()
    forecast = _forecast_configuration()
    configuration_references = tuple(
        sorted(
            (
                _configuration_reference(research, ResearchPipelineConfig.SCHEMA_VERSION),
                _configuration_reference(signal, signal.schema_version),
                _configuration_reference(forecast, forecast.schema_version),
            ),
            key=lambda item: item.sort_key,
        )
    )
    research_models = (
        research.market_regime,
        research.theme_rotation,
        research.capital_evolution,
        research.candidate_discovery,
    )
    model_references = tuple(
        sorted(
            (
                *(_model_reference(item.model_id, item.model_version) for item in research_models),
                _model_reference(signal.model_id, signal.model_version),
                _model_reference(forecast.model_id, forecast.model_version),
            ),
            key=lambda item: item.sort_key,
        )
    )
    return StageFixture(
        initial_references=initial,
        research_configuration=research,
        signal_configuration=signal,
        forecast_configuration=forecast,
        configuration_references=configuration_references,
        model_references=model_references,
        decision_date=available_at.astimezone(daily.bundle.source_manifest.decision_time.value.tzinfo).date(),
        as_of_time=available_at,
    )


def _context(
    fixture: StageFixture,
    stage_name: LifecycleStageName,
    prior_results: tuple[StageExecutionResult, ...],
) -> LifecycleStageContext:
    index = LIFECYCLE_STAGE_ORDER.index(stage_name)
    assert len(prior_results) == index
    run = LifecycleRun(
        run_id=LifecycleRunId("lifecycle-run-research-stage-test"),
        idempotency_key="research-stage-test",
        command_hash=canonical_hash({"command": "research-stage-test"}),
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=fixture.decision_date,
        as_of_time=fixture.as_of_time,
        status=LifecycleRunStatus.RUNNING,
        current_stage=stage_name,
        input_manifest_id=ArtifactId("canonical-lifecycle-input-test"),
        input_content_hash=canonical_hash({"input": "research-stage-test"}),
        completed_stages=tuple(LIFECYCLE_STAGE_ORDER[:index]),
        configuration_references=fixture.configuration_references,
        configuration_manifest_hash=configuration_manifest_hash(fixture.configuration_references),
        model_references=fixture.model_references,
        model_version_manifest_hash=model_version_manifest_hash(fixture.model_references),
        retry_state=LifecycleRetryState.NOT_REQUIRED,
        failure_reason=None,
        blocker_reason=None,
        created_at=fixture.as_of_time,
        updated_at=fixture.as_of_time + timedelta(seconds=index + 1),
        completed_at=None,
        version=index + 1,
        claim_token=1,
    )
    prior_stages = tuple(
        LifecycleStage(
            run_id=run.run_id,
            stage_name=LIFECYCLE_STAGE_ORDER[prior_index],
            stage_status=result.stage_status,
            attempt_count=1,
            input_references=result.input_references,
            output_references=result.output_references,
            started_at=fixture.as_of_time + timedelta(seconds=prior_index + 1),
            completed_at=fixture.as_of_time + timedelta(seconds=prior_index + 2),
            failure_reason=None,
            blocker_reason=result.blocker_reason,
            version=2,
        )
        for prior_index, result in enumerate(prior_results)
    )
    stage = LifecycleStage(
        run_id=run.run_id,
        stage_name=stage_name,
        stage_status=LifecycleStageStatus.RUNNING,
        attempt_count=1,
        input_references=(),
        output_references=(),
        started_at=fixture.as_of_time + timedelta(seconds=index + 1),
        completed_at=None,
        failure_reason=None,
        blocker_reason=None,
        version=2,
    )
    attempt = LifecycleAttempt(
        attempt_id=LifecycleAttemptId(f"attempt-{stage_name.value.lower()}"),
        run_id=run.run_id,
        stage_name=stage_name,
        attempt_number=1,
        started_at=stage.started_at,
        completed_at=None,
        result=LifecycleAttemptResult.RUNNING,
        exception_type=None,
        exception_message=None,
        claim_token=1,
    )
    return LifecycleStageContext(
        run=run,
        stage=stage,
        attempt=attempt,
        prior_stages=prior_stages,
        initial_references=fixture.initial_references,
    )


def _execute_through_forecast(
    tmp_path: Path,
    *,
    ranked_percentiles: bool = False,
) -> tuple[StageFixture, tuple[StageExecutionResult, ...]]:
    fixture = _stage_fixture(tmp_path, ranked_percentiles=ranked_percentiles)
    results: list[StageExecutionResult] = []
    evidence = VerifiedCompositeEvidenceStageHandler()
    evidence_context = _context(fixture, LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE, tuple(results))
    results.append(evidence.execute(evidence_context))

    research = PlatformResearchStageHandler(
        configuration=fixture.research_configuration,
        output_root=tmp_path / "runtime" / "research",
    )
    research_context = _context(fixture, LifecycleStageName.PLATFORM_RESEARCH, tuple(results))
    results.append(research.execute(research_context))

    signal = SignalStageHandler(
        configuration=fixture.signal_configuration,
        output_root=tmp_path / "runtime" / "signal",
    )
    signal_context = _context(fixture, LifecycleStageName.SIGNAL, tuple(results))
    results.append(signal.execute(signal_context))

    forecast = PathForecastStageHandler(
        configuration=fixture.forecast_configuration,
        output_root=tmp_path / "runtime" / "forecast",
    )
    forecast_context = _context(fixture, LifecycleStageName.PATH_FORECAST, tuple(results))
    results.append(forecast.execute(forecast_context))
    return fixture, tuple(results)


def test_real_h6_research_signal_forecast_chain_is_verified_and_fail_closed(
    tmp_path: Path,
) -> None:
    _, results = _execute_through_forecast(tmp_path)

    research = load_verified_research_artifact(Path(results[1].output_references[0].locator or ""))
    signal = load_verified_signal_run(Path(results[2].output_references[0].locator or ""))
    forecasts = tuple(load_verified_path_forecast(Path(item.locator or "")) for item in results[3].output_references)

    assert not research.artifact.candidate_set.selected
    assert "CANDIDATE_POPULATION_INSUFFICIENT" in research.artifact.reason_codes
    assert not signal.artifact.snapshots
    signal_reference = results[2].output_references[0]
    assert signal_reference.content_hash == signal.artifact.envelope.content_hash
    assert signal_reference.available_at == signal.artifact.envelope.created_at.astimezone(UTC)
    assert "H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE" in results[2].reason_codes
    assert len(forecasts) == len(signal.artifact.snapshots)
    assert all(item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT for item in forecasts)
    assert "H6_PATH_FORECAST_SAMPLES_NOT_AVAILABLE" in results[3].reason_codes
    assert "PATH_FORECAST_DATA_INSUFFICIENT" in results[3].reason_codes
    assert "NO_SIGNAL_SNAPSHOTS_TO_FORECAST" in results[3].reason_codes
    assert "MINIMUM_PATH_SAMPLE_COUNT_NOT_MET" not in results[3].reason_codes


def test_selected_candidates_run_real_signal_and_forecast_as_data_insufficient(
    tmp_path: Path,
) -> None:
    _, results = _execute_through_forecast(tmp_path, ranked_percentiles=True)
    signal = load_verified_signal_run(Path(results[2].output_references[0].locator or ""))
    forecasts = tuple(load_verified_path_forecast(Path(item.locator or "")) for item in results[3].output_references)

    assert signal.artifact.snapshots
    assert all(item.signal_state is SignalState.DATA_INSUFFICIENT for item in signal.artifact.snapshots)
    assert all("H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE" in item.reason_codes for item in signal.artifact.snapshots)
    assert len(forecasts) == len(signal.artifact.snapshots)
    assert "MINIMUM_PATH_SAMPLE_COUNT_NOT_MET" in results[3].reason_codes
    assert all("MINIMUM_PATH_SAMPLE_COUNT_NOT_MET" in verified.artifact.forecast.reason_codes for verified in forecasts)
    for reference, verified in zip(results[3].output_references, forecasts, strict=True):
        assert reference.content_hash == verified.artifact.forecast.envelope.content_hash
        assert reference.available_at == verified.artifact.forecast.envelope.created_at.astimezone(UTC)
        assert verified.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT


def test_research_signal_and_forecast_recover_exact_published_outputs(
    tmp_path: Path,
) -> None:
    fixture, results = _execute_through_forecast(tmp_path)
    handlers = (
        PlatformResearchStageHandler(
            configuration=fixture.research_configuration,
            output_root=tmp_path / "runtime" / "research",
        ),
        SignalStageHandler(
            configuration=fixture.signal_configuration,
            output_root=tmp_path / "runtime" / "signal",
        ),
        PathForecastStageHandler(
            configuration=fixture.forecast_configuration,
            output_root=tmp_path / "runtime" / "forecast",
        ),
    )
    for stage_name, result_index, handler in (
        (LifecycleStageName.PLATFORM_RESEARCH, 1, handlers[0]),
        (LifecycleStageName.SIGNAL, 2, handlers[1]),
        (LifecycleStageName.PATH_FORECAST, 3, handlers[2]),
    ):
        recovered = handler.recover(_context(fixture, stage_name, results[:result_index]))
        assert recovered == results[result_index]


def test_stage_rejects_configuration_not_bound_by_command(tmp_path: Path) -> None:
    fixture = _stage_fixture(tmp_path)
    evidence = VerifiedCompositeEvidenceStageHandler().execute(_context(fixture, LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE, ()))
    changed = replace(
        fixture.research_configuration,
        candidate_discovery=replace(
            fixture.research_configuration.candidate_discovery,
            top_n=fixture.research_configuration.candidate_discovery.top_n + 1,
        ),
    )
    handler = PlatformResearchStageHandler(
        configuration=changed,
        output_root=tmp_path / "runtime" / "research",
    )

    with pytest.raises(ValueError, match="does not bind"):
        handler.execute(_context(fixture, LifecycleStageName.PLATFORM_RESEARCH, (evidence,)))


def test_evidence_stage_rejects_tampered_lifecycle_hash(tmp_path: Path) -> None:
    fixture = _stage_fixture(tmp_path)
    composite = next(item for item in fixture.initial_references if item.object_type is LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST)
    tampered = replace(composite, content_hash="sha256:" + "f" * 64)
    changed_fixture = replace(
        fixture,
        initial_references=ordered_references(tuple(tampered if item is composite else item for item in fixture.initial_references)),
    )

    with pytest.raises(ValueError, match="reference mismatch"):
        VerifiedCompositeEvidenceStageHandler().execute(
            _context(
                changed_fixture,
                LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
                (),
            )
        )


def test_evidence_stage_requires_exact_h6_source_manifest_coverage(
    tmp_path: Path,
) -> None:
    fixture = _stage_fixture(tmp_path)
    source_references = tuple(item for item in fixture.initial_references if item.object_type is LifecycleObjectType.SOURCE_MANIFEST)
    assert len(source_references) == 2
    incomplete = replace(
        fixture,
        initial_references=ordered_references(tuple(item for item in fixture.initial_references if item is not source_references[0])),
    )

    with pytest.raises(ValueError, match="exactly cover H6 bindings"):
        VerifiedCompositeEvidenceStageHandler().execute(
            _context(
                incomplete,
                LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE,
                (),
            )
        )
