from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from market_regime_alpha.application.operational_research.composite_artifact import (
    COMPOSITE_OPERATIONAL_ARTIFACT_FILES,
    cleanup_orphan_composite_staging,
    load_verified_composite_operational_manifest,
    publish_composite_operational_manifest,
)
from tests.application.operational_research.test_composite_manifest_builder import (
    _build,
    _policy,
)
from tests.daily_decision.conftest import DailyDecisionFixture


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _refresh_checksum(package: Path, filename: str) -> None:
    checksum_path = package / "SHA256SUMS.json"
    checksums = json.loads(checksum_path.read_text(encoding="utf-8"))
    checksums[filename] = (
        f"sha256:{sha256((package / filename).read_bytes()).hexdigest()}"
    )
    _write_json(checksum_path, checksums)


def test_composite_package_is_exact_verified_and_repeat_publish_is_idempotent(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    manifest = _build(tmp_path / "sources", daily_decision_fixture)
    policy = _policy()

    first = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=manifest,
        composition_policy=policy,
    )
    second = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=manifest,
        composition_policy=policy,
    )
    verified = load_verified_composite_operational_manifest(first)

    assert first == second
    assert {item.name for item in first.iterdir()} == set(
        COMPOSITE_OPERATIONAL_ARTIFACT_FILES
    )
    assert verified.manifest == manifest
    assert verified.composition_policy == policy


@pytest.mark.parametrize("filename", ["artifact.json", "manifest.json"])
def test_composite_package_rejects_json_or_checksum_tamper(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    filename: str,
) -> None:
    path = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=_build(tmp_path / "sources", daily_decision_fixture),
        composition_policy=_policy(),
    )
    payload = json.loads((path / filename).read_text(encoding="utf-8"))
    payload["tampered"] = True
    (path / filename).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_composite_operational_manifest(path)


def test_composite_package_rejects_extra_file_and_conflicting_existing_path(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    manifest = _build(tmp_path / "sources", daily_decision_fixture)
    root = tmp_path / "composite"
    path = publish_composite_operational_manifest(
        root=root,
        manifest=manifest,
        composition_policy=_policy(),
    )
    (path / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="exact file set"):
        load_verified_composite_operational_manifest(path)
    with pytest.raises(ValueError, match="exact file set"):
        publish_composite_operational_manifest(
            root=root,
            manifest=manifest,
            composition_policy=_policy(),
        )


@pytest.mark.parametrize("filename", ["artifact.json", "manifest.json"])
def test_composite_package_rejects_semantic_tamper_after_checksum_refresh(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
    filename: str,
) -> None:
    path = publish_composite_operational_manifest(
        root=tmp_path / "composite",
        manifest=_build(tmp_path / "sources", daily_decision_fixture),
        composition_policy=_policy(),
    )
    payload = json.loads((path / filename).read_text(encoding="utf-8"))
    if filename == "artifact.json":
        payload["reason_codes"] = ["FORGED_VERIFIED_REASON"]
    else:
        payload["composition_policy"]["profile_id"] = "forged-profile"
    _write_json(path / filename, payload)
    _refresh_checksum(path, filename)

    with pytest.raises(ValueError):
        load_verified_composite_operational_manifest(path)


def test_staging_failure_is_cleaned_and_orphan_cleanup_is_h6_scoped(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    manifest = _build(tmp_path / "sources", daily_decision_fixture)
    root = tmp_path / "composite"

    def fail(_: Path) -> None:
        raise RuntimeError("injected before rename")

    with pytest.raises(RuntimeError, match="injected"):
        publish_composite_operational_manifest(
            root=root,
            manifest=manifest,
            composition_policy=_policy(),
            before_rename=fail,
        )
    assert not tuple(root.glob(".composite-operational-*.staging-*"))

    orphan = root / f".{manifest.manifest_id}.staging-orphan"
    orphan.mkdir()
    unrelated = root / ".unrelated-staging"
    unrelated.mkdir()
    invalid_id = root / ".composite-operational-not-a-digest.staging-orphan"
    invalid_id.mkdir()
    embedded_marker = (
        root
        / ".composite-operational-0123456789abcdef01234567.backup.staging-orphan"
    )
    embedded_marker.mkdir()
    assert cleanup_orphan_composite_staging(root) == (orphan,)
    assert unrelated.is_dir()
    assert invalid_id.is_dir()
    assert embedded_marker.is_dir()
