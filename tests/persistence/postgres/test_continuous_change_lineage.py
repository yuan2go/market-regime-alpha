from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from market_regime_alpha.application.continuous_research.change_detection import (
    ChangeDecision,
)
from market_regime_alpha.application.continuous_research.children import (
    ContinuousChildReference,
)
from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
    RuntimeTickCommand,
)
from market_regime_alpha.application.continuous_research.evidence import (
    EvidenceCommit,
    EvidenceQualityStatus,
    ProviderAttemptOutcome,
)
from market_regime_alpha.application.continuous_research.journal import (
    ChildReferenceDisposition,
    ChangeDecisionType,
    ContinuousChildKind,
    ProviderAttemptStatus,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    ContinuousResearchConflict,
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 6, 6, 50, tzinfo=timezone.utc)
HASHES = tuple("sha256:" + character * 64 for character in "123456789abcdef")


def _command() -> ContinuousResearchCommand:
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key="continuous-change-lineage",
        trading_date=date(2026, 8, 6),
        requested_symbols=("600000.SH",),
        trading_calendar_id=ArtifactId("calendar-change"),
        trading_calendar_hash=HASHES[0],
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("provider-config-change"),
        provider_configuration_hash=HASHES[1],
        research_configuration_id=ArtifactId("research-config-change"),
        research_configuration_hash=HASHES[2],
        code_revision="baseline-head",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def _commit(
    journal: PostgresContinuousResearchJournal,
    command: ContinuousResearchCommand,
    *,
    index: int,
    material_hash: str,
):
    tick_command = RuntimeTickCommand.create(
        idempotency_key=f"change-tick-{index}",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=NOW + timedelta(minutes=index),
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )
    tick = journal.admit_tick(
        tick_command, session_phase=ContinuousSessionPhase.DECISION_WINDOW
    )
    claim = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)
    started = journal.start_provider_attempt(
        claim=claim,
        provider_id="tencent-public",
        product="a-share-minute",
        request_hash=HASHES[0],
        provider_revision="fixture-v1",
    )
    attempt = journal.complete_provider_attempt(
        claim=started.claim,
        attempt_id=started.attempt.attempt_id,
        outcome=ProviderAttemptOutcome.create(
            status=ProviderAttemptStatus.SUCCEEDED,
            completed_at=NOW,
            raw_response_hash=HASHES[3],
            source_manifest_id=ArtifactId(f"manifest-change-{index}"),
            source_manifest_hash=HASHES[4],
            error_code=None,
            error_message=None,
            reason_codes=("VALIDATED_RESPONSE",),
            retry_at=None,
        ),
    )
    evidence = EvidenceCommit.create(
        attempt=attempt,
        evidence_scope="A_SHARE_MINUTE_SCOPE",
        trading_date=command.trading_date,
        request_scope_hash=command.request_scope_hash,
        raw_artifact_id=ArtifactId(f"raw-change-{index}"),
        raw_artifact_hash=HASHES[3],
        evidence_artifact_id=ArtifactId(f"evidence-change-{index}"),
        evidence_artifact_hash=HASHES[5],
        material_identity_hash=material_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        effective_at=NOW,
        retrieved_at=NOW,
        available_at=NOW,
        as_of_time=NOW,
        quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
        evidence_qualification="FREE_DATA_EXPLORATORY",
        limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
    )
    committed = journal.commit_evidence(
        claim=started.claim, attempt=attempt, evidence=evidence
    )
    return tick, committed.claim, committed.evidence


