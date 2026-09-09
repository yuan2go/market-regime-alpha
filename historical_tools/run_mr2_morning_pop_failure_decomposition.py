#!/usr/bin/env python3
"""Run bounded MR-2 diagnostics from an immutable Dataset and corrected MR-1 artifact."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_regime_alpha.research.mr2_failure_decomposition import (  # noqa: E402
    MR2_SCHEMA_VERSION,
    decompose_model_failures,
    feature_target_diagnostics,
    target_coverage,
)
from market_regime_alpha.research.prr_artifact_reader import (  # noqa: E402
    load_verified_mr1_run,
    load_verified_prr_dataset,
)


DEFAULT_ROOT = PROJECT_ROOT / "data" / "processed" / "mr2_failure_decomposition_runs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mr1-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset, mr1_run = args.dataset.resolve(), args.mr1_run.resolve()
    verified_dataset = load_verified_prr_dataset(dataset)
    verified_mr1 = load_verified_mr1_run(
        mr1_run,
        dataset=verified_dataset,
        expected_dataset_id=verified_dataset.dataset_id,
    )
    dataset_manifest = dict(verified_dataset.manifest)
    mr1_manifest = dict(verified_mr1.manifest)
    prepared = verified_dataset.prepared
    rankings = tuple(dict(row) for row in verified_dataset.ranking_rows)
    targets = [dict(row) for row in verified_mr1.morning_targets]
    mr1_metrics = [dict(row) for row in verified_mr1.metrics]
    ic, spreads = feature_target_diagnostics(ranking_rows=rankings, target_rows=targets)
    coverage = target_coverage(targets)
    failures = [dict(row) for row in decompose_model_failures(mr1_metrics=mr1_metrics, target_coverage=coverage)]
    equity = [dict(row) for row in verified_mr1.daily_equity]
    _add_day_contributions(failures, equity)
    regime = _regime_slices(prepared, rankings, targets, equity)
    summary = _failure_summary(ic, failures, regime)
    run_id = _run_id(dataset_manifest, mr1_manifest, verified_dataset.root)
    final = _write_run(args.output_root, run_id, dataset_manifest, mr1_manifest, ic, spreads, targets, failures, regime, coverage, summary)
    print(f"MR-2 completed: {final}")
    return 0


def _add_day_contributions(failures: list[dict[str, Any]], equity: list[dict[str, Any]]) -> None:
    for row in failures:
        daily = [item for item in equity if item["model_id"] == row["model_id"] and item["exit_time"] == row["exit_time"] and item["cost_scenario"] == "BASE"]
        values = [float(item["net_return"]) for item in daily]
        row["best_day_contribution"] = max(values) if values else None
        row["worst_day_contribution"] = min(values) if values else None


def _regime_slices(prepared: Any, rankings: tuple[dict[str, Any], ...], targets: list[dict[str, Any]], equity: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use only current/pre-decision composite data; emit explicit unavailable ETF context."""

    dates = tuple(sorted({session.session_date for session in prepared.sessions}))
    prior = {dates[index]: dates[index - 1] for index in range(1, len(dates))}
    regime: dict[str, dict[str, str]] = {}
    for current, previous in prior.items():
        sessions = [prepared.session_for(symbol, current) for symbol in prepared.accepted_symbols]
        previous_sessions = [prepared.session_for(symbol, previous) for symbol in prepared.accepted_symbols]
        market_move = sum(item.reference_price / before.close - 1.0 for item, before in zip(sessions, previous_sessions, strict=True)) / len(sessions)
        volatility = sum((item.high - item.low) / item.close for item in sessions) / len(sessions)
        amount_change = sum(item.amount / before.amount - 1.0 for item, before in zip(sessions, previous_sessions, strict=True) if before.amount > 0.0) / len(sessions)
        breadth = sum(item.reference_price > before.close for item, before in zip(sessions, previous_sessions, strict=True)) / len(sessions)
        regime[current.isoformat()] = {"market_direction": "UP" if market_move >= 0 else "DOWN", "market_volatility": "HIGH" if volatility >= 0.03 else "LOW", "market_amount": "EXPANDING" if amount_change >= 0 else "CONTRACTING", "candidate_breadth": "STRONG" if breadth >= 0.5 else "WEAK", "etf_sector_context": "UNAVAILABLE"}
    target_index = {(str(row["decision_date"]), str(row["symbol"]), str(row["target_id"])): row for row in targets}
    close_rankings = [row for row in rankings if row["target_id"] == "target-r5-decision-reference-to-next-session-close-return-v1"]
    output: list[dict[str, Any]] = []
    for dimension in ("market_direction", "market_volatility", "market_amount", "candidate_breadth", "etf_sector_context"):
        values = sorted({item[dimension] for item in regime.values()})
        for value in values:
            selected_dates = {day for day, labels in regime.items() if labels[dimension] == value}
            for (model_id, exit_time), group in _base_equity_groups(equity).items():
                rows = [row for row in group if row["session_date"] in selected_dates]
                if not rows:
                    continue
                model_rows = [row for row in close_rankings if row["model_id"] == model_id and row["decision_date"] in selected_dates]
                rank_ic = _mean_rank_ic(model_rows, target_index, "NEXT_SESSION_1030_RETURN")
                selected = [row for row in model_rows if row["rank"] is not None and int(row["rank"]) <= 5]
                mfe = _rate(selected, target_index, "MORNING_1030_MFE", lambda target: float(target["value"]) >= 0.005)
                up_first = _rate(selected, target_index, "MORNING_UP_005_DOWN_005_V1", lambda target: target.get("outcome") == "UP_FIRST")
                baseline = _target_baseline(selected_dates, target_index, _exit_target(exit_time))
                output.append({"schema_version": MR2_SCHEMA_VERSION, "dimension": dimension, "slice": value, "model_id": model_id, "exit_time": exit_time, "session_count": len(rows), "net_return": _compound(rows), "top5_excess": _compound(rows) - baseline if baseline is not None else None, "rank_ic": rank_ic, "mfe_hit_rate": mfe, "up_first_rate": up_first, "data_status": "UNAVAILABLE" if dimension == "etf_sector_context" else "AVAILABLE", "data_eligibility": "EXPLORATORY"})
    return output


