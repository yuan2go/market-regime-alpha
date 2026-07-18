from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from market_regime_alpha.research.mr2b_f2a_reader import VerifiedF2ARun
from market_regime_alpha.research.mr2b_f2b_primary import PrimaryAssessment, PrimaryGateResult
from market_regime_alpha.research.mr2b_f2b_statistics import PrimaryObservationSet
from market_regime_alpha.research.mr2b_f2b_v3 import F2BResultsV3
from market_regime_alpha.research.mr2b_f2b_v3_artifacts import (
    build_f2b_v3_run_identity,
    publish_f2b_v3_artifact,
)
from market_regime_alpha.research.mr2b_f2b_v3_competing_events import (
    COMPETING_EVENT_RULE_ID,
    COMPETING_EVENT_TARGET_ID,
    CompetingEventCoverage,
    CompetingEventResultV3,
)
from market_regime_alpha.research.mr2b_f2b_v3_protocol import frozen_f2b_v3_protocol
from market_regime_alpha.research.mr2b_f2b_v3_reader import load_verified_f2b_v3_run
from market_regime_alpha.research.mr2b_f2b_v3_statistics import PrimaryCoverageAssessment
from market_regime_alpha.research.prr_artifact_reader import VerifiedMR1Run, VerifiedPRRDataset


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _upstreams(root: Path) -> tuple[VerifiedPRRDataset, VerifiedMR1Run, VerifiedF2ARun]:
    dataset_root, mr1_root, f2a_root = root / "dataset", root / "mr1", root / "f2a"
    for item in (dataset_root, mr1_root, f2a_root):
        item.mkdir()
        (item / "SHA256SUMS.json").write_text("{}\n", encoding="utf-8")
    dataset = VerifiedPRRDataset(dataset_root, "dataset", {}, {}, None, (), (), (), _hash(dataset_root / "SHA256SUMS.json"))  # type: ignore[arg-type]
    mr1 = VerifiedMR1Run(
        mr1_root, "mr1", "dataset", {"top_k": 5}, (), (), (), (), (),
        _hash(mr1_root / "SHA256SUMS.json"),
    )
    f2a = VerifiedF2ARun(
        f2a_root, "f2a", "dataset", "mr1", {}, (), (), (), (), (), (), {}, {},
        _hash(f2a_root / "SHA256SUMS.json"),
    )
    return dataset, mr1, f2a


def _insufficient_results() -> F2BResultsV3:
    protocol = frozen_f2b_v3_protocol()
    coverage = PrimaryCoverageAssessment(44, 14, 30, 0, 0, True, False, ("INSUFFICIENT_UP_SLICE",))
    gate = PrimaryGateResult(
        PrimaryAssessment.INSUFFICIENT_EVIDENCE,
        (),
        coverage.insufficiency_reasons,
        coverage.insufficiency_reasons,
    )
    competing_coverage = CompetingEventCoverage(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    competing = CompetingEventResultV3(
        "COMPETING_EVENT_EVIDENCE_UNAVAILABLE",
        COMPETING_EVENT_TARGET_ID,
        COMPETING_EVENT_RULE_ID,
        (),
        competing_coverage,
    )
    return F2BResultsV3(
        protocol, PrimaryObservationSet((), 44, 0, 0), coverage, (), None, None, None,
        None, None, gate, (),
        {
            "schema_version": "mr-2b-f2b-multiple-testing-disclosure-v3",
            "comparison_count": 0,
            "primary_count": 0,
            "secondary_count": 0,
            "method_id": protocol.multiple_testing_method_id,
            "alpha": protocol.multiple_testing_alpha,
            "status": "NOT_RUN_INSUFFICIENT_PRIMARY_COVERAGE",
            "secondary_can_replace_primary": False,
        },
        competing,
    )


def _publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dataset, mr1, f2a = _upstreams(tmp_path)
    results = _insufficient_results()
    runner = tmp_path / "runner.py"
    runner.write_text("# runner\n", encoding="utf-8")
    identity = build_f2b_v3_run_identity(
        dataset_root=dataset.root, mr1_root=mr1.root, f2a_root=f2a.root,
        dataset_id=dataset.dataset_id, mr1_run_id=mr1.run_id, f2a_run_id=f2a.run_id,
        protocol=results.protocol, runner_path=runner,
    )
    final = publish_f2b_v3_artifact(output_root=tmp_path / "runs", identity=identity, results=results)
    monkeypatch.setattr("market_regime_alpha.research.mr2b_f2b_v3_reader.frozen_f2b_v3_protocol", lambda: results.protocol)
    monkeypatch.setattr("market_regime_alpha.research.mr2b_f2b_v3_reader.build_f2b_v3_results", lambda **_: results)
    return final, dataset, mr1, f2a


def _rewrite_checksums(root: Path) -> None:
    payload = {
        item.name: _hash(item) for item in sorted(root.iterdir())
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_insufficient_run_publishes_empty_fixed_schema_distributions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final, dataset, mr1, f2a = _publish(tmp_path, monkeypatch)
    assert pd.read_parquet(final / "primary_bootstrap_distribution.parquet").empty
    assert pd.read_parquet(final / "primary_circular_shift_distribution.parquet").empty
    assessment = json.loads((final / "primary_assessment.json").read_text(encoding="utf-8"))
    assert assessment["assessment"] == "INSUFFICIENT_EVIDENCE"
    assert assessment["statistics_executed"] is False
    verified = load_verified_f2b_v3_run(final, dataset=dataset, mr1=mr1, f2a=f2a)
    assert verified.artifact_verification_status == "VERIFIED_EXPLORATORY_STATISTICAL_ASSESSMENT"


@pytest.mark.parametrize(
    ("filename", "field", "value"),
    (
        ("primary_assessment.json", "insufficiency_reasons", ["INSUFFICIENT_DOWN_SLICE"]),
        ("protocol.json", "economic_effect_floor", 0.5),
        ("competing_event_status.json", "top5_missing_target_count", 99),
    ),
)
def test_checksum_valid_v3_semantic_tamper_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str, field: str, value: object
) -> None:
    final, dataset, mr1, f2a = _publish(tmp_path, monkeypatch)
    path = final / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _rewrite_checksums(final)
    with pytest.raises((ValueError, TypeError)):
        load_verified_f2b_v3_run(final, dataset=dataset, mr1=mr1, f2a=f2a)


@pytest.mark.parametrize("mutation", ("empty", "missing", "extra"))
def test_checksum_valid_inexact_implementation_module_map_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    final, dataset, mr1, f2a = _publish(tmp_path, monkeypatch)
    manifest_path = final / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = manifest["run_identity"]["implementation_module_hashes"]
    if mutation == "empty":
        hashes.clear()
    elif mutation == "missing":
        hashes.pop(next(iter(hashes)))
    else:
        hashes["future_registry.py"] = "sha256:" + "0" * 64
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _rewrite_checksums(final)
    with pytest.raises(ValueError, match="module set"):
        load_verified_f2b_v3_run(final, dataset=dataset, mr1=mr1, f2a=f2a)
