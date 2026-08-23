"""Typed PostgreSQL reload of facts consumed by pre-Strategy Risk."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
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
        positions = tuple(
            PreStrategyPositionFact(
                item.symbol,
                item.total_quantity,
                item.available_quantity,
                item.observed_market_value,
            )
            for item in account.positions
        )
        theme_exposures, theme_complete = _theme_exposures(
            candidates,
            positions,
            account.total_equity,
        )
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
            positions=positions,
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
            maximum_theme_weight=configuration.maximum_theme_weight,
            theme_exposures=theme_exposures,
            theme_exposure_complete=theme_complete,
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


class PostgresHistoricalPreStrategyRiskFactResolver:
    """Reload exact Historical Pool and explicitly bound Account/Risk owners."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        account_scope: str,
        account_state_references: tuple[RuntimeArtifactReference, ...],
        reconciliation_references: tuple[RuntimeArtifactReference, ...],
    ) -> None:
        if not account_scope:
            raise ValueError("Historical Risk requires one Account scope")
        if not account_state_references or any(
            item.reference_kind != "MANUAL_ACCOUNT_OBSERVATION"
            for item in account_state_references
        ):
            raise ValueError("Historical Risk requires exact Account Observation owners")
        if not reconciliation_references or any(
            item.reference_kind != "ACCOUNT_RECONCILIATION"
            for item in reconciliation_references
        ):
            raise ValueError("Historical Risk requires exact Reconciliation owners")
        self._factory = factory
        self._decision = PostgresDecisionSystemRepository(factory)
        self._components = PostgresHistoricalMaterializationRepository(
            factory,
            apply_migrations=False,
        )
        self._account_scope = account_scope
        self._account_references = frozenset(account_state_references)
        self._reconciliation_references = frozenset(reconciliation_references)

    def resolve(
        self,
        *,
        candidates: CandidateSet,
        account_scope: str,
        decision_time: datetime,
        risk_limit_reference: RuntimeArtifactReference,
    ) -> PreStrategyRiskFacts:
        if risk_limit_reference.reference_kind != "DECISION_RISK_CONFIGURATION":
            raise ValueError("Historical Risk requires an exact configuration owner")
        candidate_component = self._historical_candidate_component(candidates)
        pool_references = tuple(
            item
            for item in candidate_component.source_references
            if item.artifact_kind == "HISTORICAL_DYNAMIC_POOL"
        )
        if len(pool_references) != 1:
            raise ValueError("Historical Dynamic Pool owner is missing or ambiguous")
        pool = self._components.get(pool_references[0])
        if pool.component_kind is not HistoricalComponentKind.DYNAMIC_POOL:
            raise ValueError("Historical Dynamic Pool owner kind drifted")
        if account_scope != self._account_scope:
            raise ValueError("Historical Account scope drifted")
        account, reconciliation = self._decision.resolve_strategy_execution_account(
            account_id=account_scope,
            decision_time=decision_time,
        )
        account_reference = RuntimeArtifactReference(
            "MANUAL_ACCOUNT_OBSERVATION",
            account.observation_id,
            account.content_hash,
        )
        reconciliation_reference = RuntimeArtifactReference(
            "ACCOUNT_RECONCILIATION",
            reconciliation.reconciliation_id,
            reconciliation.content_hash,
        )
        if (
            account_reference not in self._account_references
            or reconciliation_reference not in self._reconciliation_references
        ):
            raise ValueError(
                "Historical session Account/Reconciliation is absent from frozen configuration"
            )
        configuration = self._decision.get_risk_configuration(
            risk_limit_reference.artifact_id
        )
        if configuration.configuration_hash != risk_limit_reference.content_hash:
            raise ValueError("Historical Risk configuration owner drifted")
        configuration_created_at = self._risk_configuration_created_at(
            risk_limit_reference
        )
        if max(
            account.as_of_time,
            reconciliation.as_of_time,
            pool.source_max_event_time,
            configuration_created_at,
        ) > decision_time:
            raise ValueError("Historical pre-Strategy owner is unavailable at DecisionTime")
        positions = tuple(
            PreStrategyPositionFact(
                item.symbol,
                item.total_quantity,
                item.available_quantity,
                item.observed_market_value,
            )
            for item in account.positions
        )
        theme_exposures, theme_complete = _theme_exposures(
            candidates,
            positions,
            account.total_equity,
        )
        return PreStrategyRiskFacts(
            account_scope=account_scope,
            account_state_reference=account_reference,
            reconciliation_reference=reconciliation_reference,
            market_state_reference=_runtime_reference(pool.reference),
            risk_limit_reference=risk_limit_reference,
            decision_time=decision_time,
            available_at=max(
                account.as_of_time,
                reconciliation.as_of_time,
                pool.source_max_event_time,
                configuration_created_at,
            ),
            total_equity=account.total_equity,
            available_cash=account.available_cash,
            positions=positions,
            market_facts=_historical_market_facts(pool.payload),
            maximum_single_symbol_weight=configuration.maximum_single_symbol_weight,
            maximum_theme_weight=configuration.maximum_theme_weight,
            theme_exposures=theme_exposures,
            theme_exposure_complete=theme_complete,
            minimum_liquidity=configuration.minimum_liquidity,
            daily_loss_limit=configuration.daily_loss_limit,
        )

    def _historical_candidate_component(
        self,
        candidates: CandidateSet,
    ) -> HistoricalSessionComponent:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT component_id, component_hash
                FROM historical_corpus_session_component
                WHERE component_kind = 'CANDIDATE'
                  AND payload_json->'payload'->'envelope'->>'artifact_id' = %s
                  AND payload_json->'payload'->'envelope'->>'content_hash' = %s
                """,
                (
                    str(candidates.envelope.artifact_id),
                    candidates.envelope.content_hash,
                ),
            ).fetchall()
        references = tuple(
            ValidationArtifactReference(
                "HISTORICAL_CANDIDATE",
                ArtifactId(str(row[0])),
                str(row[1]),
            )
            for row in rows
        )
        components = tuple(self._components.get(item) for item in references)
        exact = tuple(
            item
            for item in components
            if CandidateSet.from_canonical_dict(dict(item.payload)) == candidates
        )
        if len(exact) != 1:
            raise ValueError("Historical Candidate owner is missing or ambiguous")
        return exact[0]

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


def _theme_exposures(
    candidates: CandidateSet,
    positions: tuple[PreStrategyPositionFact, ...],
    total_equity: Decimal,
) -> tuple[tuple[tuple[str, Decimal], ...], bool]:
    if not positions:
        return (), True
    if total_equity <= 0:
        return (), False
    themes = {
        item.symbol: item.primary_theme_id
        for item in candidates.records
        if item.primary_theme_id is not None
    }
    if any(item.symbol not in themes for item in positions):
        return (), False
    exposures: dict[str, Decimal] = {}
    for position in positions:
        theme_id = themes[position.symbol]
        exposures[theme_id] = (
            exposures.get(theme_id, Decimal("0"))
            + position.observed_market_value / total_equity
        )
    return tuple(sorted(exposures.items())), True


def _historical_market_facts(
    payload: Mapping[str, object],
) -> tuple[PreStrategyMarketFact, ...]:
    raw = payload.get("universal_integrity")
    if not isinstance(raw, list):
        raise ValueError("Historical Dynamic Pool integrity facts are malformed")
    facts: list[PreStrategyMarketFact] = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("checks"), Mapping):
            raise ValueError("Historical Dynamic Pool integrity fact is malformed")
        checks = item["checks"]
        symbol = item.get("symbol")
        eligible = item.get("eligible")
        if not isinstance(symbol, str) or not isinstance(eligible, bool):
            raise ValueError("Historical Dynamic Pool eligibility is malformed")
        suspension_known = checks.get("suspension_known")
        not_suspended = checks.get("not_suspended")
        if not isinstance(suspension_known, bool) or (
            suspension_known and not isinstance(not_suspended, bool)
        ):
            raise ValueError("Historical Dynamic Pool suspension fact is malformed")
        facts.append(
            PreStrategyMarketFact(
                symbol=symbol,
                eligible=eligible,
                liquidity=None,
                is_st=None,
                suspended=(
                    None if not suspension_known else not not_suspended
                ),
            )
        )
    return tuple(sorted(facts, key=lambda item: item.symbol))


def _runtime_reference(
    reference: ValidationArtifactReference,
) -> RuntimeArtifactReference:
    return RuntimeArtifactReference(
        reference.artifact_kind,
        reference.artifact_id,
        reference.content_hash,
    )


__all__ = [
    "PostgresHistoricalPreStrategyRiskFactResolver",
    "PostgresPreStrategyRiskFactResolver",
]