def _base_equity_groups(equity: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in equity:
        if row["cost_scenario"] == "BASE":
            groups.setdefault((str(row["model_id"]), str(row["exit_time"])), []).append(row)
    return groups


def _compound(rows: list[dict[str, Any]]) -> float:
    equity = 1.0
    for row in rows:
        equity *= 1.0 + float(row["net_return"])
    return equity - 1.0


def _exit_target(exit_time: str) -> str:
    return {"09:35": "NEXT_SESSION_0935_RETURN", "10:00": "NEXT_SESSION_1000_RETURN", "10:30": "NEXT_SESSION_1030_RETURN", "CLOSE": "NEXT_SESSION_CLOSE_RETURN"}[exit_time]


def _target_baseline(dates: set[str], targets: dict[tuple[str, str, str], dict[str, Any]], target_id: str) -> float | None:
    by_date: dict[str, list[float]] = {}
    for (decision_date, _, candidate_target), row in targets.items():
        if decision_date in dates and candidate_target == target_id and row.get("status") == "AVAILABLE" and row.get("value") is not None:
            by_date.setdefault(decision_date, []).append(float(row["value"]))
    if not by_date:
        return None
    equity = 1.0
    for values in by_date.values():
        equity *= 1.0 + sum(values) / len(values)
    return equity - 1.0


def _mean_rank_ic(rows: list[dict[str, Any]], targets: dict[tuple[str, str, str], dict[str, Any]], target_id: str) -> float | None:
    by_date: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        target = targets.get((str(row["decision_date"]), str(row["symbol"]), target_id))
        if row.get("rank") is not None and target is not None and target.get("status") == "AVAILABLE" and target.get("value") is not None:
            by_date.setdefault(str(row["decision_date"]), []).append((-float(row["rank"]), float(target["value"])))
    ics = [_pearson([item[0] for item in values], [item[1] for item in values]) for values in by_date.values()]
    usable = [item for item in ics if item is not None]
    return sum(usable) / len(usable) if usable else None


def _rate(rows: list[dict[str, Any]], targets: dict[tuple[str, str, str], dict[str, Any]], target_id: str, predicate: Any) -> float | None:
    values = []
    for row in rows:
        target = targets.get((str(row["decision_date"]), str(row["symbol"]), target_id))
        if target is not None and target.get("status") == "AVAILABLE":
            values.append(bool(predicate(target)))
    return sum(values) / len(values) if values else None


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = (sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right)) ** 0.5
    return numerator / denominator if denominator else None


