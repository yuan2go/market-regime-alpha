"""PostgreSQL persistence for Opportunity and Thesis Authority."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import OpportunityAuthority, ThesisPlan
from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import OpportunityReconciliation, OpportunitySetRecord, ThesisRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresOpportunityRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_set_identity(self, decision_run_id: UUID, strategy_version_id: UUID) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"opportunity-set:{decision_run_id}:{strategy_version_id}",)
        )

    def lock_thesis_identity(self, opportunity_id: UUID) -> None:
        self._connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"thesis:{opportunity_id}",))

    def authoritative_time(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise DecisionAuthorityIntegrityError("PostgreSQL time is absent")
        return row[0]

    def insert_set(self, authority: OpportunityAuthority) -> OpportunitySetRecord:
        prepared = authority.prepared
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.opportunity_context (
                opportunity_context_id, opportunity_id, opportunity_set_id,
                decision_run_id, strategy_version_id, ordinal,
                signal_context_binding_id, signal_id, signal_group_id,
                candidate_id, strategy_context_requirement_id,
                context_assessment_id, binding_content_sha256, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                (
                    binding.opportunity_context_id,
                    item.opportunity_id,
                    authority.opportunity_set_id,
                    prepared.decision_run_id,
                    prepared.strategy_version_id,
                    binding.ordinal,
                    binding.source.signal_context_binding_id,
                    item.source.signal_id,
                    prepared.signal_group_id,
                    item.source.candidate_id,
                    binding.source.strategy_context_requirement_id,
                    binding.source.context_assessment_id,
                    binding.source.content_sha256,
                    binding.content_sha256,
                )
                for item in authority.opportunities
                for binding in item.contexts
            ),
        )
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.opportunity (
                opportunity_id, opportunity_set_id, ordinal, decision_run_id,
                strategy_version_id, forecast_group_id, forecast_id,
                forecast_content_sha256, forecast_recorded_at, signal_group_id,
                signal_id, signal_content_sha256, candidate_id, instrument_id,
                commitment_id, commitment_content_sha256, target_definition_id,
                target_definition_sha256, status, action, reason_code,
                context_count, context_roster_sha256, content_sha256, recorded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    item.opportunity_id,
                    authority.opportunity_set_id,
                    item.ordinal,
                    prepared.decision_run_id,
                    prepared.strategy_version_id,
                    prepared.forecast_group_id,
                    item.source.forecast_id,
                    item.source.forecast_content_sha256,
                    prepared.forecast_recorded_at,
                    prepared.signal_group_id,
                    item.source.signal_id,
                    item.source.signal_content_sha256,
                    item.source.candidate_id,
                    item.source.instrument_id,
                    item.source.commitment_id,
                    item.source.commitment_content_sha256,
                    item.source.target_definition_id,
                    item.source.target_definition_sha256,
                    item.status.value,
                    item.action.value,
                    item.reason_code,
                    len(item.contexts),
                    item.context_roster_sha256,
                    item.content_sha256,
                    authority.recorded_at,
                )
                for item in authority.opportunities
            ),
        )
        self._connection.execute(
            """
            INSERT INTO mra.opportunity_set (
                opportunity_set_id, decision_run_id, strategy_version_id,
                strategy_version_sha256, signal_group_id, signal_content_sha256,
                forecast_group_id, forecast_content_sha256, forecast_recorded_at,
                opportunity_count, context_count, opportunity_roster_sha256,
                request_identity, request_sha256, command_receipt_id,
                content_sha256, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                authority.opportunity_set_id,
                prepared.decision_run_id,
                prepared.strategy_version_id,
                prepared.strategy_version_sha256,
                prepared.signal_group_id,
                prepared.signal_content_sha256,
                prepared.forecast_group_id,
                prepared.forecast_content_sha256,
                prepared.forecast_recorded_at,
                len(authority.opportunities),
                authority.context_count,
                authority.opportunity_roster_sha256,
                authority.request_identity,
                authority.request_sha256,
                authority.command_receipt_id,
                authority.content_sha256,
                authority.recorded_at,
            ),
        )
        return OpportunitySetRecord(
            opportunity_set_id=authority.opportunity_set_id,
            decision_run_id=prepared.decision_run_id,
            strategy_version_id=prepared.strategy_version_id,
            opportunity_count=len(authority.opportunities),
            context_count=authority.context_count,
            content_sha256=authority.content_sha256,
            request_identity=authority.request_identity,
            request_sha256=authority.request_sha256,
            recorded_at=authority.recorded_at,
            receipt_id=authority.command_receipt_id,
        )

    def insert_thesis(
        self, plan: ThesisPlan, *, opportunity_scope: tuple[UUID, UUID, UUID], request_identity: str, request_sha256: str
    ) -> ThesisRecord:
        opportunity_set_id, decision_run_id, strategy_version_id = opportunity_scope
        self._connection.cursor().executemany(
            """
            INSERT INTO mra.thesis_condition (
                thesis_condition_id, thesis_id, ordinal, condition_code,
                condition_kind, source_kind, operator, decimal_threshold,
                text_threshold, value_unit, missing_action, invalidates,
                content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                (
                    item.thesis_condition_id,
                    item.thesis_id,
                    item.ordinal,
                    item.condition_code,
                    item.kind.value,
                    item.source.value,
                    item.operator.value,
                    item.decimal_threshold,
                    item.text_threshold,
                    item.value_unit,
                    item.missing_action.value,
                    item.invalidates,
                    item.content_sha256,
                )
                for item in plan.conditions
            ),
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.thesis (
                thesis_id, opportunity_id, opportunity_set_id, decision_run_id,
                strategy_version_id, opportunity_content_sha256, revision,
                supersedes_thesis_id, claim, condition_count,
                condition_roster_sha256, code_artifact_id, code_content_sha256,
                code_size_bytes, config_artifact_id, config_content_sha256,
                config_size_bytes, provenance_sha256, request_identity,
                request_sha256, command_receipt_id, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING frozen_at
            """,
            (
                plan.thesis_id,
                plan.opportunity_id,
                opportunity_set_id,
                decision_run_id,
                strategy_version_id,
                plan.opportunity_content_sha256,
                plan.revision,
                plan.supersedes_thesis_id,
                plan.claim,
                len(plan.conditions),
                plan.condition_roster_sha256,
                plan.code_artifact.artifact_id,
                plan.code_artifact.content_sha256,
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                plan.config_artifact.content_sha256,
                plan.config_artifact.size_bytes,
                plan.provenance_sha256,
                request_identity,
                request_sha256,
                _receipt_id(self._connection, "CREATE_THESIS", str(plan.opportunity_id), request_identity, request_sha256),
                plan.content_sha256,
            ),
        ).fetchone()
        if row is None:
            raise DecisionAuthorityIntegrityError("Thesis frozen time is absent")
        return ThesisRecord(
            thesis_id=plan.thesis_id,
            opportunity_id=plan.opportunity_id,
            revision=plan.revision,
            condition_count=len(plan.conditions),
            content_sha256=plan.content_sha256,
            request_identity=request_identity,
            request_sha256=request_sha256,
            frozen_at=row[0],
            receipt_id=_receipt_id(self._connection, "CREATE_THESIS", str(plan.opportunity_id), request_identity, request_sha256),
        )

    def set_record(self, opportunity_set_id: UUID, *, lock: bool) -> OpportunitySetRecord:
        row = _set_row(self._connection, "root.opportunity_set_id = %s", (opportunity_set_id,), lock=lock)
        if row is None:
            raise DecisionAuthorityIntegrityError("OpportunitySet is absent")
        return _set_record(row)

    def thesis_record(self, thesis_id: UUID, *, lock: bool) -> ThesisRecord:
        row = _thesis_row(self._connection, "root.thesis_id = %s", (thesis_id,), lock=lock)
        if row is None:
            raise DecisionAuthorityIntegrityError("Thesis is absent")
        return _thesis_record(row)

    def reconcile(self, opportunity_set_id: UUID, *, lock: bool) -> OpportunityReconciliation:
        suffix = " FOR SHARE" if lock else ""
        root = self._connection.execute(
            "SELECT opportunity_count, context_count, opportunity_roster_sha256 FROM mra.opportunity_set WHERE opportunity_set_id = %s"
            + suffix,
            (opportunity_set_id,),
        ).fetchone()
        if root is None:
            return OpportunityReconciliation(opportunity_set_id, 0, 0, "0" * 64, False)
        rows = self._connection.execute(
            "SELECT opportunity_id, ordinal, content_sha256 FROM mra.opportunity WHERE opportunity_set_id = %s ORDER BY ordinal",
            (opportunity_set_id,),
        ).fetchall()
        contexts = self._connection.execute(
            "SELECT count(*) FROM mra.opportunity_context WHERE opportunity_set_id = %s", (opportunity_set_id,)
        ).fetchone()
        roster_hash = canonical_json_sha256(
            tuple({"content_sha256": str(row[2]), "opportunity_id": UUID(str(row[0])), "ordinal": int(row[1])} for row in rows)
        )
        context_count = int(contexts[0]) if contexts else 0
        matched = (
            len(rows) == int(root[0])
            and context_count == int(root[1])
            and roster_hash == str(root[2])
            and tuple(int(row[1]) for row in rows) == tuple(range(1, len(rows) + 1))
        )
        return OpportunityReconciliation(opportunity_set_id, len(rows), context_count, roster_hash, matched)


