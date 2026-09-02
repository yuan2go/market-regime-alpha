"""Exact PortfolioProposal and RiskPolicy inputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    PortfolioLineStatus,
    PortfolioProposalStatus,
    PreparedRiskInputs,
    PreparedRiskLine,
    RiskAuthorityScope,
    RiskMissingAction,
    RiskOperator,
    RiskPolicyPlan,
    RiskRulePlan,
    RiskRuleScope,
    RiskSeverity,
    RiskSubject,
)
from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import RiskDecisionRecord, RiskPolicyRecord
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.decision_risks import (
    _decision_record,
    _decision_row,
    _policy_record,
    _policy_row,
)


class PostgresRiskInputPreparationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(self, portfolio_proposal_id: UUID, risk_policy_id: UUID) -> tuple[PreparedRiskInputs, RiskPolicyPlan]:
        with self._pool.connection(read_only=True) as connection:
            return _load_inputs(connection, portfolio_proposal_id, risk_policy_id, lock=False)


class PostgresRiskQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def find_policy_request(self, policy_code: str, request_identity: str) -> RiskPolicyRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _policy_row(
                connection, "root.policy_code = %s AND root.request_identity = %s", (policy_code, request_identity), lock=False
            )
        return None if row is None else _policy_record(row)

    def find_decision_request(self, portfolio_proposal_id: UUID, risk_policy_id: UUID, request_identity: str) -> RiskDecisionRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _decision_row(
                connection,
                "root.portfolio_proposal_id = %s AND root.risk_policy_id = %s AND root.request_identity = %s",
                (portfolio_proposal_id, risk_policy_id, request_identity),
                lock=False,
            )
        return None if row is None else _decision_record(row)


class PostgresRiskDependencyRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedRiskInputs, policy: RiskPolicyPlan) -> None:
        actual = _load_inputs(self._connection, prepared.portfolio_proposal_id, policy.risk_policy_id, lock=True)
        if actual != (prepared, policy):
            raise DecisionAuthorityIntegrityError("prepared Risk inputs changed before closure")


def _load_inputs(
    connection: psycopg.Connection[Any], portfolio_proposal_id: UUID, risk_policy_id: UUID, *, lock: bool
) -> tuple[PreparedRiskInputs, RiskPolicyPlan]:
    suffix = " FOR SHARE" if lock else ""
    root = connection.execute(
        """SELECT proposal.content_sha256, proposal.status, proposal.line_count,
                  proposal.included_count, proposal.not_estimable_count,
                  proposal.gross_weight, proposal.net_weight, proposal.cash_weight,
                  proposal.decision_run_id, run.research_qualification_count
           FROM mra.portfolio_proposal AS proposal
           JOIN mra.decision_run AS run ON run.decision_run_id = proposal.decision_run_id
           WHERE proposal.portfolio_proposal_id = %s"""
        + suffix,
        (portfolio_proposal_id,),
    ).fetchone()
    if root is None:
        raise DecisionAuthorityIntegrityError("PortfolioProposal is absent")
    rows = connection.execute(
        """SELECT portfolio_line_id, ordinal, status, proposed_weight,
                  content_sha256 FROM mra.portfolio_line
           WHERE portfolio_proposal_id = %s ORDER BY ordinal"""
        + suffix,
        (portfolio_proposal_id,),
    ).fetchall()
    if len(rows) != int(root[2]) or tuple(int(row[1]) for row in rows) != tuple(range(1, len(rows) + 1)):
        raise DecisionAuthorityIntegrityError("PortfolioLine roster is incomplete")
    prepared = PreparedRiskInputs(
        portfolio_proposal_id=portfolio_proposal_id,
        proposal_content_sha256=str(root[0]),
        proposal_status=PortfolioProposalStatus(str(root[1])),
        line_count=int(root[2]),
        included_count=int(root[3]),
        not_estimable_count=int(root[4]),
        gross_weight=Decimal(root[5]),
        net_weight=Decimal(root[6]),
        cash_weight=Decimal(root[7]),
        qualification_count=int(root[9]),
        lines=tuple(
            PreparedRiskLine(UUID(str(row[0])), int(row[1]), PortfolioLineStatus(str(row[2])), Decimal(row[3]), str(row[4])) for row in rows
        ),
    )
    return prepared, _load_policy(connection, risk_policy_id, lock=lock)


def _load_policy(connection: psycopg.Connection[Any], risk_policy_id: UUID, *, lock: bool) -> RiskPolicyPlan:
    suffix = " FOR SHARE" if lock else ""
    root = connection.execute(
        """SELECT policy_code, version, supersedes_policy_id, authority_scope,
                  rule_count, code_artifact_id, code_content_sha256, code_size_bytes,
                  config_artifact_id, config_content_sha256, config_size_bytes,
                  provenance_sha256, content_sha256 FROM mra.risk_policy
           WHERE risk_policy_id = %s"""
        + suffix,
        (risk_policy_id,),
    ).fetchone()
    if root is None:
        raise DecisionAuthorityIntegrityError("RiskPolicy is absent")
    rows = connection.execute(
        """SELECT risk_rule_id, ordinal, rule_code, rule_scope, subject,
                  operator, decimal_threshold, integer_threshold, text_threshold,
                  boolean_threshold, value_unit, severity, missing_action
           FROM mra.risk_rule WHERE risk_policy_id = %s ORDER BY ordinal"""
        + suffix,
        (risk_policy_id,),
    ).fetchall()
    if len(rows) != int(root[4]):
        raise DecisionAuthorityIntegrityError("RiskRule roster is incomplete")
    plan = RiskPolicyPlan(
        risk_policy_id=risk_policy_id,
        policy_code=str(root[0]),
        version=int(root[1]),
        supersedes_policy_id=UUID(str(root[2])) if root[2] is not None else None,
        authority_scope=RiskAuthorityScope(str(root[3])),
        rules=tuple(
            RiskRulePlan(
                risk_rule_id=UUID(str(row[0])),
                risk_policy_id=risk_policy_id,
                ordinal=int(row[1]),
                rule_code=str(row[2]),
                scope=RiskRuleScope(str(row[3])),
                subject=RiskSubject(str(row[4])),
                operator=RiskOperator(str(row[5])),
                decimal_threshold=Decimal(row[6]) if row[6] is not None else None,
                integer_threshold=int(row[7]) if row[7] is not None else None,
                text_threshold=str(row[8]) if row[8] is not None else None,
                boolean_threshold=bool(row[9]) if row[9] is not None else None,
                value_unit=str(row[10]),
                severity=RiskSeverity(str(row[11])),
                missing_action=RiskMissingAction(str(row[12])),
            )
            for row in rows
        ),
        code_artifact=DecisionArtifactBinding(UUID(str(root[5])), str(root[6]), int(root[7])),
        config_artifact=DecisionArtifactBinding(UUID(str(root[8])), str(root[9]), int(root[10])),
        provenance_sha256=str(root[11]),
    )
    if plan.content_sha256 != str(root[12]):
        raise DecisionAuthorityIntegrityError("RiskPolicy content is corrupt")
    return plan


__all__ = ["PostgresRiskDependencyRepository", "PostgresRiskInputPreparationProvider", "PostgresRiskQueryProvider"]
