"""Semantic Reader for immutable Candidate PredictionRun Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.platform.prediction_artifacts import (
    PREDICTION_RUN_ARTIFACT_FILES,
    PREDICTION_RUN_ARTIFACT_SCHEMA,
)
from market_regime_alpha.platform.contracts import ModelDefinition, ModelRole
from market_regime_alpha.platform.prediction_run import PredictionRun


_MODEL_DEFINITION_FIELDS = {
    "schema_version",
    "model_id",
    "name",
    "version",
    "family",
    "role",
    "target_id",
    "universe_id",
    "feature_ids",
    "implementation_ref",
    "parameter_hash",
    "decision_time_convention",
    "horizon",
    "theory_ids",
    "parent_model_id",
    "supported_data_eligibilities",
    "compatibility_refs",
}


@dataclass(frozen=True, slots=True)
class VerifiedPredictionRunArtifact:
    root: Path
    manifest: Mapping[str, Any]
    model_definition: Mapping[str, Any]
    prediction_run: PredictionRun
    checksums_hash: str


def load_verified_prediction_run_artifact(
    path: Path,
) -> VerifiedPredictionRunArtifact:
    """Verify package bytes, identities and cross-record semantics."""

    root = path.resolve()
    _verify_files(root)
    manifest = _read_object(root / "manifest.json")
    expected_manifest_fields = {
        "schema_version",
        "prediction_run_id",
        "content_hash",
        "model_id",
        "model_definition_hash",
        "required_artifacts",
        "data_eligibility",
        "evidence_level",
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("PredictionRun Artifact manifest fields mismatch")
    if manifest.get("schema_version") != PREDICTION_RUN_ARTIFACT_SCHEMA:
        raise ValueError("unsupported PredictionRun Artifact schema")
    if manifest.get("required_artifacts") != sorted(
        PREDICTION_RUN_ARTIFACT_FILES
    ):
        raise ValueError("PredictionRun required Artifact set mismatch")
    run = PredictionRun.from_canonical_dict(
        _read_object(root / "prediction_run.json")
    )
    definition = _read_object(root / "model_definition.json")
    if set(definition) != _MODEL_DEFINITION_FIELDS:
        raise ValueError("ModelDefinition fields mismatch")
    if (
        definition.get("schema_version") != ModelDefinition.SCHEMA_VERSION
        or definition.get("role") != ModelRole.CANDIDATE.value
    ):
        raise ValueError("unsupported PredictionRun ModelDefinition")
    definition_hash = _canonical_digest(definition)
    if (
        definition.get("model_id") != str(run.model_id)
        or definition.get("target_id") != str(run.target_id)
        or definition.get("universe_id") != str(run.universe_id)
        or definition.get("feature_ids")
        != [str(value) for value in run.feature_definition_ids]
        or definition.get("parameter_hash") != run.configuration_hash
        or definition_hash != run.model_definition_hash
    ):
        raise ValueError("ModelDefinition does not match PredictionRun")
    if run.data_eligibility.value not in definition.get(
        "supported_data_eligibilities",
        [],
    ):
        raise ValueError("PredictionRun DataEligibility is not model-compatible")
    if manifest != {
        "schema_version": PREDICTION_RUN_ARTIFACT_SCHEMA,
        "prediction_run_id": str(run.prediction_run_id),
        "content_hash": run.content_hash,
        "model_id": str(run.model_id),
        "model_definition_hash": run.model_definition_hash,
        "required_artifacts": sorted(PREDICTION_RUN_ARTIFACT_FILES),
        "data_eligibility": run.data_eligibility.value,
        "evidence_level": run.evidence_level.value,
    }:
        raise ValueError("PredictionRun manifest is not reconstructible")
    if root.name != str(run.prediction_run_id):
        raise ValueError("PredictionRun Artifact directory identity mismatch")
    return VerifiedPredictionRunArtifact(
        root=root,
        manifest=MappingProxyType(manifest),
        model_definition=MappingProxyType(definition),
        prediction_run=run,
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("PredictionRun Artifact is missing")
    actual = {item.name for item in root.iterdir()}
    if actual != set(PREDICTION_RUN_ARTIFACT_FILES):
        raise ValueError("PredictionRun exact file set mismatch")
    if any(not (root / name).is_file() for name in actual):
        raise ValueError("PredictionRun exact file set contains a non-file entry")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected_names = set(PREDICTION_RUN_ARTIFACT_FILES) - {"SHA256SUMS.json"}
    if set(checksums) != expected_names:
        raise ValueError("PredictionRun checksum coverage mismatch")
    for name, expected in checksums.items():
        if not isinstance(expected, str) or _content_hash(root / name) != expected:
            raise ValueError(f"PredictionRun checksum mismatch: {name}")


def _read_object(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
