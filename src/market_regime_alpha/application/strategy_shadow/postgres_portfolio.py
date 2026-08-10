"""PostgreSQL owner for immutable Portfolio Shadow headers and day states."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowPortfolio,
    ShadowPortfolioDayState,
    ShadowPortfolioPolicy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class PostgresShadowPortfolioRepository:
    """Append-only Portfolio Shadow Authority with parent-row CAS fencing."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def save_portfolio(
        self, *, policy: ShadowPortfolioPolicy, portfolio: ShadowPortfolio
    ) -> ShadowPortfolio:
        if portfolio.policy_reference.artifact_id != policy.policy_id:
            raise ValueError("Portfolio Shadow Policy identity mismatch")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO strategy_shadow_portfolio(
                    portfolio_id, portfolio_hash, policy_id, policy_hash,
                    research_artifact_id, candidate_artifact_id, initial_cash,
                    policy_json, portfolio_json, real_order_authority,
                    real_fill_authority, real_position_authority, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    false, false, false, %s
                ) ON CONFLICT (portfolio_id) DO NOTHING
                """,
                (
                    str(portfolio.portfolio_id),
                    portfolio.portfolio_hash,
                    str(policy.policy_id),
                    policy.policy_hash,
                    str(portfolio.research_reference.artifact_id),
                    str(portfolio.candidate_reference.artifact_id),
                    portfolio.initial_cash,
                    Jsonb(policy.to_canonical_dict()),
                    Jsonb(portfolio.to_canonical_dict()),
                    portfolio.created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT portfolio_hash, policy_hash
                FROM strategy_shadow_portfolio WHERE portfolio_id = %s
                """,
                (str(portfolio.portfolio_id),),
            ).fetchone()
            if row is None or tuple(str(item) for item in row) != (
                portfolio.portfolio_hash,
                policy.policy_hash,
            ):
                raise ValueError("Portfolio Shadow immutable identity conflict")

        self._factory.run_transaction(operation)
        _stored_policy, stored_portfolio = self.get_portfolio(portfolio.portfolio_id)
        return stored_portfolio

    def append_state(
        self,
        state: ShadowPortfolioDayState,
        *,
        expected_previous_state_id: ArtifactId | None,
    ) -> ShadowPortfolioDayState:
        def operation(connection: Any) -> None:
            parent = connection.execute(
                """
                SELECT portfolio_hash FROM strategy_shadow_portfolio
                WHERE portfolio_id = %s FOR UPDATE
                """,
                (str(state.portfolio_reference.artifact_id),),
            ).fetchone()
            if parent is None or str(parent[0]) != state.portfolio_reference.content_hash:
                raise ValueError("Portfolio Shadow parent identity is unavailable")
            latest = connection.execute(
                """
                SELECT state_id, state_hash, sequence
                FROM strategy_shadow_portfolio_day
                WHERE portfolio_id = %s ORDER BY sequence DESC LIMIT 1
                """,
                (str(state.portfolio_reference.artifact_id),),
            ).fetchone()
            actual_previous = None if latest is None else ArtifactId(str(latest[0]))
            if actual_previous != expected_previous_state_id:
                if latest is not None and str(latest[0]) == str(state.state_id):
                    if str(latest[1]) != state.state_hash:
                        raise ValueError("Portfolio Shadow state identity conflict")
                    return
                raise ValueError("Portfolio Shadow PostgreSQL CAS conflict")
            expected_sequence = 1 if latest is None else int(latest[2]) + 1
            state_previous = (
                None
                if state.previous_state_reference is None
                else state.previous_state_reference.artifact_id
            )
            if state.sequence != expected_sequence or state_previous != actual_previous:
                raise ValueError("Portfolio Shadow state chain is not contiguous")
            connection.execute(
                """
                INSERT INTO strategy_shadow_portfolio_day(
                    state_id, state_hash, portfolio_id, previous_state_id,
                    sequence, trading_date, cash, nav, gross_exposure,
                    turnover, drawdown, total_cost, payload_json,
                    real_trading_mutation, recorded_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, false, %s
                )
                """,
                (
                    str(state.state_id),
                    state.state_hash,
                    str(state.portfolio_reference.artifact_id),
                    None if actual_previous is None else str(actual_previous),
                    state.sequence,
                    state.trading_date,
                    state.cash,
                    state.nav,
                    state.gross_exposure,
                    state.turnover,
                    state.drawdown,
                    state.total_cost,
                    Jsonb(state.to_canonical_dict()),
                    state.recorded_at,
                ),
            )

        self._factory.run_transaction(operation)
        return self.get_state(state.state_id)

    def get_portfolio(
        self, portfolio_id: ArtifactId
    ) -> tuple[ShadowPortfolioPolicy, ShadowPortfolio]:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT policy_json, portfolio_json
                FROM strategy_shadow_portfolio WHERE portfolio_id = %s
                """,
                (str(portfolio_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], dict) or not isinstance(row[1], dict):
            raise KeyError(str(portfolio_id))
        return (
            ShadowPortfolioPolicy.from_canonical_dict(row[0]),
            ShadowPortfolio.from_canonical_dict(row[1]),
        )

    def find_by_policy(
        self, policy_id: ArtifactId
    ) -> tuple[ShadowPortfolioPolicy, ShadowPortfolio] | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT portfolio_id FROM strategy_shadow_portfolio
                WHERE policy_id = %s
                """,
                (str(policy_id),),
            ).fetchone()
        if row is None:
            return None
        return self.get_portfolio(ArtifactId(str(row[0])))

    def get_state(self, state_id: ArtifactId) -> ShadowPortfolioDayState:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_shadow_portfolio_day
                WHERE state_id = %s
                """,
                (str(state_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], dict):
            raise KeyError(str(state_id))
        return ShadowPortfolioDayState.from_canonical_dict(row[0])

    def latest_state(
        self, portfolio_id: ArtifactId
    ) -> ShadowPortfolioDayState | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_shadow_portfolio_day
                WHERE portfolio_id = %s ORDER BY sequence DESC LIMIT 1
                """,
                (str(portfolio_id),),
            ).fetchone()
        if row is None:
            return None
        if not isinstance(row[0], dict):
            raise ValueError("Portfolio Shadow durable payload is invalid")
        return ShadowPortfolioDayState.from_canonical_dict(row[0])

    def replay(
        self, portfolio_id: ArtifactId
    ) -> tuple[ShadowPortfolioDayState, ...]:
        policy, portfolio = self.get_portfolio(portfolio_id)
        if portfolio.policy_reference.artifact_id != policy.policy_id:
            raise ValueError("Portfolio Shadow durable Policy chain is invalid")
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_shadow_portfolio_day
                WHERE portfolio_id = %s ORDER BY sequence
                """,
                (str(portfolio_id),),
            ).fetchall()
        states = tuple(
            ShadowPortfolioDayState.from_canonical_dict(_payload(row[0]))
            for row in rows
        )
        previous: ShadowPortfolioDayState | None = None
        for state in states:
            expected = None if previous is None else previous.state_id
            actual = (
                None
                if state.previous_state_reference is None
                else state.previous_state_reference.artifact_id
            )
            if state.sequence != (1 if previous is None else previous.sequence + 1):
                raise ValueError("Portfolio Shadow replay sequence is not contiguous")
            if actual != expected:
                raise ValueError("Portfolio Shadow replay predecessor is invalid")
            previous = state
        return states


def _payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Portfolio Shadow durable payload is invalid")
    return value


__all__ = ["PostgresShadowPortfolioRepository"]
