from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_regime_alpha.application.free_data_operation.blocked import (
    FreeDataBlockedArtifact,
    load_free_data_blocked,
    publish_free_data_blocked,
)
from market_regime_alpha.core.identity import ArtifactId


HASH = "sha256:" + "a" * 64


def test_blocked_artifact_is_idempotent_and_tamper_evident(tmp_path: Path) -> None:
    artifact = FreeDataBlockedArtifact.create(
        command_hash=HASH,
        source_archive_id=ArtifactId("source-replay-test"),
        source_manifest_id=ArtifactId("source-manifest-test"),
        source_manifest_hash=HASH,
        provider_result_hash=HASH,
        reason_code="DATA_AVAILABLE_AFTER_DECISION_TIME",
        error_type="ValueError",
        created_at=datetime(2026, 8, 5, 14, 0, tzinfo=UTC),
        code_revision="test-revision",
    )

    path = publish_free_data_blocked(root=tmp_path, artifact=artifact)

    assert load_free_data_blocked(path) == artifact
    assert publish_free_data_blocked(root=tmp_path, artifact=artifact) == path
    (path / "artifact.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_free_data_blocked(path)


def test_blocked_artifact_rejects_unexpected_files(tmp_path: Path) -> None:
    artifact = FreeDataBlockedArtifact.create(
        command_hash=HASH,
        source_archive_id=ArtifactId("source-replay-test"),
        source_manifest_id=ArtifactId("source-manifest-test"),
        source_manifest_hash=HASH,
        provider_result_hash=HASH,
        reason_code="DATA_AVAILABLE_AFTER_DECISION_TIME",
        error_type="ValueError",
        created_at=datetime(2026, 8, 5, 14, 0, tzinfo=UTC),
        code_revision="test-revision",
    )
    path = publish_free_data_blocked(root=tmp_path, artifact=artifact)
    (path / "unexpected.txt").touch()

    with pytest.raises(ValueError, match="file set mismatch"):
        load_free_data_blocked(path)
