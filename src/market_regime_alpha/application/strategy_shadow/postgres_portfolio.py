"""PostgreSQL owner for immutable Portfolio Shadow headers and day states."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowPortfolio,
    ShadowPortfolioDayState,
    ShadowPortfolioPolicy,
)
from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ShadowObservationReceipt,
)
from market_regime_alpha.application.strategy_shadow.postgres_observations import (
    PostgresShadowObservationRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
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
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def save_portfolio(
        self, *, policy: ShadowPortfolioPolicy, portfolio: ShadowPortfolio
    ) -> ShadowPortfolio:
        if (
            portfolio.policy_reference.artifact_id != policy.policy_id
            or portfolio.policy_reference.content_hash != policy.policy_hash
        ):
            raise ValueError("Portfolio Shadow Policy identity mismatch")

        def operation(connection: Any) -> None:
            lineage_status = (
                "LEGACY_UNBOUND"
                if portfolio.strategy_reference is None
                else "EXACT_V1"
            )
            if lineage_status == "EXACT_V1":
                self._verify_exact_portfolio_owners(connection, portfolio)
            connection.execute(
                """
                INSERT INTO strategy_shadow_portfolio(
                    portfolio_id, portfolio_hash, policy_id, policy_hash,
                    research_artifact_id, candidate_artifact_id, initial_cash,
                    research_artifact_hash, candidate_artifact_hash,
                    strategy_session_id, strategy_session_hash, lineage_status,
                    policy_json, portfolio_json, real_order_authority,
                    real_fill_authority, real_position_authority, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
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
                    (
                        None
                        if lineage_status == "LEGACY_UNBOUND"
                        else portfolio.research_reference.content_hash
                    ),
                    (
                        None
                        if lineage_status == "LEGACY_UNBOUND"
                        else portfolio.candidate_reference.content_hash
                    ),
                    (
                        None
                        if portfolio.strategy_reference is None
                        else str(portfolio.strategy_reference.artifact_id)
                    ),
                    (
                        None
                        if portfolio.strategy_reference is None
                        else portfolio.strategy_reference.content_hash
                    ),
                    lineage_status,
                    Jsonb(policy.to_canonical_dict()),
                    Jsonb(portfolio.to_canonical_dict()),
                    portfolio.created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT portfolio_hash, policy_hash, research_artifact_hash,
                       candidate_artifact_hash, strategy_session_id,
                       strategy_session_hash, lineage_status
                FROM strategy_shadow_portfolio WHERE portfolio_id = %s
                """,
                (str(portfolio.portfolio_id),),
            ).fetchone()
            expected = (
                portfolio.portfolio_hash,
                policy.policy_hash,
                None
                if lineage_status == "LEGACY_UNBOUND"
                else portfolio.research_reference.content_hash,
                None
                if lineage_status == "LEGACY_UNBOUND"
                else portfolio.candidate_reference.content_hash,
                None
                if portfolio.strategy_reference is None
                else str(portfolio.strategy_reference.artifact_id),
                None
                if portfolio.strategy_reference is None
                else portfolio.strategy_reference.content_hash,
                lineage_status,
            )
            if row is None or tuple(
                None if item is None else str(item) for item in row
            ) != expected:
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
                SELECT portfolio_hash, lineage_status FROM strategy_shadow_portfolio
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
            if str(parent[1]) == "EXACT_V1":
                self._verify_state_source_owners(connection, state)
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
            for ordinal, reference in enumerate(state.source_references, start=1):
                connection.execute(
                    """
                    INSERT INTO strategy_shadow_portfolio_state_source_binding(
                        state_id, ordinal, artifact_kind, artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        str(state.state_id),
                        ordinal,
                        reference.artifact_kind,
                        str(reference.artifact_id),
                        reference.content_hash,
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
                SELECT policy_id, policy_hash, portfolio_hash, portfolio_json,
                       policy_json, lineage_status
                FROM strategy_shadow_portfolio WHERE portfolio_id = %s
                """,
                (str(portfolio_id),),
            ).fetchone()
        if row is None or not isinstance(row[3], dict) or not isinstance(row[4], dict):
            raise KeyError(str(portfolio_id))
        policy = ShadowPortfolioPolicy.from_canonical_dict(row[4])
        portfolio = ShadowPortfolio.from_canonical_dict(row[3])
        if (
            str(row[0]) != str(policy.policy_id)
            or str(row[1]) != policy.policy_hash
            or str(row[2]) != portfolio.portfolio_hash
            or portfolio.policy_reference.artifact_id != policy.policy_id
            or portfolio.policy_reference.content_hash != policy.policy_hash
        ):
            raise ValueError("Portfolio Shadow owner projection diverged")
        if str(row[5]) == "EXACT_V1":
            with self._factory.connection(read_only=True) as connection:
                self._verify_exact_portfolio_owners(connection, portfolio)
        elif portfolio.strategy_reference is not None:
            raise ValueError("Portfolio Shadow legacy lineage status drift")
        return policy, portfolio

    def find_exact(
        self,
        *,
        policy_reference: ValidationArtifactReference,
        research_reference: ValidationArtifactReference,
        candidate_reference: ValidationArtifactReference,
        strategy_reference: ValidationArtifactReference,
        initial_cash: Decimal,
    ) -> tuple[ShadowPortfolioPolicy, ShadowPortfolio] | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT portfolio_id FROM strategy_shadow_portfolio
                WHERE policy_id = %s AND policy_hash = %s
                  AND research_artifact_id = %s AND research_artifact_hash = %s
                  AND candidate_artifact_id = %s AND candidate_artifact_hash = %s
                  AND strategy_session_id = %s AND strategy_session_hash = %s
                  AND initial_cash = %s AND lineage_status = 'EXACT_V1'
                """,
                (
                    str(policy_reference.artifact_id),
                    policy_reference.content_hash,
                    str(research_reference.artifact_id),
                    research_reference.content_hash,
                    str(candidate_reference.artifact_id),
                    candidate_reference.content_hash,
                    str(strategy_reference.artifact_id),
                    strategy_reference.content_hash,
                    initial_cash,
                ),
            ).fetchone()
        if row is None:
            return None
        return self.get_portfolio(ArtifactId(str(row[0])))

    def get_state(self, state_id: ArtifactId) -> ShadowPortfolioDayState:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT state_hash, portfolio_id, payload_json, recorded_at
                FROM strategy_shadow_portfolio_day
                WHERE state_id = %s
                """,
                (str(state_id),),
            ).fetchone()
        if row is None or not isinstance(row[2], dict):
            raise KeyError(str(state_id))
        state = ShadowPortfolioDayState.from_canonical_dict(row[2])
        if (
            str(row[0]) != state.state_hash
            or str(row[1]) != str(state.portfolio_reference.artifact_id)
            or row[3] != state.recorded_at
        ):
            raise ValueError("Portfolio Shadow State owner projection diverged")
        with self._factory.connection(read_only=True) as connection:
            self._verify_state_source_projection(connection, state)
        return state

    def latest_state(
        self, portfolio_id: ArtifactId
    ) -> ShadowPortfolioDayState | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT state_id FROM strategy_shadow_portfolio_day
                WHERE portfolio_id = %s ORDER BY sequence DESC LIMIT 1
                """,
                (str(portfolio_id),),
            ).fetchone()
        if row is None:
            return None
        return self.get_state(ArtifactId(str(row[0])))

    def replay(
        self, portfolio_id: ArtifactId
    ) -> tuple[ShadowPortfolioDayState, ...]:
        policy, portfolio = self.get_portfolio(portfolio_id)
        if (
            portfolio.policy_reference.artifact_id != policy.policy_id
            or portfolio.policy_reference.content_hash != policy.policy_hash
        ):
            raise ValueError("Portfolio Shadow durable Policy chain is invalid")
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT state_id FROM strategy_shadow_portfolio_day
                WHERE portfolio_id = %s ORDER BY sequence
                """,
                (str(portfolio_id),),
            ).fetchall()
        states = tuple(self.get_state(ArtifactId(str(row[0]))) for row in rows)
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
            with self._factory.connection(read_only=True) as connection:
                self._verify_state_source_projection(connection, state)
            previous = state
        return states

    @staticmethod
    def _verify_exact_portfolio_owners(connection: Any, portfolio: ShadowPortfolio) -> None:
        assert portfolio.strategy_reference is not None
        panel = connection.execute(
            "SELECT panel_hash, created_at FROM research_evaluation_panel_v2 "
            "WHERE panel_id = %s",
            (str(portfolio.research_reference.artifact_id),),
        ).fetchone()
        candidate = connection.execute(
            "SELECT candidate_hash, created_at FROM state_runtime_candidate_artifact "
            "WHERE candidate_id = %s",
            (str(portfolio.candidate_reference.artifact_id),),
        ).fetchone()
        strategy = connection.execute(
            "SELECT session_hash, updated_at, lineage_status "
            "FROM strategy_shadow_session "
            "WHERE session_id = %s",
            (str(portfolio.strategy_reference.artifact_id),),
        ).fetchone()
        if (
            panel is None
            or str(panel[0]) != portfolio.research_reference.content_hash
            or candidate is None
            or str(candidate[0]) != portfolio.candidate_reference.content_hash
            or strategy is None
            or str(strategy[0]) != portfolio.strategy_reference.content_hash
            or str(strategy[2]) != "EXACT_V1"
            or portfolio.created_at < max(panel[1], candidate[1], strategy[1])
        ):
            raise ValueError("Portfolio Shadow exact owner identity/time mismatch")

    @staticmethod
    def _verify_state_source_projection(
        connection: Any,
        state: ShadowPortfolioDayState,
    ) -> None:
        parent = connection.execute(
            "SELECT portfolio_hash, lineage_status FROM strategy_shadow_portfolio "
            "WHERE portfolio_id = %s",
            (str(state.portfolio_reference.artifact_id),),
        ).fetchone()
        if parent is None or str(parent[0]) != state.portfolio_reference.content_hash:
            raise ValueError("Portfolio Shadow State parent owner mismatch")
        rows = connection.execute(
            """
            SELECT artifact_kind, artifact_id, content_hash
            FROM strategy_shadow_portfolio_state_source_binding
            WHERE state_id = %s ORDER BY ordinal
            """,
            (str(state.state_id),),
        ).fetchall()
        actual = [tuple(str(item) for item in row) for row in rows]
        expected = [
            (item.artifact_kind, str(item.artifact_id), item.content_hash)
            for item in state.source_references
        ]
        if actual != expected and not (
            str(parent[1]) == "LEGACY_UNBOUND" and not actual
        ):
            raise ValueError("Portfolio Shadow State source projection diverged")
        if str(parent[1]) == "LEGACY_UNBOUND":
            return
        PostgresShadowPortfolioRepository._verify_state_source_owners(
            connection,
            state,
        )

    @staticmethod
    def _verify_state_source_owners(
        connection: Any,
        state: ShadowPortfolioDayState,
    ) -> None:
        required_kinds = {
            "RESEARCH_PANEL_V2",
            "CANDIDATE_SET",
            "PORTFOLIO_SHADOW_MARKET_OBSERVATION",
            "SHADOW_OBSERVATION_RECEIPT",
        }
        kinds = {item.artifact_kind for item in state.source_references}
        if not required_kinds.issubset(kinds):
            raise ValueError("Portfolio Shadow State exact owner chain is incomplete")
        receipts = tuple(
            item for item in state.source_references
            if item.artifact_kind == "SHADOW_OBSERVATION_RECEIPT"
        )
        if len(receipts) != 1:
            raise ValueError("Portfolio Shadow Observation receipt is not unique")
        for reference in state.source_references:
            if reference.artifact_kind == "RESEARCH_PANEL_V2":
                owner = connection.execute(
                    "SELECT panel_hash, created_at FROM research_evaluation_panel_v2 "
                    "WHERE panel_id = %s",
                    (str(reference.artifact_id),),
                ).fetchone()
                PostgresShadowPortfolioRepository._require_timed_owner(
                    reference, owner, state.recorded_at, "Panel"
                )
            elif reference.artifact_kind == "CANDIDATE_SET":
                owner = connection.execute(
                    "SELECT candidate_hash, created_at "
                    "FROM state_runtime_candidate_artifact WHERE candidate_id = %s",
                    (str(reference.artifact_id),),
                ).fetchone()
                PostgresShadowPortfolioRepository._require_timed_owner(
                    reference, owner, state.recorded_at, "Candidate"
                )
            elif reference.artifact_kind == "PORTFOLIO_SHADOW_MARKET_OBSERVATION":
                owner = connection.execute(
                    "SELECT artifact_hash, created_at FROM research_validation_artifact "
                    "WHERE artifact_id = %s AND artifact_kind = %s",
                    (str(reference.artifact_id), reference.artifact_kind),
                ).fetchone()
                PostgresShadowPortfolioRepository._require_timed_owner(
                    reference, owner, state.recorded_at, "market observation"
                )
            elif reference.artifact_kind == "SHADOW_OBSERVATION_RECEIPT":
                owner = connection.execute(
                    "SELECT receipt_hash, payload_json, observed_at "
                    "FROM shadow_observation_receipt WHERE receipt_id = %s",
                    (str(reference.artifact_id),),
                ).fetchone()
                if owner is None or not isinstance(owner[1], dict):
                    raise ValueError("Portfolio Shadow Observation receipt owner mismatch")
                receipt = ShadowObservationReceipt.from_canonical_dict(owner[1])
                if (
                    receipt.receipt_hash != reference.content_hash
                    or str(owner[0]) != reference.content_hash
                    or state.recorded_at < owner[2]
                ):
                    raise ValueError("Portfolio Shadow Observation receipt owner mismatch")
                PostgresShadowObservationRepository._verify_projections(
                    connection, receipt
                )
                PostgresShadowObservationRepository._verify_typed_owner_chain(
                    connection, receipt
                )
            else:
                raise ValueError(
                    "Portfolio Shadow State contains unsupported exact owner kind"
                )

    @staticmethod
    def _require_timed_owner(
        reference: ValidationArtifactReference,
        owner: Any,
        recorded_at: Any,
        label: str,
    ) -> None:
        if (
            owner is None
            or str(owner[0]) != reference.content_hash
            or recorded_at < owner[1]
        ):
            raise ValueError(f"Portfolio Shadow {label} owner mismatch")

__all__ = ["PostgresShadowPortfolioRepository"]
