from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from market_regime_alpha.application.continuous_research.children import (
    ContinuousChildReference,
)
from market_regime_alpha.application.continuous_research.journal import (
    ChildReferenceDisposition,
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 6, 6, 48, tzinfo=timezone.utc)
HASHES = tuple("sha256:" + character * 64 for character in "123456789abcdef")


def _reference(
    disposition: ChildReferenceDisposition = ChildReferenceDisposition.CREATED,
) -> ContinuousChildReference:
    return ContinuousChildReference.create(
        trading_date=date(2026, 8, 6),
        run_id=ArtifactId("continuous-run-child"),
        tick_id=ArtifactId("continuous-tick-child"),
        tick_sequence=4,
        provider_attempt_id=7,
        source_manifest_id=ArtifactId("source-manifest-child"),
        source_manifest_hash=HASHES[0],
        evidence_commit_id=ArtifactId("evidence-commit-child"),
        evidence_commit_hash=HASHES[1],
        decision_id=ArtifactId("change-decision-child"),
        decision_hash=HASHES[2],
        child_kind=ContinuousChildKind.FEATURE_MATERIALIZATION,
        reference_disposition=disposition,
        child_run_id=ArtifactId("feature-run-existing"),
        child_receipt_id=ArtifactId("feature-receipt-existing"),
        child_receipt_hash=HASHES[3],
        child_artifact_id=ArtifactId("feature-artifact-existing"),
        child_artifact_hash=HASHES[4],
        input_references=(
            RuntimeArtifactReference("DATASET", ArtifactId("dataset"), HASHES[5]),
            RuntimeArtifactReference("EVIDENCE", ArtifactId("evidence"), HASHES[6]),
        ),
        configuration_references=(
            RuntimeArtifactReference(
                "FEATURE_CONFIGURATION", ArtifactId("feature-config"), HASHES[7]
            ),
        ),
        created_at=NOW,
    )


def test_child_reference_carries_complete_parent_lineage() -> None:
    reference = _reference()

    assert reference.aggregate_input_hash.startswith("sha256:")
    assert reference.configuration_set_hash.startswith("sha256:")
    assert ContinuousChildReference.from_canonical_dict(
        reference.to_canonical_dict()
    ) == reference
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(reference, reference_hash=HASHES[8])


def test_reuse_preserves_existing_child_identity() -> None:
    created = _reference()
    reused = _reference(ChildReferenceDisposition.REUSED)

    assert reused.child_run_id == created.child_run_id
    assert reused.child_receipt_id == created.child_receipt_id
    assert reused.child_artifact_id == created.child_artifact_id
    assert reused.reference_disposition is ChildReferenceDisposition.REUSED
