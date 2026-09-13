"""Bounded diagnostics from Model owner inputs and original fitted artifacts."""

from dataclasses import asdict
import json
from uuid import UUID

from market_regime_alpha.infrastructure.models.research_baselines import load_baseline_artifact
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.model_training_inputs import PostgresModelTrainingInputProvider
from market_regime_alpha.research_qualification.application.deterministic_linear import load_deterministic_ridge_artifact
from market_regime_alpha.research_qualification.domain.fit_diagnostics import fit_matrix_diagnostics
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def historical_fit_diagnostics(pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore, run_id: UUID) -> tuple[dict, ...]:
    with pool.connection(read_only=True) as connection:
        rows = connection.execute("""
            SELECT lineage.model_training_run_id,lineage.model_version_id,arm.arm_kind,requirement.fit_fold_id,
                version.fitted_model_artifact_id,version.fitted_model_content_sha256,version.fitted_model_size_bytes,
                version.training_input_content_sha256,version.content_sha256,
                mra.artifact_has_verified_integrity(artifact.integrity_state,artifact.last_verified_at)
            FROM mra.backtest_model_lineage lineage
            JOIN mra.backtest_model_training_requirement requirement ON requirement.backtest_model_training_requirement_id=lineage.model_training_requirement_id
            JOIN mra.exploratory_backtest_arm arm ON arm.exploratory_backtest_arm_id=requirement.exploratory_backtest_arm_id
            JOIN mra.model_version version USING(model_version_id)
            JOIN mra.artifact artifact ON artifact.artifact_id=version.fitted_model_artifact_id
            WHERE lineage.exploratory_backtest_run_id=%s ORDER BY requirement.ordinal LIMIT 241
            """, (run_id,)).fetchall()
    if not rows or len(rows)>240:
        raise ArtifactIntegrityError("FIT diagnostics require the bounded completed Model roster")
    provider = PostgresModelTrainingInputProvider(pool,byte_store)
    result = []
    for training_id,version_id,arm,fold,artifact_id,digest,size,training_sha,version_sha,readable in rows:
        training = provider.load_registered_reproducible(training_id)
        registered = training.training
        if not readable or str(registered.training_input_artifact.content_sha256)!=training_sha:
            raise ArtifactIntegrityError("FIT diagnostics Model/input Artifact binding differs")
        content = byte_store.read_bytes(digest,expected_size=size)
        model = load_deterministic_ridge_artifact(content) if registered.algorithm_code=="deterministic_ridge" else load_baseline_artifact(content)
        if model.feature_definition_ids != registered.feature_definition_ids:
            raise ArtifactIntegrityError("FIT diagnostics fitted feature order differs")
        result.append({"model_training_run_id":training_id,"model_version_id":version_id,"model_version_sha256":version_sha,
            "arm_code":arm,"fit_fold_id":fold,"training_input_artifact":asdict(registered.training_input_artifact),
            "fitted_artifact_id":artifact_id,"fitted_content_sha256":digest,"fitted_model":json.loads(content),
            "training_knowledge_cutoff":training.reproducibility.training_knowledge_cutoff,
            "feature_order":registered.feature_definition_ids,"conditioning":fit_matrix_diagnostics(registered.linear_rows),
            "coefficient_interpretation":"RIDGE_COEFFICIENTS_PER_FOLD_FIT_STD_UNIT; RAW_SLOPE=COEFFICIENT/FROZEN_SCALE; CONSTANT_CONTROLS_HAVE_NO_RANK_SIGNAL"})
    return tuple(result)
