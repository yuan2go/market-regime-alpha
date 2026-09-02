"""Sole target composition root and explicit schema-operator boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from market_regime_alpha.infrastructure.artifacts import LocalArtifactStore
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.market_uow import (
    PostgresMarketDatabaseClock,
    PostgresMarketUnitOfWorkProvider,
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
from market_regime_alpha.infrastructure.postgres.selection_uow import (
    PostgresSelectionUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.research_uow import (
    PostgresResearchUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.target_uow import (
    PostgresTargetUnitOfWorkProvider,
)
from market_regime_alpha.infrastructure.postgres.queries import (
    PostgresCandidateQueryProvider,
    PostgresCandidateResearchInputLoader,
    PostgresDecisionInputPreparationProvider,
    PostgresDecisionRunQueryProvider,
    PostgresMarketQueryProvider,
    PostgresOutcomeInputPreparationProvider,
    PostgresOutcomeQueryProvider,
    PostgresOutcomeVerificationProvider,
    PostgresResearchEvaluationVerificationProvider,
    PostgresResearchQualificationAdmissionReadPort,
    PostgresResearchQualificationVerificationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_context_inputs import (
    PostgresContextInputPreparationProvider,
    PostgresContextQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import (
    PostgresInferenceInputPreparationProvider,
    PostgresInferenceQueryProvider,
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
from market_regime_alpha.infrastructure.postgres.schema import (
    DatabaseIdentity,
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
    OpportunityCommands,
    PortfolioCommands,
    RiskCommands,
    StrategyCommands,
)
from market_regime_alpha.outcome.application import OutcomeApplication, OutcomeVerifier
from market_regime_alpha.outcome.ports import OutcomeReadPort
from market_regime_alpha.research_qualification.application import (
    AssessmentCommands,
    EvaluationCommands,
    EvidenceCommands,
    ExperimentCommands,
    ResearchPartitionCommands,
    ResearchEvaluationVerifier,
    ResearchQualificationApplication,
    ResearchQualificationVerifier,
    QualificationCommands,
)
from market_regime_alpha.research_qualification.ports import (
    ResearchQualificationAdmissionReadPort,
)
from market_regime_alpha.selection.application import (
    CandidateApplication,
    SelectionApplication,
)
from market_regime_alpha.selection.ports import CandidateQueryProvider
from market_regime_alpha.market.application import MarketApplication
from market_regime_alpha.market.ports import MarketQueryProvider


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
    runtime: RuntimeApplication
    artifacts: ArtifactApplication
    market: MarketApplication
    market_queries: MarketQueryProvider
    selection: SelectionApplication
    research_definitions: ResearchQualificationApplication
    research_partitions: ResearchPartitionCommands
    research_experiments: ExperimentCommands
    research_evaluations: EvaluationCommands
    research_evaluation_verifier: ResearchEvaluationVerifier
    research_evidence: EvidenceCommands
    research_assessments: AssessmentCommands
    research_qualifications: QualificationCommands
    research_qualification_admissions: ResearchQualificationAdmissionReadPort
    research_qualification_verifier: ResearchQualificationVerifier
    candidates: CandidateApplication
    candidate_queries: CandidateQueryProvider
    decision_support: DecisionSupportApplication
    decision_contexts: ContextCommands
    decision_strategies: StrategyCommands
    decision_inference: InferenceCommands
    decision_opportunities: OpportunityCommands
    decision_portfolios: PortfolioCommands
    decision_risk: RiskCommands
    decision_support_verifier: DecisionRunVerifier
    outcomes: OutcomeApplication
    outcome_queries: OutcomeReadPort
    outcome_verifier: OutcomeVerifier
    _pool: TargetPostgresPool

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
    byte_store = LocalArtifactStore(settings.artifact_root)
    return TargetApplication(
        runtime=RuntimeApplication(uow_provider),
        artifacts=ArtifactApplication(byte_store, uow_provider),
        market=MarketApplication(
            byte_store,
            PostgresMarketUnitOfWorkProvider(pool),
            PostgresMarketDatabaseClock(pool),
        ),
        market_queries=PostgresMarketQueryProvider(pool),
        selection=SelectionApplication(PostgresSelectionUnitOfWorkProvider(pool)),
        research_definitions=ResearchQualificationApplication(
            byte_store,
            PostgresResearchUnitOfWorkProvider(pool),
            PostgresTargetUnitOfWorkProvider(pool),
        ),
        research_partitions=ResearchPartitionCommands(
            PostgresPartitionUnitOfWorkProvider(pool, id_factory=uuid4),
            id_factory=uuid4,
        ),
        research_experiments=ExperimentCommands(
            PostgresExperimentUnitOfWorkProvider(pool),
            id_factory=uuid4,
        ),
        research_evaluations=EvaluationCommands(
            PostgresEvaluationUnitOfWorkProvider(pool, id_factory=uuid4),
            id_factory=uuid4,
        ),
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
        candidates=CandidateApplication(
            PostgresCandidateResearchInputLoader(pool, byte_store),
            PostgresCandidateUnitOfWorkProvider(pool),
        ),
        candidate_queries=PostgresCandidateQueryProvider(pool),
        decision_support=DecisionSupportApplication(
            PostgresDecisionInputPreparationProvider(pool),
            PostgresDecisionSupportUnitOfWorkProvider(pool),
            PostgresDecisionRunQueryProvider(pool),
        ),
        decision_contexts=ContextCommands(
            PostgresContextInputPreparationProvider(pool),
            PostgresContextUnitOfWorkProvider(pool),
            PostgresContextQueryProvider(pool),
        ),
        decision_strategies=StrategyCommands(
            PostgresStrategyUnitOfWorkProvider(pool),
            PostgresStrategyQueryProvider(pool),
        ),
        decision_inference=InferenceCommands(
            PostgresInferenceInputPreparationProvider(pool),
            PostgresInferenceUnitOfWorkProvider(pool),
            PostgresInferenceQueryProvider(pool),
        ),
        decision_opportunities=OpportunityCommands(
            PostgresOpportunityInputPreparationProvider(pool),
            PostgresOpportunityUnitOfWorkProvider(pool),
            PostgresOpportunityQueryProvider(pool),
        ),
        decision_portfolios=PortfolioCommands(
            PostgresPortfolioInputPreparationProvider(pool),
            PostgresPortfolioUnitOfWorkProvider(pool),
            PostgresPortfolioQueryProvider(pool),
        ),
        decision_risk=RiskCommands(
            PostgresRiskInputPreparationProvider(pool),
            PostgresRiskUnitOfWorkProvider(pool),
            PostgresRiskQueryProvider(pool),
        ),
        decision_support_verifier=DecisionRunVerifier(PostgresDecisionRunVerificationProvider(pool)),
        outcomes=OutcomeApplication(
            PostgresOutcomeInputPreparationProvider(pool),
            PostgresOutcomeUnitOfWorkProvider(pool),
            PostgresOutcomeQueryProvider(pool),
        ),
        outcome_queries=PostgresOutcomeQueryProvider(pool),
        outcome_verifier=OutcomeVerifier(
            PostgresOutcomeQueryProvider(pool),
            PostgresOutcomeVerificationProvider(pool),
        ),
        _pool=pool,
    )


def bootstrap_database(settings: TargetSettings) -> SchemaVerification:
    """Explicit DDL command; never called by ordinary application startup."""

    return SchemaManager(settings.database_url).bootstrap()


def verify_database(settings: TargetSettings) -> SchemaVerification:
    return SchemaManager(settings.database_url).verify()


def database_identity(settings: TargetSettings) -> DatabaseIdentity:
    return SchemaManager(settings.database_url).database_identity()


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
    "apply_database_recreate",
    "bootstrap_application",
    "bootstrap_database",
    "database_identity",
    "load_recreate_plan",
    "make_recreate_authorization",
    "plan_database_recreate",
    "verify_database",
]
