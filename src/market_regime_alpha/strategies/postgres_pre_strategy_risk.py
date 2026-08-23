"""Typed PostgreSQL reload of facts consumed by pre-Strategy Risk."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.state_system.pool import DynamicStockPoolVersion
from market_regime_alpha.strategies.opportunity import (
    PreStrategyMarketFact,
    PreStrategyPositionFact,
    PreStrategyRiskFacts,
)


class PostgresPreStrategyRiskFactResolver:
    """Reload Account, Position, Pool and configured Risk owners at DecisionTime."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._decision = PostgresDecisionSystemRepository(factory)
        self._state = PostgresStateSystemRepository(
            factory,
            apply_migrations=False,
        )

    def resolve(
        self,
        *,
        candidates: CandidateSet,
        account_scope: str,
        decision_time: datetime,
        risk_limit_reference: RuntimeArtifactReference,
    ) -> PreStrategyRiskFacts:
        if risk_limit_reference.reference_kind != "DECISION_RISK_CONFIGURATION":
            raise ValueError("pre-Strategy Risk requires an exact configuration owner")
        run_id, tick_id = self._candidate_scope(candidates)
        pool_reference, pool_available_at = self._pool_reference(
            run_id=run_id,
            tick_id=tick_id,
        )
        pool_payload = self._state.read_pool(pool_reference.artifact_id)
        pool = DynamicStockPoolVersion.from_canonical_dict(pool_payload)
        if (
            pool.pool_hash != pool_reference.content_hash
            or pool.available_at != pool_available_at
            or pool.decision_time != decision_time
        ):
            raise ValueError("Dynamic Pool owner DecisionTime/hash drifted")

        account, reconciliation = self._decision.resolve_strategy_execution_account(
            account_id=account_scope,
            decision_time=decision_time,
        )
        configuration = self._decision.get_risk_configuration(
            risk_limit_reference.artifact_id
        )
        if configuration.configuration_hash != risk_limit_reference.content_hash:
            raise ValueError("Decision Risk Configuration owner hash drifted")
        configuration_created_at = self._risk_configuration_created_at(
            risk_limit_reference
        )
        available_at = max(
            account.as_of_time,
            reconciliation.as_of_time,
            pool.available_at,
            configuration_created_at,
        )
        if available_at > decision_time:
            raise ValueError("pre-Strategy owner fact is unavailable at DecisionTime")
        return PreStrategyRiskFacts(
            account_scope=account_scope,
            account_state_reference=RuntimeArtifactReference(
                "MANUAL_ACCOUNT_OBSERVATION",
                account.observation_id,
                account.content_hash,
            ),
            reconciliation_reference=RuntimeArtifactReference(
                "ACCOUNT_RECONCILIATION",
                reconciliation.reconciliation_id,
                reconciliation.content_hash,
            ),
            market_state_reference=pool_reference,
            risk_limit_reference=risk_limit_reference,
            decision_time=decision_time,
            available_at=available_at,
            total_equity=account.total_equity,
            available_cash=account.available_cash,
            positions=tuple(
                PreStrategyPositionFact(
                    item.symbol,
                    item.total_quantity,
                    item.available_quantity,
                    item.observed_market_value,
                )
                for item in account.positions
            ),
            market_facts=tuple(
                PreStrategyMarketFact(
                    item.symbol,
                    item.eligibility and item.included,
                    item.liquidity,
                    item.is_st,
                    item.suspended,
                )
                for item in pool.members
            ),
            maximum_single_symbol_weight=(
                configuration.maximum_single_symbol_weight
            ),
            minimum_liquidity=configuration.minimum_liquidity,
            daily_loss_limit=configuration.daily_loss_limit,
        )

    def _candidate_scope(self, candidates: CandidateSet) -> tuple[ArtifactId, ArtifactId]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT run_id, tick_id, payload_json
                FROM state_runtime_candidate_artifact
                WHERE candidate_id = %s AND candidate_hash = %s
                """,
                (
                    str(candidates.envelope.artifact_id),
                    candidates.envelope.content_hash,
                ),
            ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][2], Mapping):
            raise ValueError("Continuous Candidate owner scope is missing or ambiguous")
        restored = CandidateSet.from_canonical_dict(dict(rows[0][2]))
        if restored != candidates:
            raise ValueError("Continuous Candidate owner projection drifted")
        return ArtifactId(str(rows[0][0])), ArtifactId(str(rows[0][1]))

    def _pool_reference(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
    ) -> tuple[RuntimeArtifactReference, datetime]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, artifact_hash, available_at
                FROM state_research_stage_authority
                WHERE run_id = %s AND tick_id = %s AND stage = 'DYNAMIC_POOL'
                """,
                (str(run_id), str(tick_id)),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError("Dynamic Pool owner is missing or ambiguous")
        return (
            RuntimeArtifactReference(
                "DYNAMIC_STOCK_POOL",
                ArtifactId(str(rows[0][0])),
                str(rows[0][1]),
            ),
            rows[0][2],
        )

    def _risk_configuration_created_at(
        self,
        reference: RuntimeArtifactReference,
    ) -> datetime:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT created_at FROM decision_risk_configuration
                WHERE configuration_id = %s AND configuration_hash = %s
                """,
                (str(reference.artifact_id), reference.content_hash),
            ).fetchone()
        if row is None:
            raise KeyError(str(reference.artifact_id))
        return row[0]


__all__ = ["PostgresPreStrategyRiskFactResolver"]
