"""Semantic Reader for Phase D Daily Decision Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.application.daily_loop.commands import DailyRunIdentity
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.daily_quality import DataQualityReport
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.daily_decision.artifact import (
    PHASE_D_DAILY_DECISION_FILES,
    PHASE_D_DAILY_DECISION_SCHEMA,
    DailyDecisionArtifactStatus,
    PhaseDDailyDecisionBundle,
    build_phase_d_manifest,
)
from market_regime_alpha.daily_decision.entry import EntryAssessment
from market_regime_alpha.daily_decision.recommendation import (
    CandidateRecommendation,
)
from market_regime_alpha.daily_decision.report import render_phase_d_daily_report
from market_regime_alpha.daily_decision.serialization import (
    eligibility_snapshot_from_dict,
    feature_definition_from_dict,
    feature_materialization_from_dict,
    universe_snapshot_from_dict,
)
from market_regime_alpha.daily_decision.snapshot import DecisionPriceSnapshot
from market_regime_alpha.platform.prediction_run import PredictionRun


@dataclass(frozen=True, slots=True)
class VerifiedPhaseDDailyDecisionArtifact:
    root: Path
    artifact_id: str
    bundle: PhaseDDailyDecisionBundle
    manifest: Mapping[str, Any]
    checksums_hash: str


def load_verified_phase_d_daily_decision_artifact(
    path: Path,
) -> VerifiedPhaseDDailyDecisionArtifact:
    root = path.resolve()
    _verify_files(root)
    manifest = _read_object(root / "manifest.json")
    expected_manifest_fields = {
        "schema_version",
        "artifact_id",
        "content_hash",
        "status",
        "run_identity",
        "source_archive_id",
        "source_manifest_id",
        "source_manifest_hash",
        "data_quality_report_id",
        "required_artifacts",
        "evidence_authority",
        "delivery_authority",
        "formal_oos_authority",
        "trading_authority",
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("Phase D manifest fields mismatch")
    if manifest["schema_version"] != PHASE_D_DAILY_DECISION_SCHEMA:
        raise ValueError("Phase D manifest schema mismatch")
    if manifest["required_artifacts"] != sorted(PHASE_D_DAILY_DECISION_FILES):
        raise ValueError("Phase D required artifacts mismatch")
    source_manifest = SourceManifest.from_canonical_dict(
        _read_object(root / "source_manifest.json")
    )
    quality_report = DataQualityReport.from_canonical_dict(
        _read_object(root / "data_quality_report.json")
    )
    universe_file = _read_wrapper(
        root / "universe_snapshot.json",
        schema="phase-d-universe-snapshot-v1",
        value_key="snapshot",
    )
    eligibility_file = _read_wrapper(
        root / "eligibility_snapshot.json",
        schema="phase-d-eligibility-snapshot-v1",
        value_key="snapshot",
    )
    decision_file = _read_wrapper(
        root / "decision_price_snapshot.json",
        schema="phase-d-decision-price-file-v1",
        value_key="snapshot",
    )
    feature_file = _read_object(root / "feature_manifest.json")
    if set(feature_file) != {
        "schema_version",
        "definitions",
        "materializations",
    } or feature_file["schema_version"] != "phase-d-feature-manifest-v1":
        raise ValueError("Feature Manifest schema mismatch")
    predictions_file = _read_items_wrapper(
        root / "prediction_runs.json",
        "phase-d-prediction-runs-v1",
    )
    recommendations_file = _read_items_wrapper(
        root / "candidate_recommendations.json",
        "phase-d-candidate-recommendations-v1",
    )
    entries_file = _read_items_wrapper(
        root / "entry_assessments.json",
        "phase-d-entry-assessments-v1",
    )
    bundle = PhaseDDailyDecisionBundle(
        status=DailyDecisionArtifactStatus(str(manifest["status"])),
        run_identity=DailyRunIdentity.from_canonical_dict(
            _mapping(manifest["run_identity"], "run_identity")
        ),
        source_archive_id=ArtifactId(str(manifest["source_archive_id"])),
        source_manifest=source_manifest,
        data_quality_report=quality_report,
        universe_snapshot=(
            universe_snapshot_from_dict(
                _mapping(universe_file, "universe snapshot")
            )
            if universe_file is not None
            else None
        ),
        eligibility_snapshot=(
            eligibility_snapshot_from_dict(
                _mapping(eligibility_file, "eligibility snapshot")
            )
            if eligibility_file is not None
            else None
        ),
        decision_price_snapshot=(
            DecisionPriceSnapshot.from_canonical_dict(
                _mapping(decision_file, "decision price snapshot")
            )
            if decision_file is not None
            else None
        ),
        feature_definitions=tuple(
            feature_definition_from_dict(_mapping(item, "FeatureDefinition"))
            for item in _array(feature_file["definitions"], "definitions")
        ),
        feature_materializations=tuple(
            feature_materialization_from_dict(
                _mapping(item, "FeatureMaterialization")
            )
            for item in _array(
                feature_file["materializations"],
                "materializations",
            )
        ),
        prediction_runs=tuple(
            PredictionRun.from_canonical_dict(_mapping(item, "PredictionRun"))
            for item in predictions_file
        ),
        recommendations=tuple(
            CandidateRecommendation.from_canonical_dict(
                _mapping(item, "CandidateRecommendation")
            )
            for item in recommendations_file
        ),
        entry_assessments=tuple(
            EntryAssessment.from_canonical_dict(
                _mapping(item, "EntryAssessment")
            )
            for item in entries_file
        ),
    )
    expected_manifest = build_phase_d_manifest(bundle)
    if manifest != expected_manifest:
        raise ValueError("Phase D manifest is not semantically reconstructible")
    if root.name != str(bundle.artifact_id):
        raise ValueError("Phase D Artifact directory identity mismatch")
    if (root / "report.md").read_text(
        encoding="utf-8"
    ) != render_phase_d_daily_report(bundle):
        raise ValueError("Phase D report is not reconstructible")
    return VerifiedPhaseDDailyDecisionArtifact(
        root=root,
        artifact_id=str(bundle.artifact_id),
        bundle=bundle,
        manifest=_deep_freeze(manifest),
        checksums_hash=_file_hash(root / "SHA256SUMS.json"),
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("Phase D Daily Decision Artifact is missing")
    entries = tuple(root.iterdir())
    if {item.name for item in entries} != set(PHASE_D_DAILY_DECISION_FILES):
        raise ValueError("Phase D exact file set mismatch")
    if any(not item.is_file() for item in entries):
        raise ValueError("Phase D exact file set contains a non-file")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected = set(PHASE_D_DAILY_DECISION_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected:
        raise ValueError("Phase D checksum coverage mismatch")
    for name, content_hash in checksums.items():
        if not isinstance(content_hash, str) or _file_hash(root / name) != content_hash:
            raise ValueError(f"Phase D checksum mismatch: {name}")


def _read_wrapper(
    path: Path,
    *,
    schema: str,
    value_key: str,
) -> Any:
    payload = _read_object(path)
    if set(payload) != {"schema_version", value_key}:
        raise ValueError(f"{path.name} fields mismatch")
    if payload["schema_version"] != schema:
        raise ValueError(f"{path.name} schema mismatch")
    return payload[value_key]


def _read_items_wrapper(path: Path, schema: str) -> list[Any]:
    value = _read_wrapper(path, schema=schema, value_key="items")
    return _array(value, path.name)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value
