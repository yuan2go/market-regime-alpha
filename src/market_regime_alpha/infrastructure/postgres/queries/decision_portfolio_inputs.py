"""Exact OpportunitySet and PortfolioPolicy inputs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    OpportunityStatus,
    PortfolioAllocationMethod,
    PortfolioPolicyPlan,
    PreparedPortfolioInputs,
    PreparedPortfolioOpportunity,
)
from market_regime_alpha.decision_support.errors import DecisionAuthorityIntegrityError
from market_regime_alpha.decision_support.ports import PortfolioPolicyRecord, PortfolioProposalRecord
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.decision_portfolios import (
    _policy_record,
    _policy_row,
    _proposal_record,
    _proposal_row,
)


class PostgresPortfolioInputPreparationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def prepare(self, opportunity_set_id: UUID, portfolio_policy_id: UUID) -> tuple[PreparedPortfolioInputs, PortfolioPolicyPlan]:
        with self._pool.connection(read_only=True) as connection:
            return _load_inputs(connection, opportunity_set_id, portfolio_policy_id, lock=False)


class PostgresPortfolioQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def find_policy_request(self, policy_code: str, request_identity: str) -> PortfolioPolicyRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _policy_row(
                connection, "root.policy_code = %s AND root.request_identity = %s", (policy_code, request_identity), lock=False
            )
        return None if row is None else _policy_record(row)

    def find_proposal_request(
        self, opportunity_set_id: UUID, portfolio_policy_id: UUID, request_identity: str
    ) -> PortfolioProposalRecord | None:
        with self._pool.connection(read_only=True) as connection:
            row = _proposal_row(
                connection,
                "root.opportunity_set_id = %s AND root.portfolio_policy_id = %s AND root.request_identity = %s",
                (opportunity_set_id, portfolio_policy_id, request_identity),
                lock=False,
            )
        return None if row is None else _proposal_record(row)


class PostgresPortfolioDependencyRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_and_revalidate(self, prepared: PreparedPortfolioInputs, policy: PortfolioPolicyPlan) -> None:
        actual = _load_inputs(self._connection, prepared.opportunity_set_id, policy.portfolio_policy_id, lock=True)
        if actual != (prepared, policy):
            raise DecisionAuthorityIntegrityError("prepared Portfolio inputs changed before closure")


def _load_inputs(
    connection: psycopg.Connection[Any], opportunity_set_id: UUID, portfolio_policy_id: UUID, *, lock: bool
) -> tuple[PreparedPortfolioInputs, PortfolioPolicyPlan]:
    suffix = " FOR SHARE" if lock else ""
    root = connection.execute(
        """SELECT decision_run_id, strategy_version_id, content_sha256,
                  recorded_at, opportunity_count FROM mra.opportunity_set
           WHERE opportunity_set_id = %s"""
        + suffix,
        (opportunity_set_id,),
    ).fetchone()
    if root is None:
        raise DecisionAuthorityIntegrityError("OpportunitySet is absent")
    rows = connection.execute(
        """SELECT opportunity_id, ordinal, candidate_id, instrument_id,
                  target_definition_id, status, content_sha256
           FROM mra.opportunity WHERE opportunity_set_id = %s ORDER BY ordinal"""
        + suffix,
        (opportunity_set_id,),
    ).fetchall()
    if len(rows) != int(root[4]) or tuple(int(row[1]) for row in rows) != tuple(range(1, len(rows) + 1)):
        raise DecisionAuthorityIntegrityError("Opportunity roster is incomplete")
    prepared = PreparedPortfolioInputs(
        decision_run_id=UUID(str(root[0])),
        strategy_version_id=UUID(str(root[1])),
        opportunity_set_id=opportunity_set_id,
        opportunity_set_sha256=str(root[2]),
        opportunity_set_recorded_at=root[3],
        opportunities=tuple(
            PreparedPortfolioOpportunity(
                opportunity_id=UUID(str(row[0])),
                ordinal=int(row[1]),
                candidate_id=UUID(str(row[2])),
                instrument_id=UUID(str(row[3])),
                target_definition_id=UUID(str(row[4])),
                status=OpportunityStatus(str(row[5])),
                content_sha256=str(row[6]),
            )
            for row in rows
        ),
    )
    return prepared, _load_policy(connection, portfolio_policy_id, lock=lock)


def _load_policy(connection: psycopg.Connection[Any], portfolio_policy_id: UUID, *, lock: bool) -> PortfolioPolicyPlan:
    suffix = " FOR SHARE" if lock else ""
    row = connection.execute(
        """SELECT policy_code, version, supersedes_policy_id, allocation_method,
                  minimum_estimable_count, maximum_line_count,
                  maximum_single_weight, maximum_gross_weight, maximum_net_weight,
                  minimum_cash_weight, maximum_turnover, decimal_places,
                  code_artifact_id, code_content_sha256, code_size_bytes,
                  config_artifact_id, config_content_sha256, config_size_bytes,
                  provenance_sha256, content_sha256
           FROM mra.portfolio_policy WHERE portfolio_policy_id = %s"""
        + suffix,
        (portfolio_policy_id,),
    ).fetchone()
    if row is None:
        raise DecisionAuthorityIntegrityError("PortfolioPolicy is absent")
    plan = PortfolioPolicyPlan(
        portfolio_policy_id=portfolio_policy_id,
        policy_code=str(row[0]),
        version=int(row[1]),
        supersedes_policy_id=UUID(str(row[2])) if row[2] is not None else None,
        allocation_method=PortfolioAllocationMethod(str(row[3])),
        minimum_estimable_count=int(row[4]),
        maximum_line_count=int(row[5]),
        maximum_single_weight=Decimal(row[6]),
        maximum_gross_weight=Decimal(row[7]),
        maximum_net_weight=Decimal(row[8]),
        minimum_cash_weight=Decimal(row[9]),
        maximum_turnover=Decimal(row[10]),
        decimal_places=int(row[11]),
        code_artifact=DecisionArtifactBinding(UUID(str(row[12])), str(row[13]), int(row[14])),
        config_artifact=DecisionArtifactBinding(UUID(str(row[15])), str(row[16]), int(row[17])),
        provenance_sha256=str(row[18]),
    )
    if plan.content_sha256 != str(row[19]):
        raise DecisionAuthorityIntegrityError("PortfolioPolicy content is corrupt")
    return plan


__all__ = ["PostgresPortfolioDependencyRepository", "PostgresPortfolioInputPreparationProvider", "PostgresPortfolioQueryProvider"]
