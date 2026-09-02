"""PostgreSQL persistence for decision-support Risk Authority."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import RiskDecisionAuthority, RiskPolicyPlan
from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import RiskDecisionRecord, RiskPolicyRecord, RiskReconciliation
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresRiskRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_policy_identity(self, policy_code: str) -> None:
        self._connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"risk-policy:{policy_code}",))

    def lock_decision_identity(self, portfolio_proposal_id: UUID, risk_policy_id: UUID) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"risk-decision:{portfolio_proposal_id}:{risk_policy_id}",)
        )

    def authoritative_time(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise DecisionAuthorityIntegrityError("PostgreSQL time is absent")
        return row[0]

    def register_policy(self, plan: RiskPolicyPlan, *, request_identity: str, request_sha256: str) -> RiskPolicyRecord:
        receipt_id = _receipt_id(self._connection, "REGISTER_RISK_POLICY", plan.policy_code, request_identity, request_sha256)
        self._connection.cursor().executemany(
            """INSERT INTO mra.risk_rule (
                risk_rule_id, risk_policy_id, ordinal, rule_code, rule_scope,
                subject, operator, decimal_threshold, integer_threshold,
                text_threshold, boolean_threshold, value_unit, severity,
                missing_action, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                (
                    item.risk_rule_id,
                    plan.risk_policy_id,
                    item.ordinal,
                    item.rule_code,
                    item.scope.value,
                    item.subject.value,
                    item.operator.value,
                    item.decimal_threshold,
                    item.integer_threshold,
                    item.text_threshold,
                    item.boolean_threshold,
                    item.value_unit,
                    item.severity.value,
                    item.missing_action.value,
                    item.content_sha256,
                )
                for item in plan.rules
            ),
        )
        row = self._connection.execute(
            """INSERT INTO mra.risk_policy (
                risk_policy_id, policy_code, version, supersedes_policy_id,
                authority_scope, rule_count, rule_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, request_identity, request_sha256,
                command_receipt_id, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING frozen_at""",
            (
                plan.risk_policy_id,
                plan.policy_code,
                plan.version,
                plan.supersedes_policy_id,
                plan.authority_scope.value,
                len(plan.rules),
                plan.rule_roster_sha256,
                plan.code_artifact.artifact_id,
                plan.code_artifact.content_sha256,
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                plan.config_artifact.content_sha256,
                plan.config_artifact.size_bytes,
                plan.provenance_sha256,
                request_identity,
                request_sha256,
                receipt_id,
                plan.content_sha256,
            ),
        ).fetchone()
        if row is None:
            raise DecisionAuthorityIntegrityError("RiskPolicy frozen time is absent")
        return RiskPolicyRecord(
            plan.risk_policy_id,
            plan.policy_code,
            plan.version,
            len(plan.rules),
            plan.content_sha256,
            request_identity,
            request_sha256,
            row[0],
            receipt_id,
        )

    def insert_decision(self, authority: RiskDecisionAuthority) -> RiskDecisionRecord:
        self._connection.cursor().executemany(
            """INSERT INTO mra.risk_reason (
                risk_reason_id, risk_decision_id, portfolio_proposal_id,
                risk_policy_id, ordinal, risk_rule_id, rule_scope, subject,
                portfolio_line_id, result, observed_decimal, observed_integer,
                observed_text, observed_boolean, reason_code, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                (
                    item.risk_reason_id,
                    authority.risk_decision_id,
                    authority.prepared.portfolio_proposal_id,
                    authority.policy.risk_policy_id,
                    item.ordinal,
                    item.rule.risk_rule_id,
                    item.rule.scope.value,
                    item.rule.subject.value,
                    item.portfolio_line_id,
                    item.result.value,
                    item.observed_decimal,
                    item.observed_integer,
                    item.observed_text,
                    item.observed_boolean,
                    item.reason_code,
                    item.content_sha256,
                )
                for item in authority.reasons
            ),
        )
        proposal = self._connection.execute(
            "SELECT decision_run_id, strategy_version_id FROM mra.portfolio_proposal WHERE portfolio_proposal_id = %s FOR SHARE",
            (authority.prepared.portfolio_proposal_id,),
        ).fetchone()
        if proposal is None:
            raise DecisionAuthorityIntegrityError("PortfolioProposal is absent")
        self._connection.execute(
            """INSERT INTO mra.risk_decision (
                risk_decision_id, portfolio_proposal_id, decision_run_id,
                strategy_version_id, proposal_content_sha256, risk_policy_id,
                risk_policy_sha256, authority_scope, status, reason_count,
                reason_roster_sha256, request_identity, request_sha256,
                command_receipt_id, content_sha256, decided_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                authority.risk_decision_id,
                authority.prepared.portfolio_proposal_id,
                proposal[0],
                proposal[1],
                authority.prepared.proposal_content_sha256,
                authority.policy.risk_policy_id,
                authority.policy.content_sha256,
                authority.policy.authority_scope.value,
                authority.status.value,
                len(authority.reasons),
                authority.reason_roster_sha256,
                authority.request_identity,
                authority.request_sha256,
                authority.command_receipt_id,
                authority.content_sha256,
                authority.decided_at,
            ),
        )
        return RiskDecisionRecord(
            authority.risk_decision_id,
            authority.prepared.portfolio_proposal_id,
            authority.policy.risk_policy_id,
            authority.status.value,
            len(authority.reasons),
            authority.content_sha256,
            authority.request_identity,
            authority.request_sha256,
            authority.decided_at,
            authority.command_receipt_id,
        )

    def policy_record(self, risk_policy_id: UUID, *, lock: bool) -> RiskPolicyRecord:
        row = _policy_row(self._connection, "root.risk_policy_id = %s", (risk_policy_id,), lock=lock)
        if row is None:
            raise DecisionAuthorityIntegrityError("RiskPolicy is absent")
        return _policy_record(row)

    def decision_record(self, risk_decision_id: UUID, *, lock: bool) -> RiskDecisionRecord:
        row = _decision_row(self._connection, "root.risk_decision_id = %s", (risk_decision_id,), lock=lock)
        if row is None:
            raise DecisionAuthorityIntegrityError("RiskDecision is absent")
        return _decision_record(row)

    def reconcile(self, risk_decision_id: UUID, *, lock: bool) -> RiskReconciliation:
        suffix = " FOR SHARE" if lock else ""
        root = self._connection.execute(
            "SELECT reason_count, reason_roster_sha256 FROM mra.risk_decision WHERE risk_decision_id = %s" + suffix, (risk_decision_id,)
        ).fetchone()
        if root is None:
            return RiskReconciliation(risk_decision_id, 0, "0" * 64, False)
        rows = self._connection.execute(
            "SELECT risk_reason_id, ordinal, content_sha256 FROM mra.risk_reason WHERE risk_decision_id = %s ORDER BY ordinal",
            (risk_decision_id,),
        ).fetchall()
        roster_hash = canonical_json_sha256(
            tuple({"content_sha256": str(row[2]), "ordinal": int(row[1]), "risk_reason_id": UUID(str(row[0]))} for row in rows)
        )
        matched = (
            len(rows) == int(root[0])
            and roster_hash == str(root[1])
            and tuple(int(row[1]) for row in rows) == tuple(range(1, len(rows) + 1))
        )
        return RiskReconciliation(risk_decision_id, len(rows), roster_hash, matched)


