from __future__ import annotations

import json
from pathlib import Path

from market_regime_alpha.cli.compare_legacy_features import main as compare_main
from market_regime_alpha.cli.materialize_features import main as materialize_main
from market_regime_alpha.cli.replay_feature_bundle import main as replay_main
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.features.materialization_v2 import (
    FeatureComputationFailedError,
    FeatureMaterializationStatus,
    FeatureReplayDivergenceError,
)
from market_regime_alpha.features.technical.catalog import (
    MOVING_AVERAGE_FEATURE_ID,
    canonical_technical_feature_set,
)
from tests.features.test_materialization_runner_v2 import _verified_dataset


def _inputs(tmp_path: Path, *, daily_count: int = 70) -> tuple[Path, Path]:
    dataset = _verified_dataset(tmp_path, daily_count=daily_count)
    feature_set = canonical_technical_feature_set(effective_from=dataset.artifact.decision_time)
    config = tmp_path / "feature-set.json"
    config.write_text(canonical_json(feature_set.to_canonical_dict()), encoding="utf-8")
    return dataset.root, config


def _materialize_args(
    dataset: Path,
    config: Path,
    output: Path,
    *,
    execution_mode: str = "START_NEW",
) -> list[str]:
    return [
        "--market-data-manifest",
        str(dataset),
        "--feature-set-config",
        str(config),
        "--decision-date",
        "2026-08-04",
        "--as-of",
        "2026-08-04T02:30:00Z",
        "--symbols",
        "600000.SH",
        "--output-dir",
        str(output),
        "--idempotency-key",
        "cli-feature-run-1",
        "--code-revision",
        "test-revision",
        "--execution-mode",
        execution_mode,
    ]


def test_materialize_and_replay_cli_are_structured_and_side_effect_free(tmp_path: Path, capsys) -> None:
    dataset, config = _inputs(tmp_path)
    output = tmp_path / "output"

    status = materialize_main(_materialize_args(dataset, config, output))
    first = json.loads(capsys.readouterr().out)
    assert status == 0
    assert first["status"] == FeatureMaterializationStatus.COMPLETE.value
    assert first["NO_ORDER_CREATED"] is True
    assert first["BROKER_NOT_INVOKED"] is True
    assert first["NO_FILL_CREATED"] is True
    assert first["TRADING_AUTHORITY_NOT_GRANTED"] is True

    status = materialize_main(
        _materialize_args(
            dataset,
            config,
            output,
            execution_mode="RETURN_IF_COMPLETE",
        )
    )
    second = json.loads(capsys.readouterr().out)
    assert status == 0
    assert second["feature_bundle_id"] == first["feature_bundle_id"]

    bundle_path = output / "feature-bundles" / first["feature_bundle_id"]
    status = replay_main(
        [
            "--market-data-manifest",
            str(dataset),
            "--feature-bundle",
            str(bundle_path),
            "--feature-artifact-root",
            str(output / "feature-artifacts"),
            "--output-dir",
            str(output / "replay-reports"),
        ]
    )
    replay = json.loads(capsys.readouterr().out)
    assert status == 0
    assert replay["status"] == "STABLE"
    assert replay["feature_bundle_hash"] == first["feature_bundle_hash"]


def test_legacy_comparison_cli_publishes_evidence_without_signal_authority(tmp_path: Path, capsys) -> None:
    dataset, config = _inputs(tmp_path)
    status = compare_main(
        [
            "--market-data-manifest",
            str(dataset),
            "--feature-set-config",
            str(config),
            "--feature-id",
            MOVING_AVERAGE_FEATURE_ID,
            "--symbols",
            "600000.SH",
            "--output-dir",
            str(tmp_path / "comparison-output"),
            "--code-revision",
            "test-revision",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert status == 0
    assert payload["status"] == "COMPARED"
    assert payload["comparison_packages"]
    assert payload["TRADING_AUTHORITY_NOT_GRANTED"] is True


def test_materialize_cli_rejects_tampered_dataset(tmp_path: Path, capsys) -> None:
    dataset, config = _inputs(tmp_path)
    artifact = dataset / "artifact.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")

    status = materialize_main(_materialize_args(dataset, config, tmp_path / "output"))
    payload = json.loads(capsys.readouterr().out)
    assert status == 3
    assert payload["status"] == "REJECTED"
    assert payload["NO_ORDER_CREATED"] is True


def test_replay_cli_classifies_semantic_divergence_as_canonical_regression(tmp_path: Path, capsys, monkeypatch) -> None:
    def diverged(**_kwargs):
        raise FeatureReplayDivergenceError("semantic mismatch")

    monkeypatch.setattr(
        "market_regime_alpha.cli.replay_feature_bundle.replay_feature_bundle_v2",
        diverged,
    )
    dataset, _ = _inputs(tmp_path)

    status = replay_main(
        [
            "--market-data-manifest",
            str(dataset),
            "--feature-bundle",
            str(tmp_path / "bundle"),
            "--feature-artifact-root",
            str(tmp_path / "artifacts"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert status == 6
    assert payload["status"] == "CANONICAL_REGRESSION"
    assert payload["reason_codes"] == ["FEATURE_REPLAY_DIVERGED"]


def test_materialize_cli_distinguishes_blocked_evidence_and_computation_failure(tmp_path: Path, capsys, monkeypatch) -> None:
    dataset, config = _inputs(tmp_path / "blocked", daily_count=5)
    status = materialize_main(_materialize_args(dataset, config, tmp_path / "blocked-output"))
    blocked = json.loads(capsys.readouterr().out)
    assert status == 4
    assert blocked["status"] == FeatureMaterializationStatus.BLOCKED_REQUIRED_FEATURE.value

    def failed(*_args, **_kwargs):
        raise FeatureComputationFailedError("injected computation failure")

    monkeypatch.setattr(
        "market_regime_alpha.cli.materialize_features.FeatureMaterializationRunner.run",
        failed,
    )
    dataset, config = _inputs(tmp_path / "failed")
    status = materialize_main(_materialize_args(dataset, config, tmp_path / "failed-output"))
    failure = json.loads(capsys.readouterr().out)
    assert status == 5
    assert failure["status"] == "COMPUTATION_FAILED"
