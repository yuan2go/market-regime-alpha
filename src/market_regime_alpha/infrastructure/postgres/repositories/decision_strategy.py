"""PostgreSQL persistence for immutable Strategy definitions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import StrategyVersionPlan
from market_regime_alpha.decision_support.errors import StrategyAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import (
    StrategyReconciliation,
    StrategyVersionRecord,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresStrategyRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(self, strategy_id: UUID) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"strategy-version:{strategy_id}",),
        )

    def register(
        self,
        plan: StrategyVersionPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> StrategyVersionRecord:
        self._connection.execute(
            """
            INSERT INTO mra.strategy (
                strategy_id, strategy_code, objective, content_sha256
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (strategy_id) DO NOTHING
            """,
            (
                plan.strategy.strategy_id,
                plan.strategy.strategy_code,
                plan.strategy.objective,
                plan.strategy.content_sha256,
            ),
        )
        root = self._connection.execute(
            """
            SELECT content_sha256 FROM mra.strategy
            WHERE strategy_id = %s FOR SHARE
            """,
            (plan.strategy.strategy_id,),
        ).fetchone()
        if root is None or str(root[0]) != plan.strategy.content_sha256:
            raise StrategyAuthorityIntegrityError(
                "Strategy identity already binds different content"
            )
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.strategy_context_requirement (
                strategy_context_requirement_id, strategy_version_id,
                ordinal, context_policy_id, context_policy_content_sha256,
                context_kind, required_state, missing_action, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                (
                    item.strategy_context_requirement_id,
                    item.strategy_version_id,
                    item.ordinal,
                    item.context_policy_id,
                    item.context_policy_content_sha256,
                    item.context_kind.value,
                    item.required_state.value,
                    item.missing_action.value,
                    item.content_sha256,
                )
                for item in plan.context_requirements
            ),
        )
        rule = plan.signal_rule
        self._connection.execute(
            """
            INSERT INTO mra.strategy_signal_rule (
                strategy_signal_rule_id, strategy_version_id,
                eligible_disposition, positive_status, negative_status,
                ineligible_status, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                rule.strategy_signal_rule_id,
                rule.strategy_version_id,
                rule.eligible_disposition.value,
                rule.positive_status.value,
                rule.negative_status.value,
                rule.ineligible_status.value,
                rule.content_sha256,
            ),
        )
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.strategy_forecast_rule (
                strategy_forecast_rule_id, strategy_version_id, ordinal,
                target_definition_id, target_definition_sha256,
                target_checkpoint_id, target_checkpoint_sha256,
                target_metric_definition_id,
                target_metric_definition_sha256, source_measure,
                coefficient, intercept, lower_offset, upper_offset,
                value_unit, content_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    item.strategy_forecast_rule_id,
                    item.strategy_version_id,
                    item.ordinal,
                    item.target_definition_id,
                    item.target_definition_sha256,
                    item.target_checkpoint_id,
                    item.target_checkpoint_sha256,
                    item.target_metric_definition_id,
                    item.target_metric_definition_sha256,
                    item.source_measure.value,
                    item.coefficient,
                    item.intercept,
                    item.lower_offset,
                    item.upper_offset,
                    item.value_unit,
                    item.content_sha256,
                )
                for item in plan.forecast_rules
            ),
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.strategy_version (
                strategy_version_id, strategy_id, strategy_content_sha256,
                version, supersedes_strategy_version_id, primary_change,
                action_policy, context_requirement_count,
                context_requirement_roster_sha256,
                strategy_signal_rule_id, signal_rule_sha256,
                forecast_rule_count, forecast_rule_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING frozen_at
            """,
            (
                plan.strategy_version_id,
                plan.strategy.strategy_id,
                plan.strategy.content_sha256,
                plan.version,
                plan.supersedes_strategy_version_id,
                plan.primary_change,
                plan.action_policy.value,
                plan.context_requirement_count,
                plan.context_requirement_roster_sha256,
                plan.signal_rule.strategy_signal_rule_id,
                plan.signal_rule.content_sha256,
                plan.forecast_rule_count,
                plan.forecast_rule_roster_sha256,
                plan.code_artifact.artifact_id,
                plan.code_artifact.content_sha256,
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                plan.config_artifact.content_sha256,
                plan.config_artifact.size_bytes,
                plan.provenance_sha256,
                plan.content_sha256,
                request_identity,
                request_sha256,
            ),
        ).fetchone()
        if row is None:
            raise StrategyAuthorityIntegrityError(
                "PostgreSQL did not return Strategy frozen time"
            )
        return StrategyVersionRecord(
            strategy_id=plan.strategy.strategy_id,
            strategy_version_id=plan.strategy_version_id,
            version=plan.version,
            context_requirement_count=plan.context_requirement_count,
            forecast_rule_count=plan.forecast_rule_count,
            content_sha256=plan.content_sha256,
            request_identity=request_identity,
            request_sha256=request_sha256,
            frozen_at=row[0],
            receipt_id=_receipt_id(
                self._connection,
                plan.strategy.strategy_id,
                request_identity,
                request_sha256,
            ),
        )

    def record(
        self,
        strategy_version_id: UUID,
        *,
        lock: bool,
    ) -> StrategyVersionRecord:
        row = _record_row(
            self._connection,
            "version.strategy_version_id = %s",
            (strategy_version_id,),
            lock=lock,
        )
        if row is None:
            raise StrategyAuthorityIntegrityError("StrategyVersion is absent")
        return _record(row)

    def reconcile(
        self,
        strategy_version_id: UUID,
        *,
        lock: bool,
    ) -> StrategyReconciliation:
        suffix = " FOR SHARE" if lock else ""
        root = self._connection.execute(
            """
            SELECT context_requirement_count,
                   context_requirement_roster_sha256,
                   forecast_rule_count, forecast_rule_roster_sha256
            FROM mra.strategy_version WHERE strategy_version_id = %s
            """
            + suffix,
            (strategy_version_id,),
        ).fetchone()
        if root is None:
            raise StrategyAuthorityIntegrityError("StrategyVersion is absent")
        context_rows = self._connection.execute(
            """
            SELECT strategy_context_requirement_id, ordinal, content_sha256
            FROM mra.strategy_context_requirement
            WHERE strategy_version_id = %s ORDER BY ordinal
            """,
            (strategy_version_id,),
        ).fetchall()
        signal_count = self._connection.execute(
            "SELECT count(*) FROM mra.strategy_signal_rule WHERE strategy_version_id = %s",
            (strategy_version_id,),
        ).fetchone()
        forecast_rows = self._connection.execute(
            """
            SELECT strategy_forecast_rule_id, ordinal, content_sha256
            FROM mra.strategy_forecast_rule
            WHERE strategy_version_id = %s ORDER BY ordinal
            """,
            (strategy_version_id,),
        ).fetchall()
        context_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(row[2]),
                    "ordinal": int(row[1]),
                    "strategy_context_requirement_id": UUID(str(row[0])),
                }
                for row in context_rows
            )
        )
        forecast_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": str(row[2]),
                    "ordinal": int(row[1]),
                    "strategy_forecast_rule_id": UUID(str(row[0])),
                }
                for row in forecast_rows
            )
        )
        signal_value = int(signal_count[0]) if signal_count is not None else 0
        matched = (
            len(context_rows) == int(root[0])
            and tuple(int(row[1]) for row in context_rows)
            == tuple(range(1, len(context_rows) + 1))
            and context_hash == str(root[1])
            and len(forecast_rows) == int(root[2])
            and tuple(int(row[1]) for row in forecast_rows)
            == tuple(range(1, len(forecast_rows) + 1))
            and forecast_hash == str(root[3])
            and signal_value == 1
        )
        return StrategyReconciliation(
            strategy_version_id=strategy_version_id,
            context_requirement_count=len(context_rows),
            signal_rule_count=signal_value,
            forecast_rule_count=len(forecast_rows),
            context_requirement_roster_sha256=context_hash,
            forecast_rule_roster_sha256=forecast_hash,
            matched=matched,
        )


def _receipt_id(
    connection: psycopg.Connection[Any],
    strategy_id: UUID,
    request_identity: str,
    request_sha256: str,
) -> UUID:
    row = connection.execute(
        """
        SELECT receipt_id FROM mra.command_receipt
        WHERE command_kind = 'REGISTER_STRATEGY_VERSION'
          AND scope_id = %s AND idempotency_key = %s AND request_hash = %s
        """,
        (str(strategy_id), request_identity, request_sha256),
    ).fetchone()
    if row is None:
        raise StrategyAuthorityIntegrityError("Strategy receipt is absent")
    return UUID(str(row[0]))


def _record_row(
    connection: psycopg.Connection[Any],
    predicate: str,
    parameters: tuple[object, ...],
    *,
    lock: bool,
):
    suffix = " FOR SHARE OF version, receipt" if lock else ""
    return connection.execute(
        """
        SELECT version.strategy_id, version.strategy_version_id,
               version.version, version.context_requirement_count,
               version.forecast_rule_count, version.content_sha256,
               version.request_identity, version.request_sha256,
               version.frozen_at, receipt.receipt_id
        FROM mra.strategy_version AS version
        JOIN mra.command_receipt AS receipt
          ON receipt.command_kind = 'REGISTER_STRATEGY_VERSION'
         AND receipt.scope_id = version.strategy_id::text
         AND receipt.idempotency_key = version.request_identity
         AND receipt.request_hash = version.request_sha256
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _record(row) -> StrategyVersionRecord:
    return StrategyVersionRecord(
        strategy_id=UUID(str(row[0])),
        strategy_version_id=UUID(str(row[1])),
        version=int(row[2]),
        context_requirement_count=int(row[3]),
        forecast_rule_count=int(row[4]),
        content_sha256=str(row[5]),
        request_identity=str(row[6]),
        request_sha256=str(row[7]),
        frozen_at=row[8],
        receipt_id=UUID(str(row[9])),
    )


__all__ = ["PostgresStrategyRepository", "_record", "_record_row"]
