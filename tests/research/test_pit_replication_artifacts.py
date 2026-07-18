import json
from pathlib import Path

import pytest

from market_regime_alpha.research.pit_replication_artifacts import publish_blocked_pit_replication
from market_regime_alpha.research.pit_replication_preflight import preflight_xuntou_replication
from market_regime_alpha.research.pit_replication_protocol import frozen_pit_replication_protocol


def test_missing_xuntou_bundle_publishes_immutable_blocker_artifact(tmp_path: Path) -> None:
    final = publish_blocked_pit_replication(
        output_root=tmp_path,
        protocol=frozen_pit_replication_protocol(),
        preflight=preflight_xuntou_replication(None),
        code_revision="abc123",
    )
    blocker = json.loads((final / "blocker.json").read_text(encoding="utf-8"))
    assert blocker["status"] == "BLOCKED_EXTERNAL_PROVIDER_INPUT"
    assert blocker["no_research_result_produced"] is True
    assert not (final / "candidate_rankings.parquet").exists()
    with pytest.raises(FileExistsError, match="immutable"):
        publish_blocked_pit_replication(
            output_root=tmp_path,
            protocol=frozen_pit_replication_protocol(),
            preflight=preflight_xuntou_replication(None),
            code_revision="abc123",
        )
