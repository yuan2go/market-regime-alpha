from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, OpportunityId, ThesisId
from market_regime_alpha.decision import DecisionEvidenceReference
import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.position import (
    ManualInvalidationEvidence,
    ThesisHealth,
    ThesisHealthObservationV2,
    ThesisHealthSupportState,
)


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 4, 14, 55, tzinfo=TZ)
SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


def _reference(name: str, artifact_type: str) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type=artifact_type,
        artifact_id=ArtifactId(name),
        content_hash=SHA_A,
        status="VERIFIED_EXPLORATORY",
    )


def _manual() -> ManualInvalidationEvidence:
    return ManualInvalidationEvidence.create(
        thesis_id=ThesisId("thesis-h5-contract"),
        thesis_version=0,
        condition_id="manual-stop",
        actor="operator-a",
        reason="explicit manual invalidation evidence",
        recorded_at=NOW - timedelta(seconds=5),
        availability_time=NOW - timedelta(seconds=4),
    )


def _observation(
    *,
    observed: ThesisHealth = ThesisHealth.HEALTHY,
    effective: ThesisHealth | None = ThesisHealth.HEALTHY,
    prior: bool = False,
) -> ThesisHealthObservationV2:
    return ThesisHealthObservationV2.create(
        thesis_id=ThesisId("thesis-h5-contract"),
        thesis_version=0,
        opportunity_id=OpportunityId("opportunity-h5-contract"),
        symbol="000001.SZ",
        primary_theme_id="theme-bank",
        assessed_at=NOW,
        actor="reviewer-a",
        reason="artifact-derived H5 assessment",
        market_price=10.5,
        price_observation_id=ArtifactId("price-observation-h5"),
        price_observation_hash=SHA_A,
        price_snapshot_id=ArtifactId("price-snapshot-h5"),
        price_snapshot_hash=SHA_B,
        market_regime_id=ArtifactId("market-h5"),
        market_regime_hash=SHA_A,
        candidate_set_id=ArtifactId("candidate-h5"),
        candidate_set_hash=SHA_B,
        signal_snapshot_id=ArtifactId("signal-h5"),
        signal_snapshot_hash=SHA_A,
        path_forecast_id=ArtifactId("path-h5"),
        path_forecast_hash=SHA_B,
        theme_rotation_id=ArtifactId("theme-h5"),
        theme_rotation_hash=SHA_A,
        capital_evolution_id=ArtifactId("capital-h5"),
        capital_evolution_hash=SHA_B,
        thesis_supporting_evidence=(
            _reference("candidate-creation", "CANDIDATE_SET"),
            _reference("path-creation", "PATH_FORECAST"),
            _reference("signal-creation", "SIGNAL_SNAPSHOT"),
        ),
        configuration_id=ArtifactId("health-config-h5"),
        configuration_hash=SHA_A,
        rule_set_id=ArtifactId("health-rules-h5"),
        rule_set_hash=SHA_B,
        builder_revision="h5-builder-v1",
        market_support_state=ThesisHealthSupportState.SUPPORTED,
        signal_support_state=ThesisHealthSupportState.SUPPORTED,
        path_support_state=ThesisHealthSupportState.SUPPORTED,
        theme_support_state=ThesisHealthSupportState.SUPPORTED,
        capital_support_state=ThesisHealthSupportState.SUPPORTED,
        triggered_condition_ids=(),
        missing_reason_codes=(
            ("SYNTHETIC_DATA_MISSING",)
            if observed is ThesisHealth.DATA_INSUFFICIENT
            else ()
        ),
        reason_codes=("THESIS_HEALTH_DERIVED_FROM_VERIFIED_ARTIFACTS",),
        observed_health_state=observed,
        prior_observation_id=(ArtifactId("prior-health-h5") if prior else None),
        prior_observation_hash=(SHA_A if prior else None),
        prior_observed_health_state=(ThesisHealth.WEAKENING if prior else None),
        prior_effective_health_state=(ThesisHealth.WEAKENING if prior else None),
        effective_health_state=effective,
        manual_evidence_ids=(),
        manual_evidence_hashes=(),
    )


def test_manual_evidence_is_content_addressed_and_reconstructible() -> None:
    evidence = _manual()

    assert ManualInvalidationEvidence.from_canonical_dict(
        evidence.to_canonical_dict()
    ) == evidence
    assert evidence.authentication_limitation == (
        "MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED"
    )


def test_manual_evidence_rejects_identity_tamper_and_invalid_time() -> None:
    payload = _manual().to_canonical_dict()
    payload["content_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="identity"):
        ManualInvalidationEvidence.from_canonical_dict(payload)

    with pytest.raises(ValueError, match="availability_time"):
        ManualInvalidationEvidence.create(
            thesis_id=ThesisId("thesis-h5-contract"),
            thesis_version=0,
            condition_id="manual-stop",
            actor="operator-a",
            reason="invalid temporal evidence",
            recorded_at=NOW,
            availability_time=NOW - timedelta(seconds=1),
        )


def test_v2_observation_has_strict_canonical_round_trip() -> None:
    observation = _observation()

    restored = ThesisHealthObservationV2.from_canonical_dict(
        observation.to_canonical_dict()
    )
    assert restored == observation
    assert restored.formal_oos_alpha == "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    assert restored.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"
    assert restored.manual_evidence_authentication == (
        "MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED"
    )


def test_v2_observation_rejects_hash_identity_and_unknown_field_tamper() -> None:
    payload = _observation().to_canonical_dict()
    payload["content_hash"] = "sha256:" + "e" * 64
    with pytest.raises(ValueError, match="identity"):
        ThesisHealthObservationV2.from_canonical_dict(payload)

    payload = _observation().to_canonical_dict()
    payload["unknown_health"] = "HEALTHY"
    with pytest.raises(ValueError, match="fields mismatch"):
        ThesisHealthObservationV2.from_canonical_dict(payload)


def test_prior_observation_identity_and_states_are_bound_together() -> None:
    observation = _observation(
        observed=ThesisHealth.HEALTHY,
        effective=ThesisHealth.WEAKENING,
        prior=True,
    )
    assert observation.prior_observation_id == ArtifactId("prior-health-h5")
    assert observation.prior_observed_health_state is ThesisHealth.WEAKENING
    assert observation.prior_effective_health_state is ThesisHealth.WEAKENING

    values = observation.semantic_payload()
    values["prior_observation_hash"] = None
    with pytest.raises(ValueError, match="prior observation"):
        ThesisHealthObservationV2.create_from_semantic(values)


def test_first_data_insufficient_does_not_forge_effective_health() -> None:
    observation = _observation(
        observed=ThesisHealth.DATA_INSUFFICIENT,
        effective=None,
    )
    assert observation.effective_health_state is None

    with pytest.raises(ValueError, match="effective"):
        _observation(
            observed=ThesisHealth.DATA_INSUFFICIENT,
            effective=ThesisHealth.HEALTHY,
        )


def test_effective_state_cannot_be_data_insufficient() -> None:
    with pytest.raises(ValueError, match="effective"):
        _observation(
            observed=ThesisHealth.DATA_INSUFFICIENT,
            effective=ThesisHealth.DATA_INSUFFICIENT,
        )
