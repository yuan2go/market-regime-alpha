from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from market_regime_alpha.research.mr2b_context import WatchlistDirection
from market_regime_alpha.research.mr2b_f2a_reader import VerifiedF2ARun
from market_regime_alpha.research.mr2b_f2b import F2BResults
from market_regime_alpha.research.mr2b_f2b_artifacts import (
    build_f2b_run_identity,
    publish_f2b_artifact,
)
from market_regime_alpha.research.mr2b_f2b_competing_events import (
    COMPETING_EVENT_TARGET_ID,
    CompetingEventResult,
)
from market_regime_alpha.research.mr2b_f2b_primary import (
    PrimaryAssessment,
    PrimaryGateResult,
)
from market_regime_alpha.research.mr2b_f2b_protocol import frozen_f2b_protocol
from market_regime_alpha.research.mr2b_f2b_reader import load_verified_f2b_run
from market_regime_alpha.research.mr2b_f2b_statistics import (
    F2BPrimaryObservation,
    PrimaryObservationSet,
    SeedPanelRobustness,
    circular_shift_randomization,
    concentration_diagnostics,
    count_preserving_permutation,
    moving_block_bootstrap,
    temporal_stability,
)
from market_regime_alpha.research.prr_artifact_reader import (
    VerifiedMR1Run,
    VerifiedPRRDataset,
)


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _upstreams(root: Path) -> tuple[VerifiedPRRDataset, VerifiedMR1Run, VerifiedF2ARun]:
    dataset_root, mr1_root, f2a_root = root / "dataset", root / "mr1", root / "f2a"
    for item in (dataset_root, mr1_root, f2a_root):
        item.mkdir()
        (item / "SHA256SUMS.json").write_text("{}\n", encoding="utf-8")
    dataset = VerifiedPRRDataset(
        root=dataset_root, dataset_id="dataset", manifest={}, quality={}, prepared=None,  # type: ignore[arg-type]
        bars=(), ranking_rows=(), decision_dates=(), checksums_hash=_hash(dataset_root / "SHA256SUMS.json"),
    )
    mr1 = VerifiedMR1Run(
        root=mr1_root, run_id="mr1", dataset_id="dataset", manifest={"top_k": 5},
        morning_targets=(), daily_equity=(), metrics=(), candidate_daily_baselines=(),
        matched_k_selections=(), checksums_hash=_hash(mr1_root / "SHA256SUMS.json"),
    )
    f2a = VerifiedF2ARun(
        root=f2a_root, run_id="f2a", dataset_id="dataset", mr1_run_id="mr1", manifest={},
        contexts=(), context_symbol_evidence=(), multiseed_selections=(), multiseed_returns=(),
        null_summaries=(), daily_candidate_excess=(), primary_comparison_input={}, coverage={},
        checksums_hash=_hash(f2a_root / "SHA256SUMS.json"),
    )
    return dataset, mr1, f2a


def _results() -> F2BResults:
    protocol = replace(
        frozen_f2b_protocol(), bootstrap_draws=20, random_permutation_draws=20
    )
    start = date(2026, 1, 1)
    observations = tuple(
        F2BPrimaryObservation(
            decision_date=start + timedelta(days=index), dataset_id="dataset", mr1_run_id="mr1",
            f2a_run_id="f2a", model_id=protocol.model_id, exit_time=protocol.exit_time,
            cost_scenario=protocol.cost_scenario, context_id=f"context-{index}",
            context_label=WatchlistDirection.UP if index % 2 else WatchlistDirection.DOWN,
            population_hash=f"population-{index}", seed_set_id="seed-set",
            metric_value=0.002 if index % 2 else 0.0,
        )
        for index in range(30)
    )
    bootstraps = tuple(
        moving_block_bootstrap(
            observations, draws=protocol.bootstrap_draws, block_length=block,
            seed=protocol.bootstrap_seed, minimum_slice_size=5,
        )
        for block in (5, 3, 10)
    )
    temporal = temporal_stability(observations)
    concentration = concentration_diagnostics(observations)
    panels = SeedPanelRobustness(
        full_seed_effect=0.002, panel_A_effect=0.002, panel_B_effect=0.002,
        panel_C_effect=0.002, panel_D_effect=0.002, positive_panel_count=4,
        direction_agreement=True, maximum_absolute_panel_deviation=0.0,
        rows=tuple({"panel": label, "effect": 0.002, "date_count": 30} for label in "ABCD"),
    )
    gate = PrimaryGateResult(
        PrimaryAssessment.PRIMARY_HYPOTHESIS_NOT_SUPPORTED,
        ("POSITIVE_DIRECTION",), ("BOOTSTRAP_INTERVAL_INCLUDES_ZERO",),
        ("BOOTSTRAP_INTERVAL_INCLUDES_ZERO",),
    )
    return F2BResults(
        protocol=protocol,
        primary_set=PrimaryObservationSet(observations, 30, 0, 0),
        bootstraps=bootstraps,
        circular=circular_shift_randomization(observations),
        permutation=count_preserving_permutation(observations, draws=20, seed=17),
        temporal=temporal,
        concentration=concentration,
        seed_panels=panels,
        primary_gate=gate,
        secondary_rows=({"model_id": "secondary", "exit_time": "10:30", "cost_scenario": "BASE", "bh_q_value": 0.5},),
        multiple_testing={"secondary_count": 1, "secondary_can_replace_primary": False},
        competing_events=CompetingEventResult(
            "COMPETING_EVENT_EVIDENCE_UNAVAILABLE", COMPETING_EVENT_TARGET_ID, (), 0.0, 30
        ),
    )


