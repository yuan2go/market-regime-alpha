from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from market_regime_alpha.application.controlled_operation.canonical_segment import (
    CanonicalLifecycleRunObjectReference,
    ControlledCanonicalLifecycleRunReceipt,
    LEGACY_CONTROLLED_CANONICAL_RUN_SCHEMA,
    load_controlled_canonical_lifecycle_run,
    publish_controlled_canonical_lifecycle_run,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash


HASH = "sha256:" + "7" * 64
NOW = datetime(2026, 8, 5, 6, 55, tzinfo=timezone.utc)


def _receipt() -> ControlledCanonicalLifecycleRunReceipt:
    inputs = (
        CanonicalLifecycleRunObjectReference(
            "CANDIDATE_FEATURE_VIEW_V2", ArtifactId("candidate-view"), HASH
        ),
    )
    outputs = tuple(
        sorted(
            (
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
            key=lambda item: (item.reference_type, str(item.object_id)),
        )
    )
    completed = (
        "VERIFY_COMPOSITE_EVIDENCE",
        "PLATFORM_RESEARCH",
        "SIGNAL",
        "PATH_FORECAST",
        "ENTRY_ASSESSMENT",
    )
    values = {
        "schema_version": "controlled-canonical-lifecycle-run-v2",
        "run_id": "lifecycle-run-test",
        "command_hash": HASH,
        "history_hash": HASH,
        "parent_operation_run_id": "controlled-operation-test",
        "parent_operation_command_hash": HASH,
        "decision_time": canonical_datetime(NOW),
        "code_revision": "test-revision",
        "configuration_manifest_hash": HASH,
        "model_manifest_hash": HASH,
        "input_references": [item.to_canonical_dict() for item in inputs],
        "output_references": [item.to_canonical_dict() for item in outputs],
        "completed_stages": list(completed),
        "stage_receipt_hashes": [HASH] * len(completed),
        "lifecycle_status": "BLOCKED_BY_MODEL_VALIDATION",
        "created_at": canonical_datetime(NOW),
        "authority_ceiling": [
            "BROKER_NOT_INVOKED",
            "ENTRY_BLOCKED",
            "NO_FILL_CREATED",
            "NO_MANUAL_TRADE_CREATED",
            "NO_ORDER_CREATED",
        ],
    }
    return ControlledCanonicalLifecycleRunReceipt(
        schema_version="controlled-canonical-lifecycle-run-v2",
        run_id=ArtifactId("lifecycle-run-test"),
        command_hash=HASH,
        history_hash=HASH,
        content_hash=canonical_hash(values),
        parent_operation_run_id=ArtifactId("controlled-operation-test"),
        parent_operation_command_hash=HASH,
        decision_time=NOW,
        code_revision="test-revision",
        configuration_manifest_hash=HASH,
        model_manifest_hash=HASH,
        input_references=inputs,
        output_references=outputs,
        completed_stages=completed,
        stage_receipt_hashes=(HASH,) * len(completed),
        lifecycle_status="BLOCKED_BY_MODEL_VALIDATION",
        created_at=NOW,
        authority_ceiling=(
            "BROKER_NOT_INVOKED",
            "ENTRY_BLOCKED",
            "NO_FILL_CREATED",
            "NO_MANUAL_TRADE_CREATED",
            "NO_ORDER_CREATED",
        ),
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


def test_legacy_v1_canonical_child_reader_preserves_identity(tmp_path: Path) -> None:
    current = _receipt()
    command_payload = {
        "schema_version": LEGACY_CONTROLLED_CANONICAL_RUN_SCHEMA,
        "parent_operation_run_id": str(current.parent_operation_run_id),
        "parent_operation_command_hash": current.parent_operation_command_hash,
        "decision_time": canonical_datetime(NOW),
        "code_revision": current.code_revision,
        "configuration_manifest_hash": current.configuration_manifest_hash,
        "model_manifest_hash": current.model_manifest_hash,
        "input_references": [
            item.to_canonical_dict() for item in current.input_references
        ],
    }
    command_hash = canonical_hash(command_payload)
    run_id = ArtifactId(
        f"controlled-canonical-run-{command_hash.split(':', 1)[1][:24]}"
    )
    values = {
        **command_payload,
        "run_id": str(run_id),
        "command_hash": command_hash,
        "output_references": [
            item.to_canonical_dict() for item in current.output_references
        ],
        "completed_stages": ["ENTRY_ASSESSMENT", "PATH_FORECAST", "SIGNAL"],
        "created_at": canonical_datetime(NOW),
        "authority_ceiling": list(current.authority_ceiling),
    }
    legacy = ControlledCanonicalLifecycleRunReceipt(
        schema_version=LEGACY_CONTROLLED_CANONICAL_RUN_SCHEMA,
        run_id=run_id,
        command_hash=command_hash,
        history_hash=None,
        content_hash=canonical_hash(values),
        parent_operation_run_id=current.parent_operation_run_id,
        parent_operation_command_hash=current.parent_operation_command_hash,
        decision_time=NOW,
        code_revision=current.code_revision,
        configuration_manifest_hash=current.configuration_manifest_hash,
        model_manifest_hash=current.model_manifest_hash,
        input_references=current.input_references,
        output_references=current.output_references,
        completed_stages=("ENTRY_ASSESSMENT", "PATH_FORECAST", "SIGNAL"),
        stage_receipt_hashes=(),
        lifecycle_status=None,
        created_at=NOW,
        authority_ceiling=current.authority_ceiling,
    )

    path = publish_controlled_canonical_lifecycle_run(root=tmp_path, artifact=legacy)

    assert load_controlled_canonical_lifecycle_run(path) == legacy
