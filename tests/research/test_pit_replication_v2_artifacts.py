from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from market_regime_alpha.research.pit_replication_success_v2 import (
    build_pit_replication_success_results,
)
from market_regime_alpha.research.pit_replication_success_v2_artifacts import (
    build_success_identity,
    publish_pit_replication_success_v2,
)
from market_regime_alpha.research.pit_replication_success_v2_protocol import (
    frozen_pit_replication_success_v2_protocol,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def _results():
    protocol = frozen_pit_replication_success_v2_protocol(test_only=True)
    inputs = build_test_success_inputs()
    provisional = build_pit_replication_success_results(inputs, protocol=protocol)
    run_id = build_success_identity(provisional).run_id()
    inputs = replace(
        inputs,
        partition_open_receipt=replace(inputs.partition_open_receipt, run_id=run_id),
    )
    return build_pit_replication_success_results(inputs, protocol=protocol)


def test_success_artifact_is_immutable_and_test_only(tmp_path: Path) -> None:
    results = _results()
    final = publish_pit_replication_success_v2(output_root=tmp_path, results=results)
    assert final.name.startswith("test-only-pit-replication-v2-")
    with pytest.raises(FileExistsError, match="immutable"):
        publish_pit_replication_success_v2(output_root=tmp_path, results=results)


def test_cost_contract_changes_semantic_run_identity() -> None:
    results = _results()
    identity = build_success_identity(results)
    changed = replace(identity, cost_model_hash="sha256:" + "9" * 64)
    assert changed.run_id() != identity.run_id()