def _receipt_id(connection, command_kind, scope_id, request_identity, request_sha256):
    row = connection.execute(
        "SELECT receipt_id FROM mra.command_receipt WHERE command_kind = %s AND scope_id = %s AND idempotency_key = %s AND request_hash = %s",
        (command_kind, scope_id, request_identity, request_sha256),
    ).fetchone()
    if row is None:
        raise DecisionAuthorityIntegrityError("Command receipt is absent")
    return UUID(str(row[0]))


def _policy_row(connection, predicate, parameters, *, lock):
    suffix = " FOR SHARE OF root, receipt" if lock else ""
    return connection.execute(
        """SELECT root.risk_policy_id, root.policy_code, root.version,
        root.rule_count, root.content_sha256, root.request_identity, root.request_sha256,
        root.frozen_at, receipt.receipt_id FROM mra.risk_policy AS root
        JOIN mra.command_receipt AS receipt ON receipt.receipt_id = root.command_receipt_id
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _policy_record(row):
    return RiskPolicyRecord(
        UUID(str(row[0])), str(row[1]), int(row[2]), int(row[3]), str(row[4]), str(row[5]), str(row[6]), row[7], UUID(str(row[8]))
    )


def _decision_row(connection, predicate, parameters, *, lock):
    suffix = " FOR SHARE OF root, receipt" if lock else ""
    return connection.execute(
        """SELECT root.risk_decision_id, root.portfolio_proposal_id,
        root.risk_policy_id, root.status, root.reason_count, root.content_sha256,
        root.request_identity, root.request_sha256, root.decided_at, receipt.receipt_id
        FROM mra.risk_decision AS root JOIN mra.command_receipt AS receipt
        ON receipt.receipt_id = root.command_receipt_id WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _decision_record(row):
    return RiskDecisionRecord(
        UUID(str(row[0])),
        UUID(str(row[1])),
        UUID(str(row[2])),
        str(row[3]),
        int(row[4]),
        str(row[5]),
        str(row[6]),
        str(row[7]),
        row[8],
        UUID(str(row[9])),
    )


__all__ = ["PostgresRiskRepository", "_decision_record", "_decision_row", "_policy_record", "_policy_row"]
