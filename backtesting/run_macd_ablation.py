#!/usr/bin/env python3
"""Run sealed four-arm MACD ablations without exposing the final segment by default."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import (  # noqa: E402
    DividendTBacktestConfig,
    DividendTBacktestResult,
    run_cosco_dividend_t_backtest,
)
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine  # noqa: E402
from market_regime_alpha.dividend_t.macd import BarInterval, MACDConfig, PriceAdjustmentMode  # noqa: E402
from market_regime_alpha.dividend_t.macd_bars import (  # noqa: E402
    CorporateAction,
    calculate_macd_from_bars,
    prepare_macd_bars,
)
from market_regime_alpha.dividend_t.macd_experiments import (  # noqa: E402
    MACD_PROFILE_NAMES,
    AblationArmContext,
    ablation_profiles,
    build_experiment_identity,
    cache_metadata,
    canonical_experiment_config,
    canonical_json,
    experiment_config_hash,
    factorial_attribution,
)
from market_regime_alpha.dividend_t.macd_oos import (  # noqa: E402
    DatasetClassification,
    build_run_manifest,
    data_split_hash,
    dataset_manifest_hash,
    dataset_version,
    evaluate_final_test_readiness,
    load_data_split_manifest,
    load_dataset_bundle,
    selected_segment_range,
    validate_four_arm_identities,
    write_immutable_run_artifact,
)
from market_regime_alpha.dividend_t.signal_intent import MACDPolicyConfig  # noqa: E402


DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "macd_oos"
PIPELINE_ID = "sealed-macd-oos-5m"
SIZING_OWNER = "dividend_t_backtest_execution"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a sealed four-arm MACD ablation.")
    parser.add_argument("--data", type=Path, nargs="+", required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--corporate-actions", type=Path, required=True)
    parser.add_argument("--suspensions", type=Path, required=True)
    parser.add_argument("--trading-calendar", type=Path, required=True)
    parser.add_argument("--trading-calendar-version", required=True)
    parser.add_argument("--data-source", required=True)
    parser.add_argument(
        "--dataset-classification",
        choices=[item.value for item in DatasetClassification],
        default=DatasetClassification.REHEARSAL.value,
    )
    parser.add_argument("--pit-adjustment-complete", action="store_true")
    parser.add_argument("--segment", choices=["train", "validation", "rehearsal", "test"], default="rehearsal")
    parser.add_argument("--final-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--random-seed", type=int, default=20260713)
    parser.add_argument("--run-timestamp", help="Fixed ISO timestamp for a reproducible rehearsal run id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    classification = DatasetClassification(args.dataset_classification)
    if args.final_test and classification is not DatasetClassification.FORMAL_FINAL_CANDIDATE:
        raise ValueError("FINAL_TEST_REQUIRES_FORMAL_DATASET_CLASSIFICATION")
    split = load_data_split_manifest(args.split_manifest)
    selected_range = selected_segment_range(split, segment=args.segment, final_test=args.final_test)
    bundle = load_dataset_bundle(
        tuple(args.data),
        data_source=args.data_source,
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=args.pit_adjustment_complete,
        trading_calendar_version=args.trading_calendar_version,
        trading_calendar_path=args.trading_calendar,
        universe_path=args.universe,
        corporate_actions_path=args.corporate_actions,
        suspensions_path=args.suspensions,
        classification=classification,
    )
    selected = _select_segment(bundle.frame, split=split, segment=args.segment, selected_range=selected_range)
    execution_config = DividendTBacktestConfig(
        signal_cache_dir=None,
        max_history_bars=96,
        signal_step_bars=6,
    )
    macd_config = MACDConfig(bar_interval=BarInterval.MINUTE_5)
    git_commit = _git_commit()
    identities = {
        name: build_experiment_identity(
            git_commit=git_commit,
            dataset_version=dataset_version(bundle.manifest),
            data_split_hash=data_split_hash(split),
            pipeline_id=PIPELINE_ID,
            macd_config=macd_config,
            policy_config=policy,
            execution_config=execution_config,
            sizing_owner=SIZING_OWNER,
        )
        for name, policy in ablation_profiles().items()
    }
    contexts = {
        name: AblationArmContext(
            profile=name,
            experiment_config_hash=experiment_config_hash(identity),
            dataset_version=identity.dataset_version,
            train_range=split.train_range,
            validation_range=split.validation_range,
            test_range=split.test_range,
            execution_config_hash=identity.execution_config_hash,
            random_seed=args.random_seed,
        )
        for name, identity in identities.items()
    }
    validate_four_arm_identities(identities, contexts)
    quality_results = _run_quality_checks() if not args.dry_run else {"dry_run": True}
    quality_pass = bool(quality_results) and all(value is True for value in quality_results.values())
    readiness = evaluate_final_test_readiness(
        manifest=bundle.manifest,
        split=split,
        identities=identities,
        contexts=contexts,
        working_tree_clean=_working_tree_clean(),
        quality_checks_pass=quality_pass,
        cache_identities_valid=_cache_identities_valid(identities),
        production_policy_config=MACDPolicyConfig(),
    )
    if args.final_test:
        readiness.require_ready()

    run_timestamp = args.run_timestamp or datetime.now().astimezone().isoformat(timespec="seconds")
    dependency_hash = _dependency_lock_hash()
    run_manifest = build_run_manifest(
        run_timestamp=run_timestamp,
        git_commit=git_commit,
        dataset_version=dataset_version(bundle.manifest),
        dataset_manifest_hash_value=dataset_manifest_hash(bundle.manifest),
        split=split,
        identities=identities,
        execution_config_hash_value=next(iter(identities.values())).execution_config_hash,
        random_seed=args.random_seed,
        dependency_lock_hash=dependency_hash,
        dependency_lock_source="installed-distributions-v1",
        platform_metadata=_platform_metadata(),
        run_mode="FINAL_TEST" if args.final_test else "REHEARSAL",
    )
    _print_plan(run_manifest, selected_range, identities, readiness)
    if args.dry_run:
        return 0

    random.seed(args.random_seed)
    actions = _load_corporate_actions(args.corporate_actions)
    profile_results: dict[str, list[DividendTBacktestResult]] = {}
    for profile_name in MACD_PROFILE_NAMES:
        policy = ablation_profiles()[profile_name]
        profile_results[profile_name] = _run_profile(
            selected,
            policy=policy,
            identity=identities[profile_name],
            execution_config=execution_config,
            macd_config=macd_config,
            expected_bar_times=bundle.expected_bar_times,
            suspension_times=bundle.suspension_times,
            corporate_actions=actions,
            adjustment_data_complete=bundle.manifest.pit_adjustment_complete,
        )

    root = args.artifact_root / ("final" if args.final_test else "rehearsal")
    artifact = write_immutable_run_artifact(
        root,
        run_id=run_manifest.run_id,
        writer=lambda stage: _write_run_artifacts(
            stage,
            run_manifest=run_manifest,
            dataset_manifest=bundle.manifest,
            split=split,
            readiness=readiness,
            quality_results=quality_results,
            identities=identities,
            profile_results=profile_results,
            execution_config=execution_config,
            selected_range=selected_range,
        ),
    )
    print(f"artifact={artifact}")
    return 0


def _run_profile(
    data: Any,
    *,
    policy: MACDPolicyConfig,
    identity: Any,
    execution_config: DividendTBacktestConfig,
    macd_config: MACDConfig,
    expected_bar_times: tuple[Any, ...],
    suspension_times: frozenset[Any],
    corporate_actions: tuple[CorporateAction, ...],
    adjustment_data_complete: bool,
) -> list[DividendTBacktestResult]:
    results: list[DividendTBacktestResult] = []
    for symbol in sorted(data["symbol"].astype(str).unique()):
        symbol_data = data.loc[data["symbol"].astype(str) == symbol].copy()
        provider = _macd_provider(
            macd_config=macd_config,
            expected_bar_times=expected_bar_times,
            suspension_times=suspension_times,
            corporate_actions=corporate_actions,
            adjustment_data_complete=adjustment_data_complete,
        )
        results.append(
            run_cosco_dividend_t_backtest(
                symbol_data,
                config=execution_config,
                engine=CoscoTimingEngine(macd_policy_config=policy),
                experiment_identity=identity,
                pipeline_id=PIPELINE_ID,
                macd_result_provider=provider,
            )
        )
    return results


def _macd_provider(
    *,
    macd_config: MACDConfig,
    expected_bar_times: tuple[Any, ...],
    suspension_times: frozenset[Any],
    corporate_actions: tuple[CorporateAction, ...],
    adjustment_data_complete: bool,
):
    def provide(history: Any):
        first = pd.Timestamp(history["timestamp"].iloc[0])
        last = pd.Timestamp(history["timestamp"].iloc[-1])
        expected = tuple(timestamp for timestamp in expected_bar_times if first <= timestamp <= last)
        suspended = frozenset(timestamp for timestamp in suspension_times if first <= timestamp <= last)
        prepared = prepare_macd_bars(
            history,
            config=macd_config,
            evaluation_time=last,
            corporate_actions=corporate_actions,
            adjustment_data_complete=adjustment_data_complete,
            expected_bar_times=expected,
            suspension_times=suspended,
        )
        return calculate_macd_from_bars(prepared, macd_config)

    return provide


def _select_segment(data: Any, *, split: Any, segment: str, selected_range: tuple[str, str]) -> Any:
    symbols = set(getattr(split, f"{segment}_symbols"))
    timestamps = pd.to_datetime(data["timestamp"])
    dates = timestamps.dt.normalize()
    start, end = (pd.Timestamp(value).normalize() for value in selected_range)
    selected = data.loc[
        data["symbol"].astype(str).isin(symbols) & dates.between(start, end)
    ].copy()
    if selected.empty:
        raise ValueError(f"EXPERIMENT_SEGMENT_EMPTY: {segment}")
    return selected


def _write_run_artifacts(
    stage: Path,
    *,
    run_manifest: Any,
    dataset_manifest: Any,
    split: Any,
    readiness: Any,
    quality_results: dict[str, bool],
    identities: dict[str, Any],
    profile_results: dict[str, list[DividendTBacktestResult]],
    execution_config: DividendTBacktestConfig,
    selected_range: tuple[str, str],
) -> None:
    manifest_payload = {
        "run": asdict(run_manifest),
        "dataset": asdict(dataset_manifest),
        "split": asdict(split),
        "readiness": {"ready": readiness.ready, "checks": [asdict(check) for check in readiness.checks]},
        "quality_checks": quality_results,
        "production_default": {"profile": "baseline", "score_weight": 0.0, "conflict_gate_enabled": False},
    }
    _write_json(stage / "manifest.json", manifest_payload)
    summaries: dict[str, dict[str, Any]] = {}
    for profile_name, results in profile_results.items():
        folder = stage / profile_name
        folder.mkdir()
        _write_json(folder / "config.json", canonical_experiment_config(identities[profile_name]))
        summary = _aggregate_results(results)
        summaries[profile_name] = summary
        _write_json(folder / "metrics.json", summary)
        pd.DataFrame([_result_row(result) for result in results]).to_csv(folder / "per_symbol_metrics.csv", index=False)
        pd.DataFrame(
            [{"symbol": result.symbol, **trade.to_dict()} for result in results for trade in result.trades]
        ).to_csv(folder / "trades.csv", index=False)
        pd.DataFrame(
            [{"symbol": result.symbol, **asdict(signal)} for result in results for signal in result.signals]
        ).to_csv(folder / "candidate_diagnostics.csv", index=False)
        (folder / "counterfactual_events.jsonl").write_text("", encoding="utf-8")
    attribution = _attribution_payload(summaries)
    attribution_folder = stage / "attribution"
    attribution_folder.mkdir()
    _write_json(attribution_folder / "metrics.json", attribution)
    report = _format_report(
        run_manifest=run_manifest,
        readiness=readiness,
        summaries=summaries,
        attribution=attribution,
        execution_config=execution_config,
        selected_range=selected_range,
    )
    (stage / "report.md").write_text(report, encoding="utf-8")


def _aggregate_results(results: list[DividendTBacktestResult]) -> dict[str, Any]:
    count = len(results)
    return {
        "symbol_count": count,
        "average_total_return": sum(result.total_return for result in results) / count,
        "average_excess_return": sum(result.excess_return for result in results) / count,
        "worst_max_drawdown": min(result.max_drawdown for result in results),
        "trade_count": sum(result.trade_count for result in results),
        "completed_trades": sum(result.completed_trades for result in results),
        "coverage": sum(result.trade_count for result in results) / max(sum(result.rows for result in results), 1),
        "turnover_notional": sum(
            trade.shares * trade.price for result in results for trade in result.trades
        ) / max(sum(result.initial_cash for result in results), 1.0),
    }


def _result_row(result: DividendTBacktestResult) -> dict[str, Any]:
    return {
        "symbol": result.symbol,
        "start": result.start,
        "end": result.end,
        "rows": result.rows,
        "total_return": result.total_return,
        "excess_return": result.excess_return,
        "max_drawdown": result.max_drawdown,
        "trade_count": result.trade_count,
        "completed_trades": result.completed_trades,
    }


def _attribution_payload(summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for metric in ("average_total_return", "average_excess_return", "coverage", "turnover_notional"):
        effect = factorial_attribution(
            baseline=float(summaries["baseline"][metric]),
            score_only=float(summaries["score-only"][metric]),
            policy_only=float(summaries["policy-only"][metric]),
            full=float(summaries["full"][metric]),
        )
        payload[metric] = asdict(effect)
    return payload


def _format_report(
    *, run_manifest: Any, readiness: Any, summaries: dict[str, dict[str, Any]],
    attribution: dict[str, Any], execution_config: DividendTBacktestConfig,
    selected_range: tuple[str, str],
) -> str:
    rows = "\n".join(
        f"| {name} | `{getattr(run_manifest, name.replace('-', '_') + '_config_hash', '-')}` | "
        f"{metrics['average_total_return']:.4%} | {metrics['worst_max_drawdown']:.4%} | "
        f"{metrics['trade_count']} | {metrics['coverage']:.4%} |"
        for name, metrics in summaries.items()
    )
    total = attribution["average_total_return"]
    return (
        "# MACD Four-Arm Rehearsal\n\n"
        f"- Run ID: `{run_manifest.run_id}`\n"
        f"- Mode: `{run_manifest.run_mode}`\n"
        f"- Segment: `{selected_range[0]}` to `{selected_range[1]}`\n"
        f"- Dataset manifest: `{run_manifest.dataset_manifest_hash}`\n"
        f"- Split: `{run_manifest.data_split_hash}`\n"
        f"- Execution config: `{run_manifest.execution_config_hash}`\n"
        f"- Final-test readiness: `{readiness.ready}`\n"
        "- Production default: `baseline`, `score_weight=0.0`, `conflict_gate_enabled=False`\n"
        f"- Slippage/commission/stamp duty: `{execution_config.slippage_bps}` bps / "
        f"`{execution_config.commission_rate}` / `{execution_config.stamp_duty_rate}`\n\n"
        "| Profile | Config hash | Avg return | Worst drawdown | Trades | Coverage |\n"
        "| --- | --- | ---: | ---: | ---: | ---: |\n"
        f"{rows}\n\n"
        "## Total-return attribution\n\n"
        f"- Score: `{total['score_effect']:.6f}`\n"
        f"- Policy: `{total['policy_effect']:.6f}`\n"
        f"- Interaction: `{total['interaction_effect']:.6f}`\n"
        f"- Total: `{total['total_effect']:.6f}`\n"
    )


def _load_corporate_actions(path: Path) -> tuple[CorporateAction, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events", []) if isinstance(payload, dict) else []
    if not isinstance(events, list):
        raise ValueError("CORPORATE_ACTION_EVENTS_INVALID")
    return tuple(
        CorporateAction(
            effective_time=event["effective_time"],
            share_factor=float(event.get("share_factor", 1.0)),
            cash_per_share=float(event.get("cash_per_share", 0.0)),
        )
        for event in events
    )


def _run_quality_checks() -> dict[str, bool]:
    commands = {
        "pytest": [sys.executable, "-m", "pytest", "-q"],
        "ruff": [sys.executable, "-m", "ruff", "check", "."],
        "mypy": [sys.executable, "-m", "mypy"],
    }
    results: dict[str, bool] = {}
    for name, command in commands.items():
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
        results[name] = completed.returncode == 0
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
    return results


def _dependency_lock_hash() -> str:
    packages = sorted(
        f"{distribution.metadata.get('Name', distribution.name).lower()}=={distribution.version}"
        for distribution in metadata.distributions()
    )
    return hashlib.sha256(canonical_json({"installed_distributions": packages}).encode("utf-8")).hexdigest()


def _cache_identities_valid(identities: dict[str, Any]) -> bool:
    for identity in identities.values():
        metadata_values = cache_metadata(identity)
        if metadata_values["_experiment_config_hash"] != experiment_config_hash(identity):
            return False
        if metadata_values["_dataset_version"] != identity.dataset_version:
            return False
        if metadata_values["_pipeline_id"] != identity.pipeline_id:
            return False
        if metadata_values["_sizing_owner"] != identity.sizing_owner:
            return False
    return True


def _platform_metadata() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()


def _working_tree_clean() -> bool:
    return not subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, text=True).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _print_plan(run_manifest: Any, selected_range: tuple[str, str], identities: dict[str, Any], readiness: Any) -> None:
    print(f"run_id={run_manifest.run_id}")
    print(f"mode={run_manifest.run_mode}")
    print(f"selected_range={selected_range[0]}..{selected_range[1]}")
    for name in MACD_PROFILE_NAMES:
        print(
            f"profile={name} config_hash={experiment_config_hash(identities[name])} "
            f"production_default={str(name == 'baseline').lower()}"
        )
    print(f"final_test_ready={str(readiness.ready).lower()}")
    if readiness.failed_checks:
        print(f"failed_readiness={','.join(readiness.failed_checks)}")


if __name__ == "__main__":
    raise SystemExit(main())
