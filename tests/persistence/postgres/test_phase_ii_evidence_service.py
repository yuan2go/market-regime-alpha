from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalEvidenceKind,
    ResearchFinding,
    ResearchStatement,
    ResearchStatementKind,
)
from market_regime_alpha.application.historical_corpus.phase_ii_service import (
    HistoricalPhaseIIResearchService,
    PhaseIIEvidenceWrite,
)
from market_regime_alpha.application.historical_corpus.postgres_evidence import (
    PostgresHistoricalEvidenceRepository,
)
from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_evaluation.postgres_target_repository import (
    PostgresTargetOutcomeRepository,
)
from market_regime_alpha.application.research_evaluation.targets import (
    exploratory_five_minute_multi_horizon_protocol,
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


NOW = datetime(2026, 8, 21, tzinfo=UTC)


def _ref(kind: str, identity: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(identity),
        canonical_hash({"kind": kind, "identity": identity}),
    )


def test_phase_ii_service_persists_and_reloads_through_existing_evidence_owner(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    experiment = _ref("RESEARCH_EXPERIMENT_DEFINITION", "phase-ii-experiment")
    scope_policy = PostgresRuntimeScopeRepository(postgres_factory).register_policy(
        build_research_universe_policy(
            policy_version="phase-ii-test/v1",
            selectors=(
                UniversePolicySelector(
                    kind=UniverseScopeKind.INDEX,
                    selector_id="phase-ii-test-scope",
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
    target_protocol = PostgresTargetOutcomeRepository(
        postgres_factory
    ).register_protocol(
        exploratory_five_minute_multi_horizon_protocol(), recorded_at=NOW
    )
    command = HistoricalResearchCommand.create(
        idempotency_key="phase-ii-evidence-service-test",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 20),
        trading_sessions=(date(2026, 8, 20),),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        trading_calendar_id=ArtifactId("phase-ii-calendar"),
        trading_calendar_hash=canonical_hash({"calendar": "phase-ii"}),
        runtime_scope_policy_id=scope_policy.policy_id,
        runtime_scope_policy_hash=scope_policy.policy_hash,
        decision_policy_id=ArtifactId("phase-ii-decision-policy"),
        decision_policy_hash=canonical_hash({"decision": "phase-ii"}),
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            target_protocol.protocol_id,
            target_protocol.protocol_hash,
        ),
        experiment_definition_reference=experiment,
        configuration_references=(
            _ref("NORMALIZED_DATASET", "phase-ii-dataset"),
        ),
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        evidence_qualification=EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE,
        code_revision="phase-ii-test",
        created_at=NOW,
    )
    PostgresHistoricalResearchJournal(postgres_factory).create_or_get(command)
    repository = PostgresHistoricalEvidenceRepository(postgres_factory)
    service = HistoricalPhaseIIResearchService(repository)
    write = PhaseIIEvidenceWrite(
        run_id=command.run_id,
        command_hash=command.command_hash,
        experiment_reference=experiment,
        evidence_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
        research_question="Can source values be independently reproduced?",
        classification=ResearchFinding.INCONCLUSIVE,
        rationale="Physical package is not available in this targeted PG test.",
        source_references=command.configuration_references,
        metrics=(),
        payload={"status": "INCONCLUSIVE"},
        created_at=NOW,
        statements=(
            ResearchStatement(
                ResearchStatementKind.FACT,
                "The Evidence was written through the existing PostgreSQL owner.",
            ),
        ),
    )

    first = service.persist(write)
    repeated = service.persist(write)

    with pytest.raises(ValueError, match="typed correctness proof"):
        service.persist(
            replace(write, payload={"status": "CORRECTNESS_SUPPORTED"})
        )

    assert repeated == first
    assert service.load_evidence(
        first.evidence_id,
        expected_kind=HistoricalEvidenceKind.ALPHA_CORRECTNESS,
    ) == first
    assert repository.list_for_run(command.run_id) == (first,)
