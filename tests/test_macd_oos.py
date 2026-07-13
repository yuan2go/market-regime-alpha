from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from market_regime_alpha.dividend_t.macd import PriceAdjustmentMode
from market_regime_alpha.dividend_t.macd import BarInterval, MACDConfig
from market_regime_alpha.dividend_t.macd_bars import expected_a_share_5m_closes
from market_regime_alpha.dividend_t.macd_experiments import (
    AblationArmContext,
    ablation_profiles,
    build_experiment_identity,
    experiment_config_hash,
)
from market_regime_alpha.dividend_t.macd_oos import (
    DataSplitManifest,
    DatasetClassification,
    ExperimentRunManifest,
    build_run_manifest,
    build_dataset_manifest,
    data_split_hash,
    dataset_manifest_hash,
    dataset_version,
    evaluate_final_test_readiness,
    selected_segment_range,
    validate_four_arm_identities,
    verify_artifact_checksums,
    write_immutable_run_artifact,
)
from market_regime_alpha.dividend_t.backtest import DividendTBacktestConfig
from market_regime_alpha.dividend_t.signal_intent import MACDPolicyConfig


def test_dataset_manifest_is_content_addressed_over_bars_and_point_in_time_sidecars(tmp_path: Path) -> None:
    bars = _write_bars(tmp_path / "bars.csv", days=("2026-05-25", "2026-05-26"))
    universe = _write_json(tmp_path / "universe.json", {"symbols": ["601919.SH"]})
    actions = _write_json(tmp_path / "corporate_actions.json", {"events": []})
    suspensions = _write_json(tmp_path / "suspensions.json", {"suspension_times": []})
    calendar = _write_json(tmp_path / "calendar.json", {"trading_dates": ["2026-05-25", "2026-05-26"]})

    manifest = build_dataset_manifest(
        (bars,),
        data_source="synthetic-rehearsal-v1",
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=True,
        trading_calendar_version="sse-calendar-fixture-v1",
        trading_calendar_path=calendar,
        universe_path=universe,
        corporate_actions_path=actions,
        suspensions_path=suspensions,
        classification=DatasetClassification.REHEARSAL,
    )

    assert manifest.total_bar_count == 96
    assert manifest.symbols == ("601919.SH",)
    assert manifest.symbols_detail[0].symbol == "601919.SH"
    assert manifest.symbols_detail[0].bar_count == 96
    assert manifest.symbols_detail[0].start_time == "2026-05-25 09:35:00"
    assert manifest.symbols_detail[0].end_time == "2026-05-26 15:00:00"
    assert manifest.start_time == "2026-05-25 09:35:00"
    assert manifest.end_time == "2026-05-26 15:00:00"
    assert manifest.quality.finalized_bar_count == 96
    assert manifest.quality.provisional_bar_count == 0
    assert manifest.quality.missing_expected_bar_count == 0
    assert manifest.quality.invalid_price_bar_count == 0
    assert manifest.quality.duplicate_timestamp_count == 0
    assert len(manifest.files[0].sha256) == 64
    assert dataset_version(manifest) == f"dataset-{dataset_manifest_hash(manifest)[:16]}"

    actions.write_text(json.dumps({"events": [{"date": "2026-05-26", "cash": 0.1}]}), encoding="utf-8")
    changed = build_dataset_manifest(
        (bars,),
        data_source="synthetic-rehearsal-v1",
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=True,
        trading_calendar_version="sse-calendar-fixture-v1",
        trading_calendar_path=calendar,
        universe_path=universe,
        corporate_actions_path=actions,
        suspensions_path=suspensions,
        classification=DatasetClassification.REHEARSAL,
    )
    assert dataset_manifest_hash(changed) != dataset_manifest_hash(manifest)
    assert dataset_version(changed) != dataset_version(manifest)


