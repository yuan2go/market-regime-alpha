"""PostgreSQL persistence for canonical multi-Strategy business facts."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.strategies.contracts import (
    MultiStrategyCycle,
    StrategyContract,
    StrategyRegistry,
    StrategyVersion,
)
from market_regime_alpha.strategies.feedback import (
    StrategyFeedbackArtifact,
    StrategyFeedbackKind,
)
from market_regime_alpha.strategies.path_outcomes import StrategyPathOutcome
from market_regime_alpha.strategies.portfolio import (
    CrossStrategyPortfolioDecision,
)
from market_regime_alpha.strategies.sleeves import FillAllocationBatch


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
                line_payload = line.to_canonical_dict()
                line_id = f"cross-strategy-line:{canonical_hash({'decision_id': str(decision.decision_id), 'line': line_payload})[7:]}"
                connection.execute(
                    """
                    INSERT INTO cross_strategy_portfolio_line(
                        line_id, decision_id, proposal_id, proposal_hash,
                        strategy_version_id, symbol, requested_weight,
                        accepted_weight, payload_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (line_id) DO NOTHING
                    """,
                    (
                        line_id,
                        str(decision.decision_id),
                        str(line.proposal_reference.artifact_id),
                        line.proposal_reference.content_hash,
                        str(line.strategy_version_reference.artifact_id),
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