def _failure_summary(ic: tuple[dict[str, Any], ...], failures: list[dict[str, Any]], regime: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = [row for row in ic if row["scope"] == "AGGREGATE" and row["target_id"] in {"NEXT_SESSION_0935_RETURN", "NEXT_SESSION_1000_RETURN", "NEXT_SESSION_1030_RETURN"}]
    mean_abs_ic = sum(abs(float(row["spearman_rank_ic"])) for row in aggregate if row["spearman_rank_ic"] is not None) / max(1, sum(row["spearman_rank_ic"] is not None for row in aggregate))
    gross_positive = any(float(row["gross_candidate_excess"]) > 0.0 for row in failures)
    net_positive = any(float(row["net_candidate_excess"]) > 0.0 for row in failures)
    assessments = []
    if mean_abs_ic < 0.03 and not gross_positive:
        assessments.append("A. EXISTING_FEATURES_HAVE_NO_MORNING_SIGNAL")
    if gross_positive and not net_positive:
        assessments.append("B. WEAK_SIGNAL_ERASED_BY_COSTS")
    regime_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in regime:
        if row["data_status"] == "AVAILABLE" and row["session_count"] >= 10 and row["top5_excess"] is not None:
            regime_groups.setdefault((row["model_id"], row["exit_time"], row["dimension"]), []).append(row)
    regime_split = any(max(float(item["top5_excess"]) for item in group) > 0.0 and min(float(item["top5_excess"]) for item in group) <= 0.0 for group in regime_groups.values())
    if regime_split:
        assessments.append("C. SIGNAL_EXISTS_ONLY_IN_SPECIFIC_REGIMES")
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in failures:
        by_model.setdefault(str(row["model_id"]), []).append(row)
    exit_split = any(max(float(item["gross_candidate_excess"]) for item in group) > 0.0 and min(float(item["gross_candidate_excess"]) for item in group) <= 0.0 for group in by_model.values())
    if exit_split and not net_positive:
        assessments.append("D. RANKING_SIGNAL_EXISTS_BUT_FIXED_EXIT_IS_WRONG")
    if not assessments:
        assessments.append("A. EXISTING_FEATURES_HAVE_NO_MORNING_SIGNAL")
    return {"schema_version": MR2_SCHEMA_VERSION, "assessments": assessments, "mean_absolute_morning_spearman_ic": mean_abs_ic, "gross_positive_model_exit_exists": gross_positive, "net_positive_model_exit_exists": net_positive, "regime_slice_sign_split": regime_split, "data_eligibility": "EXPLORATORY", "next_work": "FEATURE_AND_TARGET_DESIGN_REVIEW" if assessments == ["A. EXISTING_FEATURES_HAVE_NO_MORNING_SIGNAL"] else "NO_MODEL_SELECTION"}


def _run_id(dataset: dict[str, Any], mr1: dict[str, Any], dataset_root: Path) -> str:
    payload = json.dumps({"dataset_id": dataset["dataset_id"], "dataset_checksums": _hash_path(dataset_root / "SHA256SUMS.json"), "mr1_run": mr1["run_id"], "mr1_manifest": _canonical(mr1), "runner_hash": _hash_path(Path(__file__))}, sort_keys=True, separators=(",", ":"))
    return f"mr2-{sha256(payload.encode()).hexdigest()[:20]}"


def _write_run(root: Path, run_id: str, dataset: dict[str, Any], mr1: dict[str, Any], ic: tuple[dict[str, Any], ...], spreads: tuple[dict[str, Any], ...], targets: list[dict[str, Any]], failures: list[dict[str, Any]], regime: list[dict[str, Any]], coverage: dict[str, float], summary: dict[str, Any]) -> Path:
    final, stage = root / run_id, root / f".{run_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"MR-2 run is immutable: {final}")
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "manifest.json", {"schema_version": "mr-2-run-v1", "run_id": run_id, "dataset_id": dataset["dataset_id"], "mr1_run_id": mr1["run_id"], "data_eligibility": "EXPLORATORY"})
        _write_parquet(stage / "feature_target_ic.parquet", ic)
        _write_parquet(stage / "feature_target_spreads.parquet", spreads)
        _write_parquet(stage / "morning_path_targets.parquet", targets)
        _write_parquet(stage / "model_failure_decomposition.parquet", failures)
        _write_parquet(stage / "regime_slice_metrics.parquet", regime)
        _write_json(stage / "target_coverage.json", coverage)
        _write_json(stage / "failure_summary.json", summary)
        _write_report(stage / "report.md", run_id, dataset["dataset_id"], summary, failures)
        _write_checksums(stage)
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _write_report(path: Path, run_id: str, dataset_id: str, summary: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for row in failures:
        for reason in row["failure_reasons"]:
            counts[reason] = counts.get(reason, 0) + 1
    lines = ["# MR-2 Morning-Pop Failure Decomposition", "", f"- Run ID: `{run_id}`", f"- Dataset ID: `{dataset_id}`", "- Authority: `EXPLORATORY`", "- No model winner selection or production approval.", "", "## Evidence-led conclusions", ""]
    lines.extend(f"- {item}" for item in summary["assessments"])
    lines.extend(("", "## Failure reason counts", "", "| Reason | Model/exit rows |", "| --- | ---: |"))
    lines.extend(f"| {reason} | {count} |" for reason, count in sorted(counts.items()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_checksums(path: Path) -> None:
    expected = _read_json(path / "SHA256SUMS.json")
    for name, digest in expected.items():
        if _hash_path(path / name) != digest:
            raise ValueError(f"MR-1 checksum mismatch: {name}")


def _write_parquet(path: Path, rows: Any) -> None:
    pd.DataFrame(list(rows)).to_parquet(path, index=False)


def _write_checksums(path: Path) -> None:
    _write_json(path / "SHA256SUMS.json", {item.name: _hash_path(item) for item in sorted(path.iterdir()) if item.name != "SHA256SUMS.json"})


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, default=str, allow_nan=False) + "\n", encoding="utf-8")


def _hash_path(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


if __name__ == "__main__":
    raise SystemExit(main())
