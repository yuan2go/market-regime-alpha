"""Bounded PostgreSQL administration for Continuous Research runs."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import time as wall_time
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.composition import (
    FreeDataPreparationInvocation,
)
from market_regime_alpha.application.continuous_research.free_data_runtime import (
    CanonicalFreeDataProvider,
    CanonicalFreeDataResearchComposition,
    ControlledRuntimeModelSelector,
)
from market_regime_alpha.application.continuous_research.postgres_daily_alpha import (
    PostgresDailyAlphaEvidenceGateResolver,
    PostgresDailyAlphaOwnerResolver,
    PostgresDailyAlphaPredictionAuthority,
)
from market_regime_alpha.application.continuous_research.multi_strategy import (
    PostgresContinuousStrategyOpportunityResolver,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.replay import (
    replay_continuous_research,
)
from market_regime_alpha.application.continuous_research.report import (
    build_continuous_research_report,
)
from market_regime_alpha.application.continuous_research.scheduler import (
    ContinuousResearchScheduleRunner,
    TradingDayAssessment,
)
from market_regime_alpha.application.continuous_research.runner import (
    ContinuousResearchTickRunner,
)
from market_regime_alpha.strategies.postgres_opportunity import (
    PostgresStrategyOpportunityAuthority,
)
from market_regime_alpha.application.continuous_research.runtime_authority_evidence import (
    PostgresRuntimeAuthorityEvidenceRepository,
    RuntimeAuthorityEvidence,
)
from market_regime_alpha.application.continuous_research.ports import (
    ProviderAcquisitionRequest,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
)
from market_regime_alpha.application.free_data_operation.contracts import (
    FreeDataInstrument,
    FreeDataOperationScale,
    FreeDataPreparationRequest,
)
from market_regime_alpha.application.free_data_operation.blocked import (
    FreeDataOperationBlocked,
)
from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationService,
)
from market_regime_alpha.application.free_data_operation.research_universe import (
    FreeResearchUniverseOperator,
)
from market_regime_alpha.application.free_data_operation.historical_security_facts import (
    HistoricalSecurityFactsOperator,
)
from market_regime_alpha.application.governance.access_control import (
    PostgresAccessGovernance,
    SecurityPermission,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_corpus.baostock_archive import (
    BaoStockHistoricalArchiveClient,
)
from market_regime_alpha.application.historical_corpus.decision_materializer import (
    FREE_RESEARCH_UNIVERSE_KIND,
    HistoricalDecisionMaterializer,
)
from market_regime_alpha.application.historical_corpus.evidence_producer import (
    HistoricalEvidenceProducer,
)
from market_regime_alpha.application.historical_corpus.normalization import (
    normalize_baostock_archive,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    DEFAULT_HISTORICAL_STAGE_LEASE,
    HistoricalRunSnapshot,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.historical_research.multi_strategy import (
    MultiStrategyHistoricalAdapter,
    PostgresHistoricalStrategyOpportunityResolver,
)
from market_regime_alpha.application.historical_research.postgres_session_owner import (
    PostgresHistoricalSessionOwner,
)
from market_regime_alpha.application.historical_research.runner import (
    HistoricalResearchRunner,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_validation.free_historical_samples import (
    AShareBarProviderReader,
    FreeHistoricalSampleBuildResult,
    FreeHistoricalSamplePipeline,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationPolicy,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationProtocol,
)
from market_regime_alpha.application.research_validation.factor_research import (
    FactorResearchCatalog,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    FormalEvaluationProtocol,
)
from market_regime_alpha.application.research_validation.formal_forecast_computation import (
    FormalForecastComputationRequest,
)
from market_regime_alpha.application.research_validation.formal_hypothesis_family import (
    FamilyEvaluationObservationBindings,
)
from market_regime_alpha.application.research_validation.formal_protocol_components import (
    FeatureDefinitionSet,
    ThresholdPolicy,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    EntryHoldingExitQualificationPolicy,
    ProspectiveShadowQualificationPolicy,
)
from market_regime_alpha.application.research_validation.postgres_calibration_qualification import (
    PostgresCalibrationQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    FormalProtocolFreezeScope,
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.application.research_validation.postgres_phase_c_gates import (
    PostgresPhaseCGateAuthority,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    PostgresResearchQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_research_model import (
    PostgresResearchModelRepository,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchInferenceRequest,
    ResearchModelTrainingRequest,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
    FormalOOSQualificationPolicy,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.runtime_operations.observability import (
    PostgresRuntimeObservability,
)
from market_regime_alpha.application.runtime_operations.preflight import (
    CanonicalRuntimePreflight,
    RuntimePreflightRequest,
)
from market_regime_alpha.application.runtime_operations.query import (
    PostgresCanonicalRuntimeQuery,
)
from market_regime_alpha.application.runtime_operations.recovery_audit import (
    PostgresRecoveryAudit,
)
from market_regime_alpha.application.shadow_research.attestation import (
    ClockMode,
    RuntimeOrigin,
)
from market_regime_alpha.application.shadow_research.operations import (
    ResearchShadowOperations,
)
from market_regime_alpha.application.shadow_research.free_data_settlement import (
    FreeDataSettlementOperator,
)
from market_regime_alpha.application.strategy_shadow.operator import (
    StrategyDayObservation,
    StrategyShadowDayOperator,
)
from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ShadowOwnerLineageRequest,
    ShadowObservationPolicy,
)
from market_regime_alpha.application.strategy_shadow.performance import (
    PerformancePolicy,
)
from market_regime_alpha.application.strategy_shadow.performance_operator import (
    PortfolioPerformanceOperator,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    StrategyShadowPolicy,
    restore_strategy_shadow_artifact,
    strategy_shadow_artifact_payload,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowPortfolio,
    ShadowPortfolioPolicy,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.application.strategy_shadow.portfolio_operator import (
    PortfolioShadowDayInput,
    PortfolioShadowDayOperator,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite import (
    BaoStockFreeSupplementalClient,
    BaoStockHistoryClient,
    BaoStockSecurityStatusClient,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TencentCurrentQuoteClient,
    TencentFreeOperationalProfile,
)
from market_regime_alpha.data.free_operational_policy import (
    canonical_free_operational_evidence_policy,
)
from market_regime_alpha.data.postgres_trading_calendar import (
    PostgresPITTradingCalendarSnapshotRepository,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    BaoStockADataProvider,
)
from market_regime_alpha.forecasting.sample_provider import (
    HistoricalRegistryPathForecastSampleProvider,
)
from market_regime_alpha.market_data import AssetType, Timeframe
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.settings import DatabaseSettings
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from market_regime_alpha.strategies.feedback_service import (
    close_strategy_feedback_loop,
)
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioPolicy,
)
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.universe.operational import OperationalUniverseArtifact
from market_regime_alpha.universe.postgres_research import (
    PostgresFreeResearchUniverseRepository,
)
from market_regime_alpha.universe.postgres_historical_facts import (
    PostgresHistoricalSecurityFactsRepository,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.runtime_scope import ResearchUniversePolicy
from market_regime_alpha.universe.runtime_scope_operator import (
    PostgresRuntimeScopeOperator,
)
from zoneinfo import ZoneInfo


SUCCESS = 0
ARGUMENT_ERROR = 2
DATABASE_ERROR = 3
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_INSPECT_OPERATIONS = (
    "inspect-trading-date",
    "inspect-run",
    "inspect-tick",
    "inspect-provider",
    "inspect-evidence",
    "inspect-state",
    "inspect-pool",
    "inspect-candidate",
    "inspect-minute",
    "inspect-model-selection",
    "inspect-summary",
    "inspect-strategy",
    "trace",
    "metrics",
)
_READ_OPERATIONS = {
    "preflight",
    "report",
    "replay",
    "report-day",
    "replay-day",
    "research-universe-replay",
    "runtime-scope-report",
    "runtime-scope-replay",
    "historical-report",
    "historical-replay",
    "performance-report",
    "performance-replay",
    "strategy-replay",
    "portfolio-shadow-replay",
    "model-report",
    "model-replay",
    "recovery-audit",
    *_INSPECT_OPERATIONS,
}


def _add_run_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--run-command", type=Path, required=True)
    command.add_argument("--trading-day-assessment", type=Path, required=True)
    command.add_argument("--runtime-configuration", type=Path, required=True)
    command.add_argument("--output-root", type=Path, required=True)
    command.add_argument("--at", required=True)
    command.add_argument(
        "--runtime-clock-mode",
        choices=("LIVE", "SIMULATED"),
        default="LIVE",
        help="LIVE binds host/PostgreSQL clocks; SIMULATED is explicit engineering/replay.",
    )
    command.add_argument(
        "--supplemental-evidence",
        type=Path,
        help="Explicit immutable Free Supplemental Evidence bundle; no discovery/fallback.",
    )
    command.add_argument("--minimum-history-sessions", type=int, default=21)
    command.add_argument("--liquidity-lookback-sessions", type=int, default=21)
    command.add_argument(
        "--minimum-median-daily-amount",
        type=Decimal,
        default=Decimal("10000000"),
    )
    command.add_argument("--provider-timeout-seconds", type=float, default=8.0)
    command.add_argument(
        "--strategy-account-id",
        help=(
            "Resolve Strategy sleeve state from observed Fill allocations and "
            "manual account observations for this account."
        ),
    )
    command.add_argument("--historical-sample-lookback-calendar-days", type=int, default=180)
    command.add_argument("--historical-sample-maximum-per-symbol", type=int, default=60)
    command.add_argument(
        "--daily-alpha-candidate-evidence-id",
        help=(
            "Explicit HISTORICAL_CANDIDATE_POLICY_EVIDENCE root; omitted keeps "
            "the validated Challenger inactive."
        ),
    )
    command.add_argument(
        "--daily-alpha-candidate-evidence-hash",
        help="Exact SHA-256 for --daily-alpha-candidate-evidence-id.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        help="Explicit PostgreSQL authority; environment fallback is disabled.",
    )
    parser.add_argument(
        "--application-schema",
        default="market_regime_alpha",
        help="Explicit lowercase PostgreSQL schema authority.",
    )
    parser.add_argument(
        "--principal-id",
        help="Required active engineering Principal; caller identity is not authenticated.",
    )
    parser.add_argument(
        "--approval-decision-id",
        help="Independent approval required for non-Admin Shadow/recovery mutations.",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run-command", type=Path, required=True)
    admit = subparsers.add_parser("admit-tick")
    admit.add_argument("--tick-command", type=Path, required=True)
    admit.add_argument(
        "--session-phase",
        choices=tuple(item.value for item in ContinuousSessionPhase),
        required=True,
    )
    schedule = subparsers.add_parser("schedule")
    schedule.add_argument("--run-command", type=Path, required=True)
    schedule.add_argument("--trading-day-assessment", type=Path, required=True)
    schedule.add_argument("--at", required=True)
    reserve = subparsers.add_parser("reserve-due-tick")
    reserve.add_argument("--run-command", type=Path, required=True)
    reserve.add_argument("--at", required=True)
    for name, help_text in (
        ("run-due", "Execute one due BaoStock/Tencent Canonical Runtime Tick."),
        ("run-day", "Execute the same Canonical Tick and attach/freeze Research Shadow when in SHADOW mode."),
    ):
        run_command = subparsers.add_parser(name, help=help_text)
        _add_run_arguments(run_command)
    strategy_day = subparsers.add_parser(
        "strategy-day",
        help="Run Entry Research through Strategy Shadow Outcome from PostgreSQL lineage.",
    )
    strategy_inputs = strategy_day.add_mutually_exclusive_group(required=True)
    strategy_inputs.add_argument("--observations", type=Path)
    strategy_inputs.add_argument(
        "--auto",
        type=Path,
        help="Owner-resolved automatic observation request.",
    )
    settle_day = subparsers.add_parser(
        "settle-day",
        help="Acquire free T+1 evidence, settle Research Shadow and build Panel V2 enrichment.",
    )
    settle_day.add_argument("--trading-date", required=True)
    settle_day.add_argument("--next-session-date", required=True)
    settle_day.add_argument("--artifact-root", type=Path, required=True)
    settle_day.add_argument("--at", required=True)
    strategy_replay = subparsers.add_parser("strategy-replay")
    strategy_replay.add_argument("--session-id", required=True)
    portfolio_day = subparsers.add_parser(
        "portfolio-shadow-day",
        help="Append one PostgreSQL-owned A-share Portfolio Shadow day.",
    )
    portfolio_inputs = portfolio_day.add_mutually_exclusive_group(required=True)
    portfolio_inputs.add_argument("--observations", type=Path)
    portfolio_inputs.add_argument(
        "--auto",
        type=Path,
        help="Owner-resolved automatic Portfolio observation request.",
    )
    portfolio_replay = subparsers.add_parser("portfolio-shadow-replay")
    portfolio_replay.add_argument("--portfolio-id", required=True)
    model_train = subparsers.add_parser(
        "model-train",
        help="Train one caller-provenance exploratory Research Challenger model.",
    )
    model_train.add_argument("--input", type=Path, required=True)
    model_report = subparsers.add_parser("model-report")
    model_report.add_argument("--artifact-id", required=True)
    model_replay = subparsers.add_parser("model-replay")
    model_replay.add_argument("--artifact-id", required=True)
    model_execute = subparsers.add_parser(
        "model-execute",
        help="Record one exact-lineage exploratory Shadow inference.",
    )
    model_execute.add_argument("--input", type=Path, required=True)
    universe_sync = subparsers.add_parser("research-universe-sync")
    universe_sync.add_argument("--as-of-date", required=True)
    universe_sync.add_argument("--artifact-root", type=Path, required=True)
    historical_universe_sync = subparsers.add_parser(
        "historical-universe-sync",
        help="Freeze a real effective-dated CSI 300 constituent Research Universe.",
    )
    historical_universe_sync.add_argument("--effective-date", required=True)
    historical_universe_sync.add_argument("--artifact-root", type=Path, required=True)
    historical_universe_history_sync = subparsers.add_parser(
        "historical-universe-history-sync",
        help=("Scan real trading sessions and freeze every distinct effective-dated CSI 300 constituent cohort."),
    )
    historical_universe_history_sync.add_argument("--start-date", required=True)
    historical_universe_history_sync.add_argument("--end-date", required=True)
    historical_universe_history_sync.add_argument("--artifact-root", type=Path, required=True)
    historical_security_facts_sync = subparsers.add_parser(
        "historical-security-facts-sync",
        help=("Acquire and publish effective/publication-dated Industry, shares and corporate-action facts for exact historical cohorts."),
    )
    historical_security_facts_sync.add_argument("--input", type=Path, required=True)
    historical_security_facts_sync.add_argument("--artifact-root", type=Path, required=True)
    universe_replay = subparsers.add_parser("research-universe-replay")
    universe_replay.add_argument("--snapshot-id", required=True)
    universe_replay.add_argument("--artifact-root", type=Path, required=True)
    runtime_scope_build = subparsers.add_parser(
        "runtime-scope-build",
        help="Build one immutable Full-A Runtime Scope from owned Free Data inputs.",
    )
    runtime_scope_build.add_argument("--input", type=Path, required=True)
    runtime_scope_report = subparsers.add_parser("runtime-scope-report")
    runtime_scope_report.add_argument("--scope-id", required=True)
    runtime_scope_replay = subparsers.add_parser("runtime-scope-replay")
    runtime_scope_replay.add_argument("--scope-id", required=True)
    historical_run = subparsers.add_parser(
        "historical-run",
        help="Run a frozen Historical Research range through the shared session kernel.",
    )
    historical_run.add_argument("--input", type=Path, required=True)
    historical_run.add_argument("--artifact-root", type=Path)
    historical_resume = subparsers.add_parser("historical-resume")
    historical_resume.add_argument("--run-id", required=True)
    historical_resume.add_argument("--max-stage-commits", type=int)
    historical_resume.add_argument("--artifact-root", type=Path)
    historical_report = subparsers.add_parser("historical-report")
    historical_report.add_argument("--run-id", required=True)
    historical_replay = subparsers.add_parser("historical-replay")
    historical_replay.add_argument("--run-id", required=True)
    historical_replay.add_argument("--artifact-root", type=Path)
    strategy_feedback_close = subparsers.add_parser(
        "strategy-feedback-close",
        help="Close one Strategy feedback comparison and persist attribution/challenger artifacts.",
    )
    strategy_feedback_close.add_argument(
        "--incumbent-version-id",
        required=True,
    )
    strategy_feedback_close.add_argument(
        "--incumbent-version-hash",
        required=True,
    )
    strategy_feedback_close.add_argument(
        "--challenger-version-id",
        required=True,
    )
    strategy_feedback_close.add_argument(
        "--challenger-version-hash",
        required=True,
    )
    strategy_feedback_close.add_argument("--created-at", required=True)
    historical_acquire = subparsers.add_parser(
        "historical-corpus-acquire",
        help="Acquire, normalize, atomically publish and register frozen BaoStock data.",
    )
    historical_acquire.add_argument("--input", type=Path, required=True)
    historical_acquire.add_argument("--artifact-root", type=Path, required=True)
    historical_evidence = subparsers.add_parser(
        "historical-evidence",
        help="Produce owner-resolved Ablation, Economics and exploratory Model evidence.",
    )
    historical_evidence.add_argument("--run-id", required=True)
    historical_evidence.add_argument("--artifact-root", type=Path, required=True)
    performance_build = subparsers.add_parser(
        "performance-build",
        help="Build immutable multi-period Performance/Attribution from Portfolio Shadow.",
    )
    performance_build.add_argument("--input", type=Path, required=True)
    performance_report = subparsers.add_parser("performance-report")
    performance_report.add_argument("--report-id", required=True)
    performance_replay = subparsers.add_parser("performance-replay")
    performance_replay.add_argument("--report-id", required=True)
    report_day = subparsers.add_parser("report-day")
    report_day.add_argument("--trading-date", required=True)
    report_day.add_argument("--at", required=True)
    replay_day = subparsers.add_parser("replay-day")
    replay_day.add_argument("--trading-date", required=True)
    recovery_audit = subparsers.add_parser("recovery-audit")
    recovery_audit.add_argument("--checked-at", required=True)
    protocol_record = subparsers.add_parser(
        "qualification-protocol-record",
        help=("Record C0 only after PostgreSQL reloads every exact component owner."),
    )
    protocol_record.add_argument("--input", type=Path, required=True)
    owners_record = subparsers.add_parser(
        "qualification-owners-record",
        help=(
            "Record the exact typed pre-Protocol owner package; Model Lineage and PIT Dataset/Universe remain owned by their existing CLIs."
        ),
    )
    owners_record.add_argument("--input", type=Path, required=True)
    forecast_record = subparsers.add_parser(
        "qualification-forecast-record",
        help=("Compute one owner-controlled Formal MultiTargetForecast from Formal Protocol and Formal PIT references."),
    )
    forecast_record.add_argument("--input", type=Path, required=True)
    evaluation_record = subparsers.add_parser(
        "qualification-evaluation-record",
        help=("Resolve the complete frozen Target family through PostgreSQL and record one family-level C4 Evaluation candidate."),
    )
    evaluation_record.add_argument("--input", type=Path, required=True)
    historical_status = subparsers.add_parser(
        "qualification-historical",
        help="Resolve C3 Historical Sample qualification from PostgreSQL owners.",
    )
    historical_status.add_argument("--dataset-id", required=True)
    historical_status.add_argument("--formal-protocol-id")
    historical_status.add_argument("--formal-pit-evidence-id", action="append", dest="formal_pit_evidence_ids")
    historical_status.add_argument("--reason", required=True)
    historical_status.add_argument("--idempotency-key", required=True)
    oos_status = subparsers.add_parser(
        "qualification-oos",
        help="Resolve C4 Locked OOS qualification from replayed PostgreSQL evidence.",
    )
    oos_status.add_argument("--policy", type=Path, required=True)
    oos_status.add_argument("--formal-protocol-id", required=True)
    oos_status.add_argument("--evaluation-result-id", required=True)
    oos_status.add_argument(
        "--historical-sample-decision-id",
        action="append",
        dest="historical_sample_decision_ids",
        required=True,
    )
    oos_status.add_argument(
        "--formal-pit-evidence-id",
        action="append",
        dest="formal_pit_evidence_ids",
        required=True,
    )
    oos_status.add_argument("--reason", required=True)
    oos_status.add_argument("--idempotency-key", required=True)
    calibration_status = subparsers.add_parser(
        "qualification-calibration",
        help="Resolve C5 Calibration qualification from PostgreSQL-owned evidence.",
    )
    calibration_status.add_argument("--policy", type=Path, required=True)
    calibration_status.add_argument("--formal-protocol-id", required=True)
    calibration_status.add_argument("--calibration-artifact-id")
    calibration_status.add_argument("--reason", required=True)
    calibration_status.add_argument("--idempotency-key", required=True)
    shadow_status = subparsers.add_parser(
        "qualification-shadow",
        help="Resolve C7 sustained prospective Strategy Shadow evidence.",
    )
    shadow_status.add_argument("--policy", type=Path, required=True)
    shadow_status.add_argument("--reason", required=True)
    shadow_status.add_argument("--idempotency-key", required=True)
    phase_status = subparsers.add_parser(
        "qualification-status",
        help="Persist owner-resolved C6/C8/C9 status without granting Production.",
    )
    phase_status.add_argument("--formal-protocol-id", required=True)
    phase_status.add_argument("--entry-policy", type=Path)
    phase_status.add_argument("--governance-version", required=True)
    phase_status.add_argument("--reason", required=True)
    phase_status.add_argument("--idempotency-prefix", required=True)
    preflight = subparsers.add_parser("preflight", help="Inspect engineering readiness without executing a Tick.")
    preflight.add_argument("--trading-date", required=True)
    preflight.add_argument(
        "--runtime-mode",
        choices=tuple(item.value for item in RuntimeAuthorityMode),
        required=True,
    )
    preflight.add_argument("--provider-profile-id", required=True)
    preflight.add_argument("--operational-policy-effective-from", required=True)
    preflight.add_argument("--artifact-root", type=Path, required=True)
    preflight.add_argument("--runtime-configuration", type=Path, required=True)
    preflight.add_argument("--trading-calendar", type=Path, required=True)
    preflight.add_argument("--run-id")
    preflight.add_argument("--minimum-free-bytes", type=int, default=1_000_000_000)
    preflight.add_argument("--maximum-clock-skew-seconds", type=float, default=5.0)
    for operation in _INSPECT_OPERATIONS:
        command = subparsers.add_parser(operation)
        if operation == "inspect-trading-date":
            command.add_argument("--trading-date", required=True)
        else:
            command.add_argument("--run-id", required=True)
        if operation == "inspect-tick":
            command.add_argument("--tick-id", required=True)
        if operation == "inspect-provider":
            command.add_argument("--attempt-id", type=int)
    for operation in ("resume", "report", "replay"):
        command = subparsers.add_parser(operation)
        command.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    factory: PostgresConnectionFactory | None = None
    try:
        args = build_parser().parse_args(argv)
        if args.database_url is None:
            raise ValueError("explicit --database-url is required")
        if args.principal_id is None:
            raise ValueError("explicit --principal-id is required")
        settings = DatabaseSettings.from_sources(
            database_url=args.database_url,
            environ={},
        )
        factory = PostgresConnectionFactory(settings, application_schema=args.application_schema)
        read_only = args.operation in _READ_OPERATIONS
        governance = PostgresAccessGovernance(
            factory,
            apply_migrations=False,
        )
        resource_reference = _operator_resource(args)
        try:
            permission = _required_permission(args)
        except PermissionError:
            governance.audit_denied_operation(
                principal_id=ArtifactId(args.principal_id),
                resource_reference=resource_reference,
                reason_code="PRODUCTION_RUNTIME_AUTHORITY_CLOSED",
                occurred_at=_operational_now(),
            )
            raise
        decision = governance.authorize_operation(
            principal_id=ArtifactId(args.principal_id),
            permission=permission,
            resource_reference=resource_reference,
            approval_decision_id=(None if args.approval_decision_id is None else ArtifactId(args.approval_decision_id)),
            occurred_at=_operational_now(),
        )
        if not decision.allowed:
            raise PermissionError(
                f"Principal is not authorized for {permission.value}; "
                f"resource={resource_reference.artifact_id}@"
                f"{resource_reference.content_hash}; "
                f"reasons={','.join(decision.reason_codes)}"
            )
        journal = PostgresContinuousResearchJournal(factory, apply_migrations=not read_only)
        output = (
            _run_due(args, settings, factory, journal)
            if args.operation == "run-due"
            else _run_day(args, settings, factory, journal)
            if args.operation == "run-day"
            else _dispatch(args, journal, factory)
        )
        _emit(output)
        return SUCCESS
    except FreeDataOperationBlocked as exc:
        _emit_error("FREE_DATA_EVIDENCE_BLOCKED", exc)
        return DATABASE_ERROR
    except AShareDataError as exc:
        _emit_error("FREE_DATA_PROVIDER_FAILED", exc)
        return DATABASE_ERROR
    except PermissionError as exc:
        _emit_error("OPERATOR_NOT_AUTHORIZED", exc)
        return ARGUMENT_ERROR
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        _emit_error("ARGUMENT_OR_IDENTITY_INVALID", exc)
        return ARGUMENT_ERROR
    except Exception as exc:
        _emit_error("POSTGRESQL_OPERATION_FAILED", exc)
        return DATABASE_ERROR
    finally:
        if factory is not None:
            factory.close()


def _dispatch(
    args: argparse.Namespace,
    journal: PostgresContinuousResearchJournal,
    factory: PostgresConnectionFactory,
) -> dict[str, Any]:
    if args.operation == "historical-corpus-acquire":
        payload = _load_json_object(args.input)
        required = {"start_date", "end_date", "bucket_count"}
        if not required.issubset(payload) or not set(payload).issubset(
            {
                *required,
                "symbols",
                "universe_snapshot_id",
                "universe_snapshot_ids",
                "universe_timeline_id",
                "context_symbols",
                "context_instruments",
                "timeframe_ranges",
                "acquisition_id",
            }
        ):
            raise ValueError(
                "historical-corpus-acquire requires start_date, end_date, bucket_count and either symbols or universe_snapshot_id"
            )
        symbol_sources = tuple(
            key
            for key in (
                "symbols",
                "universe_snapshot_id",
                "universe_snapshot_ids",
                "universe_timeline_id",
            )
            if key in payload
        )
        if len(symbol_sources) != 1:
            raise ValueError("historical-corpus-acquire requires exactly one symbol source")
        acquisition_id = payload.get("acquisition_id")
        if not isinstance(acquisition_id, str) or not acquisition_id.strip():
            raise ValueError("historical-corpus-acquire requires an explicit acquisition_id")
        timeframe_ranges_payload = payload.get("timeframe_ranges")
        timeframe_ranges = None
        if timeframe_ranges_payload is not None:
            ranges = _object_value(timeframe_ranges_payload, "timeframe_ranges")
            if set(ranges) != {Timeframe.DAILY.value, Timeframe.MINUTE_5.value}:
                raise ValueError("timeframe_ranges requires exact DAILY and MINUTE_5 entries")
            timeframe_ranges = {
                timeframe: (
                    date.fromisoformat(str(_object_value(ranges[timeframe.value], timeframe.value)["start_date"])),
                    date.fromisoformat(str(_object_value(ranges[timeframe.value], timeframe.value)["end_date"])),
                )
                for timeframe in (Timeframe.DAILY, Timeframe.MINUTE_5)
            }
        universe_references: tuple[ValidationArtifactReference, ...] = ()
        if any(
            key in payload
            for key in (
                "universe_snapshot_id",
                "universe_snapshot_ids",
                "universe_timeline_id",
            )
        ):
            universe_repository = PostgresFreeResearchUniverseRepository(
                factory,
                apply_migrations=False,
            )
            timeline_reference: ValidationArtifactReference | None = None
            if "universe_timeline_id" in payload:
                timeline = universe_repository.get_timeline(ArtifactId(str(payload["universe_timeline_id"])))
                snapshot_ids = tuple(str(item.snapshot_reference.artifact_id) for item in timeline.cohorts)
                timeline_reference = timeline.reference
            else:
                snapshot_ids = (
                    (str(payload["universe_snapshot_id"]),)
                    if "universe_snapshot_id" in payload
                    else tuple(
                        str(item)
                        for item in _array_value(
                            payload["universe_snapshot_ids"],
                            "universe_snapshot_ids",
                        )
                    )
                )
            if not snapshot_ids or len(snapshot_ids) != len(set(snapshot_ids)):
                raise ValueError("historical universe snapshot IDs must be non-empty, sorted and unique")
            if timeline_reference is None and snapshot_ids != tuple(sorted(snapshot_ids)):
                raise ValueError("historical universe snapshot IDs must be non-empty, sorted and unique")
            universes = tuple(universe_repository.get(ArtifactId(snapshot_id)) for snapshot_id in snapshot_ids)
            universe_references = tuple(
                sorted(
                    (
                        *tuple(
                            ValidationArtifactReference(
                                FREE_RESEARCH_UNIVERSE_KIND,
                                universe.snapshot_id,
                                universe.snapshot_hash,
                            )
                            for universe in universes
                        ),
                        *((timeline_reference,) if timeline_reference is not None else ()),
                    ),
                    key=lambda item: (
                        item.artifact_kind,
                        str(item.artifact_id),
                        item.content_hash,
                    ),
                )
            )
            stock_symbols = tuple(
                sorted({item.symbol for universe in universes for item in universe.records if item.membership_status.value == "INCLUDED"})
            )
        else:
            stock_symbols = tuple(str(item) for item in _array_value(payload["symbols"], "symbols"))
        if "context_instruments" in payload:
            context_payload = _object_value(
                payload["context_instruments"],
                "context_instruments",
            )
            if set(context_payload) != {"market_index_symbol", "theme_etf_symbol"}:
                raise ValueError("context_instruments requires exact market_index_symbol and theme_etf_symbol")
            market_index_symbol = str(context_payload["market_index_symbol"])
            theme_etf_symbol = str(context_payload["theme_etf_symbol"])
            if market_index_symbol != "000300.SH" or theme_etf_symbol != "510300.SH":
                raise ValueError("Frozen Historical Context requires 000300.SH and 510300.SH")
            context_symbols = tuple(sorted({market_index_symbol, theme_etf_symbol}))
            frozen_context_payload = {
                "schema_version": "historical-context-instrument-set/v1",
                "market_index_symbol": market_index_symbol,
                "theme_etf_symbol": theme_etf_symbol,
                "limitations": [
                    "EXPLORATORY_CONTEXT_ONLY",
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "PIT_INCOMPLETE",
                ],
            }
            context_hash = canonical_hash(frozen_context_payload)
            context_reference = ValidationArtifactReference(
                "HISTORICAL_CONTEXT_INSTRUMENT_SET",
                ArtifactId(f"historical-context-instrument-set:{context_hash[7:]}"),
                context_hash,
            )
            PostgresResearchValidationRepository(
                factory,
                apply_migrations=False,
            ).record(
                artifact_id=context_reference.artifact_id,
                artifact_hash=context_reference.content_hash,
                artifact_kind=context_reference.artifact_kind,
                evidence_authority="ENGINEERING_ONLY",
                payload=frozen_context_payload,
                created_at=datetime.now(UTC).replace(microsecond=0),
            )
        else:
            if "universe_timeline_id" in payload:
                raise ValueError("Longitudinal corpus acquisition requires explicit context_instruments")
            context_symbols = tuple(str(item) for item in _array_value(payload.get("context_symbols", []), "context_symbols"))
            context_reference = None
        symbols = tuple(sorted({*stock_symbols, *context_symbols}))
        raw = BaoStockHistoricalArchiveClient().acquire(
            symbols=symbols,
            start_date=date.fromisoformat(str(payload["start_date"])),
            end_date=date.fromisoformat(str(payload["end_date"])),
            timeframe_ranges=timeframe_ranges,
            bucket_count=int(payload["bucket_count"]),
            checkpoint_root=(args.artifact_root.resolve() / "historical-corpus" / "query-checkpoints"),
            acquisition_id=acquisition_id,
        )
        corpus = PostgresHistoricalCorpusRepository(
            factory,
            artifact_root=args.artifact_root.resolve(),
            apply_migrations=False,
        )
        raw_package = corpus.publish_and_register(raw)
        normalized_package = corpus.publish_and_register(normalize_baostock_archive(raw_package.owner))
        return {
            "operation": "HISTORICAL_CORPUS_ACQUIRE",
            "raw_owner": raw_package.owner.to_canonical_dict(),
            "normalized_owner": normalized_package.owner.to_canonical_dict(),
            "raw_physical_hash": raw_package.physical_hash,
            "normalized_physical_hash": normalized_package.physical_hash,
            "stock_symbol_count": len(stock_symbols),
            "context_symbols": list(sorted(set(context_symbols))),
            "context_reference": (None if context_reference is None else context_reference.to_canonical_dict()),
            "universe_references": [item.to_canonical_dict() for item in universe_references],
            "formal_pit": False,
            "formal_oos": False,
            "data_eligibility": "EXPLORATORY",
        }
    if args.operation == "runtime-scope-build":
        payload = _load_json_object(args.input)
        expected = {
            "policy",
            "as_of",
            "built_at",
            "security_master_snapshot_id",
            "operational_universes",
            "code_revision",
        }
        if set(payload) != expected:
            raise ValueError("runtime-scope-build requires exact owner-bound inputs")
        runtime_scope_receipt = PostgresRuntimeScopeOperator(
            factory,
            apply_migrations=False,
        ).build(
            policy=ResearchUniversePolicy.from_canonical_dict(_object_value(payload["policy"], "policy")),
            as_of=_instant(str(payload["as_of"])),
            built_at=_instant(str(payload["built_at"])),
            security_master_snapshot_id=ArtifactId(str(payload["security_master_snapshot_id"])),
            operational_universes=tuple(
                OperationalUniverseArtifact.from_canonical_dict(_object_value(item, "operational_universe"))
                for item in _array_value(
                    payload["operational_universes"],
                    "operational_universes",
                )
            ),
            code_revision=str(payload["code_revision"]),
        )
        return {
            "operation": "RUNTIME_SCOPE_BUILD",
            **runtime_scope_receipt.to_canonical_dict(),
        }
    if args.operation in {"runtime-scope-report", "runtime-scope-replay"}:
        scope_operator = PostgresRuntimeScopeOperator(
            factory,
            apply_migrations=False,
        )
        runtime_scope_receipt = (
            scope_operator.report(ArtifactId(args.scope_id))
            if args.operation == "runtime-scope-report"
            else scope_operator.replay(ArtifactId(args.scope_id))
        )
        return {
            "operation": args.operation.replace("-", "_").upper(),
            **runtime_scope_receipt.to_canonical_dict(),
        }
    if args.operation in {
        "historical-run",
        "historical-resume",
        "historical-report",
        "historical-replay",
    }:
        historical_journal = PostgresHistoricalResearchJournal(
            factory,
            clock=_operational_now,
            lease_duration=DEFAULT_HISTORICAL_STAGE_LEASE,
            apply_migrations=False,
        )
        if args.operation == "historical-run":
            payload = _load_json_object(args.input)
            if set(payload) != {"command", "max_stage_commits"}:
                raise ValueError("historical-run requires command and max_stage_commits")
            command = HistoricalResearchCommand.from_canonical_dict(_object_value(payload["command"], "command"))
            historical_runner = _historical_runner(
                factory=factory,
                journal=historical_journal,
                command=command,
                artifact_root=args.artifact_root,
            )
            raw_limit = payload["max_stage_commits"]
            historical_snapshot = historical_runner.run(
                command=command,
                max_stage_commits=(None if raw_limit is None else int(raw_limit)),
            )
            return _historical_snapshot_payload("HISTORICAL_RUN", historical_snapshot)
        run_id = ArtifactId(args.run_id)
        if args.operation == "historical-report":
            return _historical_snapshot_payload(
                "HISTORICAL_REPORT",
                historical_journal.get_run(run_id),
            )
        command = historical_journal.get_run(run_id).command
        historical_runner = _historical_runner(
            factory=factory,
            journal=historical_journal,
            command=command,
            artifact_root=args.artifact_root,
        )
        if args.operation == "historical-resume":
            return _historical_snapshot_payload(
                "HISTORICAL_RESUME",
                historical_runner.resume(
                    run_id=run_id,
                    max_stage_commits=args.max_stage_commits,
                ),
            )
        return {
            "operation": "HISTORICAL_REPLAY",
            **historical_runner.replay(run_id=run_id).to_canonical_dict(),
        }
    if args.operation == "historical-evidence":
        run_id = ArtifactId(args.run_id)
        historical_journal = PostgresHistoricalResearchJournal(
            factory,
            clock=_operational_now,
            lease_duration=DEFAULT_HISTORICAL_STAGE_LEASE,
            apply_migrations=False,
        )
        produced = HistoricalEvidenceProducer(
            journal=historical_journal,
            corpus_repository=PostgresHistoricalCorpusRepository(
                factory,
                artifact_root=args.artifact_root.resolve(),
                apply_migrations=False,
            ),
            component_repository=PostgresHistoricalMaterializationRepository(factory, apply_migrations=False),
            evidence_repository=PostgresHistoricalEvidenceRepository(factory, apply_migrations=False),
        ).produce(run_id=run_id)
        return {
            "operation": "HISTORICAL_EVIDENCE",
            "run_id": str(run_id),
            "observation_count": produced.observation_count,
            "evidence": [item.to_canonical_dict() for item in produced.evidence],
        }
    if args.operation == "performance-build":
        payload = _load_json_object(args.input)
        if set(payload) != {"portfolio_id", "policy", "generated_at"}:
            raise ValueError("performance-build requires portfolio_id, policy and generated_at")
        performance_report = PortfolioPerformanceOperator(
            factory,
            apply_migrations=False,
        ).build(
            portfolio_id=ArtifactId(str(payload["portfolio_id"])),
            policy=PerformancePolicy.from_canonical_dict(_object_value(payload["policy"], "policy")),
            generated_at=_instant(str(payload["generated_at"])),
        )
        return {
            "operation": "PERFORMANCE_BUILD",
            **performance_report.to_canonical_dict(),
        }
    if args.operation in {"performance-report", "performance-replay"}:
        performance = PortfolioPerformanceOperator(
            factory,
            apply_migrations=False,
        )
        performance_report = (
            performance.report(ArtifactId(args.report_id))
            if args.operation == "performance-report"
            else performance.replay(ArtifactId(args.report_id))
        )
        return {
            "operation": args.operation.replace("-", "_").upper(),
            **performance_report.to_canonical_dict(),
        }
    if args.operation == "model-train":
        payload = _load_json_object(args.input)
        if set(payload) != {"request", "trained_at"}:
            raise ValueError("model-train requires request and trained_at")
        research_training_request = ResearchModelTrainingRequest.from_canonical_dict(_object_value(payload["request"], "request"))
        research_artifact = PostgresResearchModelRepository(
            factory,
            apply_migrations=False,
        ).train_exploratory(
            research_training_request,
            trained_at=_instant(str(payload["trained_at"])),
        )
        return {
            "operation": "MODEL_TRAIN",
            **research_artifact.to_canonical_dict(),
        }
    if args.operation == "model-report":
        artifact = PostgresResearchModelRepository(
            factory,
            apply_migrations=False,
        ).get_artifact(ArtifactId(args.artifact_id))
        return {"operation": "MODEL_REPORT", **artifact.to_canonical_dict()}
    if args.operation == "model-replay":
        artifact = PostgresResearchModelRepository(
            factory,
            apply_migrations=False,
        ).replay(ArtifactId(args.artifact_id))
        return {"operation": "MODEL_REPLAY", **artifact.to_canonical_dict()}
    if args.operation == "model-execute":
        payload = _load_json_object(args.input)
        if set(payload) != {"artifact_id", "request", "executed_at"}:
            raise ValueError("model-execute requires artifact_id, request and executed_at")
        research_inference_receipt = PostgresResearchModelRepository(
            factory,
            apply_migrations=False,
        ).execute(
            artifact_id=ArtifactId(str(payload["artifact_id"])),
            request=ResearchInferenceRequest.from_canonical_dict(_object_value(payload["request"], "request")),
            executed_at=_instant(str(payload["executed_at"])),
        )
        return {
            "operation": "MODEL_EXECUTE",
            **research_inference_receipt.to_canonical_dict(),
        }
    if args.operation == "strategy-feedback-close":
        return {
            "operation": "STRATEGY_FEEDBACK_CLOSE",
            "feedback": tuple(
                item.to_canonical_dict()
                for item in close_strategy_feedback_loop(
                    repository=PostgresMultiStrategyRepository(
                        factory,
                        apply_migrations=False,
                    ),
                    incumbent_version_reference=RuntimeArtifactReference(
                        "STRATEGY_VERSION",
                        ArtifactId(args.incumbent_version_id),
                        str(args.incumbent_version_hash),
                    ),
                    challenger_version_reference=RuntimeArtifactReference(
                        "STRATEGY_VERSION",
                        ArtifactId(args.challenger_version_id),
                        str(args.challenger_version_hash),
                    ),
                    formal_pit=False,
                    formal_oos=False,
                    calibrated=False,
                    net_economics_established=False,
                    prospective_evidence=False,
                    created_at=_instant(args.created_at),
                )
            ),
        }
    if args.operation == "strategy-day":
        if args.auto is not None:
            payload = _load_json_object(args.auto)
            expected = {
                "trading_date",
                "observed_at",
                "symbol",
                "observation_policy",
                "lineage",
            }
            if set(payload) != expected:
                raise ValueError("strategy-day --auto requires trading_date, observed_at, symbol and observation_policy")
            return StrategyShadowDayOperator(factory).run_auto(
                trading_date=date.fromisoformat(str(payload["trading_date"])),
                observed_at=_instant(str(payload["observed_at"])),
                symbol=(None if payload["symbol"] is None else str(payload["symbol"])),
                policy=ShadowObservationPolicy.from_canonical_dict(
                    _object_value(
                        payload["observation_policy"],
                        "observation_policy",
                    )
                ),
                lineage=ShadowOwnerLineageRequest.from_canonical_dict(_object_value(payload["lineage"], "lineage")),
            )
        payload = _load_json_object(args.observations)
        if set(payload) != {"observation", "lineage"}:
            raise ValueError("strategy-day requires exact observation and lineage objects")
        return StrategyShadowDayOperator(factory).run(
            StrategyDayObservation.from_canonical_dict(_object_value(payload["observation"], "observation")),
            lineage=ShadowOwnerLineageRequest.from_canonical_dict(_object_value(payload["lineage"], "lineage")),
        )
    if args.operation == "settle-day":
        return FreeDataSettlementOperator(
            factory,
            clock=lambda: _instant(args.at),
        ).settle_day(
            trading_date=date.fromisoformat(args.trading_date),
            next_session_date=date.fromisoformat(args.next_session_date),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "strategy-replay":
        return StrategyShadowDayOperator(factory).replay(ArtifactId(args.session_id))
    if args.operation == "portfolio-shadow-day":
        if args.auto is not None:
            payload = _load_json_object(args.auto)
            expected = {
                "research_trading_date",
                "trading_date",
                "observed_at",
                "portfolio_id",
                "initial_cash",
                "portfolio_policy",
                "observation_policy",
                "lineage",
                "strategy_reference",
            }
            if set(payload) != expected:
                raise ValueError("portfolio-shadow-day --auto requires exact owner and Policy inputs")
            portfolio_id = payload["portfolio_id"]
            return PortfolioShadowDayOperator(factory).run_auto(
                research_trading_date=date.fromisoformat(str(payload["research_trading_date"])),
                trading_date=date.fromisoformat(str(payload["trading_date"])),
                observed_at=_instant(str(payload["observed_at"])),
                portfolio_id=(None if portfolio_id is None else ArtifactId(str(portfolio_id))),
                initial_cash=Decimal(str(payload["initial_cash"])),
                policy=ShadowPortfolioPolicy.from_canonical_dict(_object_value(payload["portfolio_policy"], "portfolio_policy")),
                observation_policy=ShadowObservationPolicy.from_canonical_dict(
                    _object_value(
                        payload["observation_policy"],
                        "observation_policy",
                    )
                ),
                lineage=ShadowOwnerLineageRequest.from_canonical_dict(_object_value(payload["lineage"], "lineage")),
                strategy_reference=ValidationArtifactReference.from_canonical_dict(
                    _object_value(payload["strategy_reference"], "strategy_reference")
                ),
            )
        return PortfolioShadowDayOperator(factory).run(PortfolioShadowDayInput.from_canonical_dict(_load_json_object(args.observations)))
    if args.operation == "portfolio-shadow-replay":
        return PortfolioShadowDayOperator(factory).replay(ArtifactId(args.portfolio_id))
    if args.operation == "research-universe-sync":
        return FreeResearchUniverseOperator(factory).sync(
            as_of_date=date.fromisoformat(args.as_of_date),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "historical-universe-sync":
        return FreeResearchUniverseOperator(factory).sync_historical_constituents(
            effective_date=date.fromisoformat(args.effective_date),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "historical-universe-history-sync":
        return FreeResearchUniverseOperator(factory).sync_historical_constituent_history(
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "historical-security-facts-sync":
        payload = _load_json_object(args.input)
        common = {"start_date", "end_date"}
        if set(payload) == {*common, "universe_timeline_id"}:
            timeline_id = ArtifactId(str(payload["universe_timeline_id"]))
            timeline = PostgresFreeResearchUniverseRepository(factory, apply_migrations=False).get_timeline(timeline_id)
            raw_ids = tuple(sorted(str(item.snapshot_reference.artifact_id) for item in timeline.cohorts))
        elif set(payload) == {*common, "universe_snapshot_ids"}:
            timeline_id = None
            raw_ids = tuple(str(item) for item in _array_value(payload["universe_snapshot_ids"], "universe_snapshot_ids"))
        else:
            raise ValueError("historical-security-facts-sync requires one exact Universe timeline or cohort owner set and range")
        if not raw_ids or raw_ids != tuple(sorted(set(raw_ids))):
            raise ValueError("historical Security Fact Universe IDs must be ordered and unique")
        result = HistoricalSecurityFactsOperator(factory).sync(
            universe_snapshot_ids=tuple(ArtifactId(item) for item in raw_ids),
            universe_timeline_reference=(None if timeline_id is None else timeline.reference),
            start_date=date.fromisoformat(str(payload["start_date"])),
            end_date=date.fromisoformat(str(payload["end_date"])),
            artifact_root=args.artifact_root.resolve(),
        )
        return {
            **result,
            "universe_timeline_id": (None if timeline_id is None else str(timeline_id)),
        }
    if args.operation == "research-universe-replay":
        return FreeResearchUniverseOperator(factory).replay(
            ArtifactId(args.snapshot_id),
            artifact_root=args.artifact_root.resolve(),
        )
    if args.operation == "recovery-audit":
        return PostgresRecoveryAudit(factory).inspect(checked_at=_instant(args.checked_at)).to_canonical_dict()
    if args.operation == "qualification-owners-record":
        payload = _load_json_object(args.input)
        _require_principal_actor(args, payload)
        return _record_phase_c_owner_package(
            factory,
            payload,
        )
    if args.operation == "qualification-protocol-record":
        payload = _load_json_object(args.input)
        expected = {"freeze_scope", "actor", "reason", "idempotency_key"}
        if set(payload) != expected:
            raise ValueError(
                "qualification-protocol-record requires a references-only freeze scope plus "
                "actor, reason and idempotency_key; all component payloads are "
                "reloaded from PostgreSQL owners"
            )
        _require_principal_actor(args, payload)
        actor = str(payload["actor"])
        reason = str(payload["reason"])
        idempotency_key = str(payload["idempotency_key"])
        if not actor.strip() or not reason.strip() or not idempotency_key.strip():
            raise ValueError("Formal Protocol actor, reason and idempotency key are required")
        scope = FormalProtocolFreezeScope.from_canonical_dict(dict(_object_value(payload["freeze_scope"], "freeze_scope")))
        recorded_protocol = PostgresFormalProtocolRepository(
            factory,
            apply_migrations=False,
        ).freeze_protocol(
            scope=scope,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return {
            "operation": "QUALIFICATION_PROTOCOL_RECORD",
            **recorded_protocol.to_canonical_dict(),
        }
    if args.operation == "qualification-forecast-record":
        payload = _load_json_object(args.input)
        if set(payload) != {"request", "actor", "reason"}:
            raise ValueError("qualification-forecast-record requires request, actor and reason")
        _require_principal_actor(args, payload)
        request = FormalForecastComputationRequest.from_canonical_dict(dict(_object_value(payload["request"], "request")))
        receipt = PostgresFormalProtocolRepository(
            factory,
            apply_migrations=False,
        ).compute_forecast(
            request,
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
        )
        return {
            "operation": "QUALIFICATION_FORECAST_COMPUTE",
            **receipt.to_canonical_dict(),
        }
    if args.operation == "qualification-evaluation-record":
        payload = _load_json_object(args.input)
        common = {
            "formal_protocol_id",
            "observation_groups",
            "historical_sample_decision_ids",
            "actor",
            "reason",
            "idempotency_key",
        }
        pit_keys = {"formal_pit_evidence_id", "formal_pit_evidence_ids"}
        if set(payload).difference(common) not in (
            {"formal_pit_evidence_id"},
            {"formal_pit_evidence_ids"},
        ) or not common.issubset(payload):
            raise ValueError(
                "qualification-evaluation-record accepts only immutable owner references; result time is assigned by PostgreSQL"
            )
        raw_pit_ids = (
            (payload["formal_pit_evidence_id"],)
            if "formal_pit_evidence_id" in payload
            else _array_value(payload["formal_pit_evidence_ids"], "formal_pit_evidence_ids")
        )
        if not raw_pit_ids or set(payload).intersection(pit_keys) == pit_keys:
            raise ValueError("Formal Family Evaluation requires a non-empty PIT owner set")
        raw_sample_ids = _array_value(
            payload["historical_sample_decision_ids"],
            "historical_sample_decision_ids",
        )
        if not raw_sample_ids:
            raise ValueError("Formal Family Evaluation requires qualified C3 decisions")
        _require_principal_actor(args, payload)
        pit_ids = tuple(ArtifactId(str(item)) for item in raw_pit_ids)
        evaluation_result = PostgresResearchQualificationAuthority(
            factory,
            apply_migrations=False,
        ).record_family_evaluation_candidate(
            formal_protocol_id=ArtifactId(str(payload["formal_protocol_id"])),
            observation_groups=tuple(
                _family_observation_group(item) for item in _array_value(payload["observation_groups"], "observation_groups")
            ),
            historical_sample_decision_ids=tuple(ArtifactId(str(item)) for item in raw_sample_ids),
            formal_pit_evidence_id=pit_ids[0],
            formal_pit_evidence_ids=pit_ids,
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            idempotency_key=str(payload["idempotency_key"]),
        )
        return {
            "operation": "QUALIFICATION_FAMILY_EVALUATION_RECORD",
            "result_id": str(evaluation_result.result_id),
            "result_hash": evaluation_result.result_hash,
            **evaluation_result.identity_payload(),
        }
    if args.operation == "qualification-historical":
        historical_decision = PostgresResearchQualificationAuthority(
            factory,
            apply_migrations=False,
        ).qualify_historical_sample(
            dataset_id=ArtifactId(args.dataset_id),
            formal_protocol_id=(None if args.formal_protocol_id is None else ArtifactId(args.formal_protocol_id)),
            formal_pit_evidence_id=(None if not args.formal_pit_evidence_ids else ArtifactId(args.formal_pit_evidence_ids[0])),
            formal_pit_evidence_ids=tuple(ArtifactId(item) for item in (args.formal_pit_evidence_ids or ())),
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
        )
        return {
            "operation": "QUALIFICATION_HISTORICAL",
            **historical_decision.to_canonical_dict(),
        }
    if args.operation == "qualification-oos":
        policy = FormalOOSQualificationPolicy.from_canonical_dict(_load_json_object(args.policy))
        oos_decision = PostgresResearchQualificationAuthority(
            factory,
            apply_migrations=False,
        ).qualify_formal_oos(
            policy=policy,
            formal_protocol_id=ArtifactId(args.formal_protocol_id),
            evaluation_result_id=ArtifactId(args.evaluation_result_id),
            historical_sample_decision_id=ArtifactId(args.historical_sample_decision_ids[0]),
            historical_sample_decision_ids=tuple(ArtifactId(item) for item in args.historical_sample_decision_ids),
            formal_pit_evidence_id=ArtifactId(args.formal_pit_evidence_ids[0]),
            formal_pit_evidence_ids=tuple(ArtifactId(item) for item in args.formal_pit_evidence_ids),
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
        )
        return {
            "operation": "QUALIFICATION_OOS",
            **oos_decision.to_canonical_dict(),
        }
    if args.operation == "qualification-calibration":
        calibration_policy = CalibrationQualificationPolicy.from_canonical_dict(_load_json_object(args.policy))
        calibration_decision = PostgresCalibrationQualificationAuthority(
            factory,
            apply_migrations=False,
        ).qualify(
            policy=calibration_policy,
            formal_protocol_id=ArtifactId(args.formal_protocol_id),
            calibration_artifact_id=(None if args.calibration_artifact_id is None else ArtifactId(args.calibration_artifact_id)),
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
        )
        return {
            "operation": "QUALIFICATION_CALIBRATION",
            **calibration_decision.to_canonical_dict(),
        }
    if args.operation == "qualification-shadow":
        shadow_policy = ProspectiveShadowQualificationPolicy.from_canonical_dict(_load_json_object(args.policy))
        shadow_decision = PostgresPhaseCGateAuthority(
            factory,
            apply_migrations=False,
        ).resolve_prospective_shadow(
            policy=shadow_policy,
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=args.idempotency_key,
        )
        return {
            "operation": "QUALIFICATION_SHADOW",
            **shadow_decision.to_canonical_dict(),
        }
    if args.operation == "qualification-status":
        authority = PostgresPhaseCGateAuthority(factory, apply_migrations=False)
        formal_protocol_id = ArtifactId(args.formal_protocol_id)
        entry_policy = (
            None
            if args.entry_policy is None
            else EntryHoldingExitQualificationPolicy.from_canonical_dict(_load_json_object(args.entry_policy))
        )
        strategy = authority.resolve_entry_holding_exit(
            formal_protocol_id=formal_protocol_id,
            policy=entry_policy,
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=f"{args.idempotency_prefix}:c6",
        )
        admission = authority.resolve_production_admission(
            formal_protocol_id=formal_protocol_id,
            governance_version=args.governance_version,
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=f"{args.idempotency_prefix}:c8",
        )
        execution = authority.resolve_controlled_execution(
            formal_protocol_id=formal_protocol_id,
            actor=args.principal_id,
            reason=args.reason,
            idempotency_key=f"{args.idempotency_prefix}:c9",
        )
        return {
            "operation": "QUALIFICATION_STATUS",
            "entry_holding_exit": strategy.to_canonical_dict(),
            "production_admission": {
                "decision_id": str(admission.decision_id),
                "decision_hash": admission.decision_hash,
                **admission.identity_payload(),
            },
            "controlled_execution": execution.to_canonical_dict(),
            **_authority_ceiling(),
        }
    if args.operation == "report-day":
        trading_date = date.fromisoformat(args.trading_date)
        runtime = PostgresCanonicalRuntimeQuery(factory).inspect_trading_date(trading_date)
        with factory.connection(read_only=True) as connection:
            shadow_rows = connection.execute(
                """
                SELECT session_id
                FROM shadow_research_session
                WHERE trading_date = %s
                ORDER BY session_id
                """,
                (trading_date,),
            ).fetchall()
            portfolio_rows = connection.execute(
                """
                SELECT portfolio_id, state_id, sequence, cash, nav,
                       gross_exposure, turnover, drawdown, total_cost
                FROM strategy_shadow_portfolio_day
                WHERE trading_date = %s
                ORDER BY portfolio_id
                """,
                (trading_date,),
            ).fetchall()
        research_reports = [ResearchShadowOperations(factory).report(ArtifactId(str(row[0]))) for row in shadow_rows]
        strategy_report = StrategyShadowDayOperator(factory).report_day(
            trading_date,
            generated_at=_instant(args.at),
        )
        return {
            "operation": "REPORT_DAY",
            "trading_date": trading_date.isoformat(),
            "runtime": runtime,
            "research_shadow": research_reports,
            "strategy_shadow": strategy_report,
            "portfolio_shadow": [
                {
                    "portfolio_id": str(row[0]),
                    "state_id": str(row[1]),
                    "sequence": int(row[2]),
                    "cash": str(row[3]),
                    "nav": str(row[4]),
                    "gross_exposure": str(row[5]),
                    "turnover": str(row[6]),
                    "drawdown": str(row[7]),
                    "total_cost": str(row[8]),
                    "shadow_fill_is_real_fill": False,
                    "shadow_position_is_real_position": False,
                }
                for row in portfolio_rows
            ],
            **_authority_ceiling(),
        }
    if args.operation == "replay-day":
        trading_date = date.fromisoformat(args.trading_date)
        with factory.connection(read_only=True) as connection:
            run_rows = connection.execute(
                "SELECT run_id FROM continuous_research_run WHERE trading_date = %s ORDER BY run_id",
                (trading_date,),
            ).fetchall()
            decision_rows = connection.execute(
                """
                SELECT decision.decision_id
                FROM shadow_research_decision AS decision
                JOIN shadow_research_session AS session
                  ON session.session_id = decision.session_id
                WHERE session.trading_date = %s
                ORDER BY decision.decision_id
                """,
                (trading_date,),
            ).fetchall()
            portfolio_rows = connection.execute(
                """
                SELECT portfolio_id FROM strategy_shadow_portfolio_day
                WHERE trading_date = %s ORDER BY portfolio_id
                """,
                (trading_date,),
            ).fetchall()
        research = ResearchShadowOperations(factory)
        strategy_operator = StrategyShadowDayOperator(factory)
        strategy_sessions = strategy_operator.list_sessions(trading_date)
        portfolio_operator = PortfolioShadowDayOperator(factory)
        return {
            "operation": "REPLAY_DAY",
            "trading_date": trading_date.isoformat(),
            "continuous_runtime": [replay_continuous_research(journal, ArtifactId(str(row[0]))).to_canonical_dict() for row in run_rows],
            "research_shadow": [research.replay(ArtifactId(str(row[0]))).to_canonical_dict() for row in decision_rows],
            "strategy_shadow": [strategy_operator.replay(item.session_id) for item in strategy_sessions],
            "portfolio_shadow": [portfolio_operator.replay(ArtifactId(str(row[0]))) for row in portfolio_rows],
            **_authority_ceiling(),
        }
    if args.operation == "preflight":
        report = CanonicalRuntimePreflight(factory).inspect(
            RuntimePreflightRequest(
                trading_date=date.fromisoformat(args.trading_date),
                runtime_mode=RuntimeAuthorityMode(args.runtime_mode),
                provider_profile_id=args.provider_profile_id,
                operational_policy_effective_from=date.fromisoformat(args.operational_policy_effective_from),
                artifact_root=args.artifact_root,
                runtime_configuration_path=args.runtime_configuration,
                trading_calendar_path=args.trading_calendar,
                run_id=(None if args.run_id is None else ArtifactId(args.run_id)),
                minimum_free_bytes=args.minimum_free_bytes,
                maximum_clock_skew=timedelta(seconds=args.maximum_clock_skew_seconds),
            )
        )
        return {"operation": "PREFLIGHT", **report.to_canonical_dict()}
    if args.operation == "prepare":
        run_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        snapshot = journal.create_or_get(run_command)
        return {
            "status": snapshot.status.value,
            "operation": "PREPARE",
            "run_id": str(run_command.run_id),
            "command_hash": run_command.command_hash,
            **_authority_ceiling(),
        }
    if args.operation == "admit-tick":
        tick_command = RuntimeTickCommand.from_canonical_dict(_load_json_object(args.tick_command))
        tick = journal.admit_tick(
            tick_command,
            session_phase=ContinuousSessionPhase(args.session_phase),
        )
        return {
            "status": tick.status.value,
            "operation": "ADMIT_TICK",
            "run_id": str(tick_command.run_id),
            "tick_id": str(tick_command.tick_id),
            "tick_sequence": tick.tick_sequence,
            **_authority_ceiling(),
        }
    if args.operation == "schedule":
        schedule_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        trading_day = TradingDayAssessment.from_canonical_dict(_load_json_object(args.trading_day_assessment))
        journal.create_or_get(schedule_command)
        schedule = journal.initialize_schedule(
            run_command=schedule_command,
            policy=default_continuous_decision_window_policy(),
            trading_day=trading_day,
            initial_tick_at=_instant(args.at),
        )
        return {
            "operation": "SCHEDULE",
            **schedule.to_canonical_dict(),
            **_authority_ceiling(),
        }
    if args.operation == "reserve-due-tick":
        reserve_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        reserved_tick = journal.reserve_due_tick(
            run_command=reserve_command,
            policy=default_continuous_decision_window_policy(),
            now=_instant(args.at),
        )
        return {
            "operation": "RESERVE_DUE_TICK",
            "status": "NOT_DUE" if reserved_tick is None else "PENDING",
            "run_id": str(reserve_command.run_id),
            "tick_id": (None if reserved_tick is None else str(reserved_tick.command.tick_id)),
            "tick_sequence": (None if reserved_tick is None else reserved_tick.tick_sequence),
            **_authority_ceiling(),
        }
    if args.operation.startswith("inspect-"):
        query = PostgresCanonicalRuntimeQuery(factory)
        if args.operation == "inspect-trading-date":
            return query.inspect_trading_date(date.fromisoformat(args.trading_date))
        run_id = ArtifactId(args.run_id)
        if args.operation == "inspect-run":
            return {
                "operation": "INSPECT_RUN",
                **query.inspect_run(run_id).to_canonical_dict(),
            }
        if args.operation == "inspect-tick":
            return query.inspect_tick(run_id, ArtifactId(args.tick_id))
        if args.operation == "inspect-provider":
            return query.inspect_provider(run_id, attempt_id=args.attempt_id)
        operation_method = {
            "inspect-evidence": query.inspect_evidence,
            "inspect-state": query.inspect_state,
            "inspect-pool": query.inspect_pool,
            "inspect-candidate": query.inspect_candidate,
            "inspect-minute": query.inspect_minute,
            "inspect-model-selection": query.inspect_model_selection,
            "inspect-summary": query.inspect_summary,
            "inspect-strategy": query.inspect_strategy,
        }[args.operation]
        return operation_method(run_id)
    run_id = ArtifactId(args.run_id)
    if args.operation in {"trace", "metrics"}:
        observability = PostgresRuntimeObservability(factory)
        return observability.trace_run(run_id) if args.operation == "trace" else observability.metrics(run_id)
    if args.operation == "resume":
        snapshot = journal.resume(run_id)
        return {
            "status": snapshot.status.value,
            "operation": "RESUME",
            "run_id": str(run_id),
            "tick_count": len(snapshot.ticks),
            **_authority_ceiling(),
        }
    if args.operation == "report":
        return build_continuous_research_report(journal, run_id)
    if args.operation == "replay":
        return replay_continuous_research(journal, run_id).to_canonical_dict()
    raise ValueError("unsupported Continuous Research operation")


def _daily_alpha_evidence_root(
    args: argparse.Namespace,
) -> ValidationArtifactReference | None:
    evidence_id = args.daily_alpha_candidate_evidence_id
    evidence_hash = args.daily_alpha_candidate_evidence_hash
    if (evidence_id is None) != (evidence_hash is None):
        raise ValueError(
            "Daily Alpha Evidence root requires both exact ID and hash"
        )
    if evidence_id is None:
        return None
    return ValidationArtifactReference(
        "HISTORICAL_CANDIDATE_POLICY_EVIDENCE",
        ArtifactId(str(evidence_id)),
        str(evidence_hash),
    )


def _run_due(
    args: argparse.Namespace,
    settings: DatabaseSettings,
    factory: PostgresConnectionFactory,
    journal: PostgresContinuousResearchJournal,
) -> dict[str, Any]:
    run_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
    trading_day = TradingDayAssessment.from_canonical_dict(_load_json_object(args.trading_day_assessment))
    now = _instant(args.at).astimezone(UTC)
    operational_now = _operational_now()
    with factory.connection(read_only=True) as connection:
        row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None or not isinstance(row[0], datetime):
        raise ValueError("PostgreSQL clock authority is unavailable")
    postgres_now = row[0].astimezone(UTC)
    if args.runtime_clock_mode == "LIVE" and (
        abs((now - operational_now).total_seconds()) > 5
        or abs((now - postgres_now).total_seconds()) > 5
        or abs((operational_now - postgres_now).total_seconds()) > 5
    ):
        raise ValueError("LIVE --at, host clock and PostgreSQL clock must agree within five seconds")
    configuration_path = args.runtime_configuration.resolve()
    configuration = load_controlled_runtime_configuration(configuration_path)
    if (
        run_command.research_configuration_id != configuration.configuration_id
        or run_command.research_configuration_hash != configuration.configuration_hash
    ):
        raise ValueError("run command does not bind Controlled configuration")
    decision = datetime.combine(
        run_command.trading_date,
        time(14, 55),
        tzinfo=_SHANGHAI,
    )
    decision_utc = decision.astimezone(UTC)
    free_request = FreeDataPreparationRequest(
        scale=FreeDataOperationScale.from_symbol_count(len(run_command.requested_symbols)),
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        decision_time=DecisionTime(decision),
        created_at=now,
        code_revision=run_command.code_revision,
        instruments=tuple(FreeDataInstrument(symbol=symbol, asset_type=AssetType.A_SHARE) for symbol in run_command.requested_symbols),
        membership_source=(f"CANONICAL_FREE_DATA_{len(run_command.requested_symbols)}"),
        minimum_history_sessions=args.minimum_history_sessions,
        liquidity_lookback_sessions=args.liquidity_lookback_sessions,
        minimum_median_daily_amount=args.minimum_median_daily_amount,
        configuration_hash=configuration.configuration_hash,
    )
    repositories = RepositoryFactory(settings, postgres_factory=factory)
    repositories.bind_runtime("CONTINUOUS_RESEARCH", str(run_command.run_id))
    simulated_runtime_now = [now]

    def simulated_sleep(seconds: float) -> None:
        simulated_runtime_now[0] += timedelta(seconds=seconds)

    runtime_clock = _operational_now if args.runtime_clock_mode == "LIVE" else lambda: simulated_runtime_now[0]
    runtime_sleeper = wall_time.sleep if args.runtime_clock_mode == "LIVE" else simulated_sleep
    history_client = BaoStockHistoryClient(
        clock=runtime_clock,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    )
    canonical_supplemental_policy = canonical_free_operational_evidence_policy()
    supplemental_policy = (
        canonical_supplemental_policy
        if (
            args.runtime_clock_mode == "LIVE"
            and args.supplemental_evidence is None
            and run_command.trading_date >= min(item.effective_from for item in canonical_supplemental_policy.themes)
        )
        else None
    )
    profile = TencentFreeOperationalProfile(
        history_client=history_client,
        supplemental_client=(
            BaoStockFreeSupplementalClient(
                history_client=history_client,
                policy=supplemental_policy,
                provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
                clock=runtime_clock,
            )
            if supplemental_policy is not None
            else None
        ),
        security_status_client=BaoStockSecurityStatusClient(
            timeout_seconds=args.provider_timeout_seconds,
            clock=runtime_clock,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
        current_client=TencentCurrentQuoteClient(
            timeout_seconds=args.provider_timeout_seconds,
            clock=runtime_clock,
            provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        ),
    )
    # Every durable lease/receipt in one invocation must observe the same
    # trusted (LIVE) or explicitly simulated engineering clock.
    journal = PostgresContinuousResearchJournal(
        factory,
        clock=runtime_clock,
        lease_duration=timedelta(minutes=5),
        apply_migrations=False,
    )

    historical_sample_build: FreeHistoricalSampleBuildResult | None = None
    forecast_sample_provider = None
    validation_repository = None
    if run_command.authority_mode in {
        RuntimeAuthorityMode.RESEARCH,
        RuntimeAuthorityMode.SHADOW,
    }:
        validation_repository = PostgresResearchValidationRepository(
            factory,
            apply_migrations=False,
        )
        forecast_sample_provider = HistoricalRegistryPathForecastSampleProvider(validation_repository)

    service = FreeDataOperationService(
        repositories=repositories,
        output_root=args.output_root,
        code_revision=run_command.code_revision,
        clock=runtime_clock,
        live_profile=profile,
        sleeper=runtime_sleeper,
        forecast_sample_provider=forecast_sample_provider,
        operational_supplemental_policy=supplemental_policy,
    )
    policy = default_continuous_decision_window_policy()
    journal.create_or_get(run_command)
    schedule = journal.initialize_schedule(
        run_command=run_command,
        policy=policy,
        trading_day=trading_day,
        initial_tick_at=decision_utc,
    )
    if schedule.status.value == "NON_TRADING_DAY":
        return _run_due_stage_output(
            run_command=run_command,
            status="NON_TRADING_DAY",
            stage="NO_ACQUISITION",
            reason_codes=("ENTRY_BLOCKED", "NON_TRADING_DAY"),
        )
    local_now = now.astimezone(_SHANGHAI)
    if local_now.timetz().replace(tzinfo=None) < time(14, 54):
        service.prepare_static_sources(
            request=free_request,
            runtime_configuration_path=configuration_path,
        )
        return _run_due_stage_output(
            run_command=run_command,
            status="PREPARING",
            stage="BAOSTOCK_STATIC_SOURCES_FROZEN",
            reason_codes=(
                "BAOSTOCK_HISTORY_FROZEN",
                "BAOSTOCK_SECURITY_STATUS_FROZEN",
                "ENTRY_BLOCKED",
                "WAITING_FOR_TENCENT_DECISION_QUOTE",
            ),
        )

    if validation_repository is not None:
        historical_sample_build = FreeHistoricalSamplePipeline(
            reader=AShareBarProviderReader(BaoStockADataProvider()),
            repository=validation_repository,
            clock=runtime_clock,
            lookback_calendar_days=args.historical_sample_lookback_calendar_days,
            maximum_samples_per_symbol=args.historical_sample_maximum_per_symbol,
        ).build_and_register(
            symbols=run_command.requested_symbols,
            configuration=configuration.path_forecast,
            current_decision_time=DecisionTime(decision),
        )

    def invocation() -> FreeDataPreparationInvocation:
        return FreeDataPreparationInvocation(
            request=free_request,
            runtime_configuration_path=configuration_path,
            idempotency_key=f"{run_command.run_id}:free-data",
            supplemental_evidence_path=args.supplemental_evidence,
        )

    provider = CanonicalFreeDataProvider(
        service=service,
        invocation_builder=lambda _: invocation(),
        clock=runtime_clock,
    )
    opportunity_authority = PostgresStrategyOpportunityAuthority(factory)
    daily_alpha_evidence_root = _daily_alpha_evidence_root(args)
    children = CanonicalFreeDataResearchComposition(
        service=service,
        invocation_builder=lambda _: invocation(),
        model_selector=ControlledRuntimeModelSelector(repositories.model_governance()),
        summary_repository=repositories.decision_system(clock=runtime_clock),
        state_repository=repositories.state_system(clock=runtime_clock),
        strategy_repository=repositories.multi_strategy(),
        strategy_shadow_repository=(
            None
            if args.strategy_account_id is None
            else repositories.strategy_shadow()
        ),
        strategy_account_id=args.strategy_account_id,
        strategy_opportunity_resolver=PostgresContinuousStrategyOpportunityResolver(
            opportunity_authority
        ),
        strategy_opportunity_authority=opportunity_authority,
        daily_alpha_authority=PostgresDailyAlphaPredictionAuthority(
            factory,
            resolver=PostgresDailyAlphaOwnerResolver(factory),
        ),
        daily_alpha_evidence_gate=PostgresDailyAlphaEvidenceGateResolver(
            factory,
            root_candidate_policy_reference=daily_alpha_evidence_root,
        ).assess,
        clock=runtime_clock,
    )
    tick_runner = ContinuousResearchTickRunner(
        journal=journal,
        provider=provider,
        children=children,
        policy=policy,
        clock=runtime_clock,
    )

    def provider_request_builder(_: ContinuousResearchCommand, __: RuntimeTickCommand) -> ProviderAcquisitionRequest:
        return ProviderAcquisitionRequest(
            provider_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
            product="BAOSTOCK_TENCENT_CANONICAL_FREE_DATA",
            request_hash=free_request.command_hash,
            provider_revision="canonical-free-data-profile-v1",
        )

    result = ContinuousResearchScheduleRunner(
        journal=journal,
        tick_runner=tick_runner,
        policy=policy,
        provider_request_builder=provider_request_builder,
    ).run_due_once(
        run_command=run_command,
        trading_day=trading_day,
        now=now,
        predecision_lead=timedelta(minutes=1),
    )
    summary_id = None
    summary_outcome = None
    automatic_settlement: dict[str, Any] = {
        "status": "WAITING_FOR_T_PLUS_1_CLOSE",
        "reason_codes": ["T_PLUS_1_CLOSE_NOT_YET_OBSERVABLE"],
    }
    if result.tick_result is not None:
        tick_id = result.tick_result.tick.command.tick_id
        PostgresRuntimeAuthorityEvidenceRepository(factory).record(
            RuntimeAuthorityEvidence.create(
                run_id=run_command.run_id,
                tick_id=tick_id,
                clock_mode=(ClockMode.LIVE_TRUSTED if args.runtime_clock_mode == "LIVE" else ClockMode.SIMULATED),
                runtime_origin=RuntimeOrigin.LIVE_ACQUISITION,
                clock_source=(
                    "POSTGRESQL_AND_SYSTEM_UTC_CLOCK" if args.runtime_clock_mode == "LIVE" else "EXPLICIT_SIMULATED_RUNTIME_CLOCK"
                ),
                origin_source="BAOSTOCK_TENCENT_CANONICAL_FREE_DATA",
                observed_at=(postgres_now if args.runtime_clock_mode == "LIVE" else now),
                recorded_at=(postgres_now if args.runtime_clock_mode == "LIVE" else max(postgres_now, now)),
                code_revision=run_command.code_revision,
            )
        )
        try:
            summary = repositories.decision_system().get_research_summary_for_tick(
                run_id=run_command.run_id,
                tick_id=tick_id,
                runtime_mode=run_command.authority_mode,
            )
        except (KeyError, ValueError):
            summary = None
        if summary is not None:
            summary_id = str(summary.summary_id)
            summary_outcome = summary.outcome.value
        if local_now.timetz().replace(tzinfo=None) >= time(15):
            prepared = service.prepare(
                request=free_request,
                runtime_configuration_path=configuration_path,
                idempotency_key=f"{run_command.run_id}:free-data",
                supplemental_evidence_path=args.supplemental_evidence,
            )
            automatic_settlement = _settle_previous_prediction_if_due(
                factory=factory,
                calendar=prepared.prepared_inputs.calendar,
                current_session=run_command.trading_date,
                artifact_root=args.output_root.resolve(),
                clock=runtime_clock,
                authority_mode=run_command.authority_mode,
            )
    return {
        "operation": "RUN_DUE",
        "status": result.status,
        "run_id": str(run_command.run_id),
        "runtime_mode": run_command.authority_mode.value,
        "provider_profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        "runtime_clock_mode": args.runtime_clock_mode,
        "summary_id": summary_id,
        "summary_outcome": summary_outcome,
        "reason_codes": list(result.reason_codes),
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": summary_id is not None,
        "historical_sample_build": (None if historical_sample_build is None else historical_sample_build.to_canonical_dict()),
        "path_forecast_registry_wired": forecast_sample_provider is not None,
        "automatic_outcome_settlement": automatic_settlement,
    }


def _settle_previous_prediction_if_due(
    *,
    factory: PostgresConnectionFactory,
    calendar: Any,
    current_session: date,
    artifact_root: Path,
    clock: Any,
    authority_mode: RuntimeAuthorityMode,
) -> dict[str, Any]:
    """Settle the prior canonical session without creating another scheduler."""

    if authority_mode is not RuntimeAuthorityMode.SHADOW:
        return {
            "status": "NOT_APPLICABLE",
            "reason_codes": ["SHADOW_OUTCOME_AUTHORITY_NOT_ACTIVE"],
        }
    sessions = calendar.trading_dates
    if current_session not in sessions:
        return {
            "status": "CALENDAR_BLOCKED",
            "reason_codes": ["CURRENT_SESSION_NOT_IN_CANONICAL_CALENDAR"],
        }
    index = sessions.index(current_session)
    if index == 0:
        return {
            "status": "NO_DUE_PREDICTION",
            "reason_codes": ["NO_PREVIOUS_CANONICAL_SESSION"],
        }
    previous_session = sessions[index - 1]
    with factory.connection(read_only=True) as connection:
        row = connection.execute(
            """
            SELECT count(*), count(*) FILTER (WHERE status = 'SETTLED')
            FROM shadow_research_session
            WHERE trading_date = %s
              AND status IN ('OUTCOME_PENDING', 'SETTLED')
            """,
            (previous_session,),
        ).fetchone()
    if row is None or int(row[0]) == 0:
        return {
            "status": "NO_DUE_PREDICTION",
            "decision_session": previous_session.isoformat(),
            "target_session": current_session.isoformat(),
            "reason_codes": ["NO_PENDING_SHADOW_PREDICTION"],
        }
    if int(row[0]) != 1:
        raise ValueError("automatic settlement requires one exact prior-session owner")
    try:
        settled = FreeDataSettlementOperator(factory, clock=clock).settle_day(
            trading_date=previous_session,
            next_session_date=current_session,
            artifact_root=artifact_root,
        )
    except ValueError as exc:
        if str(exc) == "settle-day requires selected Candidates":
            return {
                "status": "NO_SELECTED_CANDIDATES",
                "decision_session": previous_session.isoformat(),
                "target_session": current_session.isoformat(),
                "reason_codes": ["NO_SELECTED_CANDIDATES"],
            }
        raise
    return {
        "status": "SETTLED" if int(row[1]) == 0 else "REPLAY_VERIFIED",
        "decision_session": previous_session.isoformat(),
        "target_session": current_session.isoformat(),
        "settlement_id": settled["factual_outcome_id"],
        "targeted_outcome_id": settled["targeted_outcome_id"],
        "reason_codes": [
            "T_PLUS_1_OUTCOME_SETTLED_IDEMPOTENTLY",
            "PREDICTION_SNAPSHOT_IMMUTABLE",
        ],
    }


def _run_day(
    args: argparse.Namespace,
    settings: DatabaseSettings,
    factory: PostgresConnectionFactory,
    journal: PostgresContinuousResearchJournal,
) -> dict[str, Any]:
    output = _run_due(args, settings, factory, journal)
    output["operation"] = "RUN_DAY"
    if output.get("status") != "COMPLETED":
        output["research_shadow_status"] = "NOT_READY"
        return output
    run_id = ArtifactId(str(output["run_id"]))
    runtime = journal.get_run(run_id)
    if runtime.command.authority_mode is not RuntimeAuthorityMode.SHADOW:
        output["research_shadow_status"] = "NOT_APPLICABLE"
        return output
    session, decision = ResearchShadowOperations(factory).run_day(run_id)
    output.update(
        {
            "research_shadow_status": session.status.value,
            "research_shadow_session_id": str(session.command.session_id),
            "research_shadow_decision_id": str(decision.decision_id),
            "shadow_order_created": False,
            "shadow_fill_created": False,
            "real_position_mutated": False,
        }
    )
    return output


def _run_due_stage_output(
    *,
    run_command: ContinuousResearchCommand,
    status: str,
    stage: str,
    reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "operation": "RUN_DUE",
        "status": status,
        "stage": stage,
        "run_id": str(run_command.run_id),
        "runtime_mode": run_command.authority_mode.value,
        "provider_profile": TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        "summary_id": None,
        "summary_outcome": None,
        "reason_codes": list(reason_codes),
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": False,
    }


def _load_json_object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("command file must contain a JSON object")
    return payload


def _object_value(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _array_value(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return tuple(value)


def _family_observation_group(
    value: object,
) -> FamilyEvaluationObservationBindings:
    group = _object_value(value, "observation_groups[]")
    if set(group) != {
        "target_reference",
        "panel_reference",
        "observation_bindings",
    }:
        raise ValueError("observation_groups[] accepts only Target, Panel and immutable bindings")
    return FamilyEvaluationObservationBindings(
        target_reference=ValidationArtifactReference.from_canonical_dict(
            _object_value(
                group["target_reference"],
                "observation_groups[].target_reference",
            )
        ),
        panel_reference=ValidationArtifactReference.from_canonical_dict(
            _object_value(
                group["panel_reference"],
                "observation_groups[].panel_reference",
            )
        ),
        observation_bindings=tuple(
            FormalEvaluationObservationBinding.from_canonical_dict(_object_value(item, "observation_bindings[]"))
            for item in _array_value(
                group["observation_bindings"],
                "observation_groups[].observation_bindings",
            )
        ),
    )


def _record_phase_c_owner_package(
    factory: PostgresConnectionFactory,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    expected = {
        "target_protocol",
        "trading_calendar",
        "evaluation_protocol",
        "feature_definition_set",
        "panel_enrichment",
        "factor_catalog",
        "threshold_policy",
        "formal_oos_policy",
        "calibration_protocol",
        "calibration_policy",
        "strategy_policy",
        "portfolio_policy",
        "portfolio",
        "entry_holding_exit_policy",
        "actor",
        "reason",
        "idempotency_key",
    }
    if set(payload) != expected:
        raise ValueError("qualification-owners-record requires the exact typed owner package")
    actor = str(payload["actor"])
    reason = str(payload["reason"])
    idempotency_key = str(payload["idempotency_key"])
    if not actor.strip() or not reason.strip() or not idempotency_key.strip():
        raise ValueError("owner package actor, reason and idempotency key are required")
    target = OutcomeTargetProtocol.from_canonical_dict(_object_value(payload["target_protocol"], "target_protocol"))
    calendar = TradingCalendarArtifact.from_canonical_dict(_object_value(payload["trading_calendar"], "trading_calendar"))
    evaluation = FormalEvaluationProtocol.from_canonical_dict(dict(_object_value(payload["evaluation_protocol"], "evaluation_protocol")))
    features = FeatureDefinitionSet.from_canonical_dict(_object_value(payload["feature_definition_set"], "feature_definition_set"))
    enrichment = ResearchPanelEnrichment.from_canonical_dict(_object_value(payload["panel_enrichment"], "panel_enrichment"))
    factors = FactorResearchCatalog.from_canonical_dict(_object_value(payload["factor_catalog"], "factor_catalog"))
    threshold = ThresholdPolicy.from_canonical_dict(_object_value(payload["threshold_policy"], "threshold_policy"))
    oos_policy = FormalOOSQualificationPolicy.from_canonical_dict(_object_value(payload["formal_oos_policy"], "formal_oos_policy"))
    calibration_protocol = CalibrationProtocol.from_canonical_dict(_object_value(payload["calibration_protocol"], "calibration_protocol"))
    calibration_policy = CalibrationQualificationPolicy.from_canonical_dict(
        _object_value(payload["calibration_policy"], "calibration_policy")
    )
    strategy_payload = dict(_object_value(payload["strategy_policy"], "strategy_policy"))
    if (
        set(strategy_payload)
        != {
            "policy_id",
            "policy_hash",
            "schema",
            "policy_version",
            "rule_kinds",
            "fixed_horizon_sessions",
            "trailing_drawdown",
            "protection_return",
            "participation_rate",
            "limitations",
        }
        or strategy_payload["schema"] != "strategy-shadow-policy/v1"
    ):
        raise ValueError("strategy_policy must use the exact typed contract")
    strategy_id = ArtifactId(str(strategy_payload.pop("policy_id")))
    strategy_hash = str(strategy_payload.pop("policy_hash"))
    strategy = restore_strategy_shadow_artifact(
        artifact_kind="POLICY",
        artifact_id=strategy_id,
        artifact_hash=strategy_hash,
        payload=strategy_payload,
    )
    if not isinstance(strategy, StrategyShadowPolicy):
        raise ValueError("strategy_policy did not restore a typed Policy")
    if canonical_hash(strategy_shadow_artifact_payload(strategy)) != strategy_hash:
        raise ValueError("strategy_policy immutable identity mismatch")
    portfolio_policy = ShadowPortfolioPolicy.from_canonical_dict(_object_value(payload["portfolio_policy"], "portfolio_policy"))
    portfolio = ShadowPortfolio.from_canonical_dict(_object_value(payload["portfolio"], "portfolio"))
    entry_policy = EntryHoldingExitQualificationPolicy.from_canonical_dict(
        _object_value(
            payload["entry_holding_exit_policy"],
            "entry_holding_exit_policy",
        )
    )

    target = PostgresTargetOutcomeRepository(factory, apply_migrations=False).register_protocol(target)
    calendar = PostgresPITTradingCalendarSnapshotRepository(factory, apply_migrations=False).record(calendar)
    validation = PostgresResearchValidationRepository(factory, apply_migrations=False)
    validation.record_formal_evaluation_protocol(evaluation)
    validation.record_feature_definition_set(features)
    validation.record_panel_enrichment(enrichment)
    validation.record_factor_catalog(factors)
    validation.record_threshold_policy(threshold)
    PostgresResearchQualificationAuthority(factory, apply_migrations=False).record_oos_policy(oos_policy)
    with factory.connection(read_only=True) as connection:
        recorded_at_row = connection.execute("SELECT date_trunc('second', clock_timestamp())").fetchone()
    if recorded_at_row is None or not isinstance(recorded_at_row[0], datetime):
        raise RuntimeError("PostgreSQL clock did not return an authority timestamp")
    recorded_at = recorded_at_row[0]
    validation.record_calibration_protocol(
        calibration_protocol,
        recorded_at=recorded_at,
    )
    PostgresCalibrationQualificationAuthority(factory, apply_migrations=False).record_policy(calibration_policy)
    PostgresStrategyShadowRepository(factory, apply_migrations=False).save_policy(strategy, created_at=recorded_at)
    PostgresShadowPortfolioRepository(factory, apply_migrations=False).save_portfolio(policy=portfolio_policy, portfolio=portfolio)
    PostgresPhaseCGateAuthority(factory, apply_migrations=False).record_entry_holding_exit_policy(entry_policy)

    owners = (
        ("FREEZE_TARGET_PROTOCOL", _reference_for("OUTCOME_TARGET_PROTOCOL", target.protocol_id, target.protocol_hash)),
        ("FREEZE_TRADING_CALENDAR", _reference_for("TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash)),
        ("FREEZE_EVALUATION_PROTOCOL", _reference_for("FORMAL_EVALUATION_PROTOCOL", evaluation.protocol_id, evaluation.protocol_hash)),
        (
            "FREEZE_FEATURE_DEFINITION_SET",
            _reference_for("FEATURE_DEFINITION_SET", features.definition_set_id, features.definition_set_hash),
        ),
        ("FREEZE_FACTOR_CATALOG", _reference_for("FACTOR_CATALOG", factors.catalog_id, factors.catalog_hash)),
        ("FREEZE_THRESHOLD_POLICY", _reference_for("THRESHOLD_POLICY", threshold.policy_id, threshold.policy_hash)),
        ("FREEZE_FORMAL_OOS_POLICY", _reference_for("FORMAL_OOS_QUALIFICATION_POLICY", oos_policy.policy_id, oos_policy.policy_hash)),
        ("FREEZE_CALIBRATION_POLICY", _reference_for("CALIBRATION_POLICY", calibration_policy.policy_id, calibration_policy.policy_hash)),
        ("FREEZE_STRATEGY_POLICY", _reference_for("STRATEGY_SHADOW_POLICY", strategy.policy_id, strategy.policy_hash)),
        ("FREEZE_COST_POLICY", _reference_for("SHADOW_PORTFOLIO_POLICY", portfolio_policy.policy_id, portfolio_policy.policy_hash)),
        (
            "FREEZE_ENTRY_HOLDING_EXIT_POLICY",
            _reference_for("ENTRY_HOLDING_EXIT_QUALIFICATION_POLICY", entry_policy.policy_id, entry_policy.policy_hash),
        ),
    )
    for action, reference in owners:
        _record_phase_c_operator_audit(
            factory,
            action_kind=action,
            reference=reference,
            actor=actor,
            reason=reason,
            idempotency_key=f"{idempotency_key}:{action}",
        )
    return {
        "operation": "QUALIFICATION_TYPED_OWNERS_RECORD",
        "owners": [item.to_canonical_dict() for _action, item in owners],
        "production_authorized": False,
    }


def _reference_for(
    kind: str,
    artifact_id: ArtifactId,
    content_hash: str,
) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, artifact_id, content_hash)


def _record_phase_c_operator_audit(
    factory: PostgresConnectionFactory,
    *,
    action_kind: str,
    reference: ValidationArtifactReference,
    actor: str,
    reason: str,
    idempotency_key: str,
) -> None:
    command = {
        "schema_version": "phase-c-formal-operator-command/v1",
        "action_kind": action_kind,
        "result_reference": reference.to_canonical_dict(),
        "actor": actor,
        "reason": reason,
    }
    command_hash = canonical_hash(command)

    def operation(connection: Any) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"phase-c-formal-operator:{idempotency_key}",),
        )
        row = connection.execute(
            """
            SELECT command_hash, action_kind, result_artifact_id,
                   result_artifact_hash, actor, reason, payload_json
            FROM phase_c_formal_operator_command WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        ).fetchone()
        expected = (
            command_hash,
            action_kind,
            str(reference.artifact_id),
            reference.content_hash,
            actor,
            reason,
            command,
        )
        if row is not None:
            if tuple(row) != expected:
                raise ValueError("Phase C Formal operator idempotency conflict")
            return
        created_at = connection.execute("SELECT date_trunc('second', clock_timestamp())").fetchone()[0]
        connection.execute(
            """
            INSERT INTO phase_c_formal_operator_command(
                idempotency_key, command_hash, action_kind,
                result_artifact_id, result_artifact_hash,
                actor, reason, payload_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                idempotency_key,
                command_hash,
                action_kind,
                str(reference.artifact_id),
                reference.content_hash,
                actor,
                reason,
                Jsonb(command),
                created_at,
            ),
        )

    factory.run_transaction(operation)


def _instant(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("--at must be timezone-aware")
    if instant.microsecond:
        raise ValueError("--at must use whole-second precision")
    return instant


def _historical_runner(
    *,
    factory: PostgresConnectionFactory,
    journal: PostgresHistoricalResearchJournal,
    command: HistoricalResearchCommand,
    artifact_root: Path | None,
) -> HistoricalResearchRunner:
    archive_materializer = None
    if command.data_authority_mode is DataAuthorityMode.FREE_RESEARCH_ARCHIVE:
        if artifact_root is None:
            raise ValueError("FREE_RESEARCH_ARCHIVE Historical execution requires --artifact-root")
        component_repository = PostgresHistoricalMaterializationRepository(
            factory,
            apply_migrations=False,
        )
        base_materializer = HistoricalDecisionMaterializer(
            run_id=command.run_id,
            corpus_repository=PostgresHistoricalCorpusRepository(
                factory,
                artifact_root=artifact_root.resolve(),
                apply_migrations=False,
            ),
            component_repository=component_repository,
            universe_repository=PostgresFreeResearchUniverseRepository(factory, apply_migrations=False),
            scope_repository=PostgresRuntimeScopeRepository(factory, apply_migrations=False),
            target_repository=PostgresTargetOutcomeRepository(factory, apply_migrations=False),
            validation_repository=PostgresResearchValidationRepository(
                factory,
                apply_migrations=False,
            ),
            historical_facts_repository=PostgresHistoricalSecurityFactsRepository(factory, apply_migrations=False),
        )
        strategy_repository = PostgresMultiStrategyRepository(
            factory,
            apply_migrations=False,
        )
        strategy_repository.register(
            canonical_exploratory_strategy_registry(),
            created_at=command.created_at,
        )
        opportunity_authority = PostgresStrategyOpportunityAuthority(
            factory,
            apply_migrations=False,
        )
        archive_materializer = MultiStrategyHistoricalAdapter(
            delegate=base_materializer,
            component_repository=component_repository,
            strategy_repository=strategy_repository,
            parent_run_reference=RuntimeArtifactReference(
                "HISTORICAL_RESEARCH_RUN",
                command.run_id,
                command.command_hash,
            ),
            portfolio_policy=CrossStrategyPortfolioPolicy(
                maximum_gross_weight=Decimal("0.50"),
                maximum_symbol_weight=Decimal("0.20"),
            ),
            opportunity_resolver=PostgresHistoricalStrategyOpportunityResolver(
                opportunity_authority
            ),
            opportunity_authority=opportunity_authority,
        )
    return HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(
            PostgresHistoricalSessionOwner(
                factory,
                archive_materializer=archive_materializer,
                apply_migrations=False,
            )
        ),
    )


def _require_principal_actor(
    args: argparse.Namespace,
    payload: Mapping[str, Any],
) -> None:
    actor = payload.get("actor")
    if not isinstance(actor, str) or actor != args.principal_id:
        raise PermissionError("Formal operator actor must equal the authorized RBAC principal")


def _operational_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _authority_ceiling() -> dict[str, bool]:
    return {
        "entry_authority_granted": False,
        "broker_authority_granted": False,
        "daily_decision_window_summary_delivered": False,
    }


def _required_permission(args: argparse.Namespace) -> SecurityPermission:
    operation = str(args.operation)
    if operation in _READ_OPERATIONS:
        return SecurityPermission.READ_RESEARCH
    if operation in {
        "historical-security-facts-sync",
        "historical-universe-history-sync",
        "historical-universe-sync",
        "research-universe-sync",
        "runtime-scope-build",
        "historical-run",
        "historical-corpus-acquire",
    }:
        return SecurityPermission.RUN_RESEARCH
    if operation == "model-train":
        return SecurityPermission.RUN_RESEARCH
    if operation in {
        "qualification-protocol-record",
        "qualification-owners-record",
        "qualification-forecast-record",
        "qualification-evaluation-record",
        "qualification-historical",
        "qualification-oos",
        "qualification-calibration",
        "qualification-shadow",
        "qualification-status",
        "historical-evidence",
        "strategy-feedback-close",
    }:
        return SecurityPermission.RECORD_RESEARCH_EVIDENCE
    if operation in {"resume", "historical-resume"}:
        return SecurityPermission.RECOVER_RUNTIME
    if operation in {"prepare", "schedule", "reserve-due-tick", "run-due", "run-day"}:
        run_command = ContinuousResearchCommand.from_canonical_dict(_load_json_object(args.run_command))
        return _runtime_permission(run_command.authority_mode)
    if operation == "admit-tick":
        tick_command = RuntimeTickCommand.from_canonical_dict(_load_json_object(args.tick_command))
        return _runtime_permission(tick_command.authority_mode)
    return SecurityPermission.RUN_SHADOW


def _runtime_permission(mode: RuntimeAuthorityMode) -> SecurityPermission:
    if mode is RuntimeAuthorityMode.RESEARCH:
        return SecurityPermission.RUN_RESEARCH
    if mode is RuntimeAuthorityMode.SHADOW:
        return SecurityPermission.RUN_SHADOW
    raise PermissionError("Free-data Continuous CLI cannot authorize Production Runtime mutations")


def _operator_resource(args: argparse.Namespace) -> ValidationArtifactReference:
    omitted = {
        "approval_decision_id",
        "application_schema",
        "artifact_root",
        "database_url",
        "output_root",
        "principal_id",
    }
    arguments: dict[str, Any] = {}
    for name, value in sorted(vars(args).items()):
        if name in omitted or value is None:
            continue
        if isinstance(value, Path):
            if value.suffix.lower() == ".json" and value.is_file():
                arguments[name] = _load_json_object(value)
            continue
        arguments[name] = _canonical_operator_argument(value)
    payload = {
        "schema_version": "continuous-operator-resource/v1",
        "operation": str(args.operation),
        "arguments": arguments,
    }
    digest = canonical_hash(payload)
    return ValidationArtifactReference(
        "CONTINUOUS_OPERATOR_OPERATION",
        ArtifactId(f"continuous-operator:{digest[7:]}"),
        digest,
    )


def _canonical_operator_argument(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _canonical_operator_argument(item) for name, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_operator_argument(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported Continuous operator argument type: {type(value).__name__}")


def _historical_snapshot_payload(
    operation: str,
    snapshot: HistoricalRunSnapshot,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "run_id": str(snapshot.command.run_id),
        "command_hash": snapshot.command.command_hash,
        "status": snapshot.status.value,
        "version": snapshot.version,
        "session_count": len(snapshot.sessions),
        "completed_sessions": snapshot.completed_sessions,
        "sessions": [
            {
                "session_id": str(item.request.session_id),
                "session_hash": item.request.session_hash,
                "trading_date": item.request.trading_date.isoformat(),
                "ordinal": item.ordinal,
                "status": item.status.value,
                "next_stage": item.next_stage.value,
                "version": item.version,
                "fencing_token": item.fencing_token,
                "receipts": [receipt.to_canonical_dict() for receipt in item.receipts],
            }
            for item in snapshot.sessions
        ],
        "evidence_qualification": snapshot.command.evidence_qualification.value,
        "limitations": list(snapshot.command.limitations),
        "formal_oos": False,
        "calibrated": False,
        **_authority_ceiling(),
    }


def _emit(payload: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _emit_error(reason_code: str, exc: BaseException) -> None:
    _emit(
        {
            "status": "FAILED",
            "reason_code": reason_code,
            "error_type": type(exc).__name__,
            "message": "Continuous Research command failed; credentials are redacted",
            **_authority_ceiling(),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
