"""PostgreSQL persistence for canonical multi-Strategy business facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.execution.manual import (
    ManualTradeAuthorityRoute,
    ManualTradeRecord,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.persistence.postgres.native_repository import (
    acquire_scope_lock,
)
from market_regime_alpha.strategies.contracts import (
    MultiStrategyCycle,
    StrategyContract,
    StrategyDecisionPrice,
    StrategyProposal,
    StrategyRegistry,
    StrategyVersion,
)
from market_regime_alpha.strategies.feedback import (
    StrategyFeedbackArtifact,
    StrategyFeedbackKind,
    StrategyFeedbackStatus,
)
from market_regime_alpha.strategies.path_outcomes import StrategyPathOutcome
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioDecision,
)
from market_regime_alpha.strategies.sleeves import (
    FillAllocation,
    FillAllocationBatch,
)


class PostgresMultiStrategyRepository:
    """One transactional owner for Strategy facts; it is not a Runtime plane."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def register(
        self,
        registry: StrategyRegistry,
        *,
        created_at: datetime,
    ) -> StrategyRegistry:
        def operation(connection: Any) -> None:
            strategy_ids = {contract.contract_id: contract.strategy_id for contract in registry.contracts}
            for contract in registry.contracts:
                payload = contract.to_canonical_dict()
                connection.execute(
                    """
                    INSERT INTO strategy_contract(
                        contract_id, contract_hash, strategy_id, family,
                        semantic_version, payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (contract_id) DO NOTHING
                    """,
                    (
                        str(contract.contract_id),
                        contract.contract_hash,
                        str(contract.strategy_id),
                        contract.family.value,
                        contract.semantic_version,
                        Jsonb(payload),
                        created_at,
                    ),
                )
                _require_stored_payload(
                    connection,
                    table="strategy_contract",
                    id_column="contract_id",
                    identity=str(contract.contract_id),
                    hash_column="contract_hash",
                    expected_hash=contract.contract_hash,
                    expected_payload=payload,
                )
            for version in registry.versions:
                contract_id = version.contract_reference.artifact_id
                payload = version.to_canonical_dict()
                connection.execute(
                    """
                    INSERT INTO strategy_version(
                        version_id, version_hash, contract_id, contract_hash,
                        strategy_id, family, semantic_version,
                        lifecycle_status, research_status,
                        production_authorized, payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                              false, %s, %s)
                    ON CONFLICT (version_id) DO NOTHING
                    """,
                    (
                        str(version.version_id),
                        version.version_hash,
                        str(contract_id),
                        version.contract_reference.content_hash,
                        str(strategy_ids[contract_id]),
                        version.family.value,
                        version.semantic_version,
                        version.lifecycle_status,
                        version.research_status,
                        Jsonb(payload),
                        created_at,
                    ),
                )
                _require_stored_payload(
                    connection,
                    table="strategy_version",
                    id_column="version_id",
                    identity=str(version.version_id),
                    hash_column="version_hash",
                    expected_hash=version.version_hash,
                    expected_payload=payload,
                )

        self._factory.run_transaction(operation)
        return self.load_registry()

    def load_registry(self) -> StrategyRegistry:
        with self._factory.connection(read_only=True) as connection:
            contract_rows = connection.execute("SELECT payload_json FROM strategy_contract ORDER BY contract_id").fetchall()
            version_rows = connection.execute("SELECT payload_json FROM strategy_version ORDER BY version_id").fetchall()
        return StrategyRegistry.create(
            contracts=tuple(StrategyContract.from_canonical_dict(_payload(row[0])) for row in contract_rows),
            versions=tuple(StrategyVersion.from_canonical_dict(_payload(row[0])) for row in version_rows),
        )

    def save_cycle(self, cycle: MultiStrategyCycle) -> MultiStrategyCycle:
        def operation(connection: Any) -> None:
            runtime_input = cycle.runtime_input
            payload = cycle.to_canonical_dict()
            acquire_scope_lock(
                connection,
                namespace="multi-strategy-cycle",
                identity=cycle.cycle_id,
            )
            connection.execute(
                """
                INSERT INTO multi_strategy_cycle(
                    cycle_id, cycle_hash, origin, authority_mode,
                    parent_run_id, parent_run_hash,
                    parent_tick_id, parent_tick_hash,
                    candidate_artifact_id, candidate_artifact_hash,
                    dataset_id, dataset_hash, decision_time, input_hash,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (cycle_id) DO NOTHING
                """,
                (
                    str(cycle.cycle_id),
                    cycle.cycle_hash,
                    runtime_input.origin.value,
                    runtime_input.authority_mode.value,
                    str(runtime_input.parent_run_reference.artifact_id),
                    runtime_input.parent_run_reference.content_hash,
                    str(runtime_input.parent_tick_reference.artifact_id),
                    runtime_input.parent_tick_reference.content_hash,
                    str(runtime_input.candidate_set.envelope.artifact_id),
                    runtime_input.candidate_set.envelope.content_hash,
                    str(runtime_input.dataset_reference.artifact_id),
                    runtime_input.dataset_reference.content_hash,
                    runtime_input.decision_time,
                    runtime_input.input_hash,
                    Jsonb(payload),
                    cycle.created_at,
                ),
            )
            _require_stored_payload(
                connection,
                table="multi_strategy_cycle",
                id_column="cycle_id",
                identity=str(cycle.cycle_id),
                hash_column="cycle_hash",
                expected_hash=cycle.cycle_hash,
                expected_payload=payload,
            )
            for run in cycle.runs:
                run_payload = run.to_canonical_dict()
                connection.execute(
                    """
                    INSERT INTO strategy_run(
                        run_id, run_hash, cycle_id, cycle_hash,
                        strategy_version_id, strategy_version_hash,
                        status, payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                    (
                        str(run.run_id),
                        run.run_hash,
                        str(cycle.cycle_id),
                        cycle.cycle_hash,
                        str(run.strategy_version_reference.artifact_id),
                        run.strategy_version_reference.content_hash,
                        run.status.value,
                        Jsonb(run_payload),
                        cycle.created_at,
                    ),
                )
                _require_stored_payload(
                    connection,
                    table="strategy_run",
                    id_column="run_id",
                    identity=str(run.run_id),
                    hash_column="run_hash",
                    expected_hash=run.run_hash,
                    expected_payload=run_payload,
                )
                for gate in run.gate_attributions:
                    gate_payload = gate.to_canonical_dict()
                    gate_id = f"strategy-gate:{canonical_hash({'run_id': str(run.run_id), 'gate': gate_payload})[7:]}"
                    connection.execute(
                        """
                        INSERT INTO strategy_gate_attribution(
                            gate_id, run_id, symbol, eligibility_status,
                            candidate_status, action, payload_json, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (gate_id) DO NOTHING
                        """,
                        (
                            gate_id,
                            str(run.run_id),
                            gate.symbol,
                            gate.eligibility_status.value,
                            gate.candidate_status,
                            gate.action.value,
                            Jsonb(gate_payload),
                            cycle.created_at,
                        ),
                    )
                    _require_stored_payload(
                        connection,
                        table="strategy_gate_attribution",
                        id_column="gate_id",
                        identity=gate_id,
                        hash_column=None,
                        expected_hash=None,
                        expected_payload=gate_payload,
                    )
                for proposal in run.proposals:
                    proposal_payload = proposal.to_canonical_dict()
                    connection.execute(
                        """
                        INSERT INTO strategy_proposal(
                            proposal_id, proposal_hash, run_id,
                            strategy_version_id, strategy_version_hash,
                            symbol, action, desired_weight, payload_json, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (proposal_id) DO NOTHING
                        """,
                        (
                            str(proposal.proposal_id),
                            proposal.proposal_hash,
                            str(run.run_id),
                            str(proposal.strategy_version_reference.artifact_id),
                            proposal.strategy_version_reference.content_hash,
                            proposal.symbol,
                            proposal.action.value,
                            proposal.desired_weight,
                            Jsonb(proposal_payload),
                            cycle.created_at,
                        ),
                    )
                    _require_stored_payload(
                        connection,
                        table="strategy_proposal",
                        id_column="proposal_id",
                        identity=str(proposal.proposal_id),
                        hash_column="proposal_hash",
                        expected_hash=proposal.proposal_hash,
                        expected_payload=proposal_payload,
                    )

        self._factory.run_transaction(operation)
        return self.get_cycle(cycle.cycle_id)

    def get_cycle(self, cycle_id: ArtifactId) -> MultiStrategyCycle:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM multi_strategy_cycle WHERE cycle_id = %s",
                (str(cycle_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(cycle_id))
            cycle = MultiStrategyCycle.from_canonical_dict(_payload(row[0]))
            _verify_cycle_children(connection, cycle)
        return cycle

    def get_cycle_for_tick(
        self,
        *,
        run_id: ArtifactId,
        tick_id: ArtifactId,
    ) -> MultiStrategyCycle:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT cycle_id FROM multi_strategy_cycle
                WHERE parent_run_id = %s AND parent_tick_id = %s
                """,
                (str(run_id), str(tick_id)),
            ).fetchone()
        if row is None:
            raise KeyError(f"{run_id}:{tick_id}")
        return self.get_cycle(ArtifactId(str(row[0])))

    def get_proposal(self, proposal_id: ArtifactId) -> StrategyProposal:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM strategy_proposal WHERE proposal_id = %s",
                (str(proposal_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(proposal_id))
        return StrategyProposal.from_canonical_dict(_payload(row[0]))

    def get_proposal_decision_time(self, proposal_id: ArtifactId) -> datetime:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT c.decision_time
                FROM strategy_proposal AS p
                JOIN strategy_run AS r ON r.run_id = p.run_id
                JOIN multi_strategy_cycle AS c ON c.cycle_id = r.cycle_id
                WHERE p.proposal_id = %s
                """,
                (str(proposal_id),),
            ).fetchone()
        if row is None or not isinstance(row[0], datetime):
            raise KeyError(str(proposal_id))
        return row[0]

    def get_proposal_decision_price(
        self, proposal_id: ArtifactId
    ) -> StrategyDecisionPrice:
        proposal = self.get_proposal(proposal_id)
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT c.cycle_id
                FROM strategy_proposal AS p
                JOIN strategy_run AS r ON r.run_id = p.run_id
                JOIN multi_strategy_cycle AS c ON c.cycle_id = r.cycle_id
                WHERE p.proposal_id = %s
                """,
                (str(proposal_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(proposal_id))
        cycle = self.get_cycle(ArtifactId(str(row[0])))
        prices = cycle.runtime_input.decision_prices
        if prices is None:
            raise ValueError(
                "DATA_INSUFFICIENT: legacy Strategy cycle has no Price owner"
            )
        matches = tuple(item for item in prices if item.symbol == proposal.symbol)
        if len(matches) != 1:
            raise ValueError("DATA_INSUFFICIENT: Strategy Price owner is not exact")
        return matches[0]

    def save_portfolio(
        self,
        decision: CrossStrategyPortfolioDecision,
        *,
        created_at: datetime,
    ) -> CrossStrategyPortfolioDecision:
        def operation(connection: Any) -> None:
            payload = decision.to_canonical_dict()
            connection.execute(
                """
                INSERT INTO cross_strategy_portfolio_decision(
                    decision_id, decision_hash, cycle_id, cycle_hash,
                    status, gross_accepted_weight, production_authorized,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, false, %s, %s)
                ON CONFLICT (decision_id) DO NOTHING
                """,
                (
                    str(decision.decision_id),
                    decision.decision_hash,
                    str(decision.cycle_reference.artifact_id),
                    decision.cycle_reference.content_hash,
                    decision.status.value,
                    decision.gross_accepted_weight,
                    Jsonb(payload),
                    created_at,
                ),
            )
            _require_stored_payload(
                connection,
                table="cross_strategy_portfolio_decision",
                id_column="decision_id",
                identity=str(decision.decision_id),
                hash_column="decision_hash",
                expected_hash=decision.decision_hash,
                expected_payload=payload,
            )
            for line in decision.lines:
                _require_proposal_version(
                    connection,
                    proposal_id=line.proposal_reference.artifact_id,
                    proposal_hash=line.proposal_reference.content_hash,
                    strategy_version_id=line.strategy_version_reference.artifact_id,
                    strategy_version_hash=line.strategy_version_reference.content_hash,
                )
                line_payload = line.to_canonical_dict()
                line_id = f"cross-strategy-line:{canonical_hash({'decision_id': str(decision.decision_id), 'line': line_payload})[7:]}"
                connection.execute(
                    """
                    INSERT INTO cross_strategy_portfolio_line(
                        line_id, decision_id, proposal_id, proposal_hash,
                        strategy_version_id, strategy_version_hash,
                        symbol, requested_weight,
                        accepted_weight, payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (line_id) DO NOTHING
                    """,
                    (
                        line_id,
                        str(decision.decision_id),
                        str(line.proposal_reference.artifact_id),
                        line.proposal_reference.content_hash,
                        str(line.strategy_version_reference.artifact_id),
                        line.strategy_version_reference.content_hash,
                        line.symbol,
                        line.requested_weight,
                        line.accepted_weight,
                        Jsonb(line_payload),
                        created_at,
                    ),
                )
                _require_stored_payload(
                    connection,
                    table="cross_strategy_portfolio_line",
                    id_column="line_id",
                    identity=line_id,
                    hash_column=None,
                    expected_hash=None,
                    expected_payload=line_payload,
                )

        self._factory.run_transaction(operation)
        return self.get_portfolio(decision.decision_id)

    def get_portfolio(self, decision_id: ArtifactId) -> CrossStrategyPortfolioDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM cross_strategy_portfolio_decision
                WHERE decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        return CrossStrategyPortfolioDecision.from_canonical_dict(_payload(row[0]))

    def save_fill_allocation(self, batch: FillAllocationBatch) -> FillAllocationBatch:
        def operation(connection: Any) -> None:
            acquire_scope_lock(
                connection,
                namespace="strategy-execution-account",
                identity=batch.account_id,
            )
            fill_row = connection.execute(
                "SELECT fill_json FROM manual_fills WHERE fill_id = %s",
                (str(batch.source_fill_id),),
            ).fetchone()
            if fill_row is None:
                raise ValueError("Fill Allocation requires persisted observed Fill")
            stored_fill = json.loads(str(fill_row[0]))
            if canonical_hash(stored_fill) != batch.source_fill_hash:
                raise ValueError("observed Fill hash differs from allocation lineage")
            payload = batch.to_canonical_dict()
            connection.execute(
                """
                INSERT INTO strategy_fill_allocation_batch(
                    batch_id, batch_hash, source_fill_id, source_fill_hash,
                    correction_of_fill_id, account_id, symbol, side, quantity,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (batch_id) DO NOTHING
                """,
                (
                    str(batch.batch_id),
                    batch.batch_hash,
                    str(batch.source_fill_id),
                    batch.source_fill_hash,
                    (None if batch.correction_of_fill_id is None else str(batch.correction_of_fill_id)),
                    batch.account_id,
                    batch.symbol,
                    batch.side.value,
                    batch.quantity,
                    Jsonb(payload),
                    batch.recorded_at,
                ),
            )
            _require_stored_payload(
                connection,
                table="strategy_fill_allocation_batch",
                id_column="batch_id",
                identity=str(batch.batch_id),
                hash_column="batch_hash",
                expected_hash=batch.batch_hash,
                expected_payload=payload,
            )
            for allocation in batch.allocations:
                _require_proposal_version(
                    connection,
                    proposal_id=allocation.proposal_reference.artifact_id,
                    proposal_hash=allocation.proposal_reference.content_hash,
                    strategy_version_id=(
                        allocation.strategy_version_reference.artifact_id
                    ),
                    strategy_version_hash=(
                        allocation.strategy_version_reference.content_hash
                    ),
                )
                _require_executable_allocation(
                    connection,
                    batch=batch,
                    allocation=allocation,
                )
                allocation_payload = allocation.to_canonical_dict()
                connection.execute(
                    """
                    INSERT INTO strategy_fill_allocation(
                        allocation_id, allocation_hash, batch_id,
                        strategy_version_id, strategy_version_hash,
                        proposal_id, proposal_hash, allocated_quantity,
                        payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (allocation_id) DO NOTHING
                    """,
                    (
                        str(allocation.allocation_id),
                        allocation.allocation_hash,
                        str(batch.batch_id),
                        str(allocation.strategy_version_reference.artifact_id),
                        allocation.strategy_version_reference.content_hash,
                        str(allocation.proposal_reference.artifact_id),
                        allocation.proposal_reference.content_hash,
                        allocation.allocated_quantity,
                        Jsonb(allocation_payload),
                        batch.recorded_at,
                    ),
                )
                _require_stored_payload(
                    connection,
                    table="strategy_fill_allocation",
                    id_column="allocation_id",
                    identity=str(allocation.allocation_id),
                    hash_column="allocation_hash",
                    expected_hash=allocation.allocation_hash,
                    expected_payload=allocation_payload,
                )

        self._factory.run_transaction(operation)
        return self.get_fill_allocation(batch.batch_id)

    def get_fill_allocation(self, batch_id: ArtifactId) -> FillAllocationBatch:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_fill_allocation_batch
                WHERE batch_id = %s
                """,
                (str(batch_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(batch_id))
        return FillAllocationBatch.from_canonical_dict(_payload(row[0]))

    def list_fill_allocations(self, *, account_id: str) -> tuple[FillAllocationBatch, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_fill_allocation_batch
                WHERE account_id = %s ORDER BY created_at, batch_id
                """,
                (account_id,),
            ).fetchall()
        return tuple(FillAllocationBatch.from_canonical_dict(_payload(row[0])) for row in rows)

    def save_path_outcome(self, outcome: StrategyPathOutcome) -> StrategyPathOutcome:
        def operation(connection: Any) -> None:
            _require_path_outcome_lineage(connection, outcome)
            payload = outcome.to_canonical_dict()
            connection.execute(
                """
                INSERT INTO strategy_path_outcome(
                    outcome_id, outcome_hash, strategy_run_id,
                    strategy_run_hash, strategy_version_id,
                    strategy_version_hash, dataset_id, dataset_hash,
                    target_id, target_hash, symbol, decision_time,
                    horizon_sessions, mfe, mae, barrier_ordering,
                    payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (outcome_id) DO NOTHING
                """,
                (
                    str(outcome.outcome_id),
                    outcome.outcome_hash,
                    str(outcome.strategy_run_reference.artifact_id),
                    outcome.strategy_run_reference.content_hash,
                    str(outcome.strategy_version_reference.artifact_id),
                    outcome.strategy_version_reference.content_hash,
                    str(outcome.dataset_reference.artifact_id),
                    outcome.dataset_reference.content_hash,
                    str(outcome.target_reference.artifact_id),
                    outcome.target_reference.content_hash,
                    outcome.symbol,
                    outcome.decision_time,
                    outcome.horizon_sessions,
                    outcome.mfe,
                    outcome.mae,
                    outcome.barrier_ordering.value,
                    Jsonb(payload),
                    outcome.measured_at,
                ),
            )
            _require_stored_payload(
                connection,
                table="strategy_path_outcome",
                id_column="outcome_id",
                identity=str(outcome.outcome_id),
                hash_column="outcome_hash",
                expected_hash=outcome.outcome_hash,
                expected_payload=payload,
            )

        self._factory.run_transaction(operation)
        return self.get_path_outcome(outcome.outcome_id)

    def get_path_outcome(self, outcome_id: ArtifactId) -> StrategyPathOutcome:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM strategy_path_outcome WHERE outcome_id = %s",
                (str(outcome_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(outcome_id))
        return StrategyPathOutcome.from_canonical_dict(_payload(row[0]))

    def list_path_outcomes(
        self,
        *,
        strategy_version_id: ArtifactId,
    ) -> tuple[StrategyPathOutcome, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM strategy_path_outcome
                WHERE strategy_version_id = %s
                ORDER BY decision_time, outcome_id
                """,
                (str(strategy_version_id),),
            ).fetchall()
        return tuple(StrategyPathOutcome.from_canonical_dict(_payload(row[0])) for row in rows)

    def save_feedback(
        self,
        artifact: StrategyFeedbackArtifact,
    ) -> StrategyFeedbackArtifact:
        def operation(connection: Any) -> None:
            _require_feedback_lineage(connection, artifact)
            payload = artifact.to_canonical_dict()
            connection.execute(
                """
                INSERT INTO strategy_feedback_artifact(
                    artifact_id, artifact_hash, artifact_kind,
                    strategy_version_id, strategy_version_hash,
                    source_artifact_ids, status, production_authorized,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, false, %s, %s)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                (
                    str(artifact.artifact_id),
                    artifact.artifact_hash,
                    artifact.artifact_kind.value,
                    str(artifact.strategy_version_reference.artifact_id),
                    artifact.strategy_version_reference.content_hash,
                    [str(item.artifact_id) for item in artifact.source_references],
                    artifact.status.value,
                    Jsonb(payload),
                    artifact.created_at,
                ),
            )
            _require_stored_payload(
                connection,
                table="strategy_feedback_artifact",
                id_column="artifact_id",
                identity=str(artifact.artifact_id),
                hash_column="artifact_hash",
                expected_hash=artifact.artifact_hash,
                expected_payload=payload,
            )

        self._factory.run_transaction(operation)
        return self.get_feedback(artifact.artifact_id)

    def get_feedback(self, artifact_id: ArtifactId) -> StrategyFeedbackArtifact:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM strategy_feedback_artifact
                WHERE artifact_id = %s
                """,
                (str(artifact_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(artifact_id))
        return StrategyFeedbackArtifact.from_canonical_dict(_payload(row[0]))

    def list_feedback(
        self,
        *,
        strategy_version_id: ArtifactId,
        artifact_kind: StrategyFeedbackKind | None = None,
    ) -> tuple[StrategyFeedbackArtifact, ...]:
        parameters: tuple[object, ...] = (str(strategy_version_id),)
        kind_clause = ""
        if artifact_kind is not None:
            kind_clause = " AND artifact_kind = %s"
            parameters = (*parameters, artifact_kind.value)
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json FROM strategy_feedback_artifact
                WHERE strategy_version_id = %s{kind_clause}
                ORDER BY created_at, artifact_id
                """,
                parameters,
            ).fetchall()
        return tuple(StrategyFeedbackArtifact.from_canonical_dict(_payload(row[0])) for row in rows)


def _verify_cycle_children(connection: Any, cycle: MultiStrategyCycle) -> None:
    run_rows = connection.execute(
        "SELECT payload_json FROM strategy_run WHERE cycle_id = %s ORDER BY run_id",
        (str(cycle.cycle_id),),
    ).fetchall()
    stored_runs = tuple(_payload(row[0]) for row in run_rows)
    expected_runs = tuple(item.to_canonical_dict() for item in sorted(cycle.runs, key=lambda run: str(run.run_id)))
    if stored_runs != expected_runs:
        raise ValueError("Strategy Cycle child Run projection mismatch")
    for run in cycle.runs:
        gate_rows = connection.execute(
            """
            SELECT payload_json FROM strategy_gate_attribution
            WHERE run_id = %s ORDER BY symbol
            """,
            (str(run.run_id),),
        ).fetchall()
        proposal_rows = connection.execute(
            """
            SELECT payload_json FROM strategy_proposal
            WHERE run_id = %s ORDER BY proposal_id
            """,
            (str(run.run_id),),
        ).fetchall()
        if tuple(_payload(row[0]) for row in gate_rows) != tuple(item.to_canonical_dict() for item in run.gate_attributions):
            raise ValueError("Strategy Run gate projection mismatch")
        if tuple(_payload(row[0]) for row in proposal_rows) != tuple(item.to_canonical_dict() for item in run.proposals):
            raise ValueError("Strategy Run proposal projection mismatch")


def _require_proposal_version(
    connection: Any,
    *,
    proposal_id: ArtifactId,
    proposal_hash: str,
    strategy_version_id: ArtifactId,
    strategy_version_hash: str,
) -> None:
    row = connection.execute(
        """
        SELECT 1 FROM strategy_proposal
        WHERE proposal_id = %s AND proposal_hash = %s
          AND strategy_version_id = %s AND strategy_version_hash = %s
        FOR SHARE
        """,
        (
            str(proposal_id),
            proposal_hash,
            str(strategy_version_id),
            strategy_version_hash,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("Proposal/Version lineage is not owner-resolved")


def _require_executable_allocation(
    connection: Any,
    *,
    batch: FillAllocationBatch,
    allocation: FillAllocation,
) -> None:
    row = connection.execute(
        """
        SELECT p.action, p.symbol, l.accepted_weight
        FROM strategy_proposal AS p
        JOIN cross_strategy_portfolio_line AS l
          ON l.proposal_id = p.proposal_id
         AND l.proposal_hash = p.proposal_hash
        WHERE p.proposal_id = %s AND p.proposal_hash = %s
        FOR SHARE OF p, l
        """,
        (
            str(allocation.proposal_reference.artifact_id),
            allocation.proposal_reference.content_hash,
        ),
    ).fetchone()
    if row is None or Decimal(str(row[2])) == 0:
        raise ValueError("Fill allocation requires an accepted Portfolio line")
    if str(row[1]) != batch.symbol:
        raise ValueError("Fill symbol does not match Strategy Proposal")
    action = str(row[0])
    if (batch.side.value == "BUY" and action not in {"ENTER", "ADD"}) or (
        batch.side.value == "SELL" and action not in {"REDUCE", "EXIT"}
    ):
        raise ValueError("Fill side does not match Strategy action")
    trade_row = connection.execute(
        """
        SELECT t.aggregate_json
        FROM manual_fills AS f
        JOIN manual_trade_records AS t
          ON t.manual_trade_id = f.manual_trade_id
        WHERE f.fill_id = %s
        FOR SHARE OF f, t
        """,
        (str(batch.source_fill_id),),
    ).fetchone()
    if trade_row is None:
        raise ValueError("Fill Allocation requires a Manual Execution owner")
    raw_trade = trade_row[0]
    if isinstance(raw_trade, str):
        raw_trade = json.loads(raw_trade)
    if not isinstance(raw_trade, dict):
        raise ValueError("Manual Execution owner payload is invalid")
    try:
        trade = ManualTradeRecord.from_canonical_dict(raw_trade)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Fill Allocation requires Strategy-authorized execution"
        ) from exc
    authorization = trade.strategy_execution_authorization
    if (
        trade.authority_route is not ManualTradeAuthorityRoute.STRATEGY
        or authorization is None
    ):
        raise ValueError("Fill Allocation requires Strategy-authorized execution")
    if (
        trade.account_id != batch.account_id
        or trade.symbol != batch.symbol
        or trade.side is not batch.side
        or authorization.proposal_reference != allocation.proposal_reference
        or authorization.strategy_version_reference
        != allocation.strategy_version_reference
        or trade.filled_quantity > authorization.intended_quantity
    ):
        raise ValueError("Fill Allocation exceeds or mismatches Strategy authority")
    if batch.correction_of_fill_id is not None:
        original = connection.execute(
            """
            SELECT a.proposal_id, a.proposal_hash,
                   a.strategy_version_id, a.strategy_version_hash
            FROM strategy_fill_allocation_batch AS b
            JOIN strategy_fill_allocation AS a ON a.batch_id = b.batch_id
            WHERE b.source_fill_id = %s
            FOR SHARE OF b, a
            """,
            (str(batch.correction_of_fill_id),),
        ).fetchone()
        if original is None or (
            str(original[0])
            != str(allocation.proposal_reference.artifact_id)
            or str(original[1]) != allocation.proposal_reference.content_hash
            or str(original[2])
            != str(allocation.strategy_version_reference.artifact_id)
            or str(original[3])
            != allocation.strategy_version_reference.content_hash
        ):
            raise ValueError("Fill Correction allocation lineage mismatch")


def _require_path_outcome_lineage(
    connection: Any,
    outcome: StrategyPathOutcome,
) -> None:
    row = connection.execute(
        """
        SELECT r.run_hash, r.strategy_version_id, r.strategy_version_hash,
               c.dataset_id, c.dataset_hash, c.decision_time,
               sc.payload_json
        FROM strategy_run r
        JOIN multi_strategy_cycle c
          ON c.cycle_id = r.cycle_id AND c.cycle_hash = r.cycle_hash
        JOIN strategy_version v
          ON v.version_id = r.strategy_version_id
         AND v.version_hash = r.strategy_version_hash
        JOIN strategy_contract sc
          ON sc.contract_id = v.contract_id
         AND sc.contract_hash = v.contract_hash
        WHERE r.run_id = %s
        FOR SHARE OF r, c, v, sc
        """,
        (str(outcome.strategy_run_reference.artifact_id),),
    ).fetchone()
    if row is None:
        raise ValueError("Path Outcome requires an owner-resolved Strategy Run")
    if (
        str(row[0]) != outcome.strategy_run_reference.content_hash
        or str(row[1]) != str(outcome.strategy_version_reference.artifact_id)
        or str(row[2]) != outcome.strategy_version_reference.content_hash
    ):
        raise ValueError("Path Outcome Run/Version lineage is not owner-resolved")
    if (
        str(row[3]) != str(outcome.dataset_reference.artifact_id)
        or str(row[4]) != outcome.dataset_reference.content_hash
    ):
        raise ValueError("Path Outcome Dataset lineage is not owner-resolved")
    if row[5] != outcome.decision_time:
        raise ValueError("Path Outcome Decision Time differs from its Strategy Cycle")
    contract = _payload(row[6])
    target_references = contract.get("target_references")
    if (
        not isinstance(target_references, list)
        or outcome.target_reference.to_canonical_dict() not in target_references
    ):
        raise ValueError("Path Outcome Target is not owned by its Strategy Contract")
    horizons = contract.get("horizon_sessions")
    if not isinstance(horizons, list) or outcome.horizon_sessions not in {
        int(value) for value in horizons
    }:
        raise ValueError("Path Outcome horizon is not owned by its Strategy Contract")


def _require_feedback_lineage(
    connection: Any,
    artifact: StrategyFeedbackArtifact,
) -> None:
    if artifact.artifact_kind is StrategyFeedbackKind.QUALIFICATION_DECISION and any(
        value == "true" for _, value in artifact.metrics
    ):
        raise ValueError(
            "positive qualification evidence must be owner-resolved, not caller asserted"
        )

    if artifact.artifact_kind is StrategyFeedbackKind.ATTRIBUTION:
        if artifact.status is StrategyFeedbackStatus.NOT_ESTIMABLE:
            if artifact.source_references != (artifact.strategy_version_reference,):
                raise ValueError(
                    "NOT_ESTIMABLE Attribution must source its exact Strategy Version"
                )
            return
        if any(
            item.reference_kind != "STRATEGY_PATH_OUTCOME"
            for item in artifact.source_references
        ):
            raise ValueError("Attribution requires Path Outcome sources")
        for source in artifact.source_references:
            row = connection.execute(
                """
                SELECT created_at FROM strategy_path_outcome
                WHERE outcome_id = %s AND outcome_hash = %s
                  AND strategy_version_id = %s AND strategy_version_hash = %s
                FOR SHARE
                """,
                (
                    str(source.artifact_id),
                    source.content_hash,
                    str(artifact.strategy_version_reference.artifact_id),
                    artifact.strategy_version_reference.content_hash,
                ),
            ).fetchone()
            if row is None:
                raise ValueError(
                    "Attribution Path Outcome/Version lineage is not owner-resolved"
                )
            if artifact.created_at < row[0]:
                raise ValueError("Attribution predates its stored Path Outcome")
        return

    expected_kinds = (
        {"STRATEGY_ATTRIBUTION"}
        if artifact.artifact_kind is StrategyFeedbackKind.CHALLENGER_EVALUATION
        else {"STRATEGY_ATTRIBUTION", "STRATEGY_CHALLENGER_EVALUATION"}
    )
    source_kinds = {item.reference_kind for item in artifact.source_references}
    expected_count = 2
    if len(artifact.source_references) != expected_count or source_kinds != expected_kinds:
        raise ValueError("Strategy Feedback source kinds do not match artifact kind")

    source_versions: list[tuple[str, str, str]] = []
    for source in artifact.source_references:
        row = connection.execute(
            """
            SELECT f.artifact_kind, f.strategy_version_id,
                   f.strategy_version_hash, f.created_at, v.family
            FROM strategy_feedback_artifact f
            JOIN strategy_version v
              ON v.version_id = f.strategy_version_id
             AND v.version_hash = f.strategy_version_hash
            WHERE f.artifact_id = %s AND f.artifact_hash = %s
            FOR SHARE OF f, v
            """,
            (str(source.artifact_id), source.content_hash),
        ).fetchone()
        if row is None or source.reference_kind != f"STRATEGY_{row[0]}":
            raise ValueError("Strategy Feedback source is not owner-resolved")
        if artifact.created_at < row[3]:
            raise ValueError("Strategy Feedback predates a stored source")
        source_versions.append((str(row[1]), str(row[2]), str(row[4])))

    artifact_version = (
        str(artifact.strategy_version_reference.artifact_id),
        artifact.strategy_version_reference.content_hash,
    )
    if artifact.artifact_kind is StrategyFeedbackKind.CHALLENGER_EVALUATION:
        if len(set(source_versions)) != 2:
            raise ValueError("Challenger sources must be distinct Strategy Versions")
        if len({item[2] for item in source_versions}) != 1:
            raise ValueError("Challenger sources must belong to one Strategy Family")
        if artifact_version not in {(item[0], item[1]) for item in source_versions}:
            raise ValueError("Challenger artifact must bind its Challenger Version")
        return

    if any((item[0], item[1]) != artifact_version for item in source_versions):
        raise ValueError("Qualification sources must bind its exact Strategy Version")


def _require_stored_payload(
    connection: Any,
    *,
    table: str,
    id_column: str,
    identity: str,
    hash_column: str | None,
    expected_hash: str | None,
    expected_payload: dict[str, Any],
) -> None:
    allowed = {
        "strategy_contract",
        "strategy_version",
        "multi_strategy_cycle",
        "strategy_run",
        "strategy_gate_attribution",
        "strategy_proposal",
        "cross_strategy_portfolio_decision",
        "cross_strategy_portfolio_line",
        "strategy_fill_allocation_batch",
        "strategy_fill_allocation",
        "strategy_path_outcome",
        "strategy_feedback_artifact",
    }
    if table not in allowed:
        raise ValueError("unsupported immutable payload table")
    columns = "payload_json" if hash_column is None else f"{hash_column}, payload_json"
    row = connection.execute(
        f"SELECT {columns} FROM {table} WHERE {id_column} = %s FOR UPDATE",
        (identity,),
    ).fetchone()
    if row is None:
        raise ValueError(f"{table} write did not persist")
    stored_hash = expected_hash if hash_column is None else str(row[0])
    stored_payload = _payload(row[0] if hash_column is None else row[1])
    if stored_hash != expected_hash or stored_payload != expected_payload:
        raise ValueError(f"{table} immutable identity conflict")


def _payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("PostgreSQL Strategy payload must be an object")
    return value


__all__ = ["PostgresMultiStrategyRepository"]
