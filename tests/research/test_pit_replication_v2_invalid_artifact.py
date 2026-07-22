from hashlib import sha256
import json
from pathlib import Path

import pytest

from market_regime_alpha.research.pit_replication_preflight import (
    PITReplicationPreflight,
    PITReplicationPreflightStatus,
)
from market_regime_alpha.research.pit_replication_v2_artifacts import publish_pit_replication_v2
from market_regime_alpha.research.pit_replication_v2_preflight import (
    preflight_xuntou_replication_v2,
)
from market_regime_alpha.research.pit_replication_v2_protocol import (
    frozen_pit_replication_v2_protocol,
)
from market_regime_alpha.research.pit_replication_v2_reader import (
    load_verified_pit_replication_v2,
)


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _rewrite_checksums(root: Path) -> None:
    payload = {
        item.name: _hash(item)
        for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_invalid_v2_artifact_preserves_and_verifies_rejection_reasons(tmp_path: Path) -> None:
    bundle = tmp_path / "invalid.json"
    bundle.write_text("{}", encoding="utf-8")
    preflight = preflight_xuntou_replication_v2(bundle)
    final = publish_pit_replication_v2(
        output_root=tmp_path / "runs",
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=preflight,
    )
    assert load_verified_pit_replication_v2(final).status == "INVALID_PIT_EVIDENCE"
    errors = json.loads((final / "validation_errors.json").read_text(encoding="utf-8"))
    errors["rejection_reasons"] = ["FORGED_REASON"]
    (final / "validation_errors.json").write_text(json.dumps(errors), encoding="utf-8")
    _rewrite_checksums(final)
    with pytest.raises(ValueError, match="rejection reasons"):
        load_verified_pit_replication_v2(final)


def test_missing_bundle_publishes_verified_blocked_v2_artifact(tmp_path: Path) -> None:
    final = publish_pit_replication_v2(
        output_root=tmp_path / "runs",
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=preflight_xuntou_replication_v2(None),
    )
    assert load_verified_pit_replication_v2(final).status == "BLOCKED_EXTERNAL_PROVIDER_INPUT"


def test_v4_missing_bundle_publishes_verified_blocked_v2_artifact(tmp_path: Path) -> None:
    preflight = PITReplicationPreflight(
        schema_version="pit-replication-provider-preflight-v2",
        status=PITReplicationPreflightStatus.BLOCKED_EXTERNAL_PROVIDER_INPUT,
        provider="XUNTOU",
        required_bundle_schema="xuntou-pit-validation-bundle-v4",
        required_product="XTQUANT",
        expected_source_files=("xuntou_pit_validation_bundle_v4.json",),
        bundle_content_hash=None,
        provider_artifact_id=None,
        provider_dataset_id=None,
        membership_source=None,
        reasons=("EXTERNAL_XTQUANT_RUNTIME_REQUIRED",),
        tencent_fallback_allowed=False,
        prepared=None,
    )
    final = publish_pit_replication_v2(
        output_root=tmp_path / "runs",
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=preflight,
    )
    assert load_verified_pit_replication_v2(final).status == "BLOCKED_EXTERNAL_PROVIDER_INPUT"


@pytest.mark.parametrize(
    ("field", "forged"),
    (
        ("data_eligibility", "FORMAL_OOS"),
        ("authority", "RESEARCH_RESULT"),
        ("provider", "TENCENT"),
        ("formal_oos_alpha", "ESTABLISHED"),
    ),
)
def test_checksum_valid_manifest_authority_tamper_fails(
    tmp_path: Path, field: str, forged: str
) -> None:
    final = publish_pit_replication_v2(
        output_root=tmp_path / "runs",
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=preflight_xuntou_replication_v2(None),
    )
    manifest_path = final / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = forged
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _rewrite_checksums(final)
    with pytest.raises(ValueError, match=r"manifest (authority|fields)"):
        load_verified_pit_replication_v2(final)


@pytest.mark.parametrize(
    ("field", "forged"),
    (
        ("provider", "TENCENT"),
        ("required_product", "FORGED_PRODUCT"),
        ("provider_dataset_id", "forged-dataset"),
        ("membership_source", "CURRENT_WATCHLIST_BACKFILL"),
        ("tencent_fallback_allowed", True),
    ),
)
def test_checksum_valid_preflight_identity_tamper_fails(
    tmp_path: Path, field: str, forged: object
) -> None:
    final = publish_pit_replication_v2(
        output_root=tmp_path / "runs",
        protocol=frozen_pit_replication_v2_protocol(),
        preflight=preflight_xuntou_replication_v2(None),
    )
    preflight_path = final / "preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight[field] = forged
    preflight_path.write_text(json.dumps(preflight, sort_keys=True), encoding="utf-8")
    _rewrite_checksums(final)
    with pytest.raises(ValueError, match="preflight"):
        load_verified_pit_replication_v2(final)
