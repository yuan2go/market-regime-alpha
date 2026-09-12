"""Sole target composition root and explicit schema-operator boundary."""

from __future__ import annotations

from market_regime_alpha.infrastructure.postgres.queries.historical_acquisition import PostgresHistoricalAcquisitionSources
from market_regime_alpha.infrastructure.postgres.queries.daily_feature_inputs import PostgresDailyFeatureInputReadPort
from market_regime_alpha.infrastructure.postgres.queries.daily_predictions import PostgresDailyPredictionReads
from market_regime_alpha.infrastructure.postgres.queries.calendar_continuity import PostgresCalendarContinuityReads
from market_regime_alpha.interfaces.daily_research import DailyResearchOperations
from market_regime_alpha.infrastructure.postgres.prospective_operation_session import (
    prospective_series_admission,
)

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from market_regime_alpha.infrastructure.postgres.queries.prospective_continuity import PostgresProspectiveContinuityReadPort
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.artifacts.evidence import FilesystemEvidenceIntegrity
from market_regime_alpha.infrastructure.postgres.evidence_backup import PostgresEvidenceBackup
from market_regime_alpha.infrastructure.postgres.queries.evidence import PostgresEvidenceSnapshotPort
from market_regime_alpha.runtime.application.evidence import EvidenceApplication
from market_regime_alpha.infrastructure.models.research_baselines import ResearchBaselineTrainer, ResearchBaselinePredictor, ResearchBaselineBacktestAdapter
from market_regime_alpha.infrastructure.models import (
    DeterministicRidgeBacktestModelAdapter,
    DeterministicRidgePredictor,
    DeterministicRidgeTrainer,
    ExplicitModelPredictorComposition,
    ExplicitModelTrainerComposition,
)
from market_regime_alpha.infrastructure.backtest_features import (
    DailyMoveBacktestFeatureAdapter,
    IntradayMoveBacktestFeatureAdapter,
)
from market_regime_alpha.infrastructure.archive_resources import (
    FilesystemArchiveResourceInspector,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.archive_uow import (
    PostgresArchiveUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.candidate_uow import (
    PostgresCandidateUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.decision_uow import (
    PostgresDecisionSupportUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.context_uow import PostgresContextUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.inference_uow import PostgresInferenceUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.opportunity_uow import PostgresOpportunityUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.portfolio_uow import PostgresPortfolioUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.risk_uow import PostgresRiskUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.strategy_uow import PostgresStrategyUnitOfWorkProvider
from market_regime_alpha.infrastructure.postgres.outcome_uow import (
    PostgresOutcomeUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.partition_uow import (
    PostgresPartitionUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.experiment_uow import (
    PostgresExperimentUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.exploratory_backtest_uow import (
    PostgresExploratoryBacktestUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.backtest_uow import (
    PostgresBacktestUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.research_model_uow import (
    PostgresResearchModelUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.evaluation_uow import (
    PostgresEvaluationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.evidence_uow import (
    PostgresEvidenceUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.assessment_uow import (
    PostgresAssessmentUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.qualification_uow import (
    PostgresQualificationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.provider_qualification_uow import (
    PostgresProviderQualificationUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.formal_campaign_uow import (
    PostgresFormalCampaignUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.selection_uow import (
    PostgresSelectionUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.research_uow import (
    PostgresResearchUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.target_uow import (
    PostgresTargetUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.archive_acquisition_readiness import PostgresArchiveAcquisitionReadinessReads
from market_regime_alpha.infrastructure.postgres.queries import (
    PostgresCandidateQueryProvider,
    PostgresArchiveOperationsReadPort,
    PostgresArchiveInspectionPort,
    PostgresArchiveVerificationPort,
    PostgresArchiveTradingSessionReadPort,
    PostgresTargetArchiveScheduleReadPort,
    PostgresCandidateResearchInputLoader,
    PostgresDecisionInputPreparationProvider,
    PostgresDecisionRunQueryProvider,
    PostgresMarketQueryProvider,
    PostgresMarketRevisionLineageReadPort,
    PostgresOutcomeInputPreparationProvider,
    PostgresOutcomeQueryProvider,
    PostgresOutcomeVerificationProvider,
    PostgresResearchEvaluationVerificationProvider,
    PostgresResearchQualificationAdmissionReadPort,
    PostgresResearchQualificationVerificationProvider,
    PostgresExploratoryFeatureInputReadPort,
    PostgresExploratoryCampaignReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_context_inputs import (
    PostgresContextInputPreparationProvider,
    PostgresContextQueryProvider,
)
from market_regime_alpha.market.ports import (
    ArchiveInspectionPort,
    ArchiveVerificationPort,
    ArchiveTradingSessionReadPort,
    MarketRevisionLineageReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import (
    PostgresInferenceInputPreparationProvider,
    PostgresInferenceQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.model_forecast_inputs import (
    PostgresModelForecastInputPreparationProvider,
    PostgresModelForecastQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_opportunity_inputs import (
    PostgresOpportunityInputPreparationProvider,
    PostgresOpportunityQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_portfolio_inputs import (
    PostgresPortfolioInputPreparationProvider,
    PostgresPortfolioQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_risk_inputs import (
    PostgresRiskInputPreparationProvider,
    PostgresRiskQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_strategy import PostgresStrategyQueryProvider
from market_regime_alpha.infrastructure.postgres.queries.decision_verification import PostgresDecisionRunVerificationProvider
from market_regime_alpha.infrastructure.postgres.queries.formal_pit import (
    PostgresFormalPitSourceReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.formal_campaigns import (
    PostgresFormalCampaignQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.provider_qualification import (
    PostgresProviderQualificationQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.exploratory_backtests import (
    PostgresExploratoryBacktestVerificationPort,
)
from market_regime_alpha.infrastructure.postgres.queries.model_training_inputs import (
    PostgresModelTrainingInputProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_actions import (
    PostgresBacktestActionReadPort,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_execution import (
    PostgresBacktestExecutionObservationPort,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_history import (
    PostgresBacktestAuthorityQueryPort,
)
from market_regime_alpha.infrastructure.postgres.queries.backtest_reports import (
    PostgresBacktestReportSourcePort,
)
from market_regime_alpha.infrastructure.postgres.operational_diagnostics import PostgresOperationalDiagnostics
from market_regime_alpha.infrastructure.postgres.queries.backtest_diagnostics import PostgresBacktestDiagnosticsSourcePort
from market_regime_alpha.infrastructure.postgres.queries.prospective_health import PostgresProspectiveHealthReadPort
from market_regime_alpha.research_qualification.application.backtest_diagnostics import BacktestDiagnosticsApplication
from market_regime_alpha.infrastructure.postgres.queries.backtests import (
    PostgresBacktestQueryPort,
)
from market_regime_alpha.infrastructure.postgres.schema import (
    DatabaseIdentity,
    OperationalUpgradeAuthorization,
    OperationalUpgradePlan,
    OperationalUpgradeResult,
    RecreateAuthorization,
    RecreatePlan,
    RecreateResult,
    SchemaManager,
    SchemaVerification,
)
from market_regime_alpha.infrastructure.postgres.uow import PostgresUnitOfWorkProvider
from market_regime_alpha.runtime.application import ArtifactApplication, RuntimeApplication
from market_regime_alpha.decision_support.application import (
    ContextCommands,
    DecisionRunVerifier,
    DecisionSupportApplication,
    InferenceCommands,
    ModelForecastCommands,
    OpportunityCommands,
    PortfolioCommands,
    RiskCommands,
    StrategyCommands,
)
from market_regime_alpha.decision_support.ports import DecisionRunQueryProvider
from market_regime_alpha.outcome.application import OutcomeApplication, OutcomeVerifier
from market_regime_alpha.outcome.ports import OutcomeReadPort
from market_regime_alpha.research_qualification.application import (
    AssessmentCommands,
    EvaluationCommands,
    EvidenceCommands,
    ExperimentCommands,
    ExploratoryBacktestCommands,
    ModelCommands,
    ResearchModelApplication,
    ResearchPartitionCommands,
    FormalCampaignCommands,
    ResearchEvaluationVerifier,
    ResearchQualificationApplication,
    ResearchQualificationVerifier,
    QualificationCommands,
)
from market_regime_alpha.research_qualification.ports import (
    ExploratoryCampaignReadPort,
    ExploratoryFeatureInputReadPort,
    FormalPitSourceReadPort,
    FormalCampaignQueryPort,
    ResearchQualificationAdmissionReadPort,
)
from market_regime_alpha.research_qualification.ports.exploratory_backtest_queries import (
    ExploratoryBacktestVerificationPort,
)
from market_regime_alpha.research_qualification.application.backtest_execution import (
    BacktestExecutor,
)
from market_regime_alpha.research_qualification.application.backtest_replay import (
    BacktestReplayApplication,
)
from market_regime_alpha.research_qualification.application.backtest_reports import (
    BacktestReportApplication,
)
from market_regime_alpha.research_qualification.application.backtest_runtime import (
    BacktestRuntimeActionExecutor,
)
from market_regime_alpha.research_qualification.application.backtests import (
    BacktestApplication,
)
from market_regime_alpha.interfaces.backtest_actions import (
    BacktestCanonicalActionHandler,
)
from market_regime_alpha.selection.application import (
    CandidateApplication,
    SelectionApplication,
)
from market_regime_alpha.selection.ports import CandidateQueryProvider
from market_regime_alpha.market.application import (
    ArchiveCommands,
    MarketApplication,
    MarketArchiveOperations,
    ProspectiveArchiveRuntimeApplication,
)
from market_regime_alpha.market.application import ProviderQualificationCommands
from market_regime_alpha.market.ports import (
    MarketQueryProvider,
    ProviderQualificationQueryPort,
    TargetArchiveScheduleReadPort,
)


_ALLOWED_ENVIRONMENT_KEYS = frozenset(
    {
        "MRA_DATABASE_URL",
        "MRA_ARTIFACT_ROOT",
        "MRA_SCHEMA",
        "MRA_SCHEMA_EPOCH",
        "MRA_POOL_MIN_SIZE",
        "MRA_POOL_MAX_SIZE",
    }
)


@dataclass(frozen=True, slots=True)
class TargetSettings:
    database_url: str
    artifact_root: Path
    pool_min_size: int = 1
    pool_max_size: int = 4
    schema: str = "mra"
    schema_epoch: str = "MRA_REFOUNDATION_1"

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("MRA_DATABASE_URL is required")
        if not self.artifact_root.is_absolute():
            raise ValueError("MRA_ARTIFACT_ROOT must be an absolute path")
        if self.schema != "mra":
            raise ValueError("MRA_SCHEMA must be exactly mra")
        if self.schema_epoch != "MRA_REFOUNDATION_1":
            raise ValueError("MRA_SCHEMA_EPOCH must be exactly MRA_REFOUNDATION_1")
        if isinstance(self.pool_min_size, bool) or self.pool_min_size < 0:
            raise ValueError("MRA_POOL_MIN_SIZE must be non-negative")
        if isinstance(self.pool_max_size, bool) or self.pool_max_size < max(1, self.pool_min_size) or self.pool_max_size > 32:
            raise ValueError("MRA_POOL_MAX_SIZE must be between max(1, min size) and 32")

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> TargetSettings:
        source = os.environ if environ is None else environ
        unknown = sorted(key for key in source if key.startswith("MRA_") and key not in _ALLOWED_ENVIRONMENT_KEYS)
        if unknown:
            raise ValueError(f"unknown MRA configuration keys: {unknown}")
        database_url = source.get("MRA_DATABASE_URL", "")
        artifact_root_raw = source.get("MRA_ARTIFACT_ROOT", "")
        if not artifact_root_raw:
            raise ValueError("MRA_ARTIFACT_ROOT is required")
        try:
            pool_min_size = int(source.get("MRA_POOL_MIN_SIZE", "1"))
            pool_max_size = int(source.get("MRA_POOL_MAX_SIZE", "4"))
        except ValueError as exc:
            raise ValueError("MRA pool sizes must be integers") from exc
        return cls(
            database_url=database_url,
            artifact_root=Path(artifact_root_raw).expanduser().resolve(),
            pool_min_size=pool_min_size,
            pool_max_size=pool_max_size,
            schema=source.get("MRA_SCHEMA", "mra"),
            schema_epoch=source.get("MRA_SCHEMA_EPOCH", "MRA_REFOUNDATION_1"),
        )


@dataclass(slots=True)
class TargetApplication:
    daily_prediction_reads: PostgresDailyPredictionReads
    calendar_continuity_reads: PostgresCalendarContinuityReads
    evidence: EvidenceApplication
    operational_diagnostics: PostgresOperationalDiagnostics
    backtest_diagnostics: BacktestDiagnosticsApplication
    runtime: RuntimeApplication
    artifacts: ArtifactApplication
    market: MarketApplication
    market_archives: ArchiveCommands
    archive_operations: MarketArchiveOperations
    prospective_archives: ProspectiveArchiveRuntimeApplication
    archive_inspection: ArchiveInspectionPort
    historical_acquisition_sources: PostgresHistoricalAcquisitionSources
    archive_acquisition_readiness: PostgresArchiveAcquisitionReadinessReads
    archive_verification: ArchiveVerificationPort
    archive_trading_sessions: ArchiveTradingSessionReadPort
    archive_continuity: PostgresProspectiveContinuityReadPort
    prospective_health: PostgresProspectiveHealthReadPort
    target_archive_schedules: TargetArchiveScheduleReadPort
    provider_qualifications: ProviderQualificationCommands
    provider_qualification_queries: ProviderQualificationQueryPort
    market_queries: MarketQueryProvider
    market_revision_lineage: MarketRevisionLineageReadPort
    selection: SelectionApplication
    research_definitions: ResearchQualificationApplication
    research_partitions: ResearchPartitionCommands
    research_experiments: ExperimentCommands
    backtests: BacktestApplication
    backtest_specifications: PostgresBacktestQueryPort
    backtest_execution: BacktestExecutor
    backtest_replay: BacktestReplayApplication
    backtest_reports: BacktestReportApplication
    exploratory_backtests: ExploratoryBacktestCommands
    exploratory_backtest_verifier: ExploratoryBacktestVerificationPort
    exploratory_campaigns: ExploratoryCampaignReadPort
    exploratory_feature_inputs: ExploratoryFeatureInputReadPort
    research_models: ResearchModelApplication
    research_evaluations: EvaluationCommands
    research_evaluation_verifier: ResearchEvaluationVerifier
    research_evidence: EvidenceCommands
    research_assessments: AssessmentCommands
    research_qualifications: QualificationCommands
    formal_research_campaigns: FormalCampaignCommands
    formal_pit_sources: FormalPitSourceReadPort
    formal_research_queries: FormalCampaignQueryPort
    research_qualification_admissions: ResearchQualificationAdmissionReadPort
    research_qualification_verifier: ResearchQualificationVerifier
    candidates: CandidateApplication
    candidate_queries: CandidateQueryProvider
    decision_support: DecisionSupportApplication
    decision_runs: DecisionRunQueryProvider
    decision_contexts: ContextCommands
    decision_strategies: StrategyCommands
    decision_inference: InferenceCommands
    decision_model_forecasts: ModelForecastCommands
    decision_opportunities: OpportunityCommands
    decision_portfolios: PortfolioCommands
    decision_risk: RiskCommands
    decision_support_verifier: DecisionRunVerifier
    outcomes: OutcomeApplication
    outcome_queries: OutcomeReadPort
    outcome_verifier: OutcomeVerifier
    _pool: TargetPostgresPool

    @property
    def daily_research(self) -> DailyResearchOperations:
        return DailyResearchOperations(self, self.daily_prediction_reads)

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> TargetApplication:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def bootstrap_application(settings: TargetSettings) -> TargetApplication:
    """Verify-only startup, then compose target handlers and concrete adapters."""

    SchemaManager(settings.database_url).verify()
    pool = TargetPostgresPool(
        settings.database_url,
        min_size=settings.pool_min_size,
        max_size=settings.pool_max_size,
        application_schema=settings.schema,
    )
    uow_provider = PostgresUnitOfWorkProvider(pool)
    runtime_application = RuntimeApplication(uow_provider)
    byte_store = LocalArtifactStore(settings.artifact_root)
    artifact_application = ArtifactApplication(byte_store, uow_provider)
    market_clock = PostgresMarketDatabaseClock(pool)
    market_application = MarketApplication(
        byte_store,
        PostgresMarketUnitOfWorkProvider(pool),
        market_clock,
    )
    archive_commands = ArchiveCommands(
        PostgresArchiveUnitOfWorkProvider(pool),
        id_factory=uuid4,
    )
    archive_operations = MarketArchiveOperations(
        market_application,
        archive_commands,
        PostgresArchiveOperationsReadPort(pool),
        FilesystemArchiveResourceInspector(settings.artifact_root),
        market_clock,
        byte_store=byte_store,
    )
    selection_application = SelectionApplication(PostgresSelectionUnitOfWorkProvider(pool))
    research_definitions_application = ResearchQualificationApplication(
        byte_store,
        PostgresResearchUnitOfWorkProvider(pool),
        PostgresTargetUnitOfWorkProvider(pool),
    )
    research_partition_commands = ResearchPartitionCommands(
        PostgresPartitionUnitOfWorkProvider(pool, id_factory=uuid4),
        id_factory=uuid4,
    )
    experiment_commands = ExperimentCommands(
        PostgresExperimentUnitOfWorkProvider(pool),
        id_factory=uuid4,
    )
    evaluation_commands = EvaluationCommands(
        PostgresEvaluationUnitOfWorkProvider(pool, id_factory=uuid4),
        id_factory=uuid4,
        outcome_prices=PostgresOutcomeQueryProvider(pool),
    )
    model_trainers = ExplicitModelTrainerComposition(
        (DeterministicRidgeTrainer(), ResearchBaselineTrainer())
    )
    model_predictors = ExplicitModelPredictorComposition(
        (DeterministicRidgePredictor(), ResearchBaselinePredictor())
    )
    model_training_inputs = PostgresModelTrainingInputProvider(pool, byte_store)
    research_model_application = ResearchModelApplication(
        ModelCommands(
            PostgresResearchModelUnitOfWorkProvider(pool),
            id_factory=uuid4,
        ),
        model_training_inputs,
        artifact_application,
        model_trainers,
    )
    candidate_research_inputs = PostgresCandidateResearchInputLoader(pool, byte_store)
    candidate_application = CandidateApplication(
        candidate_research_inputs,
        PostgresCandidateUnitOfWorkProvider(pool),
    )
    decision_input_provider = PostgresDecisionInputPreparationProvider(pool)
    decision_support_application = DecisionSupportApplication(
        decision_input_provider,
        PostgresDecisionSupportUnitOfWorkProvider(pool),
        PostgresDecisionRunQueryProvider(pool),
        exploratory_preparation=decision_input_provider,
    )
    context_commands = ContextCommands(
        PostgresContextInputPreparationProvider(pool),
        PostgresContextUnitOfWorkProvider(pool),
        PostgresContextQueryProvider(pool),
    )
    inference_input_provider = PostgresInferenceInputPreparationProvider(pool)
    inference_commands = InferenceCommands(
        inference_input_provider,
        PostgresInferenceUnitOfWorkProvider(pool),
        PostgresInferenceQueryProvider(pool),
    )
    model_forecast_commands = ModelForecastCommands(
        PostgresModelForecastInputPreparationProvider(
            pool,
            byte_store,
            inference_input_provider,
            model_predictors,
        ),
        PostgresInferenceUnitOfWorkProvider(pool),
        PostgresInferenceQueryProvider(pool),
        PostgresModelForecastQueryProvider(pool),
    )
    opportunity_commands = OpportunityCommands(
        PostgresOpportunityInputPreparationProvider(pool),
        PostgresOpportunityUnitOfWorkProvider(pool),
        PostgresOpportunityQueryProvider(pool),
    )
    portfolio_commands = PortfolioCommands(
        PostgresPortfolioInputPreparationProvider(pool),
        PostgresPortfolioUnitOfWorkProvider(pool),
        PostgresPortfolioQueryProvider(pool),
    )
    risk_commands = RiskCommands(
        PostgresRiskInputPreparationProvider(pool),
        PostgresRiskUnitOfWorkProvider(pool),
        PostgresRiskQueryProvider(pool),
    )
    outcome_application = OutcomeApplication(
        PostgresOutcomeInputPreparationProvider(pool),
        PostgresOutcomeUnitOfWorkProvider(pool),
        PostgresOutcomeQueryProvider(pool),
    )
    backtest_application = BacktestApplication(
        PostgresBacktestUnitOfWorkProvider(pool),
        id_factory=uuid4,
    )
    backtest_specifications = PostgresBacktestQueryPort(pool)
    backtest_observations = PostgresBacktestExecutionObservationPort(
        pool, model_inputs=model_training_inputs,
        dataset_inputs=candidate_research_inputs,
    )
    backtest_action_handler = BacktestCanonicalActionHandler(
        artifacts=artifact_application,
        selection=selection_application,
        research_definitions=research_definitions_application,
        reads=PostgresBacktestActionReadPort(pool),
        feature_materializers=(
            IntradayMoveBacktestFeatureAdapter(PostgresExploratoryFeatureInputReadPort(pool)),
            DailyMoveBacktestFeatureAdapter(PostgresDailyFeatureInputReadPort(pool, byte_store)),
        ),
        worker_id="generic-backtest-worker",
        candidates=candidate_application,
        decision_support=decision_support_application,
        decision_contexts=context_commands,
        decision_inference=inference_commands,
        decision_model_forecasts=model_forecast_commands,
        decision_opportunities=opportunity_commands,
        decision_portfolios=portfolio_commands,
        decision_risk=risk_commands,
        outcomes=outcome_application,
        research_partitions=research_partition_commands,
        research_experiments=experiment_commands,
        research_evaluations=evaluation_commands,
        research_models=research_model_application,
        model_adapters=(DeterministicRidgeBacktestModelAdapter(), ResearchBaselineBacktestAdapter()),
        backtests=backtest_application,
        runtime=runtime_application,
    )
    backtest_action_executor = BacktestRuntimeActionExecutor(
        runtime=runtime_application,
        backtests=backtest_application,
        specifications=backtest_specifications,
        handler=backtest_action_handler,
        worker_id="generic-backtest-worker",
    )
    backtest_execution = BacktestExecutor(
        backtest_observations,
        backtest_action_executor,
    )
    backtest_replay = BacktestReplayApplication(
        PostgresBacktestAuthorityQueryPort(pool),
        byte_store,
        backtest_observations,
    )
    backtest_reports = BacktestReportApplication(
        PostgresBacktestReportSourcePort(pool),
        backtest_replay,
    )
    def verify_daily_evidence() -> dict[str, Any]:
        from market_regime_alpha.interfaces.daily_health import daily_health
        return daily_health(application, complete_history=True, replay=True)

    application = TargetApplication(
        daily_prediction_reads=PostgresDailyPredictionReads(pool, byte_store),
        calendar_continuity_reads=PostgresCalendarContinuityReads(pool, byte_store),
        operational_diagnostics=PostgresOperationalDiagnostics(pool),
        backtest_diagnostics=BacktestDiagnosticsApplication(
            PostgresBacktestDiagnosticsSourcePort(pool), backtest_reports,
        ),
        evidence=EvidenceApplication(
            PostgresEvidenceSnapshotPort(pool),
            FilesystemEvidenceIntegrity(settings.artifact_root),
            settings.artifact_root,
            PostgresEvidenceBackup(settings.database_url, settings.artifact_root),
            PostgresArchiveVerificationPort(pool).verify,
            backtest_replay.verify,
            verify_daily_evidence,
        ),
        runtime=runtime_application,
        artifacts=artifact_application,
        market=market_application,
        market_archives=archive_commands,
        archive_operations=archive_operations,
        prospective_archives=ProspectiveArchiveRuntimeApplication(
            runtime=runtime_application,
            artifacts=artifact_application,
            archives=archive_commands,
            operations=archive_operations,
            database_clock=market_clock,
            due_query=PostgresArchiveOperationsReadPort(pool).due_slice_ids,
            terminal_capture_reconciliation=PostgresArchiveOperationsReadPort(pool),
            continuity=PostgresProspectiveContinuityReadPort(pool),
            trading_sessions=PostgresArchiveTradingSessionReadPort(pool),
            target_schedules=PostgresTargetArchiveScheduleReadPort(pool),
            manifest_reader=lambda digest, size: byte_store.read_bytes(ContentHash(digest), expected_size=size),
            archive_inspection=PostgresArchiveInspectionPort(pool),
            archive_verification=PostgresArchiveVerificationPort(pool),
            admission_scope=prospective_series_admission,
        ),
        archive_inspection=PostgresArchiveInspectionPort(pool),
        historical_acquisition_sources=PostgresHistoricalAcquisitionSources(pool),
        archive_acquisition_readiness=PostgresArchiveAcquisitionReadinessReads(pool, byte_store),
        archive_verification=PostgresArchiveVerificationPort(pool),
        archive_trading_sessions=PostgresArchiveTradingSessionReadPort(pool),
        archive_continuity=PostgresProspectiveContinuityReadPort(pool),
        prospective_health=PostgresProspectiveHealthReadPort(pool),
        target_archive_schedules=PostgresTargetArchiveScheduleReadPort(pool),
        provider_qualifications=ProviderQualificationCommands(
            PostgresProviderQualificationUnitOfWorkProvider(pool, id_factory=uuid4),
            id_factory=uuid4,
        ),
        provider_qualification_queries=PostgresProviderQualificationQueryPort(pool),
        market_queries=PostgresMarketQueryProvider(pool),
        market_revision_lineage=PostgresMarketRevisionLineageReadPort(pool),
        selection=selection_application,
        research_definitions=research_definitions_application,
        research_partitions=research_partition_commands,
        research_experiments=experiment_commands,
        backtests=backtest_application,
        backtest_specifications=backtest_specifications,
        backtest_execution=backtest_execution,
        backtest_replay=backtest_replay,
        backtest_reports=backtest_reports,
        exploratory_backtests=ExploratoryBacktestCommands(
            PostgresExploratoryBacktestUnitOfWorkProvider(pool),
            id_factory=uuid4,
        ),
        exploratory_backtest_verifier=(PostgresExploratoryBacktestVerificationPort(pool)),
        exploratory_campaigns=PostgresExploratoryCampaignReadPort(pool),
        exploratory_feature_inputs=PostgresExploratoryFeatureInputReadPort(pool),
        research_models=research_model_application,
        research_evaluations=evaluation_commands,
        research_evaluation_verifier=ResearchEvaluationVerifier(PostgresResearchEvaluationVerificationProvider(pool)),
        research_evidence=EvidenceCommands(
            PostgresEvidenceUnitOfWorkProvider(pool),
            id_factory=uuid4,
        ),
        research_assessments=AssessmentCommands(
            PostgresAssessmentUnitOfWorkProvider(pool, id_factory=uuid4),
            id_factory=uuid4,
        ),
        research_qualifications=QualificationCommands(
            PostgresQualificationUnitOfWorkProvider(pool, id_factory=uuid4),
            id_factory=uuid4,
        ),
        research_qualification_admissions=(PostgresResearchQualificationAdmissionReadPort(pool)),
        research_qualification_verifier=ResearchQualificationVerifier(PostgresResearchQualificationVerificationProvider(pool)),
        formal_research_campaigns=FormalCampaignCommands(
            PostgresFormalCampaignUnitOfWorkProvider(pool),
            id_factory=uuid4,
        ),
        formal_pit_sources=PostgresFormalPitSourceReadPort(pool),
        formal_research_queries=PostgresFormalCampaignQueryPort(pool),
        candidates=candidate_application,
        candidate_queries=PostgresCandidateQueryProvider(pool),
        decision_support=decision_support_application,
        decision_runs=PostgresDecisionRunQueryProvider(pool),
        decision_contexts=context_commands,
        decision_strategies=StrategyCommands(
            PostgresStrategyUnitOfWorkProvider(pool),
            PostgresStrategyQueryProvider(pool),
        ),
        decision_inference=inference_commands,
        decision_model_forecasts=model_forecast_commands,
        decision_opportunities=opportunity_commands,
        decision_portfolios=portfolio_commands,
        decision_risk=risk_commands,
        decision_support_verifier=DecisionRunVerifier(PostgresDecisionRunVerificationProvider(pool)),
        outcomes=outcome_application,
        outcome_queries=PostgresOutcomeQueryProvider(pool),
        outcome_verifier=OutcomeVerifier(
            PostgresOutcomeQueryProvider(pool),
            PostgresOutcomeVerificationProvider(pool),
        ),
        _pool=pool,
    )
    return application


def bootstrap_database(settings: TargetSettings) -> SchemaVerification:
    """Explicit DDL command; never called by ordinary application startup."""

    return SchemaManager(settings.database_url).bootstrap()


def verify_database(settings: TargetSettings) -> SchemaVerification:
    return SchemaManager(settings.database_url).verify()


def database_identity(settings: TargetSettings) -> DatabaseIdentity:
    return SchemaManager(settings.database_url).database_identity()


def inspect_operational_database(
    settings: TargetSettings, *, run_id: UUID, expected_database_name: str,
    expected_database_oid: int, expected_cluster_identity: str, repetitions: int = 2,
) -> dict[str, Any]:
    """Read-only observations remain available before a controlled upgrade.

    No Application writer or schema admission is constructed. This is not an
    alternate business bootstrap and never falls back to a different database.
    """
    pool = TargetPostgresPool(settings.database_url, min_size=0, max_size=1)
    try:
        result = PostgresOperationalDiagnostics(pool).inspect(
            run_id, expected_database_name=expected_database_name,
            expected_database_oid=expected_database_oid,
            expected_cluster_identity=expected_cluster_identity, repetitions=repetitions,
        )
        result["schema_admission"] = "NOT_PERFORMED_READ_ONLY_DIAGNOSTICS"
        return result
    finally:
        pool.close()


def inspect_prospective_series(
    settings: TargetSettings, *, series_code: str, expected_database_name: str,
    expected_database_oid: int, expected_cluster_identity: str,
) -> dict[str, Any]:
    """Exact-scope read-only health, including a scope pending schema upgrade."""
    pool = TargetPostgresPool(settings.database_url, min_size=0, max_size=1)
    try:
        result = PostgresProspectiveHealthReadPort(pool).inspect(series_code)
        identity = result["database"]
        if (identity["name"], identity["oid"], identity["cluster_identity"]) != (
            expected_database_name, expected_database_oid, expected_cluster_identity,
        ):
            raise ValueError("OPERATION_DATABASE_IDENTITY_MISMATCH")
        result["schema_admission"] = "NOT_PERFORMED_READ_ONLY_DIAGNOSTICS"
        return result
    finally:
        pool.close()


def plan_database_recreate(
    settings: TargetSettings,
    authorization: RecreateAuthorization,
) -> RecreatePlan:
    return SchemaManager(settings.database_url).plan_recreate(authorization)


def apply_database_recreate(
    settings: TargetSettings,
    plan: RecreatePlan,
    *,
    challenge: str,
    operator_id: str,
) -> RecreateResult:
    return SchemaManager(settings.database_url).apply_recreate(
        plan,
        challenge=challenge,
        operator_id=operator_id,
    )


def load_recreate_plan(payload: str) -> RecreatePlan:
    return RecreatePlan.from_json(payload)


def plan_operational_database_upgrade(
    settings: TargetSettings,
    authorization: OperationalUpgradeAuthorization,
) -> OperationalUpgradePlan:
    return SchemaManager(settings.database_url).plan_operational_upgrade(authorization)


def apply_operational_database_upgrade(
    settings: TargetSettings,
    plan: OperationalUpgradePlan,
    *,
    challenge: str,
    operator_id: str,
) -> OperationalUpgradeResult:
    return SchemaManager(settings.database_url).apply_operational_upgrade(
        plan,
        challenge=challenge,
        operator_id=operator_id,
    )


def load_operational_upgrade_plan(payload: str) -> OperationalUpgradePlan:
    return OperationalUpgradePlan.from_json(payload)


def make_operational_upgrade_authorization(
    *,
    expected_database_name: str,
    expected_database_oid: int,
    operator_id: str,
    reason: str,
    backup_path: Path,
    backup_sha256: str,
    backup_size_bytes: int,
    minimum_free_bytes: int,
    code_sha: str,
) -> OperationalUpgradeAuthorization:
    return OperationalUpgradeAuthorization(
        expected_database_name=expected_database_name,
        expected_database_oid=expected_database_oid,
        operator_id=operator_id,
        reason=reason,
        backup_path=backup_path,
        backup_sha256=backup_sha256,
        backup_size_bytes=backup_size_bytes,
        minimum_free_bytes=minimum_free_bytes,
        code_sha=code_sha,
    )


def make_recreate_authorization(
    *,
    expected_database_name: str,
    expected_database_oid: int,
    operator_id: str,
    reason: str,
    backup_attestation: str,
) -> RecreateAuthorization:
    return RecreateAuthorization(
        expected_database_name=expected_database_name,
        expected_database_oid=expected_database_oid,
        operator_id=operator_id,
        reason=reason,
        backup_attestation=backup_attestation,
    )


__all__ = [
    "TargetApplication",
    "TargetSettings",
    "apply_operational_database_upgrade",
    "apply_database_recreate",
    "bootstrap_application",
    "bootstrap_database",
    "database_identity",
    "inspect_operational_database",
    "inspect_prospective_series",
    "load_recreate_plan",
    "load_operational_upgrade_plan",
    "make_operational_upgrade_authorization",
    "make_recreate_authorization",
    "plan_database_recreate",
    "plan_operational_database_upgrade",
    "verify_database",
]