def _publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, VerifiedPRRDataset, VerifiedMR1Run, VerifiedF2ARun, F2BResults]:
    dataset, mr1, f2a = _upstreams(tmp_path)
    results = _results()
    runner = tmp_path / "runner.py"
    runner.write_text("# runner\n", encoding="utf-8")
    identity = build_f2b_run_identity(
        dataset_root=dataset.root, mr1_root=mr1.root, f2a_root=f2a.root,
        dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id, f2a_run_id=f2a.run_id,
        protocol=results.protocol, runner_path=runner,
    )
    final = publish_f2b_artifact(output_root=tmp_path / "runs", identity=identity, results=results)
    monkeypatch.setattr(
        "market_regime_alpha.research.mr2b_f2b_reader.frozen_f2b_protocol",
        lambda: results.protocol,
    )
    monkeypatch.setattr(
        "market_regime_alpha.research.mr2b_f2b_reader.build_f2b_results",
        lambda **_: results,
    )
    return final, dataset, mr1, f2a, results


def _rewrite_checksums(root: Path) -> None:
    payload = {
        item.name: _hash(item) for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_verified_reader_reconstructs_f2b_from_verified_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    final, dataset, mr1, f2a, _ = _publish(tmp_path, monkeypatch)
    verified = load_verified_f2b_run(final, dataset=dataset, mr1=mr1, f2a=f2a)
    assert verified.dataset_id == dataset.dataset_id
    assert verified.primary_assessment["assessment"] == "PRIMARY_HYPOTHESIS_NOT_SUPPORTED"


@pytest.mark.parametrize(
    ("filename", "column", "value"),
    (
        ("primary_bootstrap_distribution.parquet", "effect", 9.0),
        ("primary_circular_shift_distribution.parquet", "effect", 9.0),
        ("primary_seed_panel_robustness.parquet", "effect", -9.0),
        ("secondary_comparison_inventory.parquet", "bh_q_value", 0.01),
    ),
)
def test_checksum_valid_parquet_semantic_tampering_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str, column: str, value: object
) -> None:
    final, dataset, mr1, f2a, _ = _publish(tmp_path, monkeypatch)
    frame = pd.read_parquet(final / filename)
    frame.loc[0, column] = value
    frame.to_parquet(final / filename, index=False)
    _rewrite_checksums(final)
    with pytest.raises(ValueError, match="not reconstructible"):
        load_verified_f2b_run(final, dataset=dataset, mr1=mr1, f2a=f2a)


@pytest.mark.parametrize(
    ("filename", "field", "value"),
    (
        ("primary_assessment.json", "observed_effect", -9.0),
        ("primary_concentration.json", "largest_absolute_contribution_share", 0.99),
        ("multiple_testing_disclosure.json", "secondary_can_replace_primary", True),
        ("competing_event_status.json", "coverage", 1.0),
        ("protocol.json", "alternative", "DOWN_GREATER_THAN_UP"),
        ("protocol.json", "economic_effect_floor", 0.0),
    ),
)
def test_checksum_valid_json_semantic_tampering_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str, field: str, value: object
) -> None:
    final, dataset, mr1, f2a, _ = _publish(tmp_path, monkeypatch)
    path = final / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _rewrite_checksums(final)
    with pytest.raises((ValueError, TypeError)):
        load_verified_f2b_run(final, dataset=dataset, mr1=mr1, f2a=f2a)


def test_wrong_f2a_binding_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    final, dataset, mr1, f2a, _ = _publish(tmp_path, monkeypatch)
    wrong = replace(f2a, run_id="wrong-f2a")
    with pytest.raises(ValueError, match="input identity mismatch"):
        load_verified_f2b_run(final, dataset=dataset, mr1=mr1, f2a=wrong)
