from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from market_regime_alpha.application.continuous_research.change_detection import (
    ChangeDecision,
    MaterialIdentityInput,
)
from market_regime_alpha.application.continuous_research.evidence import (
    EvidenceCommit,
    EvidenceQualityStatus,
    ProviderAttemptSnapshot,
)
from market_regime_alpha.application.continuous_research.journal import (
    ChangeDecisionType,
    ProviderAttemptStatus,
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 6, 6, 45, tzinfo=timezone.utc)
HASHES = tuple("sha256:" + character * 64 for character in "123456789abcdef")


def _material(**overrides: object) -> MaterialIdentityInput:
    values: dict[str, object] = {
        "raw_content_hash": HASHES[0],
        "normalized_content_hash": HASHES[1],
        "source_manifest_semantic_hash": HASHES[2],
        "request_scope_hash": HASHES[3],
        "as_of_time": NOW,
        "configuration_references": (
            RuntimeArtifactReference(
                "PROVIDER_CONFIGURATION", ArtifactId("provider-config"), HASHES[4]
            ),
            RuntimeArtifactReference(
                "RESEARCH_CONFIGURATION", ArtifactId("research-config"), HASHES[5]
            ),
        ),
        "retrieved_at": NOW,
        "attempt_id": 1,
        "retry_count": 0,
        "fencing_token": 1,
    }
    values.update(overrides)
    return MaterialIdentityInput(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("raw_content_hash", HASHES[6]),
        ("normalized_content_hash", HASHES[6]),
        ("source_manifest_semantic_hash", HASHES[6]),
        ("request_scope_hash", HASHES[6]),
        (
            "configuration_references",
            (
                RuntimeArtifactReference(
                    "PROVIDER_CONFIGURATION",
                    ArtifactId("provider-config"),
                    HASHES[6],
                ),
            ),
        ),
    ),
)
def test_semantic_inputs_change_material_identity(field: str, value: object) -> None:
    assert _material().material_identity_hash != _material(
        **{field: value}
    ).material_identity_hash


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("retrieved_at", NOW + timedelta(minutes=2)),
        ("as_of_time", NOW + timedelta(minutes=1)),
        ("attempt_id", 99),
        ("retry_count", 8),
        ("fencing_token", 7),
    ),
)
def test_transport_metadata_does_not_change_material_identity(
    field: str, value: object
) -> None:
    assert _material().material_identity_hash == _material(
        **{field: value}
    ).material_identity_hash


def _attempt(*, attempt_id: int, tick_id: str) -> ProviderAttemptSnapshot:
    return ProviderAttemptSnapshot(
        attempt_id=attempt_id,
        run_id=ArtifactId("continuous-run-change"),
        tick_id=ArtifactId(tick_id),
        attempt_number=1,
        claim_id=f"claim-{attempt_id}",
        fencing_token=attempt_id,
        tick_version=3,
        provider_id="tencent-public",
        product="a-share-minute",
        request_hash=HASHES[0],
        started_at=NOW,
        completed_at=NOW,
        lease_expires_at=NOW + timedelta(seconds=30),
        heartbeat_at=NOW,
        status=ProviderAttemptStatus.SUCCEEDED,
        raw_response_hash=HASHES[0],
        source_manifest_id=ArtifactId(f"manifest-{attempt_id}"),
        source_manifest_hash=HASHES[2],
        error_code=None,
        error_message=None,
        reason_codes=("VALIDATED_RESPONSE",),
        retry_at=None,
        provider_revision="fixture-v1",
    )


def _evidence(*, attempt_id: int, tick_id: str, material_hash: str) -> EvidenceCommit:
    return EvidenceCommit.create(
        attempt=_attempt(attempt_id=attempt_id, tick_id=tick_id),
        evidence_scope="A_SHARE_MINUTE_SCOPE",
        trading_date=date(2026, 8, 6),
        request_scope_hash=HASHES[3],
        raw_artifact_id=ArtifactId(f"raw-{attempt_id}"),
        raw_artifact_hash=HASHES[0],
        evidence_artifact_id=ArtifactId(f"evidence-{attempt_id}"),
        evidence_artifact_hash=HASHES[1],
        material_identity_hash=material_hash,
        provider_configuration_id=ArtifactId("provider-config"),
        provider_configuration_hash=HASHES[4],
        effective_at=NOW,
        retrieved_at=NOW,
        available_at=NOW,
        as_of_time=NOW,
        quality_status=EvidenceQualityStatus.PIT_INCOMPLETE,
        evidence_qualification="FREE_DATA_EXPLORATORY",
        limitations=("FORMAL_PIT_NOT_ESTABLISHED", "NO_TRADING_AUTHORITY"),
    )


def test_change_decision_is_deterministic_and_fail_closed() -> None:
    first = _evidence(attempt_id=1, tick_id="tick-1", material_hash=HASHES[6])
    initial = ChangeDecision.create(
        evidence=first,
        previous_evidence=None,
        downstream_contract_satisfied=True,
        created_at=NOW,
    )
    assert initial.decision_type is ChangeDecisionType.INITIAL_EVIDENCE

    same = _evidence(attempt_id=2, tick_id="tick-2", material_hash=HASHES[6])
    no_change = ChangeDecision.create(
        evidence=same,
        previous_evidence=first,
        downstream_contract_satisfied=True,
        created_at=NOW,
    )
    assert no_change.decision_type is ChangeDecisionType.NO_MATERIAL_CHANGE

    changed = _evidence(attempt_id=3, tick_id="tick-3", material_hash=HASHES[7])
    material = ChangeDecision.create(
        evidence=changed,
        previous_evidence=first,
        downstream_contract_satisfied=True,
        created_at=NOW,
    )
    assert material.decision_type is ChangeDecisionType.MATERIAL_CHANGE

    blocked = ChangeDecision.create(
        evidence=changed,
        previous_evidence=first,
        downstream_contract_satisfied=False,
        created_at=NOW,
    )
    assert blocked.decision_type is ChangeDecisionType.DATA_INSUFFICIENT
    assert ChangeDecision.from_canonical_dict(blocked.to_canonical_dict()) == blocked
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(blocked, decision_hash=HASHES[8])


def test_first_validated_evidence_can_be_data_insufficient() -> None:
    evidence = _evidence(
        attempt_id=1, tick_id="tick-insufficient", material_hash=HASHES[6]
    )

    decision = ChangeDecision.create(
        evidence=evidence,
        previous_evidence=None,
        downstream_contract_satisfied=False,
        created_at=NOW,
    )

    assert decision.decision_type is ChangeDecisionType.DATA_INSUFFICIENT
    assert decision.previous_evidence_commit_id is None
