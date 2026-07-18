from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_regime_alpha.research.prr_artifact_reader import (
    MR1_DAILY_CANDIDATE_BASELINE_SCHEMA_VERSION,
    MR1_RUN_FILENAMES,
    PRR_DATASET_FILENAMES,
    load_verified_mr1_run,
    load_verified_prr_dataset,
)


TZ = ZoneInfo("Asia/Shanghai")


def _digest(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _checksums(root: Path) -> None:
    payload = {
        item.name: _digest(item)
        for item in sorted(root.iterdir())
        if item.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _dataset(root: Path) -> Path:
    root.mkdir()
    timestamp = datetime(2026, 1, 5, 14, 50, tzinfo=TZ).isoformat()
    pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "session_date": date(2026, 1, 5).isoformat(),
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.2,
                "amount": 100.0,
                "reference_price": 10.0,
                "reference_timestamp": timestamp,
                "source_kinds": "LOCAL",
            }
        ]
    ).to_parquet(root / "prepared_sessions.parquet", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "timestamp": timestamp,
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.2,
                "volume": 10.0,
                "amount": 100.0,
                "source": "LOCAL",
            }
        ]
    ).to_parquet(root / "bars.parquet", index=False)
    pd.DataFrame(
        [{"decision_date": date(2026, 1, 5).isoformat(), "symbol": "000001.SZ"}]
    ).to_parquet(root / "decision_snapshots.parquet", index=False)
    pd.DataFrame(
        [{"decision_date": date(2026, 1, 5).isoformat(), "model_id": "fixed-b0"}]
    ).to_parquet(root / "candidate_rankings.parquet", index=False)
    (root / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "prr-mvp-1-dataset-v1",
                "dataset_id": "prr-dataset-test",
                "data_eligibility": "EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    (root / "data_quality.json").write_text("{}", encoding="utf-8")
    (root / "limitations.json").write_text("[]", encoding="utf-8")
    _checksums(root)
    assert frozenset(item.name for item in root.iterdir()) == PRR_DATASET_FILENAMES
    return root


def _mr1_run(root: Path, dataset_id: str = "prr-dataset-test") -> Path:
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "mr-1-run-v2",
                "run_id": root.name,
                "dataset_id": dataset_id,
                "data_eligibility": "EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    records = [{"decision_date": "2026-01-05", "value": 0.01}]
    for name in ("morning_targets.parquet", "daily_equity.parquet", "chronological_model_metrics.parquet"):
        pd.DataFrame(records).to_parquet(root / name, index=False)
    pd.DataFrame(
        [
            {
                "schema_version": MR1_DAILY_CANDIDATE_BASELINE_SCHEMA_VERSION,
                "data_eligibility": "EXPLORATORY",
                "candidate_gross_return": 0.01,
            }
        ]
    ).to_parquet(root / "candidate_daily_baseline.parquet", index=False)
    for name in ("orders.parquet", "fills.parquet", "trades.parquet"):
        pd.DataFrame(records).to_parquet(root / name, index=False)
    (root / "limitations.json").write_text("[]", encoding="utf-8")
    (root / "model_target_matrix.csv").write_text("model_id\nfixed-b0\n", encoding="utf-8")
    (root / "exit_time_comparison.json").write_text("{}", encoding="utf-8")
    (root / "metrics.json").write_text("[]", encoding="utf-8")
    (root / "report.md").write_text("# MR-1\n", encoding="utf-8")
    _checksums(root)
    assert frozenset(item.name for item in root.iterdir()) == MR1_RUN_FILENAMES
    return root


def test_verified_dataset_loading_is_checksum_protected_and_non_mutating(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "dataset")
    before = (root / "SHA256SUMS.json").read_bytes()

    verified = load_verified_prr_dataset(root)

    assert verified.dataset_id == "prr-dataset-test"
    assert verified.decision_dates == (date(2026, 1, 5),)
    assert (root / "SHA256SUMS.json").read_bytes() == before
    (root / "bars.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact checksum mismatch: bars.parquet"):
        load_verified_prr_dataset(root)


@pytest.mark.parametrize(
    "filename",
    (
        "daily_equity.parquet",
        "morning_targets.parquet",
        "chronological_model_metrics.parquet",
        "candidate_daily_baseline.parquet",
    ),
)
def test_verified_mr1_run_fails_closed_for_any_protected_table(tmp_path: Path, filename: str) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    load_verified_mr1_run(root, expected_dataset_id="prr-dataset-test")

    (root / filename).write_bytes(b"tampered")

    with pytest.raises(ValueError, match=f"artifact checksum mismatch: {filename}"):
        load_verified_mr1_run(root, expected_dataset_id="prr-dataset-test")


def test_verified_mr1_run_rejects_dataset_id_mismatch(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")

    with pytest.raises(ValueError, match="MR-1 Dataset ID does not match"):
        load_verified_mr1_run(root, expected_dataset_id="prr-dataset-other")
