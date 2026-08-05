from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledEvidenceReference,
    ControlledOperationalEvidencePackage,
    ControlledOperationalEvidenceStatus,
    StageRuntimeLatency,
    load_controlled_operation_package,
    publish_controlled_operation_package,
    replay_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
    DecisionTimeOperationReceipt,
    DecisionTimeOperationStageName,
)
from market_regime_alpha.application.controlled_operation.policy import (
    default_decision_time_operation_policy,
)
from market_regime_alpha.core.identity import ArtifactId


UTC = timezone.utc
HASH = "sha256:" + "a" * 64
REQUIRED = (
    "TRADING_CALENDAR",
    "OPERATIONAL_UNIVERSE",
    "DAILY_SOURCE_ARCHIVE",
    "DAILY_SOURCE_MANIFEST",
    "DAILY_DATASET",
    "STATIC_FEATURE_BUNDLE",
    "CONTROLLED_RESEARCH",
    "CANDIDATE_SET",
    "MINUTE_ACQUISITION_COVERAGE",
    "MINUTE_DATASET",
    "INTRADAY_FEATURE_OVERLAY",
    "CANDIDATE_FEATURE_VIEW_V2",
    "SIGNAL_V3",
    "PATH_FORECAST",
    "ENTRY_BLOCKER",
)


def _artifact(
    *,
    decision_time: datetime = datetime(2026, 8, 5, 6, 55, tzinfo=UTC),
    daily_dataset_id: ArtifactId = ArtifactId("evidence-3"),
    daily_dataset_hash: str = HASH,
) -> ControlledOperationalEvidencePackage:
    policy = default_decision_time_operation_policy()
    command = ControlledOperationCommand.create(
        idempotency_key="package-test",
        decision_date=decision_time.date(),
        decision_time=decision_time,
        policy_id=policy.policy_id,
        policy_hash=policy.content_hash,
        trading_calendar_id=ArtifactId("calendar-test"),
        trading_calendar_hash=HASH,
        configuration_manifest_id=ArtifactId("config-manifest-test"),
        configuration_manifest_hash=HASH,
        model_manifest_id=ArtifactId("model-manifest-test"),
        model_manifest_hash=HASH,
        code_revision="test-revision",
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )
    receipt = DecisionTimeOperationReceipt.create(
        run_id=command.run_id,
        stage_name=DecisionTimeOperationStageName.ENTRY_ASSESSMENT,
        attempt_number=1,
        input_references=(),
        output_references=(),
        child_run_references=(),
        reason_codes=("ENTRY_BLOCKED",),
        created_at=datetime(2026, 8, 5, 6, 55, tzinfo=UTC),
    )
    refs = tuple(
        ControlledEvidenceReference(
            reference_type=kind,
            object_id=(ArtifactId(str(daily_dataset_id)) if kind == "DAILY_DATASET" else ArtifactId(f"evidence-{index}")),
            content_hash=(daily_dataset_hash if kind == "DAILY_DATASET" else HASH),
            locator=f"evidence/{index}",
        )
        for index, kind in enumerate(sorted(REQUIRED))
    )
    return ControlledOperationalEvidencePackage.create(
        command=command,
        policy=policy,
        status=ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
        evidence_references=refs,
        stage_receipts=(receipt,),
        code_revision="test-revision",
        feature_set_id=ArtifactId("static-feature-set-test"),
        signal_model_id="canonical-signal-model-v3",
        signal_model_version="3.0.0-exploratory",
        configuration_hashes=(HASH,),
        universe_count=100,
        candidate_count=5,
        minute_success_count=4,
        minute_failure_count=1,
        signal_state_counts=(("DATA_INSUFFICIENT", 1), ("WAIT", 4)),
        stage_latencies=(StageRuntimeLatency("SIGNAL", 12),),
        deadline_status="ON_TIME",
        created_at=datetime(2026, 8, 5, 6, 55, tzinfo=UTC),
        authority_ceiling=(
            "BROKER_NOT_INVOKED",
            "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "NO_FILL_CREATED",
            "NO_ORDER_CREATED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
        limitations=("ENGINEERING_FIXTURE", "FORMAL_PIT_NOT_ESTABLISHED"),
    )


def test_operation_package_is_exact_immutable_and_replayable(tmp_path: Path) -> None:
    artifact = _artifact()
    path = publish_controlled_operation_package(root=tmp_path, artifact=artifact)

    assert load_controlled_operation_package(path) == artifact
    assert replay_controlled_operation_package(path) == artifact
    assert publish_controlled_operation_package(root=tmp_path, artifact=artifact) == path

    payload = json.loads((path / "artifact.json").read_text(encoding="utf-8"))
    payload["candidate_count"] = 9
    (path / "artifact.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_controlled_operation_package(path)


def test_operation_package_rejects_absolute_or_parent_locator() -> None:
    with pytest.raises(ValueError, match="relative path"):
        ControlledEvidenceReference("X", ArtifactId("x"), HASH, "/tmp/x")
    with pytest.raises(ValueError, match="relative path"):
        ControlledEvidenceReference("X", ArtifactId("x"), HASH, "../x")
