from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from market_regime_alpha.research.pit_replication_success_v2 import (
    build_pit_replication_success_results,
)
from market_regime_alpha.research.pit_replication_success_v2_artifacts import (
    build_success_identity,
    publish_pit_replication_success_v2,
    success_reader_implementation_identity,
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
        partition_open_receipt=replace(
            inputs.partition_open_receipt,
            run_id=run_id,
            reader_implementation_identity=success_reader_implementation_identity(),
        ),
    )
    return build_pit_replication_success_results(inputs, protocol=protocol)


def test_success_artifact_is_immutable_and_test_only(tmp_path: Path) -> None:
    results = _results()
    final = publish_pit_replication_success_v2(output_root=tmp_path, results=results)
    assert final.name.startswith("test-only-pit-replication-v2-")
    chronological = json.loads(
        (final / "chronological_replication_summary.json").read_text(encoding="utf-8")
    )
    assert chronological["monthly_slices"]
    assert chronological["quarterly_slices"]
    assert chronological["feature_completeness"]["overall_ratio"] == 1.0
    assert chronological["turnover"]["definition_id"] == "top5-one-minus-overlap-v1"
    assert chronological["liquidity_slices"]["status"] == "UNAVAILABLE"
    with pytest.raises(FileExistsError, match="immutable"):
        publish_pit_replication_success_v2(output_root=tmp_path, results=results)


def test_cost_contract_changes_semantic_run_identity() -> None:
    results = _results()
    identity = build_success_identity(results)
    changed = replace(identity, cost_model_hash="sha256:" + "9" * 64)
    assert changed.run_id() != identity.run_id()


def test_publisher_rejects_invalid_first_open_receipt(tmp_path: Path) -> None:
    results = _results()
    broken = replace(
        results,
        inputs=replace(
            results.inputs,
            partition_open_receipt=replace(
                results.inputs.partition_open_receipt,
                reader_implementation_identity="sha256:" + "0" * 64,
            ),
        ),
    )
    with pytest.raises(ValueError, match="first-open receipt"):
        publish_pit_replication_success_v2(output_root=tmp_path, results=broken)
