"""PostgreSQL persistence for Portfolio Authority."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import PortfolioPolicyPlan, PortfolioProposalAuthority
from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import PortfolioPolicyRecord, PortfolioProposalRecord, PortfolioReconciliation
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresPortfolioRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_policy_identity(self, policy_code: str) -> None:
        self._connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"portfolio-policy:{policy_code}",))

    def lock_proposal_identity(self, decision_run_id: UUID, strategy_version_id: UUID, portfolio_policy_id: UUID) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"portfolio-proposal:{decision_run_id}:{strategy_version_id}:{portfolio_policy_id}",),
        )

    def authoritative_time(self):
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise DecisionAuthorityIntegrityError("PostgreSQL time is absent")
        return row[0]

    def register_policy(self, plan: PortfolioPolicyPlan, *, request_identity: str, request_sha256: str) -> PortfolioPolicyRecord:
        row = self._connection.execute(
            """INSERT INTO mra.portfolio_policy (
                portfolio_policy_id, policy_code, version, supersedes_policy_id,
                allocation_method, minimum_estimable_count, maximum_line_count,
                maximum_single_weight, maximum_gross_weight, maximum_net_weight,
                minimum_cash_weight, maximum_turnover, decimal_places,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, request_identity, request_sha256,
                command_receipt_id, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING frozen_at""",
            (
                plan.portfolio_policy_id,
                plan.policy_code,
                plan.version,
                plan.supersedes_policy_id,
                plan.allocation_method.value,
                plan.minimum_estimable_count,
                plan.maximum_line_count,
                plan.maximum_single_weight,
                plan.maximum_gross_weight,
                plan.maximum_net_weight,
                plan.minimum_cash_weight,
                plan.maximum_turnover,
                plan.decimal_places,
                plan.code_artifact.artifact_id,
                plan.code_artifact.content_sha256,
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                plan.config_artifact.content_sha256,
                plan.config_artifact.size_bytes,
                plan.provenance_sha256,
                request_identity,
                request_sha256,
                _receipt_id(self._connection, "REGISTER_PORTFOLIO_POLICY", plan.policy_code, request_identity, request_sha256),
                plan.content_sha256,
            ),
        ).fetchone()
        if row is None:
            raise DecisionAuthorityIntegrityError("PortfolioPolicy frozen time is absent")
        return PortfolioPolicyRecord(
            plan.portfolio_policy_id,
            plan.policy_code,
            plan.version,
            plan.content_sha256,
            request_identity,
            request_sha256,
            row[0],
            _receipt_id(self._connection, "REGISTER_PORTFOLIO_POLICY", plan.policy_code, request_identity, request_sha256),
        )

    def insert_proposal(self, authority: PortfolioProposalAuthority) -> PortfolioProposalRecord:
        prepared, policy = authority.prepared, authority.policy
        self._connection.cursor().executemany(
            """INSERT INTO mra.portfolio_line (
                portfolio_line_id, portfolio_proposal_id, decision_run_id,
                strategy_version_id, ordinal, opportunity_id,
                opportunity_set_id, candidate_id, instrument_id,
                target_definition_id, opportunity_status,
                opportunity_content_sha256, status, proposed_weight,
                reason_code, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                (
                    item.portfolio_line_id,
                    authority.portfolio_proposal_id,
                    prepared.decision_run_id,
                    prepared.strategy_version_id,
                    item.ordinal,
                    item.source.opportunity_id,
                    prepared.opportunity_set_id,
                    item.source.candidate_id,
                    item.source.instrument_id,
                    item.source.target_definition_id,
                    item.source.status.value,
                    item.source.content_sha256,
                    item.status.value,
                    item.proposed_weight,
                    item.reason_code,
                    item.content_sha256,
                )
                for item in authority.lines
            ),
        )
        self._connection.execute(
            """INSERT INTO mra.portfolio_proposal (
                portfolio_proposal_id, decision_run_id, strategy_version_id,
                opportunity_set_id, opportunity_set_sha256,
                opportunity_set_recorded_at, portfolio_policy_id,
                portfolio_policy_sha256, status, line_count,
                line_roster_sha256, included_count, excluded_count,
                not_estimable_count, gross_weight, net_weight, cash_weight,
                turnover_weight, request_identity, request_sha256,
                command_receipt_id, content_sha256, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                authority.portfolio_proposal_id,
                prepared.decision_run_id,
                prepared.strategy_version_id,
                prepared.opportunity_set_id,
                prepared.opportunity_set_sha256,
                prepared.opportunity_set_recorded_at,
                policy.portfolio_policy_id,
                policy.content_sha256,
                authority.status.value,
                len(authority.lines),
                authority.line_roster_sha256,
                authority.included_count,
                authority.excluded_count,
                authority.not_estimable_count,
                authority.gross_weight,
                authority.net_weight,
                authority.cash_weight,
                authority.turnover_weight,
                authority.request_identity,
                authority.request_sha256,
                authority.command_receipt_id,
                authority.content_sha256,
                authority.recorded_at,
            ),
        )
        return PortfolioProposalRecord(
            authority.portfolio_proposal_id,
            prepared.decision_run_id,
            prepared.strategy_version_id,
            policy.portfolio_policy_id,
            authority.status.value,
            len(authority.lines),
            authority.included_count,
            authority.content_sha256,
            authority.request_identity,
            authority.request_sha256,
            authority.recorded_at,
            authority.command_receipt_id,
        )

    def policy_record(self, portfolio_policy_id: UUID, *, lock: bool) -> PortfolioPolicyRecord:
        row = _policy_row(self._connection, "root.portfolio_policy_id = %s", (portfolio_policy_id,), lock=lock)
        if row is None:
            raise DecisionAuthorityIntegrityError("PortfolioPolicy is absent")
        return _policy_record(row)

    def proposal_record(self, portfolio_proposal_id: UUID, *, lock: bool) -> PortfolioProposalRecord:
        row = _proposal_row(self._connection, "root.portfolio_proposal_id = %s", (portfolio_proposal_id,), lock=lock)
        if row is None:
            raise DecisionAuthorityIntegrityError("PortfolioProposal is absent")
        return _proposal_record(row)

    def reconcile(self, portfolio_proposal_id: UUID, *, lock: bool) -> PortfolioReconciliation:
        suffix = " FOR SHARE" if lock else ""
        root = self._connection.execute(
            "SELECT line_count, line_roster_sha256, gross_weight FROM mra.portfolio_proposal WHERE portfolio_proposal_id = %s" + suffix,
            (portfolio_proposal_id,),
        ).fetchone()
        if root is None:
            return PortfolioReconciliation(portfolio_proposal_id, 0, "0" * 64, "0", False)
        rows = self._connection.execute(
            "SELECT portfolio_line_id, ordinal, content_sha256, proposed_weight FROM mra.portfolio_line WHERE portfolio_proposal_id = %s ORDER BY ordinal",
            (portfolio_proposal_id,),
        ).fetchall()
        roster_hash = canonical_json_sha256(
            tuple({"content_sha256": str(row[2]), "ordinal": int(row[1]), "portfolio_line_id": UUID(str(row[0]))} for row in rows)
        )
        gross = sum((row[3] for row in rows), 0)
        matched = (
            len(rows) == int(root[0])
            and roster_hash == str(root[1])
            and gross == root[2]
            and tuple(int(row[1]) for row in rows) == tuple(range(1, len(rows) + 1))
        )
        return PortfolioReconciliation(portfolio_proposal_id, len(rows), roster_hash, str(gross), matched)


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
        """SELECT root.portfolio_policy_id, root.policy_code, root.version,
        root.content_sha256, root.request_identity, root.request_sha256, root.frozen_at,
        receipt.receipt_id FROM mra.portfolio_policy AS root JOIN mra.command_receipt AS receipt
        ON receipt.receipt_id = root.command_receipt_id WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _policy_record(row):
    return PortfolioPolicyRecord(
        UUID(str(row[0])), str(row[1]), int(row[2]), str(row[3]), str(row[4]), str(row[5]), row[6], UUID(str(row[7]))
    )


def _proposal_row(connection, predicate, parameters, *, lock):
    suffix = " FOR SHARE OF root, receipt" if lock else ""
    return connection.execute(
        """SELECT root.portfolio_proposal_id, root.decision_run_id,
        root.strategy_version_id, root.portfolio_policy_id, root.status, root.line_count,
        root.included_count, root.content_sha256, root.request_identity, root.request_sha256,
        root.recorded_at, receipt.receipt_id FROM mra.portfolio_proposal AS root
        JOIN mra.command_receipt AS receipt ON receipt.receipt_id = root.command_receipt_id
        WHERE """
        + predicate
        + suffix,
        parameters,
    ).fetchone()


def _proposal_record(row):
    return PortfolioProposalRecord(
        UUID(str(row[0])),
        UUID(str(row[1])),
        UUID(str(row[2])),
        UUID(str(row[3])),
        str(row[4]),
        int(row[5]),
        int(row[6]),
        str(row[7]),
        str(row[8]),
        str(row[9]),
        row[10],
        UUID(str(row[11])),
    )


__all__ = ["PostgresPortfolioRepository", "_policy_record", "_policy_row", "_proposal_record", "_proposal_row"]
