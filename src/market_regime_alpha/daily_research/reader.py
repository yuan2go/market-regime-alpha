"""Semantic Reader for Daily Quant Decision Artifacts V1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.daily_research.artifacts import (
    DAILY_QUANT_DECISION_FILES,
    DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES,
    DAILY_QUANT_DECISION_MANIFEST_FIELDS,
    DAILY_QUANT_DECISION_SCHEMA_VERSION,
    build_daily_quant_decision_manifest,
    content_hash,
    implementation_module_hashes,
    read_json_array,
    read_json_object,
    render_daily_quant_decision_report,
    validate_daily_decision_aggregate,
)
from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyResearchSnapshot,
    EntryAssessment,
)


@dataclass(frozen=True, slots=True)
class VerifiedDailyQuantDecisionArtifact:
    """Typed, semantically reconstructed daily decision evidence."""

    root: Path
    artifact_id: str
    snapshot: DailyResearchSnapshot
    recommendations: tuple[CandidateRecommendation, ...]
    entry_assessments: tuple[EntryAssessment, ...]
    manifest: Mapping[str, Any]
    checksums_hash: str


def load_verified_daily_quant_decision_artifact(path: str | Path) -> VerifiedDailyQuantDecisionArtifact:
    """Verify exact files, bytes, identities, references, and rendered report."""

    root = Path(path).resolve()
    _verify_files(root)
    manifest = read_json_object(root / "manifest.json")
    if set(manifest) != DAILY_QUANT_DECISION_MANIFEST_FIELDS:
        raise ValueError("daily decision manifest fields mismatch")
    if manifest.get("schema_version") != DAILY_QUANT_DECISION_SCHEMA_VERSION:
        raise ValueError("daily decision Artifact Schema mismatch")
    if manifest.get("required_artifacts") != sorted(DAILY_QUANT_DECISION_FILES):
        raise ValueError("daily decision required Artifact set mismatch")
    hashes = manifest.get("implementation_module_hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES):
        raise ValueError("daily decision implementation module set mismatch")
    if hashes != implementation_module_hashes():
        raise ValueError("daily decision implementation identity is stale")

    try:
        snapshot = DailyResearchSnapshot.from_canonical_dict(
            read_json_object(root / "daily_research_snapshot.json")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Daily Research Snapshot semantic verification failed") from exc
    recommendations = _recommendations(root)
    entries = _entries(root)
    ordered_recommendations, ordered_entries = validate_daily_decision_aggregate(
        snapshot=snapshot,
        recommendations=recommendations,
        entry_assessments=entries,
    )
    expected_manifest = build_daily_quant_decision_manifest(
        snapshot=snapshot,
        recommendations=ordered_recommendations,
        entry_assessments=ordered_entries,
    )
    if manifest != expected_manifest:
        raise ValueError("daily decision manifest is not semantically reconstructible")
    artifact_id = str(expected_manifest["artifact_id"])
    if root.name != artifact_id:
        raise ValueError("daily decision Artifact directory identity mismatch")
    expected_report = render_daily_quant_decision_report(snapshot, ordered_recommendations, ordered_entries)
    if (root / "report.md").read_text(encoding="utf-8") != expected_report:
        raise ValueError("daily decision report is not semantically reconstructible")
    return VerifiedDailyQuantDecisionArtifact(
        root=root,
        artifact_id=artifact_id,
        snapshot=snapshot,
        recommendations=ordered_recommendations,
        entry_assessments=ordered_entries,
        manifest=_deep_freeze(manifest),
        checksums_hash=content_hash(root / "SHA256SUMS.json"),
    )


def _recommendations(root: Path) -> tuple[CandidateRecommendation, ...]:
    values = read_json_array(root / "candidate_recommendations.json")
    records: list[CandidateRecommendation] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Candidate Recommendation must be an object")
        try:
            records.append(CandidateRecommendation.from_canonical_dict(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("Candidate Recommendation identity or semantics mismatch") from exc
    return tuple(records)


def _entries(root: Path) -> tuple[EntryAssessment, ...]:
    values = read_json_array(root / "entry_assessments.json")
    records: list[EntryAssessment] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Entry Assessment must be an object")
        try:
            records.append(EntryAssessment.from_canonical_dict(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("Entry Assessment identity or semantics mismatch") from exc
    return tuple(records)


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("daily decision Artifact is missing")
    actual = {item.name for item in root.iterdir() if item.is_file()}
    if actual != set(DAILY_QUANT_DECISION_FILES):
        raise ValueError("daily decision exact file set mismatch")
    checksums = read_json_object(root / "SHA256SUMS.json")
    expected_files = set(DAILY_QUANT_DECISION_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected_files:
        raise ValueError("daily decision checksum coverage mismatch")
    for name, expected in checksums.items():
        if not isinstance(expected, str) or content_hash(root / name) != expected:
            raise ValueError(f"daily decision checksum mismatch: {name}")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value
