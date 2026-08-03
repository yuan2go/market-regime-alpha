from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeCoveragePolicy,
    CompositeDecisionTimePolicy,
    CompositeOperationalComponentReference,
    CompositeOperationalComponentRole,
    CompositeOperationalCompositionPolicy,
    CompositeOperationalCompositionStatus,
    CompositeOperationalFieldAuthorityReference,
    CompositeOperationalFieldAuthorityRequirement,
    CompositeOperationalFieldGroup,
    CompositeOperationalInputManifest,
    CompositeSourceConflictPolicy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility


HASH_A = "sha256:" + "1" * 64
HASH_B = "sha256:" + "2" * 64
HASH_C = "sha256:" + "3" * 64
NOW = datetime(2026, 8, 4, 10, 35, tzinfo=timezone.utc)


def _requirement() -> CompositeOperationalFieldAuthorityRequirement:
    return CompositeOperationalFieldAuthorityRequirement(
        field_group=CompositeOperationalFieldGroup.PRICE,
        component_role=CompositeOperationalComponentRole.DECISION_PRICE_SNAPSHOT,
    )


def _policy() -> CompositeOperationalCompositionPolicy:
    return CompositeOperationalCompositionPolicy.create(
        profile_id="operational-exploratory-v1",
        required_component_roles=(
            CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
            CompositeOperationalComponentRole.DECISION_PRICE_SNAPSHOT,
        ),
        required_field_authorities=(_requirement(),),
        allowed_data_eligibility=(DataEligibility.EXPLORATORY,),
        decision_time_policy=CompositeDecisionTimePolicy.EXACT_MATCH,
        source_conflict_policy=CompositeSourceConflictPolicy.FAIL_CLOSED,
        coverage_policy=CompositeCoveragePolicy.EXACT_PREDICTION_POPULATION,
        builder_revision="h6-builder-v1",
    )


