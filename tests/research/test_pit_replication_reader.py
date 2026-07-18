from hashlib import sha256
import json
from pathlib import Path

import pytest

from market_regime_alpha.research.pit_replication_artifacts import publish_blocked_pit_replication
from market_regime_alpha.research.pit_replication_preflight import preflight_xuntou_replication
from market_regime_alpha.research.pit_replication_protocol import frozen_pit_replication_protocol
from market_regime_alpha.research.pit_replication_reader import load_verified_pit_replication_run


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _rewrite(root: Path) -> None:
    payload = {item.name: _hash(item) for item in root.iterdir() if item.name != "SHA256SUMS.json"}
    (root / "SHA256SUMS.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_blocker_reader_reconstructs_preflight_and_identity(tmp_path: Path) -> None:
    final = publish_blocked_pit_replication(
        output_root=tmp_path,
        protocol=frozen_pit_replication_protocol(),
        preflight=preflight_xuntou_replication(None),
        code_revision="abc123",
    )
    verified = load_verified_pit_replication_run(final)
    assert verified.status == "BLOCKED_EXTERNAL_PROVIDER_INPUT"


def test_checksum_valid_blocker_semantic_tamper_fails(tmp_path: Path) -> None:
    final = publish_blocked_pit_replication(
        output_root=tmp_path,
        protocol=frozen_pit_replication_protocol(),
        preflight=preflight_xuntou_replication(None),
        code_revision="abc123",
    )
    blocker_path = final / "blocker.json"
    blocker = json.loads(blocker_path.read_text(encoding="utf-8"))
    blocker["status"] = "PIT_REPLICATION_SUPPORTED_EXPLORATORY"
    blocker_path.write_text(json.dumps(blocker), encoding="utf-8")
    _rewrite(final)
    with pytest.raises(ValueError, match="blocker"):
        load_verified_pit_replication_run(final)