def _child(
    *,
    tick_sequence: int,
    evidence: EvidenceCommit,
    decision: ChangeDecision,
    disposition: ChildReferenceDisposition,
) -> ContinuousChildReference:
    return ContinuousChildReference.create(
        trading_date=evidence.trading_date,
        run_id=evidence.run_id,
        tick_id=evidence.tick_id,
        tick_sequence=tick_sequence,
        provider_attempt_id=evidence.attempt_id,
        source_manifest_id=evidence.source_manifest_id,
        source_manifest_hash=evidence.source_manifest_hash,
        evidence_commit_id=evidence.evidence_commit_id,
        evidence_commit_hash=evidence.commit_hash,
        decision_id=decision.decision_id,
        decision_hash=decision.decision_hash,
        child_kind=ContinuousChildKind.FEATURE_MATERIALIZATION,
        reference_disposition=disposition,
        child_run_id=ArtifactId("existing-feature-run"),
        child_receipt_id=ArtifactId("existing-feature-receipt"),
        child_receipt_hash=HASHES[6],
        child_artifact_id=ArtifactId("existing-feature-artifact"),
        child_artifact_hash=HASHES[7],
        input_references=(
            RuntimeArtifactReference(
                "EVIDENCE_COMMIT", evidence.evidence_commit_id, evidence.commit_hash
            ),
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "RESEARCH_CONFIGURATION",
                ArtifactId("research-config-change"),
                HASHES[2],
            ),
        ),
        created_at=NOW,
    )


def test_change_decision_and_child_reuse_survive_restart(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)

    first_tick, first_claim, first_evidence = _commit(
        journal, command, index=0, material_hash=HASHES[8]
    )
    initial = ChangeDecision.create(
        evidence=first_evidence,
        previous_evidence=None,
        downstream_contract_satisfied=True,
        created_at=NOW,
    )
    first_recorded = journal.record_change_decision(
        claim=first_claim, decision=initial
    )
    created = _child(
        tick_sequence=first_tick.tick_sequence,
        evidence=first_evidence,
        decision=initial,
        disposition=ChildReferenceDisposition.CREATED,
    )
    journal.record_child_reference(claim=first_recorded.claim, reference=created)

    _, second_claim, second_evidence = _commit(
        journal, command, index=1, material_hash=HASHES[8]
    )
    no_change = ChangeDecision.create(
        evidence=second_evidence,
        previous_evidence=first_evidence,
        downstream_contract_satisfied=True,
        created_at=NOW,
    )
    second_recorded = journal.record_change_decision(
        claim=second_claim, decision=no_change
    )
    reused = _child(
        tick_sequence=2,
        evidence=second_evidence,
        decision=no_change,
        disposition=ChildReferenceDisposition.REUSED,
    )
    journal.record_child_reference(claim=second_recorded.claim, reference=reused)

    restarted = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    assert restarted.get_change_decision(no_change.decision_id) == no_change
    assert restarted.get_child_references(command.run_id, second_evidence.tick_id) == (
        reused,
    )
    assert no_change.decision_type is ChangeDecisionType.NO_MATERIAL_CHANGE


def test_change_decision_rejects_fabricated_previous_lineage(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    _, claim, evidence = _commit(
        journal, command, index=0, material_hash=HASHES[8]
    )
    attempt = journal.get_provider_attempt(evidence.attempt_id)
    fabricated_previous = EvidenceCommit.create(
        attempt=attempt,
        evidence_scope=evidence.evidence_scope,
        trading_date=evidence.trading_date,
        request_scope_hash=evidence.request_scope_hash,
        raw_artifact_id=ArtifactId("fabricated-raw"),
        raw_artifact_hash=HASHES[3],
        evidence_artifact_id=ArtifactId("fabricated-evidence"),
        evidence_artifact_hash=HASHES[5],
        material_identity_hash=HASHES[9],
        provider_configuration_id=evidence.provider_configuration_id,
        provider_configuration_hash=evidence.provider_configuration_hash,
        effective_at=NOW,
        retrieved_at=NOW,
        available_at=NOW,
        as_of_time=NOW,
        quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
        evidence_qualification="FREE_DATA_EXPLORATORY",
        limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
    )
    fabricated = ChangeDecision.create(
        evidence=evidence,
        previous_evidence=fabricated_previous,
        downstream_contract_satisfied=True,
        created_at=NOW,
    )

    with pytest.raises(ContinuousResearchConflict, match="previous Evidence"):
        journal.record_change_decision(claim=claim, decision=fabricated)
