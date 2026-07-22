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
    "contracts.py",
    "artifacts.py",
    "reader.py",
)
DAILY_QUANT_DECISION_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_id",
        "snapshot_id",
        "snapshot_content_hash",
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


def validate_daily_decision_aggregate(
    *,
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> tuple[tuple[CandidateRecommendation, ...], tuple[EntryAssessment, ...]]:
    """Validate cross-record references and deterministic ordering."""

    if not isinstance(snapshot, DailyResearchSnapshot):
        raise TypeError("snapshot must be a DailyResearchSnapshot")
    if any(not isinstance(item, CandidateRecommendation) for item in recommendations):
        raise TypeError("recommendations must contain CandidateRecommendation values")
    if any(not isinstance(item, EntryAssessment) for item in entry_assessments):
        raise TypeError("entry_assessments must contain EntryAssessment values")
    ordered_recommendations = tuple(
        sorted(
            recommendations,
            key=lambda item: (item.instrument_type.value, item.candidate_rank, item.symbol),
        )
    )
    recommendation_ids = tuple(str(item.recommendation_id) for item in ordered_recommendations)
    if len(recommendation_ids) != len(set(recommendation_ids)):
        raise ValueError("Candidate Recommendation IDs must be unique")
    symbol_keys = tuple((item.instrument_type, item.symbol) for item in ordered_recommendations)
    if len(symbol_keys) != len(set(symbol_keys)):
        raise ValueError("Candidate Recommendation instrument/symbol keys must be unique")
    for instrument_type in InstrumentType:
        ranks = tuple(
            item.candidate_rank
            for item in ordered_recommendations
            if item.instrument_type is instrument_type
        )
        if ranks != tuple(range(1, len(ranks) + 1)):
            raise ValueError(f"{instrument_type.value} Candidate ranks must be contiguous from one")
    for recommendation in ordered_recommendations:
        if recommendation.decision_snapshot_id != snapshot.snapshot_id:
            raise ValueError("Candidate Recommendation references a different snapshot")
        if recommendation.data_authority is not snapshot.data_authority:
            raise ValueError("Candidate Recommendation authority mismatch")
        if recommendation.model_identity != snapshot.model_identity:
            raise ValueError("Candidate Recommendation model identity mismatch")

    ordered_entries = tuple(sorted(entry_assessments, key=lambda item: str(item.recommendation_id)))
    entry_recommendation_ids = tuple(str(item.recommendation_id) for item in ordered_entries)
    if len(entry_recommendation_ids) != len(set(entry_recommendation_ids)):
        raise ValueError("one Entry Assessment per recommendation is required")
    if set(entry_recommendation_ids) != set(recommendation_ids):
        raise ValueError("Entry Assessment coverage must exactly match recommendations")
    for entry in ordered_entries:
        if entry.decision_snapshot_id != snapshot.snapshot_id:
            raise ValueError("Entry Assessment references a different snapshot")
        if entry.data_authority is not snapshot.data_authority:
            raise ValueError("Entry Assessment authority mismatch")
    return ordered_recommendations, ordered_entries


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

    payload = {
        "schema_version": DAILY_QUANT_DECISION_SCHEMA_VERSION,
        "snapshot_id": str(snapshot.snapshot_id),
        "snapshot_content_hash": snapshot.content_hash,
        "data_authority": snapshot.data_authority.value,
        "implementation_module_hashes": implementation_module_hashes(),
        "recommendation_ids": [str(item.recommendation_id) for item in recommendations],
        "entry_assessment_ids": [str(item.entry_assessment_id) for item in entry_assessments],
    }
    digest = canonical_content_hash(payload).split(":", 1)[1][:24]
    prefix = (
        "test-only-daily-quant-decision"
        if snapshot.data_authority is DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE
        else "daily-quant-decision"
    )
    return f"{prefix}-{digest}"


def evidence_authority(data_authority: DailyDataAuthority) -> str:
    if data_authority is DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE:
        return DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE.value
    return "NOT_FORMAL_OOS"


def implementation_module_hashes() -> dict[str, str]:
    module_root = Path(__file__).resolve().parent
    return {
        name: content_hash(module_root / name)
        for name in DAILY_QUANT_DECISION_IMPLEMENTATION_MODULES
    }


def render_daily_quant_decision_report(
    snapshot: DailyResearchSnapshot,
    recommendations: tuple[CandidateRecommendation, ...],
    entry_assessments: tuple[EntryAssessment, ...],
) -> str:
    """Render the human-readable report solely from structured evidence."""

    entries = {entry.recommendation_id: entry for entry in entry_assessments}
    lines = [
        "# Daily Quant Decision Report",
        "",
        "## Evidence identity",
        "",
        f"- Snapshot: `{snapshot.snapshot_id}`",
        f"- Decision Time: `{snapshot.decision_time.isoformat()}`",
        f"- Data Authority: `{snapshot.data_authority.value}`",
        f"- Evidence Authority: `{evidence_authority(snapshot.data_authority)}`",
        "- No Alpha or trading authority is established by this report.",
        "- Source Artifacts: "
        + ", ".join(
            f"`{source.artifact_id}` ({source.provider_id}, {source.data_authority.value})"
            for source in snapshot.source_artifacts
        ),
        "",
        "## Candidate Recommendations and Entry Assessments",
        "",
    ]
    if not recommendations:
        lines.extend(
            [
                "- No Candidate Recommendation was produced. This valid empty result was not backfilled.",
                "",
            ]
        )
    for recommendation in recommendations:
        entry = entries[recommendation.recommendation_id]
        lines.extend(
            [
                f"### {recommendation.candidate_rank}. {recommendation.symbol} ({recommendation.instrument_type.value})",
                "",
                f"- Candidate score: `{recommendation.candidate_score}`",
                "- Score components: "
                + ", ".join(f"{item.name}={item.value}" for item in recommendation.score_components),
                f"- Candidate model: `{recommendation.model_identity}`",
                f"- Target: `{recommendation.target_definition}`",
                f"- Expected horizon: `{recommendation.expected_horizon}`",
                f"- Industry: `{recommendation.industry or 'UNAVAILABLE'}`",
                f"- Themes: {', '.join(recommendation.themes) or 'UNAVAILABLE'}",
                f"- Related ETFs: {', '.join(recommendation.related_etfs) or 'UNAVAILABLE'}",
                f"- Data quality: `{recommendation.data_quality.value}`",
                f"- Selection reasons: {', '.join(recommendation.selection_reasons)}",
                f"- Risk reasons: {', '.join(recommendation.risk_reasons) or 'NONE_DECLARED'}",
                f"- Invalidation conditions: {', '.join(recommendation.invalidation_conditions)}",
                f"- Entry state: `{entry.entry_state.value}`",
                f"- Entry score: `{entry.entry_score}`",
                f"- Reference price: `{entry.reference_price}`",
                "- Preferred price zone: `"
                + (
                    f"{entry.preferred_price_zone.lower}..{entry.preferred_price_zone.upper}"
                    if entry.preferred_price_zone is not None
                    else "UNAVAILABLE"
                )
                + "`",
                f"- Maximum acceptable price: `{entry.maximum_acceptable_price}`",
                f"- Invalidation price: `{entry.invalidation_price}`",
                f"- Expected MFE / MAE: `{entry.expected_mfe}` / `{entry.expected_mae}`",
                f"- Risk/reward estimate: `{entry.risk_reward_estimate}`",
                f"- Uncertainty: `{entry.uncertainty}`",
                f"- Entry reasons: {', '.join(entry.entry_reasons) or 'NONE_DECLARED'}",
                f"- Blocking reasons: {', '.join(entry.blocking_reasons) or 'NONE'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundaries",
            "",
            "- Candidate ranking and Entry timing are separate records.",
            "- This Artifact contains no manual trade, broker fill, Portfolio Decision, or order.",
            "- Auxiliary or exploratory evidence cannot substitute for formal Xuntou PIT validation.",
            "",
        ]
    )
    return "\n".join(lines)


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
