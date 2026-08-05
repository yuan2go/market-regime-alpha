from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from market_regime_alpha.application.controlled_operation.canonical_segment import (
    CanonicalLifecycleRunObjectReference,
    ControlledCanonicalLifecycleRunReceipt,
    load_controlled_canonical_lifecycle_run,
    publish_controlled_canonical_lifecycle_run,
)
from market_regime_alpha.core.identity import ArtifactId


HASH = "sha256:" + "7" * 64
NOW = datetime(2026, 8, 5, 6, 55, tzinfo=timezone.utc)


def _receipt() -> ControlledCanonicalLifecycleRunReceipt:
    return ControlledCanonicalLifecycleRunReceipt.create(
        parent_operation_run_id=ArtifactId("controlled-operation-test"),
        parent_operation_command_hash=HASH,
        decision_time=NOW,
        code_revision="test-revision",
        configuration_manifest_hash=HASH,
        model_manifest_hash=HASH,
        input_references=(
            CanonicalLifecycleRunObjectReference(
                "CANDIDATE_FEATURE_VIEW_V2", ArtifactId("candidate-view"), HASH
            ),
        ),
        output_references=(
            CanonicalLifecycleRunObjectReference(
                "SIGNAL_V3", ArtifactId("signal-v3"), HASH
            ),
            CanonicalLifecycleRunObjectReference(
                "PATH_FORECAST", ArtifactId("path-forecast"), HASH
            ),
            CanonicalLifecycleRunObjectReference(
                "ENTRY_BLOCKER", ArtifactId("entry-blocker"), HASH
            ),
        ),
        created_at=NOW,
    )


def test_canonical_child_run_is_real_immutable_receipt(tmp_path: Path) -> None:
    artifact = _receipt()
    path = publish_controlled_canonical_lifecycle_run(
        root=tmp_path,
        artifact=artifact,
    )

    assert load_controlled_canonical_lifecycle_run(path) == artifact
    assert publish_controlled_canonical_lifecycle_run(
        root=tmp_path,
        artifact=artifact,
    ) == path
    assert artifact.run_id != artifact.parent_operation_run_id
