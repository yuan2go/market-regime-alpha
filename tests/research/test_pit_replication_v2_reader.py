from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

import pandas as pd
import pytest

from market_regime_alpha.research.pit_replication_success_v2_reader import (
    VerifiedPITReplicationSuccessV2,
    load_verified_pit_replication_success_v2,
)
from market_regime_alpha.research.pit_replication_success_v2_runner import (
    run_pit_replication_success_v2,
)
from market_regime_alpha.research.pit_replication_v2_reader import (
    load_verified_pit_replication_artifact_v2,
)
from tests.research.pit_replication_v2_fixtures import build_test_success_inputs


def _digest(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _rewrite_checksums(root: Path) -> None:
    payload = {
        item.name: _digest(item)
        for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _published(tmp_path: Path) -> Path:
    return run_pit_replication_success_v2(
        xuntou_bundle=None,
        output_root=tmp_path,
        success_inputs=build_test_success_inputs(),
    )


def _json_tamper(filename: str, mutate: Callable[[dict[str, object]], None]):
    def apply(root: Path) -> None:
        path = root / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return apply


def _parquet_tamper(filename: str, column: str, value: object):
    def apply(root: Path) -> None:
        path = root / filename
        frame = pd.read_parquet(path)
        frame.loc[0, column] = value
        frame.to_parquet(path, index=False)

    return apply


@pytest.mark.parametrize(
    "tamper",
    (
        _json_tamper(
            "model_spec.json",
            lambda row: row["components"][0].__setitem__("normalized_weight", 0.99),
        ),
        _json_tamper("partition_seal.json", lambda row: row["included_sessions"].pop()),
        _json_tamper(
            "partition_open_receipt.json",
            lambda row: row.__setitem__("reader_implementation_identity", "sha256:" + "0" * 64),
        ),
        _json_tamper(
            "manifest.json",
            lambda row: row.__setitem__("authority", "FORMAL_OOS_ALPHA"),
        ),
        _json_tamper(
            "cost_model.json",
            lambda row: row["configs"]["BASE"].__setitem__("minimum_commission", 0.0),
        ),
        _parquet_tamper("candidate_feature_evidence.parquet", "feature_value", 999.0),
        _parquet_tamper("candidate_rankings.parquet", "rank", 999),
        _parquet_tamper("evaluation_marks.parquet", "evaluation_price", 999.0),
        _parquet_tamper("path_diagnostics.parquet", "status", "FABRICATED"),
        _parquet_tamper("matched_k_selections.parquet", "symbol", "999999.SZ"),
        _parquet_tamper("daily_replication_metrics.parquet", "net_lift_vs_multiseed_median", 9.0),
    ),
)
def test_checksum_valid_semantic_tampering_is_rejected(
    tmp_path: Path, tamper: Callable[[Path], None]
) -> None:
    final = _published(tmp_path)
    tamper(final)
    _rewrite_checksums(final)
    with pytest.raises(ValueError):
        load_verified_pit_replication_success_v2(final)


def test_verified_success_result_is_typed_and_semantically_reconstructed(tmp_path: Path) -> None:
    final = _published(tmp_path)
    verified = load_verified_pit_replication_success_v2(final)
    assert isinstance(verified, VerifiedPITReplicationSuccessV2)
    assert verified.test_only is True
    assert verified.decision_date_count == 2
    assert verified.path_status == "PATH_DIAGNOSTICS_UNAVAILABLE"
    assert load_verified_pit_replication_artifact_v2(final).run_id == verified.run_id


def test_checksum_valid_population_lineage_tampering_is_rejected(tmp_path: Path) -> None:
    final = _published(tmp_path)
    path = final / "candidate_populations.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "universe_row_id"] = "unrelated-universe-row"
    frame.to_parquet(path, index=False)
    _rewrite_checksums(final)
    with pytest.raises(ValueError, match="input evidence identity|lineage"):
        load_verified_pit_replication_success_v2(final)
