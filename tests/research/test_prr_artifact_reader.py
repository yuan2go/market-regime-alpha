from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_regime_alpha.research.mr1_candidate_baselines import CandidateBaselineId
from market_regime_alpha.research.prr_artifact_reader import (
    load_verified_mr1_run,
    load_verified_prr_dataset,
)
from market_regime_alpha.research.prr_artifact_schemas import (
    MR1_BASELINE_PRIMARY_SEED,
    MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
    MR1_CASH_LOCK_POLICY_ID,
    MR1_COST_SCENARIOS,
    MR1_EXIT_TIMES,
    MR1_MISSING_WEIGHT_POLICY_ID,
    MR1_RUN_SCHEMA,
    PRR_DATASET_SCHEMA,
)


TZ = ZoneInfo("Asia/Shanghai")
DAY_1 = date(2026, 1, 5)
DAY_2 = date(2026, 1, 6)
ACCEPTED = "000001.SZ"
REJECTED = "000002.SZ"


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
    prepared_rows = []
    bar_rows = []
    for day in (DAY_1, DAY_2):
        timestamp = datetime(day.year, day.month, day.day, 14, 50, tzinfo=TZ).isoformat()
        prepared_rows.append(
            {
                "symbol": ACCEPTED,
                "session_date": day.isoformat(),
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.2,
                "amount": 100.0,
                "reference_price": 10.0,
                "reference_timestamp": timestamp,
                "source_kinds": "LOCAL",
            }
        )
        bar_rows.append(
            {
                "symbol": ACCEPTED,
                "timestamp": timestamp,
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.2,
                "volume": 10.0,
                "amount": 100.0,
                "source": "LOCAL",
            }
        )
    pd.DataFrame(prepared_rows).to_parquet(root / "prepared_sessions.parquet", index=False)
    pd.DataFrame(bar_rows).to_parquet(root / "bars.parquet", index=False)
    pd.DataFrame([{"decision_date": DAY_1.isoformat(), "symbol": ACCEPTED}]).to_parquet(
        root / "decision_snapshots.parquet", index=False
    )
    pd.DataFrame(
        [
            {
                "decision_date": DAY_1.isoformat(),
                "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
                "model_id": "fixed-b0",
                "symbol": ACCEPTED,
            }
        ]
    ).to_parquet(root / "candidate_rankings.parquet", index=False)
    manifest = {
        "schema_version": PRR_DATASET_SCHEMA.schema_version,
        "dataset_id": "prr-dataset-test",
        "data_eligibility": "EXPLORATORY",
        "symbol_count": 2,
        "accepted_symbol_count": 1,
        "session_count": 2,
        "decision_count": 1,
        "row_counts": {
            "bars": 2,
            "prepared_sessions": 2,
            "decision_snapshots": 1,
            "candidate_rankings": 1,
        },
        "date_range": {"start": DAY_1.isoformat(), "end": DAY_2.isoformat()},
        "quality_disposition": "PASS",
        "retrieved_at": datetime(2026, 1, 7, tzinfo=TZ).isoformat(),
    }
    (root / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    quality = {
        "disposition": "PASS",
        "quality_gate": {
            "requested_symbols": [ACCEPTED, REJECTED],
            "accepted_symbols": [ACCEPTED],
            "common_session_dates": [DAY_1.isoformat(), DAY_2.isoformat()],
            "required_session_count": 2,
            "minimum_accepted_symbols": 1,
            "dispositions": [
                {
                    "symbol": ACCEPTED,
                    "code": "ACCEPTED",
                    "complete_session_count": 2,
                    "findings": [],
                },
                {
                    "symbol": REJECTED,
                    "code": "REJECTED_FETCH_FAILURE",
                    "complete_session_count": 0,
                    "findings": [
                        {"code": "FETCH_FAILED", "message": "retained failure", "critical": True}
                    ],
                },
            ],
        },
    }
    (root / "data_quality.json").write_text(json.dumps(quality), encoding="utf-8")
    (root / "limitations.json").write_text(json.dumps(["AUXILIARY_DATA_ONLY"]), encoding="utf-8")
    _checksums(root)
    assert frozenset(item.name for item in root.iterdir()) == PRR_DATASET_SCHEMA.required_files
    return root


def _baseline_rows() -> list[dict[str, object]]:
    rows = []
    for exit_time in MR1_EXIT_TIMES:
        for scenario in MR1_COST_SCENARIOS:
            for baseline_id in CandidateBaselineId:
                is_gross = baseline_id in {
                    CandidateBaselineId.ALL_CANDIDATE_GROSS_V1,
                    CandidateBaselineId.MATCHED_K_HASH_GROSS_V1,
                }
                rows.append(
                    {
                        "schema_version": MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
                        "decision_date": DAY_1.isoformat(),
                        "exit_time": exit_time,
                        "cost_scenario": scenario,
                        "baseline_id": baseline_id.value,
                        "baseline_seed": MR1_BASELINE_PRIMARY_SEED,
                        "baseline_selection_id": "test-selection-v1",
                        "top_k": 5,
                        "gross_return": 0.01,
                        "net_return": 0.01 if is_gross else 0.009,
                        "candidate_symbol_count": 20,
                        "selected_symbol_count": (
                            20
                            if baseline_id
                            in {
                                CandidateBaselineId.ALL_CANDIDATE_GROSS_V1,
                                CandidateBaselineId.ALL_CANDIDATE_NET_DIAGNOSTIC_V1,
                            }
                            else 5
                        ),
                        "observed_weight": 1.0,
                        "missing_weight": 0.0,
                        "cash_locked_weight": 0.0,
                        "baseline_slot_status": "EXECUTED",
                        "selection_algorithm_id": "test-v1",
                        "cost_policy_id": "test-cost-v1",
                        "cash_lock_policy_id": MR1_CASH_LOCK_POLICY_ID,
                        "missing_weight_policy_id": MR1_MISSING_WEIGHT_POLICY_ID,
                        "data_eligibility": "EXPLORATORY",
                    }
                )
    return rows


def _mr1_run(root: Path, dataset_id: str = "prr-dataset-test") -> Path:
    root.mkdir()
    manifest = {
        "schema_version": MR1_RUN_SCHEMA.schema_version,
        "run_id": root.name,
        "dataset_id": dataset_id,
        "data_eligibility": "EXPLORATORY",
        "required_artifacts": sorted(MR1_RUN_SCHEMA.required_files),
        "candidate_daily_baseline_schema_version": MR1_CANDIDATE_BASELINE_SCHEMA_VERSION,
        "top_k": 5,
        "exit_times": list(MR1_EXIT_TIMES),
        "cost_scenarios": list(MR1_COST_SCENARIOS),
        "run_identity": {"baseline_seed": MR1_BASELINE_PRIMARY_SEED},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pd.DataFrame([{"decision_date": DAY_1.isoformat(), "value": 0.01}]).to_parquet(
        root / "morning_targets.parquet", index=False
    )
    equity = [
        {
            "session_date": DAY_1.isoformat(),
            "model_id": "fixed-b0",
            "exit_time": exit_time,
            "cost_scenario": scenario,
            "gross_return": 0.01,
            "net_return": 0.009,
            "cash_ratio": 0.0,
        }
        for exit_time in MR1_EXIT_TIMES
        for scenario in MR1_COST_SCENARIOS
    ]
    pd.DataFrame(equity).to_parquet(root / "daily_equity.parquet", index=False)
    pd.DataFrame([{"model_id": "fixed-b0"}]).to_parquet(
        root / "chronological_model_metrics.parquet", index=False
    )
    pd.DataFrame(_baseline_rows()).to_parquet(
        root / "candidate_daily_baselines.parquet", index=False
    )
    for name in ("orders.parquet", "fills.parquet", "trades.parquet"):
        pd.DataFrame([{"decision_date": DAY_1.isoformat()}]).to_parquet(root / name, index=False)
    (root / "limitations.json").write_text("[]", encoding="utf-8")
    (root / "model_target_matrix.csv").write_text("model_id\nfixed-b0\n", encoding="utf-8")
    (root / "exit_time_comparison.json").write_text("{}", encoding="utf-8")
    (root / "metrics.json").write_text("[]", encoding="utf-8")
    (root / "report.md").write_text("# MR-1\n", encoding="utf-8")
    _checksums(root)
    assert frozenset(item.name for item in root.iterdir()) == MR1_RUN_SCHEMA.required_files
    return root


def _rewrite_parquet(root: Path, filename: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(root / filename, index=False)
    _checksums(root)


def test_verified_dataset_preserves_rejected_quality_evidence(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "dataset")
    before = (root / "SHA256SUMS.json").read_bytes()

    verified = load_verified_prr_dataset(root)

    assert verified.dataset_id == "prr-dataset-test"
    assert verified.decision_dates == (DAY_1,)
    assert verified.prepared.accepted_symbols == (ACCEPTED,)
    assert verified.prepared.quality.requested_symbols == (ACCEPTED, REJECTED)
    assert verified.prepared.quality.dispositions[1].findings[0].code == "FETCH_FAILED"
    assert verified.quality["disposition"] == "PASS"
    assert (root / "SHA256SUMS.json").read_bytes() == before


def test_dataset_checksum_tamper_fails_closed(tmp_path: Path) -> None:
    root = _dataset(tmp_path / "dataset")
    (root / "bars.parquet").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="artifact checksum mismatch: bars.parquet"):
        load_verified_prr_dataset(root)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    (
        ("decision_date", DAY_2.isoformat(), "ranking dates must equal Decision Dates"),
        ("symbol", "999999.SZ", "ranking symbols must belong"),
    ),
)
def test_dataset_cross_table_ranking_invariants_fail_closed(
    tmp_path: Path,
    column: str,
    value: str,
    message: str,
) -> None:
    root = _dataset(tmp_path / "dataset")
    frame = pd.read_parquet(root / "candidate_rankings.parquet")
    frame.loc[0, column] = value
    _rewrite_parquet(root, "candidate_rankings.parquet", frame)

    with pytest.raises(ValueError, match=message):
        load_verified_prr_dataset(root)


@pytest.mark.parametrize(
    "filename",
    (
        "daily_equity.parquet",
        "morning_targets.parquet",
        "chronological_model_metrics.parquet",
        "candidate_daily_baselines.parquet",
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


def test_mr1_baseline_duplicate_key_fails_after_valid_checksum(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    frame = pd.read_parquet(root / "candidate_daily_baselines.parquet")
    _rewrite_parquet(root, "candidate_daily_baselines.parquet", pd.concat([frame, frame.iloc[[0]]]))

    with pytest.raises(ValueError, match="primary keys must be present and unique"):
        load_verified_mr1_run(root)


def test_mr1_baseline_incomplete_cardinality_fails(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    frame = pd.read_parquet(root / "candidate_daily_baselines.parquet").iloc[:-1]
    _rewrite_parquet(root, "candidate_daily_baselines.parquet", frame)

    with pytest.raises(ValueError, match="baseline family is incomplete|cardinality is incomplete"):
        load_verified_mr1_run(root)


def test_mr1_baseline_weight_must_reconcile(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    frame = pd.read_parquet(root / "candidate_daily_baselines.parquet")
    frame.loc[0, "missing_weight"] = 0.1
    _rewrite_parquet(root, "candidate_daily_baselines.parquet", frame)

    with pytest.raises(ValueError, match="weights must reconcile"):
        load_verified_mr1_run(root)


def test_mr1_baseline_gross_and_net_rows_must_share_selection_semantics(
    tmp_path: Path,
) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    frame = pd.read_parquet(root / "candidate_daily_baselines.parquet")
    mask = frame["baseline_id"] == CandidateBaselineId.MATCHED_K_HASH_NET_V1.value
    frame.loc[mask, "observed_weight"] = 0.8
    frame.loc[mask, "missing_weight"] = 0.2
    _rewrite_parquet(root, "candidate_daily_baselines.parquet", frame)

    with pytest.raises(ValueError, match="matched-K gross and net baselines must share"):
        load_verified_mr1_run(root)


def test_mr1_close_cash_lock_must_match_model_equity(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    baselines = pd.read_parquet(root / "candidate_daily_baselines.parquet")
    close = baselines["exit_time"] == "CLOSE"
    baselines.loc[close, "baseline_slot_status"] = "CASH_LOCKED"
    baselines.loc[close, "gross_return"] = 0.0
    baselines.loc[close, "net_return"] = 0.0
    baselines.loc[close, "selected_symbol_count"] = 0
    baselines.loc[close, "observed_weight"] = 0.0
    baselines.loc[close, "missing_weight"] = 0.0
    baselines.loc[close, "cash_locked_weight"] = 1.0
    _rewrite_parquet(root, "candidate_daily_baselines.parquet", baselines)

    with pytest.raises(ValueError, match="share cash-lock semantics"):
        load_verified_mr1_run(root)


def test_mr1_daily_equity_dates_must_match_baselines(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    frame = pd.read_parquet(root / "daily_equity.parquet")
    frame["session_date"] = DAY_2.isoformat()
    _rewrite_parquet(root, "daily_equity.parquet", frame)

    with pytest.raises(ValueError, match="daily equity, baseline, and Target dates must match"):
        load_verified_mr1_run(root)


def test_mr1_manifest_required_artifacts_must_match_contract(tmp_path: Path) -> None:
    root = _mr1_run(tmp_path / "mr1-test")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["required_artifacts"] = ["manifest.json"]
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    _checksums(root)

    with pytest.raises(ValueError, match="required_artifacts must match"):
        load_verified_mr1_run(root)
