"""Owner-backed Phase C fixtures; no caller payload is treated as Authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationMethod,
    CalibrationProtocol,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationPolicy,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.entry_qualification import (
    EntryResearchModel,
    EntryResearchVariant,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    FactorFamily,
    ResearchFactorExposure,
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.factor_research import (
    build_factor_research_catalog,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingMethod,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    FormalResearchProtocol,
)
from market_regime_alpha.application.research_validation.formal_protocol_components import (
    FeatureDefinitionSet,
    ThresholdComparison,
    ThresholdPolicy,
    ThresholdRule,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    EntryHoldingExitQualificationPolicy,
)
from market_regime_alpha.application.research_validation.postgres_calibration_qualification import (
    PostgresCalibrationQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_phase_c_gates import (
    PostgresPhaseCGateAuthority,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    PostgresResearchQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalOOSMetricFloor,
    FormalOOSQualificationPolicy,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    HoldingRuleKind,
    StrategyShadowPolicy,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolioPolicy,
    build_shadow_portfolio,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.pit_authority import PITArtifactReference
from market_regime_alpha.data.pit_artifact_authority import (
    PITArtifactAuthorityResolution,
)
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.data.trading_calendar import (
    TradingCalendarArtifact,
    TradingSession,
    build_trading_calendar_artifact,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features.spine import (
    FeatureDefinitionV2,
    FeatureOutputDefinition,
    FeatureValidationStatus,
    MissingnessPolicy,
    ValueType,
)
from market_regime_alpha.forecasting.path import (
    PATH_FORECAST_SAMPLE_SCHEMA,
    PathForecastSample,
)
from market_regime_alpha.market_data import Timeframe
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.durable_governance import PersistentModelRegistry
from market_regime_alpha.platform.postgres_runtime_governance import (
    PostgresModelGovernanceRepository,
)
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    ModelVersionLineage,
)
from market_regime_alpha.strategies.entry.contracts import (
    EntryPathObservationStatus,
    EntryPathReasonCode,
)
from tests.persistence.postgres.pit_fixture import (
    HASH_A,
    FixturePITArtifactAuthorityResolver,
    MutableClock,
    fixture_provider_policy,
)
from tests.platform.test_platform_kernel import _model_definition


NOW = datetime(2026, 8, 1, 8, tzinfo=UTC)


class StablePhaseCPITResolver(FixturePITArtifactAuthorityResolver):
    """Keep owner-resolution identity stable across Phase C fixture writers."""

    def resolve(
        self,
        reference: PITArtifactReference,
        *,
        resolved_at: datetime,
    ) -> PITArtifactAuthorityResolution:
        return super().resolve(reference, resolved_at=NOW)


@dataclass(frozen=True, slots=True)
class PhaseCOwnerFixture:
    protocol: FormalResearchProtocol
    targets: OutcomeTargetProtocol
    calendar: TradingCalendarArtifact
    evaluation: FormalEvaluationProtocol
    model_lineage: ModelVersionLineage
    calibration_policy: CalibrationQualificationPolicy
    entry_policy: EntryHoldingExitQualificationPolicy


def record_phase_c_protocol_owners(
    factory: PostgresConnectionFactory,
) -> PhaseCOwnerFixture:
    targets = engineering_multi_horizon_protocol()
    PostgresTargetOutcomeRepository(factory).register_protocol(targets)
    target = targets.targets[0]
    definition = replace(
        _model_definition(),
        target_id=TargetId(str(target.target_id)),
        universe_id=UniverseId("universe-a"),
        feature_ids=(FeatureDefinitionId("feature-a"),),
    )
    target_reference = ValidationArtifactReference(
        "OUTCOME_TARGET", target.target_id, target.target_hash
    )

    calendar = _calendar()
    evaluation = _evaluation(targets)
    validation = PostgresResearchValidationRepository(factory)
    validation.record_formal_evaluation_protocol(evaluation)

    universe_reference = ValidationArtifactReference(
        "UNIVERSE", ArtifactId(str(definition.universe_id)), HASH_A
    )
    dataset_reference = ValidationArtifactReference(
        "MARKET_DATA_DATASET", ArtifactId("dataset-a"), HASH_A
    )
    pit = PostgresPITAuthority(
        factory,
        clock=MutableClock(NOW),
        artifact_resolver=StablePhaseCPITResolver(),
        provider_policy=fixture_provider_policy(),
    )
    calendar_reference = ValidationArtifactReference(
        "TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash
    )
    for reference in (calendar_reference, universe_reference, dataset_reference):
        pit.resolve_artifact(
            PITArtifactReference(
                reference.artifact_kind,
                reference.artifact_id,
                reference.content_hash,
            ),
            actor="phase-c-owner-test",
            reason="resolve immutable fixture owner",
            idempotency_key=f"resolve-{reference.artifact_kind.lower()}",
        )
    PostgresPITTradingCalendarSnapshotRepository(factory).record(calendar)

    historical = _historical_dataset(target_reference)
    validation.record_sample_dataset(historical)
    feature_set = FeatureDefinitionSet.create(
        definition_set_version="phase-c-owner-v1",
        definitions=(_feature_definition(str(definition.feature_ids[0])),),
        locked_at=NOW,
    )
    validation.record_feature_definition_set(feature_set)
    enrichment = _factor_enrichment(feature_set.definitions[0])
    validation.record_panel_enrichment(enrichment)
    factor_catalog = build_factor_research_catalog(
        enrichment=enrichment, created_at=NOW
    )
    validation.record_factor_catalog(factor_catalog)

    governance = PostgresModelGovernanceRepository(factory)
    PersistentModelRegistry(governance).register(
        definition, idempotency_key="phase-c-owner-model-register"
    )
    model_lineage = governance.record_version_lineage(
        ModelVersionLineage.create(
            model_id=definition.model_id,
            model_version=definition.version,
            definition_hash=definition.definition_hash,
            target_id=definition.target_id,
            universe_contract_id=definition.universe_id,
            feature_definition_ids=definition.feature_ids,
            model_parameter_hash=definition.parameter_hash,
            configuration=ArtifactLineageReference(
                reference_kind="MODEL_CONFIGURATION",
                artifact_id=ArtifactId("configuration-a"),
                content_hash=HASH_A,
            ),
            implementation_ref=definition.implementation_ref,
            code_revision="80bd8e85daf6115bbf147fcd3bfbe60ce781e02c",
            code_hash=canonical_hash(
                {"code_revision": "phase-c-owner-model-code-v1"}
            ),
            validation_protocol_refs=(
                ArtifactLineageReference(
                    reference_kind="VALIDATION_PROTOCOL",
                    artifact_id=evaluation.protocol_id,
                    content_hash=evaluation.protocol_hash,
                ),
            ),
            supported_data_eligibilities=definition.supported_data_eligibilities,
            created_at=NOW,
        ),
        actor="phase-c-owner-test",
        reason="freeze exact model lineage",
        idempotency_key="phase-c-owner-model-lineage",
    )
    pit.resolve_artifact(
        PITArtifactReference(
            "CONFIGURATION",
            model_lineage.configuration.artifact_id,
            model_lineage.configuration.content_hash,
        ),
        actor="phase-c-owner-test",
        reason="resolve exact Model Configuration owner",
        idempotency_key="resolve-model-configuration",
    )
    threshold = ThresholdPolicy.create(
        policy_version="phase-c-owner-v1",
        rules=(
            ThresholdRule(
                "candidate_score",
                ThresholdComparison.GREATER_THAN_OR_EQUAL,
                Decimal("0.6"),
            ),
        ),
        locked_at=NOW,
    )
    validation.record_threshold_policy(threshold)
    oos_policy = FormalOOSQualificationPolicy.create(
        policy_version="phase-c-owner-v1",
        metric_floors=(FormalOOSMetricFloor("SPREAD", Decimal("0.001"), None),),
        minimum_sample_count=20,
        maximum_adjusted_p_value=Decimal("0.05"),
        require_confidence_interval_excludes_zero=True,
        required_sensitivity_multipliers=(Decimal("0.9"), Decimal("1")),
        locked_at=NOW,
    )
    PostgresResearchQualificationAuthority(factory).record_oos_policy(oos_policy)

    calibration_protocol = CalibrationProtocol.create(
        protocol_version="phase-c-owner-v1",
        method=CalibrationMethod.PLATT_LOGISTIC,
        minimum_fit_samples=2,
    )
    validation.record_calibration_protocol(calibration_protocol, recorded_at=NOW)
    calibration_policy = CalibrationQualificationPolicy.create(
        policy_version="phase-c-owner-v1",
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL", targets.protocol_id, targets.protocol_hash
        ),
        target_reference=target_reference,
        barrier_id=target.barriers[0].barrier_id,
        calibration_protocol_reference=ValidationArtifactReference(
            "CALIBRATION_PROTOCOL",
            calibration_protocol.protocol_id,
            calibration_protocol.protocol_hash,
        ),
        minimum_oos_samples=2,
        maximum_brier=Decimal("0.25"),
        maximum_log_loss=Decimal("0.70"),
        maximum_ece=Decimal("0.10"),
        minimum_coverage=Decimal("0.90"),
        locked_at=NOW,
    )
    PostgresCalibrationQualificationAuthority(factory).record_policy(
        calibration_policy
    )

    strategy_policy = StrategyShadowPolicy.create(
        policy_version="phase-c-owner-v1",
        rule_kinds=(HoldingRuleKind.FIXED_TIME,),
        fixed_horizon_sessions=1,
        trailing_drawdown=None,
        protection_return=None,
        participation_rate=Decimal("0.1"),
    )
    PostgresStrategyShadowRepository(factory).save_policy(
        strategy_policy, created_at=NOW
    )
    portfolio_policy = _portfolio_policy()
    portfolio = build_shadow_portfolio(
        policy=portfolio_policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "phase-c-owner-panel"),
        candidate_reference=_reference("CANDIDATE_SET", "phase-c-owner-candidates"),
        initial_cash=Decimal("100000"),
        created_at=NOW,
    )
    PostgresShadowPortfolioRepository(factory).save_portfolio(
        policy=portfolio_policy, portfolio=portfolio
    )
    entry_model = EntryResearchModel.create(
        model_version="phase-c-owner-v1",
        variant=EntryResearchVariant.CANDIDATE_FORECAST,
        score_threshold=Decimal("0.6"),
    )
    validation.record(
        artifact_id=ArtifactId(str(entry_model.model_id)),
        artifact_hash=entry_model.model_hash,
        artifact_kind="ENTRY_RESEARCH_MODEL",
        evidence_authority="ENGINEERING_ONLY",
        payload=entry_model.identity_payload(),
        created_at=NOW,
    )
    entry_policy = EntryHoldingExitQualificationPolicy.create(
        policy_version="phase-c-owner-v1",
        entry_model_reference=ValidationArtifactReference(
            "ENTRY_RESEARCH_MODEL",
            ArtifactId(str(entry_model.model_id)),
            entry_model.model_hash,
        ),
        strategy_policy_reference=ValidationArtifactReference(
            "STRATEGY_SHADOW_POLICY",
            strategy_policy.policy_id,
            strategy_policy.policy_hash,
        ),
        portfolio_policy_reference=ValidationArtifactReference(
            "SHADOW_PORTFOLIO_POLICY",
            portfolio_policy.policy_id,
            portfolio_policy.policy_hash,
        ),
        minimum_samples=20,
        minimum_hit_rate=Decimal("0.55"),
        minimum_cost_adjusted_return=Decimal("0.001"),
        maximum_mean_mae=Decimal("-0.05"),
        required_exit_rule_coverage=(HoldingRuleKind.FIXED_TIME,),
        allowed_result_provenance=(
            ShadowParameterProvenance.CALIBRATED_PARAMETER,
            ShadowParameterProvenance.OBSERVED_FACT,
        ),
        locked_at=NOW,
    )
    PostgresPhaseCGateAuthority(factory).record_entry_holding_exit_policy(
        entry_policy
    )

    with factory.connection(read_only=True) as connection:
        protocol_locked_at = connection.execute(
            "SELECT date_trunc('second', clock_timestamp())"
        ).fetchone()[0]
    protocol = FormalResearchProtocol.create(
        protocol_version="phase-c-owner-v1",
        target_protocol=targets,
        trading_calendar=calendar,
        evaluation_protocol=evaluation,
        universe_reference=universe_reference,
        dataset_reference=dataset_reference,
        historical_sample_dataset_reference=ValidationArtifactReference(
            "HISTORICAL_SAMPLE_DATASET", historical.dataset_id, historical.dataset_hash
        ),
        feature_reference=ValidationArtifactReference(
            "FEATURE_DEFINITION_SET",
            feature_set.definition_set_id,
            feature_set.definition_set_hash,
        ),
        factor_reference=ValidationArtifactReference(
            "FACTOR_CATALOG", factor_catalog.catalog_id, factor_catalog.catalog_hash
        ),
        model_reference=ValidationArtifactReference(
            "MODEL_VERSION_LINEAGE",
            model_lineage.lineage_id,
            model_lineage.lineage_hash,
        ),
        threshold_policy_reference=ValidationArtifactReference(
            "THRESHOLD_POLICY", threshold.policy_id, threshold.policy_hash
        ),
        formal_oos_qualification_policy_reference=ValidationArtifactReference(
            "FORMAL_OOS_QUALIFICATION_POLICY",
            oos_policy.policy_id,
            oos_policy.policy_hash,
        ),
        cost_policy_reference=entry_policy.portfolio_policy_reference,
        calibration_policy_reference=ValidationArtifactReference(
            "CALIBRATION_POLICY",
            calibration_policy.policy_id,
            calibration_policy.policy_hash,
        ),
        strategy_policy_reference=entry_policy.strategy_policy_reference,
        entry_holding_exit_qualification_policy_reference=ValidationArtifactReference(
            "ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY",
            entry_policy.policy_id,
            entry_policy.policy_hash,
        ),
        locked_at=protocol_locked_at,
    )
    return PhaseCOwnerFixture(
        protocol,
        targets,
        calendar,
        evaluation,
        model_lineage,
        calibration_policy,
        entry_policy,
    )


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def _calendar() -> TradingCalendarArtifact:
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("phase-c-owner-calendar-source"),
        market="XSHG-XSHE",
        calendar_version="phase-c-owner-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(
                date(2026, 1, day),
                datetime(2026, 1, day, 7, tzinfo=UTC),
            )
            for day in range(5, 31)
        ),
    )


def _evaluation(targets: OutcomeTargetProtocol) -> FormalEvaluationProtocol:
    return FormalEvaluationProtocol.create(
        protocol_version="phase-c-owner-v1",
        target_protocol=targets,
        windows=(
            EvaluationWindow(
                "train", EvaluationPartition.TRAIN, date(2026, 1, 5), date(2026, 1, 12), 1
            ),
            EvaluationWindow(
                "validation",
                EvaluationPartition.VALIDATION,
                date(2026, 1, 13),
                date(2026, 1, 20),
                1,
            ),
            EvaluationWindow(
                "locked-oos",
                EvaluationPartition.LOCKED_OOS,
                date(2026, 1, 21),
                date(2026, 1, 30),
                1,
            ),
        ),
        bootstrap_iterations=100,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        locked_at=NOW,
    )


def _historical_dataset(
    target_reference: ValidationArtifactReference,
) -> HistoricalSampleDataset:
    sample = PathForecastSample(
        sample_id=ArtifactId("phase-c-owner-sample"),
        source_artifact_id=ArtifactId("phase-c-owner-outcome"),
        source_content_hash=canonical_hash({"outcome": "phase-c-owner"}),
        symbol="000001.SZ",
        target_id=TargetId(str(target_reference.artifact_id)),
        sample_decision_time=DecisionTime(NOW - timedelta(days=5)),
        available_at=AvailabilityTime(NOW - timedelta(days=1)),
        observation_status=EntryPathObservationStatus.AVAILABLE,
        observation_reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
        realized_mfe=0.04,
        realized_mae=-0.02,
        realized_return=0.01,
        schema_version=PATH_FORECAST_SAMPLE_SCHEMA,
    )
    record = HistoricalPathSampleRecord.register_unqualified(
        sample=sample,
        target_reference=target_reference,
        outcome_reference=_reference("FACTUAL_OUTCOME", "phase-c-owner-outcome"),
        pit_lineage=(),
        registered_at=NOW - timedelta(days=1),
    )
    return HistoricalSampleDataset.create(
        registry_version="phase-c-owner-v1",
        target_reference=target_reference,
        records=(record,),
        available_at=NOW - timedelta(days=1),
    )


def _feature_definition(feature_id: str) -> FeatureDefinitionV2:
    return FeatureDefinitionV2.create(
        feature_id=feature_id,
        feature_version="1.0.0",
        model_id=ModelId("phase-c-owner-feature-model"),
        model_version="1.0.0",
        required_fields=("close",),
        supported_timeframes=(Timeframe.DAILY,),
        minimum_history=2,
        warmup_policy="STRICT_TRAILING_WINDOW",
        missingness_policy=MissingnessPolicy.EXPLICIT_NO_IMPUTATION,
        output_schema=(FeatureOutputDefinition("value", ValueType.DECIMAL),),
        validation_status=FeatureValidationStatus.MODEL_ASSUMPTION,
        limitations=("RESEARCH_ONLY",),
    )


def _factor_enrichment(
    definition: FeatureDefinitionV2,
) -> ResearchPanelEnrichment:
    source = ValidationArtifactReference(
        "FEATURE_DEFINITION_V2",
        ArtifactId(str(definition.definition_id)),
        definition.definition_hash,
    )
    exposure = ResearchFactorExposure(
        symbol="000001.SZ",
        family=FactorFamily.PRICE,
        factor_id=definition.feature_id,
        timeframe="DAILY",
        raw_numeric=Decimal("1"),
        raw_text=None,
        normalized_exposure=None,
        model_contribution=None,
        gate_result=None,
        missingness=(),
        available_at=NOW,
        source_reference=source,
        source_value_path="values.value",
    )
    return ResearchPanelEnrichment.create(
        panel_reference=_reference("RESEARCH_PANEL_V2", "phase-c-owner-panel"),
        exposures=(exposure,),
        extracted_at=NOW,
    )


def _portfolio_policy() -> ShadowPortfolioPolicy:
    return ShadowPortfolioPolicy.create(
        policy_version="phase-c-owner-v1",
        top_k=1,
        weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
        lot_size=100,
        t_plus_one=True,
        parameters={
            name: (Decimal(value), ShadowParameterProvenance.ENGINEERING_ASSUMPTION)
            for name, value in {
                "commission_bps": "2",
                "slippage_bps": "5",
                "impact_bps": "3",
                "exit_cost_bps": "2",
                "max_participation_rate": "0.1",
            }.items()
        },
        created_at=NOW,
    )


__all__ = ["NOW", "PhaseCOwnerFixture", "record_phase_c_protocol_owners"]
