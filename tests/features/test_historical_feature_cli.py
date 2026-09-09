from __future__ import annotations

import json
from pathlib import Path

from market_regime_alpha.cli.replay_feature_bundle import main as replay_main
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.features.materialization_v2 import (
    FeatureReplayDivergenceError,
)
from market_regime_alpha.features.technical.catalog import (
    canonical_technical_feature_set,
)
from tests.features.test_materialization_runner_v2 import _verified_dataset


def _inputs(tmp_path: Path, *, daily_count: int = 70) -> tuple[Path, Path]:
    dataset = _verified_dataset(tmp_path, daily_count=daily_count)
    feature_set = canonical_technical_feature_set(effective_from=dataset.artifact.decision_time)
    config = tmp_path / "feature-set.json"
    config.write_text(canonical_json(feature_set.to_canonical_dict()), encoding="utf-8")
    return dataset.root, config










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
