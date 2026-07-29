from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.envelope import (
    ArtifactEnvelope,
    EvidenceAuthority,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _envelope() -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type="MARKET_REGIME_SNAPSHOT",
        artifact_payload={"market_state": "RISK_NEUTRAL", "score": 0.0},
        decision_date=date(2026, 7, 29),
        decision_time=DecisionTime(
            datetime(2026, 7, 29, 14, 55, tzinfo=SHANGHAI)
        ),
        created_at=datetime(2026, 7, 29, 15, 1, tzinfo=SHANGHAI),
        code_revision="abc123",
        configuration_id=ArtifactId("market-regime-config-1"),
        configuration_hash="sha256:" + "1" * 64,
        source_manifest_id=ArtifactId("source-manifest-1"),
        source_manifest_hash="sha256:" + "2" * 64,
        input_artifact_ids=(ArtifactId("input-a"), ArtifactId("input-b")),
        input_content_hashes=(
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
        ),
        model_id=ModelId("market-regime-v0"),
        model_version="0.1.0",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("MODEL_ASSUMPTION",),
        limitations=("NOT_EMPIRICALLY_VALIDATED",),
    )


def test_envelope_identity_is_deterministic_and_payload_bound() -> None:
    first = _envelope()
    second = _envelope()

    assert first == second
    assert str(first.artifact_id).startswith("market-regime-snapshot-")
    first.verify_payload({"market_state": "RISK_NEUTRAL", "score": 0.0})
    with pytest.raises(ValueError, match="payload hash mismatch"):
        first.verify_payload({"market_state": "RISK_ON", "score": 1.0})


def test_envelope_round_trip_rejects_unknown_and_missing_fields() -> None:
    payload = _envelope().to_canonical_dict()
    assert ArtifactEnvelope.from_canonical_dict(payload) == _envelope()

    with pytest.raises(ValueError, match="fields mismatch"):
        ArtifactEnvelope.from_canonical_dict({**payload, "unknown": True})
    missing = dict(payload)
    missing.pop("status")
    with pytest.raises(ValueError, match="fields mismatch"):
        ArtifactEnvelope.from_canonical_dict(missing)


def test_envelope_cannot_inflate_public_research_authority() -> None:
    payload = _envelope().to_canonical_dict()
    payload["data_eligibility"] = "FORMAL_RESEARCH"
    with pytest.raises(ValueError, match="EXPLORATORY"):
        ArtifactEnvelope.from_canonical_dict(payload)

