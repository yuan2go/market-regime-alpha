"""PostgreSQL adapter for exact ModelVersion-to-Forecast bindings."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import ForecastModelBindingPlan
from market_regime_alpha.decision_support.errors import (
    InferenceAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    ModelForecastReconciliation,
    PreparedModelForecastInputs,
)
from market_regime_alpha.infrastructure.postgres.queries.model_forecast_inputs import (
    _load_root,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresModelForecastRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedModelForecastInputs) -> None:
        row = _load_root(
            self._connection,
            prepared.inference.signal_inputs.decision_run_id,
            prepared.model_version_id,
            lock=True,
        )
        observed = (
            UUID(str(row[0])),
            UUID(str(row[1])),
            UUID(str(row[2])),
            UUID(str(row[3])),
            UUID(str(row[4])),
            int(row[5]),
            UUID(str(row[7])),
            UUID(str(row[8])),
            UUID(str(row[9])),
            int(row[10]),
            str(row[11]),
            UUID(str(row[14])),
            str(row[15]),
            int(row[16]),
            row[17],
            UUID(str(row[18])),
        )
        expected = (
            prepared.dataset_id,
            prepared.exploratory_backtest_run_id,
            prepared.exploratory_backtest_arm_id,
            prepared.exploratory_backtest_fold_id,
            prepared.exploratory_backtest_fold_session_id,
            prepared.inference_fold_ordinal,
            prepared.model_id,
            prepared.model_training_run_id,
            prepared.training_fold_id,
            prepared.training_fold_ordinal,
            prepared.model_version_sha256,
            prepared.fitted_model_artifact.artifact_id,
            str(prepared.fitted_model_artifact.content_sha256),
            prepared.fitted_model_artifact.size_bytes,
            prepared.model_registered_at,
            prepared.target_metric_definition_id,
        )
        if observed != expected:
            raise InferenceAuthorityIntegrityError(
                "Model Forecast parent graph changed before commit"
            )

    def insert(self, bindings: tuple[ForecastModelBindingPlan, ...]) -> None:
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.forecast_model_binding (
                forecast_model_binding_id, forecast_id, forecast_group_id,
                forecast_estimate_id, decision_run_id, strategy_version_id,
                commitment_id, status, calibration_status, reason_code,
                target_metric_definition_id,
                forecast_estimate_content_sha256, dataset_id,
                exploratory_backtest_run_id, exploratory_backtest_arm_id,
                exploratory_backtest_fold_id,
                exploratory_backtest_fold_session_id,
                inference_fold_ordinal, model_version_id, model_id,
                model_training_run_id, training_fold_id,
                training_fold_ordinal, model_version_sha256,
                fitted_model_artifact_id, fitted_model_content_sha256,
                fitted_model_size_bytes, feature_vector_sha256,
                point_estimate, model_registered_at, forecast_recorded_at,
                inference_input_sha256, inference_output_sha256,
                content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                (
                    item.forecast_model_binding_id,
                    item.forecast_id,
                    item.forecast_group_id,
                    item.forecast_estimate_id,
                    item.decision_run_id,
                    item.strategy_version_id,
                    item.commitment_id,
                    item.prediction_state.value,
                    (
                        "UNCALIBRATED"
                        if item.point_estimate is not None
                        else "NOT_APPLICABLE"
                    ),
                    item.reason_code,
                    item.target_metric_definition_id,
                    item.forecast_estimate_content_sha256,
                    item.dataset_id,
                    item.exploratory_backtest_run_id,
                    item.exploratory_backtest_arm_id,
                    item.exploratory_backtest_fold_id,
                    item.exploratory_backtest_fold_session_id,
                    item.inference_fold_ordinal,
                    item.model_version_id,
                    item.model_id,
                    item.model_training_run_id,
                    item.training_fold_id,
                    item.training_fold_ordinal,
                    item.model_version_sha256,
                    item.fitted_model_artifact_id,
                    item.fitted_model_content_sha256,
                    item.fitted_model_size_bytes,
                    item.feature_vector_sha256,
                    item.point_estimate,
                    item.model_registered_at,
                    item.forecast_recorded_at,
                    item.inference_input_sha256,
                    item.inference_output_sha256,
                    item.content_sha256,
                )
                for item in bindings
            ),
        )

    def reconcile(
        self,
        forecast_group_id: UUID,
        model_version_id: UUID,
        *,
        lock: bool,
    ) -> ModelForecastReconciliation:
        suffix = " FOR SHARE OF forecast, binding" if lock else ""
        rows = self._connection.execute(
            """
            SELECT forecast.forecast_count, forecast.forecast_id,
                   binding.forecast_model_binding_id,
                   binding.model_version_id, forecast.ordinal,
                   binding.content_sha256
            FROM mra.forecast AS forecast
            LEFT JOIN mra.forecast_model_binding AS binding
              ON binding.forecast_id = forecast.forecast_id
             AND binding.forecast_group_id = forecast.forecast_group_id
            WHERE forecast.forecast_group_id = %s
            ORDER BY forecast.ordinal
            """
            + suffix,
            (forecast_group_id,),
        ).fetchall()
        if not rows:
            raise InferenceAuthorityIntegrityError("Model Forecast roster is absent")
        forecast_count = int(rows[0][0])
        binding_count = sum(row[2] is not None for row in rows)
        roster_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(row[5]),
                    "forecast_model_binding_id": UUID(str(row[2])),
                    "ordinal": int(row[4]),
                }
                for row in rows
                if row[2] is not None
            )
        )
        matched = (
            len(rows) == forecast_count
            and binding_count == forecast_count
            and all(
                row[2] is not None and UUID(str(row[3])) == model_version_id
                for row in rows
            )
        )
        return ModelForecastReconciliation(
            forecast_group_id=forecast_group_id,
            model_version_id=model_version_id,
            forecast_count=forecast_count,
            binding_count=binding_count,
            binding_roster_sha256=roster_hash,
            matched=matched,
        )


__all__ = ["PostgresModelForecastRepository"]