def test_dataset_manifest_records_missing_and_provisional_bars_without_filling(tmp_path: Path) -> None:
    bars = _write_bars(tmp_path / "bars.csv", days=("2026-05-25",))
    data = pd.read_csv(bars)
    data = data.drop(index=3).reset_index(drop=True)
    data.loc[0, "bar_final"] = False
    data.to_csv(bars, index=False)

    manifest = _manifest_for(bars, tmp_path)

    assert manifest.total_bar_count == 47
    assert manifest.quality.provisional_bar_count == 1
    assert manifest.quality.missing_expected_bar_count == 1
    assert manifest.quality.finalized_bar_count == 46


def test_data_split_hash_covers_ranges_symbol_holdout_and_policy_version() -> None:
    split = DataSplitManifest(
        train_range=("2026-05-25", "2026-05-26"),
        validation_range=("2026-05-27", "2026-05-27"),
        rehearsal_range=("2026-05-28", "2026-05-29"),
        test_range=("2026-06-01", "2026-06-01"),
        train_symbols=("601919.SH",),
        validation_symbols=("601919.SH",),
        rehearsal_symbols=("601919.SH",),
        test_symbols=("601919.SH",),
        symbol_holdout_definition="no-symbol-holdout-fixture",
        split_policy_version="chronological-holdout-v1",
    )

    original = data_split_hash(split)
    assert len(original) == 64
    assert data_split_hash(replace(split, test_range=("2026-06-02", "2026-06-02"))) != original
    assert data_split_hash(replace(split, test_symbols=("600900.SH",))) != original
    assert data_split_hash(replace(split, split_policy_version="chronological-holdout-v2")) != original


def test_data_split_rejects_overlapping_time_ranges() -> None:
    with pytest.raises(ValueError, match="DATA_SPLIT_RANGES_OVERLAP"):
        DataSplitManifest(
            train_range=("2026-05-25", "2026-05-27"),
            validation_range=("2026-05-27", "2026-05-28"),
            rehearsal_range=("2026-05-29", "2026-05-29"),
            test_range=("2026-06-01", "2026-06-01"),
            train_symbols=("601919.SH",),
            validation_symbols=("601919.SH",),
            rehearsal_symbols=("601919.SH",),
            test_symbols=("601919.SH",),
            symbol_holdout_definition="none",
            split_policy_version="v1",
        )


def test_four_arm_validation_allows_only_score_and_policy_experiment_variables() -> None:
    split = _split_fixture()
    identities, contexts = _four_arm_fixtures(split)

    validate_four_arm_identities(identities, contexts)

    changed = dict(identities)
    changed["full"] = replace(changed["full"], fast_period=10)
    with pytest.raises(ValueError, match="ABLATION_NON_EXPERIMENT_FIELD_MISMATCH"):
        validate_four_arm_identities(changed, contexts)


def test_immutable_artifact_is_atomic_checksummed_and_never_overwritten(tmp_path: Path) -> None:
    def writer(stage: Path) -> None:
        (stage / "manifest.json").write_text("{}\n", encoding="utf-8")
        for profile in ("baseline", "score-only", "policy-only", "full"):
            folder = stage / profile
            folder.mkdir()
            (folder / "metrics.json").write_text("{}\n", encoding="utf-8")
        (stage / "attribution").mkdir()
        (stage / "attribution" / "metrics.json").write_text("{}\n", encoding="utf-8")
        (stage / "report.md").write_text("# rehearsal\n", encoding="utf-8")

    artifact = write_immutable_run_artifact(tmp_path, run_id="rehearsal-run", writer=writer)

    assert artifact == tmp_path / "rehearsal-run"
    assert (artifact / "COMPLETED").is_file()
    assert (artifact / "checksums.sha256").is_file()
    assert verify_artifact_checksums(artifact)
    with pytest.raises(FileExistsError):
        write_immutable_run_artifact(tmp_path, run_id="rehearsal-run", writer=writer)


