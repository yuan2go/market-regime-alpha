from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

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
    ProviderAttemptStatus,
)
from market_regime_alpha.application.continuous_research.policy import (
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)
from market_regime_alpha.application.continuous_research.postgres_journal import (
    ContinuousResearchClaimRejected,
    PostgresContinuousResearchJournal,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


NOW = datetime(2026, 8, 6, 6, 40, tzinfo=timezone.utc)
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
HASH_3 = "sha256:" + "3" * 64


def _command() -> ContinuousResearchCommand:
    policy = default_continuous_decision_window_policy()
    return ContinuousResearchCommand.create(
        idempotency_key="continuous-evidence-isolation",
        trading_date=date(2026, 8, 6),
        requested_symbols=("600000.SH",),
        trading_calendar_id=ArtifactId("calendar-fixture"),
        trading_calendar_hash=HASH_1,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        provider_configuration_id=ArtifactId("provider-config"),
        provider_configuration_hash=HASH_1,
        research_configuration_id=ArtifactId("research-config"),
        research_configuration_hash=HASH_2,
        code_revision="baseline-head",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def _tick(command: ContinuousResearchCommand, index: int) -> RuntimeTickCommand:
    return RuntimeTickCommand.create(
        idempotency_key=f"evidence-tick-{index}",
        run_id=command.run_id,
        trading_date=command.trading_date,
        observed_at=NOW + timedelta(minutes=index),
        request_scope_hash=command.request_scope_hash,
        provider_configuration_id=command.provider_configuration_id,
        provider_configuration_hash=command.provider_configuration_hash,
        research_configuration_id=command.research_configuration_id,
        research_configuration_hash=command.research_configuration_hash,
    )


def _success_outcome() -> ProviderAttemptOutcome:
    return ProviderAttemptOutcome.create(
        status=ProviderAttemptStatus.SUCCEEDED,
        completed_at=NOW,
        raw_response_hash=HASH_2,
        source_manifest_id=ArtifactId("source-manifest-valid"),
        source_manifest_hash=HASH_3,
        error_code=None,
        error_message=None,
        reason_codes=("VALIDATED_RESPONSE",),
        retry_at=None,
    )


def _evidence(attempt) -> EvidenceCommit:
    return EvidenceCommit.create(
        attempt=attempt,
        evidence_scope="A_SHARE_MINUTE_SCOPE",
        trading_date=date(2026, 8, 6),
        request_scope_hash=HASH_1,
        raw_artifact_id=ArtifactId("raw-valid"),
        raw_artifact_hash=HASH_2,
        evidence_artifact_id=ArtifactId("evidence-valid"),
        evidence_artifact_hash=HASH_3,
        material_identity_hash=HASH_3,
        provider_configuration_id=ArtifactId("provider-config"),
        provider_configuration_hash=HASH_1,
        effective_at=NOW,
        retrieved_at=NOW,
        available_at=NOW,
        as_of_time=NOW,
        quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
        evidence_qualification="FREE_DATA_EXPLORATORY",
        limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
    )


def _start(journal, command, index):
    tick = journal.admit_tick(
        _tick(command, index),
        session_phase=ContinuousSessionPhase.AFTERNOON_SESSION,
    )
    claim = journal.claim_tick(run_id=command.run_id, tick_id=tick.command.tick_id)
    return journal.start_provider_attempt(
        claim=claim,
        provider_id="tencent-public",
        product="a-share-minute",
        request_hash=HASH_1,
        provider_revision="fixture-v1",
    )


def test_failed_attempts_never_replace_last_valid_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    journal = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    command = _command()
    journal.create_or_get(command)
    started = _start(journal, command, 0)
    succeeded = journal.complete_provider_attempt(
        claim=started.claim,
        attempt_id=started.attempt.attempt_id,
        outcome=_success_outcome(),
    )
    committed = journal.commit_evidence(
        claim=started.claim,
        attempt=succeeded,
        evidence=_evidence(succeeded),
    )
    baseline = committed.current

    for index, status in enumerate(
        (
            ProviderAttemptStatus.FAILED,
            ProviderAttemptStatus.TIMED_OUT,
            ProviderAttemptStatus.INVALID_RESPONSE,
            ProviderAttemptStatus.RATE_LIMITED,
            ProviderAttemptStatus.CIRCUIT_OPEN,
        ),
        start=1,
    ):
        later = _start(journal, command, index)
        journal.complete_provider_attempt(
            claim=later.claim,
            attempt_id=later.attempt.attempt_id,
            outcome=ProviderAttemptOutcome.create(
                status=status,
                completed_at=NOW,
                raw_response_hash=HASH_2 if status is ProviderAttemptStatus.INVALID_RESPONSE else None,
                source_manifest_id=None,
                source_manifest_hash=None,
                error_code=status.value,
                error_message="provider attempt failed",
                reason_codes=(status.value,),
                retry_at=None,
            ),
        )
        assert journal.get_current_evidence(
            command.run_id, "A_SHARE_MINUTE_SCOPE"
        ) == baseline

    restarted = PostgresContinuousResearchJournal(postgres_factory, clock=lambda: NOW)
    assert restarted.get_current_evidence(
        command.run_id, "A_SHARE_MINUTE_SCOPE"
    ) == baseline


def test_expired_claim_cannot_finish_attempt_or_commit_evidence(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    current = NOW

    def clock() -> datetime:
        return current

    journal = PostgresContinuousResearchJournal(
        postgres_factory,
        clock=clock,
        lease_duration=timedelta(seconds=10),
    )
    command = _command()
    journal.create_or_get(command)
    started = _start(journal, command, 0)
    current += timedelta(seconds=11)
    journal.resume(command.run_id)

    with pytest.raises(ContinuousResearchClaimRejected, match="fencing"):
        journal.complete_provider_attempt(
            claim=started.claim,
            attempt_id=started.attempt.attempt_id,
            outcome=_success_outcome(),
        )