def _components() -> tuple[CompositeOperationalComponentReference, ...]:
    source = CompositeOperationalComponentReference(
        role=CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
        scope_key="PRIMARY",
        artifact_id=ArtifactId("source-manifest-daily"),
        content_hash=HASH_A,
        source_manifest_id=ArtifactId("source-manifest-daily"),
        source_manifest_hash=HASH_A,
        availability_time=AvailabilityTime(NOW),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    price = CompositeOperationalComponentReference(
        role=CompositeOperationalComponentRole.DECISION_PRICE_SNAPSHOT,
        scope_key="ALL",
        artifact_id=ArtifactId("decision-price-snapshot"),
        content_hash=HASH_B,
        source_manifest_id=ArtifactId("source-manifest-daily"),
        source_manifest_hash=HASH_A,
        availability_time=AvailabilityTime(NOW),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    return tuple(sorted((source, price), key=lambda item: item.sort_key))


def _fields() -> tuple[CompositeOperationalFieldAuthorityReference, ...]:
    return (
        CompositeOperationalFieldAuthorityReference(
            field_group=CompositeOperationalFieldGroup.PRICE,
            scope_key="ALL",
            component_role=(
                CompositeOperationalComponentRole.DECISION_PRICE_SNAPSHOT
            ),
            artifact_id=ArtifactId("decision-price-snapshot"),
            content_hash=HASH_B,
        ),
    )


def _manifest() -> CompositeOperationalInputManifest:
    return CompositeOperationalInputManifest.create(
        status=CompositeOperationalCompositionStatus.VERIFIED,
        decision_time=DecisionTime(NOW),
        created_at=NOW,
        composition_policy=_policy(),
        daily_artifact_id=ArtifactId("daily-decision-artifact"),
        daily_artifact_hash=HASH_C,
        daily_source_manifest_id=ArtifactId("source-manifest-daily"),
        daily_source_manifest_hash=HASH_A,
        supplemental_bundle_id=ArtifactId("supplemental-bundle"),
        supplemental_bundle_hash=HASH_C,
        supplemental_source_manifest_id=ArtifactId("source-manifest-supplemental"),
        supplemental_source_manifest_hash=HASH_B,
        component_references=_components(),
        field_authority_references=_fields(),
        missing_evidence=(),
        source_conflicts=(),
        reason_codes=("COMPOSITE_OPERATIONAL_EVIDENCE_VERIFIED",),
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )


def test_policy_and_manifest_are_content_addressed_round_trips() -> None:
    policy = _policy()
    manifest = _manifest()

    assert (
        CompositeOperationalCompositionPolicy.from_canonical_dict(
            policy.to_canonical_dict()
        )
        == policy
    )
    assert (
        CompositeOperationalInputManifest.from_canonical_dict(
            manifest.to_canonical_dict(), composition_policy=policy
        )
        == manifest
    )
    assert str(policy.policy_id).startswith("composite-policy-")
    assert str(manifest.manifest_id).startswith("composite-operational-")
    assert manifest.data_eligibility is DataEligibility.EXPLORATORY
    assert manifest.formal_pit == "FORMAL_PIT_NOT_ESTABLISHED"
    assert manifest.formal_oos_alpha == "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    assert manifest.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"


def test_policy_rejects_hidden_authority_or_duplicate_requirements() -> None:
    with pytest.raises(ValueError, match="allowed_data_eligibility"):
        CompositeOperationalCompositionPolicy.create(
            profile_id="invalid",
            required_component_roles=(
                CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
            ),
            required_field_authorities=(_requirement(),),
            allowed_data_eligibility=(DataEligibility.FORMAL_RESEARCH,),
            decision_time_policy=CompositeDecisionTimePolicy.EXACT_MATCH,
            source_conflict_policy=CompositeSourceConflictPolicy.FAIL_CLOSED,
            coverage_policy=CompositeCoveragePolicy.EXACT_PREDICTION_POPULATION,
            builder_revision="h6-builder-v1",
        )
    with pytest.raises(ValueError, match="required component roles"):
        CompositeOperationalCompositionPolicy.create(
            profile_id="invalid",
            required_component_roles=(
                CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
                CompositeOperationalComponentRole.DAILY_SOURCE_MANIFEST,
            ),
            required_field_authorities=(_requirement(),),
            allowed_data_eligibility=(DataEligibility.EXPLORATORY,),
            decision_time_policy=CompositeDecisionTimePolicy.EXACT_MATCH,
            source_conflict_policy=CompositeSourceConflictPolicy.FAIL_CLOSED,
            coverage_policy=CompositeCoveragePolicy.EXACT_PREDICTION_POPULATION,
            builder_revision="h6-builder-v1",
        )


def test_manifest_rejects_tamper_duplicates_and_authority_inflation() -> None:
    manifest = _manifest()
    payload = manifest.to_canonical_dict()
    payload["content_hash"] = HASH_A
    with pytest.raises(ValueError, match="identity mismatch"):
        CompositeOperationalInputManifest.from_canonical_dict(
            payload, composition_policy=_policy()
        )

    with pytest.raises(ValueError, match="component reference keys"):
        replace(
            manifest,
            component_references=(
                manifest.component_references[0],
                manifest.component_references[0],
            ),
        )
    with pytest.raises(ValueError, match="authority cannot be inflated"):
        replace(manifest, formal_pit="FORMAL_PIT_ESTABLISHED")


def test_manifest_rejects_same_artifact_id_with_different_hash() -> None:
    manifest = _manifest()
    conflicting = replace(
        manifest.component_references[1],
        artifact_id=manifest.component_references[0].artifact_id,
        content_hash=HASH_C,
    )
    with pytest.raises(ValueError, match="conflicting hashes"):
        replace(
            manifest,
            component_references=tuple(
                sorted(
                    (manifest.component_references[0], conflicting),
                    key=lambda item: item.sort_key,
                )
            ),
        )


def test_only_terminal_manifest_statuses_are_constructible() -> None:
    with pytest.raises(ValueError, match="ASSEMBLING"):
        replace(
            _manifest(),
            status=CompositeOperationalCompositionStatus.ASSEMBLING,
        )
    with pytest.raises(ValueError, match="missing evidence"):
        replace(
            _manifest(),
            status=CompositeOperationalCompositionStatus.DATA_INSUFFICIENT,
        )
    with pytest.raises(ValueError, match="source conflicts"):
        replace(
            _manifest(),
            status=CompositeOperationalCompositionStatus.CONFLICTED,
        )
