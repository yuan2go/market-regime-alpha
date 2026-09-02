"""Exact immutable Forecast inputs for Opportunity Authority."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    ForecastCalibrationStatus,
    ForecastStatus,
    PreparedOpportunityContext,
    PreparedOpportunityInput,
    PreparedOpportunityInputs,
    SignalStatus,
)
from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import OpportunitySetRecord, ThesisRecord
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.decision_opportunities import (
    _set_record,
    _set_row,
    _thesis_record,
    _thesis_row,
)


class PostgresOpportunityInputPreparationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(self, decision_run_id: UUID, strategy_version_id: UUID) -> PreparedOpportunityInputs:
        with self._pool.connection(read_only=True) as connection:
            return _load_inputs(connection, decision_run_id, strategy_version_id, lock=False)


class PostgresOpportunityQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def find_set_request(self, decision_run_id: UUID, strategy_version_id: UUID, request_identity: str) -> OpportunitySetRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _set_row(
                connection,
                "root.decision_run_id = %s AND root.strategy_version_id = %s AND root.request_identity = %s",
                (decision_run_id, strategy_version_id, request_identity),
                lock=False,
            )
        return None if row is None else _set_record(row)

    def find_thesis_request(self, opportunity_id: UUID, request_identity: str) -> ThesisRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _thesis_row(
                connection, "root.opportunity_id = %s AND root.request_identity = %s", (opportunity_id, request_identity), lock=False
            )
        return None if row is None else _thesis_record(row)


class PostgresOpportunityDependencyRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedOpportunityInputs) -> None:
        actual = _load_inputs(self._connection, prepared.decision_run_id, prepared.strategy_version_id, lock=True)
        if actual != prepared:
            raise DecisionAuthorityIntegrityError("prepared Opportunity inputs changed before closure")

    def require_opportunity(self, opportunity_id: UUID, content_sha256: str, *, lock: bool) -> tuple[UUID, UUID, UUID]:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            "SELECT opportunity_set_id, decision_run_id, strategy_version_id, content_sha256 FROM mra.opportunity WHERE opportunity_id = %s"
            + suffix,
            (opportunity_id,),
        ).fetchone()
        if row is None or str(row[3]) != content_sha256:
            raise DecisionAuthorityIntegrityError("exact Opportunity is absent")
        return UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2]))


def _load_inputs(
    connection: psycopg.Connection[Any], decision_run_id: UUID, strategy_version_id: UUID, *, lock: bool
) -> PreparedOpportunityInputs:
    suffix = " FOR SHARE OF forecast_run, signal_run, strategy" if lock else ""
    root = connection.execute(
        """
        SELECT forecast_run.forecast_group_id, forecast_run.content_sha256,
               forecast_run.recorded_at, forecast_run.forecast_count,
               forecast_run.signal_group_id, signal_run.content_sha256,
               strategy.content_sha256
        FROM mra.forecast_run AS forecast_run
        JOIN mra.signal_run AS signal_run
          ON signal_run.signal_group_id = forecast_run.signal_group_id
         AND signal_run.decision_run_id = forecast_run.decision_run_id
         AND signal_run.strategy_version_id = forecast_run.strategy_version_id
        JOIN mra.strategy_version AS strategy
          ON strategy.strategy_version_id = forecast_run.strategy_version_id
        WHERE forecast_run.decision_run_id = %s
          AND forecast_run.strategy_version_id = %s
        """
        + suffix,
        (decision_run_id, strategy_version_id),
    ).fetchone()
    if root is None:
        raise DecisionAuthorityIntegrityError("exact ForecastRun is absent")
    child_suffix = " FOR SHARE OF forecast, signal, commitment, definition" if lock else ""
    rows = connection.execute(
        """
        SELECT forecast.forecast_id, forecast.ordinal, forecast.content_sha256,
               forecast.status, forecast.calibration_status,
               signal.signal_id, signal.content_sha256, signal.status,
               forecast.candidate_id, forecast.instrument_id,
               forecast.commitment_id, commitment.content_sha256,
               forecast.target_definition_id, definition.content_sha256
        FROM mra.forecast AS forecast
        JOIN mra.signal AS signal
          ON signal.signal_id = forecast.signal_id
         AND signal.signal_group_id = forecast.signal_group_id
         AND signal.decision_run_id = forecast.decision_run_id
         AND signal.candidate_id = forecast.candidate_id
         AND signal.strategy_version_id = forecast.strategy_version_id
        JOIN mra.decision_target_commitment AS commitment
          ON commitment.commitment_id = forecast.commitment_id
         AND commitment.decision_run_id = forecast.decision_run_id
         AND commitment.candidate_id = forecast.candidate_id
         AND commitment.instrument_id = forecast.instrument_id
         AND commitment.target_definition_id = forecast.target_definition_id
        JOIN mra.target_definition AS definition
          ON definition.target_definition_id = forecast.target_definition_id
        WHERE forecast.forecast_group_id = %s
        ORDER BY forecast.ordinal
        """
        + child_suffix,
        (root[0],),
    ).fetchall()
    if len(rows) != int(root[3]) or tuple(int(row[1]) for row in rows) != tuple(range(1, len(rows) + 1)):
        raise DecisionAuthorityIntegrityError("Forecast roster is incomplete")
    items: list[PreparedOpportunityInput] = []
    for row in rows:
        context_suffix = " FOR SHARE" if lock else ""
        context_rows = connection.execute(
            """
            SELECT signal_context_binding_id,
                   strategy_context_requirement_id, context_assessment_id,
                   context_kind, content_sha256, binding_ordinal
            FROM mra.signal_context_binding
            WHERE signal_id = %s ORDER BY binding_ordinal
            """
            + context_suffix,
            (row[5],),
        ).fetchall()
        if not context_rows or tuple(int(item[5]) for item in context_rows) != tuple(range(1, len(context_rows) + 1)):
            raise DecisionAuthorityIntegrityError("Signal Context roster is incomplete")
        items.append(
            PreparedOpportunityInput(
                forecast_id=UUID(str(row[0])),
                forecast_ordinal=int(row[1]),
                forecast_content_sha256=str(row[2]),
                forecast_status=ForecastStatus(str(row[3])),
                calibration_status=ForecastCalibrationStatus(str(row[4])),
                signal_id=UUID(str(row[5])),
                signal_content_sha256=str(row[6]),
                signal_status=SignalStatus(str(row[7])),
                candidate_id=UUID(str(row[8])),
                instrument_id=UUID(str(row[9])),
                commitment_id=UUID(str(row[10])),
                commitment_content_sha256=str(row[11]),
                target_definition_id=UUID(str(row[12])),
                target_definition_sha256=str(row[13]),
                contexts=tuple(
                    PreparedOpportunityContext(
                        signal_context_binding_id=UUID(str(item[0])),
                        strategy_context_requirement_id=UUID(str(item[1])),
                        context_assessment_id=UUID(str(item[2])),
                        context_kind=str(item[3]),
                        content_sha256=str(item[4]),
                    )
                    for item in context_rows
                ),
            )
        )
    return PreparedOpportunityInputs(
        decision_run_id=decision_run_id,
        strategy_version_id=strategy_version_id,
        strategy_version_sha256=str(root[6]),
        signal_group_id=UUID(str(root[4])),
        signal_content_sha256=str(root[5]),
        forecast_group_id=UUID(str(root[0])),
        forecast_content_sha256=str(root[1]),
        forecast_recorded_at=root[2],
        items=tuple(items),
    )


__all__ = [
    "PostgresOpportunityDependencyRepository",
    "PostgresOpportunityInputPreparationProvider",
    "PostgresOpportunityQueryProvider",
]
