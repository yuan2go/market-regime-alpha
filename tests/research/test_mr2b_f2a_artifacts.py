from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_regime_alpha.research.mr1_candidate_baselines import (
    build_candidate_daily_baselines,
    build_model_candidate_populations,
)
from market_regime_alpha.research.mr1_research_runner import mr1_cost_scenarios
from market_regime_alpha.research.mr2b_context import CONTEXT_GRID
from market_regime_alpha.research.mr2b_f2a import (
    F2AInputs,
    build_f2a_inputs,
    build_primary_comparison_input,
)
from market_regime_alpha.research.mr2b_f2a_artifacts import (
    F2A_LIMITATIONS,
    build_f2a_run_identity,
    publish_f2a_artifact,
)
from market_regime_alpha.research.mr2b_f2a_reader import load_verified_f2a_run
from market_regime_alpha.research.prr_artifact_reader import (
    VerifiedMR1Run,
    VerifiedPRRDataset,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeDispositionCode,
    CompositeQualityReport,
    CompositeSourceKind,
    CompositeSymbolDisposition,
    PreparedCompositeData,
)


PREVIOUS = date(2026, 1, 2)
DAY = date(2026, 1, 5)
DATASET_ID = "prr-dataset-test"
MR1_RUN_ID = "mr1-test"
MODEL = "prr-mvp-1-b1-e-v1"
TARGET = "target-r5-decision-reference-to-next-session-close-return-v1"
SYMBOL = "000001.SZ"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _bar(day: date, endpoint: time, *, close: float, amount: float) -> CompositeBar:
    return CompositeBar(
        symbol=SYMBOL,
        timestamp=datetime.combine(day, endpoint, tzinfo=SHANGHAI),
        open=close,
        high=close * 1.001,
        low=close * 0.999,
        close=close,
        volume=100.0,
        amount=amount,
        source=CompositeSourceKind.LOCAL,
    )


def _verified_inputs(tmp_path: Path) -> tuple[VerifiedPRRDataset, VerifiedMR1Run]:
    dataset_root = tmp_path / "dataset"
    mr1_root = tmp_path / "mr1"
    dataset_root.mkdir(parents=True)
    mr1_root.mkdir(parents=True)
    (dataset_root / "dataset_manifest.json").write_text("{}\n", encoding="utf-8")
    (dataset_root / "SHA256SUMS.json").write_text("{}\n", encoding="utf-8")
    (mr1_root / "manifest.json").write_text("{}\n", encoding="utf-8")
    (mr1_root / "SHA256SUMS.json").write_text("{}\n", encoding="utf-8")

    bars = tuple(
        [
            *(_bar(PREVIOUS, endpoint, close=10.0, amount=100.0) for endpoint in CONTEXT_GRID),
            _bar(PREVIOUS, time(15, 0), close=10.0, amount=50.0),
            *(_bar(DAY, endpoint, close=10.1, amount=110.0) for endpoint in CONTEXT_GRID),
        ]
    )
    quality = CompositeQualityReport(
        requested_symbols=(SYMBOL,),
        accepted_symbols=(SYMBOL,),
        dispositions=(
            CompositeSymbolDisposition(
                symbol=SYMBOL,
                code=CompositeDispositionCode.ACCEPTED,
                complete_session_count=2,
                findings=(),
            ),
        ),
        common_session_dates=(PREVIOUS, DAY),
        required_session_count=1,
        minimum_accepted_symbols=1,
    )
    prepared = PreparedCompositeData(
        accepted_symbols=(SYMBOL,),
        common_session_dates=(PREVIOUS, DAY),
        sessions=(),
        quality=quality,
        limitations=(),
    )
    rankings = (
        {
            "decision_date": DAY.isoformat(),
            "target_id": TARGET,
            "model_id": MODEL,
            "symbol": SYMBOL,
            "eligible_for_ranking": True,
            "rank": 1,
        },
    )
    dataset = VerifiedPRRDataset(
        root=dataset_root,
        dataset_id=DATASET_ID,
        manifest={},
        quality={},
        prepared=prepared,
        bars=bars,
        ranking_rows=rankings,
        decision_dates=(DAY,),
        checksums_hash=_content_hash(dataset_root / "SHA256SUMS.json"),
    )
    target_rows = tuple(
        {
            "decision_date": DAY.isoformat(),
            "target_session_date": "2026-01-06",
            "target_id": target_id,
            "symbol": SYMBOL,
            "status": "AVAILABLE",
            "reference_price": 10.1,
            "exit_price": 10.2,
            "exit_time": exit_time,
        }
        for exit_time, target_id in (
            ("09:35", "NEXT_SESSION_0935_RETURN"),
            ("10:00", "NEXT_SESSION_1000_RETURN"),
            ("10:30", "NEXT_SESSION_1030_RETURN"),
            ("CLOSE", "NEXT_SESSION_CLOSE_RETURN"),
        )
    )
    populations = build_model_candidate_populations(
        dataset_id=DATASET_ID, ranking_rows=rankings
    )
    baselines = build_candidate_daily_baselines(
        populations=populations,
        target_rows=target_rows,
        decision_dates=(DAY,),
        cost_configs=mr1_cost_scenarios(),
        top_k=1,
        baseline_seed=17,
    )
    equity = tuple(
        {
            "session_date": DAY.isoformat(),
            "model_id": MODEL,
            "exit_time": exit_time,
            "cost_scenario": scenario,
            "gross_return": 0.02,
            "net_return": 0.019,
        }
        for exit_time in ("09:35", "10:00", "10:30", "CLOSE")
        for scenario in ("LOW", "BASE", "HIGH")
    )
    mr1 = VerifiedMR1Run(
        root=mr1_root,
        run_id=MR1_RUN_ID,
        dataset_id=DATASET_ID,
        manifest={"top_k": 1},
        morning_targets=target_rows,
        daily_equity=equity,
        metrics=(),
        candidate_daily_baselines=baselines.baseline_rows,
        matched_k_selections=baselines.selection_rows,
        checksums_hash=_content_hash(mr1_root / "SHA256SUMS.json"),
    )
    return dataset, mr1


