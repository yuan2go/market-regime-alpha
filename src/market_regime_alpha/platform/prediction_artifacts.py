"""Atomic content-addressed Publisher for one PredictionRun."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.platform.contracts import ModelDefinition, ModelRole
from market_regime_alpha.platform.prediction_run import PredictionRun


PREDICTION_RUN_ARTIFACT_SCHEMA = "candidate-prediction-run-artifact-v1"
PREDICTION_RUN_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "manifest.json",
    "model_definition.json",
    "prediction_run.json",
)


def publish_prediction_run_artifact(
    *,
    root: Path,
    prediction_run: PredictionRun,
    model_definition: ModelDefinition,
) -> Path:
    """Publish an exact, checksum-covered, non-overwriting package."""

    if model_definition.model_id != prediction_run.model_id:
        raise ValueError("ModelDefinition identity does not match PredictionRun")
    if model_definition.role is not ModelRole.CANDIDATE:
        raise ValueError("PredictionRun requires a Candidate ModelDefinition")
    if model_definition.definition_hash != prediction_run.model_definition_hash:
        raise ValueError("ModelDefinition hash does not match PredictionRun")
    if model_definition.parameter_hash != prediction_run.configuration_hash:
        raise ValueError("ModelDefinition parameters do not match PredictionRun configuration")
    if (
        model_definition.target_id != prediction_run.target_id
        or model_definition.universe_id != prediction_run.universe_id
        or model_definition.feature_ids != prediction_run.feature_definition_ids
    ):
        raise ValueError("ModelDefinition scope does not match PredictionRun")
    root.mkdir(parents=True, exist_ok=True)
    final = root / str(prediction_run.prediction_run_id)
    if final.exists():
        raise FileExistsError(f"PredictionRun Artifact already exists: {final}")
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{prediction_run.prediction_run_id}.",
            dir=root,
        )
    )
    try:
        model_payload = model_definition.canonical_payload()
        run_payload = prediction_run.to_canonical_dict()
        manifest = {
            "schema_version": PREDICTION_RUN_ARTIFACT_SCHEMA,
            "prediction_run_id": str(prediction_run.prediction_run_id),
            "content_hash": prediction_run.content_hash,
            "model_id": str(prediction_run.model_id),
            "model_definition_hash": prediction_run.model_definition_hash,
            "required_artifacts": sorted(PREDICTION_RUN_ARTIFACT_FILES),
            "data_eligibility": prediction_run.data_eligibility.value,
            "evidence_level": prediction_run.evidence_level.value,
        }
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "model_definition.json", model_payload)
        _write_json(stage / "prediction_run.json", run_payload)
        checksums = {
            name: _content_hash(stage / name)
            for name in (
                "manifest.json",
                "model_definition.json",
                "prediction_run.json",
            )
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        if {item.name for item in stage.iterdir()} != set(
            PREDICTION_RUN_ARTIFACT_FILES
        ):
            raise RuntimeError("PredictionRun staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _content_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"
