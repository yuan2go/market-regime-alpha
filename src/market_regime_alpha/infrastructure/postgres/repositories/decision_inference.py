"""PostgreSQL persistence for complete Signal and Forecast rosters."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    ForecastAuthority,
    SignalAuthority,
)
from market_regime_alpha.decision_support.errors import InferenceAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import (
    InferenceReconciliation,
    InferenceRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresInferenceRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
    ) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"signal-forecast:{decision_run_id}:{strategy_version_id}",),
        )

    def authoritative_recorded_at(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise InferenceAuthorityIntegrityError(
                "PostgreSQL did not return authoritative time"
            )
        return row[0]

    def insert(
        self,
        signal: SignalAuthority,
        forecast: ForecastAuthority,
    ) -> InferenceRecord:
        if (
            signal.command_receipt_id != forecast.command_receipt_id
            or signal.request_sha256 != forecast.request_sha256
            or signal.recorded_at != forecast.recorded_at
        ):
            raise InferenceAuthorityIntegrityError(
                "Signal and Forecast command identity differs"
            )
        version = signal.strategy_version
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.signal_context_binding (
                signal_context_binding_id, signal_id, signal_group_id,
                decision_run_id, candidate_id, strategy_version_id,
                binding_ordinal, strategy_context_requirement_id,
                context_policy_id, context_policy_content_sha256,
                context_kind, context_assessment_id, assessment_group_id,
                assessment_status, assessment_state,
                assessment_content_sha256, assessment_recorded_at,
                content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    binding.signal_context_binding_id,
                    item.signal_id,
                    signal.signal_group_id,
                    signal.decision_run_id,
                    item.candidate.candidate_id,
                    version.strategy_version_id,
                    ordinal,
                    binding.context.strategy_context_requirement_id,
                    binding.context.context_policy_id,
                    binding.context.context_policy_content_sha256,
                    binding.context.context_kind.value,
                    binding.context.context_assessment_id,
                    binding.context.assessment_group_id,
                    binding.context.assessment_status.value,
                    binding.context.assessment_state.value,
                    binding.context.assessment_content_sha256,
                    binding.context.recorded_at,
                    binding.content_sha256,
                )
                for item in signal.signals
                for ordinal, binding in enumerate(item.context_bindings, start=1)
            ),
        )
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.signal (
                signal_id, signal_group_id, ordinal, signal_count,
                signal_roster_sha256, group_content_sha256,
                decision_run_id, candidate_set_id,
                candidate_set_content_sha256, candidate_roster_sha256,
                decision_time, candidate_count, candidate_id, instrument_id,
                candidate_disposition, candidate_score,
                strategy_version_id, strategy_version_sha256,
                strategy_signal_rule_id, strategy_signal_rule_sha256,
                status, reason_code, context_binding_count,
                context_binding_roster_sha256,
                total_context_binding_count, request_identity,
                request_sha256, command_receipt_id, content_sha256, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    item.signal_id,
                    signal.signal_group_id,
                    item.ordinal,
                    signal.signal_count,
                    signal.signal_roster_sha256,
                    signal.content_sha256,
                    signal.decision_run_id,
                    signal.candidate_set_id,
                    signal.candidate_set_content_sha256,
                    signal.candidate_roster_sha256,
                    signal.decision_time,
                    signal.signal_count,
                    item.candidate.candidate_id,
                    item.candidate.instrument_id,
                    item.candidate.disposition.value,
                    item.candidate.composite_score,
                    version.strategy_version_id,
                    version.content_sha256,
                    version.signal_rule.strategy_signal_rule_id,
                    version.signal_rule.content_sha256,
                    item.status.value,
                    item.reason_code,
                    len(item.context_bindings),
                    item.context_binding_roster_sha256,
                    signal.context_binding_count,
                    signal.request_identity,
                    signal.request_sha256,
                    signal.command_receipt_id,
                    item.content_sha256,
                    signal.recorded_at,
                )
                for item in signal.signals
            ),
        )
        self._connection.execute(
            """
            INSERT INTO mra.signal_run (
                signal_group_id, decision_run_id, candidate_set_id,
                candidate_set_content_sha256, candidate_roster_sha256,
                decision_time, candidate_count, strategy_version_id,
                strategy_version_sha256, signal_count,
                context_binding_count, signal_roster_sha256,
                request_identity, request_sha256, command_receipt_id,
                content_sha256, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                signal.signal_group_id,
                signal.decision_run_id,
                signal.candidate_set_id,
                signal.candidate_set_content_sha256,
                signal.candidate_roster_sha256,
                signal.decision_time,
                signal.signal_count,
                version.strategy_version_id,
                version.content_sha256,
                signal.signal_count,
                signal.context_binding_count,
                signal.signal_roster_sha256,
                signal.request_identity,
                signal.request_sha256,
                signal.command_receipt_id,
                signal.content_sha256,
                signal.recorded_at,
            ),
        )
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.forecast_estimate (
                forecast_estimate_id, forecast_id, forecast_group_id,
                decision_run_id, strategy_version_id, estimate_ordinal,
                strategy_forecast_rule_id, target_definition_id,
                target_metric_definition_id, value_unit, point_estimate,
                lower_bound, upper_bound, content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    estimate.forecast_estimate_id,
                    item.forecast_id,
                    forecast.forecast_group_id,
                    forecast.decision_run_id,
                    version.strategy_version_id,
                    ordinal,
                    estimate.rule.strategy_forecast_rule_id,
                    estimate.rule.target_definition_id,
                    estimate.rule.target_metric_definition_id,
                    estimate.rule.value_unit,
                    estimate.point_estimate,
                    estimate.lower_bound,
                    estimate.upper_bound,
                    estimate.content_sha256,
                )
                for item in forecast.forecasts
                for ordinal, estimate in enumerate(item.estimates, start=1)
            ),
        )
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.forecast (
                forecast_id, forecast_group_id, ordinal, forecast_count,
                forecast_roster_sha256, group_content_sha256,
                decision_run_id, strategy_version_id,
                strategy_version_sha256, signal_group_id, signal_id,
                signal_content_sha256, commitment_id, candidate_id,
                instrument_id, target_definition_id,
                target_definition_sha256, target_checkpoint_id,
                target_checkpoint_sha256, commitment_content_sha256,
                status, calibration_status, reason_code, estimate_count,
                estimate_roster_sha256, total_estimate_count,
                request_identity, request_sha256, command_receipt_id,
                content_sha256, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    item.forecast_id,
                    forecast.forecast_group_id,
                    item.ordinal,
                    forecast.forecast_count,
                    forecast.forecast_roster_sha256,
                    forecast.content_sha256,
                    forecast.decision_run_id,
                    version.strategy_version_id,
                    version.content_sha256,
                    signal.signal_group_id,
                    item.signal.signal_id,
                    item.signal.content_sha256,
                    item.commitment.commitment_id,
                    item.commitment.candidate_id,
                    item.commitment.instrument_id,
                    item.commitment.target_definition_id,
                    item.commitment.target_definition_sha256,
                    item.commitment.target_checkpoint_id,
                    item.commitment.target_checkpoint_sha256,
                    item.commitment.commitment_content_sha256,
                    item.status.value,
                    item.calibration_status.value,
                    item.reason_code,
                    len(item.estimates),
                    item.estimate_roster_sha256,
                    forecast.estimate_count,
                    forecast.request_identity,
                    forecast.request_sha256,
                    forecast.command_receipt_id,
                    item.content_sha256,
                    forecast.recorded_at,
                )
                for item in forecast.forecasts
            ),
        )
        self._connection.execute(
            """
            INSERT INTO mra.forecast_run (
                forecast_group_id, decision_run_id, strategy_version_id,
                strategy_version_sha256, signal_group_id,
                signal_content_sha256, forecast_count, estimate_count,
                forecast_roster_sha256, request_identity, request_sha256,
                command_receipt_id, content_sha256, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                forecast.forecast_group_id,
                forecast.decision_run_id,
                version.strategy_version_id,
                version.content_sha256,
                signal.signal_group_id,
                signal.content_sha256,
                forecast.forecast_count,
                forecast.estimate_count,
                forecast.forecast_roster_sha256,
                forecast.request_identity,
                forecast.request_sha256,
                forecast.command_receipt_id,
                forecast.content_sha256,
                forecast.recorded_at,
            ),
        )
        return InferenceRecord(
            decision_run_id=signal.decision_run_id,
            strategy_version_id=version.strategy_version_id,
            signal_group_id=signal.signal_group_id,
            forecast_group_id=forecast.forecast_group_id,
            signal_count=signal.signal_count,
            forecast_count=forecast.forecast_count,
            context_binding_count=signal.context_binding_count,
            estimate_count=forecast.estimate_count,
            signal_content_sha256=signal.content_sha256,
            forecast_content_sha256=forecast.content_sha256,
            request_identity=signal.request_identity,
            request_sha256=signal.request_sha256,
            recorded_at=signal.recorded_at,
            receipt_id=signal.command_receipt_id,
        )

    def record(
        self,
        signal_group_id: UUID,
        forecast_group_id: UUID,
        *,
        lock: bool,
    ) -> InferenceRecord:
        rows = _inference_record_rows(
            self._connection,
            "signal_run.signal_group_id = %s AND forecast_run.forecast_group_id = %s",
            (signal_group_id, forecast_group_id),
            lock=lock,
        )
        if rows is None:
            raise InferenceAuthorityIntegrityError("Inference Authority is absent")
        return _inference_record(rows)

    def forecast_group_for_signal(
        self,
        signal_group_id: UUID,
        *,
        lock: bool,
    ) -> UUID:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            "SELECT forecast_group_id FROM mra.forecast_run WHERE signal_group_id = %s"
            + suffix,
            (signal_group_id,),
        ).fetchone()
        if row is None:
            raise InferenceAuthorityIntegrityError("Forecast root is absent")
        return UUID(str(row[0]))

    def reconcile(
        self,
        signal_group_id: UUID,
        forecast_group_id: UUID,
        *,
        lock: bool,
    ) -> InferenceReconciliation:
        suffix = " FOR SHARE OF signal_run, forecast_run" if lock else ""
        root = self._connection.execute(
            """
            SELECT signal_run.signal_count, signal_run.context_binding_count,
                   signal_run.signal_roster_sha256,
                   forecast_run.forecast_count, forecast_run.estimate_count,
                   forecast_run.forecast_roster_sha256
            FROM mra.signal_run AS signal_run
            JOIN mra.forecast_run AS forecast_run
              ON forecast_run.signal_group_id = signal_run.signal_group_id
            WHERE signal_run.signal_group_id = %s
              AND forecast_run.forecast_group_id = %s
            """
            + suffix,
            (signal_group_id, forecast_group_id),
        ).fetchone()
        if root is None:
            return InferenceReconciliation(
                signal_group_id=signal_group_id,
                forecast_group_id=forecast_group_id,
                signal_count=0,
                context_binding_count=0,
                forecast_count=0,
                estimate_count=0,
                matched=False,
            )
        signal_rows = self._connection.execute(
            "SELECT signal_id, ordinal, content_sha256 FROM mra.signal "
            "WHERE signal_group_id = %s ORDER BY ordinal",
            (signal_group_id,),
        ).fetchall()
        forecast_rows = self._connection.execute(
            "SELECT forecast_id, ordinal, content_sha256 FROM mra.forecast "
            "WHERE forecast_group_id = %s ORDER BY ordinal",
            (forecast_group_id,),
        ).fetchall()
        binding_count_row = self._connection.execute(
            "SELECT count(*) FROM mra.signal_context_binding WHERE signal_group_id = %s",
            (signal_group_id,),
        ).fetchone()
        estimate_count_row = self._connection.execute(
            "SELECT count(*) FROM mra.forecast_estimate WHERE forecast_group_id = %s",
            (forecast_group_id,),
        ).fetchone()
        signal_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(row[2]),
                    "ordinal": int(row[1]),
                    "signal_id": UUID(str(row[0])),
                }
                for row in signal_rows
            )
        )
        forecast_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(row[2]),
                    "forecast_id": UUID(str(row[0])),
                    "ordinal": int(row[1]),
                }
                for row in forecast_rows
            )
        )
        binding_count = int(binding_count_row[0]) if binding_count_row else 0
        estimate_count = int(estimate_count_row[0]) if estimate_count_row else 0
        matched = (
            len(signal_rows) == int(root[0])
            and tuple(int(row[1]) for row in signal_rows)
            == tuple(range(1, len(signal_rows) + 1))
            and binding_count == int(root[1])
            and signal_hash == str(root[2])
            and len(forecast_rows) == int(root[3])
            and tuple(int(row[1]) for row in forecast_rows)
            == tuple(range(1, len(forecast_rows) + 1))
            and estimate_count == int(root[4])
            and forecast_hash == str(root[5])
        )
        return InferenceReconciliation(
            signal_group_id=signal_group_id,
            forecast_group_id=forecast_group_id,
            signal_count=len(signal_rows),
            context_binding_count=binding_count,
            forecast_count=len(forecast_rows),
            estimate_count=estimate_count,
            matched=matched,
        )


def _inference_record_rows(
    connection: psycopg.Connection[Any],
    predicate: str,
    parameters: tuple[object, ...],
    *,
    lock: bool,
):
    suffix = " FOR SHARE OF signal_run, forecast_run, receipt" if lock else ""
    return connection.execute(
        """
        SELECT signal_run.decision_run_id, signal_run.strategy_version_id,
               signal_run.signal_group_id, forecast_run.forecast_group_id,
               signal_run.signal_count, forecast_run.forecast_count,
               signal_run.context_binding_count, forecast_run.estimate_count,
               signal_run.content_sha256, forecast_run.content_sha256,
               signal_run.request_identity, signal_run.request_sha256,
               signal_run.recorded_at, receipt.receipt_id,
               forecast_run.request_identity, forecast_run.request_sha256,
               forecast_run.command_receipt_id
        FROM mra.signal_run AS signal_run
        JOIN mra.forecast_run AS forecast_run
          ON forecast_run.signal_group_id = signal_run.signal_group_id
         AND forecast_run.decision_run_id = signal_run.decision_run_id
         AND forecast_run.strategy_version_id = signal_run.strategy_version_id
        JOIN mra.command_receipt AS receipt
          ON receipt.receipt_id = signal_run.command_receipt_id
         AND receipt.receipt_id = forecast_run.command_receipt_id
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _inference_record(row) -> InferenceRecord:
    if (
        str(row[10]) != str(row[14])
        or str(row[11]) != str(row[15])
        or UUID(str(row[13])) != UUID(str(row[16]))
    ):
        raise InferenceAuthorityIntegrityError("Inference roots do not reconcile")
    return InferenceRecord(
        decision_run_id=UUID(str(row[0])),
        strategy_version_id=UUID(str(row[1])),
        signal_group_id=UUID(str(row[2])),
        forecast_group_id=UUID(str(row[3])),
        signal_count=int(row[4]),
        forecast_count=int(row[5]),
        context_binding_count=int(row[6]),
        estimate_count=int(row[7]),
        signal_content_sha256=str(row[8]),
        forecast_content_sha256=str(row[9]),
        request_identity=str(row[10]),
        request_sha256=str(row[11]),
        recorded_at=row[12],
        receipt_id=UUID(str(row[13])),
    )


__all__ = [
    "PostgresInferenceRepository",
    "_inference_record",
    "_inference_record_rows",
]