def _publish(tmp_path: Path) -> tuple[Path, VerifiedPRRDataset, VerifiedMR1Run, F2AInputs]:
    dataset, mr1 = _verified_inputs(tmp_path)
    inputs = build_f2a_inputs(dataset=dataset, mr1=mr1, seeds=(17,))
    identity = build_f2a_run_identity(
        dataset_root=dataset.root,
        mr1_root=mr1.root,
        dataset_id=dataset.dataset_id,
        mr1_run_id=mr1.run_id,
        watchlist_id=inputs.contexts[0].watchlist_id,
        top_k=1,
        runner_path=Path("scripts/run_mr2b_f2a_conditionality_inputs.py").resolve(),
        seeds=(17,),
    )
    root = publish_f2a_artifact(
        output_root=tmp_path / "runs", run_identity=identity, inputs=inputs
    )
    return root, dataset, mr1, inputs


def _rewrite_checksums(root: Path) -> None:
    payload = {
        path.name: _content_hash(path)
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def test_f2a_artifact_has_exact_files_and_is_semantically_verified(tmp_path: Path) -> None:
    root, dataset, mr1, inputs = _publish(tmp_path)

    verified = load_verified_f2a_run(root, dataset=dataset, mr1=mr1)

    assert verified.manifest["data_eligibility"] == "EXPLORATORY"
    assert len(verified.context_symbol_evidence) == 1
    expected_primary = build_primary_comparison_input(inputs.daily_excess_rows)
    assert verified.primary_comparison_input["UP_count"] == expected_primary["UP_count"]
    assert verified.primary_comparison_input["descriptive_mean_difference"] == expected_primary[
        "descriptive_mean_difference"
    ]
    assert tuple(json.loads((root / "limitations.json").read_text())) == F2A_LIMITATIONS


def test_publisher_has_no_caller_supplied_primary_or_coverage_channel() -> None:
    assert "primary_comparison_input" not in F2AInputs.__dataclass_fields__
    assert "coverage" not in F2AInputs.__dataclass_fields__


@pytest.mark.parametrize(
    ("filename", "column", "value"),
    (
        ("auxiliary_watchlist_context.parquet", "watchlist_direction", "DOWN"),
        ("auxiliary_watchlist_context.parquet", "coverage", 0.5),
        ("auxiliary_watchlist_context.parquet", "expected_bar_count_per_symbol", 45),
        ("auxiliary_watchlist_context.parquet", "cutoff_time", "2026-01-05T14:45:00+08:00"),
        ("auxiliary_watchlist_context_symbol_evidence.parquet", "return_to_1450", -9.0),
        ("multi_seed_matched_k_selections.parquet", "slot_index", 2),
        ("multi_seed_matched_k_selections.parquet", "symbol", "999999.SZ"),
        ("multi_seed_matched_k_selections.parquet", "selection_id", "sha256:fake"),
        ("multi_seed_matched_k_returns.parquet", "gross_return", 9.0),
        ("multi_seed_matched_k_returns.parquet", "observed_weight", 0.5),
        ("multi_seed_matched_k_returns.parquet", "selection_status", "CASH_LOCKED"),
        ("multi_seed_matched_k_returns.parquet", "selection_id", "sha256:fake"),
        ("multi_seed_null_summary.parquet", "net_median", 9.0),
        ("multi_seed_null_summary.parquet", "net_p10", 9.0),
        ("multi_seed_null_summary.parquet", "model_net_percentile", 0.99),
        ("multi_seed_null_summary.parquet", "unique_selection_count", 999),
        ("daily_candidate_excess.parquet", "net_lift_vs_multiseed_median", 9.0),
        ("daily_candidate_excess.parquet", "gross_lift_vs_all_candidate", 9.0),
        ("daily_candidate_excess.parquet", "cost_drag_difference_primary_seed", 9.0),
        ("daily_candidate_excess.parquet", "context_id", "sha256:fake"),
        ("daily_candidate_excess.parquet", "population_hash", "sha256:fake"),
    ),
)
def test_reader_rejects_checksum_valid_semantic_table_tamper(
    tmp_path: Path, filename: str, column: str, value: object
) -> None:
    root, dataset, mr1, _ = _publish(tmp_path / filename.replace(".", "-"))
    path = root / filename
    frame = pd.read_parquet(path)
    frame.loc[0, column] = value
    frame.to_parquet(path, index=False)
    _rewrite_checksums(root)

    with pytest.raises(ValueError, match="reconstructible|primary keys"):
        load_verified_f2a_run(root, dataset=dataset, mr1=mr1)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("UP_count", 999),
        ("DOWN_count", 999),
        ("descriptive_mean_difference", 99.0),
        ("model_id", "stale-model"),
    ),
)
def test_reader_rejects_checksum_valid_primary_projection_tamper(
    tmp_path: Path, field: str, value: object
) -> None:
    root, dataset, mr1, _ = _publish(tmp_path / field)
    path = root / "primary_comparison_input.json"
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _rewrite_checksums(root)

    with pytest.raises(ValueError, match="Primary Input"):
        load_verified_f2a_run(root, dataset=dataset, mr1=mr1)


