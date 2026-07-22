from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from market_regime_alpha.daily_research.reader import (
    load_verified_daily_quant_decision_artifact,
)


def _rewrite_checksums(root: Path) -> None:
    checksums = {
        path.name: f"sha256:{sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (root / "SHA256SUMS.json").write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _rewrite_json(root: Path, filename: str, value: object) -> None:
    (root / filename).write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _rewrite_checksums(root)


def test_reader_reconstructs_verified_immutable_daily_decision(published_artifact) -> None:
    verified = load_verified_daily_quant_decision_artifact(published_artifact)

    assert verified.root == published_artifact.resolve()
    assert verified.artifact_id == published_artifact.name
    assert verified.snapshot.snapshot_id.value == verified.manifest["snapshot_id"]
    assert len(verified.recommendations) == 1
    assert len(verified.entry_assessments) == 1
    assert verified.entry_assessments[0].recommendation_id == verified.recommendations[0].recommendation_id
    with pytest.raises(TypeError):
        verified.manifest["data_authority"] = "FORMAL_RESEARCH"  # type: ignore[index]
    with pytest.raises(TypeError):
        verified.manifest["instrument_counts"]["ETF"] = 1  # type: ignore[index]


def test_reader_rejects_semantic_candidate_tampering_after_checksum_rewrite(published_artifact) -> None:
    payload = json.loads((published_artifact / "candidate_recommendations.json").read_text())
    payload[0]["candidate_score"] = 999.0
    _rewrite_json(published_artifact, "candidate_recommendations.json", payload)

    with pytest.raises(ValueError, match="Candidate Recommendation identity"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_entry_tampering_after_checksum_rewrite(published_artifact) -> None:
    payload = json.loads((published_artifact / "entry_assessments.json").read_text())
    payload[0]["entry_state"] = "REJECT"
    _rewrite_json(published_artifact, "entry_assessments.json", payload)

    with pytest.raises(ValueError, match="Entry Assessment"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_report_tampering_after_checksum_rewrite(published_artifact) -> None:
    (published_artifact / "report.md").write_text("# Plausible but invented report\n", encoding="utf-8")
    _rewrite_checksums(published_artifact)

    with pytest.raises(ValueError, match="report"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_cross_snapshot_reference_after_checksum_rewrite(published_artifact) -> None:
    payload = json.loads((published_artifact / "candidate_recommendations.json").read_text())
    payload[0]["decision_snapshot_id"] = "daily-snapshot-other"
    _rewrite_json(published_artifact, "candidate_recommendations.json", payload)

    with pytest.raises(ValueError, match="Candidate Recommendation"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_extra_file_even_with_valid_payloads(published_artifact) -> None:
    (published_artifact / "unowned.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exact file set"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_extra_directory(published_artifact) -> None:
    (published_artifact / "unowned").mkdir()

    with pytest.raises(ValueError, match="exact file set"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_noncanonical_record_order(tmp_path) -> None:
    from market_regime_alpha.daily_research.artifacts import publish_daily_quant_decision_artifact

    from .conftest import make_entry, make_recommendation, make_snapshot

    snapshot = make_snapshot()
    first = make_recommendation(snapshot, symbol="600001.SH", rank=1, score=0.75)
    second = make_recommendation(snapshot, symbol="600002.SH", rank=2, score=0.5)
    artifact = publish_daily_quant_decision_artifact(
        root=tmp_path,
        snapshot=snapshot,
        recommendations=(first, second),
        entry_assessments=(make_entry(snapshot, first), make_entry(snapshot, second)),
    )
    payload = json.loads((artifact / "candidate_recommendations.json").read_text())
    _rewrite_json(artifact, "candidate_recommendations.json", list(reversed(payload)))

    with pytest.raises(ValueError, match="canonical order"):
        load_verified_daily_quant_decision_artifact(artifact)


def test_reader_rejects_contiguous_but_semantically_altered_ranking(published_artifact) -> None:
    payload = json.loads((published_artifact / "candidate_recommendations.json").read_text())
    payload[0]["candidate_rank"] = 1
    payload[0]["symbol"] = "000001.SZ"
    _rewrite_json(published_artifact, "candidate_recommendations.json", payload)

    with pytest.raises(ValueError, match="Candidate Recommendation identity"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_boolean_numeric_fields(published_artifact) -> None:
    payload = json.loads((published_artifact / "candidate_recommendations.json").read_text())
    payload[0]["candidate_score"] = True
    _rewrite_json(published_artifact, "candidate_recommendations.json", payload)

    with pytest.raises(ValueError, match="Candidate Recommendation"):
        load_verified_daily_quant_decision_artifact(published_artifact)


def test_reader_rejects_incomplete_implementation_identity(published_artifact) -> None:
    manifest = json.loads((published_artifact / "manifest.json").read_text())
    manifest["implementation_module_hashes"] = {}
    _rewrite_json(published_artifact, "manifest.json", manifest)

    with pytest.raises(ValueError, match="implementation module set"):
        load_verified_daily_quant_decision_artifact(published_artifact)
