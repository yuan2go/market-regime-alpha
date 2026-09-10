"""Exact frozen daily research lineage; no latest Market substitution or writes."""

from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPredictionPlan
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


class PostgresDailyValidityReads:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool = pool
        self._byte_store = byte_store

    def calendar(self) -> list[dict[str, Any]]:
        """Complete captured calendar; future cohort anchors must not age out."""
        with self._pool.connection(read_only=True) as connection, connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute("""
                SELECT session.* FROM mra.trading_session session
                WHERE exchange='XSHG' AND EXISTS (
                    SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                    JOIN mra.data_capture capture USING(capture_id)
                    WHERE binding.session_id=session.session_id
                      AND capture.status='CAPTURED' AND capture.recorded_at<=statement_timestamp()
                )
                ORDER BY session_date
            """).fetchall()

    def project(self, plan: DailyPredictionPlan, evaluation_id: UUID, decision_id: UUID) -> dict[str, Any]:
        with self._pool.connection(read_only=True) as connection, connection.cursor(row_factory=dict_row) as cursor:
            model = cursor.execute("SELECT * FROM mra.model_version WHERE model_version_id=%s", (plan.model_version_id,)).fetchone()
            use = cursor.execute("SELECT * FROM mra.experimental_model_use WHERE experimental_model_use_id=%s", (plan.experimental_model_use_id,)).fetchone()
            feature = cursor.execute("SELECT * FROM mra.feature_definition WHERE feature_definition_id=%s", (plan.feature_definition_id,)).fetchone()
            target = cursor.execute("SELECT * FROM mra.target_definition WHERE target_definition_id=%s", (plan.target_definition_id,)).fetchone()
            baseline = cursor.execute("SELECT * FROM mra.strategy_version WHERE strategy_version_id=%s", (plan.baseline_strategy_version_id,)).fetchone()
            dataset = cursor.execute("SELECT * FROM mra.dataset WHERE dataset_id=%s", (plan.dataset_id,)).fetchone()
            decision = cursor.execute("SELECT * FROM mra.decision_run WHERE decision_run_id=%s", (decision_id,)).fetchone()
            session = cursor.execute("SELECT * FROM mra.trading_session WHERE session_id=%s", (plan.target_session_id,)).fetchone()
            if any(row is None for row in (model, use, feature, target, baseline, dataset, decision, session)):
                raise ArtifactIntegrityError("research observation frozen identity is absent")
            assert model is not None and dataset is not None and session is not None
            assert use is not None and feature is not None and target is not None
            model_definition = cursor.execute("SELECT * FROM mra.model WHERE model_id=%s", (model["model_id"],)).fetchone()
            model_features = cursor.execute("SELECT * FROM mra.model_feature_definition WHERE model_id=%s ORDER BY ordinal", (model["model_id"],)).fetchall()
            forecast_bindings = cursor.execute("""SELECT * FROM mra.forecast_model_binding
                WHERE decision_run_id=%s AND strategy_version_id=%s ORDER BY commitment_id""",
                (decision_id, plan.strategy_version_id)).fetchall()
            if model_definition is None or (
                model_definition["target_definition_id"] != plan.target_definition_id
                or model_definition["target_definition_sha256"] != target["content_sha256"]
                or model_definition["feature_roster_sha256"] != use["feature_roster_sha256"]
                or not any(row["feature_definition_id"] == plan.feature_definition_id
                    and row["feature_definition_sha256"] == feature["content_sha256"] for row in model_features)
                or not forecast_bindings
                or any(row["model_version_id"] != plan.model_version_id
                    or row["model_version_sha256"] != model["content_sha256"]
                    or row["model_registered_at"] != model["registered_at"]
                    or row["dataset_id"] != plan.dataset_id
                    or row["experimental_model_use_id"] != plan.experimental_model_use_id
                    for row in forecast_bindings)
            ):
                raise ArtifactIntegrityError("research observation frozen Model/Feature/Target binding differs")
            training = cursor.execute("SELECT * FROM mra.model_training_reproducibility WHERE model_training_run_id=%s", (model["model_training_run_id"],)).fetchone()
            checkpoints = cursor.execute("SELECT * FROM mra.target_checkpoint WHERE target_definition_id=%s ORDER BY ordinal", (plan.target_definition_id,)).fetchall()
            commitments = cursor.execute("SELECT * FROM mra.decision_target_commitment WHERE decision_run_id=%s ORDER BY commitment_id", (decision_id,)).fetchall()
            references = cursor.execute("SELECT * FROM mra.decision_reference_observation WHERE decision_run_id=%s ORDER BY commitment_id", (decision_id,)).fetchall()
            sources = cursor.execute("""
                SELECT source.*, coalesce(bar.instrument_id,gap.instrument_id,fact.instrument_id) AS source_instrument_id,
                       coalesce(bar.known_at,gap.known_at,fact.known_at) AS source_known_at,
                       coalesce(bar.recorded_at,gap.recorded_at,fact.recorded_at) AS source_recorded_at,
                       coalesce(bar.session_id,gap.session_id,source.market_trading_session_id) AS session_id,
                       coalesce(bar.event_start,gap.event_start) AS event_start,
                       coalesce(bar.event_end,gap.event_end) AS event_end,
                       capture.capture_id, capture.capture_key, capture.request_hash,
                       capture.capture_started_at AS capture_requested_at,
                       capture.capture_completed_at AS capture_response_at,
                       capture.recorded_at AS capture_recorded_at, capture.known_at AS capture_known_at,
                       capture.status AS capture_status, capture.provider_product_id,
                       capture.source_availability_status, capture.source_available_at,
                       artifact.artifact_id, artifact.content_sha256 AS capture_content_sha256,
                       artifact.size_bytes AS capture_size_bytes,
                       normalization.normalization_receipt_id,
                       normalization.content_sha256 AS normalization_sha256,
                       normalization.recorded_at AS normalized_at
                FROM mra.dataset_source source
                LEFT JOIN mra.market_bar_revision bar ON bar.bar_revision_id=source.market_bar_revision_id
                LEFT JOIN mra.source_gap gap ON gap.gap_id=source.market_source_gap_id
                LEFT JOIN mra.instrument_fact_revision fact ON fact.fact_revision_id=source.market_instrument_fact_revision_id
                LEFT JOIN mra.data_capture capture ON capture.capture_id=coalesce(
                    bar.capture_id,gap.capture_id,fact.capture_id,source.market_capture_id)
                LEFT JOIN mra.artifact artifact ON artifact.artifact_id=capture.artifact_id
                LEFT JOIN mra.market_capture_reference_normalization normalization ON normalization.capture_id=capture.capture_id
                WHERE source.dataset_id=%s ORDER BY source.dataset_source_id
            """, (plan.dataset_id,)).fetchall()
            outcomes = cursor.execute("""
                SELECT source.*, revision.commitment_id, checkpoint.checkpoint_role,
                       checkpoint.value_field, capture.capture_key, capture.request_hash,
                       capture.capture_started_at AS capture_requested_at,
                       capture.capture_completed_at AS capture_response_at,
                       capture.recorded_at AS capture_recorded_at, capture.known_at AS capture_known_at,
                       capture.status AS capture_status, capture.source_availability_status,
                       capture.source_available_at, artifact.artifact_id,
                       artifact.content_sha256 AS capture_content_sha256,
                       artifact.size_bytes AS capture_size_bytes,
                       normalization.normalization_receipt_id,
                       normalization.content_sha256 AS normalization_sha256,
                       normalization.recorded_at AS normalized_at
                FROM mra.evaluation_observation acquired
                JOIN mra.market_target_outcome_revision revision USING(market_target_outcome_revision_id)
                JOIN mra.market_target_outcome_source source USING(market_target_outcome_revision_id)
                LEFT JOIN mra.target_checkpoint checkpoint USING(target_checkpoint_id)
                LEFT JOIN mra.data_capture capture ON capture.capture_id=source.capture_id
                LEFT JOIN mra.artifact artifact ON artifact.artifact_id=capture.artifact_id
                LEFT JOIN mra.market_capture_reference_normalization normalization ON normalization.capture_id=capture.capture_id
                WHERE acquired.evaluation_run_id=%s
                ORDER BY revision.commitment_id, source.source_ordinal
            """, (evaluation_id,)).fetchall()
            checkpoint_observations = cursor.execute("""
                SELECT observation.*, revision.commitment_id
                FROM mra.evaluation_observation acquired
                JOIN mra.market_target_outcome_revision revision USING(market_target_outcome_revision_id)
                JOIN mra.market_target_outcome_observation observation USING(market_target_outcome_revision_id)
                WHERE acquired.evaluation_run_id=%s ORDER BY revision.commitment_id,observation.observation_ordinal
            """, (evaluation_id,)).fetchall()
        manifest_bytes = self._byte_store.read_bytes(dataset["manifest_content_sha256"], expected_size=dataset["manifest_size_bytes"])
        if sha256(manifest_bytes).hexdigest() != dataset["manifest_content_sha256"]:
            raise ArtifactIntegrityError("research observation Dataset manifest bytes differ")
        manifest = json.loads(manifest_bytes)
        artifacts = {
            (row["capture_content_sha256"], row["capture_size_bytes"])
            for row in (*sources, *outcomes) if row["capture_content_sha256"] is not None
        }
        for content_hash, size in artifacts:
            content = self._byte_store.read_bytes(content_hash, expected_size=size)
            if sha256(content).hexdigest() != content_hash:
                raise ArtifactIntegrityError("research observation source Capture bytes differ")
        # Dataset creation follows computation. Input knowledge is the frozen
        # source clock, never the later Dataset registration clock.
        source_times = [row[key] for row in sources for key in (
            "source_known_at", "source_recorded_at", "capture_recorded_at", "capture_known_at",
        ) if row[key] is not None]
        market_sources = [row for row in sources if row["source_role"].startswith("MARKET_")]
        clocks_complete = bool(market_sources) and all(
            row["capture_known_at"] is not None and (
                row["source_role"] == "MARKET_CAPTURE" or row["source_known_at"] is not None
            ) for row in market_sources
        )
        feature_known_at = max(source_times, default=None) if clocks_complete else None
        for checkpoint in checkpoints:
            checkpoint["local_time"] = checkpoint["local_time"].isoformat()
        return {
            "frozen_identities": {"model": model, "experimental_model_use": use,
                "feature": feature, "target": target, "baseline": baseline,
                "dataset": dataset, "decision": decision, "model_training": training,
                "model_definition": model_definition, "model_feature_bindings": model_features},
            "frozen_forecast_bindings": forecast_bindings,
            "dataset_manifest": manifest,
            "dataset_manifest_content": manifest_bytes.decode("utf-8"),
            "feature_sources": sources, "commitments": commitments,
            "reference_observations": references, "target_checkpoints": checkpoints,
            "outcome_source_observations": outcomes,
            "outcome_checkpoint_observations": checkpoint_observations,
            "temporal_facts": {
                "model_recorded_at": model["registered_at"],
                "model_training_knowledge_cutoff": None if training is None else training["training_knowledge_cutoff"],
                "feature_known_at": feature_known_at,
                "feature_known_at_reason": "EXACT_FROZEN_DATASET_SOURCE_CLOCKS" if clocks_complete else "FROZEN_SOURCE_KNOWLEDGE_UNAVAILABLE",
                "dataset_frozen_at": dataset["created_at"],
                "decision_time": plan.decision_time, "input_cutoff": plan.input_cutoff,
                "target_start": session["open_at"], "target_end": session["close_at"],
                "outcome_observations": [row for row in outcomes if row["source_role"] == "OUTCOME_OBSERVATION"],
            },
        }
