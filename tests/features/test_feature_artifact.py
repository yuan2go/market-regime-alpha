from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

import market_regime_alpha.features.artifact as feature_artifact_module
from market_regime_alpha.features.artifact import (
    FEATURE_ARTIFACT_FILES,
    bind_feature_artifact_identity,
    load_verified_feature_artifact,
    publish_feature_artifact,
)
from market_regime_alpha.features.technical.moving_average import (
    MovingAverageObservation,
    SimpleMovingAverageComputer,
)

from .test_moving_average import _request


def _published(tmp_path: Path) -> tuple[Path, object]:
    artifact = SimpleMovingAverageComputer().compute(_request())
    path = publish_feature_artifact(root=tmp_path, artifact=artifact)
    return path, artifact


def test_feature_publisher_has_exact_files_and_is_idempotent(tmp_path: Path) -> None:
    path, artifact = _published(tmp_path)

    assert {item.name for item in path.iterdir()} == set(FEATURE_ARTIFACT_FILES)
    assert publish_feature_artifact(root=tmp_path, artifact=artifact) == path
    verified = load_verified_feature_artifact(path)
    assert verified.artifact.to_canonical_dict() == artifact.to_canonical_dict()
    assert verified.checksums_hash.startswith("sha256:")


def test_feature_reader_rejects_checksum_tamper(tmp_path: Path) -> None:
    path, _ = _published(tmp_path)
    (path / "artifact.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_feature_artifact(path)


def test_feature_reader_rejects_unexpected_file(tmp_path: Path) -> None:
    path, _ = _published(tmp_path)
    (path / "extra.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exact file set"):
        load_verified_feature_artifact(path)


def test_feature_reader_rejects_semantic_hash_tamper_even_with_new_checksums(
    tmp_path: Path,
) -> None:
    import hashlib
    import json

    path, _ = _published(tmp_path)
    artifact_path = path / "artifact.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["state"] = "DATA_INSUFFICIENT"
    artifact_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    checksum_path = path / "SHA256SUMS.json"
    checksums = json.loads(checksum_path.read_text(encoding="utf-8"))
    checksums["artifact.json"] = (
        "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    )
    checksum_path.write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="payload hash mismatch"):
        load_verified_feature_artifact(path)


def test_feature_publisher_rejects_unbound_or_conflicting_content(
    tmp_path: Path,
) -> None:
    artifact = SimpleMovingAverageComputer().compute(_request())
    invalid = replace(artifact, state="DATA_INSUFFICIENT")

    with pytest.raises(ValueError, match="payload hash mismatch"):
        publish_feature_artifact(root=tmp_path, artifact=invalid)

    path = publish_feature_artifact(root=tmp_path, artifact=artifact)
    (path / "manifest.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_feature_artifact(root=tmp_path, artifact=artifact)


@pytest.mark.parametrize("invalid_field", ["available_at", "market_date"])
def test_publisher_and_reader_reject_rebound_post_as_of_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_field: str,
) -> None:
    original = SimpleMovingAverageComputer().compute(_request())
    observations = list(original.observations)
    final = observations[-1]
    assert isinstance(final, MovingAverageObservation)
    invalid_observation = (
        replace(final, available_at=original.as_of_time + timedelta(seconds=1))
        if invalid_field == "available_at"
        else replace(final, market_date=date(2026, 8, 5))
    )
    observations[-1] = invalid_observation
    rebound = bind_feature_artifact_identity(
        replace(original, observations=tuple(observations))
    )
    rebound.verify_content_identity()
    assert rebound.content_hash != original.content_hash

    with pytest.raises(ValueError, match="exceeds as_of_time"):
        publish_feature_artifact(root=tmp_path / "publisher", artifact=rebound)

    # Build the impossible-on-the-public-path package to exercise Reader semantics.
    with monkeypatch.context() as context:
        context.setattr(
            feature_artifact_module,
            "_validate_supported_artifact",
            lambda artifact: None,
        )
        path = publish_feature_artifact(root=tmp_path / "reader", artifact=rebound)
    with pytest.raises(ValueError, match="exceeds as_of_time"):
        load_verified_feature_artifact(path)