def _receipt_id(connection, command_kind, scope_id, request_identity, request_sha256):
    row = connection.execute(
        "SELECT receipt_id FROM mra.command_receipt WHERE command_kind = %s AND scope_id = %s AND idempotency_key = %s AND request_hash = %s",
        (command_kind, scope_id, request_identity, request_sha256),
    ).fetchone()
    if row is None:
        raise DecisionAuthorityIntegrityError("Command receipt is absent")
    return UUID(str(row[0]))


def _set_row(connection, predicate, parameters, *, lock):
    suffix = " FOR SHARE OF root, receipt" if lock else ""
    return connection.execute(
        """
        SELECT root.opportunity_set_id, root.decision_run_id,
               root.strategy_version_id, root.opportunity_count,
               root.context_count, root.content_sha256, root.request_identity,
               root.request_sha256, root.recorded_at, receipt.receipt_id
        FROM mra.opportunity_set AS root JOIN mra.command_receipt AS receipt
          ON receipt.receipt_id = root.command_receipt_id
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _set_record(row):
    return OpportunitySetRecord(
        UUID(str(row[0])),
        UUID(str(row[1])),
        UUID(str(row[2])),
        int(row[3]),
        int(row[4]),
        str(row[5]),
        str(row[6]),
        str(row[7]),
        row[8],
        UUID(str(row[9])),
    )


def _thesis_row(connection, predicate, parameters, *, lock):
    suffix = " FOR SHARE OF root, receipt" if lock else ""
    return connection.execute(
        """
        SELECT root.thesis_id, root.opportunity_id, root.revision,
               root.condition_count, root.content_sha256, root.request_identity,
               root.request_sha256, root.frozen_at, receipt.receipt_id
        FROM mra.thesis AS root JOIN mra.command_receipt AS receipt
          ON receipt.receipt_id = root.command_receipt_id
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _thesis_record(row):
    return ThesisRecord(
        UUID(str(row[0])), UUID(str(row[1])), int(row[2]), int(row[3]), str(row[4]), str(row[5]), str(row[6]), row[7], UUID(str(row[8]))
    )


__all__ = ["PostgresOpportunityRepository", "_set_record", "_set_row", "_thesis_record", "_thesis_row"]
