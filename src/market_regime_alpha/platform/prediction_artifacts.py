"""Atomic content-addressed Publisher for one PredictionRun."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.platform.contracts import ModelDefinition, ModelRole
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.platform.runtime_governance import (
    ModelSelectionReceipt,
    RuntimeModelLineage,
    SelectionStatus,
)


PREDICTION_RUN_ARTIFACT_SCHEMA = "candidate-prediction-run-artifact-v1"
PREDICTION_RUN_ARTIFACT_FILES = (
    "SHA256SUMS.json",
    "manifest.json",
    "model_definition.json",
    "prediction_run.json",
)
GOVERNED_PREDICTION_RUN_ARTIFACT_SCHEMA = (
    "candidate-prediction-run-artifact-v2"
)
GOVERNED_PREDICTION_RUN_ARTIFACT_FILES = (
    *PREDICTION_RUN_ARTIFACT_FILES,
    "model_selection_receipt.json",
    "runtime_model_lineage.json",
)


def publish_prediction_run_artifact(
    *,
    root: Path,
    prediction_run: PredictionRun,
    model_definition: ModelDefinition,
    model_selection_receipt: ModelSelectionReceipt | None = None,
    runtime_model_lineage: RuntimeModelLineage | None = None,
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
    governed = (
        model_selection_receipt is not None or runtime_model_lineage is not None
    )
    if (model_selection_receipt is None) != (runtime_model_lineage is None):
        raise ValueError("governed PredictionRun evidence must be complete")
    runtime_universe_bound = model_definition.universe_id != prediction_run.universe_id
    if governed:
        _validate_governed_runtime_binding(
            prediction_run=prediction_run,
            model_definition=model_definition,
            model_selection_receipt=model_selection_receipt,
            runtime_model_lineage=runtime_model_lineage,
        )
    elif runtime_universe_bound:
        raise ValueError(
            "Runtime Universe mismatch requires exact Model Selection lineage"
        )
    if (
        model_definition.target_id != prediction_run.target_id
        or (
            model_definition.universe_id != prediction_run.universe_id
            and not runtime_universe_bound
        )
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
        artifact_schema = (
            GOVERNED_PREDICTION_RUN_ARTIFACT_SCHEMA
            if governed
            else PREDICTION_RUN_ARTIFACT_SCHEMA
        )
        artifact_files = (
            GOVERNED_PREDICTION_RUN_ARTIFACT_FILES
            if governed
            else PREDICTION_RUN_ARTIFACT_FILES
        )
        manifest = {
            "schema_version": artifact_schema,
            "prediction_run_id": str(prediction_run.prediction_run_id),
            "content_hash": prediction_run.content_hash,
            "model_id": str(prediction_run.model_id),
            "model_definition_hash": prediction_run.model_definition_hash,
            "required_artifacts": sorted(artifact_files),
            "data_eligibility": prediction_run.data_eligibility.value,
            "evidence_level": prediction_run.evidence_level.value,
        }
        _write_json(stage / "manifest.json", manifest)
        _write_json(stage / "model_definition.json", model_payload)
        _write_json(stage / "prediction_run.json", run_payload)
        if governed:
            assert model_selection_receipt is not None
            assert runtime_model_lineage is not None
            manifest.update(
                {
                    "model_selection_receipt_id": str(
                        model_selection_receipt.receipt_id
                    ),
                    "model_selection_receipt_hash": (
                        model_selection_receipt.receipt_hash
                    ),
                    "runtime_lineage_id": str(
                        runtime_model_lineage.runtime_lineage_id
                    ),
                    "runtime_lineage_hash": (
                        runtime_model_lineage.runtime_lineage_hash
                    ),
                }
            )
            _write_json(
                stage / "model_selection_receipt.json",
                model_selection_receipt.to_canonical_dict(),
            )
            _write_json(
                stage / "runtime_model_lineage.json",
                runtime_model_lineage.to_canonical_dict(),
            )
            _write_json(stage / "manifest.json", manifest)
        checksums = {
            name: _content_hash(stage / name)
            for name in artifact_files
            if name != "SHA256SUMS.json"
        }
        _write_json(stage / "SHA256SUMS.json", checksums)
        if {item.name for item in stage.iterdir()} != set(
            artifact_files
        ):
            raise RuntimeError("PredictionRun staging exact file set mismatch")
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final


def _validate_governed_runtime_binding(
    *,
    prediction_run: PredictionRun,
    model_definition: ModelDefinition,
    model_selection_receipt: ModelSelectionReceipt | None,
    runtime_model_lineage: RuntimeModelLineage | None,
) -> None:
    materialization_ids = tuple(
        reference.artifact_id
        for reference in runtime_model_lineage.feature_materializations
    ) if runtime_model_lineage is not None else ()
    validation_ids = tuple(
        reference.artifact_id
        for reference in runtime_model_lineage.validation_protocol_refs
    ) if runtime_model_lineage is not None else ()
    runtime_universe_bound = model_definition.universe_id != prediction_run.universe_id
    if (
        model_selection_receipt is None
        or runtime_model_lineage is None
        or (
            runtime_universe_bound
            and "RUNTIME_UNIVERSE_BOUND_BY_SELECTION_LINEAGE"
            not in model_definition.compatibility_refs
        )
        or model_selection_receipt.status is not SelectionStatus.SELECTED
        or model_selection_receipt.selected_model_id != prediction_run.model_id
        or model_selection_receipt.selected_definition_hash
        != model_definition.definition_hash
        or model_selection_receipt.runtime_lineage_hash
        != runtime_model_lineage.runtime_lineage_hash
        or runtime_model_lineage.model_id != prediction_run.model_id
        or runtime_model_lineage.definition_hash
        != prediction_run.model_definition_hash
        or runtime_model_lineage.universe_id != prediction_run.universe_id
        or runtime_model_lineage.feature_definition_ids
        != prediction_run.feature_definition_ids
        or runtime_model_lineage.dataset.artifact_id
        != ArtifactId(str(prediction_run.dataset_id))
        or materialization_ids
        != tuple(
            ArtifactId(str(item))
            for item in prediction_run.feature_materialization_ids
        )
        or runtime_model_lineage.configuration.content_hash
        != f"sha256:{prediction_run.configuration_hash}"
        or runtime_model_lineage.code_revision != prediction_run.code_revision
        or validation_ids
        != (ArtifactId(str(prediction_run.evaluation_protocol_id)),)
        or runtime_model_lineage.data_eligibility
        is not prediction_run.data_eligibility
        or model_selection_receipt.selected_at
        != prediction_run.decision_time.value
    ):
        raise ValueError(
            "PredictionRun requires exact Model Selection execution lineage"
        )


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
