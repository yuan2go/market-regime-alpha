from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from market_regime_alpha.application.continuous_research.evidence import (
    EvidenceCommit,
    EvidenceQualityStatus,
    ProviderAttemptOutcome,
    ProviderAttemptSnapshot,
)
from market_regime_alpha.application.continuous_research.journal import (
    ProviderAttemptStatus,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 6, 6, 42, tzinfo=timezone.utc)
HASH_1 = "sha256:" + "1" * 64
HASH_2 = "sha256:" + "2" * 64
HASH_3 = "sha256:" + "3" * 64


def _attempt(
    status: ProviderAttemptStatus = ProviderAttemptStatus.SUCCEEDED,
) -> ProviderAttemptSnapshot:
    return ProviderAttemptSnapshot(
        attempt_id=1,
        run_id=ArtifactId("continuous-run-fixture"),
        tick_id=ArtifactId("continuous-tick-fixture"),
        attempt_number=1,
        claim_id="claim-fixture",
        fencing_token=1,
        tick_version=3,
        provider_id="tencent-public",
        product="a-share-minute",
        request_hash=HASH_1,
        started_at=NOW,
        completed_at=NOW if status is not ProviderAttemptStatus.STARTED else None,
        lease_expires_at=NOW.replace(second=30),
        heartbeat_at=NOW,
        status=status,
        raw_response_hash=HASH_2 if status is ProviderAttemptStatus.SUCCEEDED else None,
        source_manifest_id=(
            ArtifactId("source-manifest-fixture")
            if status is ProviderAttemptStatus.SUCCEEDED
            else None
        ),
        source_manifest_hash=(
            HASH_3 if status is ProviderAttemptStatus.SUCCEEDED else None
        ),
        error_code=None if status is ProviderAttemptStatus.SUCCEEDED else "PROVIDER_FAILED",
        error_message=None if status is ProviderAttemptStatus.SUCCEEDED else "failure",
        reason_codes=(
            ("VALIDATED_RESPONSE",)
            if status is ProviderAttemptStatus.SUCCEEDED
            else ("PROVIDER_FAILED",)
        ),
        retry_at=None,
        provider_revision="fixture-v1",
    )


def _evidence(attempt: ProviderAttemptSnapshot) -> EvidenceCommit:
    return EvidenceCommit.create(
        attempt=attempt,
        evidence_scope="A_SHARE_MINUTE_SCOPE",
        trading_date=date(2026, 8, 6),
        request_scope_hash=HASH_1,
        raw_artifact_id=ArtifactId("raw-artifact-fixture"),
        raw_artifact_hash=HASH_2,
        evidence_artifact_id=ArtifactId("evidence-artifact-fixture"),
        evidence_artifact_hash=HASH_3,
        material_identity_hash=HASH_3,
        provider_configuration_id=ArtifactId("provider-config-fixture"),
        provider_configuration_hash=HASH_1,
        effective_at=NOW,
        retrieved_at=NOW,
        available_at=NOW,
        as_of_time=NOW,
        quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
        evidence_qualification="FREE_DATA_EXPLORATORY",
        limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
    )


def test_only_successful_validated_attempt_can_create_evidence() -> None:
    evidence = _evidence(_attempt())

    assert str(evidence.evidence_commit_id).startswith("evidence-commit-")
    assert EvidenceCommit.from_canonical_dict(evidence.to_canonical_dict()) == evidence
    with pytest.raises(ValueError, match="successful validated"):
        _evidence(_attempt(ProviderAttemptStatus.TIMED_OUT))


@pytest.mark.parametrize(
    "status",
    (
        ProviderAttemptStatus.FAILED,
        ProviderAttemptStatus.TIMED_OUT,
        ProviderAttemptStatus.INVALID_RESPONSE,
        ProviderAttemptStatus.RATE_LIMITED,
        ProviderAttemptStatus.CIRCUIT_OPEN,
    ),
)
def test_failure_outcome_cannot_carry_source_manifest(
    status: ProviderAttemptStatus,
) -> None:
    with pytest.raises(ValueError, match="failed Attempt cannot carry"):
        ProviderAttemptOutcome.create(
            status=status,
            completed_at=NOW,
            raw_response_hash=None,
            source_manifest_id=ArtifactId("invented-manifest"),
            source_manifest_hash=HASH_1,
            error_code="PROVIDER_FAILURE",
            error_message="failure",
            reason_codes=(status.value,),
            retry_at=None,
        )


def test_evidence_identity_rejects_tamper() -> None:
    evidence = _evidence(_attempt())

    with pytest.raises(ValueError, match="hash mismatch"):
        replace(evidence, commit_hash="sha256:" + "0" * 64)


def test_evidence_available_after_as_of_time_is_rejected() -> None:
    attempt = _attempt()

    with pytest.raises(ValueError, match="AvailableAt"):
        EvidenceCommit.create(
            attempt=attempt,
            evidence_scope="A_SHARE_MINUTE_SCOPE",
            trading_date=date(2026, 8, 6),
            request_scope_hash=HASH_1,
            raw_artifact_id=ArtifactId("raw-artifact-future"),
            raw_artifact_hash=HASH_2,
            evidence_artifact_id=ArtifactId("evidence-artifact-future"),
            evidence_artifact_hash=HASH_3,
            material_identity_hash=HASH_3,
            provider_configuration_id=ArtifactId("provider-config-future"),
            provider_configuration_hash=HASH_1,
            effective_at=NOW,
            retrieved_at=NOW,
            available_at=NOW.replace(minute=43),
            as_of_time=NOW,
            quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
            evidence_qualification="FREE_DATA_EXPLORATORY",
            limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
        )