def test_reader_rejects_checksum_valid_identity_and_limitation_tamper(tmp_path: Path) -> None:
    root, dataset, mr1, _ = _publish(tmp_path)
    limitations = root / "limitations.json"
    limitations.write_text(json.dumps(list(F2A_LIMITATIONS[:-1])) + "\n", encoding="utf-8")
    _rewrite_checksums(root)
    with pytest.raises(ValueError, match="limitations"):
        load_verified_f2a_run(root, dataset=dataset, mr1=mr1)


def test_reader_rejects_checksum_valid_run_identity_tamper(tmp_path: Path) -> None:
    root, dataset, mr1, _ = _publish(tmp_path)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["run_identity"]["quantile_method_id"] = "tampered-method"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _rewrite_checksums(root)

    with pytest.raises(ValueError, match="run ID|identity"):
        load_verified_f2a_run(root, dataset=dataset, mr1=mr1)


def test_reader_rejects_checksum_valid_coverage_tamper(tmp_path: Path) -> None:
    root, dataset, mr1, _ = _publish(tmp_path)
    path = root / "coverage.json"
    coverage = json.loads(path.read_text())
    coverage["context_label_counts"]["UP"] = 999
    path.write_text(json.dumps(coverage, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _rewrite_checksums(root)

    with pytest.raises(ValueError, match="coverage"):
        load_verified_f2a_run(root, dataset=dataset, mr1=mr1)


def test_reader_requires_matching_verified_upstream_inputs(tmp_path: Path) -> None:
    root, dataset, mr1, _ = _publish(tmp_path)

    with pytest.raises(ValueError, match="upstream input identity"):
        load_verified_f2a_run(
            root,
            dataset=replace(dataset, dataset_id="prr-dataset-wrong"),
            mr1=mr1,
        )
