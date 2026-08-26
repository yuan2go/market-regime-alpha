from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from market_regime_alpha.application.historical_corpus.correctness_failures import (
    AlphaCorrectnessFailureDetail,
    AlphaCorrectnessFailureIndex,
    FailureSourceBinding,
)
from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    HistoricalResearchEvidence,
    ResearchFinding,
)
from market_regime_alpha.application.historical_corpus.frozen_experiment import (
    create_golden_loop_v2_historical_experiment,
)
from market_regime_alpha.application.historical_corpus.postgres_correctness_failures import (
    PostgresAlphaCorrectnessFailureRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.target_semantics import (
    BarrierOrderingOutcome,
    TargetSemanticResult,
    TargetSemanticStatus,
    wp_alpha_correctness_02_target_semantic_specification,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.postgres_repository import (
    PostgresResearchValidationRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from market_regime_alpha.universe.runtime_scope import (
    UniversePolicySelector,
    UniverseScopeKind,
    build_research_universe_policy,
)
from tests.application.historical_corpus.support import normalized_owner, raw_owner


NOW = datetime(2026, 8, 26, 3, tzinfo=UTC)
DECISION_SESSION = date(2023, 1, 3)
TARGET_SESSION = date(2023, 1, 4)


def test_failure_index_is_idempotent_owner_verified_and_reloadable(
    postgres_factory: PostgresConnectionFactory,
    tmp_path: Path,
) -> None:
    corpus = PostgresHistoricalCorpusRepository(
        postgres_factory,
        artifact_root=tmp_path / "artifact-root",
    )
    raw = raw_owner()
    normalized = normalized_owner(raw)
    corpus.publish_and_register(raw)
    corpus.publish_and_register(normalized)
    target_protocol = PostgresTargetOutcomeRepository(
        postgres_factory
    ).register_protocol(
        exploratory_five_minute_multi_horizon_protocol(),
        recorded_at=NOW,
    )
    experiment = create_golden_loop_v2_historical_experiment(
        target_protocol,
        locked_at=NOW,
    )
    PostgresResearchValidationRepository(
        postgres_factory
    ).record_historical_experiment_definition(experiment, recorded_at=NOW)
    scope = PostgresRuntimeScopeRepository(postgres_factory).register_policy(
        build_research_universe_policy(
            policy_version="correctness-failure-test/v1",
            selectors=(
                UniversePolicySelector(
                    kind=UniverseScopeKind.INDEX,
                    selector_id="CORRECTNESS_FAILURE_TEST",
                    symbols=(),
                ),
            ),
            minimum_history_sessions=1,
            minimum_median_daily_amount=Decimal("1"),
            include_st=False,
            require_tradable=True,
            lot_size=100,
            data_authority="FREE_RESEARCH_ARCHIVE_PIT_INCOMPLETE",
        )
    )
    calendar_hash = canonical_hash({"calendar": "correctness-failure-test"})
    command = HistoricalResearchCommand.create(
        idempotency_key="correctness-failure-repository-test",
        start_date=DECISION_SESSION,
        end_date=DECISION_SESSION,
        trading_sessions=(DECISION_SESSION,),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        trading_calendar_id=ArtifactId("correctness-failure-calendar"),
        trading_calendar_hash=calendar_hash,
        runtime_scope_policy_id=scope.policy_id,
        runtime_scope_policy_hash=scope.policy_hash,
        decision_policy_id=ArtifactId("correctness-failure-decision-policy"),
        decision_policy_hash=canonical_hash(
            {"decision": "correctness-failure-test"}
        ),
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ),
        experiment_definition_reference=ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            experiment.definition_id,
            experiment.definition_hash,
        ),
        configuration_references=(normalized.reference,),
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        evidence_qualification=(
            EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE
        ),
        code_revision="correctness-failure-test",
        created_at=NOW,
    )
    PostgresHistoricalResearchJournal(postgres_factory).create_or_get(command)
    evidence = PostgresHistoricalEvidenceRepository(postgres_factory).put(
        HistoricalResearchEvidence.create(
            run_id=command.run_id,
            command_hash=command.command_hash,
            experiment_reference=command.experiment_definition_reference,
            evidence_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
            research_question="Can the predecessor Target be reproduced?",
            classification=ResearchFinding.NEGATIVE,
            rationale="The legacy checker rejected one Target source path.",
            source_references=(raw.reference, normalized.reference),
            metrics=(),
            payload={"status": "CORRECTNESS_FAILED"},
            created_at=NOW,
        )
    )
    index = _failure_index(
        command=command,
        evidence=evidence,
        raw_reference=raw.reference,
        normalized_reference=normalized.reference,
    )
    repository = PostgresAlphaCorrectnessFailureRepository(postgres_factory)

    first = repository.put(index)
    repeated = repository.put(index)

    assert repeated == first == index
    assert repository.get(index.index_id) == index
    assert repository.get_for_source(
        run_id=command.run_id,
        evidence_id=evidence.evidence_id,
        semantic_revision=index.semantic_revision,
    ) == index


def _failure_index(
    *,
    command: HistoricalResearchCommand,
    evidence: HistoricalResearchEvidence,
    raw_reference: ValidationArtifactReference,
    normalized_reference: ValidationArtifactReference,
) -> AlphaCorrectnessFailureIndex:
    specification = wp_alpha_correctness_02_target_semantic_specification()
    decision_time = datetime.combine(
        DECISION_SESSION, time(14, 55), UTC
    )
    outcome_start = datetime.combine(TARGET_SESSION, time(1, 30), UTC)
    outcome_end = datetime.combine(TARGET_SESSION, time(2, 30), UTC)
    result = TargetSemanticResult(
        semantic_specification=specification.reference,
        symbol="600000.SH",
        decision_time=decision_time,
        target_session=TARGET_SESSION,
        outcome_window_start=outcome_start,
        outcome_window_end=outcome_end,
        expected_outcome_bar_count=12,
        observed_outcome_bar_count=0,
        decision_reference_status=TargetSemanticStatus.UNAVAILABLE,
        outcome_window_status=TargetSemanticStatus.UNAVAILABLE,
        checkpoint_observation_status=TargetSemanticStatus.UNAVAILABLE,
        checkpoint_return_status=TargetSemanticStatus.UNAVAILABLE,
        mfe_status=TargetSemanticStatus.UNAVAILABLE,
        mae_status=TargetSemanticStatus.UNAVAILABLE,
        barrier_status=TargetSemanticStatus.UNAVAILABLE,
        decision_reference_price=None,
        checkpoint_price=None,
        checkpoint_return=None,
        mfe=None,
        mae=None,
        barrier_passages=(),
        barrier_ordering=BarrierOrderingOutcome.NOT_APPLICABLE,
        decision_source_references=(),
        outcome_source_references=(),
        diagnostic_source_references=(),
        reason_codes=("SOURCE_BAR_UNAVAILABLE",),
    )
    label_reference = ValidationArtifactReference(
        "TARGET_OUTCOME_LABEL",
        ArtifactId("correctness-failure-predecessor-label"),
        canonical_hash({"label": "correctness-failure-predecessor"}),
    )
    component_reference = ValidationArtifactReference(
        "HISTORICAL_SESSION_COMPONENT",
        ArtifactId("correctness-failure-predecessor-component"),
        canonical_hash({"component": "correctness-failure-predecessor"}),
    )
    detail = AlphaCorrectnessFailureDetail.create(
        decision_session=DECISION_SESSION,
        decision_time=decision_time,
        target_session=TARGET_SESSION,
        target_window_end=outcome_end,
        symbol="600000.SH",
        classification="PREDECESSOR_CORRECTNESS_FAILURE",
        discrepancy_code="PERSISTED_TARGET_SOURCE_NOT_REPRODUCIBLE",
        predecessor_label_reference=label_reference,
        predecessor_component_reference=component_reference,
        predecessor_availability_status="AVAILABLE",
        predecessor_decision_reference_price=None,
        predecessor_checkpoint_price=None,
        predecessor_checkpoint_return=None,
        predecessor_mfe=None,
        predecessor_mae=None,
        materializer_result=result,
        checker_result=result,
        source_bindings=(
            FailureSourceBinding("NORMALIZED_OWNER", normalized_reference),
        ),
        normalization_revision="baostock-historical-normalization/v1",
        semantic_revision=specification.semantic_revision,
        analysis_code_sha="a" * 40,
    )
    return AlphaCorrectnessFailureIndex.create(
        source_run_reference=ValidationArtifactReference(
            "HISTORICAL_RESEARCH_RUN",
            command.run_id,
            command.command_hash,
        ),
        source_evidence_reference=evidence.reference,
        experiment_reference=command.experiment_definition_reference,
        target_protocol_reference=command.target_protocol_reference,
        calendar_reference=ValidationArtifactReference(
            "TRADING_CALENDAR",
            command.trading_calendar_id,
            command.trading_calendar_hash,
        ),
        raw_owner_reference=raw_reference,
        normalized_owner_reference=normalized_reference,
        normalization_revision="baostock-historical-normalization/v1",
        analysis_code_sha="a" * 40,
        semantic_revision=specification.semantic_revision,
        details=(detail,),
        created_at=NOW,
    )
