"""Read the exact Model owner graph; no latest-version substitution or fitting."""

from dataclasses import asdict
from hashlib import sha256
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.queries.model_training_inputs import PostgresModelTrainingInputProvider
from market_regime_alpha.infrastructure.postgres.repositories.research_models import PostgresResearchModelRepository
from market_regime_alpha.research_qualification.application.deterministic_linear import load_deterministic_ridge_artifact
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def model_training_lineage(pool: Any, store: Any, model_version_id: UUID) -> dict[str, Any]:
    with pool.connection(read_only=True) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        owner = PostgresResearchModelRepository(connection)
        version = owner.version_record(model_version_id, lock=False)
        training = owner.training_run_record(version.model_training_run_id, lock=False)
        model = owner.model_record(version.model_id, lock=False)
        if training.model_id != model.model_id:
            raise ArtifactIntegrityError("MODEL_TRAINING_PARENT_MISMATCH")
        with connection.cursor(row_factory=dict_row) as cursor:
            fitted = cursor.execute("""SELECT artifact.artifact_id, artifact.content_sha256, artifact.size_bytes,
                version.fitted_model_content_sha256 AS frozen_sha256, version.fitted_model_size_bytes AS frozen_size
                FROM mra.model_version version JOIN mra.artifact artifact ON artifact.artifact_id=version.fitted_model_artifact_id
                WHERE version.model_version_id=%s""", (model_version_id,)).fetchone()
            datasets = cursor.execute("""SELECT DISTINCT decision.dataset_id FROM mra.model_training_sample sample
                JOIN mra.decision_run decision USING(decision_run_id) WHERE sample.model_training_run_id=%s
                ORDER BY decision.dataset_id""", (version.model_training_run_id,)).fetchall()
            lineage = cursor.execute("SELECT * FROM mra.backtest_model_lineage WHERE model_version_id=%s", (model_version_id,)).fetchall()
            uses = cursor.execute("SELECT experimental_model_use_id FROM mra.experimental_model_use WHERE model_version_id=%s ORDER BY registered_at,experimental_model_use_id", (model_version_id,)).fetchall()
    if fitted is None or (fitted["content_sha256"], fitted["size_bytes"]) != (fitted["frozen_sha256"], fitted["frozen_size"]):
        raise ArtifactIntegrityError("MODEL_FITTED_ARTIFACT_PARENT_MISMATCH")
    content = store.read_bytes(fitted["content_sha256"], expected_size=fitted["size_bytes"])
    if sha256(content).hexdigest() != fitted["frozen_sha256"]:
        raise ArtifactIntegrityError("MODEL_FITTED_ARTIFACT_BYTES_DIFFER")
    registered = PostgresModelTrainingInputProvider(pool, store).load_registered_reproducible(version.model_training_run_id)
    if registered.training.algorithm_code == "research_baseline" and registered.training.algorithm_version == "1.0.0":
        from market_regime_alpha.infrastructure.models.research_baselines import load_baseline_artifact
        decoded: Any = load_baseline_artifact(content)
    elif registered.training.algorithm_code == "deterministic_ridge":
        decoded = load_deterministic_ridge_artifact(content)
    else:
        raise ArtifactIntegrityError("MODEL_LINEAGE_UNSUPPORTED_ARTIFACT_ALGORITHM")
    if registered.training.model_id != version.model_id or tuple(decoded.feature_definition_ids) != tuple(registered.training.feature_definition_ids):
        raise ArtifactIntegrityError("MODEL_FITTED_FEATURE_ROSTER_DIFFERS")
    return {"model": asdict(model), "model_version": asdict(version), "training_run": asdict(training),
            "training_datasets": datasets, "training_reproducibility": asdict(registered.reproducibility),
            "fitted_artifact": fitted, "fitted_format_version": decoded.format_version,
            "backtest_model_lineage": lineage, "experimental_model_uses": uses,
            "physical_training_and_fitted_bytes": "VERIFIED", "business_writes": 0}
