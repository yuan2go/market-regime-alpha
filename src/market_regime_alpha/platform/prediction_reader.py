"""Semantic Reader for immutable Candidate PredictionRun Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.platform.prediction_artifacts import (
    GOVERNED_PREDICTION_RUN_ARTIFACT_FILES,
    GOVERNED_PREDICTION_RUN_ARTIFACT_SCHEMA,
    PREDICTION_RUN_ARTIFACT_FILES,
    PREDICTION_RUN_ARTIFACT_SCHEMA,
)
from market_regime_alpha.platform.contracts import ModelDefinition, ModelRole
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.platform.runtime_governance import (
    ModelSelectionReceipt,
    RuntimeModelLineage,
    SelectionStatus,
)


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
    model_selection_receipt: ModelSelectionReceipt | None = None
    runtime_model_lineage: RuntimeModelLineage | None = None


def load_verified_prediction_run_artifact(
    path: Path,
) -> VerifiedPredictionRunArtifact:
    """Verify package bytes, identities and cross-record semantics."""

    root = path.resolve()
    _verify_files(root)
    manifest = _read_object(root / "manifest.json")
    base_manifest_fields = {
        "schema_version",
        "prediction_run_id",
        "content_hash",
        "model_id",
        "model_definition_hash",
        "required_artifacts",
        "data_eligibility",
        "evidence_level",
    }
    governed = manifest.get("schema_version") == (
        GOVERNED_PREDICTION_RUN_ARTIFACT_SCHEMA
    )
    expected_manifest_fields = base_manifest_fields | (
        {
            "model_selection_receipt_id",
            "model_selection_receipt_hash",
            "runtime_lineage_id",
            "runtime_lineage_hash",
        }
        if governed
        else set()
    )
    if set(manifest) != expected_manifest_fields:
        raise ValueError("PredictionRun Artifact manifest fields mismatch")
    if manifest.get("schema_version") not in {
        PREDICTION_RUN_ARTIFACT_SCHEMA,
        GOVERNED_PREDICTION_RUN_ARTIFACT_SCHEMA,
    }:
        raise ValueError("unsupported PredictionRun Artifact schema")
    if manifest.get("required_artifacts") != sorted(
        (
            GOVERNED_PREDICTION_RUN_ARTIFACT_FILES
            if governed
            else PREDICTION_RUN_ARTIFACT_FILES
        )
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
    model_selection_receipt = None
    runtime_model_lineage = None
    runtime_universe_bound = definition.get("universe_id") != str(run.universe_id)
    if governed:
        model_selection_receipt = ModelSelectionReceipt.from_canonical_dict(
            _read_object(root / "model_selection_receipt.json")
        )
        runtime_model_lineage = RuntimeModelLineage.from_canonical_dict(
            _read_object(root / "runtime_model_lineage.json")
        )
        materialization_ids = tuple(
            reference.artifact_id
            for reference in runtime_model_lineage.feature_materializations
        )
        validation_ids = tuple(
            reference.artifact_id
            for reference in runtime_model_lineage.validation_protocol_refs
        )
        if (
            (
                runtime_universe_bound
                and "RUNTIME_UNIVERSE_BOUND_BY_SELECTION_LINEAGE"
                not in definition.get("compatibility_refs", [])
            )
            or model_selection_receipt.status is not SelectionStatus.SELECTED
            or model_selection_receipt.selected_model_id != run.model_id
            or model_selection_receipt.selected_definition_hash
            != run.model_definition_hash
            or model_selection_receipt.runtime_lineage_hash
            != runtime_model_lineage.runtime_lineage_hash
            or runtime_model_lineage.model_id != run.model_id
            or runtime_model_lineage.definition_hash != run.model_definition_hash
            or runtime_model_lineage.universe_id != run.universe_id
            or runtime_model_lineage.feature_definition_ids
            != run.feature_definition_ids
            or runtime_model_lineage.dataset.artifact_id
            != ArtifactId(str(run.dataset_id))
            or materialization_ids
            != tuple(
                ArtifactId(str(item))
                for item in run.feature_materialization_ids
            )
            or runtime_model_lineage.configuration.content_hash
            != f"sha256:{run.configuration_hash}"
            or runtime_model_lineage.code_revision != run.code_revision
            or validation_ids
            != (ArtifactId(str(run.evaluation_protocol_id)),)
            or runtime_model_lineage.data_eligibility is not run.data_eligibility
            or model_selection_receipt.selected_at != run.decision_time.value
        ):
            raise ValueError("governed PredictionRun execution lineage mismatch")
    elif runtime_universe_bound:
        raise ValueError(
            "Runtime Universe mismatch lacks governed Artifact evidence"
        )
    if (
        definition.get("model_id") != str(run.model_id)
        or definition.get("target_id") != str(run.target_id)
        or (
            definition.get("universe_id") != str(run.universe_id)
            and not runtime_universe_bound
        )
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
    expected_manifest = {
        "schema_version": PREDICTION_RUN_ARTIFACT_SCHEMA,
        "prediction_run_id": str(run.prediction_run_id),
        "content_hash": run.content_hash,
        "model_id": str(run.model_id),
        "model_definition_hash": run.model_definition_hash,
        "required_artifacts": sorted(PREDICTION_RUN_ARTIFACT_FILES),
        "data_eligibility": run.data_eligibility.value,
        "evidence_level": run.evidence_level.value,
    }
    if governed:
        assert model_selection_receipt is not None
        assert runtime_model_lineage is not None
        expected_manifest.update(
            {
                "schema_version": GOVERNED_PREDICTION_RUN_ARTIFACT_SCHEMA,
                "required_artifacts": sorted(
                    GOVERNED_PREDICTION_RUN_ARTIFACT_FILES
                ),
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
    if manifest != expected_manifest:
        raise ValueError("PredictionRun manifest is not reconstructible")
    if root.name != str(run.prediction_run_id):
        raise ValueError("PredictionRun Artifact directory identity mismatch")
    return VerifiedPredictionRunArtifact(
        root=root,
        manifest=MappingProxyType(manifest),
        model_definition=MappingProxyType(definition),
        prediction_run=run,
        checksums_hash=_content_hash(root / "SHA256SUMS.json"),
        model_selection_receipt=model_selection_receipt,
        runtime_model_lineage=runtime_model_lineage,
    )


def _verify_files(root: Path) -> None:
    if not root.is_dir():
        raise ValueError("PredictionRun Artifact is missing")
    actual = {item.name for item in root.iterdir()}
    if frozenset(actual) not in {
        frozenset(PREDICTION_RUN_ARTIFACT_FILES),
        frozenset(GOVERNED_PREDICTION_RUN_ARTIFACT_FILES),
    }:
        raise ValueError("PredictionRun exact file set mismatch")
    if any(not (root / name).is_file() for name in actual):
        raise ValueError("PredictionRun exact file set contains a non-file entry")
    checksums = _read_object(root / "SHA256SUMS.json")
    expected_names = actual - {"SHA256SUMS.json"}
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