def test_failed_artifact_write_leaves_no_completed_or_partial_run(tmp_path: Path) -> None:
    def fail(_stage: Path) -> None:
        raise RuntimeError("profile failed")

    with pytest.raises(RuntimeError, match="profile failed"):
        write_immutable_run_artifact(tmp_path, run_id="failed-run", writer=fail)

    assert not (tmp_path / "failed-run").exists()
    assert not list(tmp_path.glob(".failed-run.tmp-*"))


def test_readiness_requires_every_gate_and_a_formal_dataset(tmp_path: Path) -> None:
    days = ("2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-06-01")
    bars = _write_bars(tmp_path / "bars.csv", days=days)
    manifest = build_dataset_manifest(
        (bars,),
        data_source="formal-fixture-v1",
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=True,
        trading_calendar_version="sse-calendar-fixture-v1",
        trading_calendar_path=_write_json(tmp_path / "calendar.json", {"trading_dates": list(days)}),
        universe_path=_write_json(tmp_path / "universe.json", {"symbols": ["601919.SH"]}),
        corporate_actions_path=_write_json(tmp_path / "actions.json", {"events": []}),
        suspensions_path=_write_json(tmp_path / "suspensions.json", {"suspension_times": []}),
        classification=DatasetClassification.FORMAL_FINAL_CANDIDATE,
    )
    split = _split_fixture()
    identities, contexts = _four_arm_fixtures(split, dataset=dataset_version(manifest))

    report = evaluate_final_test_readiness(
        manifest=manifest,
        split=split,
        identities=identities,
        contexts=contexts,
        working_tree_clean=True,
        quality_checks_pass=True,
        cache_identities_valid=True,
        production_policy_config=MACDPolicyConfig(),
    )

    assert report.ready
    assert all(check.passed for check in report.checks)

    rehearsal = replace(manifest, classification=DatasetClassification.REHEARSAL)
    blocked = evaluate_final_test_readiness(
        manifest=rehearsal,
        split=split,
        identities=identities,
        contexts=contexts,
        working_tree_clean=True,
        quality_checks_pass=True,
        cache_identities_valid=True,
        production_policy_config=MACDPolicyConfig(),
    )
    assert not blocked.ready
    assert blocked.failed_checks == ("formal_dataset_selected",)


def test_test_segment_is_sealed_without_explicit_final_test_flag() -> None:
    split = _split_fixture()

    assert selected_segment_range(split, segment="rehearsal", final_test=False) == split.rehearsal_range
    with pytest.raises(ValueError, match="FINAL_TEST_SEGMENT_SEALED"):
        selected_segment_range(split, segment="test", final_test=False)
    with pytest.raises(ValueError, match="FINAL_TEST_FLAG_REQUIRES_TEST_SEGMENT"):
        selected_segment_range(split, segment="rehearsal", final_test=True)
    assert selected_segment_range(split, segment="test", final_test=True) == split.test_range


def test_run_manifest_records_reproducibility_and_all_four_config_hashes() -> None:
    split = _split_fixture()
    identities, _contexts = _four_arm_fixtures(split)

    manifest = build_run_manifest(
        run_timestamp="2026-07-13T21:00:00+08:00",
        git_commit="71b7880",
        dataset_version="dataset-fixture-v1",
        dataset_manifest_hash_value="d" * 64,
        split=split,
        identities=identities,
        execution_config_hash_value=next(iter(identities.values())).execution_config_hash,
        random_seed=20260713,
        dependency_lock_hash="e" * 64,
        dependency_lock_source="installed-distributions-v1",
        platform_metadata={"python_implementation": "CPython", "system": "Darwin"},
        run_mode="REHEARSAL",
    )

    assert isinstance(manifest, ExperimentRunManifest)
    assert manifest.run_id.startswith("rehearsal-")
    assert manifest.dataset_manifest_hash == "d" * 64
    assert manifest.data_split_hash == data_split_hash(split)
    assert manifest.baseline_config_hash == experiment_config_hash(identities["baseline"])
    assert manifest.score_only_config_hash == experiment_config_hash(identities["score-only"])
    assert manifest.policy_only_config_hash == experiment_config_hash(identities["policy-only"])
    assert manifest.full_config_hash == experiment_config_hash(identities["full"])
    assert manifest.random_seed == 20260713
    assert manifest.dependency_lock_hash == "e" * 64
    assert manifest.dependency_lock_source == "installed-distributions-v1"


