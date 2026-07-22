"""Atomic Publisher for immutable Daily Quant Decision Artifacts V1."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any

from market_regime_alpha.daily_research.contracts import (
    CandidateRecommendation,
    DailyDataAuthority,
    DailyResearchSnapshot,
    EntryAssessment,
    InstrumentType,
    canonical_content_hash,
)
from market_regime_alpha.daily_research.policy import (
    evidence_authority,
    validate_daily_decision_aggregate,
)
from market_regime_alpha.daily_research.report import render_daily_quant_decision_report


DAILY_QUANT_DECISION_SCHEMA_VERSION = "daily-quant-decision-artifact-v1"
DAILY_QUANT_DECISION_FILES: tuple[str, ...] = (
    "manifest.json",
    "daily_research_snapshot.json",
    "candidate_recommendations.json",
    "entry_assessments.json",
    "report.md",
    "SHA256SUMS.json",
)
DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES: tuple[str, ...] = (
    "_contract_support.py",
    "contracts.py",
    "snapshot.py",
    "recommendation.py",
    "entry.py",
    "policy.py",
    "report.py",
    "artifacts.py",
    "reader.py",
)
DAILY_QUANT_DECISION_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "snapshot_id",
        "snapshot_content_hash",
        "snapshot_record_hash",
        "decision_date",
        "decision_time",
        "data_authority",
        "evidence_authority",
        "required_artifacts",
        "implementation_module_hashes",
        "recommendation_ids",
        "entry_assessment_ids",
        "recommendation_count",
        "entry_assessment_count",
        "instrument_counts",
    }
)


def publish_daily_quant_decision_artifact(
    *,
    root: str | Path,
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> Path:
    """Publish one exact, non-overwriting daily decision evidence package."""

    ordered_recommendations, ordered_entries = validate_daily_decision_aggregate(
        snapshot=snapshot,
        recommendations=recommendations,
        entry_assessments=entry_assessments,
    )
    artifact_id = daily_quant_decision_artifact_id(
        snapshot=snapshot,
        recommendations=ordered_recommendations,
        entry_assessments=ordered_entries,
    )
    root_path = Path(root)
    final = root_path / artifact_id
    stage = root_path / f".{artifact_id}.staging"
    if final.exists() or stage.exists():
        raise FileExistsError(f"daily decision Artifact path already exists: {final}")
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "daily_research_snapshot.json", snapshot.to_canonical_dict())
        _write_json(
            stage / "candidate_recommendations.json",
            [item.to_canonical_dict() for item in ordered_recommendations],
        )
        _write_json(
            stage / "entry_assessments.json",
            [item.to_canonical_dict() for item in ordered_entries],
        )
        (stage / "report.md").write_text(
            render_daily_quant_decision_report(snapshot, ordered_recommendations, ordered_entries),
            encoding="utf-8",
        )
        manifest = build_daily_quant_decision_manifest(
            snapshot=snapshot,
            recommendations=ordered_recommendations,
            entry_assessments=ordered_entries,
        )
        _write_json(stage / "manifest.json", manifest)
        _write_json(
            stage / "SHA256SUMS.json",
            {
                path.name: content_hash(path)
                for path in sorted(stage.iterdir(), key=lambda item: item.name)
                if path.is_file()
            },
        )
        actual = {item.name for item in stage.iterdir() if item.is_file()}
        if actual != set(DAILY_QUANT_DECISION_FILES):
            raise RuntimeError("daily decision staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def build_daily_quant_decision_manifest(
    *,
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> dict[str, Any]:
    counts = Counter(item.instrument_type.value for item in recommendations)
    return {
        "schema_version": DAILY_QUANT_DECISION_SCHEMA_VERSION,
        "artifact_id": daily_quant_decision_artifact_id(
            snapshot=snapshot,
            recommendations=recommendations,
            entry_assessments=entry_assessments,
        ),
        "snapshot_id": str(snapshot.snapshot_id),
        "snapshot_content_hash": snapshot.content_hash,
        "snapshot_record_hash": canonical_content_hash(snapshot.to_canonical_dict()),
        "decision_date": snapshot.decision_date.isoformat(),
        "decision_time": snapshot.decision_time.isoformat(),
        "data_authority": snapshot.data_authority.value,
        "evidence_authority": evidence_authority(snapshot.data_authority),
        "required_artifacts": sorted(DAILY_QUANT_DECISION_FILES),
        "implementation_module_hashes": implementation_module_hashes(),
        "recommendation_ids": [str(item.recommendation_id) for item in recommendations],
        "entry_assessment_ids": [str(item.entry_assessment_id) for item in entry_assessments],
        "recommendation_count": len(recommendations),
        "entry_assessment_count": len(entry_assessments),
        "instrument_counts": {key: counts.get(key, 0) for key in sorted(item.value for item in InstrumentType)},
    }


def daily_quant_decision_artifact_id(
    *,
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> str:
    """Derive the package identity from every result-affecting record identity."""

    ordered_recommendations = tuple(
        sorted(
            recommendations,
            key=lambda item: (item.instrument_type.value, item.candidate_rank, item.symbol),
        )
    )
    ordered_entries = tuple(sorted(entry_assessments, key=lambda item: str(item.recommendation_id)))
    payload = {
        "schema_version": DAILY_QUANT_DECISION_SCHEMA_VERSION,
        "snapshot_id": str(snapshot.snapshot_id),
        "snapshot_content_hash": snapshot.content_hash,
        "snapshot_record_hash": canonical_content_hash(snapshot.to_canonical_dict()),
        "data_authority": snapshot.data_authority.value,
        "implementation_module_hashes": implementation_module_hashes(),
        "recommendation_ids": [str(item.recommendation_id) for item in ordered_recommendations],
        "entry_assessment_ids": [str(item.entry_assessment_id) for item in ordered_entries],
    }
    digest = canonical_content_hash(payload).split(":", 1)[1][:24]
    prefix = (
        "test-only-daily-quant-decision"
        if snapshot.data_authority is DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE
        else "daily-quant-decision"
    )
    return f"{prefix}-{digest}"


def implementation_module_hashes() -> dict[str, str]:
    module_root = Path(__file__).resolve().parent
    return {
        name: content_hash(module_root / name)
        for name in DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES
    }


def content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def write_json(path: Path, value: Any) -> None:
    _write_json(path, value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_json_object(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def read_json_array(path: Path) -> list[Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path.name} must contain an array")
    return value