def test_runner_exposes_no_force_overwrite_option() -> None:
    script = Path(__file__).resolve().parents[1] / "backtesting" / "run_macd_ablation.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--final-test" in completed.stdout
    assert "--force" not in completed.stdout


def _manifest_for(bars: Path, root: Path):
    return build_dataset_manifest(
        (bars,),
        data_source="synthetic-rehearsal-v1",
        price_adjustment_mode=PriceAdjustmentMode.POINT_IN_TIME_ADJUSTED,
        pit_adjustment_complete=True,
        trading_calendar_version="sse-calendar-fixture-v1",
        trading_calendar_path=_write_json(root / "calendar.json", {"trading_dates": ["2026-05-25"]}),
        universe_path=_write_json(root / "universe.json", {"symbols": ["601919.SH"]}),
        corporate_actions_path=_write_json(root / "actions.json", {"events": []}),
        suspensions_path=_write_json(root / "suspensions.json", {"suspension_times": []}),
        classification=DatasetClassification.REHEARSAL,
    )


def _split_fixture() -> DataSplitManifest:
    return DataSplitManifest(
        train_range=("2026-05-25", "2026-05-26"),
        validation_range=("2026-05-27", "2026-05-27"),
        rehearsal_range=("2026-05-28", "2026-05-29"),
        test_range=("2026-06-01", "2026-06-01"),
        train_symbols=("601919.SH",),
        validation_symbols=("601919.SH",),
        rehearsal_symbols=("601919.SH",),
        test_symbols=("601919.SH",),
        symbol_holdout_definition="no-symbol-holdout-fixture",
        split_policy_version="chronological-holdout-v1",
    )


def _four_arm_fixtures(
    split: DataSplitManifest,
    *,
    dataset: str = "dataset-fixture-v1",
) -> tuple[dict[str, object], dict[str, AblationArmContext]]:
    execution = DividendTBacktestConfig(signal_cache_dir=None)
    identities = {
        name: build_experiment_identity(
            git_commit="71b7880",
            dataset_version=dataset,
            data_split_hash=data_split_hash(split),
            pipeline_id="macd-oos-5m",
            macd_config=MACDConfig(bar_interval=BarInterval.MINUTE_5),
            policy_config=policy,
            execution_config=execution,
            sizing_owner="dividend_t_backtest_execution",
        )
        for name, policy in ablation_profiles().items()
    }
    contexts = {
        name: AblationArmContext(
            profile=name,
            experiment_config_hash=experiment_config_hash(identity),
            dataset_version=dataset,
            train_range=split.train_range,
            validation_range=split.validation_range,
            test_range=split.test_range,
            execution_config_hash=identity.execution_config_hash,
            random_seed=20260713,
        )
        for name, identity in identities.items()
    }
    return identities, contexts


def _write_bars(path: Path, *, days: tuple[str, ...], symbol: str = "601919.SH") -> Path:
    timestamps = [timestamp for day in days for timestamp in expected_a_share_5m_closes(day)]
    rows = []
    for index, timestamp in enumerate(timestamps):
        close = 10.0 + index * 0.001
        rows.append(
            {
                "symbol": symbol,
                "timestamp": timestamp,
                "open": close - 0.01,
                "high": close + 0.02,
                "low": close - 0.02,
                "close": close,
                "volume": 100_000.0,
                "bar_final": True,
                "source_freq": "5min",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path
